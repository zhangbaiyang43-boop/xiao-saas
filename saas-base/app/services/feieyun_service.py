import hashlib
import time
import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

FEIEYUN_API = "https://api.feieyun.cn/Api/Open/"


def _sig(user: str, ukey: str, stime: str) -> str:
    raw = user + ukey + stime
    return hashlib.sha1(raw.encode()).hexdigest()


async def print_order(sn: str, key: str, content: str, times: int = 1) -> bool:
    """调飞鹅云打印一张小票，成功返回 True。"""
    user = settings.FEIEYUN_USER
    ukey = settings.FEIEYUN_UKEY
    if not user or not ukey:
        logger.warning("飞鹅云平台账号未配置，跳过打印")
        return False

    stime = str(int(time.time()))
    data = {
        "user": user,
        "ukey": ukey,
        "stime": stime,
        "sig": _sig(user, ukey, stime),
        "apiname": "Open_printMsg",
        "sn": sn,
        "k": key,
        "content": content,
        "times": str(times),
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(FEIEYUN_API, data=data)
            body = resp.json()
            if body.get("ret") == 1:
                return True
            logger.warning(f"飞鹅云打印失败: {body}")
            return False
    except Exception as e:
        logger.warning(f"飞鹅云请求异常: {e}")
        return False


def build_order_ticket(order, order_items) -> str:
    """把订单对象格式化为小票文本（ESC 指令 + 纯文本）。

    order_items 是查出来的 OrderItem 行（.name/.qty/.price 属性，不是 dict）——Order
    模型本身没有 items 关系/属性，之前这里用 getattr(order, "items", None) 永远拿到
    空列表，导致飞鹅云小票从不包含任何菜品明细。"""
    lines = []
    lines.append("<CB>新订单</CB>")   # 居中加粗标题
    pickup_no = getattr(order, "pickup_no", None)
    if pickup_no:
        lines.append(f"<CB>取餐号：{pickup_no}</CB>")
    lines.append(f"桌号：{getattr(order, 'table_no', '') or '—'}")
    lines.append(f"单号：{str(order.id)[-8:]}")
    lines.append(f"来源：{'H5点餐' if getattr(order, 'source', '') == 'h5' else '小程序'}")
    lines.append("--------------------------------")

    for item in order_items or []:
        lines.append(f"{item.name}  x{item.qty}  ¥{float(item.price):.1f}")

    lines.append("--------------------------------")
    remark = getattr(order, "remark", "") or ""
    if remark:
        lines.append(f"备注：{remark}")
    total = getattr(order, "total", 0)
    lines.append(f"合计：¥{float(total):.2f}")
    lines.append("<BR>")
    return "\n".join(lines)
