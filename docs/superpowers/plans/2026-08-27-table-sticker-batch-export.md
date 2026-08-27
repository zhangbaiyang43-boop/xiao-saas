# Table Sticker Batch Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tenant-safe one-click export in table-code management that downloads 10 × 12 cm print-ready PNGs, a one-sticker-per-page PDF, and an A4 four-up PDF in one ZIP.

**Architecture:** Keep existing entrance-code creation and scan resolution untouched. A new backend `TableStickerExportService` validates existing table-code records and source images, renders bounded temporary files with Pillow, and returns a ZIP through one binary endpoint; the admin page owns selection and download state while a focused dialog only presents confirmation.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy async, Pillow 10.4, Python `tempfile`/`zipfile`, Vue 3, Ant Design Vue, Axios, Node built-in test runner.

---

## File map

### Backend

- Create `saas-base/app/services/table_sticker_export_service.py` — source-image validation, fixed-layout PNG rendering, bounded-memory PDF creation, ZIP packaging, cleanup artifact.
- Create `saas-base/app/assets/fonts/NotoSansSC-Bold.otf` — vendored Simplified Chinese print font from the official Noto CJK `Sans2.004` release.
- Create `saas-base/app/assets/fonts/OFL.txt` — font license shipped with the binary asset.
- Modify `saas-base/app/schemas/entrance_code.py` — add the isolated camelCase export request model.
- Modify `saas-base/app/api/v1/entrance_codes.py` — add the static export route before `/{code_id}` routes.
- Create `saas-base/tests/test_table_sticker_export_service.py` — renderer, path safety, dimensions, PDF, ZIP, and cleanup tests.
- Create `saas-base/tests/test_table_sticker_export_api.py` — request contract, tenant isolation, record validation, binary response, and background cleanup tests.

### Admin

- Create `admin-h5/src/utils/tableStickerExport.js` — pure eligibility, selection, Blob error, filename, and browser-download helpers.
- Create `admin-h5/src/components/TableStickerExportDialog.vue` — presentational confirmation drawer.
- Modify `admin-h5/src/api/index.js` — add the isolated Blob export request with its own timeout.
- Modify `admin-h5/src/views/EntranceCodeList.vue` — selection toolbar, row checkboxes, confirmation, and download orchestration.
- Create `admin-h5/scripts/test-table-sticker-export.mjs` — executable helper and source-wiring contracts.
- Modify `admin-h5/package.json` — add only a test script; no dependency changes.

### Documentation/artifacts

- Use `outputs/table-sticker-sample/` only for local visual QA output. Do not commit generated customer codes, ZIPs, PDFs, or sample images.

## Non-negotiable constraints

- Do not modify the database, migrations, existing entrance-code response fields, source code generation, scan resolution, or miniapp.
- Do not add npm or Python dependencies.
- Do not accept arbitrary image URLs. Only resolve `/static/entrance-codes/<basename>` under the existing entrance-code directory.
- Require `channel == "TABLE"`, `entry_type == "table"`, `status == 1`, `env_version == "release"`, `generation_status == "SUCCESS"`, nonblank `table_no`, and a decodable image.
- Treat a missing request ID and an ID owned by another tenant identically.
- Generate all files or none. A backend validation race must return JSON error data and no partial ZIP.
- Keep PDF creation memory-bounded by appending one page at a time; never materialize 100 RGB canvases in a list.

### Task 1: Vendor and verify the print font

**Files:**
- Create: `saas-base/app/assets/fonts/NotoSansSC-Bold.otf`
- Create: `saas-base/app/assets/fonts/OFL.txt`
- Create: `saas-base/tests/test_table_sticker_export_service.py`

- [ ] **Step 1: Write the failing font asset test**

Create the test file with this initial content:

```python
from pathlib import Path
import unittest

from PIL import ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "app" / "assets" / "fonts"
FONT_PATH = FONT_DIR / "NotoSansSC-Bold.otf"
LICENSE_PATH = FONT_DIR / "OFL.txt"


class TableStickerFontAssetTests(unittest.TestCase):
    def test_bundled_font_and_license_are_loadable(self):
        self.assertTrue(FONT_PATH.is_file())
        self.assertTrue(LICENSE_PATH.is_file())
        font = ImageFont.truetype(str(FONT_PATH), 64)
        self.assertGreater(font.getlength("扫码点餐 A01桌"), 0)
        self.assertIn("SIL OPEN FONT LICENSE", LICENSE_PATH.read_text(encoding="utf-8").upper())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
cd C:\Users\15936\Desktop\xiao\saas-base
py -3.10 -m pytest tests/test_table_sticker_export_service.py -q
```

Expected: FAIL because `NotoSansSC-Bold.otf` and `OFL.txt` do not exist.

- [ ] **Step 3: Download the immutable official font release into a temporary directory**

Use the official Noto CJK `Sans2.004` Simplified Chinese subset release:

```powershell
$stickerFontTemp = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("table-sticker-font-" + [guid]::NewGuid()))
Invoke-WebRequest -Uri "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/18_NotoSansSC.zip" -OutFile (Join-Path $stickerFontTemp "NotoSansSC.zip")
Expand-Archive -LiteralPath (Join-Path $stickerFontTemp "NotoSansSC.zip") -DestinationPath (Join-Path $stickerFontTemp "font")
New-Item -ItemType Directory -Force -Path "app\assets\fonts"
Copy-Item -LiteralPath (Join-Path $stickerFontTemp "font\NotoSansSC-Bold.otf") -Destination "app\assets\fonts\NotoSansSC-Bold.otf"
Copy-Item -LiteralPath (Join-Path $stickerFontTemp "font\LICENSE") -Destination "app\assets\fonts\OFL.txt"
```

Do not copy any other weights. After the two required files are verified inside the repository, remove only the resolved `$stickerFontTemp` directory.

- [ ] **Step 4: Run the font test and verify GREEN**

Run the same pytest command. Expected: `1 passed`.

- [ ] **Step 5: Commit the isolated asset task**

```powershell
git add -- saas-base/app/assets/fonts/NotoSansSC-Bold.otf saas-base/app/assets/fonts/OFL.txt saas-base/tests/test_table_sticker_export_service.py
git commit -m "chore: bundle table sticker print font"
```

### Task 2: Add the single-sticker renderer and source safety

**Files:**
- Create: `saas-base/app/services/table_sticker_export_service.py`
- Modify: `saas-base/tests/test_table_sticker_export_service.py`

- [ ] **Step 1: Add failing tests for path safety, image validation, dimensions, and table-number fitting**

Append tests that create a square RGB fixture inside a temporary `entrance-codes` directory and assert this public interface:

```python
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PIL import Image

from app.services.table_sticker_export_service import (
    STICKER_HEIGHT,
    STICKER_WIDTH,
    TableStickerExportError,
    TableStickerExportService,
)


class TableStickerRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.code_dir = self.root / "entrance-codes"
        self.code_dir.mkdir()
        self.service = TableStickerExportService(entrance_code_dir=self.code_dir)

    def tearDown(self):
        self.temp.cleanup()

    def make_code(self, table_no="A01", image_name="code.png"):
        Image.new("RGB", (430, 430), "white").save(self.code_dir / image_name)
        return SimpleNamespace(
            id=101,
            tenant_id="tenant-a",
            channel="TABLE",
            entry_type="table",
            status=1,
            env_version="release",
            generation_status="SUCCESS",
            image_url=f"/static/entrance-codes/{image_name}",
            table_no=table_no,
        )

    def test_render_png_has_exact_print_dimensions(self):
        sticker = self.service.render_sticker(self.make_code())
        self.assertEqual(sticker.size, (STICKER_WIDTH, STICKER_HEIGHT))
        self.assertEqual(sticker.mode, "RGB")

    def test_source_path_cannot_escape_entrance_code_directory(self):
        code = self.make_code()
        code.image_url = "/static/entrance-codes/../secret.png"
        with self.assertRaisesRegex(TableStickerExportError, "桌码图片无效"):
            self.service.render_sticker(code)

    def test_corrupt_source_is_rejected(self):
        bad = self.code_dir / "bad.png"
        bad.write_bytes(b"not-an-image")
        with self.assertRaisesRegex(TableStickerExportError, "桌码图片损坏"):
            self.service.render_sticker(self.make_code(image_name="bad.png"))

    def test_unfittable_table_number_is_rejected(self):
        with self.assertRaisesRegex(TableStickerExportError, "桌号过长"):
            self.service.render_sticker(self.make_code(table_no="超长桌号" * 12))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
py -3.10 -m pytest tests/test_table_sticker_export_service.py -q
```

Expected: import failure for `app.services.table_sticker_export_service`.

- [ ] **Step 3: Implement the minimal renderer service**

Create `table_sticker_export_service.py` with these concrete boundaries and constants:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from app.services.entrance_code_service import ENTRANCE_CODE_DIR


DPI = 300
STICKER_WIDTH = 1181
STICKER_HEIGHT = 1417
A4_WIDTH = 2480
A4_HEIGHT = 3508
QR_SIZE = 732
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_DIMENSION = 4096
FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC-Bold.otf"
SAFE_IMAGE_PREFIX = "/static/entrance-codes/"


class TableStickerExportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExportArtifact:
    zip_path: Path
    temp_dir: Path
    download_name: str


class TableStickerExportService:
    def __init__(self, db=None, entrance_code_dir: str | Path = ENTRANCE_CODE_DIR):
        self.db = db
        self.entrance_code_dir = Path(entrance_code_dir).resolve()

    def _font(self, size: int):
        if not FONT_PATH.is_file():
            raise TableStickerExportError("FONT_MISSING", "桌贴印刷字体缺失")
        return ImageFont.truetype(str(FONT_PATH), size)

    def _source_path(self, image_url: str | None) -> Path:
        if not image_url or not image_url.startswith(SAFE_IMAGE_PREFIX):
            raise TableStickerExportError("IMAGE_INVALID", "桌码图片无效")
        relative = image_url[len(SAFE_IMAGE_PREFIX):]
        if not relative or Path(relative).name != relative:
            raise TableStickerExportError("IMAGE_INVALID", "桌码图片无效")
        candidate = (self.entrance_code_dir / relative).resolve()
        if candidate.parent != self.entrance_code_dir:
            raise TableStickerExportError("IMAGE_INVALID", "桌码图片无效")
        if not candidate.is_file() or candidate.stat().st_size > MAX_SOURCE_BYTES:
            raise TableStickerExportError("IMAGE_INVALID", "桌码图片无效")
        return candidate

    def _load_source(self, image_url: str | None) -> Image.Image:
        path = self._source_path(image_url)
        try:
            with Image.open(path) as probe:
                if max(probe.size) > MAX_SOURCE_DIMENSION:
                    raise TableStickerExportError("IMAGE_INVALID", "桌码图片尺寸异常")
                probe.verify()
            with Image.open(path) as source:
                source.load()
                if source.width != source.height or source.width < 300:
                    raise TableStickerExportError("IMAGE_INVALID", "桌码图片必须为完整正方形")
                return source.convert("RGB")
        except TableStickerExportError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise TableStickerExportError("IMAGE_CORRUPT", "桌码图片损坏") from exc

    def _fit_table_font(self, draw: ImageDraw.ImageDraw, text: str, max_width: int):
        for size in range(150, 59, -6):
            font = self._font(size)
            if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
                return font
        raise TableStickerExportError("TABLE_NO_TOO_LONG", f"桌号过长：{text}")

    def render_sticker(self, code) -> Image.Image:
        table_no = str(getattr(code, "table_no", "") or "").strip()
        if not table_no:
            raise TableStickerExportError("TABLE_NO_MISSING", "桌号不能为空")
        source = self._load_source(getattr(code, "image_url", None))
        canvas = Image.new("RGB", (STICKER_WIDTH, STICKER_HEIGHT), "white")
        draw = ImageDraw.Draw(canvas)

        draw.rounded_rectangle((18, 18, 1163, 1399), radius=60, outline="#D1D5DB", width=5)
        draw.text((72, 72), "扫码点餐", fill="#050505", font=self._font(146))
        draw.text((76, 270), "微信扫码 · 本桌下单", fill="#334155", font=self._font(54))

        badge = (785, 64, 1107, 252)
        draw.rounded_rectangle(badge, radius=42, fill="#08A83C")
        table_text = f"{table_no}桌"
        table_font = self._fit_table_font(draw, table_text, badge[2] - badge[0] - 34)
        box = draw.textbbox((0, 0), table_text, font=table_font)
        draw.text(
            ((badge[0] + badge[2] - (box[2] - box[0])) / 2, (badge[1] + badge[3] - (box[3] - box[1])) / 2 - box[1]),
            table_text,
            fill="white",
            font=table_font,
        )

        resized = source.resize((QR_SIZE, QR_SIZE), Image.Resampling.LANCZOS)
        try:
            canvas.paste(resized, ((STICKER_WIDTH - QR_SIZE) // 2, 360))
        finally:
            resized.close()
            source.close()

        footer = "加菜也扫这里"
        footer_font = self._font(86)
        footer_box = draw.textbbox((0, 0), footer, font=footer_font)
        draw.text(((STICKER_WIDTH - footer_box[2]) / 2, 1240), footer, fill="#050505", font=footer_font)
        return canvas
```

Do not add optional templates or customization hooks.

- [ ] **Step 4: Run the service tests and verify GREEN**

Expected: all font, path-safety, corrupt-image, dimensions, and table-number tests pass.

- [ ] **Step 5: Commit the renderer**

```powershell
git add -- saas-base/app/services/table_sticker_export_service.py saas-base/tests/test_table_sticker_export_service.py
git commit -m "feat: render print-ready table stickers"
```

### Task 3: Generate PDFs, ZIP, safe filenames, and bounded cleanup

**Files:**
- Modify: `saas-base/app/services/table_sticker_export_service.py`
- Modify: `saas-base/tests/test_table_sticker_export_service.py`

- [ ] **Step 1: Add failing bundle tests**

Add tests for 1, 4, and 5 fixtures. Open the resulting ZIP and assert exact entries, PNG dimensions, PDF page counts and MediaBox sizes, duplicate-name suffixes, traversal-safe names, and cleanup:

```python
import math
import re
import zipfile

PAGE_RE = re.compile(rb"/Type\s*/Page\b")
MEDIA_BOX_RE = re.compile(
    rb"/MediaBox\s*\[\s*0(?:\.0+)?\s+0(?:\.0+)?\s+([0-9.]+)\s+([0-9.]+)\s*\]"
)


def pdf_stats(data):
    boxes = [(float(width), float(height)) for width, height in MEDIA_BOX_RE.findall(data)]
    return len(PAGE_RE.findall(data)), boxes


class TableStickerBundleTests(TableStickerRenderTests):
    def test_bundle_contains_png_and_two_correct_pdfs(self):
        codes = [self.make_code(table_no=f"A{i:02d}", image_name=f"code-{i}.png") for i in range(1, 6)]
        artifact = self.service.build_bundle(codes, merchant_name="测试餐厅")
        try:
            with zipfile.ZipFile(artifact.zip_path) as archive:
                names = archive.namelist()
                self.assertEqual(len([n for n in names if n.startswith("PNG/")]), 5)
                self.assertIn("PDF/单贴印厂版.pdf", names)
                self.assertIn("PDF/A4四联打印版.pdf", names)
                self.assertIn("导出说明.txt", names)
                single_count, single_boxes = pdf_stats(archive.read("PDF/单贴印厂版.pdf"))
                four_up_count, four_up_boxes = pdf_stats(archive.read("PDF/A4四联打印版.pdf"))
                self.assertEqual(single_count, 5)
                self.assertEqual(four_up_count, math.ceil(5 / 4))
                self.assertAlmostEqual(single_boxes[0][0], 100 / 25.4 * 72, places=1)
                self.assertAlmostEqual(single_boxes[0][1], 120 / 25.4 * 72, places=1)
                self.assertAlmostEqual(four_up_boxes[0][0], 210 / 25.4 * 72, places=1)
                self.assertAlmostEqual(four_up_boxes[0][1], 297 / 25.4 * 72, places=1)
        finally:
            artifact.cleanup()
        self.assertFalse(artifact.temp_dir.exists())
```

- [ ] **Step 2: Run the bundle tests and verify RED**

Expected: `build_bundle` and `cleanup` are missing.

- [ ] **Step 3: Implement bounded PDF append and ZIP packaging**

Add these methods and extend `ExportArtifact` with `cleanup()`:

```python
import shutil
import tempfile
import zipfile
from datetime import datetime


@dataclass(frozen=True)
class ExportArtifact:
    zip_path: Path
    temp_dir: Path
    download_name: str

    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", value).strip(" .-")
    return cleaned[:64] or fallback


def _append_pdf_page(pdf_path: Path, image_path: Path, first: bool):
    with Image.open(image_path) as page:
        page.load()
        rgb = page.convert("RGB")
        try:
            rgb.save(
                pdf_path,
                "PDF",
                resolution=DPI,
                quality=95,
                subsampling=0,
                append=not first,
            )
        finally:
            rgb.close()


def _draw_crop_marks(draw: ImageDraw.ImageDraw, x: int, y: int):
    mark = 34
    gap = 10
    color = "#6B7280"
    width = 2
    for px in (x, x + STICKER_WIDTH):
        draw.line((px, y - gap - mark, px, y - gap), fill=color, width=width)
        draw.line((px, y + STICKER_HEIGHT + gap, px, y + STICKER_HEIGHT + gap + mark), fill=color, width=width)
    for py in (y, y + STICKER_HEIGHT):
        draw.line((x - gap - mark, py, x - gap, py), fill=color, width=width)
        draw.line((x + STICKER_WIDTH + gap, py, x + STICKER_WIDTH + gap + mark, py), fill=color, width=width)
```

Implement `build_bundle(codes, merchant_name)` so that it:

1. Creates `Path(tempfile.mkdtemp(prefix="table-stickers-"))`.
2. Creates `PNG` and `PDF` children.
3. Renders and saves one RGB PNG at a time with `dpi=(300, 300)`, then explicitly closes that sticker image before rendering the next code.
4. Uses `_append_pdf_page` once per sticker for the single-page PDF, closing each Pillow image before continuing.
5. Builds one A4 RGB canvas for each four-sticker group, pastes stickers into slots `(59,337)`, `(1240,337)`, `(59,1754)`, `(1240,1754)`, draws crop marks outside each slot, saves that A4 page to a temporary PNG, appends it to the A4 PDF, then deletes the temporary A4 page.
6. Writes UTF-8 `导出说明.txt` with count, date, `100 × 120 mm`, `300 DPI`, and `实际大小/100%`.
7. Creates the ZIP with `ZIP_DEFLATED` and explicit safe arc names.
8. Uses `try/except` to remove the whole temporary directory before re-raising any generation error.
9. Returns `ExportArtifact(zip_path, temp_dir, safe_download_name)` only after the ZIP closes successfully.

For repeated sanitized table names, assign `A01桌.png`, `A01桌-2.png`, `A01桌-3.png` in input order. Never use a set for output ordering.

- [ ] **Step 4: Run bundle tests and inspect memory behavior**

Run:

```powershell
py -3.10 -m pytest tests/test_table_sticker_export_service.py -q
```

Expected: all tests pass. Confirm the implementation contains no list comprehension that calls `render_sticker()` for all codes and no `append_images=[...]` PDF call.

- [ ] **Step 5: Commit bundle generation**

```powershell
git add -- saas-base/app/services/table_sticker_export_service.py saas-base/tests/test_table_sticker_export_service.py
git commit -m "feat: package table sticker print files"
```

### Task 4: Add the tenant-safe export API

**Files:**
- Modify: `saas-base/app/schemas/entrance_code.py`
- Modify: `saas-base/app/api/v1/entrance_codes.py`
- Modify: `saas-base/app/services/table_sticker_export_service.py`
- Create: `saas-base/tests/test_table_sticker_export_api.py`

- [ ] **Step 1: Write failing request and tenant-isolation tests**

Use the existing async SQLite test pattern. Seed tenant A and tenant B codes with explicit IDs and assert:

```python
class TableStickerExportApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_model_uses_camel_case_and_rejects_duplicates(self):
        request = TableStickerExportRequest.model_validate({"entranceCodeIds": ["101", "102"]})
        self.assertEqual(request.entrance_code_ids, [101, 102])
        with self.assertRaises(ValidationError):
            TableStickerExportRequest.model_validate({"entranceCodeIds": ["101", "101"]})

    async def test_other_tenant_id_has_same_failure_as_missing_id(self):
        TenantContext.set_tenant_id("tenant-a")
        foreign = await export_table_stickers(
            TableStickerExportRequest.model_validate({"entranceCodeIds": [str(TENANT_B_CODE_ID)]}),
            db=self.db,
        )
        missing = await export_table_stickers(
            TableStickerExportRequest.model_validate({"entranceCodeIds": ["999999"]}),
            db=self.db,
        )
        self.assertEqual(foreign.code, missing.code)
        self.assertEqual(foreign.msg, missing.msg)

    async def test_valid_export_returns_zip_file_response(self):
        TenantContext.set_tenant_id("tenant-a")
        response = await export_table_stickers(
            TableStickerExportRequest.model_validate({"entranceCodeIds": [str(TENANT_A_CODE_ID)]}),
            db=self.db,
        )
        self.assertEqual(response.media_type, "application/zip")
        self.assertIn("attachment", response.headers["content-disposition"])
        await response.background()
```

Also test each invalid record property: channel, entry type, status, env version, generation status, blank table number, and missing image.

- [ ] **Step 2: Run API tests and verify RED**

Run:

```powershell
py -3.10 -m pytest tests/test_table_sticker_export_api.py -q
```

Expected: missing request model and route.

- [ ] **Step 3: Add the isolated request schema**

Append to `app/schemas/entrance_code.py`:

```python
from pydantic import AliasChoices, field_validator


class TableStickerExportRequest(BaseModel):
    entrance_code_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("entranceCodeIds"),
        serialization_alias="entranceCodeIds",
    )

    @field_validator("entrance_code_ids")
    @classmethod
    def reject_duplicate_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("桌码不能重复")
        return values
```

Use only `entranceCodeIds` as the accepted public field. Do not add aliases for generic `ids` or snake_case request payloads.

- [ ] **Step 4: Add tenant-scoped record loading and validation**

Add an async method to the export service:

```python
from sqlalchemy import select
from app.models.entrance_code import EntranceCode


async def load_valid_codes(self, tenant_id: str, entrance_code_ids: list[int]):
    result = await self.db.execute(
        select(EntranceCode).where(
            EntranceCode.tenant_id == tenant_id,
            EntranceCode.id.in_(entrance_code_ids),
        )
    )
    by_id = {int(code.id): code for code in result.scalars().all()}
    if len(by_id) != len(entrance_code_ids):
        raise TableStickerExportError("TABLE_CODE_INVALID", "桌码状态已变化，请刷新后重新选择")
    ordered = [by_id[value] for value in entrance_code_ids]
    for code in ordered:
        if (
            code.channel != "TABLE"
            or code.entry_type != "table"
            or code.status != 1
            or code.env_version != "release"
            or code.generation_status != "SUCCESS"
            or not str(code.table_no or "").strip()
            or not code.image_url
        ):
            raise TableStickerExportError("TABLE_CODE_INVALID", "桌码状态已变化，请刷新后重新选择")
    return ordered
```

The `tenant_id` predicate must remain in the SQL statement; do not fetch then filter in Python.

- [ ] **Step 5: Add the static export route before `/{code_id}`**

Import `FileResponse`, `BackgroundTask`, `run_in_threadpool`, the new schema, and the service. Add:

```python
@router.post("/table-stickers/export")
async def export_table_stickers(data: TableStickerExportRequest, db=Depends(get_db)):
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        return error_response(code=401, msg="未登录或商户信息已失效")
    service = TableStickerExportService(db)
    try:
        codes = await service.load_valid_codes(tenant_id, data.entrance_code_ids)
        tenant = await TenantService(db).get_tenant(tenant_id)
        artifact = await run_in_threadpool(
            service.build_bundle,
            codes,
            tenant.name if tenant else "商户",
        )
    except TableStickerExportError as exc:
        logger.warning(
            f"[TABLE_STICKER_EXPORT] tenant_id={tenant_id} count={len(data.entrance_code_ids)} success=False error_code={exc.code}"
        )
        return error_response(code=422, msg=exc.message)
    logger.info(
        f"[TABLE_STICKER_EXPORT] tenant_id={tenant_id} count={len(codes)} success=True"
    )
    return FileResponse(
        path=artifact.zip_path,
        media_type="application/zip",
        filename=artifact.download_name,
        background=BackgroundTask(artifact.cleanup),
    )
```

Do not declare `response_model=RespVo` on the binary route.

- [ ] **Step 6: Run backend API and service tests**

Run:

```powershell
py -3.10 -m pytest tests/test_table_sticker_export_service.py tests/test_table_sticker_export_api.py -q
```

Expected: all pass with no network calls and no leftover `table-stickers-*` temporary directories created by tests.

- [ ] **Step 7: Commit the API**

```powershell
git add -- saas-base/app/schemas/entrance_code.py saas-base/app/api/v1/entrance_codes.py saas-base/app/services/table_sticker_export_service.py saas-base/tests/test_table_sticker_export_api.py
git commit -m "feat: export tenant-safe table sticker bundles"
```

### Task 5: Add admin export helpers and Blob API

**Files:**
- Create: `admin-h5/src/utils/tableStickerExport.js`
- Modify: `admin-h5/src/api/index.js`
- Create: `admin-h5/scripts/test-table-sticker-export.mjs`
- Modify: `admin-h5/package.json`

- [ ] **Step 1: Write the failing Node helper tests**

Create the script with `node:test` and `node:assert/strict` tests:

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  classifyTableStickerCode,
  parseBlobErrorMessage,
  selectedExportableCodes,
} from '../src/utils/tableStickerExport.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

test('only formal successful table codes are exportable', () => {
  const valid = { id: '1', channel: 'TABLE', entry_type: 'table', status: 1, env_version: 'release', generation_status: 'SUCCESS', image_url: '/static/entrance-codes/a.jpg', table_no: 'A01' }
  assert.deepEqual(classifyTableStickerCode(valid), { valid: true, reason: '' })
  assert.equal(classifyTableStickerCode({ ...valid, env_version: 'trial' }).valid, false)
  assert.equal(classifyTableStickerCode({ ...valid, table_no: ' ' }).valid, false)
  assert.deepEqual(selectedExportableCodes([valid, { ...valid, id: '2', status: 0 }], new Set(['1', '2'])), [valid])
})

test('blob JSON error uses backend message', async () => {
  const blob = new Blob([JSON.stringify({ code: 422, msg: '桌码状态已变化，请刷新后重新选择' })], { type: 'application/json' })
  assert.equal(await parseBlobErrorMessage(blob), '桌码状态已变化，请刷新后重新选择')
})

test('API request stays isolated from the global timeout', () => {
  const api = fs.readFileSync(path.join(root, 'src/api/index.js'), 'utf8')
  assert.match(api, /exportTableStickers[\s\S]*responseType:\s*['"]blob['"][\s\S]*timeout:\s*120000/)
  assert.match(api, /meta:\s*\{\s*rawResponse:\s*true\s*\}/)
})
```

- [ ] **Step 2: Add the npm script and verify RED**

Add:

```json
"test:table-sticker-export": "node --test scripts/test-table-sticker-export.mjs"
```

Run `npm run test:table-sticker-export`. Expected: import failure for the helper module.

- [ ] **Step 3: Implement pure helper functions**

Create `tableStickerExport.js`:

```javascript
export const classifyTableStickerCode = (code) => {
  if (code?.channel !== 'TABLE' || code?.entry_type !== 'table') return { valid: false, reason: '不是桌贴码' }
  if (Number(code?.status) !== 1) return { valid: false, reason: '桌码已停用' }
  if (code?.env_version !== 'release') return { valid: false, reason: '体验码，请先重新生成正式码' }
  if (code?.generation_status !== 'SUCCESS' || !code?.image_url) return { valid: false, reason: '桌码图片不可用' }
  if (!String(code?.table_no || '').trim()) return { valid: false, reason: '缺少桌号' }
  return { valid: true, reason: '' }
}

export const selectedExportableCodes = (codes, selectedIds) =>
  codes.filter(code => selectedIds.has(String(code.id)) && classifyTableStickerCode(code).valid)

export const parseBlobErrorMessage = async (blob) => {
  try {
    const data = JSON.parse(await blob.text())
    return data?.msg || '桌贴生成失败，请稍后重试'
  } catch {
    return '桌贴生成失败，请稍后重试'
  }
}

export const triggerBlobDownload = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}
```

- [ ] **Step 4: Add the isolated API method**

Append to `src/api/index.js`:

```javascript
export const exportTableStickers = (entranceCodeIds) => request.post(
  '/v1/entrance-codes/table-stickers/export',
  { entranceCodeIds },
  { responseType: 'blob', timeout: 120000, meta: { rawResponse: true } },
)
```

- [ ] **Step 5: Run helper tests and verify GREEN**

Run `npm run test:table-sticker-export`. Expected: all tests pass.

- [ ] **Step 6: Commit helpers and API**

```powershell
git add -- admin-h5/src/utils/tableStickerExport.js admin-h5/src/api/index.js admin-h5/scripts/test-table-sticker-export.mjs admin-h5/package.json
git commit -m "feat: add table sticker export client"
```

### Task 6: Build the export confirmation component

**Files:**
- Create: `admin-h5/src/components/TableStickerExportDialog.vue`
- Modify: `admin-h5/scripts/test-table-sticker-export.mjs`

- [ ] **Step 1: Add failing component contracts**

Read the component source in the Node test and require these contracts:

```javascript
test('export dialog is presentational and states print outputs', () => {
  const source = fs.readFileSync(path.join(root, 'src/components/TableStickerExportDialog.vue'), 'utf8')
  assert.match(source, /defineProps/)
  assert.match(source, /defineEmits\(\['close', 'confirm'\]\)/)
  assert.match(source, /10 × 12 cm/)
  assert.match(source, /300 DPI/)
  assert.match(source, /A4 每页 4 张/)
  assert.match(source, /异常桌码/)
  assert.doesNotMatch(source, /exportTableStickers|request\.|axios/)
})
```

- [ ] **Step 2: Run and verify RED**

Expected: missing component file.

- [ ] **Step 3: Create the focused component**

Implement a bottom `a-drawer` with these props and emits:

```vue
<script setup>
defineProps({
  open: { type: Boolean, default: false },
  validCodes: { type: Array, default: () => [] },
  invalidCodes: { type: Array, default: () => [] },
  exporting: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'confirm'])
</script>
```

The template must show:

- `可生成 {{ validCodes.length }} 张`;
- specification chips `10 × 12 cm`, `300 DPI`, `单桌高清 PNG`, `单贴单页 PDF`, `A4 每页 4 张`;
- an exception list with `item.tableNo` and `item.reason` when `invalidCodes.length > 0`;
- a disabled confirmation button when `validCodes.length === 0`;
- `exporting` loading state;
- a note saying `打印时请选择“实际大小/100%”，不要适应页面`.

Use existing Ant Design Vue components and scoped mobile-first CSS. Do not add a preview canvas or template editor.

- [ ] **Step 4: Run the component contract and Vue SFC compilation**

Run:

```powershell
npm run test:table-sticker-export
npm run build
```

Expected: component contract passes and Vite build exits 0.

- [ ] **Step 5: Commit the component**

```powershell
git add -- admin-h5/src/components/TableStickerExportDialog.vue admin-h5/scripts/test-table-sticker-export.mjs
git commit -m "feat: add table sticker export confirmation"
```

### Task 7: Wire selection and download into EntranceCodeList

**Files:**
- Modify: `admin-h5/src/views/EntranceCodeList.vue`
- Modify: `admin-h5/scripts/test-table-sticker-export.mjs`

- [ ] **Step 1: Add failing page-wiring contracts**

Require the page source to contain the component, selection set, valid-only select-all, exact request field mapping through the API helper, loading guard, and cleanup helper:

```javascript
test('EntranceCodeList wires valid-only batch selection and guarded download', () => {
  const source = fs.readFileSync(path.join(root, 'src/views/EntranceCodeList.vue'), 'utf8')
  assert.match(source, /TableStickerExportDialog/)
  assert.match(source, /selectedTableCodeIds/)
  assert.match(source, /classifyTableStickerCode/)
  assert.match(source, /exportTableStickers\(validCodes\.map\(code => String\(code\.id\)\)\)/)
  assert.match(source, /if \(exporting\.value\) return/)
  assert.match(source, /parseBlobErrorMessage/)
  assert.match(source, /triggerBlobDownload/)
})
```

- [ ] **Step 2: Run and verify RED**

Expected: page-wiring contract fails.

- [ ] **Step 3: Add selection state and computed groups**

Import the dialog, API method, and helper functions. Add:

```javascript
const selectedTableCodeIds = ref(new Set())
const showStickerExport = ref(false)
const exporting = ref(false)

const tableCodes = computed(() => codes.value.filter(code => code.channel === 'TABLE'))
const validTableCodes = computed(() => tableCodes.value.filter(code => classifyTableStickerCode(code).valid))
const invalidTableCodes = computed(() => tableCodes.value
  .filter(code => !classifyTableStickerCode(code).valid)
  .map(code => ({ tableNo: code.table_no || code.name || '未命名桌码', reason: classifyTableStickerCode(code).reason })))
const selectedValidCodes = computed(() => selectedExportableCodes(codes.value, selectedTableCodeIds.value))

const toggleTableCode = (code) => {
  if (!classifyTableStickerCode(code).valid) return
  const next = new Set(selectedTableCodeIds.value)
  const key = String(code.id)
  next.has(key) ? next.delete(key) : next.add(key)
  selectedTableCodeIds.value = next
}

const selectAllValidTableCodes = () => {
  selectedTableCodeIds.value = new Set(validTableCodes.value.map(code => String(code.id)))
}
```

After `loadData()` replaces `codes`, intersect the selected IDs with IDs still present and valid so refresh cannot retain stale selection.

- [ ] **Step 4: Add guarded export orchestration**

```javascript
const confirmStickerExport = async () => {
  if (exporting.value) return
  const validCodes = selectedValidCodes.value
  if (!validCodes.length) {
    message.warning('请选择至少一个有效桌码')
    return
  }
  exporting.value = true
  try {
    const response = await exportTableStickers(validCodes.map(code => String(code.id)))
    if (!(response?.data instanceof Blob) || response.data.type.includes('json')) {
      throw new Error(await parseBlobErrorMessage(response?.data || new Blob()))
    }
    const date = new Date().toISOString().slice(0, 10).replaceAll('-', '')
    triggerBlobDownload(response.data, `桌贴-${date}.zip`)
    showStickerExport.value = false
    message.success(`已生成 ${validCodes.length} 张桌贴`)
  } catch (error) {
    const backendBlob = error?.response?.data
    const text = backendBlob instanceof Blob
      ? await parseBlobErrorMessage(backendBlob)
      : (error?.message || '桌贴生成失败，请稍后重试')
    message.error(text)
  } finally {
    exporting.value = false
  }
}
```

- [ ] **Step 5: Add the mobile-first controls**

In the table-code list card:

- add a compact batch bar above rows with `已选 {{ selectedValidCodes.length }} 张`, `全选有效桌码`, `清空`, and primary `批量生成桌贴`;
- render a checkbox only for `code.channel === 'TABLE'`;
- disable the checkbox and show the eligibility reason when classification is invalid;
- keep the existing thumbnail click and single-image download actions unchanged;
- mount `TableStickerExportDialog` once at page root with `validCodes`, `invalidCodes`, `exporting`, `@close`, and `@confirm`.

Do not move or delete onboarding, creation, sorting, regeneration, or download logic.

- [ ] **Step 6: Run admin tests and build**

Run:

```powershell
npm run test:table-sticker-export
npm run test:onboarding-continuation
npm run check:text
npm run build
```

Expected: all commands exit 0. Existing Sass/chunk-size warnings are allowed; new compile errors are not.

- [ ] **Step 7: Commit page integration**

```powershell
git add -- admin-h5/src/views/EntranceCodeList.vue admin-h5/scripts/test-table-sticker-export.mjs
git commit -m "feat: batch export table stickers from admin"
```

### Task 8: End-to-end verification and visual sample

**Files:**
- Modify only if a verification failure identifies an in-scope defect in the files listed above.
- Generate locally, do not commit: `outputs/table-sticker-sample/*`

- [ ] **Step 1: Run focused backend tests**

```powershell
cd C:\Users\15936\Desktop\xiao\saas-base
py -3.10 -m pytest tests/test_table_sticker_export_service.py tests/test_table_sticker_export_api.py tests/test_entrance_code_coupon_template_tenant_isolation.py tests/test_scan_entry_contracts.py -q
```

Expected: all pass; this proves the new feature and unchanged entrance-code security/scan contracts.

- [ ] **Step 2: Run focused admin tests and production build**

```powershell
cd C:\Users\15936\Desktop\xiao\admin-h5
npm run test:table-sticker-export
npm run test:onboarding-continuation
npm run check:text
npm run build
```

Expected: all exit 0.

- [ ] **Step 3: Verify no forbidden scope changes**

Run:

```powershell
git diff --name-only HEAD~7..HEAD
git diff -- saas-base/alembic saas-base/requirements.txt admin-h5/package-lock.json member-mini-client
```

Expected: no migration, requirements, lockfile, or miniapp diff. Review every changed runtime file against the file map at the top of this plan.

- [ ] **Step 4: Generate a deterministic local sample**

Create a temporary 430 × 430 square fixture with a high-contrast finder-like pattern, then call `TableStickerExportService.build_bundle` for table numbers `01`, `A12`, `包厢1`, and a longer but valid table number. Extract the result to `outputs/table-sticker-sample/`.

Do not use a real merchant code or commit the output. The sample exists only to inspect composition, dimensions, PDF pagination, crop marks, and Chinese glyph rendering.

- [ ] **Step 5: Inspect the sample visually**

Open at least:

- `outputs/table-sticker-sample/PNG/A12桌.png`
- a rendered first page of `PDF/A4四联打印版.pdf`

Verify the reference hierarchy: large `扫码点餐`, green table badge, intact centered code, bottom `加菜也扫这里`, safe border, and crop marks outside finished stickers. If the visual hierarchy is wrong, adjust only layout constants in `table_sticker_export_service.py`, update exact pixel-contract assertions, and rerun Tasks 2–4 tests.

- [ ] **Step 6: Run verification-before-completion checks**

Re-run the exact focused backend and admin commands from Steps 1–2 after any visual adjustment. Record command output, counts, and build result in the final handoff.

- [ ] **Step 7: Commit only necessary visual corrections, if any**

If no correction was needed, do not create an empty commit. If needed:

```powershell
git add -- saas-base/app/services/table_sticker_export_service.py saas-base/tests/test_table_sticker_export_service.py
git commit -m "fix: tune table sticker print layout"
```

## Release gate retained for the user

Code completion does not certify physical printing. Before ordering the full batch:

1. Print one generated sticker at `实际大小/100%` on the intended material.
2. Measure that the finished sticker is 100 × 120 mm.
3. Scan it with two phones under the restaurant's normal light.
4. Confirm merchant name and table number after entry.
5. Only then send the full ZIP/PDF package to the printer.
