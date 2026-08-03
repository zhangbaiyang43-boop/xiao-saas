import os
import uuid
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

COS_SECRET_ID = os.getenv("COS_SECRET_ID", "") or os.getenv("COS_SECRET_", "")
COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "")
COS_REGION = os.getenv("COS_REGION", "ap-guangzhou")
COS_BUCKET = os.getenv("COS_BUCKET", "")
COS_BASE_URL = os.getenv("COS_BASE_URL", "").rstrip("/")

IMAGE_MAX_DIMENSION = 1600
IMAGE_WEBP_QUALITY = 80


def _base_url() -> str:
    return COS_BASE_URL or f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com"


def process_image(content: bytes) -> bytes:
    """解码上传的图片，按 EXIF 修正方向、按最长边等比缩放、转码为 WebP。

    输入无法解码为图片时抛 ValueError；调用方必须据此拒绝上传，不能回退到原始字节上传——
    这一步和上层的 magic-bytes 嗅探是同一道防线的两层，跳过 Pillow 解码失败直接放行，
    等于把两层校验都绕开了。这是同步/CPU 密集操作，调用方应在线程池里跑，避免阻塞事件循环。
    """
    from PIL import Image, ImageOps

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

    if max(img.width, img.height) > IMAGE_MAX_DIMENSION:
        img.thumbnail((IMAGE_MAX_DIMENSION, IMAGE_MAX_DIMENSION), Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="WEBP", quality=IMAGE_WEBP_QUALITY)
    return out.getvalue()


def upload_image(file_bytes: bytes, filename: str, content_type: str = "image/jpeg") -> str:
    if not COS_SECRET_ID or not COS_SECRET_KEY or not COS_BUCKET:
        raise RuntimeError("COS not configured")
    from qcloud_cos import CosConfig, CosS3Client
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    object_key = f"dish_images/{uuid.uuid4().hex}.{ext}"
    config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
    client = CosS3Client(config)
    client.put_object(Bucket=COS_BUCKET, Body=file_bytes, Key=object_key, ContentType=content_type)
    return f"{_base_url()}/{object_key}"



