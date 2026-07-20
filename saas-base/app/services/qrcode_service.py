import os
import io
from urllib.parse import urlencode

CHANNEL_ENTRY_DIR = "static/channel-entries"

class QRCodeService:
    @staticmethod
    def ensure_static_dir():
        os.makedirs(CHANNEL_ENTRY_DIR, exist_ok=True)

    @staticmethod
    def get_h5_base_url():
        from app.config import settings
        return getattr(settings, "H5_BASE_URL", "https://api.zhangbaiyang.com")

    @staticmethod
    def generate_h5_url(base_url: str, entry_id: int, channel_code: str) -> str:
        params = {"id": entry_id, "channel": channel_code}
        return f"{base_url}/h5/channel/landing?{urlencode(params)}"

    @staticmethod
    def generate_qrcode_image_data(url: str) -> tuple:
        try:
            import qrcode
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue(), 'png'
        except ImportError:
            return QRCodeService._generate_fallback_qrcode(url), 'svg'

    @staticmethod
    def _generate_fallback_qrcode(url: str) -> bytes:
        svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
  <rect width="200" height="200" fill="white"/>
  <text x="100" y="80" text-anchor="middle" font-size="14" fill="#333">扫码访问</text>
  <text x="100" y="105" text-anchor="middle" font-size="10" fill="#666">{url[:30]}...</text>
  <text x="100" y="130" text-anchor="middle" font-size="10" fill="#999">请使用微信扫码</text>
  <rect x="10" y="10" width="20" height="20" fill="#333"/>
  <rect x="170" y="10" width="20" height="20" fill="#333"/>
  <rect x="10" y="170" width="20" height="20" fill="#333"/>
  <rect x="90" y="90" width="20" height="20" fill="#333"/>
  <rect x="90" y="10" width="20" height="20" fill="#333"/>
  <rect x="10" y="90" width="20" height="20" fill="#333"/>
  <rect x="170" y="90" width="20" height="20" fill="#333"/>
  <rect x="90" y="170" width="20" height="20" fill="#333"/>
</svg>'''
        return svg_content.encode('utf-8')

    @staticmethod
    async def generate_qrcode_file(url: str, file_name: str) -> str:
        QRCodeService.ensure_static_dir()
        image_data, ext = QRCodeService.generate_qrcode_image_data(url)
        
        # 根据实际生成的格式确定文件名后缀
        if ext == 'png':
            if file_name.endswith('.svg'):
                file_name = file_name[:-4] + '.png'
        else:
            if file_name.endswith('.png'):
                file_name = file_name[:-4] + '.svg'
        
        file_path = os.path.join(CHANNEL_ENTRY_DIR, file_name)
        with open(file_path, "wb") as f:
            f.write(image_data)
        
        return f"/static/channel-entries/{file_name}"