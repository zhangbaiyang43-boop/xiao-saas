from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont
import pytest


ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = ROOT / "app" / "assets" / "fonts" / "NotoSansSC-Bold.otf"
LICENSE_PATH = ROOT / "app" / "assets" / "fonts" / "OFL.txt"


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
