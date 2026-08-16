from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.models.perf_sample import PerfSample

router = APIRouter(prefix="/api/v1/perf", tags=["性能采样"])

# 跟 member-mini-client/src/utils/perf.js 里的 TRACKED_METRICS 保持完全一致，
# 防止上报接口被拿去塞任意字符串当 metric 名，污染统计维度。以后 perf.js 那边
# 加新指标，这里要跟着同步加，两边手动保持一致，不做成共享配置（跨语言共享
# 配置这种小事没必要，注释里互相提醒对方位置就够）。
ALLOWED_METRICS = {
    "scan_to_interactive",
    "stage_cold_start_to_onload",
    "stage_onload_to_menu_ready",
    "stage_menu_ready_to_render",
    "menu_api",
    "cart_open",
    "submit_order",
    "launch_to_entry",
    "entry_resolve",
    "entry_to_menu",
    "menu_onload_to_first_content",
    "menu_onload_to_interactive",
    "shop_info_api",
    "menu_processing",
    "first_content_to_interactive",
    "first_cart_response",
}

MAX_BATCH_SIZE = 50


@router.post("/report")
async def report_perf_samples(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tenant_id = str(body.get("tenant_id") or "")[:32]
    client_id = str(body.get("client_id") or "")[:64] or None
    samples = body.get("samples")
    if not isinstance(samples, list):
        return success_response(data={"accepted": 0}, msg="ok")
    rows = []
    for s in samples[:MAX_BATCH_SIZE]:
        metric = str(s.get("metric") or "")
        ms = s.get("ms")
        if metric not in ALLOWED_METRICS or not isinstance(ms, (int, float)) or ms < 0:
            continue
        meta = s.get("meta")
        rows.append(PerfSample(
            tenant_id=tenant_id,
            metric=metric,
            ms=int(ms),
            meta=str(meta)[:500] if meta else None,
            client_id=client_id,
        ))
    if rows:
        db.add_all(rows)
        await db.commit()
    return success_response(data={"accepted": len(rows)}, msg="ok")
