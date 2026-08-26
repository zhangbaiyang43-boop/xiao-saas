<template>
  <a-drawer
    :open="open"
    title="顾客加菜"
    placement="bottom"
    height="90%"
    :body-style="{ padding: 0, display: 'flex', flexDirection: 'column' }"
    @update:open="onOpenChange"
  >
    <div class="ao-body">
        <!-- STEP 1: 选桌 -->
        <div v-if="step === 1" class="ao-step">
          <div class="ao-step-label">选哪一桌</div>
          <div v-if="loadingSessions" class="ao-empty">加载中…</div>
          <div v-else-if="!sessions.length" class="ao-empty">当前桌台没有进行中的用餐订单</div>
          <div v-else class="ao-tables">
            <button
              v-for="s in sessions"
              :key="s.dining_session_id"
              type="button"
              class="ao-table-card"
              :class="{ selected: selectedSessionId === s.dining_session_id }"
              @click="selectSession(s)"
            >
              <strong class="ao-table-no">{{ s.table_no || '未分桌' }}号桌</strong>
              <span v-if="s.pickup_no" class="muted">{{ s.pickup_no }}号桌牌</span>
              <span v-else class="muted">未发牌</span>
            </button>
          </div>
          <a-button
            type="primary"
            block
            size="large"
            class="ao-next"
            :disabled="!selectedSessionId"
            @click="step = 2"
          >下一步</a-button>
        </div>

        <!-- STEP 2: 选菜 -->
        <div v-else-if="step === 2" class="ao-step ao-step-menu">
          <div class="ao-context">
            {{ selectedSession?.table_no || '-' }}号桌
            <span v-if="selectedSession?.pickup_no"> · {{ selectedSession.pickup_no }}号桌牌</span>
          </div>
          <div v-if="!loadingMenu && categoryNavItems.length > 1" class="ao-cat-nav">
            <button
              v-for="c in categoryNavItems"
              :key="c"
              type="button"
              class="ao-cat-nav-chip"
              :class="{ hot: c === '热门加菜' }"
              @click="scrollToCategory(c)"
            >{{ c }}</button>
          </div>
          <div v-if="loadingMenu" class="ao-empty">菜单加载中…</div>
          <div v-else class="ao-menu">
            <div v-if="hotDishes.length" id="ao-cat-热门加菜" class="ao-cat">
              <div class="ao-cat-title ao-cat-title-hot">🔥 热门加菜</div>
              <button
                v-for="dish in hotDishes"
                :key="'hot-' + dish.id"
                type="button"
                class="ao-dish ao-dish-hot"
                :class="{ disabled: isSoldOut(dish) }"
                :disabled="isSoldOut(dish)"
                @click="onDishClick(dish)"
              >
                <div class="ao-dish-main">
                  <div class="ao-dish-name">{{ dish.name }}</div>
                  <div class="ao-dish-price">¥{{ Number(dish.price || 0).toFixed(2) }}</div>
                </div>
                <div class="ao-qty" v-if="qtyOf(dish.id) > 0" @click.stop>
                  <a-button size="small" shape="circle" @click="decLine(dish.id)">-</a-button>
                  <span>{{ qtyOf(dish.id) }}</span>
                  <a-button size="small" shape="circle" type="primary" :disabled="isSoldOut(dish)" @click="incSimple(dish)">+</a-button>
                </div>
                <span v-else-if="isSoldOut(dish)" class="sold">售罄</span>
                <span v-else class="add-hint">+</span>
              </button>
            </div>
            <div v-for="cat in categories" :key="cat" :id="'ao-cat-' + cat" class="ao-cat">
              <div class="ao-cat-title">{{ cat }}</div>
              <button
                v-for="dish in dishesByCategory(cat)"
                :key="dish.id"
                type="button"
                class="ao-dish"
                :class="{ disabled: isSoldOut(dish) }"
                :disabled="isSoldOut(dish)"
                @click="onDishClick(dish)"
              >
                <div class="ao-dish-main">
                  <div class="ao-dish-name">{{ dish.name }}</div>
                  <div class="ao-dish-price">¥{{ Number(dish.price || 0).toFixed(2) }}</div>
                </div>
                <div class="ao-qty" v-if="qtyOf(dish.id) > 0" @click.stop>
                  <a-button size="small" shape="circle" @click="decLine(dish.id)">-</a-button>
                  <span>{{ qtyOf(dish.id) }}</span>
                  <a-button size="small" shape="circle" type="primary" :disabled="isSoldOut(dish)" @click="incSimple(dish)">+</a-button>
                </div>
                <span v-else-if="isSoldOut(dish)" class="sold">售罄</span>
                <span v-else class="add-hint">+</span>
              </button>
            </div>
          </div>
          <div class="ao-footer">
            <a-button @click="backToTables">重选桌</a-button>
            <a-button type="primary" size="large" :disabled="cartCount === 0" @click="step = 3">
              确认（{{ cartCount }}）
            </a-button>
          </div>
        </div>

        <!-- STEP 3: 确认 -->
        <div v-else-if="step === 3" class="ao-step">
          <div class="ao-step-label">确认加单</div>
          <div class="ao-confirm-card">
            <div class="ao-confirm-table">{{ selectedSession?.table_no || '-' }}号桌
              <span v-if="selectedSession?.pickup_no"> · {{ selectedSession.pickup_no }}号桌牌</span>
            </div>
            <div v-for="(line, idx) in cartLines" :key="idx" class="ao-line">
              <span>{{ line.name }}{{ line.specText ? `（${line.specText}）` : '' }} ×{{ line.qty }}</span>
              <span>¥{{ (line.unitPrice * line.qty).toFixed(2) }}</span>
            </div>
            <div class="ao-total">
              <span class="ao-total-count">共 {{ cartCount }} 件</span>
              <strong class="ao-total-amount">¥{{ cartTotal.toFixed(2) }}</strong>
            </div>
          </div>
          <div class="ao-remark-label">加菜备注</div>
          <div class="ao-remark-row">
            <button
              v-for="tag in quickRemarks"
              :key="tag"
              type="button"
              class="ao-chip"
              :class="{ on: remarkTags.includes(tag) }"
              @click="toggleRemark(tag)"
            >{{ tag }}</button>
            <button type="button" class="ao-chip" :class="{ on: showOtherRemark }" @click="showOtherRemark = !showOtherRemark">其他备注</button>
          </div>
          <a-textarea
            v-if="showOtherRemark"
            v-model:value="otherRemark"
            :rows="2"
            maxlength="64"
            placeholder="其他备注"
            class="ao-other"
          />
          <div v-if="submitError" class="ao-fail">{{ submitError }}</div>
          <div class="ao-footer">
            <a-button @click="step = 2">返回</a-button>
            <a-button type="primary" size="large" :loading="submitting" :disabled="submitting || cartCount === 0" @click="submit">
              {{ paymentMode === 'prepay' ? '生成付款码' : '确认加单' }}
            </a-button>
          </div>
        </div>

        <!-- STEP 4: 顾客付款 -->
        <div v-else class="ao-step">
          <div class="ao-pay-head">
            <div>
              <div class="ao-step-label">请顾客扫码付款</div>
              <div class="ao-pay-sub">{{ selectedSession?.table_no || '-' }}号桌 · ¥{{ cartTotal.toFixed(2) }}</div>
            </div>
            <a-tag color="orange">{{ handoffStatusText }}</a-tag>
          </div>
          <div class="ao-pay-card">
            <img v-if="handoff?.qr_image" class="ao-pay-qr" :src="handoff.qr_image" alt="付款码" />
            <div v-else class="ao-empty compact">{{ handoff?.qr_error || '付款码生成失败，请重试' }}</div>
            <div class="ao-pay-tip">顾客付款成功后，系统会自动通知厨房。</div>
          </div>
          <div v-if="handoffError" class="ao-fail">{{ handoffError }}</div>
          <div class="ao-footer">
            <a-button :disabled="submitting" @click="regenerateHandoff">重新生成</a-button>
            <a-button type="primary" size="large" @click="emit('update:open', false)">先关闭</a-button>
          </div>
        </div>
    </div>

    <!-- Spec picker -->
    <a-modal v-model:open="specOpen" title="选择规格" :footer="null" centered>
      <div v-if="specDish">
        <div v-for="group in specGroups(specDish)" :key="group.name" class="ao-spec-group">
          <div class="ao-cat-title">{{ group.name }}</div>
          <div class="ao-remark-row">
            <button
              v-for="opt in group.options || []"
              :key="opt.name"
              type="button"
              class="ao-chip"
              :class="{ on: specSelections[group.name] === opt.name }"
              @click="specSelections[group.name] = opt.name"
            >{{ opt.name }}{{ opt.price_delta ? ` +¥${opt.price_delta}` : '' }}</button>
          </div>
        </div>
        <a-button type="primary" block size="large" style="margin-top:12px" @click="confirmSpec">加入</a-button>
      </div>
    </a-modal>
  </a-drawer>
</template>

<script setup>
import { computed, ref, onBeforeUnmount, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { createOrder, createPaymentHandoff, getActiveDiningSessions, getMenuItems, getPaymentHandoff } from '../api'

const props = defineProps({
  open: { type: Boolean, default: false },
  /** Preselect from a task card */
  presetTableNo: { type: String, default: '' },
  presetDiningSessionId: { type: [String, Number], default: '' },
  shopId: { type: String, required: true },
})
const emit = defineEmits(['update:open', 'success'])

const step = ref(1)
const loadingSessions = ref(false)
const loadingMenu = ref(false)
const sessions = ref([])
const paymentMode = ref('')
const selectedSessionId = ref('')
const menuItems = ref([])
const cart = ref([]) // { key, dishId, name, qty, unitPrice, specifications, extras, specText }
const submitting = ref(false)
const submitError = ref('')
const requestId = ref('')
const remarkTags = ref([])
const showOtherRemark = ref(false)
const otherRemark = ref('')
const quickRemarks = ['不要香菜', '少辣', '多辣', '不放葱']
const handoff = ref(null)
const handoffOrderId = ref('')
const handoffError = ref('')
const paymentStatusTimer = ref(null)
const paymentStatusInFlight = ref(false)
const paymentPollingActive = ref(false)
const PAYMENT_STATUS_POLL_INTERVAL_MS = 2500

const specOpen = ref(false)
const specDish = ref(null)
const specSelections = ref({})

const selectedSession = computed(() =>
  sessions.value.find((s) => String(s.dining_session_id) === String(selectedSessionId.value)) || null,
)
const categories = computed(() => {
  const set = new Set(menuItems.value.map((d) => d.category || '其他'))
  return Array.from(set)
})
// 热门加菜：商家在菜单管理里给菜品打过标签（招牌/热销等）就代表这道菜是主推的，
// 直接摘出来放最前面，服务员不用再从头翻到对应分类去找。
const hotDishes = computed(() =>
  menuItems.value.filter((d) => Array.isArray(d.tags) && d.tags.length > 0 && !isSoldOut(d)).slice(0, 8),
)
const categoryNavItems = computed(() => (hotDishes.value.length ? ['热门加菜', ...categories.value] : categories.value))
function scrollToCategory(cat) {
  document.getElementById('ao-cat-' + cat)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const cartLines = computed(() => cart.value)
const cartCount = computed(() => cart.value.reduce((n, l) => n + l.qty, 0))
const cartTotal = computed(() => cart.value.reduce((n, l) => n + l.qty * l.unitPrice, 0))
const handoffStatusText = computed(() => {
  const status = handoff.value?.status || ''
  if (status === 'PAID' || handoff.value?.payment_status === 'paid') return '已付款'
  if (status === 'CLAIMED') return '顾客已打开'
  if (status === 'EXPIRED') return '已过期'
  if (status === 'CANCELLED') return '已作废'
  return '待扫码'
})

function dishesByCategory(cat) {
  return menuItems.value.filter((d) => (d.category || '其他') === cat)
}
function isSoldOut(dish) {
  return dish.sold_out === true || dish.available === false || Number(dish.stock || 1) <= 0
}
function qtyOf(dishId) {
  return cart.value.filter((l) => String(l.dishId) === String(dishId)).reduce((n, l) => n + l.qty, 0)
}
function lineKey(dishId, specifications) {
  return `${dishId}:${JSON.stringify(specifications || [])}`
}
function hasRequiredSpecs(dish) {
  const groups = specGroups(dish)
  return groups.some((g) => (g.options || []).length > 0)
}
function specGroups(dish) {
  const raw = dish?.spec_groups
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function resetCart() {
  cart.value = []
  remarkTags.value = []
  showOtherRemark.value = false
  otherRemark.value = ''
  submitError.value = ''
  requestId.value = ''
  handoff.value = null
  handoffOrderId.value = ''
  handoffError.value = ''
  stopHandoffPolling()
}

function selectSession(s) {
  if (selectedSessionId.value && selectedSessionId.value !== s.dining_session_id) {
    resetCart()
  }
  selectedSessionId.value = String(s.dining_session_id)
}

function backToTables() {
  step.value = 1
  resetCart()
}

function onDishClick(dish) {
  if (isSoldOut(dish)) return
  if (hasRequiredSpecs(dish)) {
    specDish.value = dish
    specSelections.value = {}
    const groups = specGroups(dish)
    groups.forEach((g) => {
      if (g.options?.length) specSelections.value[g.name] = g.options[0].name
    })
    specOpen.value = true
    return
  }
  addLine(dish, [], Number(dish.price || 0), '')
}

function confirmSpec() {
  const dish = specDish.value
  if (!dish) return
  const specifications = Object.entries(specSelections.value).map(([group, value]) => ({ group, value }))
  let delta = 0
  const parts = []
  for (const g of specGroups(dish)) {
    const chosen = specSelections.value[g.name]
    const opt = (g.options || []).find((o) => o.name === chosen)
    if (opt) {
      delta += Number(opt.price_delta || 0)
      parts.push(opt.name)
    }
  }
  addLine(dish, specifications, Number(dish.price || 0) + delta, parts.join('/'))
  specOpen.value = false
  specDish.value = null
}

function addLine(dish, specifications, unitPrice, specText) {
  const key = lineKey(dish.id, specifications)
  const existing = cart.value.find((l) => l.key === key)
  if (existing) {
    existing.qty += 1
    cart.value = [...cart.value]
    return
  }
  cart.value = [
    ...cart.value,
    {
      key,
      dishId: dish.id,
      name: dish.name,
      qty: 1,
      unitPrice,
      specifications,
      extras: [],
      specText,
    },
  ]
}

function incSimple(dish) {
  if (hasRequiredSpecs(dish)) {
    onDishClick(dish)
    return
  }
  addLine(dish, [], Number(dish.price || 0), '')
}

function decLine(dishId) {
  const idx = cart.value.findIndex((l) => String(l.dishId) === String(dishId))
  if (idx < 0) return
  const next = [...cart.value]
  next[idx] = { ...next[idx], qty: next[idx].qty - 1 }
  if (next[idx].qty <= 0) next.splice(idx, 1)
  cart.value = next
}

function toggleRemark(tag) {
  if (remarkTags.value.includes(tag)) {
    remarkTags.value = remarkTags.value.filter((t) => t !== tag)
  } else {
    remarkTags.value = [...remarkTags.value, tag]
  }
}

function buildRemark() {
  const parts = [...remarkTags.value]
  if (showOtherRemark.value && otherRemark.value.trim()) parts.push(otherRemark.value.trim())
  return parts.join('；') || undefined
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    const res = await getActiveDiningSessions()
    const data = res?.data?.data || res?.data || {}
    paymentMode.value = data.payment_mode || ''
    sessions.value = Array.isArray(data.sessions) ? data.sessions : []
    if (props.presetDiningSessionId) {
      const hit = sessions.value.find(
        (s) => String(s.dining_session_id) === String(props.presetDiningSessionId),
      )
      if (hit) {
        selectedSessionId.value = String(hit.dining_session_id)
        step.value = 2
      }
    } else if (props.presetTableNo) {
      const hit = sessions.value.find((s) => String(s.table_no) === String(props.presetTableNo))
      if (hit) {
        selectedSessionId.value = String(hit.dining_session_id)
        step.value = 2
      }
    }
  } catch {
    sessions.value = []
    message.error('加载桌台失败')
  } finally {
    loadingSessions.value = false
  }
}

function handoffStatusOf(next) {
  if (next?.payment_status === 'paid') return 'PAID'
  return String(next?.status || '')
}

function isHandoffTerminal(next) {
  return ['PAID', 'EXPIRED', 'CANCELLED'].includes(handoffStatusOf(next))
}

function isHandoffWaiting(next) {
  return ['PENDING_SCAN', 'CLAIMED'].includes(handoffStatusOf(next))
}

function clearPaymentStatusTimer() {
  if (paymentStatusTimer.value) {
    clearTimeout(paymentStatusTimer.value)
    paymentStatusTimer.value = null
  }
}

function shouldPollPaymentHandoff() {
  if (!paymentPollingActive.value || !props.open || step.value !== 4 || !handoffOrderId.value || !handoff.value) return false
  if (typeof document !== 'undefined' && document.hidden) return false
  return isHandoffWaiting(handoff.value)
}

function stopHandoffPolling() {
  paymentPollingActive.value = false
  clearPaymentStatusTimer()
}

function handleHandoffPaid(next) {
  if (next?.status === 'PAID' || next?.payment_status === 'paid') {
    stopHandoffPolling()
    message.success('顾客已付款，厨房已收到')
    emit('update:open', false)
    emit('success')
  }
}

function schedulePaymentStatusCheck() {
  clearPaymentStatusTimer()
  if (!shouldPollPaymentHandoff()) return
  paymentStatusTimer.value = setTimeout(() => {
    paymentStatusTimer.value = null
    void checkPaymentHandoffStatus({ scheduleAfter: true })
  }, PAYMENT_STATUS_POLL_INTERVAL_MS)
}

async function checkPaymentHandoffStatus({ scheduleAfter = true } = {}) {
  if (paymentStatusInFlight.value) return { skipped: true }
  const orderId = handoffOrderId.value
  if (!paymentPollingActive.value || !orderId || !props.open || (typeof document !== 'undefined' && document.hidden)) {
    clearPaymentStatusTimer()
    return { skipped: true }
  }
  paymentStatusInFlight.value = true
  try {
    const res = await getPaymentHandoff(orderId, {
      meta: { fromPolling: true, dedupe: true, dedupeKey: `handoff:${orderId}` },
    })
    const data = res?.data || res
    if (String(handoffOrderId.value) === String(orderId)) {
      handoff.value = { ...(handoff.value || {}), ...(data || {}) }
      handleHandoffPaid(handoff.value)
    }
    return { skipped: false }
  } catch (err) {
    if (!err?.__duplicateSkipped && props.open && step.value === 4) handoffError.value = '付款状态刷新失败'
    return { skipped: false, error: err }
  } finally {
    paymentStatusInFlight.value = false
    if (scheduleAfter) schedulePaymentStatusCheck()
  }
}

function startHandoffPolling() {
  clearPaymentStatusTimer()
  paymentPollingActive.value = true
  void checkPaymentHandoffStatus({ scheduleAfter: true })
}

function onPaymentVisibilityChange() {
  if (document.hidden) {
    clearPaymentStatusTimer()
    return
  }
  if (shouldPollPaymentHandoff()) void checkPaymentHandoffStatus({ scheduleAfter: true })
}

async function openPaymentHandoff(orderId) {
  handoffOrderId.value = String(orderId || '')
  handoffError.value = ''
  submitting.value = true
  try {
    const res = await createPaymentHandoff(orderId)
    const data = res?.data || res
    handoff.value = data
    step.value = 4
    handleHandoffPaid(data)
    startHandoffPolling()
    if (data?.qr_error) handoffError.value = '二维码生成失败，可点击重新生成'
  } catch {
    handoffError.value = '付款码生成失败，请重试'
  } finally {
    submitting.value = false
  }
}

async function regenerateHandoff() {
  if (!handoffOrderId.value || submitting.value) return
  await openPaymentHandoff(handoffOrderId.value)
}

async function loadMenu() {
  loadingMenu.value = true
  try {
    const res = await getMenuItems({ shop: props.shopId })
    const payload = res?.data?.data || res?.data || {}
    const items = payload.items || payload || []
    menuItems.value = Array.isArray(items) ? items : []
  } catch {
    menuItems.value = []
    message.error('菜单加载失败')
  } finally {
    loadingMenu.value = false
  }
}

async function submit() {
  if (!selectedSession.value || cartCount.value === 0 || submitting.value) return
  if (!requestId.value) {
    requestId.value = `ao-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  }
  submitting.value = true
  submitError.value = ''
  try {
    const items = cart.value.map((l) => ({
      dish_id: Number(l.dishId),
      name: l.name,
      price: l.unitPrice,
      qty: l.qty,
      specifications: l.specifications?.length ? l.specifications : undefined,
      extras: l.extras?.length ? l.extras : undefined,
    }))
    const res = await createOrder({
      shop: props.shopId,
      table: selectedSession.value.table_no,
      dining_session_id: Number(selectedSession.value.dining_session_id),
      items,
      total: cartTotal.value,
      remark: buildRemark(),
      request_id: requestId.value,
    })
    if (res?.code === 200) {
      const data = res?.data || {}
      if (data.need_payment === true && data.payment_mode === 'prepay') {
        await openPaymentHandoff(data.order_id || data.id)
        return
      }
      message.success('加单成功，厨房已收到')
      emit('update:open', false)
      emit('success')
    } else {
      submitError.value = res?.msg || '加单失败，请重试'
    }
  } catch {
    submitError.value = '加单失败，请重试'
  } finally {
    submitting.value = false
  }
}

function onOpenChange(v) {
  if (!v) stopHandoffPolling()
  emit('update:open', v)
}

watch(
  () => props.open,
  async (v) => {
    if (!v) return
    step.value = 1
    selectedSessionId.value = ''
    resetCart()
    await loadSessions()
    await loadMenu()
  },
)

onMounted(() => {
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onPaymentVisibilityChange)
  }
})

onBeforeUnmount(() => {
  stopHandoffPolling()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onPaymentVisibilityChange)
  }
})
</script>

<style scoped>
.ao-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.ao-step { padding: 12px 16px 88px; flex: 1; overflow: auto; }
.ao-step-menu { padding-bottom: 96px; }
.ao-step-label { font-size: 15px; font-weight: 700; margin-bottom: 12px; }
.ao-empty { padding: 48px 16px; text-align: center; color: #888; font-size: 14px; }
.ao-empty.compact { padding: 24px 12px; }
.ao-tables { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ao-table-card {
  border: 1px solid #e5e5e5; border-radius: 12px; padding: 14px 12px; background: #fff;
  text-align: left; display: flex; flex-direction: column; gap: 4px; font-size: 13px;
}
.ao-table-card.selected { border-color: #1677ff; background: #e6f4ff; }
.ao-table-card .muted { color: #999; font-size: 12px; }
.ao-table-no { font-size: 19px; font-weight: 800; color: #111; }
.ao-context { font-size: 13px; color: #666; margin-bottom: 8px; }
.ao-cat-nav {
  display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 4px;
  position: sticky; top: 0; background: #fff; z-index: 1;
}
.ao-cat-nav-chip {
  flex: 0 0 auto; border: 1px solid #e5e5e5; border-radius: 999px; padding: 6px 14px;
  font-size: 13px; font-weight: 600; color: #444; background: #fff; white-space: nowrap;
}
.ao-cat-nav-chip.hot { border-color: #f59e0b; color: #b45309; background: #fffbeb; }
.ao-cat-title { font-size: 13px; font-weight: 700; color: #666; margin: 10px 0 4px; }
.ao-cat-title-hot { color: #b45309; }
.ao-dish {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0; border: 0; border-bottom: 1px solid #f0f0f0; background: transparent; text-align: left;
}
.ao-dish.disabled { opacity: 0.45; }
.ao-dish-hot { background: #fffbeb; padding-left: 8px; padding-right: 8px; border-radius: 8px; border-bottom-color: transparent; }
.ao-dish-name { font-size: 16px; font-weight: 700; color: #111; }
.ao-dish-price { font-size: 13px; color: #07c160; font-weight: 700; margin-top: 2px; }
.ao-qty { display: flex; align-items: center; gap: 8px; }
.sold { color: #999; font-size: 12px; }
.add-hint { font-size: 22px; color: #1677ff; font-weight: 700; padding: 0 8px; }
.ao-footer {
  position: absolute; left: 0; right: 0; bottom: 0; display: flex; gap: 10px;
  padding: 12px 16px 20px; background: #fff; border-top: 1px solid #eee;
}
.ao-footer .ant-btn-primary { flex: 1; }
.ao-next { margin-top: 16px; }
.ao-confirm-card { background: #fafafa; border-radius: 12px; padding: 12px; }
.ao-confirm-table { font-size: 12px; color: #888; margin-bottom: 4px; }
.ao-line { display: flex; justify-content: space-between; font-size: 14px; padding: 6px 0; }
.ao-total { display: flex; justify-content: flex-end; align-items: baseline; gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e5e5e5; }
.ao-total-count { font-size: 12px; color: #888; }
.ao-total-amount { font-size: 24px; font-weight: 800; color: #111; }
.ao-remark-label { font-size: 12px; color: #888; margin: 14px 0 8px; }
.ao-remark-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 12px; }
.ao-chip {
  border: 1px solid #ddd; border-radius: 16px; padding: 6px 12px; background: #fff; font-size: 13px;
}
.ao-chip.on { border-color: #1677ff; color: #1677ff; background: #e6f4ff; }
.ao-other { margin-bottom: 8px; }
.ao-fail { color: #cf1322; font-size: 13px; margin-bottom: 8px; }
.ao-spec-group { margin-bottom: 10px; }
.ao-pay-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.ao-pay-sub { color: #666; font-size: 13px; }
.ao-pay-card { background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 16px; text-align: center; }
.ao-pay-qr { width: 220px; height: 220px; max-width: 74vw; object-fit: contain; }
.ao-pay-tip { color: #666; font-size: 13px; margin-top: 10px; }
</style>
