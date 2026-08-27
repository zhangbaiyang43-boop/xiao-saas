import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from sqlalchemy import and_, func
from sqlalchemy.future import select

from app.config import settings
from app.core.tenant_context import TenantContext
from app.models.coupon_template import CouponTemplate
from app.models.entrance_code import EntranceCode, EntranceScanLog
from app.services.base_service import BaseService
from app.services.coupon_service import CouponService
from app.services.tenant_service import TenantService
from app.utils.id_generator import generate_snowflake_id


STATIC_ROOT = os.path.abspath(os.path.join(os.getcwd(), "static"))
ENTRANCE_CODE_DIR = os.path.join(STATIC_ROOT, "entrance-codes")
MINIAPP_ENTRY_PAGE = "pages/entry/index"
DEFAULT_NEW_CUSTOMER_COUPON_NAME = "scan_new_customer_coupon"


class EntranceCodeService(BaseService):
    def _resolve_target_page(self, entry_type: str) -> str:
        if entry_type in ["table", "takeaway"]:
            return "subpkg-order/pages/menu"
        if entry_type in ["poster", "douyin"]:
            return "pages/index/index"
        return "subpkg-order/pages/menu"

    def _resolve_order_mode(self, entry_type: str) -> str:
        if entry_type == "takeaway":
            return "takeaway"
        if entry_type == "pickup":
            return "pickup"
        return "dine_in"

    async def _validate_coupon_template_id(self, coupon_template_id) -> int | None:
        if coupon_template_id in (None, ""):
            return None
        tenant_id = self.require_tenant_id()
        try:
            template_id = int(coupon_template_id)
        except (TypeError, ValueError):
            raise ValueError("优惠券模板不存在")

        result = await self.db.execute(
            select(CouponTemplate.id).filter(
                CouponTemplate.id == template_id,
                CouponTemplate.tenant_id == tenant_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise ValueError("优惠券模板不存在")
        return template_id

    async def create_entrance_code(
        self,
        name: str,
        channel: str = "STORE",
        coupon_template_id: int | None = None,
        page: str = MINIAPP_ENTRY_PAGE,
        env_version: str = "release",
        table_no: str | None = None,
        entry_type: str = "table",
        order_mode: str | None = None,
        table_id: int | None = None,
        target_page: str | None = None,
        zone_type: str | None = None,
        staff_id: int | None = None,
    ) -> EntranceCode:
        tenant_id = self.require_tenant_id()
        coupon_template_id = await self._validate_coupon_template_id(coupon_template_id)
        scene = await self._generate_scene()
        resolved_target_page = target_page or self._resolve_target_page(entry_type)
        resolved_order_mode = order_mode or self._resolve_order_mode(entry_type)
        
        image_result = await self._generate_code_image(
            scene, MINIAPP_ENTRY_PAGE, env_version,
            tenant_id=tenant_id, channel=channel or "STORE", table_no=table_no or ""
        )
        entrance_code = EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=tenant_id,
            name=name,
            channel=(channel or "STORE").upper(),
            scene=scene,
            page=MINIAPP_ENTRY_PAGE,
            coupon_template_id=coupon_template_id,
            image_url=image_result["image_url"],
            env_version=env_version,
            code_type=image_result["code_type"],
            generation_status=image_result["generation_status"],
            generation_error=image_result["generation_error"],
            status=1,
            table_no=table_no or None,
            entry_type=entry_type,
            order_mode=resolved_order_mode,
            table_id=table_id,
            target_page=resolved_target_page,
            zone_type=zone_type or None,
            staff_id=staff_id,
        )
        self.db.add(entrance_code)
        await self.db.commit()
        await self.db.refresh(entrance_code)
        
        from app.core.logger import logger
        logger.info(f"[MINI_CODE_GENERATE] entry_code={scene} tenant_id={tenant_id} entry_type={entry_type} page={MINIAPP_ENTRY_PAGE} target_page={resolved_target_page} code_type={image_result.get('code_type')} success={image_result['generation_status'] == 'SUCCESS'} error={image_result.get('generation_error') or ''}")
        
        return entrance_code

    async def list_entrance_codes(self, skip: int = 0, limit: int = 100) -> list:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(EntranceCode)
            .filter(EntranceCode.tenant_id == tenant_id)
            .order_by(EntranceCode.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_entrance_codes(self) -> int:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(func.count()).select_from(EntranceCode).filter(EntranceCode.tenant_id == tenant_id)
        )
        return int(result.scalar() or 0)

    async def table_registry_active(self, tenant_id: str, table_no: str) -> bool:
        """P0-01: server-side authority check for "does this (tenant_id, table_no)
        correspond to a real, currently-usable table" -- the canonical source of
        truth is an EntranceCode row with entry_type='table' and status==1. Explicit
        tenant_id param (not self.require_tenant_id()) because callers here resolve
        tenant_id from an unauthenticated request body, same as get_by_scene above.

        Uses EXISTS/limit(1), not scalar_one_or_none(): production has confirmed
        cases of more than one active table EntranceCode for the same (tenant_id,
        table_no) pair (re-generated codes), which is a data-hygiene concern, not
        an authority violation -- this check must not raise on that shape.
        """
        normalized_table_no = (table_no or "").strip()
        if not tenant_id or not normalized_table_no:
            return False
        result = await self.db.execute(
            select(EntranceCode.id)
            .where(
                EntranceCode.tenant_id == tenant_id,
                func.trim(EntranceCode.table_no) == normalized_table_no,
                EntranceCode.entry_type == "table",
                EntranceCode.status == 1,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_scene(self, scene: str) -> EntranceCode | None:
        normalized_scene = (scene or "").strip()
        result = await self.db.execute(select(EntranceCode).filter(EntranceCode.scene == normalized_scene))
        return result.scalar_one_or_none()

    async def get_tenant_code(self, entrance_code_id: int) -> EntranceCode | None:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(EntranceCode).filter(
                EntranceCode.id == entrance_code_id,
                EntranceCode.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, entrance_code_id: int, status: int) -> EntranceCode | None:
        entrance_code = await self.get_tenant_code(entrance_code_id)
        if not entrance_code:
            return None
        entrance_code.status = status
        await self.db.commit()
        await self.db.refresh(entrance_code)
        return entrance_code

    async def regenerate_entrance_code(self, entrance_code_id: int) -> EntranceCode | None:
        """Regenerate mini program code with release env."""
        entrance_code = await self.get_tenant_code(entrance_code_id)
        if not entrance_code:
            return None
        image_result = await self._generate_code_image(
            entrance_code.scene, MINIAPP_ENTRY_PAGE, "release",
            tenant_id=entrance_code.tenant_id,
            channel=entrance_code.channel or "STORE",
            table_no=getattr(entrance_code, "table_no", "") or "",
        )
        entrance_code.page = MINIAPP_ENTRY_PAGE
        entrance_code.env_version = "release"
        entrance_code.image_url = image_result["image_url"]
        entrance_code.code_type = image_result["code_type"]
        entrance_code.generation_status = image_result["generation_status"]
        entrance_code.generation_error = image_result["generation_error"]
        await self.db.commit()
        await self.db.refresh(entrance_code)
        
        from app.core.logger import logger
        logger.info(f"[MINI_CODE_GENERATE] entry_code={entrance_code.scene} tenant_id={entrance_code.tenant_id} entry_type={getattr(entrance_code, 'entry_type', '')} page={MINIAPP_ENTRY_PAGE} target_page={getattr(entrance_code, 'target_page', '')} code_type={image_result.get('code_type')} success={image_result['generation_status'] == 'SUCCESS'} error={image_result.get('generation_error') or ''}")
        
        return entrance_code

    async def delete_entrance_code(self, entrance_code_id: int) -> bool:
        entrance_code = await self.get_tenant_code(entrance_code_id)
        if not entrance_code:
            return False
        
        if entrance_code.image_url:
            file_name = entrance_code.image_url.split("/")[-1]
            file_path = os.path.join(ENTRANCE_CODE_DIR, file_name)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        await self.db.delete(entrance_code)
        await self.db.commit()
        return True

    async def resolve_scene(
        self,
        scene: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> EntranceCode | None:
        entrance_code = await self.get_by_scene(scene)
        if not entrance_code or entrance_code.status != 1:
            from app.core.logger import logger
            logger.info(f"[MINI_ENTRY_RESOLVE] entry_code={scene} tenant_id='' table_id='' channel='' success=False")
            return None

        TenantContext.set_tenant_id(entrance_code.tenant_id)
        entrance_code.scan_count = int(entrance_code.scan_count or 0) + 1
        entrance_code.last_scan_time = datetime.utcnow()
        self.db.add(
            EntranceScanLog(
                id=generate_snowflake_id(),
                tenant_id=entrance_code.tenant_id,
                entrance_code_id=entrance_code.id,
                scene=entrance_code.scene,
                channel=entrance_code.channel,
                event_type="SCAN",
                ip=ip,
                user_agent=user_agent[:255] if user_agent else None,
            )
        )
        await self.db.commit()
        await self.db.refresh(entrance_code)
        
        from app.core.logger import logger
        logger.info(f"[MINI_ENTRY_RESOLVE] entry_code={scene} tenant_id={entrance_code.tenant_id} table_id={getattr(entrance_code, 'table_id', '')} channel={entrance_code.channel} success=True")
        
        return entrance_code

    async def record_member_conversion(
        self,
        scene: str | None,
        customer_id: int,
        openid: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> EntranceCode | None:
        if not scene:
            return None
        entrance_code = await self.get_by_scene(scene)
        if not entrance_code or entrance_code.status != 1:
            return None

        TenantContext.set_tenant_id(entrance_code.tenant_id)
        entrance_code.member_count = int(entrance_code.member_count or 0) + 1
        self.db.add(
            EntranceScanLog(
                id=generate_snowflake_id(),
                tenant_id=entrance_code.tenant_id,
                entrance_code_id=entrance_code.id,
                customer_id=customer_id,
                openid=openid,
                scene=entrance_code.scene,
                channel=entrance_code.channel,
                event_type="MEMBER_CREATED",
                ip=ip,
                user_agent=user_agent[:255] if user_agent else None,
            )
        )
        await self.db.commit()
        await self.db.refresh(entrance_code)

        return entrance_code

    async def ensure_new_customer_coupon_template(self, entrance_code: EntranceCode) -> CouponTemplate:
        if entrance_code.coupon_template_id:
            template = await CouponService(self.db).get_template(entrance_code.coupon_template_id)
            if template and template.status == 1:
                return template

        config = await TenantService(self.db).ensure_tenant_config(entrance_code.tenant_id)
        rule = (config.coupon_rules or {}).get("new_customer_coupon", {})
        amount = float(rule.get("amount") or 10)
        valid_days = int(rule.get("valid_days") or 30)

        reusable_template = await self._find_reusable_new_customer_template(entrance_code.tenant_id, amount)
        if reusable_template:
            return reusable_template

        template = CouponTemplate(
            id=generate_snowflake_id(),
            tenant_id=entrance_code.tenant_id,
            name=DEFAULT_NEW_CUSTOMER_COUPON_NAME,
            type="FIXED",
            value=amount,
            min_amount=0,
            total_stock=9999,
            used_stock=0,
            start_time=datetime.utcnow() - timedelta(minutes=1),
            end_time=datetime.utcnow() + timedelta(days=valid_days),
            status=1,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def issue_new_customer_coupon(self, entrance_code: EntranceCode, customer_id: int) -> dict:
        """走 /v1/member/login-or-create 这条（目前小程序没在用，走的是
        miniapp.py 的 entry/join）历史入会路径时的新客券发放。这条路径本身
        没被前端调用、风险很低，但补上和其它自动发券入口一致的去重保护，
        避免以后谁重新接上这个入口时又出现同一个客户被发两次新客券的问题。
        """
        TenantContext.set_tenant_id(entrance_code.tenant_id)
        coupon_service = CouponService(self.db)
        coupon_service.set_tenant_id(entrance_code.tenant_id)
        existing = await coupon_service.get_available_auto_coupon(customer_id, "new_customer_coupon")
        if existing:
            return {"success_count": 0, "fail_count": 0, "reason": "已持有未使用的新客券", "sent": [], "failed": []}
        template = await self.ensure_new_customer_coupon_template(entrance_code)
        return await coupon_service.send_coupons_with_result(template.id, [customer_id])

    async def _find_reusable_new_customer_template(self, tenant_id: str, amount: float) -> CouponTemplate | None:
        now = datetime.utcnow()
        result = await self.db.execute(
            select(CouponTemplate)
            .filter(
                CouponTemplate.tenant_id == tenant_id,
                CouponTemplate.name == DEFAULT_NEW_CUSTOMER_COUPON_NAME,
                CouponTemplate.type == "FIXED",
                CouponTemplate.status == 1,
                CouponTemplate.end_time > now,
                CouponTemplate.total_stock > CouponTemplate.used_stock,
                and_(CouponTemplate.value >= amount - 0.001, CouponTemplate.value <= amount + 0.001),
            )
            .order_by(CouponTemplate.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _generate_scene(self) -> str:
        while True:
            scene = f"E{str(generate_snowflake_id())[-11:]}"
            result = await self.db.execute(select(EntranceCode).filter(EntranceCode.scene == scene))
            if not result.scalar_one_or_none():
                return scene

    async def _is_miniprogram_tenant(self, tenant_id: str) -> bool:
        """Return whether tenant uses paid mini program mode."""
        try:
            from app.models.tenant import Tenant
            from sqlalchemy.future import select as _select
            result = await self.db.execute(_select(Tenant).where(Tenant.tenant_id == tenant_id))
            tenant = result.scalar_one_or_none()
            return bool(tenant and getattr(tenant, "wx_pay_enabled", False))
        except Exception:
            return False

    async def _generate_code_image(
        self, scene: str, page: str, env_version: str,
        tenant_id: str = "", channel: str = "STORE", table_no: str = ""
    ) -> dict:
        try:
            os.makedirs(ENTRANCE_CODE_DIR, exist_ok=True)
        except Exception as exc:
            return {
                "image_url": None,
                "code_type": "WECHAT",
                "generation_status": "FAILED",
                "generation_error": f"创建目录失败: {str(exc)}",
            }

        if not settings.WECHAT_APP_ or not settings.WECHAT_APP_SECRET:
            return {
                "image_url": None,
                "code_type": "WECHAT",
                "generation_status": "FAILED",
                "generation_error": "微信小程序码生成失败：未配置小程序APPID或APPSECRET",
            }

        try:
            image_bytes = self._fetch_wechat_code(scene, page, env_version)
            logo_url = await self._get_tenant_logo_url(tenant_id)
            if logo_url:
                image_bytes = self._overlay_center_logo(image_bytes, logo_url)
            file_name = f"{scene}.jpg"
            file_path = os.path.join(ENTRANCE_CODE_DIR, file_name)
            with open(file_path, "wb") as file:
                file.write(image_bytes)
            return {
                "image_url": f"/static/entrance-codes/{file_name}",
                "code_type": "WECHAT",
                "generation_status": "SUCCESS",
                "generation_error": None,
            }
        except Exception as exc:
            wechat_error = self._format_wechat_error(exc)
            return {
                "image_url": None,
                "code_type": "WECHAT",
                "generation_status": "FAILED",
                "generation_error": wechat_error,
            }

    async def _get_tenant_logo_url(self, tenant_id: str) -> str | None:
        if not tenant_id:
            return None
        try:
            from app.models.tenant import Tenant
            result = await self.db.execute(
                select(Tenant.logo_url).where(Tenant.tenant_id == tenant_id)
            )
            logo_url = result.scalar_one_or_none()
            return logo_url or None
        except Exception:
            return None

    def _overlay_center_logo(self, image_bytes: bytes, logo_url: str) -> bytes:
        """把门店 Logo 叠在小程序码中心，盖掉默认的平台头像。

        任何一步失败（Logo 下载不到、格式坏、Pillow 报错）都返回原图，
        绝不因为 Logo 让整张码出不来。
        """
        try:
            from io import BytesIO
            from PIL import Image, ImageDraw

            if not logo_url or not str(logo_url).lower().startswith(("http://", "https://")):
                return image_bytes

            code_img = Image.open(BytesIO(image_bytes)).convert("RGBA")
            cw, ch = code_img.size

            request = urllib.request.Request(
                logo_url, headers={"User-Agent": "xiao-entrance-code/1.0"}
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                logo_img = Image.open(BytesIO(response.read())).convert("RGBA")

            ss = 4  # 超采样抗锯齿
            # 直径压在码宽的 20% 以内：这正好是小程序码原生头像的占位，
            # 再大就会盖住外圈的数据点导致扫不出。白边只要薄薄一圈，
            # 够盖掉原平台头像的边缘即可，不是一圈光晕。
            diameter = max(40, int(cw * 0.20))
            ring = max(2, int(diameter * 0.04))
            backing = diameter + ring * 2

            logo_scaled = logo_img.resize((diameter * ss, diameter * ss), Image.LANCZOS)
            mask = Image.new("L", (diameter * ss, diameter * ss), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, diameter * ss, diameter * ss), fill=255)
            logo_round = Image.new("RGBA", (diameter * ss, diameter * ss), (0, 0, 0, 0))
            logo_round.paste(logo_scaled, (0, 0), mask)
            logo_round = logo_round.resize((diameter, diameter), Image.LANCZOS)

            backing_img = Image.new("RGBA", (backing * ss, backing * ss), (0, 0, 0, 0))
            ImageDraw.Draw(backing_img).ellipse(
                (0, 0, backing * ss, backing * ss), fill=(255, 255, 255, 255)
            )
            backing_img = backing_img.resize((backing, backing), Image.LANCZOS)

            cx, cy = cw // 2, ch // 2
            code_img.alpha_composite(backing_img, (cx - backing // 2, cy - backing // 2))
            code_img.alpha_composite(logo_round, (cx - diameter // 2, cy - diameter // 2))

            out = BytesIO()
            code_img.convert("RGB").save(out, "JPEG", quality=92)
            return out.getvalue()
        except Exception:
            return image_bytes

    def _write_qr_code(self, scene: str, tenant_id: str, channel: str, table_no: str, use_h5: bool = False) -> dict:
        try:
            import qrcode
            from PIL import Image, ImageDraw, ImageFont

            base = getattr(settings, "H5_ORDER_BASE_URL", "https://saas.zhangbaiyang.com")
            if use_h5:
                if tenant_id and table_no:
                    url = f"{base}/h5/{tenant_id}?table={table_no}"
                elif tenant_id:
                    url = f"{base}/h5/{tenant_id}"
                else:
                    url = base
            elif channel == "TABLE" and tenant_id and table_no:
                url = f"{base}/order?shop={tenant_id}&table={table_no}"
            elif tenant_id:
                url = f"{base}/order?shop={tenant_id}"
            else:
                url = base

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=3,
            )
            qr.add_data(url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="#111827", back_color="white").convert("RGB")

            label = f"扫码点餐 - {table_no}" if table_no else "扫码点餐"
            canvas_w, canvas_h = qr_img.width, qr_img.height + 60
            canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
            canvas.paste(qr_img, (0, 60))

            draw = ImageDraw.Draw(canvas)
            font = None
            _cn_font_paths = [
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            ]
            for _fp in _cn_font_paths:
                try:
                    font = ImageFont.truetype(_fp, 26)
                    break
                except Exception:
                    continue
            if font is None:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), label, font=font)
            text_w = bbox[2] - bbox[0]
            draw.text(((canvas_w - text_w) // 2, 16), label, fill="#07C160", font=font)

            file_name = f"{scene}.png"
            file_path = os.path.join(ENTRANCE_CODE_DIR, file_name)
            canvas.save(file_path, "PNG")
            return {
                "image_url": f"/static/entrance-codes/{file_name}",
                "code_type": "QR",
                "generation_status": "SUCCESS",
                "generation_error": None,
            }
        except Exception as exc:
            return {
                "image_url": None,
                "code_type": "QR",
                "generation_status": "FAILED",
                "generation_error": f"二维码生成失败: {str(exc)}",
            }

    @staticmethod
    def _format_wechat_error(exc: Exception) -> str:
        text = str(exc)
        if "10061" in text or "actively refused" in text:
            return "Wechat code generation failed: cannot connect to WeChat API"
        if "timed out" in text or "timeout" in text:
            return "Wechat code generation failed: WeChat API request timed out"
        return f"Wechat code generation failed: {text}"[:512]

    def _fetch_wechat_code(self, scene: str, page: str, env_version: str) -> bytes:
        token_params = urllib.parse.urlencode(
            {
                "grant_type": "client_credential",
                "appid": settings.WECHAT_APP_,
                "secret": settings.WECHAT_APP_SECRET,
            }
        )
        token_url = f"https://api.weixin.qq.com/cgi-bin/token?{token_params}"
        with urllib.request.urlopen(token_url, timeout=8) as response:
            token_data = json.loads(response.read().decode("utf-8"))
        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError(token_data.get("errmsg") or "WeChat access_token request failed")

        payload = json.dumps(
            {
                "scene": scene,
                "page": page,
                "check_path": False,
                "env_version": env_version,
                "width": 430,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token={access_token}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            error = json.loads(body.decode("utf-8"))
            raise RuntimeError(error.get("errmsg") or "WeChat mini program code generation failed")
        return body
