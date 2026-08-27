"""桌码管理新增能力：桌号防呆、停用/删除边界、批量打包下载。

沿用 test_entrance_code_coupon_template_tenant_isolation.py 的内存库夹具，
`_generate_code_image` 一律打桩，不联网。
"""

import asyncio
import io
import os
import unittest
import zipfile
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.services.entrance_code_service import EntranceCodeService, ENTRANCE_CODE_DIR

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


class EntranceCodeManagementTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        TenantContext.set_tenant_id(TENANT_A)
        self._written = []

    async def asyncTearDown(self):
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()
        for path in self._written:
            try:
                os.remove(path)
            except OSError:
                pass

    def _service(self, tenant_id=TENANT_A):
        service = EntranceCodeService(self.db)
        service.set_tenant_id(tenant_id)

        async def fake_generate_code_image(scene, *args, **kwargs):
            return {
                "image_url": f"/static/entrance-codes/{scene}.png",
                "code_type": "QR",
                "generation_status": "SUCCESS",
                "generation_error": None,
            }

        service._generate_code_image = fake_generate_code_image
        return service

    def _touch_image(self, scene):
        os.makedirs(ENTRANCE_CODE_DIR, exist_ok=True)
        path = os.path.join(ENTRANCE_CODE_DIR, f"{scene}.png")
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
        self._written.append(path)
        return path

    async def test_duplicate_active_table_no_is_rejected(self):
        service = self._service()
        await service.create_entrance_code(name="A01", channel="TABLE", table_no="A01")

        with self.assertRaisesRegex(ValueError, "已有启用中的桌贴码"):
            await service.create_entrance_code(name="A01 again", channel="TABLE", table_no=" A01 ")

        rows = (await self.db.execute(select(EntranceCode))).scalars().all()
        self.assertEqual(len(rows), 1)

    async def test_disabled_table_no_can_be_recreated(self):
        service = self._service()
        first = await service.create_entrance_code(name="A01", channel="TABLE", table_no="A01")
        await service.update_status(first.id, 0)

        again = await service.create_entrance_code(name="A01 v2", channel="TABLE", table_no="A01")
        self.assertNotEqual(again.id, first.id)

    async def test_other_tenant_same_table_no_is_fine(self):
        await self._service(TENANT_A).create_entrance_code(name="A01", channel="TABLE", table_no="A01")
        code_b = await self._service(TENANT_B).create_entrance_code(name="A01", channel="TABLE", table_no="A01")
        self.assertEqual(code_b.tenant_id, TENANT_B)

    async def test_delete_blocked_when_code_has_scans(self):
        service = self._service()
        code = await service.create_entrance_code(name="A01", channel="TABLE", table_no="A01")
        code.scan_count = 3
        await self.db.commit()

        with self.assertRaisesRegex(ValueError, "已有扫码记录"):
            await service.delete_entrance_code(code.id)
        self.assertIsNotNone(await service.get_tenant_code(code.id))

    async def test_delete_allowed_when_never_scanned(self):
        service = self._service()
        code = await service.create_entrance_code(name="A02", channel="TABLE", table_no="A02")
        self.assertTrue(await service.delete_entrance_code(code.id))
        self.assertIsNone(await service.get_tenant_code(code.id))

    async def test_build_zip_names_entries_by_table_no(self):
        service = self._service()
        c1 = await service.create_entrance_code(name="一号桌", channel="TABLE", table_no="A01")
        c2 = await service.create_entrance_code(name="二号桌", channel="TABLE", table_no="A02")
        self._touch_image(c1.scene)
        self._touch_image(c2.scene)

        name, blob = await service.build_codes_zip([c1.id, c2.id])
        self.assertEqual(name, "桌贴码.zip")
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            self.assertEqual(sorted(zf.namelist()), ["A01.png", "A02.png"])

    async def test_build_zip_rejects_other_tenants_codes(self):
        mine = await self._service(TENANT_A).create_entrance_code(name="A01", channel="TABLE", table_no="A01")
        theirs = await self._service(TENANT_B).create_entrance_code(name="B01", channel="TABLE", table_no="B01")
        self._touch_image(mine.scene)
        self._touch_image(theirs.scene)

        _, blob = await self._service(TENANT_A).build_codes_zip([mine.id, theirs.id])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            self.assertEqual(zf.namelist(), ["A01.png"])

    async def test_build_zip_raises_when_no_images_on_disk(self):
        service = self._service()
        code = await service.create_entrance_code(name="A01", channel="TABLE", table_no="A01")
        with self.assertRaisesRegex(ValueError, "还没有生成图片"):
            await service.build_codes_zip([code.id])

    async def test_build_zip_needs_at_least_one_id(self):
        with self.assertRaisesRegex(ValueError, "请选择"):
            await self._service().build_codes_zip([])

    async def test_response_serializes_bigint_id_as_string(self):
        # admin-h5 的 axios 用普通 JSON.parse，19 位数字型 ID 会被舍入，
        # 回传时对不上行。出参里 id 必须是字符串，且精度不丢。
        from fastapi.encoders import jsonable_encoder

        from app.schemas.entrance_code import EntranceCodeResponse

        service = self._service()
        code = await service.create_entrance_code(name="A01", channel="TABLE", table_no="A01")
        payload = jsonable_encoder(EntranceCodeResponse.model_validate(code))
        self.assertIsInstance(payload["id"], str)
        self.assertEqual(payload["id"], str(code.id))


if __name__ == "__main__":
    unittest.main()
