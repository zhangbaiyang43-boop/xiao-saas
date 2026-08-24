# 开心点单 Frontend Constitution V1

```
VERSION=V1.0
SCOPE=member-mini-client
PLATFORM=mp-weixin primary
AUTHORITY=Frontend Constitution V1
```

This is the executable frontend contract for `member-mini-client`.
It is not a design-system catalog and not a visual style guide.

## Status

NEW code MUST comply.
TOUCHED old code migrates only the primitive related to that change.
UNTOUCHED old code MAY remain.

```
BIG_BANG_REWRITE=FORBIDDEN
TOUCH_AND_MIGRATE=REQUIRED
DOM_ORDER_IS_AUTHORITY=NO
```

## Current CI Contract

mp-weixin is the primary platform build gate. H5 build stays.

```
CI_REQUIRED_GATES=
Lint
Frontend UI Contracts
Unit Tests
Build H5
Build mp-weixin
```

These run in `.github/workflows/member-mini-client-ci.yml` via package scripts (`npm run lint`, `npm run check:ui-contracts`, `npm run test:unit`, `npm run build:h5`, `npm run build:mp-weixin`). Workflow MUST NOT invoke raw `uni build`.

## Authority Hierarchy

1. Payment / money business contracts (not redefined here)
2. This Constitution
3. Named primitives (Overlay, BaseSheet, Layer tokens, existing State*, AddBtn)
4. Legacy implementation (not a source of new standards)

## Architecture

```
Pages → Business Components → Design System Primitives → Tokens
```

Primitives MUST NOT import pages, business composables, or API / payment logic.
Business components MUST NOT reimplement a named primitive.
`useCheckout` keeps order/payment state. Do not move that authority back into `menu.vue`.

## Layer Contract

```
CHROME < FLOATING < BLOCKING < BLOCKING_TOP < CRITICAL
```

Tokens in `src/styles/global.scss`:

| Token | Value |
|---|---|
| `--z-chrome` | 300 |
| `--z-floating` | 850 |
| `--z-blocking` | 3100 |
| `--z-blocking-top` | 3200 |
| `--z-critical` | 4000 |
| `--overlay-dim` | `rgba(0,0,0,0.5)` |

Business components MUST NOT invent blocking z-index numbers (`3000`, `3100`, `9000`, `9999`, …).

No toast / popover / dropdown / drawer bands.

## Overlay / Blocking Surface Contract

Full-screen blocking overlay geometry, dim, and layer belong to **BaseOverlay**.

Consumers:

| Surface | Authority | Layer |
|---|---|---|
| CheckoutSheet | BaseSheet → BaseOverlay | BLOCKING (`3100`) |
| CouponPicker | BaseSheet → BaseOverlay | BLOCKING_TOP (`3200`) |
| Remaining `_shared.scss` `.mask` users (SpecSheet, PaymentSuccessSheet, WelcomeCouponSheet) | legacy `.mask` | BLOCKING (`var(--z-blocking)` = 3100) |
| OrderHistorySheet, TableBillSheet | BaseSheet → BaseOverlay | BLOCKING (`3100`) |
| MemberCheckoutChoice | BaseOverlay | BLOCKING_TOP (`3200`) |
| CheckoutAuthSheet | BaseOverlay | BLOCKING_TOP (`3200`) |

When CheckoutSheet is open and MemberCheckoutChoice, CheckoutAuthSheet, or CouponPicker is also open, the latter MUST sit above CheckoutSheet because **3200 > 3100**. DOM order in `menu.vue` is not the stack authority.

Concurrent blocking surfaces MUST either replace or explicitly stack. Unspecified dual-boolean stacking is forbidden.

BaseOverlay owns: `position:fixed`, `inset:0`, dim, layer, and **mask-click via a dedicated backdrop node**.
Slot content clicks MUST NOT emit `mask-click`. Consumers MUST NOT be required to remember `@click.stop` for this to be true.
BaseOverlay does **not** own: sheet chrome, bottom placement, title, footer, safe-area, buttons, business state.

Invalid `layer` MUST fail closed. It MUST NOT fall back to `blocking`.

## Bottom Sheet Shell Contract

**BaseSheet** is sheet-shell authority for new standard bottom sheets.

```
Pages → Business Components → BaseSheet → BaseOverlay → Tokens
```

BaseSheet MUST compose BaseOverlay. It MUST NOT reimplement overlay geometry, dim, or blocking z-index.

BaseSheet owns: bottom placement, sheet surface, top radius, max-height, flex column shell, standard header (title + close), optional `header-left`, default body slot, footer slot, mask-click → `close`, and the shared safe-area shell used by the first family.

BaseSheet does **not** own: business loading/empty/error, order status, coupon/payment/table state, business footers, APIs, checkout, or scroll data.

Full-screen blocking overlay → BaseOverlay authority.
Bottom sheet shell → BaseSheet for **new standard bottom sheets**.
These layers are not the same.

Legal: a special blocking overlay MAY use BaseOverlay directly.
Forbidden: requiring every BaseOverlay consumer to use BaseSheet.

## Async Visible Feedback

For submit / pay / join member / phone auth / opening a blocking surface:
state change without a visible result is forbidden (`STATE_CHANGED_BUT_UI_INVISIBLE`).

Text-only loading is enough only while the clicked control stays visible.
`showX=true` with an invisible overlay is a constitution failure.

## Page-level State

New page-level loading / empty / error MUST use existing `StateLoading` / `StateEmpty` / `StateError`.
Menu skeleton (`LoadingStates`) remains a separate legal primitive.
Do not create `AppState`.

## Color (narrow)

New primary CTAs MUST use `--brand` / `--btn-primary-*`.
Do not introduce a third brand green (`#16c76f` copies).
Coupon red and member gold are allowed business colors.
Do not tokenise every hex.

## MUST

1. New blocking overlays go through BaseOverlay. Exact class token `mask` is legal only on F1C-registered `LEGACY_MASK_ALLOWLIST` paths that also import `_shared.scss`. Importing `_shared.scss` does **not** self-promote a new file to legacy.
2. Stacked checkout choice/auth layers use `layer="blocking-top"`.
3. New standard bottom sheets use BaseSheet, which composes BaseOverlay. Touched legacy bottom sheets migrate the shell only.
4. Core-flow state changes are visible.
5. Touched files migrate only the related primitive.
6. Machine-checkable overlay MUSTs stay in `npm run check:ui-contracts`.

## MUST NOT

1. Do not implement raw `position:fixed` + full-viewport + dim + blocking z-index outside BaseOverlay / listed legacy.
2. Do not add a new exact class token `mask` consumer. Legacy `mask` files must stay on the F1C allowlist and keep the `_shared.scss` import.
3. Do not use `class="mask"` in MemberCheckoutChoice, CheckoutAuthSheet, OrderHistorySheet, or TableBillSheet.
4. Do not treat DOM order as overlay stack authority.
5. Do not require every BaseOverlay consumer to use BaseSheet.
6. Do not big-bang rewrite UI, buttons, typography, cards, or payment state machines under this constitution.

## Exception

PR must record: why the primitive does not fit, limited file paths, `temporary` (with follow-up) or `permanent`.
Unrecorded exceptions are unapproved.

## Deferred (not forgotten)

AppButton, AppCard, typography/spacing/radius systems, full hex cleanup, merging LoadingStates into StateError.
