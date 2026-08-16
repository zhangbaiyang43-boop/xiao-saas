import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from pathlib import Path

def test_r08_empty_snapshot_cursor_uses_pre_query_watermark_and_delivers_racing_order():
    from app.services import workbench_sync_service as sync_service

    t0 = datetime(2026, 8, 15, 4, 0, 0)
    racing_order = SimpleNamespace(id=101, updated_at=t0 + timedelta(seconds=2))
    query_started = False

    async def load_candidates(_db, _tenant_id):
        nonlocal query_started
        query_started = True
        return []

    async def run():
        return await sync_service.load_workbench_snapshot_with_cursor(
            object(),
            'tenant-a',
            now_fn=lambda: t0,
            candidate_loader=load_candidates,
        )

    orders, cursor = asyncio.run(run())

    assert query_started is True
    assert orders == []
    watermark, page_updated_at, page_order_id = sync_service.decode_workbench_cursor(cursor)
    assert watermark == t0
    assert sync_service.order_matches_delta_cursor(
        racing_order,
        watermark=watermark,
        page_u=page_updated_at,
        page_i=page_order_id,
    ) is True


def test_r08_workbench_full_endpoint_uses_pre_query_snapshot_helper():
    source = (Path(__file__).parents[1] / 'app/api/v1/orders.py').read_text(encoding='utf-8')
    function_source = source.split('async def list_workbench_orders(', 1)[1].split(
        '@router.get("/orders/workbench/changes")', 1
    )[0]
    assert 'load_workbench_snapshot_with_cursor' in function_source
    assert 'cursor_from_orders(candidates, fallback_now=datetime.utcnow())' not in function_source


def test_owner_dataset_visibility_preserves_today_history_and_old_active_orders():
    from app.services import workbench_sync_service as sync_service

    day_start = datetime(2026, 8, 15, 0, 0, 0)
    day_end = day_start + timedelta(days=1)

    def order(status, created_at):
        return SimpleNamespace(status=status, created_at=created_at)

    today = day_start + timedelta(hours=2)
    old = day_start - timedelta(days=2)
    assert sync_service.is_order_visible_in_owner_list(order('pending_payment', today), day_start, day_end)
    assert sync_service.is_order_visible_in_owner_list(order('cancelled', today), day_start, day_end)
    assert sync_service.is_order_visible_in_owner_list(order('settled', today), day_start, day_end)
    assert sync_service.is_order_visible_in_owner_list(order('done', old), day_start, day_end)
    assert sync_service.is_order_visible_in_owner_list(order('pending', old), day_start, day_end)
    assert not sync_service.is_order_visible_in_owner_list(order('cancelled', old), day_start, day_end)


def test_owner_delta_route_exists_and_is_owner_only_pure_read():
    source = (Path(__file__).parents[1] / 'app/api/v1/orders.py').read_text(encoding='utf-8')
    assert source.count('@router.get("/orders/changes")') == 1
    route = source.split('async def list_owner_order_changes(', 1)[1].split('@router.', 1)[0]
    assert 'principal.is_owner' in route
    assert 'reconcile_print_orders' not in route
    assert 'get_owner_order_changes' in route


def test_empty_owner_delta_is_one_query_without_order_item_n_plus_one():
    from app.services import workbench_sync_service as sync_service

    class Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class DB:
        calls = 0

        async def execute(self, _query):
            self.calls += 1
            return Result()

    db = DB()
    cursor = sync_service.committed_cursor_from_watermark(datetime.utcnow() - timedelta(seconds=2))
    packed = asyncio.run(
        sync_service.get_owner_order_changes(db, tenant_id='tenant-a', cursor=cursor)
    )
    assert packed['orders'] == []
    assert packed['removed_ids'] == []
    assert db.calls == 1


def test_twenty_owner_delta_page_does_not_preload_items_before_route_serialization():
    from app.services import workbench_sync_service as sync_service

    now = datetime.utcnow()
    rows = [
        SimpleNamespace(
            id=index,
            tenant_id='tenant-a',
            status='pending',
            created_at=now,
            updated_at=now,
        )
        for index in range(1, 21)
    ]

    class Result:
        def __init__(self, values):
            self.values = values

        def scalars(self):
            return self

        def all(self):
            return self.values

    class DB:
        calls = 0

        async def execute(self, _query):
            self.calls += 1
            return Result(rows if self.calls == 1 else [])

    db = DB()
    cursor = sync_service.committed_cursor_from_watermark(now - timedelta(seconds=2))
    packed = asyncio.run(
        sync_service.get_owner_order_changes(db, tenant_id='tenant-a', cursor=cursor)
    )
    assert len(packed['orders']) == 20
    assert packed['removed_ids'] == []
    assert db.calls == 1


def test_empty_owner_delta_route_skips_complete_owner_serializer():
    source = (Path(__file__).parents[1] / 'app/api/v1/orders.py').read_text(encoding='utf-8')
    route = source.split('async def list_owner_order_changes(', 1)[1].split('@router.', 1)[0]
    assert 'if packed["orders"]' in route


def test_final_delta_page_advances_to_pre_query_boundary_instead_of_replaying_overlap_forever():
    from app.services import workbench_sync_service as sync_service

    old_watermark = datetime(2026, 8, 15, 4, 0, 0)
    scan_boundary = old_watermark + timedelta(seconds=5)
    repeated = SimpleNamespace(
        id=20,
        updated_at=old_watermark,
        created_at=old_watermark,
        tenant_id='tenant-a',
        status='pending',
    )
    previous = sync_service.committed_cursor_from_watermark(old_watermark)
    advanced = sync_service.advance_cursor_after_page(
        [repeated],
        previous,
        has_more=False,
        committed_watermark=scan_boundary,
    )
    watermark, page_updated_at, page_order_id = sync_service.decode_workbench_cursor(advanced)
    assert watermark == scan_boundary
    assert not sync_service.order_matches_delta_cursor(
        repeated,
        watermark=watermark,
        page_u=page_updated_at,
        page_i=page_order_id,
    )


def test_owner_delta_captures_scan_boundary_before_query_and_commits_it():
    source = (Path(__file__).parents[1] / 'app/services/workbench_sync_service.py').read_text(encoding='utf-8')
    owner_delta = source.split('async def get_owner_order_changes(', 1)[1]
    assert 'scan_boundary = datetime.utcnow()' in owner_delta
    assert 'committed_watermark=scan_boundary' in owner_delta


def test_owner_full_cursor_header_preserves_direct_business_return_contract():
    source = (Path(__file__).parents[1] / 'app/api/v1/orders.py').read_text(encoding='utf-8')
    route = source.split('async def list_orders(', 1)[1].split('@router.get("/orders/changes")', 1)[0]
    assert 'response: Response = None' in route
    assert 'response.headers[WORKBENCH_CURSOR_HEADER]' in route
    assert 'JSONResponse(content=result.to_response())' not in route
    assert 'return result' in route
