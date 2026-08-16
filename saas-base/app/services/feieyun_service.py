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


async def print_order(sn: str, key: str, content: str, times: int = 1) -> str:
    """调飞鹅云打印一张小票。返回三态而不是布尔值，因为这两种失败在语义上完全不同，调用方
    需要能分开处理：

    - "success"：飞鹅云明确回了 ret==1，真的打印了。
    - "failed"：飞鹅云回了响应，但明确说没成功（sn/key 不对、打印机离线等）——可以放心
      认定这次没打印，重试是安全的。
    - "unknown"：请求超时/网络异常，没拿到飞鹅云的响应——不知道这次请求有没有真的送达
      并打印成功。飞鹅云的 Open_printMsg 接口不支持外部单号幂等去重（已核实其开放平台
      文档），如果这种情况也当"failed"处理然后自动重试，一旦上一次其实已经打印成功，
      就会造成同一单重复出票。调用方必须把这种情况和"failed"分开，不能自动重试，只能
      交给能看到打印机的人来判断。
    """
    user = settings.FEIEYUN_USER
    ukey = settings.FEIEYUN_UKEY
    if not user or not ukey:
        logger.warning("飞鹅云平台账号未配置，跳过打印")
        return "failed"

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
                return "success"
            logger.warning(f"飞鹅云打印失败: {body}")
            return "failed"
    except Exception as e:
        logger.warning(f"飞鹅云请求异常，打印结果未知: {e}")
        return "unknown"


def build_order_ticket(order, order_items) -> str:
    """把订单对象格式化为小票文本（ESC 指令 + 纯文本）。

    order_items 是查出来的 OrderItem 行（.name/.qty/.price 属性，不是 dict）——Order
    模型本身没有 items 关系/属性，之前这里用 getattr(order, "items", None) 永远拿到
    空列表，导致飞鹅云小票从不包含任何菜品明细。"""
    lines = []
    lines.append("<CB>新订单</CB>")   # 居中加粗标题
    pickup_no = getattr(order, "pickup_no", None)
    if pickup_no:
        lines.append(f"<CB>桌牌号：{pickup_no}</CB>")
    lines.append(f"桌号：{getattr(order, 'table_no', '') or '—'}")
    lines.append(f"单号：{str(order.id)[-8:]}")
    lines.append(f"来源：{'H5点餐' if getattr(order, 'source', '') == 'h5' else '小程序'}")
    lines.append("--------------------------------")

    for item in order_items or []:
        lines.append(f"{item.name}  x{item.qty}  ¥{float(item.price):.1f}")
        item_remark = (getattr(item, "item_remark", "") or "").strip()
        if item_remark:
            lines.append(f"  菜品备注：{item_remark}")

    lines.append("--------------------------------")
    remark = getattr(order, "remark", "") or ""
    if remark:
        lines.append(f"备注：{remark}")
    total = getattr(order, "total", 0)
    lines.append(f"合计：¥{float(total):.2f}")
    lines.append("<BR>")
    return "\n".join(lines)
