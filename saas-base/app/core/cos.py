import os
import uuid
from io import BytesIO
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

COS_SECRET_ID = os.getenv("COS_SECRET_ID", "") or os.getenv("COS_SECRET_", "")
COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "")
COS_REGION = os.getenv("COS_REGION", "ap-guangzhou")
COS_BUCKET = os.getenv("COS_BUCKET", "")
COS_BASE_URL = os.getenv("COS_BASE_URL", "").rstrip("/")

IMAGE_MAX_DIMENSION = 1600
IMAGE_LOGO_MAX_DIMENSION = 512
IMAGE_WEBP_QUALITY = 80


def _base_url() -> str:
    return COS_BASE_URL or f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com"


def sniff_image_content_type(content: bytes) -> str | None:
    """按文件头 magic bytes 识别真实图片格式。不信后缀/客户端 Content-Type。"""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def process_image(content: bytes, max_dimension: int = IMAGE_MAX_DIMENSION) -> bytes:
    """解码上传的图片，按 EXIF 修正方向、按最长边等比缩放、转码为 WebP。

    输入无法解码为图片时抛 ValueError；调用方必须据此拒绝上传，不能回退到原始字节上传——
    这一步和上层的 magic-bytes 嗅探是同一道防线的两层，跳过 Pillow 解码失败直接放行，
    等于把两层校验都绕开了。这是同步/CPU 密集操作，调用方应在线程池里跑，避免阻塞事件循环。
    """
    try:
        from PIL import Image, ImageOps
    except ModuleNotFoundError as e:
        raise RuntimeError("服务器未安装 Pillow，请执行: pip install Pillow==10.4.0") from e

    try:
        img = Image.open(BytesIO(content))
        img.load()
    except Exception as e:
        raise ValueError("无法解析图片内容") from e

    img = ImageOps.exif_transpose(img)
    if img.mode == "P":
        img = img.convert("RGBA" if img.info.get("transparency") is not None else "RGB")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

    limit = max(1, int(max_dimension))
    if max(img.width, img.height) > limit:
        img.thumbnail((limit, limit), Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="WEBP", quality=IMAGE_WEBP_QUALITY)
    return out.getvalue()


def upload_image(
    file_bytes: bytes,
    filename: str,
    content_type: str = "image/jpeg",
    folder: str = "dish_images",
) -> str:
    if not COS_SECRET_ID or not COS_SECRET_KEY or not COS_BUCKET:
        raise RuntimeError("COS not configured")
    from qcloud_cos import CosConfig, CosS3Client
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    safe_folder = (folder or "dish_images").strip("/").replace("..", "")
    object_key = f"{safe_folder}/{uuid.uuid4().hex}.{ext}"
    config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
    client = CosS3Client(config)
    client.put_object(Bucket=COS_BUCKET, Body=file_bytes, Key=object_key, ContentType=content_type)
    return f"{_base_url()}/{object_key}"


def is_allowed_cos_url(url: str | None) -> bool:
    """校验 URL 是否指向本项目 COS（或空，表示清除 Logo）。"""
    value = (url or "").strip()
    if not value:
        return True
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    allowed_hosts = set()
    base = _base_url()
    if base:
        base_host = urlparse(base).netloc.lower()
        if base_host:
            allowed_hosts.add(base_host)
    if COS_BUCKET and COS_REGION:
        allowed_hosts.add(f"{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com".lower())
    return parsed.netloc.lower() in allowed_hosts
