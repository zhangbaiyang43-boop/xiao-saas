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

`build:mp-weixin` MUST enter member-mini-client CI no later than **F1C**.

## Authority Hierarchy

1. Payment / money business contracts (not redefined here)
2. This Constitution
3. Named primitives (Overlay, Layer tokens, existing State*, AddBtn)
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

F1B consumers:

| Surface | Authority | Layer |
|---|---|---|
| CheckoutSheet and other `_shared.scss` `.mask` users | legacy `.mask` | BLOCKING (`var(--z-blocking)` = 3100) |
| MemberCheckoutChoice | BaseOverlay | BLOCKING_TOP (`3200`) |
| CheckoutAuthSheet | BaseOverlay | BLOCKING_TOP (`3200`) |

When CheckoutSheet is open and MemberCheckoutChoice or CheckoutAuthSheet is also open, the latter MUST sit above CheckoutSheet because **3200 > 3100**. DOM order in `menu.vue` is not the stack authority.

Concurrent blocking surfaces MUST either replace or explicitly stack. Unspecified dual-boolean stacking is forbidden.

BaseOverlay owns: `position:fixed`, `inset:0`, dim, layer, and **mask-click via a dedicated backdrop node**.
Slot content clicks MUST NOT emit `mask-click`. Consumers MUST NOT be required to remember `@click.stop` for this to be true.
BaseOverlay does **not** own: sheet chrome, bottom placement, title, footer, safe-area, buttons, business state.

Invalid `layer` MUST fail closed. It MUST NOT fall back to `blocking`.

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

1. New blocking overlays go through BaseOverlay (legacy: `_shared.scss` `.mask` **and** that import).
2. Stacked checkout choice/auth layers use `layer="blocking-top"`.
3. Core-flow state changes are visible.
4. Touched files migrate only the related primitive.
5. Machine-checkable overlay MUSTs stay in `npm run check:ui-contracts`.

## MUST NOT

1. Do not implement raw `position:fixed` + full-viewport + dim + blocking z-index outside BaseOverlay / listed legacy.
2. Do not use class token `mask` without importing `_shared.scss`.
3. Do not use `class="mask"` in MemberCheckoutChoice or CheckoutAuthSheet.
4. Do not treat DOM order as overlay stack authority.
5. Do not big-bang rewrite UI, buttons, typography, cards, or payment state machines under this constitution.

## Exception

PR must record: why the primitive does not fit, limited file paths, `temporary` (with follow-up) or `permanent`.
Unrecorded exceptions are unapproved.

## Deferred (not forgotten)

BaseSheet, AppButton, AppCard, typography/spacing/radius systems, full hex cleanup, merging LoadingStates into StateError.
`build:mp-weixin` in CI: F1C, not later.
