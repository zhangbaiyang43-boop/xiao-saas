# SaaS Subscription Architecture Audit

**Type:** Read-only Phase 01 audit. No code, schema, config, or test files were modified to produce this report.
**Scope:** `saas-base` (FastAPI + MySQL), `admin-h5` (Vue3 + Vite merchant/super-admin console), `member-mini-client` (uni-app customer mini-program), `channel-h5` (channel-partner portal, discovered during audit).
**Date:** 2026-08-11

---

## 1. Executive Summary

The platform is production-grade for restaurant transactions (menu, dining orders, WeChat Pay, printing, membership, coupons, three payment modes) and already contains **real, working scaffolding** for SaaS commercialization that the product owner may not be fully aware of:

- A billing subsystem (`BillingInvoice` / `BillingPayment`) already exists, with a `charge_type` enum that **already includes `"SAAS_SUBSCRIPTION"`**. It is currently used only for manual, one-off channel-partner-commission invoicing, and its real WeChat Pay path is deliberately disabled (`PlatformWxPayBillingProvider.enabled == False`) — only a fake/test payment provider is live.
- A gated self-registration endpoint (`POST /api/v1/register`) already does "create tenant → issue JWT → auto-login," end to end. It's gated behind a static shared-secret key, not open to the public, but the registration→login mechanics are proven.
- A mature, production Tencent Cloud SMS OTP service already exists and is used for merchant-owner and channel-partner login (never for restaurant customers). It is realistically reusable for a future registration-verification flow with modest, additive changes.
- **No plan/package/trial/expiry concept exists anywhere on `Tenant`.** The only tenant-level state today is a single boolean `status` (a manual admin ban/unban switch), which must **not** be reused to represent "subscription expired" — see §15.
- Tenant creation (`Tenant` + `TenantConfig`) is atomic as a pair, but nothing else in onboarding is transactionally linked to it — see §4.
- The dining WeChat payment pipeline is verified `WX_CALLBACK_ONLY` (only WeChat's own confirmation — via webhook or active reconciliation query — ever marks an order paid), idempotent, and tightly coupled to the `orders` table by design. It must not be reused for subscription payments — the codebase's own `BillingInvoice`/`BillingPayment` model is the correct home for that, and is already isolated from dining code.

**No blocking architectural defect was found.** The main risks are process risks (partial-failure onboarding, conflating Tenant.status with billing state, an app-level-only phone-uniqueness check) rather than fundamental design flaws. See §28 for the Go/No-Go call.

---

## 2. Repository Status

```
Branch: main
HEAD:   bf8d844 fix: repair guest-order lookup, queue-take navigation, and order-bubble hint position
Alembic head (repo):        20260809_0006 (single head, no branching)
Alembic current (local DB): 20260803_0003 — six migrations behind repo head on this machine's local dev DB
```

Working tree has a large number of pre-existing uncommitted changes unrelated to this audit (spanning `member-mini-client`, `saas-base/app/core/cos.py`, `saas-base/app/main.py`, `saas-base/app/services/order_print_service.py`, several `saas-base/tests/*` files, plus untracked scratch files and a `saas-base.backup.20260801/` directory). **None of this was touched, staged, reverted, or otherwise acted upon during this audit** — it is reported here only as an observed fact per the audit's git-safety instructions. The local dev DB's alembic version lagging the repo head is a local-environment note only; it says nothing about production (per this repo's own deployment notes, production is migrated separately via `alembic upgrade head` on the server).

No destructive git commands were run. Alembic was only queried (`heads`, `current`, `history`) — never `upgrade`/`downgrade`.

---

## 3. Current Tenant Model

`saas-base/app/models/tenant.py:8-38`, table `tenant`. Uses the shared `Base` from `app/models/base.py:6` (imported at `tenant.py:6`) — **not** a separate SQLAlchemy declarative registry (an unused `from sqlalchemy.ext.declarative import declarative_base` import sits at `tenant.py:2` but is never called; there is only one `Base`/one metadata object across the whole `app/models/` tree).

| Field | File:Line | Type | Current use | Conflicts with future Subscription? |
|---|---|---|---|---|
| `id` | tenant.py:11 | BigInteger PK (snowflake) | Internal PK | No |
| `tenant_id` | tenant.py:12 | String(32), unique | Public sharding key, used everywhere as the tenant-scoping value | No |
| `name` | tenant.py:13 | String(64) | Shop name | No |
| `password_hash` | tenant.py:14 | String(128), NOT NULL | **Vestigial.** Always written as `""`; the one API that could change it is hard-disabled, returns "已改为手机号验证码登录，暂不支持修改密码". | Naming-collision risk only — a future "account password" concept should not reuse this dead field. |
| `corp_id` | tenant.py:15 | String(64) | WeWork corp id | No |
| `phone` | tenant.py:16 | String(20), nullable, **no unique constraint** | Owner SMS-login lookup key | No, but see §5 (race condition) |
| `address`, `logo_url` | tenant.py:17-18 | String | Store profile | No |
| `status` | tenant.py:19 | Boolean, default True | **The only tenant-level on/off flag that exists today** — a manual super-admin ban switch | **Yes — must not be reused as "subscription active/expired."** See §15. |
| `is_open` | tenant.py:20 | Boolean, default True | Comment says "营业开关" (business-open toggle) but **dead code** — the real open/closed flag actually read by order/menu code is `TenantConfig.business_info["is_open"]` (JSON), not this column. | Low — just don't confuse the two when reading old code. |
| `payment_mode` | tenant.py:21 | String(32), default "prepay" | Dining order-flow setting: prepay / postpay / table_account | No |
| `wx_pay_enabled` + 7 `wx_*` columns | tenant.py:22-29 | Boolean/String | Tenant's **own** WeChat Pay sub-merchant credentials (for collecting money from diners), encrypted at rest | No — semantically about the merchant's own payment collection, not what they owe the platform |
| `receiver_name`, `receiver_type`, `receiver_verified`, `payment_locked`, `verified_time` | tenant.py:30-34 | various | KYC-style verification state on that same WeChat Pay sub-merchant, set by super-admin | No |
| `feieyun_sn`, `feieyun_key` | tenant.py:35-36 | String(64) | 飞鹅云 printer credentials | No |
| `created_at`, `updated_at` | tenant.py:37-38 | DateTime | Standard timestamps; `created_at` is already used elsewhere for created_at-based cohorting (see §16) | No |

**Confirmed absent** (checked against the model, the original migration DDL, and the runtime schema-patcher `app/core/schema_compat.py:96-129`): `enabled`, `is_active`, `expired_at`, `expire_at`, `trial`, `vip`, `is_paid`, `plan`, `package`, `edition`, `subscription`.

**Runtime schema-drift note:** `app/core/schema_compat.py:ensure_tenant_schema()` ALTER TABLEs new WX-pay/printer columns onto `tenant` at process startup if missing (gated by `settings.AUTO_CREATE_TABLES`, called from `app/main.py:397-403`). The live DB schema for `tenant` is therefore not fully captured by Alembic migrations alone — any future Subscription-related column additions to `Tenant` (if that design is chosen) should go through Alembic, and should be aware this out-of-band patcher exists so the two mechanisms don't diverge.

A separate 1:1 model, `TenantConfig` (`app/models/tenant_config.py:6-12`, table `tenant_config`), holds the real settings surface as four JSON blobs: `member_rules`, `coupon_rules`, `business_info`, `plugin_settings`.

---

## 4. Tenant Provisioning Flow

Three entry points, all converging on one service method:

```
A) Super Admin creates a merchant
POST /api/super/merchants                              (app/api/v1/super_admin.py:253)
  ↓ create_merchant()
  → TenantService.get_tenant_by_phone()  [uniqueness check, app-level only]
  → generate_tenant_id()                 (app/utils/id_generator.py)
  → TenantService.create_tenant()        (app/services/tenant_service.py:179-210)
  → _audit(...)                          [IP-only audit log]

B) Gated public self-registration (already exists, key-gated)
POST /api/v1/register                                  (app/api/v1/login.py:79-102)
  ↓ register()
  → check data.platform_key == settings.PLATFORM_REGISTER_KEY   [403 if not: "注册暂未开放，请联系平台开通"]
  → TenantService.get_tenant_by_phone()
  → generate_tenant_id()
  → TenantService.create_tenant()
  → create_access_token(tenant_id, role=owner)   [auto-login, returns session immediately]

C) Legacy duplicate — DEAD CODE, not reachable
POST /api/auth/register                                 (app/api/auth.py:38-57)
  — app.api.auth is never imported/include_router'd in app/main.py. Confirmed unreachable.
  — Sibling /api/auth/login (auth.py:22) has a hardcoded SMS bypass code "123456" — dead, but flag for cleanup.

Core creation logic — TenantService.create_tenant()      (app/services/tenant_service.py:179-210)
  tenant = Tenant(tenant_id, name, password_hash="", phone, address, logo_url, status=True)
  config = TenantConfig(tenant_id, member_rules=DEFAULT_*, coupon_rules=DEFAULT_*,
                         business_info=DEFAULT_*, plugin_settings=DEFAULT_*)
  db.add(tenant); db.add(config)
  await db.commit()                       ← single commit, see §5
```

**What gets auto-created:** `Tenant` + `TenantConfig` (with default JSON settings) only.

**What does NOT get auto-created:**
- **Store** — there is no separate Store model at all (`grep "class Store"` → no matches). Tenant *is* the store; this is a single-store-per-tenant architecture.
- **Merchant Admin/User account** — none. The owner authenticates directly as the `Tenant` row via SMS (§6); no separate admin-user row is needed or created.
- **Role / Permission** — hardcoded in `app/core/permissions.py`, not DB rows.
- **Printer settings** — left null; configured later, manually.
- **Menu/dish data** — none. (An explicit, opt-in `POST /api/super/merchants/{tenant_id}/seed-test-data` endpoint can synthesize demo data, but it is gated to only run when the tenant has zero real orders, and is not part of normal provisioning.)
- **Payment settings** — WeChat Pay fields left default (`wx_pay_enabled=False`, `payment_locked=True`); configured later by super-admin via `PATCH /api/super/merchants/{tenant_id}/wxpay`.
- **Membership/Marketing settings** — seeded, but only as JSON defaults *inside* `TenantConfig`, not as separate rows.
- **Plugins (`TenantPlugin` rows)** — none created at provisioning. Note: `TenantConfig.plugin_settings` sets JSON "default_enabled" flags for coupon/points/crm/bargain/distribution, but this is a separate, older mechanism from the real `TenantPlugin` table-driven install/enable lifecycle (`app/plugins/plugin_manager.py`) — a fresh tenant's actual enabled-plugin set is empty regardless of what the JSON says, until something explicitly installs a plugin. This is a latent inconsistency, not something this audit should fix, but worth being aware of if a future "plan includes these plugins" design is built on top of either mechanism.
- **Entrance/QR codes** — none.

---

## 5. Merchant Identity Model

There is **no separate admin-user model for the tenant owner** — the `Tenant` row itself is the owner's login identity (explicit code comments confirm this: `app/models/merchant_account.py:9`, `app/core/merchant_auth.py:52`).

Non-owner staff use a distinct model, `MerchantAccount` (`app/models/merchant_account.py:6-23`, table `merchant_accounts`): `tenant_id` (bare string, no FK), `username`, `password_hash` (bcrypt), `role` (`frontdesk|waiter|kitchen`), `status`. Unique constraint is `(tenant_id, username)` — usernames are only unique *within* a tenant. Created via `POST /api/v1/merchant-accounts`, gated behind an owner-only permission.

There's also a `Staff` model (`app/models/staff.py`) that is explicitly unrelated to login — a lightweight "referral code" identity for tracking which staff member brought in a customer.

**Key answers:**
- **Multiple Tenants per phone?** Nothing prevents it at the DB level — `Tenant.phone` has no unique constraint. Uniqueness is enforced only in application code (`TenantService.get_tenant_by_phone`, checked before insert), which is a check-then-act race: two concurrent registrations with the same phone could both pass the check. If that ever produced two `Tenant` rows sharing a phone, `get_tenant_by_phone()`'s `scalar_one_or_none()` would raise `MultipleResultsFound` on the next lookup — an unhandled exception path.
- **Multiple admins per Tenant?** Yes for staff (`MerchantAccount`, unlimited), but there is only ever one owner (the `Tenant` row itself) — no co-owner concept.
- **Password hashing:** Standard `passlib`/bcrypt (`app/core/security.py:10-99`).
- **SMS verification:** Yes, already in production use for owner login (`TencentSmsService`, see §7).
- **Phone unique DB constraint:** No — app-level only.
- **How is `tenant_id` determined per request:** Not a per-request DB lookup — it's carried directly as a claim inside the signed JWT, read into `request.state.tenant_id` and mirrored into a `contextvars.ContextVar`.
- **Does the JWT include `tenant_id`:** Yes — `create_access_token()` (`app/core/security.py:13-30`) puts `tenant_id`, `type: "merchant"`, `role`, and (for staff) `account_id` directly in the payload. Owner tokens live 7 days.

---

## 6. Authentication Flow

```
Owner login:
POST /api/v1/login/code   (login.py:45-59)  → lookup Tenant by phone, check tenant.status, send SMS (TencentSmsService)
POST /api/v1/login        (login.py:62-76)  → re-check status, verify code, create_access_token(), return session

Every subsequent request passes through TWO middlewares (registration order in app/main.py
means actual execution order is CORS → Logging → TenantMiddleware → AuthMiddleware → route):

  TenantMiddleware.dispatch()   (app/middleware/tenant_middleware.py:27-51)
    → decodes JWT, sets TenantContext contextvar + request.state.tenant_id
  AuthMiddleware.dispatch()     (app/middleware/auth_middleware.py:88-185)
    → decodes JWT AGAIN (independently), does real enforcement:
      whitelist check, tenant.status active check (45s cache, _is_tenant_active),
      staff role resolution + route allowlisting, member/merchant/channel path checks
```

`get_current_tenant()` (`app/api/v1/tenant.py:81-89`) and `get_current_user()` (`app/core/security.py:79-89`) read `tenant_id` off request state.

**Could "register → auto-login → own dashboard" be built on this as-is?** Largely yes — `POST /api/v1/register` already does exactly this mechanically. Real obstacles, precisely:
1. Phone uniqueness is app-level-only and race-prone (§5) — fine at today's low registration volume (super-admin or key-holders only), riskier under real public signup traffic.
2. No trial/expiry/plan concept exists (§3) — a self-serve paid product needs *something* to gate access post-signup, and nothing does that today.
3. No automated billing linkage at signup — `BillingInvoice`/`BillingPayment` exist but are wired to channel-partner commission flows, not tenant-pays-platform subscription charges.
4. Two middlewares independently parse the JWT with **not-quite-identical** whitelist/optional-auth path lists — any new self-registration-adjacent route must be added correctly to both or it will behave inconsistently between them.
5. `PLATFORM_REGISTER_KEY` is a single shared static secret, not per-invite/per-partner — turning this into true open signup needs redesigning this gate, not just flipping a flag.
6. Single-store-per-tenant is baked deeply into the data model — "one owner, multiple locations" would be a real architectural change, not a config toggle. (Not required for Phase 02, noted for completeness.)

---

## 7. SMS Capability

A mature, production Tencent Cloud SMS OTP service already exists: `app/services/tencent_sms_service.py`, class `TencentSmsService`.

- **Provider:** Tencent Cloud SMS, called directly over `httpx` (hand-rolled TC3-HMAC-SHA256 signing — no official `tencentcloud-sdk-python` package is a dependency).
- **Code generation:** `secrets.randbelow(1_000_000)` (CSPRNG), zero-padded to 6 digits.
- **Storage:** Never plaintext — HMAC-SHA256 hash keyed by `JWT_SECRET_KEY`, verified with constant-time compare.
- **Redis:** Real Redis via `app/core/redis_client.py`, with an in-process dict fallback if Redis is unreachable. Key pattern: `sms:merchant-login:{code|cooldown|daily}:{phone}`. TTLs are configurable (`SMS_CODE_TTL_SECONDS` default 300s, resend cooldown 60s, daily cap 10, max verify attempts 5).
- **Anti-abuse:** resend cooldown, daily send cap, verify-attempt cap with auto-lockout, all already implemented.
- **Currently used for:** merchant-owner login and channel-partner login (`app/services/channel_auth_code_service.py`, a near-identical clone under its own Redis key namespace). **Never** used for restaurant customers — customer identity runs entirely on WeChat mini-program OAuth (openid), not phone+SMS.

**Reuse assessment for future merchant registration** (assessment only — not implemented, not recommended for Phase 02): structurally close to reuse-ready. `TencentSmsService` is already namespace-isolated by Redis key prefix, and `ChannelAuthCodeService` is a working precedent for "clone the pattern under a new namespace for a new identity type." Would need: a new Redis key namespace (e.g. `sms:merchant-register:*`) to avoid colliding with existing login codes for the same phone, a distinct Tencent SMS template ID (only a login template exists today), and replacing/extending the `PLATFORM_REGISTER_KEY` gate with the OTP result. No gap in the anti-abuse/storage layer itself.

---

## 8. Existing Commercial Logic

**The single most important finding of this audit:** a real billing subsystem already exists, built 2026-08-09, but it is invoice-based (manual, one-off) and gates nothing.

- `app/models/billing.py` — `BillingInvoice`, `BillingPayment`
- `app/services/billing_service.py` — `BillingService`; `CHARGE_TYPES` (line 35) = `{"SAAS_SUBSCRIPTION", "SETUP_SERVICE", "MINIPROGRAM_CERTIFICATION", "HARDWARE", "SMS_TOPUP", "ADDON", "OTHER"}` — **verified directly, `"SAAS_SUBSCRIPTION"` is a real, already-defined charge type.**
- `app/services/billing_payment_provider.py` — `FakeBillingPaymentProvider` (live) and `PlatformWxPayBillingProvider` (real WeChat Pay, **deliberately disabled**: `.enabled` returns `False`, `create_payment` raises `RuntimeError(REAL_PAYMENT_BLOCKED_REASON)` — the code comment notes the relevant `WX_SP_*` config is "not confirmed platform SaaS receivables config").
- `app/api/v1/billing.py` (merchant-facing) / `app/api/v1/super_billing.py` (super-admin manually creates invoices)
- `tests/test_saas_billing_foundation.py` — includes a test literally named `test_consumer_order_payment_system_remains_unchanged`, confirming this was built as a deliberately isolated addition.

**Why it exists:** to support channel-partner commission tracking, not tenant self-billing. `app/services/channel_commission_policy.py:6` — `ELIGIBLE_CHARGE_TYPES = {"SAAS_SUBSCRIPTION", "ADDON"}` — and every successful billing payment triggers `ChannelCommissionService.handle_billing_payment_success()`. The channel-partner portal (`channel-h5`) shows partner-facing copy "软件服务费 20%" — this billing foundation's real purpose today is "let a channel partner earn commission when a merchant's SaaS invoice gets paid," not "gate merchant access on payment."

**Answers to the standard commercial-logic questions:**
1. Plan/package for tenants? **No.**
2. Tenant-level expiration/trial timestamp? **No** (only `BillingInvoice.expired_at`, per-invoice, not per-tenant).
3. Merchant VIP/paid-tier concept? **No** — all VIP/会员 code found is the *customer* membership system (LV1/LV2/LV3), unrelated to tenants.
4. Tenant paid/unpaid boolean/gate? **No**, but `Tenant.status` (the manual ban switch, §3/§15) is the closest existing mechanism and must not be silently repurposed for this.
5. Has admin-h5 ever gated a feature behind "paid"? **No** — the entire billing backend has zero frontend consumption in `admin-h5` today.
6. Has saas-base ever gated an API behind a paid/plan check? **No** — no middleware or route references billing/invoice state as an access gate.
7. Does a SaaS/recharge order distinct from dining orders exist? **Yes** — `BillingInvoice`/`BillingPayment`, already architecturally separate from `Order`.
8. Abandoned/vestigial billing logic? None in the merchant-billing area (it's new and internally consistent). One self-documented dead path exists in the unrelated *customer* points-redemption code (`membership_service.py:27-37`, an old "freely redeem points" design that no endpoint ever executed).

**Consumer wallet vs. merchant billing — explicitly not the same thing, and not currently confusable:** `MemberAccount.balance` is a real restaurant-customer stored-value wallet (`GET/POST /api/v1/member/balance`, `/recharge`), spendable against dining orders — but its recharge endpoint is hard-gated behind `settings.ALLOW_MOCK_MONEY_ENDPOINTS` (default `False`) with an explicit docstring: "当前为模拟支付，仅限测试环境。生产环境需替换为真实微信支付回调." There is **no equivalent wallet/recharge concept for tenants/merchants** anywhere in the codebase — the only merchant-side money-movement concept is the one-off `BillingInvoice`/`BillingPayment` pair above.

---

## 9. Existing Feature Flags

Four independent, **not fully reconciled** "is this feature on for this tenant" mechanisms exist today:

| Feature | Field | Model | Checked at | Fit for future Plan mapping? |
|---|---|---|---|---|
| Business open/closed | `is_open` (JSON key) | `TenantConfig.business_info` | `orders.py:244`, `menu.py:163` | This is the *real* one — `Tenant.is_open` column is dead, don't confuse them |
| Physical pickup-number plates | `pickup_no_enabled` | `TenantConfig.business_info` | `menu.py:180`, `pickup_no_service.py:42` | Yes — a natural per-plan feature toggle candidate |
| Dine-in / pickup ordering | `dine_in_enabled`, `pickup_enabled` | `TenantConfig.business_info` (Python-level default fallback, not seeded into fresh JSON) | `menu.py:165-166` | Yes, but note the seeding gap |
| Queue/printer config | `queue_query_enabled`, `printer_provider`, etc. | `TenantConfig.business_info` | `tenant.py` printer endpoints | Possibly |
| Plugin default-enable intent | `plugin_settings.<code>.default_enabled` | `TenantConfig.plugin_settings` | Not actually read to auto-create `TenantPlugin` rows — **logically disconnected** from real plugin state | Needs reconciliation before being trusted as an entitlement source |
| Actual plugin install/enable state | `TenantPlugin` rows | `app/plugins/plugin_manager.py` | `get_tenant_plugins_from_db` | The real source of truth for "is plugin X on," disagrees with the JSON above |
| Own WeChat Pay active | `wx_pay_enabled` | `Tenant` column | Multiple payment/order services | Not really plan-shaped — this is a merchant capability, not a platform-granted entitlement |
| Coupon-rule toggles | `coupon_rules[*].enabled` | `TenantConfig.coupon_rules` | `coupon_service.py` | Marketing-rule-level, separate system again |

**Explicitly not converted to plan-based gating in this phase** (per instructions) — this table is a mapping only. The fragmentation itself (four+ independent flag surfaces) is worth carrying into future entitlement design so a fifth, disagreeing mechanism isn't added on top.

---

## 10. Current Payment Architecture

```
Dining payment, verified end-to-end:

POST /api/v1/orders                     (orders.py:809)  → Order row, status="pending"/"pending_payment"
    │  payment state lives directly ON the orders row (payment_status, payment_method,
    │  payment_time, refund_* columns) — there is NO separate Payment/PaymentTransaction model
    ↓
POST /api/v1/orders/{id}/wxpay          (orders.py:917 → order_payment_service.py:509)
    → WxPayService(tenant).create_jsapi_order(out_trade_no=str(order.id), ...)
    ↓
POST /api/v1/orders/wxpay-notify        (orders.py:927 → order_payment_service.py:650, wxpay_notify)
    → verify signature (per-tenant credentials)
    → Order.id == int(out_trade_no)  [SELECT ... FOR UPDATE]
    → idempotency guard: only runs if order.status == "pending_payment"; already-advanced
      orders short-circuit and return SUCCESS without reprocessing
    ↓ _on_payment_success()             (order_payment_service.py:90-237)
    → payment_status="paid", payment_method="wxpay", payment_time=now
    → coupon write-off + referral commission
    → coupon auto-issuance, membership points (apply_consumption)
    → kitchen/receipt print triggered (order_print_service.py)
    → payment-handoff marked (payment_handoff_service.py)
```

For **postpay/table_account** (offline/counter payment, a legitimate non-WeChat business mode): `order_lifecycle_service.py:_mark_order_offline_paid()` (staff-authenticated only) → `_apply_paid_order_member_assets_once` for the same points/coupon side effects, no WeChat involvement.

**out_trade_no format:** literally `str(order.id)` — the dining order's own primary key, no namespace/prefix. Verified directly at `order_payment_service.py:349,420,609`.

**Callback → Order lookup:** by casting `out_trade_no` back to the order PK (`Order.id == int(out_trade_no)`, `order_payment_service.py:700`) — not by WeChat's own `transaction_id` (that's logged only, never used for lookup).

**Coupling:** Tight, intentional coupling — there is no generic "payment core" for dining; `wxpay_notify` reads straight from `orders`. By contrast, the *separate* `BillingInvoice`/`BillingPayment` model (§8) already has its own `out_trade_no`, `provider`, `transaction_id`, and its own `wxpay-notify` route — an already-isolated, more generic shape.

**Reusable infra vs. dining business logic:**
- **Reusable low-level infra:** `wxpay_service.py` (`WxPayService`) — generic per-tenant JSAPI create/refund/query/verify given `out_trade_no`/`amount_fen`/`openid`; knows nothing about dining. `billing_payment_provider.py`'s abstract `BillingPaymentProvider` interface is effectively the already-built generic pattern for a second payment purpose.
- **Must never be reused as-is:** `OrderPaymentService` in full (coupon/points/print/handoff side effects baked into `_on_payment_success`), `wxpay_notify`'s order-PK lookup, refund logic tied to dining-specific fields, `order_lifecycle_service.py`, `pickup_no_service.py`, `order_print_service.py`, `payment_handoff_service.py`.

**Should SaaS subscription payment be a separate `SubscriptionOrder`, independent of `DiningOrder`? Yes — and this is already the codebase's own precedent, not a hypothetical recommendation.** The `orders` table is saturated with dining-only semantics (`table_no`, `dining_session_id`, `participant_id`, `pickup_no`, menu items, `print_status`, `served_at`, `payment_mode`) that have zero meaning for a subscription charge, and reusing it would risk a subscription payment accidentally triggering kitchen printing or coupon issuance. `BillingInvoice`/`BillingPayment` is the correct, already-present, already-isolated model to extend for this.

---

## 11. Payment Authority

```
Authority:      WX_CALLBACK_ONLY (verified — see below)
Idempotency:    Row lock (SELECT ... FOR UPDATE) + status guard
                (only order.status=="pending_payment" triggers side effects;
                 subsequent duplicate callbacks see the already-advanced status and no-op)
                Proven by tests/test_wxpay_notify_idempotency.py — same callback fired
                3x, side effects run exactly once.
Reconciliation: Active — _pending_payment_reconcile_loop (main.py:182-228, every 60s for
                orders pending >90s) calls WeChat's own query_order_by_out_trade_no and
                only proceeds to _on_payment_success if WeChat itself reports SUCCESS.
                This is WeChat-authoritative too, not a local-invented status.
Risk:           The one carve-out is _mark_order_offline_paid (order_lifecycle_service.py:20),
                reachable only via staff-authenticated postpay/table_account settlement —
                a distinct, intentional OFFLINE payment mode, not a bypass of the online
                WeChat-payment authority. Grepping the whole app/ tree for
                payment_status="paid" assignments finds exactly these two production sites
                and no others; no client-supplied field ever sets it directly.
```

**Note on the recent "harden assisted payment handoff polling" commit (`5eaab3f`):** verified by reading the actual diff — it touches only `admin-h5/src/components/AssistedOrderSheet.vue` (frontend polling-loop hardening: setTimeout self-reschedule, in-flight dedupe, visibility-change pause) and adds a new backend regression test file. It does **not** modify `payment_handoff_service.py`'s payment-status logic, and the endpoint it polls remains strictly read-only. No new non-callback path to "paid" was introduced by that change.

---

## 12. Merchant Admin UI Entry Points

Relevant `admin-h5` pages (router at `admin-h5/src/router/index.js`):

| Page | Route | Responsibility | Shows plan/status today? |
|---|---|---|---|
| `Dashboard.vue` | `/` | Merchant home: open/closed toggle, "待办" (todo) urgency list, revenue stats, first-run "开店三步走" guide | No |
| `MerchantSettings.vue` | `/settings` | Settings hub — links to store/business/payment/devices/notifications, shows inline badges for unverified WeChat Pay / unconfigured printer | No |
| `StoreSettings.vue` | `/settings/store` | Editable store profile + a plain "商家 ID" info card at the bottom | No — closest thing to an "account info" section today |
| `SuperAdmin.vue` | `/super` | Two tabs: 商家管理 (tenant list — name/phone/today's orders/WeChat-Pay status/enable-disable toggle, **no plan field**) and 渠道管理 (`ChannelPartnerPanel.vue`) | No |

**Channel Partner vs. Tenant — confirmed separate concepts.** `ChannelPartner` (`app/models/channel_revenue.py:9`) is its own table representing an external referral/reseller entity (a supplier, a POS agent, etc.), joined to a real `tenant_id` only via `ChannelPartnerTenantBinding`, which does carry a *commission-term* expiry (`commission_ends_at`) — but that tracks the platform's commission arrangement with the partner, not a merchant's own subscription plan. Do not conflate these when designing Subscription.

**Recommended placement (analysis only, no UI changed):** `StoreSettings.vue` is the most natural home for a persistent "当前套餐 / 到期时间 / 立即续费 / 套餐管理" entry — it already has a sibling plain-info "商家 ID" card at the bottom, so a "当前套餐" card fits the same established pattern. `MerchantSettings.vue` is a good secondary surface for a status badge, following the same pattern already used for the WeChat-Pay-unverified / printer-unconfigured badges. `Dashboard.vue`'s existing `todoItems` mechanism is well-suited only for an "about to expire" urgency nudge — its design philosophy is explicitly "silent unless something needs attention," so it should not become the permanent plan-management home.

---

## 13. Existing Recharge / Wallet Logic

Covered in full in §8. Summary: a real **Consumer Domain** stored-value wallet exists (`MemberAccount.balance`, spendable against dining orders, but its top-up path is mock-payment-only and disabled by default). **No Merchant Billing Domain wallet/recharge concept exists** — the only merchant-side money movement is the one-off `BillingInvoice`/`BillingPayment` pair. These two domains are already cleanly separated in the code; a future Subscription system must keep it that way and not touch `MemberAccount`.

---

## 14. Tenant Initialization Dependencies

**Foundational fact:** `BaseModel.tenant_id` (`app/models/base.py:12`) is a plain `String(32)` column with **no `ForeignKey`** to `tenant.tenant_id`. Every tenant-scoped model relies entirely on application-level query filtering, not DB-level referential integrity. There is no `relationship()` anywhere in `app/models/`, and Tenants are never hard-deleted (only `status` is toggled) — so "cascade behavior" is uniformly "none, because nothing is DB-linked and nothing deletes a Tenant."

| Record Type | Model | FK to Tenant | Classification | Why |
|---|---|---|---|---|
| Tenant | `tenant.py` | — (root) | — | Created via `TenantService.create_tenant()` |
| Store | *(no model — Tenant IS the store)* | N/A | — | Single-store-per-tenant architecture, confirmed by code comments |
| TenantConfig | `tenant_config.py` | string, not null | **MUST at creation** (created eagerly, and has a lazy-creation fallback everywhere else) | Created eagerly with `Tenant` in the same commit; every other read path defends against absence via `ensure_tenant_config()` or explicit `None` handling — no unhandled-crash path found |
| MerchantAccount (staff) | `merchant_account.py` | string, not null | **OPTIONAL** | Never created at tenant birth; owner login never queries it; a tenant with zero staff accounts works fine (owner-only shop) |
| Order | `order.py` | string (+ real FK to dining_session/participant, nullable) | **LAZY** | Created on demand; menu list gracefully returns `[]` when empty, no crash |
| Customer | `customer.py` | string | **LAZY** | Created on first WeChat login (`get_customer_by_openid` miss → `create_customer`) |
| MemberAccount | `member_account.py` | string (+ `customer_id`, no FK) | **LAZY** | `MembershipService.ensure_account()` — query-then-create-if-missing pattern |
| Coupon / CouponTemplate | `coupon.py` / `coupon_template.py` | string (+ real FKs to each other) | **LAZY** | Never pre-seeded; auto-issuance creates templates on first use if the relevant rule is enabled; gracefully no-ops otherwise |
| Printer config | columns on `Tenant` (`feieyun_sn/key`) | N/A | **OPTIONAL** | Nullable, defaults to `NULL`; UI shows "未配置打印机" gracefully, no crash path found |

**Practical takeaway for a future Subscription/Plan table:** based on this pattern, a new `Subscription` row should almost certainly follow the same convention as everything else in this codebase — a plain string `tenant_id` column, no FK, application-filtered — for consistency, unless there's a deliberate reason to deviate (flagged as a design decision for Phase 02, not a mandate).

---

## 15. Tenant Disable / Expire Semantics

**No soft-delete or hard-delete exists.** No `deleted_at` column; no tenant-delete endpoint anywhere in `app/api/`. Tenants are only ever disabled, never removed.

**Mechanism:** `Tenant.status` (Boolean), flipped by `PATCH /api/super/merchants/{id}/status` (`super_admin.py:408-418`, a simple `not tenant.status` toggle — not distinct enable/disable endpoints).

**What "disabled" (status=False) actually does, precisely:**
1. Blocks new owner logins immediately (`login.py:53-54,70-71` check `tenant.status` before issuing an SMS code or a token).
2. Already-issued JWTs (valid up to 7 days) are **not** immediately invalidated by that check alone — closed by a real-time enforcement layer instead: `AuthMiddleware._is_tenant_active()` (`auth_middleware.py:17-35`) re-checks `Tenant.status` on every non-whitelisted request, cached 45 seconds, returning `403 {"msg":"商家已停用"}` once it catches up. The code comment explicitly documents this exact reasoning: banning doesn't invalidate already-issued tokens, so this middleware check shrinks the effective ban-propagation delay from "up to 7-30 days" down to "at most the cache TTL."
3. Effectively blocks **both** merchant console access **and** customer ordering/membership APIs for that tenant, since both route families pass through the same `AuthMiddleware` gate.
4. Does **not** block whitelisted paths (`/api/super/*`, public webhook callbacks like `wxpay-notify`) — deliberately, so in-flight payment settlement always completes regardless of tenant status.
5. Does **not** block already-queued async print jobs — the background print-recovery loop iterates pending jobs directly, not through the HTTP auth path.
6. Background marketing automation (daily recall-coupon job) does correctly filter `WHERE Tenant.status == True` before running.

**No intermediate states** — this is a single boolean, binary on/off. No "suspended/read-only/grace-period" state exists.

### ⚠️ Explicit conclusion (as instructed): **Subscription expiration must NOT be implemented by flipping `Tenant.status`.**

Because `status=False` currently means "instantly blocks the merchant AND every one of that tenant's live customers from ordering, within ~45 seconds, everywhere" — reusing it for "this month's subscription invoice hasn't been paid yet" would mean a billing lapse instantly halts real, in-progress restaurant service for that tenant's diners. That is a fundamentally different severity than a subscription lapse should carry (which, per the product owner's own stated future plan, should "降级免费版" — downgrade to a free tier — not "shut off completely"). A future Subscription/Entitlement system needs its own state and its own enforcement layer, entirely separate from `Tenant.status`, which should remain reserved for its current purpose (abuse/ban).

---

## 16. Legacy Tenant Strategy

Feasible, with a proven precedent already in the codebase:

- `Tenant.created_at` is reliably populated (Python-side default via the ORM path, `nullable=False`) and is **already used for exactly this kind of cohorting today** — `app/api/v1/tenant.py:27-32`, `_is_new_merchant(tenant)`, flags tenants created within the last 7 days for onboarding UI. This proves created_at-based tenant cohorting is a known, working technique in this codebase, not a new idea.
- "Absence of a future subscription record" is also structurally sound, and requires **zero backfill**, precisely because no subscription table exists yet — any tenant created before that table's introduction will naturally have zero rows there. `NOT EXISTS (subscription WHERE tenant_id=...)` is a valid, ready-to-use legacy-detection predicate the moment the table exists.
- **Caveat:** `created_at` is a Python-side ORM default, not a DB server default — a tenant inserted by direct DB manipulation outside `TenantService.create_tenant()` could theoretically have an inconsistent value. Worth a spot-check against real production data before relying on it, but every tenant created through the normal code paths (all three entry points in §4) will have it reliably set.

### Principle to carry into Phase 02+ design (per product owner's own stated requirement)
Any legacy tenant with `subscription IS NULL` (or no subscription row) must resolve to **FULL ACCESS**, not `DENY`. This is a design principle for future enforcement phases — Phase 02 itself performs no enforcement at all (§27), so this principle has no code impact yet, but it should be written into whatever `EntitlementService` eventually reads subscription state, from day one.

---

## 17. Commercialization Domain Boundary

```
                        SaaS Layer (future)
                             │
         ┌───────────────────┼───────────────────┐
         ↓                   ↓                    ↓
   Registration        Subscription           Billing
   (extends existing   (NEW — Plan,           (extends existing
    /api/v1/register    Subscription,          BillingInvoice/
    + SMS infra)         SubscriptionOrder)     BillingPayment)
         │                   │                    │
         └──────────→   Tenant   ←────────────────┘
                             │
                             ↓
                Existing Restaurant Domain
        (Menu, Table, DiningOrder, DiningPayment,
         DiningSession, Printer, PickupNo,
         Membership, Coupon, Marketing)
```

**Reusable across the boundary (verified real, not aspirational):**
- `WxPayService` — generic low-level per-tenant WeChat JSAPI client
- `TencentSmsService` — production SMS OTP infra (own new key namespace/template needed)
- `create_access_token` / JWT auth plumbing — tenant_id-in-token pattern already works for any tenant, regardless of provisioning origin
- `TenantService.create_tenant()` — the atomic Tenant+TenantConfig creation primitive
- `BillingInvoice` / `BillingPayment` / `BillingPaymentProvider` — already the right shape for subscription charges; already has a `SAAS_SUBSCRIPTION` charge type reserved

**Must NOT be mixed (verified, not just recommended):**
- `SubscriptionOrder` (future) must be a distinct concept from `DiningOrder` (`orders` table) — the dining `orders` table is saturated with dining-only semantics.
- Subscription payment confirmation must never route through `OrderPaymentService`/`wxpay_notify` — that pipeline's side effects (kitchen printing, coupon issuance, pickup-no assignment) have zero meaning for a subscription charge and would misfire if triggered by one.
- `Tenant.status` (ban switch) must not become the subscription-expiry flag (§15).

---

## 18. Restaurant Domain Boundary

Untouchable-by-default core (see §20 for exact files): Menu/dish data, Table/DiningSession, DiningOrder + all three payment modes, dining WeChat payment + callback, printing (feieyun/kuaimai), pickup number leasing, membership points/levels, coupons, marketing recall campaigns. None of these need to change for Phase 02 (a pure data-skeleton addition) or, in the product owner's own stated design, for any phase up through feature-enforcement — enforcement should be additive (a new check layered on top), not a rewrite of these state machines.

---

## 19. Reusable Infrastructure

(Consolidated from §17 for clarity)

| Component | File | Reuse fit |
|---|---|---|
| WeChat Pay low-level client | `app/services/wxpay_service.py` | Direct — generic per-tenant JSAPI create/refund/query/verify |
| SMS OTP service | `app/services/tencent_sms_service.py` | Direct, with a new key namespace + template ID |
| User auth / JWT | `app/core/security.py` | Direct — `create_access_token`/tenant_id-in-JWT pattern is provisioning-origin-agnostic |
| Tenant provisioning primitive | `app/services/tenant_service.py::create_tenant` | Direct — the atomic Tenant+TenantConfig insert is the right foundation to build a future "create Subscription alongside Tenant" step on top of (see §4's atomicity caveat about *additional* steps not being wrapped in the same transaction) |
| Billing/invoice pipeline | `app/models/billing.py`, `app/services/billing_service.py`, `app/services/billing_payment_provider.py` | Direct — already has `SAAS_SUBSCRIPTION` charge type and an isolated WeChat-Pay-notify route |

---

## 20. DO NOT TOUCH

Every file below either enforces the payment-authority invariant (§11), a physical real-world uniqueness constraint (pickup numbers), or a security boundary (tenant isolation). Modifying any of them "in passing" during Subscription work is the single highest-risk mistake this audit can flag.

| File | Controls | Breaks if touched carelessly |
|---|---|---|
| `app/services/order_payment_service.py` | The entire dining payment authority (§11): callback handling, idempotency guard, refunds, all post-payment side effects | Duplicate points/coupons/prints on retried callbacks; paid orders silently left unpaid; double refunds; wrong orders auto-refunded |
| `app/services/wxpay_service.py` | Low-level WeChat client, signature verification, per-tenant credential handling | A signature-verification bug breaks payment for *every* tenant simultaneously, or worse, lets a forged notify be accepted (payment fraud) |
| `app/services/order_lifecycle_service.py` | Order status state machine, table settlement, offline-paid marking | Illegal status transitions slip through; double refunds; table settlement double-counts revenue/points |
| `app/services/pickup_no_service.py` | Unique-per-tenant physical pickup-number leasing | Two customers physically issued the same pickup number at once |
| `app/services/dining_session_service.py` | Table/session identity, participant token hashing | Orders misattributed to the wrong table; participant token collisions leak one diner's order to another |
| `app/services/order_print_service.py` | Kitchen/receipt ticket idempotency and retry logic | Duplicate physical tickets, or a ticket silently dropped (kitchen never cooks the order) |
| `app/services/payment_handoff_service.py` | Staff-assisted prepay QR handoff, token hashing/claim binding | A customer could claim another customer's staff-created order |
| `app/services/membership_service.py` (payment-adjacent: `apply_consumption`/`reverse_consumption`) | Points/level ledger tied to order lifecycle | Points minted without payment, or lost on legitimate purchases |
| `app/services/coupon_service.py` (payment-adjacent: `issue_auto_coupon`, `_mark_order_coupon_used_if_locked`) | Coupon lock/use/release tied to order lifecycle | Coupon double-spend |
| `app/middleware/auth_middleware.py` / `app/middleware/tenant_middleware.py` | Tenant isolation, tenant-active enforcement, whitelist | Cross-tenant data leakage, or accidentally exposing an authenticated route publicly |
| `app/models/order.py` | Dining order schema — saturated with dining semantics | A future Subscription model must never extend or alter this table (§10/§17) |
| `app/core/security.py` | JWT creation/verification, password hashing | A payload/algorithm change invalidates every existing session across all tenants |

---

## 21. Allowed Touch (Future — not implemented now)

**New files that would plausibly be added** (naming/shape only — nothing created in this phase):
- `app/models/subscription.py` — `Plan`, `Subscription`, `SubscriptionOrder` (see §27 for why `PlanFeature` is recommended to be deferred)
- `app/services/subscription_service.py`
- A new Alembic revision, additive-only, building on the current single head `20260809_0006`

**Existing files that would eventually need small, additive changes** (later phases, not Phase 02):
- `app/services/tenant_service.py::create_tenant()` — eventually needs to also create an initial trial `Subscription` row. Max allowed range when that day comes: add one more `db.add()` call inside the same commit that already creates `Tenant`+`TenantConfig`, preserving the existing atomicity rather than adding a second, separate commit (§4's own atomicity gap should not be widened further).
- `app/models/tenant.py` — if a denormalized/cached `plan_type` convenience column is ever wanted on `Tenant` itself (a judgment call, not required), it must be purely additive (nullable, defaulted) and go through Alembic, mindful of the `ensure_tenant_schema()` runtime patcher noted in §3.
- `admin-h5/src/views/settings/StoreSettings.vue`, `MerchantSettings.vue` — future UI surface for plan display (§12) — explicitly **not** in scope for Phase 02 (no UI, per §27).
- `app/api/v1/login.py::register()` — future real self-serve signup (SMS + removing the static key gate) — a distinct, later phase, not Phase 02.

---

## 22. P0 Risks

Risks that could break orders, payments, printing, or destroy tenant/production data:

1. **Reusing `orders`/`OrderPaymentService`/`wxpay_notify` for subscription payments** instead of `BillingInvoice`/`BillingPayment` — would inject non-dining semantics into a schema/pipeline saturated with dining-only meaning, and could misfire kitchen printing or coupon issuance on a subscription charge.
2. **Equating `Tenant.status = False` with "subscription expired."** Per §15, this would instantly halt live, in-progress restaurant service (both merchant console and customer ordering) for a billing lapse, contradicting the product owner's own stated intent (expiry → downgrade to free tier, not "shut off").
3. **Modifying any file in §20** (payment authority, pickup-no uniqueness, session identity, printing idempotency, tenant isolation middleware) as a side effect of unrelated Subscription-layer work.
4. **Breaking the phone-uniqueness check-then-insert pattern further** (e.g., removing the pre-check without adding a real DB constraint) while building a higher-volume public registration flow on top of §5/§6's existing gap.

## 23. P1 Risks

Risks that could cause failed signups, wrong trial timing, or inconsistent state — recoverable, not catastrophic:

1. **New Subscription creation not wrapped in the same transaction as Tenant creation** — repeating the pattern already seen in §4 (WeChat-Pay-config / plugin-install / demo-seed all being separate, un-linked commits after `create_tenant()`), a Subscription row could fail to be created after Tenant succeeds, leaving an "orphaned but not broken" tenant with no subscription record (which, per §16's principle, should default to full access anyway — but should still be understood as a real gap, not silently tolerated).
2. **New routes not added to both `TenantMiddleware` and `AuthMiddleware` whitelists consistently** (§6) — inconsistent enforcement between the two.
3. **Trusting `TenantConfig.plugin_settings.*.default_enabled` as if it reflected real plugin state** (§4/§9) when it doesn't — a naive entitlement design built on that JSON would disagree with the actual `TenantPlugin` table.
4. **Race condition in `get_tenant_by_phone`** (§5) surfacing as an unhandled `MultipleResultsFound` under real registration traffic, rather than today's low-volume super-admin/key-holder usage.

## 24. P2 Risks

Cosmetic/non-critical:

1. UI placement/labels for future plan display (§12) — a judgment call, not a correctness risk.
2. `Tenant.is_open` dead column and `Tenant.password_hash` vestigial field — potential naming confusion for future developers, no functional risk today.
3. Legacy dead code (`app/api/auth.py`, unmounted, containing a hardcoded SMS bypass) — unreachable in production, worth a cleanup ticket someday, not urgent.

---

## 25. Existing Regression Tests

Real files under `saas-base/tests/`, grouped by domain (§20's DO NOT TOUCH files should all stay green before and after any future Subscription-phase merge):

- **Order:** `test_order_amount_security_contracts.py`, `test_order_cancellation_refund.py`, `test_order_creation_idempotency.py`, `test_order_entry_security.py`, `test_order_overview_stats.py`, `test_order_split_item_stock_oversell.py`, `test_order_state_machine_contracts.py`, `test_order_stock_restoration.py`, `test_paid_order_recoverability_contracts.py`, `test_unauthenticated_basic_order_contracts.py`, `test_add_on_order_contracts.py`, `test_merchant_order_delivery_contracts.py`, `test_merchant_order_lookup_contracts.py`
- **Payment:** `test_order_payment_security.py`, `test_payment_idempotency_contracts.py`, `test_payment_mode_concurrency_contracts.py`, `test_payment_mode_contracts.py`, `test_payment_mode_integration_contracts.py`, `test_payment_mode_p1_contracts.py`, `test_payment_result_recovery_contracts.py`, `test_pending_payment_reconcile_loop.py`, `test_prepay_assisted_payment_handoff.py`, `test_settle_table_offline_paid_behavior.py`
- **WxPay:** `test_wxpay_cancel_race_reconciliation.py`, `test_wxpay_notify_idempotency.py`
- **Printer:** `test_feieyun_ticket_includes_items.py`, `test_kuaimai_contracts.py`, `test_kuaimai_service_contracts.py`, `test_kuaimai_service_file_contracts.py`, `test_print_failure_recovery_contracts.py`
- **Pickup:** `test_pickup_no_assignments.py`, `test_pickup_no_mode_consistency.py`, `test_pickup_no_shared_across_table.py`
- **Tenant:** `test_tenant_account_contracts.py`, `test_tenant_isolation_scan.py`, `test_tenant_logo_upload.py`, `test_channel_entry_tenant_isolation.py`, `test_coupon_tenant_security.py`, `test_entrance_code_coupon_template_tenant_isolation.py`
- **Auth:** `test_auth_middleware_tenant_status.py`, `test_merchant_sms_login_contracts.py`, `test_merchant_staff_permissions.py`, `test_merchant_staff_security_gate.py`, `test_staff_password_trusted_device.py`, `test_staff_session_service.py`, `test_channel_production_sms_login.py`, `test_channel_portal_security_gate.py`
- **Membership:** `test_member_asset_idempotency_contracts.py`, `test_member_client_contracts.py`, `test_member_mock_identity_security.py`, `test_customer_identity_contracts.py`, `test_customer_identity_resolve_join.py`
- **Coupon:** `test_coupon_loop_contracts.py`, `test_coupon_payment_mode_rewards.py`, `test_coupon_redis_fallback_idempotency.py`, `test_coupon_template_snapshot.py`, `test_coupon_tenant_security.py`, `test_member_coupon_rule_consistency.py`, `test_table_coupon_activity_contracts.py`
- **Billing (existing, relevant precedent):** `test_saas_billing_foundation.py`

**Minimum bar before merging any future Subscription-phase change:** an app-import smoke test, the full `payment mode contracts` group, `test_wxpay_notify_idempotency.py`, `test_pending_payment_reconcile_loop.py`, the printer group, the pickup group, and `test_tenant_isolation_scan.py` — since Subscription work touches `Tenant`-adjacent code paths even when additive, tenant-isolation regressions are the most plausible accidental breakage.

---

## 26. Alembic Status

```
alembic heads:    20260809_0006 (single head — no unmerged branches currently)
alembic current:  20260803_0003 (this machine's local dev DB — six migrations behind repo head)
```

Migration naming style: `YYYYMMDD_NNNN_description.py` (date-prefixed, sequential per day), mostly linear; one historical branchpoint (`20260429_0007 -> 20260430_0008`) exists in `alembic history` but has since been merged back to a single head. No `upgrade`/`downgrade` was run during this audit. The local-current-vs-head gap is a note about this development machine's local database only — it says nothing about production, which is migrated separately per this repo's own documented deployment recipe.

---

## 27. Recommended Phase 02 Scope

**Phase 02 — Subscription Data Skeleton.** Strictly data-model only.

**In scope:**
- New Alembic migration (additive-only, built on top of head `20260809_0006`): create tables for `Plan` and `Subscription` (and `SubscriptionOrder` if the team wants the audit trail from day one — reasonable to include since `BillingInvoice`/`BillingPayment` already establishes the "charge/payment as separate rows" pattern this would mirror).
- Corresponding SQLAlchemy models in a new `app/models/subscription.py`, following this codebase's existing convention: plain string `tenant_id`, no FK (consistent with every other tenant-scoped model per §14), `Base` from `app/models/base.py` (the one real shared registry — confirmed in §3, no separate-registry pattern actually exists to replicate or avoid).
- **Recommendation: defer `PlanFeature` to a later phase.** §9 already found four-plus independent, partially-inconsistent "is this feature on" mechanisms in the existing codebase. Adding a fifth (a Plan→Feature mapping) before entitlement-enforcement design is settled risks becoming yet another disagreeing source of truth. `Plan`/`Subscription`/`SubscriptionOrder` alone are sufficient for a true data skeleton; feature-to-plan mapping is a Phase 03+ (enforcement-phase) concern, in keeping with "Less but Better."

**Explicitly out of scope (per product owner's own constraint, and this audit agrees):**
```
NO UI
NO REGISTRATION CHANGES
NO PAYMENT WIRING (BillingPaymentProvider stays exactly as-is, real WX path stays disabled)
NO FEATURE ENFORCEMENT
NO EXPIRATION ENFORCEMENT (Tenant.status is untouched, per §15)
NO RESTAURANT DOMAIN CHANGE (§20 files untouched)
```

**Success criterion:** Phase 02 could be merged and deployed to production, and **zero existing user (merchant or diner) would notice any difference** — new empty tables, nothing reads or writes them yet outside of tests.

**Required new tests for Phase 02:** a migration-applies-cleanly test (or equivalent CI check), and model-level tests confirming the new tables don't interfere with `Tenant`/`TenantConfig` creation (i.e., `TenantService.create_tenant()` behavior is byte-for-byte unchanged — no new required Subscription row yet, since that's a later phase per §21).

---

## 28. Final Go / No-Go Decision

## GO

Rationale: no blocking architectural defect was found. The path to Phase 02 is unusually well-prepared for this kind of codebase — `BillingInvoice`/`BillingPayment` already reserves a `SAAS_SUBSCRIPTION` charge type and already isolates itself from dining payment code; SMS OTP infra is production-grade and reusable; a gated self-registration endpoint already proves the register→auto-login mechanics; `created_at`-based legacy cohorting is an established pattern, not a new idea; and the dining payment pipeline's `WX_CALLBACK_ONLY` authority is verified intact and already structurally separated from where subscription payments would live.

**Conditions attached to the GO** (all non-negotiable per this audit's findings, not optional style preferences):
1. Phase 02 touches **only** new files (`app/models/subscription.py`, `app/services/subscription_service.py` if needed, one new Alembic migration). Zero files from §20 (DO NOT TOUCH) may be modified.
2. New tables use plain string `tenant_id` (no FK), consistent with every existing tenant-scoped model.
3. `Tenant.status` remains untouched and is not connected to subscription state in this phase (§15).
4. No new middleware, no new route gating, no UI changes (§27).
5. Before Phase 02's migration work begins on this machine, run `alembic upgrade head` locally first (§26) so the new migration is authored against a clean, current baseline — this does not require production access and is not itself part of Phase 02's scope, just local hygiene.

**Phase 02 maximum modification scope:**
- New files: up to 3 (`app/models/subscription.py`, `app/services/subscription_service.py`, one Alembic revision file)
- Existing files modified: 0 (the additive changes described in §21 for `tenant_service.py`/`tenant.py` are explicitly **not** part of Phase 02 — they belong to a later phase, once Subscription creation is actually wired into onboarding)
- Files forbidden from modification: everything listed in §20
- Required new tests: as specified in §27

**Audit document:** written to `docs/saas-subscription-audit.md` at the monorepo root (no pre-existing `docs/` directory was found at the root; one exists only inside `saas-base/docs` and `saas-base.backup.20260801/docs`, so a new root-level `docs/` was created per the audit's own fallback instruction, containing only this one file).
