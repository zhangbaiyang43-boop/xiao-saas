import os
import uuid
from dotenv import load_dotenv

load_dotenv()

COS_SECRET_ID = os.getenv("COS_SECRET_ID", "") or os.getenv("COS_SECRET_", "")
COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "")
COS_REGION = os.getenv("COS_REGION", "ap-guangzhou")
COS_BUCKET = os.getenv("COS_BUCKET", "")
COS_BASE_URL = os.getenv("COS_BASE_URL", "").rstrip("/")


def _base_url() -> str:
    return COS_BASE_URL or f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com"


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



