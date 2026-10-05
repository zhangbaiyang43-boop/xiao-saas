<template>
  <section class="merchant-section animate-in" aria-label="商户列表">
    <div class="toolbar">
      <div class="search-wrap">
        <input
          v-model="searchText"
          type="search"
          class="search-input"
          placeholder="搜索商户名称、手机号或 Tenant ID"
          aria-label="搜索商户名称、手机号或 Tenant ID"
          @input="onSearchInput"
          @keydown.esc="clearSearch"
        />
        <button v-if="searchText" type="button" class="search-clear" aria-label="清除搜索" @click="clearSearch">×</button>
      </div>
      <label class="filter-field">
        <span>账号</span>
        <select :value="filters.account" @change="setFilter('account', $event.target.value)">
          <option v-for="o in ACCOUNT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label class="filter-field">
        <span>收款</span>
        <select :value="filters.payment" @change="setFilter('payment', $event.target.value)">
          <option v-for="o in PAYMENT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label class="filter-field">
        <span>套餐</span>
        <select :value="filters.plan" @change="setFilter('plan', $event.target.value)">
          <option v-for="o in PLAN_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label class="filter-field">
        <span>排序</span>
        <select :value="filters.sort" @change="setFilter('sort', $event.target.value)">
          <option value="">默认（最新开通）</option>
          <option value="expiry">到期最近</option>
          <option value="orders">今日订单最多</option>
        </select>
      </label>
      <button type="button" class="ghost-btn tap-shrink" :disabled="!hasFilter" @click="resetFilters">重置</button>
      <button type="button" class="ghost-btn tap-shrink" :disabled="loading" @click="$emit('refresh')">{{ loading ? '刷新中...' : '刷新' }}</button>
    </div>

    <div class="list-summary" aria-live="polite">
      <template v-if="merchants.length">共 {{ merchants.length }} 个商户<template v-if="hasFilter">，符合条件 {{ rows.length }} 个</template></template>
    </div>

    <div v-if="loading && !merchants.length" class="state-box">加载中...</div>
    <div v-else-if="error" class="state-box error-state">
      <div>{{ error }}</div>
      <button type="button" class="ghost-btn tap-shrink" @click="$emit('refresh')">重新加载</button>
    </div>
    <div v-else-if="merchants.length === 0" class="state-box">
      <div>暂无商户</div>
      <button type="button" class="ghost-btn tap-shrink" @click="$emit('create')">开通商户</button>
    </div>
    <div v-else-if="rows.length === 0" class="state-box">
      <div>没有符合筛选条件的商户</div>
      <button type="button" class="ghost-btn tap-shrink" @click="resetFilters">重置筛选</button>
    </div>

    <template v-else>
      <!-- Desktop (>= 1280px): one dense table. Same rows, same actions as the stacked cards below. -->
      <table class="merchant-table">
        <caption class="sr-only">商户列表</caption>
        <colgroup>
          <col class="c-merchant" /><col class="c-account" /><col class="c-payment" /><col class="c-plan" />
          <col class="c-expiry" /><col class="c-channel" /><col class="c-orders" /><col class="c-actions" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">商户</th>
            <th scope="col">账号</th>
            <th scope="col">收款</th>
            <th scope="col">套餐</th>
            <th scope="col" :aria-sort="filters.sort === 'expiry' ? 'ascending' : 'none'">到期</th>
            <th scope="col">渠道</th>
            <th scope="col" class="num" :aria-sort="filters.sort === 'orders' ? 'descending' : 'none'">今日订单</th>
            <th scope="col" class="actions-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="m in rows" :key="m.tenant_id">
            <tr>
              <td>
                <button type="button" class="name-link" :title="m.name" @click="$emit('open', m)">{{ m.name }}</button>
                <div class="sub-line">
                  <button type="button" class="phone-btn" :title="phoneTitle(m)" @click="togglePhone(m.tenant_id)">{{ phoneText(m) }}</button>
                </div>
                <div class="sub-line tenant-id" :title="m.tenant_id">{{ m.tenant_id }}</div>
              </td>
              <td><span class="badge" :class="m.status ? 'acct-on' : 'acct-off'">{{ accountText(m) }}</span></td>
              <td><span class="badge" :class="`pay-${paymentKey(m)}`">{{ statusText(paymentKey(m)) }}</span></td>
              <td>
                <div class="cell-main" :class="{ 'cell-error': planCell(m.subscription).error }">{{ planCell(m.subscription).name }}</div>
                <span v-if="planCell(m.subscription).tag" class="badge plan-tag" :class="planCell(m.subscription).tag === '试用' ? 'plan-trial' : 'plan-ended'">{{ planCell(m.subscription).tag }}</span>
              </td>
              <td>
                <div class="cell-main">{{ expiryCell(m.subscription).date }}</div>
                <div v-if="expiryCell(m.subscription).remaining" class="sub-line" :class="{ urgent: expiryCell(m.subscription).urgent }">{{ expiryCell(m.subscription).remaining }}</div>
              </td>
              <td><div class="cell-main" :class="{ muted: !m.channel?.bound }" :title="channelLabel(m.channel)">{{ channelLabel(m.channel) }}</div></td>
              <td class="num">{{ todayOrdersText(m) }}</td>
              <td class="actions-col">
                <MerchantRowActions
                  :merchant="m"
                  :danger-open="dangerOpenId === m.tenant_id"
                  @view="$emit('open', m)"
                  @pay-config="$emit('pay-config', m)"
                  @toggle-danger="$emit('toggle-danger', m.tenant_id)"
                />
              </td>
            </tr>
            <tr v-if="hasDetailRow(m)" class="detail-row">
              <td colspan="8">
                <MerchantDangerZone
                  v-if="dangerOpenId === m.tenant_id"
                  :merchant="m"
                  :busy="rowBusy(m.tenant_id)"
                  :status-busy="statusBusyId === m.tenant_id"
                  :seeding="seedingId === m.tenant_id"
                  @toggle-status="$emit('toggle-status', m)"
                  @seed="$emit('seed', m)"
                />
                <div v-if="statusResult && statusResult.tenant_id === m.tenant_id" class="result-note" :class="statusResult.ok ? 'ok' : 'err'">{{ statusResult.msg }}</div>
                <div v-if="seedResult && seedResult.tenant_id === m.tenant_id" class="result-note" :class="seedResult.ok ? 'ok' : 'err'">{{ seedResult.msg }}</div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <!-- Narrow (< 1280px): compact stacked cards from the same rows. -->
      <ul class="merchant-cards">
        <li v-for="m in rows" :key="m.tenant_id" class="merchant-card">
          <div class="card-head">
            <button type="button" class="name-link" :title="m.name" @click="$emit('open', m)">{{ m.name }}</button>
            <span class="badge" :class="m.status ? 'acct-on' : 'acct-off'">{{ accountText(m) }}</span>
          </div>
          <div class="sub-line">
            <button type="button" class="phone-btn" :title="phoneTitle(m)" @click="togglePhone(m.tenant_id)">{{ phoneText(m) }}</button>
            · <span class="tenant-id">{{ m.tenant_id }}</span>
          </div>
          <dl class="card-facts">
            <div><dt>收款</dt><dd><span class="badge" :class="`pay-${paymentKey(m)}`">{{ statusText(paymentKey(m)) }}</span></dd></div>
            <div>
              <dt>套餐</dt>
              <dd>
                <span :class="{ 'cell-error': planCell(m.subscription).error }">{{ planCell(m.subscription).name }}</span>
                <span v-if="planCell(m.subscription).tag" class="badge plan-tag" :class="planCell(m.subscription).tag === '试用' ? 'plan-trial' : 'plan-ended'">{{ planCell(m.subscription).tag }}</span>
              </dd>
            </div>
            <div>
              <dt>到期</dt>
              <dd>{{ expiryCell(m.subscription).date }}<span v-if="expiryCell(m.subscription).remaining" class="remaining" :class="{ urgent: expiryCell(m.subscription).urgent }"> · {{ expiryCell(m.subscription).remaining }}</span></dd>
            </div>
            <div><dt>渠道</dt><dd :class="{ muted: !m.channel?.bound }">{{ channelLabel(m.channel) }}</dd></div>
            <div><dt>今日订单</dt><dd class="num-inline">{{ todayOrdersText(m) }}</dd></div>
          </dl>
          <div class="card-actions">
            <MerchantRowActions
              :merchant="m"
              :danger-open="dangerOpenId === m.tenant_id"
              @view="$emit('open', m)"
              @pay-config="$emit('pay-config', m)"
              @toggle-danger="$emit('toggle-danger', m.tenant_id)"
            />
          </div>
          <div v-if="hasDetailRow(m)" class="card-detail">
            <MerchantDangerZone
              v-if="dangerOpenId === m.tenant_id"
              :merchant="m"
              :busy="rowBusy(m.tenant_id)"
              :status-busy="statusBusyId === m.tenant_id"
              :seeding="seedingId === m.tenant_id"
              @toggle-status="$emit('toggle-status', m)"
              @seed="$emit('seed', m)"
            />
            <div v-if="statusResult && statusResult.tenant_id === m.tenant_id" class="result-note" :class="statusResult.ok ? 'ok' : 'err'">{{ statusResult.msg }}</div>
            <div v-if="seedResult && seedResult.tenant_id === m.tenant_id" class="result-note" :class="seedResult.ok ? 'ok' : 'err'">{{ seedResult.msg }}</div>
          </div>
        </li>
      </ul>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MerchantDangerZone from './MerchantDangerZone.vue'
import MerchantRowActions from './MerchantRowActions.vue'
import {
  ACCOUNT_OPTIONS,
  PAYMENT_OPTIONS,
  PLAN_OPTIONS,
  accountText,
  channelLabel,
  expiryCell,
  filterMerchants,
  filtersFromQuery,
  hasActiveFilter,
  maskPhone,
  planCell,
  queryWithPatch,
  sortMerchants,
  statusText,
  todayOrdersText,
} from './merchantListModel'

const props = defineProps({
  merchants: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  dangerOpenId: { type: String, default: '' },
  statusBusyId: { type: String, default: '' },
  seedingId: { type: String, default: '' },
  statusResult: { type: Object, default: null },
  seedResult: { type: Object, default: null },
})
defineEmits(['refresh', 'create', 'open', 'pay-config', 'toggle-danger', 'toggle-status', 'seed'])

const route = useRoute()
const router = useRouter()

// The URL query is the single source of truth for filters: Back / Forward, refresh and a
// copied link all restore the same view. Overview shortcuts already use ?payment= / ?account=.
const filters = computed(() => filtersFromQuery(route.query))
const searchText = ref(filters.value.q)
const revealedPhones = reactive(new Set())
let searchTimer = null

watch(() => filters.value.q, (q) => {
  if (q !== searchText.value.trim()) searchText.value = q
})

// Filtering follows the typed text immediately; the URL is updated a moment later.
const effective = computed(() => ({ ...filters.value, q: searchText.value.trim() }))
const hasFilter = computed(() => hasActiveFilter(effective.value))
const rows = computed(() => sortMerchants(filterMerchants(props.merchants, effective.value), filters.value.sort))

function pushPatch(patch) {
  router.replace({ path: route.path, query: queryWithPatch(route.query, patch) })
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => pushPatch({ q: searchText.value.trim() }), 250)
}

function clearSearch() {
  clearTimeout(searchTimer)
  searchText.value = ''
  pushPatch({ q: '' })
}

function setFilter(key, value) {
  pushPatch({ [key]: value })
}

function resetFilters() {
  clearTimeout(searchTimer)
  searchText.value = ''
  pushPatch({ q: '', account: '', payment: '', plan: '' })
}

function paymentKey(m) {
  return m.payment_status || 'unconfigured'
}

function phoneText(m) {
  return revealedPhones.has(m.tenant_id) ? (m.phone || '-') : (m.phone_masked || maskPhone(m.phone))
}

function phoneTitle(m) {
  return revealedPhones.has(m.tenant_id) ? '点击隐藏手机号' : '点击显示完整手机号'
}

function togglePhone(tenantId) {
  if (revealedPhones.has(tenantId)) revealedPhones.delete(tenantId)
  else revealedPhones.add(tenantId)
}

function rowBusy(tenantId) {
  return props.statusBusyId === tenantId || props.seedingId === tenantId
}

function hasDetailRow(m) {
  return props.dangerOpenId === m.tenant_id
    || (props.statusResult && props.statusResult.tenant_id === m.tenant_id)
    || (props.seedResult && props.seedResult.tenant_id === m.tenant_id)
}

onBeforeUnmount(() => clearTimeout(searchTimer))
</script>

<style scoped>
.merchant-section { margin: 0 16px 16px; padding: 16px; background: var(--bg-card); border-radius: var(--radius-card); }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

/* ─── Toolbar ───────────────────────────────────────────────── */
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.search-wrap { position: relative; flex: 1 1 240px; min-width: 200px; }
.search-input {
  width: 100%; height: 36px; padding: 0 30px 0 12px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-card); color: var(--text-1); font-size: 14px; outline: none;
}
.search-input:focus { border-color: var(--hero-dark); box-shadow: 0 0 0 2px rgba(26,26,46,.12); }
.search-clear {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%); width: 28px; height: 28px;
  border: 0; border-radius: 6px; background: transparent; color: var(--text-3); font-size: 18px; line-height: 1; cursor: pointer;
}
.filter-field { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 800; color: var(--text-3); }
.filter-field select {
  height: 36px; padding: 0 8px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card);
  color: var(--text-1); font-size: 13px; font-weight: 700;
}
.filter-field select:focus-visible, .ghost-btn:focus-visible, .name-link:focus-visible, .phone-btn:focus-visible, .search-clear:focus-visible { outline: 2px solid var(--hero-dark); outline-offset: 2px; }
.ghost-btn {
  height: 36px; padding: 0 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card);
  color: var(--text-2); font-size: 13px; font-weight: 700; cursor: pointer;
}
.ghost-btn:disabled { opacity: .55; cursor: not-allowed; }
.list-summary { min-height: 20px; margin: 10px 0 6px; font-size: 12px; color: var(--text-3); }

/* ─── States ────────────────────────────────────────────────── */
.state-box { display: grid; justify-items: center; gap: 10px; padding: 28px 0; color: var(--text-3); font-size: 14px; text-align: center; }
.error-state { color: var(--danger); }

/* ─── Shared cell bits ──────────────────────────────────────── */
.name-link {
  display: block; max-width: 100%; padding: 0; border: 0; background: transparent; color: var(--text-1);
  font-size: 14px; font-weight: 800; text-align: left; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.name-link:hover { text-decoration: underline; }
.phone-btn { padding: 0; border: 0; border-bottom: 1px dashed var(--text-3); background: transparent; color: var(--text-2); font-size: 12px; cursor: pointer; }
.sub-line { margin-top: 2px; font-size: 12px; color: var(--text-3); }
.tenant-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cell-main { font-size: 13px; font-weight: 700; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cell-error { color: var(--danger); }
.muted { color: var(--text-3); font-weight: 600; }
.urgent { color: #b45309; font-weight: 800; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; white-space: nowrap; }
.acct-on { background: var(--brand-light); color: var(--success); }
.acct-off { background: #f3f4f6; color: var(--text-2); box-shadow: inset 0 0 0 1px var(--text-3); }
.pay-verified { background: var(--brand-light); color: var(--success); }
.pay-pending { background: rgba(245, 158, 11, .16); color: #b45309; }
.pay-unconfigured { background: #f3f4f6; color: var(--text-2); box-shadow: inset 0 0 0 1px var(--border); }
.pay-paused { background: #fef2f2; color: var(--danger); }
.plan-tag { margin-top: 3px; padding: 1px 7px; font-size: 11px; }
.plan-trial { background: #eff6ff; color: #2563eb; }
.plan-ended { background: #f3f4f6; color: var(--text-2); box-shadow: inset 0 0 0 1px var(--text-3); }
.result-note { margin-top: 8px; padding: 8px 10px; border-radius: 8px; font-size: 13px; }
.result-note.ok { background: var(--brand-light); color: var(--success); }
.result-note.err { background: #fef2f2; color: var(--danger); }

/* ─── Desktop table (>= 1280px) ─────────────────────────────── */
.merchant-table { display: none; width: 100%; border-collapse: collapse; table-layout: fixed; }
.merchant-table th {
  padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; font-size: 12px; font-weight: 800; color: var(--text-3);
}
.merchant-table td { padding: 10px; border-bottom: 1px solid var(--border); vertical-align: middle; overflow: visible; }
.merchant-table tbody tr:hover > td { background: var(--bg-page); }
.merchant-table .detail-row > td, .merchant-table .detail-row:hover > td { background: transparent; padding-top: 0; }
.merchant-table .num, .num-inline { text-align: right; font-variant-numeric: tabular-nums; font-weight: 800; }
.merchant-table td.num { font-size: 15px; }
.merchant-table .actions-col { text-align: right; }
.c-merchant { width: 23%; } .c-account { width: 8%; } .c-payment { width: 9%; } .c-plan { width: 12%; }
.c-expiry { width: 14%; } .c-channel { width: 12%; } .c-orders { width: 8%; } .c-actions { width: 14%; }

/* ─── Narrow cards (< 1280px) ───────────────────────────────── */
.merchant-cards { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.merchant-card { padding: 12px; border-radius: 10px; background: var(--bg-page); }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 6px 14px; margin: 8px 0 0; }
.card-facts div { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
.card-facts dt { flex: none; font-size: 12px; color: var(--text-3); }
.card-facts dd { margin: 0; min-width: 0; font-size: 13px; font-weight: 700; color: var(--text-1); }
.remaining { font-weight: 600; color: var(--text-3); }
.remaining.urgent { color: #b45309; font-weight: 800; }
.card-actions { margin-top: 10px; }
.card-detail { margin-top: 8px; }

@media (min-width: 1280px) {
  .merchant-table { display: table; }
  .merchant-cards { display: none; }
}

@media (max-width: 420px) {
  .merchant-section { margin-right: 0; margin-left: 0; }
  .filter-field { flex: 1 1 140px; }
  .filter-field select { flex: 1; }
}
</style>
