from __future__ import annotations

from pathlib import Path
import warnings

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


DPI = 300
STICKER_WIDTH = 1181
STICKER_HEIGHT = 1417
QR_CONTAINER_SIZE = 752
QR_CONTENT_SIZE = 652
QR_QUIET_ZONE = 50
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_DIMENSION = 4096
SAFE_IMAGE_PREFIX = "/static/entrance-codes/"
STATIC_ROOT = (Path.cwd() / "static").resolve()
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
        try:
            canvas = Image.new("RGB", (STICKER_WIDTH, STICKER_HEIGHT), "white")
            draw = ImageDraw.Draw(canvas)

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

                qr_image = source_image.resize((QR_CONTENT_SIZE, QR_CONTENT_SIZE), Image.Resampling.LANCZOS)
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
        finally:
            source_image.close()

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
        if not source_path.is_file():
            raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")

        if source_path.stat().st_size > MAX_SOURCE_BYTES:
            raise TableStickerExportError(INVALID_SOURCE_IMAGE, "桌码图片无效")

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
            converted = image.convert("RGB")
            image.close()
            return converted
        return image

    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        if not FONT_PATH.is_file():
            raise TableStickerExportError(FONT_NOT_FOUND, f"桌贴字体缺失: {FONT_PATH}")
        try:
            return ImageFont.truetype(str(FONT_PATH), size=size)
        except OSError as exc:
            raise TableStickerExportError(FONT_NOT_FOUND, f"桌贴字体缺失: {FONT_PATH}") from exc

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
        total_left_offset, total_right_offset, total_width = self._table_badge_text_layout(draw, table_body, body_font, unit_font)
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
        min_size = 32
        for size in range(64, min_size - 1, -1):
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
