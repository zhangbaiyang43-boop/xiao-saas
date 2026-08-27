from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


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
