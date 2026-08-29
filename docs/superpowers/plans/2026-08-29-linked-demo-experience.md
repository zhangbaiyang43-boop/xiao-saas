# Linked Demo Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 30-minute, passwordless, session-isolated demo where a customer orders in the real WeChat mini program and a restaurant owner fulfills that same order in a safe merchant Demo workbench.

**Architecture:** A dedicated demo tenant owns a pool of 20 pre-generated `channel=DEMO` table entrance codes. A signed launch code creates a real `DiningSession`, returns a 30-minute `demo_merchant` JWT scoped to that session, and the new Admin H5 Demo workbench calls only `/api/v1/demo/*`. The existing mini-program order flow is reused with a narrow guest-only Demo branch, while middleware and query predicates prevent the Demo token from reaching formal merchant data or another Demo session.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy AsyncSession, MySQL, Redis, PyJWT, Vue 3, Ant Design Vue, Axios, uni-app, Vitest, Node test runner.

---

## Execution preflight

Implement in an isolated worktree based on commit `1cb4eec`. Do not execute this plan in the dirty `main` checkout. Use branch `codex/linked-demo-experience`, worktree `C:\Users\15936\Desktop\xiao-linked-demo-experience`, and preserve all unrelated files in `C:\Users\15936\Desktop\xiao`.

Before Task 1, run:

```powershell
cd C:\Users\15936\Desktop\xiao
git worktree add C:\Users\15936\Desktop\xiao-linked-demo-experience -b codex/linked-demo-experience 1cb4eec
cd C:\Users\15936\Desktop\xiao-linked-demo-experience
git rev-parse HEAD
git status --short
```

Expected in the isolated worktree: HEAD includes `1cb4eec`; status is clean. If the new branch starts from a later commit, record that exact SHA and confirm it contains `1cb4eec` before continuing.

## File responsibility map

Backend:

- `saas-base/app/config.py`: Demo environment configuration only.
- `saas-base/app/core/security.py`: create and validate launch/session JWTs.
- `saas-base/app/middleware/auth_middleware.py`: admit `demo_merchant` only to Demo API paths.
- `saas-base/app/services/demo_session_service.py`: rate limit, table allocation, stale session expiry, scoped reads and actions.
- `saas-base/app/api/v1/demo.py`: request/response models and route wiring.
- `saas-base/app/api/v1/member.py`: reject member creation for the configured Demo tenant.
- `saas-base/app/main.py`: register the Demo router.
- `saas-base/scripts/generate_demo_launch_code.py`: generate the signed 365-day card launch code.

Admin H5:

- `admin-h5/src/demo/session.js`: Demo-only session storage and order-action mapping.
- `admin-h5/src/api/demoRequest.js`: Axios client that reads only the Demo session token.
- `admin-h5/src/api/demo.js`: Demo endpoint functions.
- `admin-h5/src/views/DemoWorkbench.vue`: mobile-first owner Demo page.
- `admin-h5/src/router/index.js`: public `/demo` route and guard exception.
- `admin-h5/scripts/test-demo-workbench.mjs`: behavior and route/storage contract tests.
- `admin-h5/package.json`: targeted test command.

Mini program:

- `member-mini-client/src/pages/entry/index.vue`: persist `channel=DEMO` and clear prior customer session.
- `member-mini-client/src/subpkg-order/composables/useCheckout.js`: Demo checkout goes directly to guest submit.
- Existing focused tests verify formal checkout is unchanged.

Sales material:

- `docs/frontend/owner-experience-card-ab-demo.html`: owner QR becomes the primary entrance and explains the dynamic customer code.
- `docs/frontend/owner-experience-card-ab-demo.test.cjs`: assert the new two-device flow and retain A6/print checks.

## Task 1: Demo configuration and signed token helpers

**Files:**

- Modify: `saas-base/app/config.py`
- Modify: `saas-base/app/core/security.py`
- Create: `saas-base/scripts/generate_demo_launch_code.py`
- Create: `saas-base/tests/test_demo_security.py`

- [ ] **Step 1: Write failing token tests**

Create `saas-base/tests/test_demo_security.py` with behavior tests for launch and session tokens:

```python
from datetime import timedelta
import unittest
from unittest.mock import patch

from app.core.security import (
    create_demo_launch_code,
    create_demo_session_token,
    decode_demo_launch_code,
    decode_demo_session_token,
)


class DemoSecurityTest(unittest.TestCase):
    @patch("app.core.security.settings.DEMO_TENANT_ID", "demo-tenant")
    def test_launch_code_has_launch_type_only(self):
        token = create_demo_launch_code(expires_delta=timedelta(minutes=5))
        payload = decode_demo_launch_code(token)
        self.assertEqual(payload["type"], "demo_launch")
        self.assertNotIn("tenant_id", payload)

    @patch("app.core.security.settings.DEMO_TENANT_ID", "demo-tenant")
    def test_session_token_is_scoped_to_one_dining_session(self):
        token = create_demo_session_token(
            tenant_id="demo-tenant",
            dining_session_id="123",
            table_no="DEMO-01",
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_demo_session_token(token)
        self.assertEqual(payload["type"], "demo_merchant")
        self.assertEqual(payload["scope"], "demo_order_fulfillment")
        self.assertEqual(payload["dining_session_id"], "123")

    def test_wrong_token_type_is_rejected(self):
        self.assertIsNone(decode_demo_session_token(create_demo_launch_code()))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd C:\Users\15936\Desktop\xiao-linked-demo-experience\saas-base
py -3.10 -m pytest tests/test_demo_security.py -v
```

Expected: collection fails because the four Demo security functions do not exist.

- [ ] **Step 3: Add explicit Demo settings**

Add to `Settings` in `saas-base/app/config.py` near the existing auth settings:

```python
    DEMO_TENANT_ID: str = ""
    DEMO_SESSION_MINUTES: int = 30
    DEMO_LAUNCH_DAYS: int = 365
    DEMO_TABLE_POOL_SIZE: int = 20
    DEMO_START_IP_LIMIT_PER_MINUTE: int = 5
    DEMO_START_CODE_LIMIT_PER_MINUTE: int = 20
```

Defaults must disable allocation when `DEMO_TENANT_ID` is empty. Do not add a secret or tenant identifier to source control.

- [ ] **Step 4: Implement typed token helpers**

Add these focused helpers to `saas-base/app/core/security.py` using the existing JWT secret and algorithm:

```python
def create_demo_launch_code(expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(days=settings.DEMO_LAUNCH_DAYS))
    return jwt.encode(
        {"sub": "demo-launch", "type": "demo_launch", "exp": expire},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_demo_launch_code(token: str) -> Optional[dict]:
    payload = verify_token(token)
    if not payload or payload.get("type") != "demo_launch":
        return None
    return payload


def create_demo_session_token(
    *, tenant_id: str, dining_session_id: str, table_no: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.DEMO_SESSION_MINUTES))
    return jwt.encode(
        {
            "sub": f"demo-session:{dining_session_id}",
            "tenant_id": tenant_id,
            "dining_session_id": str(dining_session_id),
            "table_no": table_no,
            "type": "demo_merchant",
            "scope": "demo_order_fulfillment",
            "exp": expire,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_demo_session_token(token: str) -> Optional[dict]:
    payload = verify_token(token)
    if not payload or payload.get("type") != "demo_merchant":
        return None
    if payload.get("scope") != "demo_order_fulfillment":
        return None
    if not payload.get("tenant_id") or not payload.get("dining_session_id"):
        return None
    return payload
```

- [ ] **Step 5: Add the launch-code CLI**

Create `saas-base/scripts/generate_demo_launch_code.py`:

```python
from app.config import settings
from app.core.security import create_demo_launch_code


def main() -> None:
    if not settings.DEMO_TENANT_ID:
        raise SystemExit("DEMO_TENANT_ID 未配置，拒绝生成体验入口")
    print(create_demo_launch_code())


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests and commit**

Run:

```powershell
py -3.10 -m pytest tests/test_demo_security.py -v
```

Expected: all tests pass.

Commit only the four Task 1 files:

```powershell
git add -- saas-base/app/config.py saas-base/app/core/security.py saas-base/scripts/generate_demo_launch_code.py saas-base/tests/test_demo_security.py
git commit -m "feat(demo): add scoped demo tokens"
```

## Task 2: Middleware isolation for Demo tokens

**Files:**

- Modify: `saas-base/app/middleware/auth_middleware.py`
- Create: `saas-base/tests/test_demo_auth_middleware.py`

- [ ] **Step 1: Write middleware isolation tests**

Create `saas-base/tests/test_demo_auth_middleware.py` using the same `Request` construction style as `test_auth_middleware_tenant_status.py`. Cover:

```python
@patch("app.middleware.auth_middleware._is_tenant_active", return_value=True)
@patch("app.middleware.auth_middleware.verify_token")
async def test_demo_token_can_reach_demo_session(self, verify, _active):
    verify.return_value = {
        "type": "demo_merchant",
        "tenant_id": "demo-tenant",
        "dining_session_id": "123",
        "table_no": "DEMO-01",
        "scope": "demo_order_fulfillment",
        "sub": "demo-session:123",
    }
    response = await self.middleware.dispatch(make_request("/api/v1/demo/session"), dummy_call_next)
    self.assertEqual(response.status_code, 200)


async def test_demo_token_cannot_reach_formal_orders(self):
    response = await self.dispatch_demo("/api/v1/orders")
    self.assertEqual(response.status_code, 403)


async def test_demo_token_for_wrong_tenant_is_rejected(self):
    response = await self.dispatch_demo("/api/v1/demo/session", tenant_id="other")
    self.assertEqual(response.status_code, 403)


async def test_formal_merchant_path_remains_unchanged(self):
    response = await self.dispatch_owner("/api/v1/customers")
    self.assertEqual(response.status_code, 200)
```

Patch `settings.DEMO_TENANT_ID` to `demo-tenant` in the Demo cases.

- [ ] **Step 2: Run tests and verify RED**

```powershell
py -3.10 -m pytest tests/test_demo_auth_middleware.py -v
```

Expected: Demo token requests return 403 because middleware has no Demo branch.

- [ ] **Step 3: Add a fail-closed Demo branch**

In `AuthMiddleware.dispatch`, immediately after payload fields are copied to `request.state` and before merchant resolution, add:

```python
        if payload.get("type") == "demo_merchant":
            expected_tenant = (settings.DEMO_TENANT_ID or "").strip()
            allowed = (
                bool(expected_tenant)
                and request.url.path.startswith("/api/v1/demo/")
                and payload.get("tenant_id") == expected_tenant
                and payload.get("scope") == "demo_order_fulfillment"
                and payload.get("dining_session_id")
            )
            if not allowed:
                return JSONResponse(
                    status_code=403,
                    content=RespVo(code=403, msg="体验凭证无权访问此功能").to_response(),
                )
            request.state.demo_session_id = str(payload["dining_session_id"])
            request.state.demo_table_no = str(payload.get("table_no") or "")
            if not await _is_tenant_active(expected_tenant):
                return JSONResponse(
                    status_code=403,
                    content=RespVo(code=403, msg="体验门店不可用").to_response(),
                )
            return await call_next(request)
```

Import `settings` from `app.config`. Add `/api/v1/demo/sessions/start` to `WHITELIST`; no other Demo path belongs in the whitelist.

- [ ] **Step 4: Run focused and existing auth tests**

```powershell
py -3.10 -m pytest tests/test_demo_auth_middleware.py tests/test_auth_middleware_tenant_status.py tests/test_register_code_auth_whitelist.py -v
```

Expected: all tests pass; formal owner and member behavior is unchanged.

- [ ] **Step 5: Commit**

```powershell
git add -- saas-base/app/middleware/auth_middleware.py saas-base/tests/test_demo_auth_middleware.py
git commit -m "feat(demo): isolate demo authentication"
```

## Task 3: Demo session allocation and rate limiting

**Files:**

- Create: `saas-base/app/services/demo_session_service.py`
- Create: `saas-base/tests/test_demo_session_service.py`

- [ ] **Step 1: Write allocation tests with a real async database**

Create `test_demo_session_service.py` with an in-memory SQLite database containing one demo tenant and two active `EntranceCode` rows with `channel="DEMO"`, `entry_type="table"`, `table_no="DEMO-01"` and `DEMO-02`. Mock only Redis rate limiting and token encoding. Test these behaviors:

```python
async def test_start_allocates_open_session_and_returns_table_code(self):
    result = await service.start_session("valid-launch", "127.0.0.1")
    self.assertEqual(result["tableNo"], "DEMO-01")
    self.assertEqual(result["customerCodeImageUrl"], "/static/entrance-codes/demo-01.png")
    self.assertTrue(result["diningSessionId"])


async def test_two_active_starts_use_different_tables(self):
    first = await service.start_session("valid-launch", "127.0.0.1")
    second = await service.start_session("valid-launch", "127.0.0.2")
    self.assertNotEqual(first["tableNo"], second["tableNo"])


async def test_pool_full_raises_rate_style_error_without_reuse(self):
    await service.start_session("valid-launch", "127.0.0.1")
    await service.start_session("valid-launch", "127.0.0.2")
    with self.assertRaises(DemoPoolFullError):
        await service.start_session("valid-launch", "127.0.0.3")


async def test_expired_open_session_is_closed_before_reuse(self):
    stale = await self.insert_open_session(started_minutes_ago=31, table_no="DEMO-01")
    result = await service.start_session("valid-launch", "127.0.0.1")
    await self.db.refresh(stale)
    self.assertEqual(stale.status, "EXPIRED")
    self.assertIsNone(stale.active_key)
    self.assertEqual(result["tableNo"], "DEMO-01")
```

- [ ] **Step 2: Run allocation tests and verify RED**

```powershell
py -3.10 -m pytest tests/test_demo_session_service.py -v
```

Expected: import fails because `DemoSessionService` does not exist.

- [ ] **Step 3: Implement fail-closed Redis limiting**

In `demo_session_service.py`, define explicit exceptions and use `redis_client.pipeline(transaction=True)`:

```python
class DemoUnavailableError(RuntimeError):
    pass


class DemoRateLimitedError(RuntimeError):
    pass


class DemoPoolFullError(RuntimeError):
    pass


class DemoInvalidLaunchError(RuntimeError):
    pass


async def enforce_demo_start_limit(ip: str, launch_code: str) -> None:
    if not settings.REDIS_ENABLED:
        raise DemoUnavailableError("体验服务暂不可用")
    fingerprint = hashlib.sha256(launch_code.encode("utf-8")).hexdigest()[:16]
    minute = int(time.time() // 60)
    keys = [
        (f"demo:start:ip:{ip}:{minute}", settings.DEMO_START_IP_LIMIT_PER_MINUTE),
        (f"demo:start:code:{fingerprint}:{minute}", settings.DEMO_START_CODE_LIMIT_PER_MINUTE),
    ]
    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            for key, _limit in keys:
                pipe.incr(key)
                pipe.expire(key, 90)
            values = await pipe.execute()
    except Exception as exc:
        raise DemoUnavailableError("体验服务暂不可用") from exc
    counts = [int(values[0]), int(values[2])]
    if any(count > limit for count, (_key, limit) in zip(counts, keys)):
        raise DemoRateLimitedError("请求过于频繁，请稍后再试")
```

- [ ] **Step 4: Implement transaction-scoped table allocation**

`DemoSessionService` must inherit `BaseService`. Its `start_session` must:

1. Reject empty `DEMO_TENANT_ID`.
2. Validate `decode_demo_launch_code(launch_code)`.
3. Enforce rate limit.
4. Select active `EntranceCode` rows for only the configured tenant, `channel="DEMO"`, `entry_type="table"`, limited by `DEMO_TABLE_POOL_SIZE`, ordered by table number, with `with_for_update(skip_locked=True)`.
5. For each row, expire an `OPEN` `DiningSession` only when `started_at` is older than the 30-minute cutoff.
6. Skip rows with a non-stale `OPEN` session.
7. Call existing `DiningSessionService.resolve_session` for the first free row with `client_id=f"demo-admin-{secrets.token_hex(8)}"`.
8. Commit once and return camelCase data plus a signed Demo token.

The central query predicates must be visible in code:

```python
select(EntranceCode).where(
    EntranceCode.tenant_id == demo_tenant_id,
    EntranceCode.channel == "DEMO",
    EntranceCode.entry_type == "table",
    EntranceCode.status == 1,
)
```

When expiring a stale Demo session, set:

```python
stale.status = "EXPIRED"
stale.active_key = None
stale.closed_at = now
stale.closed_by = "demo_expiry"
```

Never accept a tenant or table from the request body.

- [ ] **Step 5: Run allocation tests**

```powershell
py -3.10 -m pytest tests/test_demo_session_service.py -v
```

Expected: all allocation, pool-full, expiry and missing-config tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- saas-base/app/services/demo_session_service.py saas-base/tests/test_demo_session_service.py
git commit -m "feat(demo): allocate isolated demo sessions"
```

## Task 4: Scoped Demo order reads and fulfillment actions

**Files:**

- Modify: `saas-base/app/services/demo_session_service.py`
- Modify: `saas-base/tests/test_demo_session_service.py`

- [ ] **Step 1: Add failing behavior tests**

Extend the service test with orders belonging to two sessions and another tenant:

```python
async def test_snapshot_returns_only_token_session_and_no_pii(self):
    data = await service.get_session_snapshot("demo-tenant", self.session_a.id)
    self.assertEqual([o["orderId"] for o in data["orders"]], [str(self.order_a.id)])
    forbidden = {"phone", "openid", "customerId", "transactionId", "paymentTransactionId"}
    self.assertTrue(forbidden.isdisjoint(data["orders"][0]))


async def test_cross_session_status_update_looks_not_found(self):
    with self.assertRaises(DemoOrderNotFoundError):
        await service.update_order_status(
            tenant_id="demo-tenant",
            dining_session_id=self.session_a.id,
            order_id=self.order_b.id,
            status="preparing",
        )


async def test_only_pending_preparing_done_transitions_are_exposed(self):
    preparing = await service.update_order_status(
        tenant_id="demo-tenant",
        dining_session_id=self.session_a.id,
        order_id=self.order_a.id,
        status="preparing",
    )
    done = await service.update_order_status(
        tenant_id="demo-tenant",
        dining_session_id=self.session_a.id,
        order_id=self.order_a.id,
        status="done",
    )
    self.assertEqual(preparing["status"], "preparing")
    self.assertEqual(done["status"], "done")
    with self.assertRaises(DemoActionDeniedError):
        await service.update_order_status(
            tenant_id="demo-tenant",
            dining_session_id=self.session_a.id,
            order_id=self.order_a.id,
            status="settled",
        )


async def test_serve_is_scoped_and_idempotent(self):
    first = await service.serve_order(
        tenant_id="demo-tenant",
        dining_session_id=self.session_a.id,
        order_id=self.order_a.id,
    )
    second = await service.serve_order(
        tenant_id="demo-tenant",
        dining_session_id=self.session_a.id,
        order_id=self.order_a.id,
    )
    self.assertTrue(first["servedAt"])
    self.assertTrue(second["servedAt"])
```

- [ ] **Step 2: Run the new tests and verify RED**

```powershell
py -3.10 -m pytest tests/test_demo_session_service.py -v
```

Expected: the snapshot and action methods are missing.

- [ ] **Step 3: Implement an allowlisted Demo DTO**

Query `Order` and `OrderItem` with both tenant and session predicates. Build each order from this exact allowlist:

```python
{
    "orderId": str(order.id),
    "displayOrderNo": str(order.id)[-4:],
    "tableNo": order.table_no or "",
    "status": order.status,
    "servedAt": order.served_at.isoformat() if order.served_at else None,
    "createdAt": order.created_at.isoformat() if order.created_at else None,
    "remark": order.remark or "",
    "items": [
        {"name": item.name, "quantity": item.qty, "remark": item.item_remark or ""}
        for item in items
    ],
}
```

Do not reuse serializers that add payment, print or customer fields.

- [ ] **Step 4: Reuse lifecycle services after a scoped precheck**

Before every mutation, load the order using all three predicates:

```python
select(Order).where(
    Order.id == int(order_id),
    Order.tenant_id == tenant_id,
    Order.dining_session_id == int(dining_session_id),
)
```

Reject target statuses outside `{"preparing", "done"}`. Then instantiate `OrderLifecycleService(self.db)`, call `set_tenant_id(tenant_id)`, and invoke `update_order_status(order_id, OrderStatusUpdate(status=status), account_id=None, role="demo")`. Convert a non-200 `RespVo` result into the corresponding Demo service exception; return only the Demo allowlisted DTO on success. For serve, perform the same scoped precheck, set the lifecycle service tenant, and call `serve_order(order_id, account_id=None, role="demo")`. Return 404-equivalent service errors for cross-session or cross-tenant records.

- [ ] **Step 5: Run service and lifecycle regression tests**

```powershell
py -3.10 -m pytest tests/test_demo_session_service.py tests/test_order_state_machine_contracts.py tests/test_tenant_isolation_scan.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- saas-base/app/services/demo_session_service.py saas-base/tests/test_demo_session_service.py
git commit -m "feat(demo): scope demo order fulfillment"
```

## Task 5: Demo API routes and application registration

**Files:**

- Create: `saas-base/app/api/v1/demo.py`
- Modify: `saas-base/app/main.py`
- Create: `saas-base/tests/test_demo_api.py`

- [ ] **Step 1: Write API tests**

Use FastAPI `TestClient` or direct async route calls with a mocked `DemoSessionService`. Cover exact response semantics:

```python
def test_start_returns_respvo_and_camel_case_data():
    response = client.post("/api/v1/demo/sessions/start", json={"launchCode": launch_code})
    assert response.status_code == 200
    assert response.json()["code"] == 200
    assert set(response.json()["data"]) == {
        "demoToken", "expiresAt", "diningSessionId", "tableNo",
        "customerCodeImageUrl", "shopName",
    }


def test_pool_full_returns_429():
    assert response.status_code == 429
    assert response.json()["code"] == 429


def test_demo_snapshot_requires_demo_token():
    assert client.get("/api/v1/demo/session").status_code == 401


def test_cross_session_action_returns_404():
    assert response.status_code == 404
```

- [ ] **Step 2: Run and verify RED**

```powershell
py -3.10 -m pytest tests/test_demo_api.py -v
```

Expected: `/api/v1/demo/*` routes are not registered.

- [ ] **Step 3: Implement four thin routes**

Create `APIRouter(prefix="/api/v1/demo", tags=["体验演示"])` with:

```python
class DemoStartIn(BaseModel):
    launchCode: str


class DemoStatusIn(BaseModel):
    status: str


@router.post("/sessions/start", response_model=RespVo)
async def start_demo_session(body: DemoStartIn, request: Request, db: AsyncSession = Depends(get_db)):
    service = DemoSessionService(db)
    try:
        data = await service.start_session(
            launch_code=body.launchCode,
            client_ip=request.client.host if request.client else "unknown",
        )
        return success_response(data=data, msg="success")
    except DemoInvalidLaunchError:
        return _error_response(403, "体验入口无效或已过期")
    except (DemoRateLimitedError, DemoPoolFullError):
        return _error_response(429, "体验人数较多，请稍后再试")
    except DemoUnavailableError:
        return _error_response(503, "体验服务暂不可用")


@router.get("/session", response_model=RespVo)
async def get_demo_session(request: Request, db: AsyncSession = Depends(get_db)):
    service = DemoSessionService(db)
    data = await service.get_session_snapshot(
        tenant_id=request.state.tenant_id,
        dining_session_id=request.state.demo_session_id,
    )
    return success_response(data=data, msg="success")


@router.patch("/orders/{order_id}/status", response_model=RespVo)
async def update_demo_order_status(order_id: int, body: DemoStatusIn, request: Request, db: AsyncSession = Depends(get_db)):
    service = DemoSessionService(db)
    try:
        data = await service.update_order_status(
            tenant_id=request.state.tenant_id,
            dining_session_id=request.state.demo_session_id,
            order_id=order_id,
            status=body.status,
        )
        return success_response(data=data, msg="success")
    except DemoOrderNotFoundError:
        return _error_response(404, "订单不存在")
    except DemoActionDeniedError:
        return _error_response(409, "当前订单状态不能执行此操作")


@router.post("/orders/{order_id}/serve", response_model=RespVo)
async def serve_demo_order(order_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    service = DemoSessionService(db)
    try:
        data = await service.serve_order(
            tenant_id=request.state.tenant_id,
            dining_session_id=request.state.demo_session_id,
            order_id=order_id,
        )
        return success_response(data=data, msg="success")
    except DemoOrderNotFoundError:
        return _error_response(404, "订单不存在")
    except DemoActionDeniedError:
        return _error_response(409, "当前订单状态不能执行此操作")
```

Define `_error_response(status_code, message)` once in this route module. It must return `JSONResponse(status_code=status_code, content=error_response(code=status_code, msg=message).to_response())`, preserving the repository's `RespVo {code,msg,data}` contract. Each protected route reads `request.state.tenant_id` and `request.state.demo_session_id`. Map service exceptions deliberately: invalid launch 403, pool/rate limit 429, unavailable 503, cross-session 404, illegal transition 409. Use `success_response` and `error_response`; do not hand-build response dictionaries.

- [ ] **Step 4: Register the router**

In `saas-base/app/main.py`, import `demo_router` and call `app.include_router(demo_router)` beside other v1 routers. Do not reorder or duplicate existing routers.

- [ ] **Step 5: Run API, middleware and isolation tests**

```powershell
py -3.10 -m pytest tests/test_demo_api.py tests/test_demo_auth_middleware.py tests/test_demo_session_service.py tests/test_tenant_isolation_scan.py -v
```

Expected: all tests pass and the tenant-isolation scanner accepts or explicitly audits the new tenant-scoped selects.

- [ ] **Step 6: Commit**

```powershell
git add -- saas-base/app/api/v1/demo.py saas-base/app/main.py saas-base/tests/test_demo_api.py
git commit -m "feat(demo): expose demo session API"
```

## Task 6: Block member creation for the Demo tenant

**Files:**

- Modify: `saas-base/app/api/v1/member.py`
- Create: `saas-base/tests/test_demo_member_guard.py`

- [ ] **Step 1: Write the failing guard test**

Test both direct `tenant_id` and entrance-scene resolution:

```python
async def test_demo_tenant_member_login_is_rejected(self):
    response = await login_or_create(request, FakeBody(tenant_id="demo-tenant"), self.db)
    self.assertEqual(response.code, 403)
    self.assertEqual(response.msg, "体验模式无需登录会员")
    self.assertEqual(await self.customer_count(), 0)


async def test_formal_tenant_member_login_is_unchanged(self):
    response = await login_or_create(request, FakeBody(tenant_id="formal-tenant"), self.db)
    self.assertEqual(response.code, 200)
```

- [ ] **Step 2: Run and verify RED**

```powershell
py -3.10 -m pytest tests/test_demo_member_guard.py -v
```

Expected: Demo tenant member creation currently proceeds.

- [ ] **Step 3: Add one narrow backend guard**

After `tenant_id` has been resolved from either body or scene, but before customer resolution, add:

```python
    demo_tenant_id = (settings.DEMO_TENANT_ID or "").strip()
    if demo_tenant_id and tenant_id == demo_tenant_id:
        return error_response(code=403, msg="体验模式无需登录会员")
```

Do not alter any formal tenant branch.

- [ ] **Step 4: Run member regression and commit**

```powershell
py -3.10 -m pytest tests/test_demo_member_guard.py tests/test_member_mock_identity_security.py tests/test_member_client_contracts.py tests/test_p0_b1_member_value_contract.py tests/test_p1_01_member_orders.py -v
```

Commit:

```powershell
git add -- saas-base/app/api/v1/member.py saas-base/tests/test_demo_member_guard.py
git commit -m "fix(demo): keep demo checkout guest only"
```

## Task 7: Admin Demo session state, API client and public route

**Files:**

- Create: `admin-h5/src/demo/session.js`
- Create: `admin-h5/src/api/demoRequest.js`
- Create: `admin-h5/src/api/demo.js`
- Modify: `admin-h5/src/router/index.js`
- Create: `admin-h5/scripts/test-demo-workbench.mjs`
- Modify: `admin-h5/package.json`

- [ ] **Step 1: Write failing pure behavior tests**

Create `test-demo-workbench.mjs` with Node assertions and a fake storage object:

```javascript
import assert from 'node:assert/strict'
import { clearDemoSession, nextDemoAction, readDemoSession, saveDemoSession } from '../src/demo/session.js'

const data = new Map()
const storage = {
  getItem: (key) => data.get(key) || null,
  setItem: (key, value) => data.set(key, value),
  removeItem: (key) => data.delete(key),
}

saveDemoSession(storage, { demoToken: 'demo-token', expiresAt: '2099-01-01T00:00:00Z' })
assert.equal(readDemoSession(storage).demoToken, 'demo-token')
assert.equal(data.has('token'), false)
assert.deepEqual(nextDemoAction({ status: 'pending' }), { status: 'preparing', label: '接单' })
assert.deepEqual(nextDemoAction({ status: 'preparing' }), { status: 'done', label: '制作完成' })
assert.deepEqual(nextDemoAction({ status: 'done', servedAt: null }), { serve: true, label: '确认上菜' })
assert.equal(nextDemoAction({ status: 'done', servedAt: '2026-08-29T00:00:00Z' }), null)
clearDemoSession(storage)
assert.equal(readDemoSession(storage), null)
```

Also read `src/router/index.js` and assert `/demo` exists and the guard has an `isDemo` exemption.

- [ ] **Step 2: Add package command and verify RED**

Add:

```json
"test:demo-workbench": "node scripts/test-demo-workbench.mjs"
```

Run:

```powershell
npm run test:demo-workbench
```

Expected: module imports fail because Demo files do not exist.

- [ ] **Step 3: Implement Demo-only session storage**

Create `src/demo/session.js`:

```javascript
export const DEMO_SESSION_KEY = 'kaixin_demo_session'

export function saveDemoSession(storage, value) {
  storage.setItem(DEMO_SESSION_KEY, JSON.stringify(value))
}

export function readDemoSession(storage) {
  try {
    const value = JSON.parse(storage.getItem(DEMO_SESSION_KEY) || 'null')
    if (!value?.demoToken || !value?.expiresAt) return null
    return value
  } catch {
    return null
  }
}

export function clearDemoSession(storage) {
  storage.removeItem(DEMO_SESSION_KEY)
}

export function nextDemoAction(order) {
  if (order?.status === 'pending') return { status: 'preparing', label: '接单' }
  if (order?.status === 'preparing') return { status: 'done', label: '制作完成' }
  if (order?.status === 'done' && !order?.servedAt) return { serve: true, label: '确认上菜' }
  return null
}
```

- [ ] **Step 4: Implement the isolated Axios client**

Create `demoRequest.js` using `resolveApiBaseURL()`. Request interception reads only `sessionStorage[DEMO_SESSION_KEY]` and sets its `demoToken`. A 401/403 clears only the Demo key and rejects the error; it must not clear `localStorage`, redirect to `/login`, or import the formal `request.js` client.

Create `demo.js`:

```javascript
import demoRequest from './demoRequest'

export const startDemoSession = (launchCode) => demoRequest.post('/v1/demo/sessions/start', { launchCode })
export const getDemoSession = () => demoRequest.get('/v1/demo/session')
export const updateDemoOrderStatus = (orderId, status) => demoRequest.patch(`/v1/demo/orders/${orderId}/status`, { status })
export const serveDemoOrder = (orderId) => demoRequest.post(`/v1/demo/orders/${orderId}/serve`)
```

- [ ] **Step 5: Add the public route without formal auth hydration**

Lazy import `DemoWorkbench.vue` and add `{ path: '/demo', name: 'DemoWorkbench', component: DemoWorkbench }`. In the guard define `const isDemo = to.path === '/demo'` and include it in the existing public-route early return. Do not call `auth.ensureSession()` for `/demo`.

- [ ] **Step 6: Run tests and commit**

```powershell
npm run test:demo-workbench
```

Expected: pure storage/action and route isolation tests pass.

Commit:

```powershell
git add -- admin-h5/src/demo/session.js admin-h5/src/api/demoRequest.js admin-h5/src/api/demo.js admin-h5/src/router/index.js admin-h5/scripts/test-demo-workbench.mjs admin-h5/package.json
git commit -m "feat(admin): add isolated demo session client"
```

## Task 8: Mobile-first owner Demo workbench

**Files:**

- Create: `admin-h5/src/views/DemoWorkbench.vue`
- Modify: `admin-h5/scripts/test-demo-workbench.mjs`

- [ ] **Step 1: Extend the failing UI contract**

Read the SFC source and assert these user-visible states and controls exist:

```javascript
assert.match(source, /正在准备本次体验/)
assert.match(source, /请用另一台手机扫描/)
assert.match(source, /订单可能不是最新/)
assert.match(source, /重新开始30分钟体验/)
assert.match(source, /customerCodeImageUrl/)
assert.match(source, /nextDemoAction/)
assert.doesNotMatch(source, /退款|真实打印|会员导出/)
```

Run `npm run test:demo-workbench`; expected failure because the SFC does not exist.

- [ ] **Step 2: Implement explicit page states**

Create `DemoWorkbench.vue` with these refs:

```javascript
const phase = ref('loading')
const session = ref(null)
const orders = ref([])
const syncFailed = ref(false)
const actionOrderId = ref('')
const remainingSeconds = ref(0)
```

On mount:

1. Read `launchCode` from `route.query`.
2. Resume an unexpired `sessionStorage` Demo session when present.
3. Otherwise call `startDemoSession(launchCode)` and save the response.
4. Start a 2-second order poll only after a session exists.
5. Start a 1-second countdown.
6. Clear both timers in `onBeforeUnmount`.

Use a single `performOrderAction(order)` that calls either status update or serve based on `nextDemoAction(order)`, awaits backend success, then refreshes the snapshot. Never mutate an order to the target status before the API confirms success.

- [ ] **Step 3: Implement the page layout**

Use Ant Design Vue `a-alert`, `a-button`, `a-card`, `a-empty`, `a-spin` and `a-tag`. The visual order must be:

```text
Header and countdown
Customer mini-program code and three-step instruction
New/current Demo orders
Persistent sync or expiry feedback
```

The empty state text is exactly “请用另一台手机扫描上方顾客点餐码，提交后订单会自动出现在这里”。 Failed polling retains prior orders and shows “订单可能不是最新，请检查网络后重试”。 Each order shows only the one action returned by `nextDemoAction`.

Use scoped styles with a white card surface, brand green primary action, 44px minimum touch targets, 12-16px radii, and a one-column mobile layout. Do not introduce Vant, new dependencies, a PC table, gradients or animations.

- [ ] **Step 4: Verify UI contracts, SFC compilation and build**

```powershell
npm run test:demo-workbench
npm run check:text
npm run build
```

Expected: Demo tests pass, UTF-8 check passes, Vite production build succeeds.

- [ ] **Step 5: Browser-check the page**

Run the existing Admin dev server and open `/demo?launchCode=invalid` at 390x844. Verify the failure state is readable and does not redirect to `/login`. With backend fixtures or a mocked valid response, verify QR, empty state, order card, one-action rule and expiry view without horizontal scroll.

- [ ] **Step 6: Commit**

```powershell
git add -- admin-h5/src/views/DemoWorkbench.vue admin-h5/scripts/test-demo-workbench.mjs
git commit -m "feat(admin): add owner demo workbench"
```

## Task 9: Guest-only Demo checkout in the mini program

**Files:**

- Modify: `member-mini-client/src/pages/entry/index.vue`
- Modify: `member-mini-client/src/subpkg-order/composables/useCheckout.js`
- Create: `member-mini-client/src/subpkg-order/composables/__tests__/useCheckout.demo-mode.test.js`
- Create: `member-mini-client/src/pages/entry/__tests__/entry-demo-mode.test.js`

- [ ] **Step 1: Write failing entry behavior tests**

The entry test should mount or isolate `saveContext` and prove that `channel=DEMO` clears customer auth before persistence while `channel=TABLE` does not add a new clear:

```javascript
it('clears prior customer identity for DEMO entrance', () => {
  saveContext({ tenant_id: 'demo-tenant', table: 'DEMO-01', channel: 'DEMO' })
  expect(clearCustomerSession).toHaveBeenCalledTimes(1)
  expect(uni.setStorageSync).toHaveBeenCalledWith('channel', 'DEMO')
})
```

- [ ] **Step 2: Write failing checkout behavior tests**

Extend the existing `useCheckout` test fixture. Store `channel=DEMO`, call the public checkout handler, and assert it calls the existing order submit path without showing member choice or invoking `wxLogin`:

```javascript
it('DEMO channel submits as guest without member choice', async () => {
  uni.getStorageSync.mockImplementation((key) => key === 'channel' ? 'DEMO' : '')
  await checkout.checkout()
  expect(state.showMemberCheckoutChoice.value).toBe(false)
  expect(wxLogin).not.toHaveBeenCalled()
  expect(createOrder).toHaveBeenCalledTimes(1)
})
```

Retain a second test proving the formal `TABLE` guest still sees the current member-choice behavior.

- [ ] **Step 3: Run and verify RED**

```powershell
npx vitest run src/pages/entry/__tests__/entry-demo-mode.test.js src/subpkg-order/composables/__tests__/useCheckout.demo-mode.test.js
```

Expected: Demo channel currently follows normal member-choice behavior.

- [ ] **Step 4: Add the narrow entry guard**

In `saveContext` after any cross-tenant cleanup, add:

```javascript
if (ctx.channel === 'DEMO') {
  clearCustomerSession()
}
```

Do not alter other channels.

- [ ] **Step 5: Add the narrow checkout branch**

Inside `useCheckout`, add:

```javascript
const isDemoMode = () => String(uni.getStorageSync('channel') || '').toUpperCase() === 'DEMO'
```

In the existing checkout handler, after standard eligibility checks and before the member-choice branch:

```javascript
if (isDemoMode()) {
  clearCustomerSession()
  refreshCustomerAuthState()
  return submitOrder()
}
```

Do not change `performSubmitOrder`, payment recovery, pending intent, table identity or formal member conversion.

- [ ] **Step 6: Run focused and full Mini gates**

```powershell
npx vitest run src/pages/entry/__tests__/entry-demo-mode.test.js src/subpkg-order/composables/__tests__/useCheckout.demo-mode.test.js src/subpkg-order/composables/__tests__/useCheckout.p0-a-member-checkout-choice.test.js
npm run check:ui-contracts
npm run build:mp-weixin
```

Expected: focused Demo and formal checkout tests pass, UI contracts pass, WeChat build succeeds.

- [ ] **Step 7: Commit**

```powershell
git add -- member-mini-client/src/pages/entry/index.vue member-mini-client/src/subpkg-order/composables/useCheckout.js member-mini-client/src/pages/entry/__tests__/entry-demo-mode.test.js member-mini-client/src/subpkg-order/composables/__tests__/useCheckout.demo-mode.test.js
git commit -m "feat(mini): keep demo orders guest only"
```

## Task 10: Update the A/B experience card for the linked flow

**Files:**

- Modify: `docs/frontend/owner-experience-card-ab-demo.html`
- Modify: `docs/frontend/owner-experience-card-ab-demo.test.cjs`

- [ ] **Step 1: Change the test first**

Add assertions for the new primary flow:

```javascript
assert.match(html, /老板扫码进入Demo工作台/)
assert.match(html, /进入后生成本次专属顾客点餐码/)
assert.match(html, /顾客下单.*商家接单.*制作完成.*确认上菜/s)
assert.match(html, /当前二维码不可扫码，请勿直接印刷/)
```

Run:

```powershell
node --test docs/frontend/owner-experience-card-ab-demo.test.cjs
```

Expected: new flow-copy assertions fail.

- [ ] **Step 2: Update only the card copy and QR hierarchy**

Keep the existing A6 geometry, print CSS, A/B switch and front/back switch. Change the main QR label to “老板扫码进入Demo工作台”. Replace the fixed customer QR promise with “进入后生成本次专属顾客点餐码”. On the back, show the four-step closed loop in order:

```text
顾客下单 → 商家接单 → 制作完成 → 确认上菜
```

Keep the explicit non-scannable warning until the deployed `/demo` URL with its signed launch-code query value is available.

- [ ] **Step 3: Verify layout and tests**

```powershell
node --test docs/frontend/owner-experience-card-ab-demo.test.cjs
```

Expected: all tests pass. Then open the HTML at desktop width and 390px mobile width; verify front/back have no internal overflow and print remains A6 portrait.

- [ ] **Step 4: Commit**

```powershell
git add -- docs/frontend/owner-experience-card-ab-demo.html docs/frontend/owner-experience-card-ab-demo.test.cjs
git commit -m "docs(sales): link owner demo experience flow"
```

## Task 11: Integrated verification and release handoff

**Files:**

- Modify only if required by verified failures from Tasks 1-10.
- Read before completion: `AI_COMPLETION_PROTOCOL.md`, `AI_MEMORY_UPDATE_PROTOCOL.md`.

- [ ] **Step 1: Run complete Backend regression**

```powershell
cd C:\Users\15936\Desktop\xiao-linked-demo-experience\saas-base
py -3.10 -m pytest tests/ -v
py -3.10 -m alembic heads
```

Expected: the full test suite exits 0 and Alembic reports exactly one head. Do not claim a pass if the command times out without a final summary.

- [ ] **Step 2: Run complete Admin gate**

```powershell
cd C:\Users\15936\Desktop\xiao-linked-demo-experience\admin-h5
npm run check
```

Expected: all Admin checks and the production build exit 0.

- [ ] **Step 3: Run complete Mini gate**

```powershell
cd C:\Users\15936\Desktop\xiao-linked-demo-experience\member-mini-client
npm run lint
npm run test
npm run build:h5
npm run build:mp-weixin
```

Expected: lint, unit/legacy/UI contracts and both builds exit 0.

- [ ] **Step 4: Run the sales material test**

```powershell
cd C:\Users\15936\Desktop\xiao-linked-demo-experience
node --test docs/frontend/owner-experience-card-ab-demo.test.cjs
```

Expected: all card tests pass.

- [ ] **Step 5: Provision a non-production Demo tenant**

Set environment values outside source control:

Set `DEMO_TENANT_ID` to the exact `tenant_id` displayed for the dedicated non-production tenant in SuperAdmin; stop if that value cannot be verified. Set `DEMO_SESSION_MINUTES=30`, `DEMO_LAUNCH_DAYS=365`, and `DEMO_TABLE_POOL_SIZE=20`. Keep all four environment values outside source control.

Use the existing SuperAdmin test-data action to seed the empty dedicated tenant. In Admin, configure `postpay`, leave printer provider/SN empty, and create 20 active table codes `DEMO-01` through `DEMO-20` with `channel=DEMO`. Generate the launch code only after these checks pass:

```powershell
cd C:\Users\15936\Desktop\xiao-linked-demo-experience\saas-base
py -3.10 scripts/generate_demo_launch_code.py
```

Do not paste the generated code into git, logs or documentation.

- [ ] **Step 6: Execute two-device acceptance**

Using the non-production environment:

1. Capture the generated value as `$launchCode` in the deployment secret manager, set `$demoUrl = "$adminBaseUrl/demo?launchCode=$launchCode"`, and open `$demoUrl` on the owner phone without writing either value into source control or documentation.
2. Scan the returned mini-program code on a second phone.
3. Submit a guest postpay order.
4. Verify it appears within 2 seconds.
5. Execute 接单, 制作完成, 确认上菜.
6. Verify the customer side reflects each state.
7. Start another Demo session and verify it cannot see the first session order.
8. Use an expired token and verify all protected Demo APIs reject it.
9. Confirm no real payment, printer call, member, coupon, point or commission record was created.

- [ ] **Step 7: Replace the sales-card QR only after acceptance**

Encode the deployed Admin URL containing the generated launch code into the card's main QR, rerun the HTML test, print one A6 proof, scan it with a real phone, and only then authorize the 500-copy print run.

- [ ] **Step 8: Final scoped commit if verification required fixes**

If verification required code fixes, stage only the verified task files and commit with a message describing the actual fix. If no fixes were required, do not create an empty commit.

- [ ] **Step 9: Update project memory according to protocol**

Record only stable final facts: Demo architecture, exact tests, deployment prerequisites, and whether the two-device gate passed. Do not write secrets, launch codes or customer data to Obsidian.
