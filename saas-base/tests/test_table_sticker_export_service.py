import importlib
import inspect
import math
from pathlib import Path
import re
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import zipfile

from PIL import Image, ImageDraw, ImageFont
import pytest


ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = ROOT / "app" / "assets" / "fonts" / "NotoSansSC-Bold.otf"
LICENSE_PATH = ROOT / "app" / "assets" / "fonts" / "OFL.txt"
EXPECTED_DEFAULT_ENTRANCE_CODE_DIR = ROOT / "static" / "entrance-codes"


def test_table_sticker_print_font_assets_exist_and_render_chinese_text():
    assert FONT_PATH.is_file()
    assert LICENSE_PATH.is_file()
    assert "SIL OPEN FONT LICENSE" in LICENSE_PATH.read_text(encoding="utf-8")

    font = ImageFont.truetype(str(FONT_PATH), size=48)
    assert font.getname() == ("Noto Sans SC", "Bold")
    missing = bytes(font.getmask("\U0010ffff"))
    for char in "扫码点餐桌":
        assert bytes(font.getmask(char)) != missing

    image = Image.new("RGB", (500, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), "扫码点餐 A01桌", font=font, fill="black")

    assert draw.textbbox((0, 0), "扫码点餐 A01桌", font=font) is not None


def _write_source_image(directory: Path, name: str = "table.png", size=(430, 430)) -> str:
    source_path = directory / name
    image = Image.new("RGB", size, "black")
    try:
        image.save(source_path)
    finally:
        image.close()
    return f"/static/entrance-codes/{name}"


def _service_and_code(directory: Path, image_url: str, table_no: str = "A01"):
    from app.services.table_sticker_export_service import TableStickerExportService

    return TableStickerExportService(entrance_code_dir=directory), SimpleNamespace(
        image_url=image_url,
        table_no=table_no,
    )


def _pixel_close(actual: tuple[int, int, int], expected: tuple[int, int, int], tolerance: int = 10) -> bool:
    return all(abs(channel - target) <= tolerance for channel, target in zip(actual, expected))


def _region_has_color(
    image: Image.Image,
    box: tuple[int, int, int, int],
    expected: tuple[int, int, int],
    tolerance: int = 10,
    minimum_hits: int = 4,
) -> bool:
    hits = 0
    for x in range(box[0], box[2]):
        for y in range(box[1], box[3]):
            if _pixel_close(image.getpixel((x, y)), expected, tolerance=tolerance):
                hits += 1
                if hits >= minimum_hits:
                    return True
    return False


def _measure_drawn_text_bounds(text_calls: list[dict]) -> tuple[int, int, int, int]:
    left = None
    top = None
    right = None
    bottom = None
    for call in text_calls:
        x, y = call["xy"]
        x0, y0, x1, y1 = call["bbox"]
        call_left = x + x0
        call_top = y + y0
        call_right = x + x1
        call_bottom = y + y1
        left = call_left if left is None else min(left, call_left)
        top = call_top if top is None else min(top, call_top)
        right = call_right if right is None else max(right, call_right)
        bottom = call_bottom if bottom is None else max(bottom, call_bottom)
    assert left is not None and top is not None and right is not None and bottom is not None
    return left, top, right, bottom


def test_render_sticker_returns_exact_rgb_print_canvas_for_valid_source():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory))

        rendered = service.render_sticker(code)
        try:
            assert rendered.mode == "RGB"
            assert rendered.size == (1181, 1417)
        finally:
            rendered.close()


def test_table_sticker_service_default_entrance_code_dir_ignores_cwd(monkeypatch):
    import app.services.table_sticker_export_service as export_service

    with TemporaryDirectory() as temp_dir:
        monkeypatch.chdir(temp_dir)
        export_service = importlib.reload(export_service)

        service = export_service.TableStickerExportService()

        assert export_service.ENTRANCE_CODE_DIR == EXPECTED_DEFAULT_ENTRANCE_CODE_DIR
        assert service.entrance_code_dir == EXPECTED_DEFAULT_ENTRANCE_CODE_DIR

        monkeypatch.chdir(ROOT)
        importlib.reload(export_service)


@pytest.mark.parametrize(
    "image_url",
    [
        "../secret.png",
        "/static/entrance-codes/nested/table.png",
        "/static/other/table.png",
        "https://example.com/table.png",
    ],
)
def test_render_sticker_rejects_unsafe_source_paths(image_url):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, image_url)

        with pytest.raises(ValueError, match="桌码图片无效"):
            service.render_sticker(code)


def test_render_sticker_rejects_absolute_source_path():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        image_url = str((directory / "table.png").resolve())
        service, code = _service_and_code(directory, image_url)

        with pytest.raises(ValueError, match="桌码图片无效"):
            service.render_sticker(code)


@pytest.mark.parametrize("file_name, is_oversized", [("missing.png", False), ("large.png", True)])
def test_render_sticker_rejects_missing_or_oversized_source(file_name, is_oversized):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        if is_oversized:
            (directory / file_name).write_bytes(b"0" * (10 * 1024 * 1024 + 1))
        service, code = _service_and_code(directory, f"/static/entrance-codes/{file_name}")

        with pytest.raises(ValueError, match="桌码图片无效"):
            service.render_sticker(code)


def test_render_sticker_rejects_corrupted_source_image():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        (directory / "corrupted.png").write_bytes(b"not an image")
        service, code = _service_and_code(directory, "/static/entrance-codes/corrupted.png")

        with pytest.raises(ValueError, match="桌码图片损坏"):
            service.render_sticker(code)


@pytest.mark.parametrize("method_name", ["is_file", "stat"])
def test_render_sticker_converts_source_metadata_oserror_to_structured_error(monkeypatch, method_name):
    import app.services.table_sticker_export_service as export_service

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        source_path = directory / "table.png"
        source_path.write_bytes(b"placeholder")
        service, code = _service_and_code(directory, "/static/entrance-codes/table.png")

        if method_name == "is_file":
            monkeypatch.setattr(Path, "is_file", lambda _self: (_ for _ in ()).throw(PermissionError("denied")))
        else:
            monkeypatch.setattr(Path, "stat", lambda _self: (_ for _ in ()).throw(OSError("stat failed")))

        with pytest.raises(export_service.TableStickerExportError, match="桌码图片无效") as exc_info:
            service.render_sticker(code)

        assert exc_info.value.code == export_service.INVALID_SOURCE_IMAGE


def test_render_sticker_rejects_source_larger_than_dimension_limit(monkeypatch):
    import app.services.table_sticker_export_service as export_service

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory))
        monkeypatch.setattr(export_service, "MAX_SOURCE_DIMENSION", 400)

        with pytest.raises(ValueError, match="桌码图片无效"):
            service.render_sticker(code)


@pytest.mark.parametrize("size", [(430, 429), (299, 299)])
def test_render_sticker_rejects_non_square_or_too_small_source(size):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory, size=size))

        with pytest.raises(ValueError, match="桌码图片无效"):
            service.render_sticker(code)


@pytest.mark.parametrize("table_no", [None, "", "   "])
def test_render_sticker_rejects_empty_table_number(table_no):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory), table_no)

        with pytest.raises(ValueError, match="桌号"):
            service.render_sticker(code)


def test_render_sticker_rejects_table_number_that_cannot_fit_badge():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(
            directory,
            _write_source_image(directory),
            "超长桌号" * 12,
        )

        with pytest.raises(ValueError, match="桌号过长"):
            service.render_sticker(code)


def test_render_sticker_accepts_merchant_name_keyword_and_truncates_safely():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory), "A08")

        rendered = service.render_sticker(
            code,
            merchant_name="大宝羊肉汤弘农路直营旗舰店" * 4,
        )
        try:
            assert rendered.mode == "RGB"
            assert rendered.size == (1181, 1417)
        finally:
            rendered.close()


def test_render_sticker_visual_contract_matches_approved_demo(monkeypatch):
    captured_text_calls = []
    original_text = ImageDraw.ImageDraw.text

    def spy_text(drawer, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        captured_text_calls.append(
            {
                "xy": xy,
                "text": text,
                "font_size": getattr(font, "size", None),
                "bbox": drawer.textbbox((0, 0), text, font=font),
            }
        )
        return original_text(drawer, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy_text)

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory), "A08桌")

        rendered = service.render_sticker(
            code,
            merchant_name="大宝羊肉汤弘农路直营旗舰店" * 4,
        )
        try:
            assert _region_has_color(rendered, (300, 100, 340, 140), (7, 193, 96), tolerance=4)
            assert _region_has_color(rendered, (2, 80, 6, 120), (230, 233, 236), tolerance=8)
            # 桌号牌：深绿底 #059646 + 红棕描边 #9A3412
            assert _region_has_color(rendered, (452, 214, 468, 230), (5, 150, 70), tolerance=8)
            assert _region_has_color(rendered, (438, 250, 442, 270), (154, 52, 18), tolerance=14)
            # 二维码：静区（卡片左沿到内容左沿之间）留白，内容区纯黑
            assert _region_has_color(rendered, (165, 410, 180, 425), (255, 255, 255), tolerance=0)
            assert _region_has_color(rendered, (320, 500, 340, 520), (0, 0, 0), tolerance=0)

            merchant_calls = [
                call
                for call in captured_text_calls
                if call["xy"][1] < 200
            ]
            assert merchant_calls
            assert merchant_calls[0]["text"].endswith("...")
            # "扫码点餐" 已删除
            assert all(call["text"] != "扫码点餐" for call in captured_text_calls)

            badge_calls = [
                call
                for call in captured_text_calls
                if 180 <= call["xy"][1] <= 360
            ]
            assert any(call["text"] == "A08" and 100 <= (call["font_size"] or 0) <= 140 for call in badge_calls)
            assert any(call["text"] == "桌" and 50 <= (call["font_size"] or 0) <= 66 for call in badge_calls)
            assert all(call["text"] != "A08桌" for call in badge_calls)
            badge_text_calls = [call for call in badge_calls if call["text"] in {"A08", "桌"}]
            combined_left, _, combined_right, _ = _measure_drawn_text_bounds(badge_text_calls)
            assert combined_left >= 438 + 16
            assert combined_right <= 743 - 16

            line1 = [c for c in captured_text_calls if c["text"] == "微信扫码，本桌点单"]
            line2 = [c for c in captured_text_calls if c["text"] == "加菜也扫这里"]
            hint = [c for c in captured_text_calls if c["text"] == "扫码 → 选菜 → 下单 · 有事招呼服务员"]
            assert len(line1) == 1 and len(line2) == 1 and len(hint) == 1
            assert line1[0]["font_size"] == 48 and line2[0]["font_size"] == 48
            assert hint[0]["font_size"] == 32
            assert line1[0]["xy"][1] >= 1200
            assert line2[0]["xy"][1] > line1[0]["xy"][1]
            assert hint[0]["xy"][1] > line2[0]["xy"][1]
        finally:
            rendered.close()


def test_render_sticker_checks_dimensions_before_loading_reopened_image(monkeypatch):
    import app.services.table_sticker_export_service as export_service

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        source_path = directory / "table.png"
        source_path.write_bytes(b"placeholder")
        service, code = _service_and_code(directory, "/static/entrance-codes/table.png")
        load_called = False

        class VerifyImage:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def verify(self):
                return None

        class OversizedImage:
            size = (export_service.MAX_SOURCE_DIMENSION + 1, export_service.MAX_SOURCE_DIMENSION + 1)
            mode = "RGB"

            def load(self):
                nonlocal load_called
                load_called = True

            def close(self):
                return None

        images = iter([VerifyImage(), OversizedImage()])
        monkeypatch.setattr(export_service.Image, "open", lambda *_args, **_kwargs: next(images))

        with pytest.raises(export_service.TableStickerExportError, match="桌码图片无效") as exc_info:
            service.render_sticker(code)

        assert exc_info.value.code == export_service.INVALID_SOURCE_IMAGE
        assert load_called is False


@pytest.mark.parametrize("bomb_kind", ["error", "warning"])
def test_render_sticker_rejects_pillow_decompression_bomb(monkeypatch, bomb_kind):
    import app.services.table_sticker_export_service as export_service

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        source_path = directory / "table.png"
        source_path.write_bytes(b"placeholder")
        service, code = _service_and_code(directory, "/static/entrance-codes/table.png")

        class VerifyImage:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def verify(self):
                return None

        class BombImage:
            size = (430, 430)
            mode = "RGB"

            def load(self):
                if bomb_kind == "error":
                    raise Image.DecompressionBombError("boom")
                raise Image.DecompressionBombWarning("boom")

            def close(self):
                return None

        images = iter([VerifyImage(), BombImage()])
        monkeypatch.setattr(export_service.Image, "open", lambda *_args, **_kwargs: next(images))

        with pytest.raises(export_service.TableStickerExportError, match="桌码图片损坏") as exc_info:
            service.render_sticker(code)

        assert exc_info.value.code == export_service.CORRUPTED_SOURCE_IMAGE


def test_render_sticker_converts_mode_convert_oserror_to_structured_error(monkeypatch):
    import app.services.table_sticker_export_service as export_service

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        source_path = directory / "table.png"
        source_path.write_bytes(b"placeholder")
        service, code = _service_and_code(directory, "/static/entrance-codes/table.png")
        image_closed = False

        class VerifyImage:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def verify(self):
                return None

        class ConvertFailImage:
            size = (430, 430)
            mode = "RGBA"

            def load(self):
                return None

            def convert(self, _mode):
                raise OSError("convert failed")

            def close(self):
                nonlocal image_closed
                image_closed = True

        images = iter([VerifyImage(), ConvertFailImage()])
        monkeypatch.setattr(export_service.Image, "open", lambda *_args, **_kwargs: next(images))

        with pytest.raises(export_service.TableStickerExportError, match="桌码图片损坏") as exc_info:
            service.render_sticker(code)

        assert exc_info.value.code == export_service.CORRUPTED_SOURCE_IMAGE
        assert image_closed is True


@pytest.mark.parametrize("table_no", ["A01", "A08", "春风桌"])
def test_render_sticker_keeps_combined_badge_text_inside_badge(table_no, monkeypatch):
    captured = []
    original_text = ImageDraw.ImageDraw.text

    def spy_text(drawer, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        captured.append(
            {
                "xy": xy,
                "text": text,
                "font_size": getattr(font, "size", None),
                "bbox": drawer.textbbox((0, 0), text, font=font),
            }
        )
        return original_text(drawer, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy_text)

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory), table_no)

        rendered = service.render_sticker(code)
        try:
            badge_calls = [call for call in captured if call["text"] in {service._normalize_table_no(table_no), "桌"}]
            assert [call["text"] for call in badge_calls] == [service._normalize_table_no(table_no), "桌"]
            combined_left, _, combined_right, _ = _measure_drawn_text_bounds(badge_calls)
            assert combined_left >= 438 + 16
            assert combined_right <= 743 - 16
        finally:
            rendered.close()


def test_render_sticker_uses_nearest_resize_to_preserve_qr_pixels():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        source_path = directory / "table.png"
        image = Image.new("RGB", (300, 300), "white")
        try:
            for x in range(150):
                for y in range(300):
                    image.putpixel((x, y), (0, 0, 0))
            image.save(source_path)
        finally:
            image.close()

        service, code = _service_and_code(directory, "/static/entrance-codes/table.png")
        rendered = service.render_sticker(code)
        try:
            qr_crop = rendered.crop((194, 396, 986, 1188))
            try:
                colors = set(qr_crop.getdata())
            finally:
                qr_crop.close()
            assert colors <= {(0, 0, 0), (255, 255, 255)}
        finally:
            rendered.close()


def test_render_sticker_visual_contract_includes_outer_border_and_merchant_cap(monkeypatch):
    captured_text_calls = []
    original_text = ImageDraw.ImageDraw.text

    def spy_text(drawer, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        captured_text_calls.append(
            {
                "xy": xy,
                "text": text,
                "font_size": getattr(font, "size", None),
            }
        )
        return original_text(drawer, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy_text)

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory), "A01")

        rendered = service.render_sticker(code, merchant_name="大宝羊肉汤")
        try:
            assert _region_has_color(rendered, (2, 80, 6, 120), (230, 233, 236), tolerance=8)
            assert not _region_has_color(rendered, (18, 80, 24, 120), (230, 233, 236), tolerance=8)
            merchant_calls = [call for call in captured_text_calls if call["text"] == "大宝羊肉汤"]
            assert len(merchant_calls) == 1
            assert merchant_calls[0]["font_size"] == 50
        finally:
            rendered.close()


def test_table_sticker_font_cache_reuses_sizes_across_renders():
    from app.services.table_sticker_export_service import TableStickerExportService

    TableStickerExportService._cached_font.cache_clear()
    before = TableStickerExportService._cached_font.cache_info()
    assert before.hits == 0

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory), "A01")

        first = service.render_sticker(code, merchant_name="大宝羊肉汤")
        first.close()
        after_first = TableStickerExportService._cached_font.cache_info()

        second = service.render_sticker(code, merchant_name="大宝羊肉汤")
        second.close()
        after_second = TableStickerExportService._cached_font.cache_info()

    assert after_first.misses > 0
    assert after_first.maxsize == 128
    assert after_second.hits > after_first.hits


@pytest.mark.parametrize("table_no", ["18", "A01", "春风桌"])
def test_render_sticker_renders_reasonable_table_numbers(table_no):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, code = _service_and_code(directory, _write_source_image(directory), table_no)

        rendered = service.render_sticker(code)
        try:
            assert rendered.size == (1181, 1417)
        finally:
            rendered.close()


PAGE_RE = re.compile(rb"/Type\s*/Page\b")
MEDIA_BOX_RE = re.compile(
    rb"/MediaBox\s*\[\s*0(?:\.0+)?\s+0(?:\.0+)?\s+([0-9.]+)\s+([0-9.]+)\s*\]"
)


def _pdf_stats(data: bytes) -> tuple[int, list[tuple[float, float]]]:
    boxes = [(float(width), float(height)) for width, height in MEDIA_BOX_RE.findall(data)]
    return len(PAGE_RE.findall(data)), boxes


def _bundle_service_and_codes(directory: Path, count: int):
    from app.services.table_sticker_export_service import TableStickerExportService

    image_url = _write_source_image(directory, name="shared-code.png")
    codes = [
        SimpleNamespace(image_url=image_url, table_no=f"A{index:02d}")
        for index in range(1, count + 1)
    ]
    return TableStickerExportService(entrance_code_dir=directory), codes


@pytest.mark.parametrize(
    "count, expected_single_pages, expected_a4_pages",
    [(1, 1, 1), (4, 4, 1), (5, 5, 2)],
)
def test_bundle_for_one_four_and_five_stickers_has_exact_files_and_pdf_sizes(
    count,
    expected_single_pages,
    expected_a4_pages,
):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, codes = _bundle_service_and_codes(directory, count)

        artifact = service.build_bundle(codes, merchant_name="测试餐厅")
        try:
            with zipfile.ZipFile(artifact.zip_path) as archive:
                expected_entries = [f"PNG/A{index:02d}桌.png" for index in range(1, count + 1)] + [
                    "PDF/单贴印厂版.pdf",
                    "PDF/A4四联打印版.pdf",
                    "导出说明.txt",
                ]
                assert archive.namelist() == expected_entries

                for png_name in expected_entries[:count]:
                    with archive.open(png_name) as png_file, Image.open(png_file) as png:
                        png.load()
                        assert png.mode == "RGB"
                        assert png.size == (1181, 1417)
                        assert png.info["dpi"] == pytest.approx((300, 300), abs=0.1)

                single_count, single_boxes = _pdf_stats(archive.read("PDF/单贴印厂版.pdf"))
                four_up_count, four_up_boxes = _pdf_stats(archive.read("PDF/A4四联打印版.pdf"))
                assert single_count == expected_single_pages
                assert four_up_count == expected_a4_pages
                assert all(width == pytest.approx(100 / 25.4 * 72, abs=0.1) for width, _ in single_boxes)
                assert all(height == pytest.approx(120 / 25.4 * 72, abs=0.1) for _, height in single_boxes)
                assert all(width == pytest.approx(210 / 25.4 * 72, abs=0.1) for width, _ in four_up_boxes)
                assert all(height == pytest.approx(297 / 25.4 * 72, abs=0.1) for _, height in four_up_boxes)

                instructions = archive.read("导出说明.txt").decode("utf-8")
                assert f"桌贴数量：{count}" in instructions
                assert "100 × 120 mm" in instructions
                assert "300 DPI" in instructions
                assert "实际大小/100%" in instructions
        finally:
            artifact.cleanup()
        assert not artifact.temp_dir.exists()


def test_bundle_uses_stable_sanitized_duplicate_names_and_safe_download_name():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, codes = _bundle_service_and_codes(directory, 3)
        codes[0].table_no = "../A01"
        codes[1].table_no = "..\\A01"
        codes[2].table_no = "..."

        artifact = service.build_bundle(codes, merchant_name="../危险/餐厅\\名称")
        try:
            with zipfile.ZipFile(artifact.zip_path) as archive:
                assert archive.namelist()[:3] == [
                    "PNG/A01桌.png",
                    "PNG/A01桌-2.png",
                    "PNG/桌码桌.png",
                ]
                assert all(".." not in name and "\\" not in name for name in archive.namelist())
            assert re.fullmatch(r"危险-餐厅-名称-桌贴-\d{8}\.zip", artifact.download_name)
            assert "/" not in artifact.download_name
            assert "\\" not in artifact.download_name
        finally:
            artifact.cleanup()
            artifact.cleanup()
        assert not artifact.temp_dir.exists()


def test_bundle_composes_four_a4_slots_and_crop_marks(monkeypatch):
    import app.services.table_sticker_export_service as export_service

    captured_a4 = []

    def fake_render(_code, *, merchant_name=None):
        return Image.new("RGB", (1181, 1417), "#E11D48")

    def inspect_pdf_page(_writer, image_path, first):
        del first
        with Image.open(image_path) as page:
            page.load()
            if page.size == (2480, 3508):
                captured_a4.append(page.copy())

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, codes = _bundle_service_and_codes(directory, 4)
        monkeypatch.setattr(service, "render_sticker", fake_render)
        monkeypatch.setattr(export_service, "_append_pdf_page", inspect_pdf_page)

        artifact = service.build_bundle(codes, merchant_name="测试餐厅")
        try:
            assert len(captured_a4) == 1
            page = captured_a4[0]
            try:
                expected_slots = ((36, 314), (1263, 314), (36, 1777), (1263, 1777))
                assert export_service.A4_SLOTS == expected_slots
                for x, y in expected_slots:
                    assert page.getpixel((x + 100, y + 100)) == (225, 29, 72)
                    assert page.getpixel((x, y - 10)) == (107, 114, 128)
                    assert page.getpixel((x - 10, y)) == (107, 114, 128)
                    assert page.getpixel((x + 5, y + 5)) == (225, 29, 72)
                    assert page.getpixel((x + 1175, y + 5)) == (225, 29, 72)
                    assert page.getpixel((x + 5, y + 1411)) == (225, 29, 72)
                    assert page.getpixel((x + 1175, y + 1411)) == (225, 29, 72)
            finally:
                page.close()
        finally:
            artifact.cleanup()


def test_bundle_closes_each_render_before_rendering_the_next(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "entrance-codes"
        directory.mkdir()
        service, codes = _bundle_service_and_codes(directory, 5)
        previous = None

        def tracked_render(_code, *, merchant_name=None):
            nonlocal previous
            if previous is not None:
                with pytest.raises(ValueError):
                    previous.getbbox()
            previous = Image.new("RGB", (1181, 1417), "white")
            return previous

        monkeypatch.setattr(service, "render_sticker", tracked_render)
        artifact = service.build_bundle(codes, merchant_name="测试餐厅")
        try:
            assert previous is not None
            with pytest.raises(ValueError):
                previous.getbbox()
        finally:
            artifact.cleanup()

    source = inspect.getsource(type(service).build_bundle)
    assert "append_images" not in source
    assert "[self.render_sticker" not in source


def test_bundle_removes_entire_temp_directory_when_generation_fails(monkeypatch, tmp_path):
    import app.services.table_sticker_export_service as export_service

    created_temp_dir = tmp_path / "table-stickers-known"

    def create_known_temp_dir(**_kwargs):
        created_temp_dir.mkdir()
        return str(created_temp_dir)

    monkeypatch.setattr(export_service.tempfile, "mkdtemp", create_known_temp_dir)

    directory = tmp_path / "entrance-codes"
    directory.mkdir()
    service, codes = _bundle_service_and_codes(directory, 1)
    monkeypatch.setattr(service, "render_sticker", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        service.build_bundle(codes, merchant_name="测试餐厅")

    assert not created_temp_dir.exists()
