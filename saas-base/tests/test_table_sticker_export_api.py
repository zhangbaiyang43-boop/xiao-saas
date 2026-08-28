import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.entrance_codes as entrance_codes_api
from app.api.v1.entrance_codes import export_table_stickers, router
from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.tenant import Tenant
from app.schemas.entrance_code import TableStickerExportRequest
from app.services.table_sticker_export_service import ExportArtifact


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


TENANT_A_CODE_ID = 910001
TENANT_B_CODE_ID = 920001
INVALID_CODE_ID_START = 930001


def _code(code_id: int, tenant_id: str, **overrides) -> EntranceCode:
    values = {
        "id": code_id,
        "tenant_id": tenant_id,
        "name": f"table-{code_id}",
        "channel": "TABLE",
        "scene": f"scene-{code_id}",
        "page": "pages/entry/index",
        "image_url": f"/static/entrance-codes/{code_id}.png",
        "env_version": "release",
        "code_type": "WECHAT",
        "generation_status": "SUCCESS",
        "status": 1,
        "scan_count": 0,
        "member_count": 0,
        "table_no": f"A{code_id}",
        "entry_type": "table",
        "order_mode": "dine_in",
        "target_page": "subpkg-order/pages/menu",
    }
    values.update(overrides)
    return EntranceCode(**values)


class TableStickerExportApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(
                    id=900001,
                    tenant_id="tenant-a",
                    name="甲商户",
                    password_hash="test",
                    phone="13800000001",
                ),
                Tenant(
                    id=900002,
                    tenant_id="tenant-b",
                    name="乙商户",
                    password_hash="test",
                    phone="13800000002",
                ),
                _code(TENANT_A_CODE_ID, "tenant-a"),
                _code(TENANT_B_CODE_ID, "tenant-b"),
                _code(INVALID_CODE_ID_START, "tenant-a", channel="STORE"),
                _code(INVALID_CODE_ID_START + 1, "tenant-a", entry_type="poster"),
                _code(INVALID_CODE_ID_START + 2, "tenant-a", status=0),
                _code(INVALID_CODE_ID_START + 3, "tenant-a", env_version="trial"),
                _code(INVALID_CODE_ID_START + 4, "tenant-a", generation_status="FAILED"),
                _code(INVALID_CODE_ID_START + 5, "tenant-a", table_no=" "),
                _code(INVALID_CODE_ID_START + 6, "tenant-a", image_url=None),
                _code(INVALID_CODE_ID_START + 7, "tenant-a", image_url="   "),
            ]
        )
        await self.db.commit()
        TenantContext.set_tenant_id("tenant-a")

    async def asyncTearDown(self):
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()

    async def test_request_model_only_accepts_camel_case_with_one_to_one_hundred_unique_ids(self):
        request = TableStickerExportRequest.model_validate({"entranceCodeIds": ["101", "102"]})
        self.assertEqual(request.entrance_code_ids, [101, 102])
        self.assertEqual(request.model_dump(by_alias=True), {"entranceCodeIds": [101, 102]})

        invalid_payloads = (
            {"entranceCodeIds": ["101", "101"]},
            {"entranceCodeIds": []},
            {"entranceCodeIds": list(range(101))},
            {"entrance_code_ids": [101]},
            {"ids": [101]},
            {"entranceCodeIds": [101], "ids": [202]},
            {"entranceCodeIds": [101], "entrance_code_ids": [202]},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                TableStickerExportRequest.model_validate(payload)

    async def test_other_tenant_id_has_same_failure_as_missing_id(self):
        foreign = await export_table_stickers(
            TableStickerExportRequest.model_validate({"entranceCodeIds": [str(TENANT_B_CODE_ID)]}),
            db=self.db,
        )
        missing = await export_table_stickers(
            TableStickerExportRequest.model_validate({"entranceCodeIds": ["999999"]}),
            db=self.db,
        )

        self.assertEqual(foreign.code, 422)
        self.assertEqual(foreign.code, missing.code)
        self.assertEqual(foreign.msg, missing.msg)
        self.assertNotIn(str(TENANT_B_CODE_ID), foreign.msg)

    async def test_each_ineligible_record_property_returns_the_same_safe_error(self):
        for offset in range(8):
            code_id = INVALID_CODE_ID_START + offset
            with self.subTest(code_id=code_id):
                response = await export_table_stickers(
                    TableStickerExportRequest.model_validate({"entranceCodeIds": [str(code_id)]}),
                    db=self.db,
                )
                self.assertEqual(response.code, 422)
                self.assertEqual(response.msg, "桌码状态已变化，请刷新后重新选择")

    async def test_missing_tenant_context_uses_existing_error_response_contract(self):
        TenantContext.clear()

        response = await export_table_stickers(
            TableStickerExportRequest.model_validate({"entranceCodeIds": [str(TENANT_A_CODE_ID)]}),
            db=self.db,
        )

        self.assertEqual(response.code, 401)
        self.assertEqual(response.msg, "未登录或商户信息已失效")

    async def test_valid_export_returns_zip_from_threadpool_and_background_cleans_it(self):
        caller_thread_id = threading.get_ident()
        observed = {}

        def fake_build_bundle(service, codes, merchant_name):
            observed["thread_id"] = threading.get_ident()
            observed["code_ids"] = [code.id for code in codes]
            observed["merchant_name"] = merchant_name
            temp_dir = Path(tempfile.mkdtemp(prefix="table-stickers-api-test-"))
            zip_path = temp_dir / "bundle.zip"
            zip_path.write_bytes(b"PK\x05\x06" + (b"\x00" * 18))
            return ExportArtifact(zip_path=zip_path, temp_dir=temp_dir, download_name="甲商户-桌贴.zip")

        with patch.object(
            entrance_codes_api.table_sticker_export_service.TableStickerExportService,
            "build_bundle",
            autospec=True,
            side_effect=fake_build_bundle,
        ):
            response = await export_table_stickers(
                TableStickerExportRequest.model_validate({"entranceCodeIds": [str(TENANT_A_CODE_ID)]}),
                db=self.db,
            )

        artifact_dir = Path(response.path).parent
        self.assertEqual(response.media_type, "application/zip")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(observed["code_ids"], [TENANT_A_CODE_ID])
        self.assertEqual(observed["merchant_name"], "甲商户")
        self.assertNotEqual(observed["thread_id"], caller_thread_id)
        self.assertTrue(artifact_dir.exists())

        await response.background()

        self.assertFalse(artifact_dir.exists())

    async def test_static_export_route_is_registered_before_dynamic_code_route(self):
        paths = [route.path for route in router.routes]
        self.assertLess(
            paths.index("/api/v1/entrance-codes/table-stickers/export"),
            paths.index("/api/v1/entrance-codes/{code_id}"),
        )


if __name__ == "__main__":
    unittest.main()
