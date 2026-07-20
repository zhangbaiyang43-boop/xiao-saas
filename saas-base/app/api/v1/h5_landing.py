from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.channel_entry_service import ChannelEntryService

router = APIRouter(prefix="/h5", tags=["H5落地页"])


CHANNEL_NAMES = {
    "douyin": "抖音",
    "kuaishou": "快手",
    "meituan": "美团",
    "eleme": "饿了么",
    "moments": "朋友圈",
    "offline": "线下门店",
    "custom": "自定义",
}


def error_html(message: str, status_code: int = 400):
    content = f"""
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>页面不可用</title>
</head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f7fb;font-family:Arial,sans-serif;">
    <div style="width:86%;max-width:420px;padding:28px 22px;background:#fff;border-radius:14px;text-align:center;box-shadow:0 8px 24px rgba(15,23,42,.08);">
        <h1 style="margin:0 0 12px;font-size:22px;color:#111827;">页面暂时不可用</h1>
        <p style="margin:0;color:#64748b;line-height:1.6;">{message}</p>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=content, status_code=status_code)


def mini_program_redirect_html(merchant_name: str = "", scene: str = ""):
    content = f"""
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>请使用小程序</title>
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            var ua = navigator.userAgent.toLowerCase();
            if (ua.indexOf('micromessenger') > -1) {{
                document.getElementById('wechat-tip').style.display = 'block';
            }}
        }});
    </script>
</head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f7fb;font-family:Arial,sans-serif;">
    <div style="width:86%;max-width:420px;padding:28px 22px;background:#fff;border-radius:14px;text-align:center;box-shadow:0 8px 24px rgba(15,23,42,.08);">
        <div style="width:120px;height:120px;margin:0 auto 20px;border-radius:16px;background:#e8f5e9;display:flex;align-items:center;justify-content:center;">
            <svg viewBox="0 0 64 64" width="64" height="64" fill="none">
                <rect x="4" y="4" width="56" height="56" rx="12" fill="#07c160"/>
                <rect x="14" y="14" width="16" height="16" rx="2" fill="white"/>
                <rect x="34" y="14" width="16" height="16" rx="2" fill="white"/>
                <rect x="14" y="34" width="16" height="16" rx="2" fill="white"/>
                <rect x="34" y="34" width="16" height="16" rx="2" fill="white"/>
                <rect x="20" y="20" width="4" height="4" rx="1" fill="#07c160"/>
                <rect x="40" y="20" width="4" height="4" rx="1" fill="#07c160"/>
                <rect x="20" y="40" width="4" height="4" rx="1" fill="#07c160"/>
                <rect x="42" y="42" width="8" height="8" rx="2" fill="#07c160"/>
            </svg>
        </div>
        <h1 style="margin:0 0 12px;font-size:22px;color:#111827;">请使用微信小程序</h1>
        <p style="margin:0 0 20px;color:#64748b;line-height:1.6;">{merchant_name} 的点餐服务已升级，<br>请使用微信扫描小程序码完成点餐和支付。</p>
        <div id="wechat-tip" style="display:none;background:#fff3cd;border:1px solid #ffeeba;border-radius:8px;padding:12px;color:#856404;font-size:14px;">
            在微信中无法直接打开小程序，请返回使用微信扫一扫功能扫描小程序码。
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=content, status_code=200)


@router.get("/channel/landing", response_class=HTMLResponse)
async def h5_landing_page(request: Request):
    return mini_program_redirect_html()


@router.get("/channel/landing/{entry_id}", response_class=HTMLResponse)
async def h5_landing_page_by_id(entry_id: int, request: Request):
    return mini_program_redirect_html()
