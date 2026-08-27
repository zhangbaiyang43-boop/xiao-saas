from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import re
import shutil
import tempfile
import warnings
import zipfile

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


DPI = 300
STICKER_WIDTH = 1181
STICKER_HEIGHT = 1417
A4_WIDTH = 2480
A4_HEIGHT = 3508
A4_SLOTS = ((59, 337), (1240, 337), (59, 1754), (1240, 1754))
QR_CONTAINER_SIZE = 752
QR_CONTENT_SIZE = 652
QR_QUIET_ZONE = 50
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_DIMENSION = 4096
SAFE_IMAGE_PREFIX = "/static/entrance-codes/"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = PROJECT_ROOT / "static"
ENTRANCE_CODE_DIR = STATIC_ROOT / "entrance-codes"
FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC-Bold.otf"

INVALID_SOURCE_IMAGE = "INVALID_SOURCE_IMAGE"
CORRUPTED_SOURCE_IMAGE = "CORRUPTED_SOURCE_IMAGE"
EMPTY_TABLE_NO = "EMPTY_TABLE_NO"
TABLE_NO_TOO_LONG = "TABLE_NO_TOO_LONG"
FONT_NOT_FOUND = "FONT_NOT_FOUND"
BADGE_HORIZONTAL_PADDING = 16
BADGE_TEXT_GAP = 8
BADGE_UNIT_TEXT = "桌"


@dataclass(frozen=True)
class ExportArtifact:
    zip_path: Path
    temp_dir: Path
    download_name: str

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", str(value or "")).strip(" .-")
    return cleaned[:64] or fallback


class _PdfPageWriter:
    def __init__(self, pdf_path: Path, page_width_points: float, page_height_points: float):
        self.pdf_path = pdf_path
        self.page_width_points = page_width_points
        self.page_height_points = page_height_points
        self._file = None
        self._offsets: dict[int, int] = {}
        self._page_ids: list[int] = []
        self._next_object_id = 3

    def __enter__(self):
        self._file = self.pdf_path.open("wb")
        self._file.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        self._write_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        return self

    def __exit__(self, exc_type, _exc, _traceback):
        try:
            if exc_type is None:
                self._finish()
        finally:
            if self._file is not None:
                self._file.close()
                self._file = None

    def append(self, image_path: Path) -> None:
        if self._file is None:
            raise RuntimeError("PDF writer is not open")

        with Image.open(image_path) as page:
            page.load()
            rgb = page.convert("RGB")
            try:
                width, height = rgb.size
                encoded = BytesIO()
                rgb.save(encoded, "JPEG", quality=95, subsampling=0)
                image_data = encoded.getvalue()
            finally:
                rgb.close()

        image_id = self._next_object_id
        content_id = image_id + 1
        page_id = image_id + 2
        self._next_object_id += 3
        self._page_ids.append(page_id)

        image_header = (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(image_data)} >>\nstream\n"
        ).encode("ascii")
        self._write_object(image_id, image_header + image_data + b"\nendstream")

        content = (
            f"q\n{self.page_width_points:.6f} 0 0 {self.page_height_points:.6f} 0 0 cm\n/Im0 Do\nQ\n"
        ).encode("ascii")
        content_body = f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"endstream"
        self._write_object(content_id, content_body)

        page_body = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.page_width_points:.6f} {self.page_height_points:.6f}] "
            f"/Resources << /XObject << /Im0 {image_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        self._write_object(page_id, page_body)

    def _write_object(self, object_id: int, body: bytes) -> None:
        if self._file is None:
            raise RuntimeError("PDF writer is not open")
        self._offsets[object_id] = self._file.tell()
        self._file.write(f"{object_id} 0 obj\n".encode("ascii"))
        self._file.write(body)
        self._file.write(b"\nendobj\n")

    def _finish(self) -> None:
        if self._file is None:
            raise RuntimeError("PDF writer is not open")
        kids = " ".join(f"{page_id} 0 R" for page_id in self._page_ids)
        self._write_object(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(self._page_ids)} >>".encode("ascii"))

        max_object_id = self._next_object_id - 1
        xref_offset = self._file.tell()
        self._file.write(f"xref\n0 {max_object_id + 1}\n".encode("ascii"))
        self._file.write(b"0000000000 65535 f \n")
        for object_id in range(1, max_object_id + 1):
            self._file.write(f"{self._offsets[object_id]:010d} 00000 n \n".encode("ascii"))
        self._file.write(
            (
                f"trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("ascii")
        )


def _append_pdf_page(writer: _PdfPageWriter, image_path: Path, first: bool) -> None:
    del first
    writer.append(image_path)


def _draw_crop_marks(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    mark = 34
    gap = 10
    color = "#6B7280"
    width = 2
    for px in (x, x + STICKER_WIDTH):
        draw.line((px, y - gap - mark, px, y - gap), fill=color, width=width)
        draw.line(
            (px, y + STICKER_HEIGHT + gap, px, y + STICKER_HEIGHT + gap + mark),
            fill=color,
            width=width,
        )
    for py in (y, y + STICKER_HEIGHT):
        draw.line((x - gap - mark, py, x - gap, py), fill=color, width=width)
        draw.line(
            (x + STICKER_WIDTH + gap, py, x + STICKER_WIDTH + gap + mark, py),
            fill=color,
            width=width,
        )


class TableStickerExportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TableStickerExportService:
    def __init__(self, db=None, entrance_code_dir=ENTRANCE_CODE_DIR):
        self.db = db
        self.entrance_code_dir = Path(entrance_code_dir).resolve()

    def render_sticker(self, code, *, merchant_name: str | None = None) -> Image.Image:
        table_no = (getattr(code, "table_no", "") or "").strip()
        if not table_no:
            raise TableStickerExportError(EMPTY_TABLE_NO, "桌号不能为空")

        merchant_label = self._normalize_merchant_name(merchant_name)
        source_path = self._source_path(getattr(code, "image_url", ""))
        source_image = self._load_source(source_path)
        canvas = None
        try:
            canvas = Image.new("RGB", (STICKER_WIDTH, STICKER_HEIGHT), "white")
            draw = ImageDraw.Draw(canvas)

            draw.rounded_rectangle(
                (2, 2, 1178, 1414),
                radius=56,
                outline="#E6E9EC",
                width=3,
            )
            self._draw_dashed_guide(draw, (28, 28, 1153, 1389), radius=34, dash=18, gap=12, fill="#CFD6DD", width=3)
            draw.rounded_rectangle(
                (62, 62, 1119, 188),
                radius=34,
                fill="#07C160",
            )
            merchant_font, merchant_label = self._fit_merchant_font(
                draw,
                merchant_label,
                max_width=961,
                max_height=74,
            )
            self._draw_centered_text(draw, (110, 82, 1071, 168), merchant_label, merchant_font, fill="white")

            title_font = self._font(59)
            footer_font = self._font(44)
            table_body = self._normalize_table_no(table_no)
            unit_font = self._font(56)
            body_font = self._fit_table_font(
                draw,
                table_body,
                unit_font=unit_font,
                max_total_width=(1109 - 797) - (BADGE_HORIZONTAL_PADDING * 2),
                max_height=126,
            )

            draw.text((84, 248), "扫码点餐", font=title_font, fill="#111418")
            draw.rounded_rectangle(
                (797, 220, 1109, 400),
                radius=28,
                fill="#EAFAF0",
                outline="#07C160",
                width=4,
            )
            self._draw_table_badge_text(
                draw,
                (797, 220, 1109, 400),
                table_body,
                body_font,
                unit_font,
            )

            qr_card = Image.new("RGB", (QR_CONTAINER_SIZE, QR_CONTAINER_SIZE), "white")
            try:
                draw_card = ImageDraw.Draw(qr_card)
                draw_card.rounded_rectangle((0, 0, QR_CONTAINER_SIZE - 1, QR_CONTAINER_SIZE - 1), radius=32, fill="white")

                qr_image = source_image.resize((QR_CONTENT_SIZE, QR_CONTENT_SIZE), Image.Resampling.NEAREST)
                try:
                    qr_card.paste(qr_image, (QR_QUIET_ZONE, QR_QUIET_ZONE))
                finally:
                    qr_image.close()

                qr_left = (STICKER_WIDTH - QR_CONTAINER_SIZE) // 2
                qr_top = 418
                canvas.paste(qr_card, (qr_left, qr_top))
            finally:
                qr_card.close()

            footer_text = "微信扫码 · 本桌下单，加菜也扫这里"
            footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
            footer_width = footer_bbox[2] - footer_bbox[0]
            draw.text(
                ((STICKER_WIDTH - footer_width) // 2, 1312),
                footer_text,
                font=footer_font,
                fill="#111418",
            )

            return canvas
        except Exception:
            if canvas is not None:
                canvas.close()
            raise
        finally:
            source_image.close()

    def build_bundle(self, codes, merchant_name: str) -> ExportArtifact:
        temp_dir = Path(tempfile.mkdtemp(prefix="table-stickers-"))
        png_dir = temp_dir / "PNG"
        pdf_dir = temp_dir / "PDF"
        single_pdf_path = pdf_dir / "单贴印厂版.pdf"
        four_up_pdf_path = pdf_dir / "A4四联打印版.pdf"
        instructions_path = temp_dir / "导出说明.txt"
        zip_path = temp_dir / "桌贴打印包.zip"

        try:
            png_dir.mkdir()
            pdf_dir.mkdir()
            png_entries: list[tuple[Path, str]] = []
            name_counts: dict[str, int] = {}

            with _PdfPageWriter(
                single_pdf_path,
                page_width_points=100 / 25.4 * 72,
                page_height_points=120 / 25.4 * 72,
            ) as single_pdf:
                for index, code in enumerate(codes):
                    table_no = self._normalize_table_no((getattr(code, "table_no", "") or "").strip())
                    safe_table_no = _safe_name(table_no, "桌码")
                    name_counts[safe_table_no] = name_counts.get(safe_table_no, 0) + 1
                    duplicate_index = name_counts[safe_table_no]
                    suffix = "" if duplicate_index == 1 else f"-{duplicate_index}"
                    file_name = f"{safe_table_no}桌{suffix}.png"
                    image_path = png_dir / file_name

                    sticker = self.render_sticker(code, merchant_name=merchant_name)
                    try:
                        if sticker.mode != "RGB" or sticker.size != (STICKER_WIDTH, STICKER_HEIGHT):
                            raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌贴图片生成失败")
                        sticker.save(image_path, "PNG", dpi=(DPI, DPI))
                    finally:
                        sticker.close()

                    _append_pdf_page(single_pdf, image_path, first=index == 0)
                    png_entries.append((image_path, f"PNG/{file_name}"))

            if not png_entries:
                raise TableStickerExportError(EMPTY_TABLE_NO, "请选择至少一个桌码")

            self._build_four_up_pdf([path for path, _ in png_entries], four_up_pdf_path, temp_dir)

            export_date = datetime.now().strftime("%Y-%m-%d")
            instructions_path.write_text(
                "\n".join(
                    (
                        "桌贴打印说明",
                        f"桌贴数量：{len(png_entries)}",
                        f"导出日期：{export_date}",
                        "成品尺寸：100 × 120 mm",
                        "图片精度：300 DPI",
                        "打印时请选择“实际大小/100%”，不要适应页面。",
                    )
                ),
                encoding="utf-8",
            )

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for image_path, arc_name in png_entries:
                    archive.write(image_path, arc_name)
                archive.write(single_pdf_path, "PDF/单贴印厂版.pdf")
                archive.write(four_up_pdf_path, "PDF/A4四联打印版.pdf")
                archive.write(instructions_path, "导出说明.txt")

            safe_merchant = _safe_name(merchant_name, "商户")
            download_name = f"{safe_merchant}-桌贴-{datetime.now().strftime('%Y%m%d')}.zip"
            return ExportArtifact(zip_path=zip_path, temp_dir=temp_dir, download_name=download_name)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    @staticmethod
    def _build_four_up_pdf(png_paths: list[Path], pdf_path: Path, temp_dir: Path) -> None:
        with _PdfPageWriter(
            pdf_path,
            page_width_points=210 / 25.4 * 72,
            page_height_points=297 / 25.4 * 72,
        ) as four_up_pdf:
            for page_index in range(0, len(png_paths), 4):
                page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
                page_path = temp_dir / f"a4-page-{page_index // 4 + 1}.png"
                try:
                    draw = ImageDraw.Draw(page)
                    for slot, image_path in zip(A4_SLOTS, png_paths[page_index : page_index + 4]):
                        with Image.open(image_path) as sticker:
                            sticker.load()
                            page.paste(sticker, slot)
                        _draw_crop_marks(draw, *slot)
                    page.save(page_path, "PNG", dpi=(DPI, DPI))
                finally:
                    page.close()

                try:
                    _append_pdf_page(four_up_pdf, page_path, first=page_index == 0)
                finally:
                    page_path.unlink(missing_ok=True)

    def _source_path(self, image_url: str) -> Path:
        normalized_url = (image_url or "").strip()
        if not normalized_url.startswith(SAFE_IMAGE_PREFIX):
            raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")

        file_name = normalized_url[len(SAFE_IMAGE_PREFIX) :]
        if (
            not file_name
            or file_name in {".", ".."}
            or "/" in file_name
            or "\\" in file_name
            or Path(file_name).name != file_name
            or Path(file_name).is_absolute()
        ):
            raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")

        resolved_path = (self.entrance_code_dir / file_name).resolve()
        if resolved_path.parent != self.entrance_code_dir:
            raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")
        return resolved_path

    def _load_source(self, source_path: Path) -> Image.Image:
        try:
            if not source_path.is_file():
                raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")

            if source_path.stat().st_size > MAX_SOURCE_BYTES:
                raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")
        except TableStickerExportError:
            raise
        except OSError as exc:
            raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效") from exc

        image = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source_path) as verifying_image:
                    verifying_image.verify()

            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(source_path)
            width, height = image.size
            if (
                width <= 0
                or height <= 0
                or width != height
                or width < 300
                or height < 300
                or width > MAX_SOURCE_DIMENSION
                or height > MAX_SOURCE_DIMENSION
            ):
                raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")

            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image.load()
        except TableStickerExportError:
            if image is not None:
                image.close()
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            if image is not None:
                image.close()
            raise TableStickerExportError(CORRUPTED_SOURCE_IMAGE, "桌码图片损坏") from exc
        except (FileNotFoundError, UnidentifiedImageError, OSError, SyntaxError) as exc:
            if image is not None:
                image.close()
            raise TableStickerExportError(CORRUPTED_SOURCE_IMAGE, "桌码图片损坏") from exc

        if image.mode != "RGB":
            try:
                converted = image.convert("RGB")
            except OSError as exc:
                image.close()
                raise TableStickerExportError(CORRUPTED_SOURCE_IMAGE, "桌码图片损坏") from exc
            image.close()
            return converted
        return image

    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        if not FONT_PATH.is_file():
            raise TableStickerExportError(FONT_NOT_FOUND, f"桌贴字体缺失: {FONT_PATH}")
        try:
            return self._cached_font(size)
        except OSError as exc:
            raise TableStickerExportError(FONT_NOT_FOUND, f"桌贴字体缺失: {FONT_PATH}") from exc

    @staticmethod
    @lru_cache(maxsize=128)
    def _cached_font(size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(FONT_PATH), size=size)

    @staticmethod
    def _normalize_table_no(table_no: str) -> str:
        normalized = (table_no or "").strip()
        if normalized.endswith("桌"):
            normalized = normalized[:-1].rstrip()
        if not normalized:
            raise TableStickerExportError(EMPTY_TABLE_NO, "桌号不能为空")
        return normalized

    def _fit_table_font(
        self,
        draw: ImageDraw.ImageDraw,
        table_no: str,
        unit_font: ImageFont.FreeTypeFont,
        max_total_width: int,
        max_height: int,
    ) -> ImageFont.FreeTypeFont:
        for size in range(150, 59, -1):
            font = self._font(size)
            bbox = draw.textbbox((0, 0), table_no, font=font)
            text_height = bbox[3] - bbox[1]
            _, _, combined_width = self._table_badge_text_layout(draw, table_no, font, unit_font)
            if combined_width <= max_total_width and text_height <= max_height:
                return font
        raise TableStickerExportError(TABLE_NO_TOO_LONG, "桌号过长")

    def _draw_table_badge_text(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        table_body: str,
        body_font: ImageFont.FreeTypeFont,
        unit_font: ImageFont.FreeTypeFont,
    ) -> None:
        left, top, right, bottom = box
        body_bbox = draw.textbbox((0, 0), table_body, font=body_font)
        unit_bbox = draw.textbbox((0, 0), BADGE_UNIT_TEXT, font=unit_font)
        body_width = body_bbox[2] - body_bbox[0]
        body_height = body_bbox[3] - body_bbox[1]
        unit_height = unit_bbox[3] - unit_bbox[1]
        inner_left = left + BADGE_HORIZONTAL_PADDING
        inner_right = right - BADGE_HORIZONTAL_PADDING
        total_left_offset, _, total_width = self._table_badge_text_layout(draw, table_body, body_font, unit_font)
        start_x = inner_left + ((inner_right - inner_left) - total_width) // 2 - total_left_offset
        baseline_top = top + ((bottom - top) - max(body_height, unit_height)) // 2 + 8
        body_y = baseline_top - body_bbox[1]
        unit_y = baseline_top + (body_height - unit_height) + 10 - unit_bbox[1]
        draw.text((start_x, body_y), table_body, font=body_font, fill="#05913F")
        draw.text((start_x + body_width + BADGE_TEXT_GAP, unit_y), BADGE_UNIT_TEXT, font=unit_font, fill="#05913F")

    @staticmethod
    def _table_badge_text_layout(
        draw: ImageDraw.ImageDraw,
        table_body: str,
        body_font: ImageFont.FreeTypeFont,
        unit_font: ImageFont.FreeTypeFont,
    ) -> tuple[int, int, int]:
        body_bbox = draw.textbbox((0, 0), table_body, font=body_font)
        unit_bbox = draw.textbbox((0, 0), BADGE_UNIT_TEXT, font=unit_font)
        body_width = body_bbox[2] - body_bbox[0]
        unit_x = body_width + BADGE_TEXT_GAP
        total_left = min(body_bbox[0], unit_x + unit_bbox[0])
        total_right = max(body_bbox[2], unit_x + unit_bbox[2])
        return total_left, total_right, total_right - total_left

    def _fit_merchant_font(
        self,
        draw: ImageDraw.ImageDraw,
        merchant_name: str,
        max_width: int,
        max_height: int,
    ) -> tuple[ImageFont.FreeTypeFont, str]:
        min_size = 28
        for size in range(50, min_size - 1, -1):
            font = self._font(size)
            bbox = draw.textbbox((0, 0), merchant_name, font=font)
            if (bbox[2] - bbox[0]) <= max_width and (bbox[3] - bbox[1]) <= max_height:
                return font, merchant_name

        font = self._font(min_size)
        if self._text_width(draw, merchant_name, font) <= max_width:
            return font, merchant_name

        ellipsis = "..."
        trimmed = merchant_name
        while trimmed:
            candidate = f"{trimmed}{ellipsis}"
            if self._text_width(draw, candidate, font) <= max_width:
                return font, candidate
            trimmed = trimmed[:-1]
        return font, ellipsis

    @staticmethod
    def _normalize_merchant_name(merchant_name: str | None) -> str:
        normalized = (merchant_name or "").strip()
        return normalized or "商家官方桌码"

    @staticmethod
    def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    @staticmethod
    def _draw_centered_text(
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: str,
    ) -> None:
        left, top, right, bottom = box
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = left + ((right - left) - text_width) // 2
        y = top + ((bottom - top) - text_height) // 2 - bbox[1]
        draw.text((x, y), text, font=font, fill=fill)

    @staticmethod
    def _draw_dashed_guide(
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        radius: int,
        dash: int,
        gap: int,
        fill: str,
        width: int,
    ) -> None:
        left, top, right, bottom = box
        TableStickerExportService._draw_dashed_line(
            draw,
            (left + radius, top),
            (right - radius, top),
            dash,
            gap,
            fill,
            width,
        )
        TableStickerExportService._draw_dashed_line(
            draw,
            (right, top + radius),
            (right, bottom - radius),
            dash,
            gap,
            fill,
            width,
        )
        TableStickerExportService._draw_dashed_line(
            draw,
            (right - radius, bottom),
            (left + radius, bottom),
            dash,
            gap,
            fill,
            width,
        )
        TableStickerExportService._draw_dashed_line(
            draw,
            (left, bottom - radius),
            (left, top + radius),
            dash,
            gap,
            fill,
            width,
        )

        TableStickerExportService._draw_dashed_arc(draw, (left, top, left + radius * 2, top + radius * 2), 180, 270, dash, gap, fill, width)
        TableStickerExportService._draw_dashed_arc(draw, (right - radius * 2, top, right, top + radius * 2), 270, 360, dash, gap, fill, width)
        TableStickerExportService._draw_dashed_arc(draw, (right - radius * 2, bottom - radius * 2, right, bottom), 0, 90, dash, gap, fill, width)
        TableStickerExportService._draw_dashed_arc(draw, (left, bottom - radius * 2, left + radius * 2, bottom), 90, 180, dash, gap, fill, width)

    @staticmethod
    def _draw_dashed_line(
        draw: ImageDraw.ImageDraw,
        start: tuple[int, int],
        end: tuple[int, int],
        dash: int,
        gap: int,
        fill: str,
        width: int,
    ) -> None:
        x1, y1 = start
        x2, y2 = end
        if x1 == x2:
            direction = 1 if y2 >= y1 else -1
            cursor = y1
            limit = y2
            while (limit - cursor) * direction >= 0:
                segment_end = cursor + direction * min(dash, abs(limit - cursor))
                draw.line((x1, cursor, x2, segment_end), fill=fill, width=width)
                cursor = segment_end + direction * gap
        else:
            direction = 1 if x2 >= x1 else -1
            cursor = x1
            limit = x2
            while (limit - cursor) * direction >= 0:
                segment_end = cursor + direction * min(dash, abs(limit - cursor))
                draw.line((cursor, y1, segment_end, y2), fill=fill, width=width)
                cursor = segment_end + direction * gap

    @staticmethod
    def _draw_dashed_arc(
        draw: ImageDraw.ImageDraw,
        bounds: tuple[int, int, int, int],
        start_angle: int,
        end_angle: int,
        dash: int,
        gap: int,
        fill: str,
        width: int,
    ) -> None:
        angle = start_angle
        while angle < end_angle:
            span = min(dash, end_angle - angle)
            draw.arc(bounds, start=angle, end=angle + span, fill=fill, width=width)
            angle += dash + gap
