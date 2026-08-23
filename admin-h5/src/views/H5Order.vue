<template>
  <div class="h5-wrap">
    <!-- 顶栏 -->
    <div class="top-bar animate-in">
      <div class="shop-name">{{ shop.name || '加载中…' }}</div>
      <div class="shop-meta">
        <span class="status-dot" :class="shop.is_open ? 'open' : 'closed'"></span>
        {{ shop.is_open ? '营业中' : '休息中' }}
        <span v-if="tableNo" class="table-tag">桌号 {{ tableNo }}</span>
      </div>
    </div>

    <!-- 关闭提示 -->
    <div v-if="shop.name && !shop.is_open" class="closed-banner">
      门店暂时休息，欢迎稍后再来
    </div>

    <!-- 主体：分类 + 菜品 -->
    <div class="menu-body animate-in animate-in--delay-1" v-if="!showCart && !showSuccess">
      <!-- 分类横栏 -->
      <div class="cat-bar" ref="catBarRef">
        <div
          v-for="cat in categories"
          :key="cat"
          class="cat-item tap-shrink"
          :class="{ active: activeCat === cat }"
          @click="scrollToCategory(cat)"
        >{{ cat }}</div>
      </div>

      <!-- 菜品列表 -->
      <div class="dish-list" ref="dishListRef" @scroll="onDishScroll">
        <div v-if="!shop.name && categories.length === 0" class="menu-loading">
          <div class="menu-loading-spinner"></div>
          <p>菜单加载中，马上就好…</p>
        </div>
        <div v-else-if="categories.length === 0" class="menu-empty">
          <span class="menu-empty-icon">🍽️</span>
          <p>菜单还没配置好</p>
          <span>请稍后刷新，或联系商家确认</span>
        </div>
        <template v-else>
          <div v-for="cat in categories" :key="cat" :ref="el => catSectionRefs[cat] = el">
            <div class="cat-section-title">{{ cat }}</div>
            <div
              v-for="dish in dishesByCategory[cat]"
              :key="dish.id"
              class="dish-row"
              :class="{ unavailable: !dish.available }"
            >
              <img v-if="dish.image || dish.image_url" :src="dish.image || dish.image_url" class="dish-img" />
              <div class="dish-img dish-img-placeholder" v-else>
                <span>{{ dish.name?.charAt(0) }}</span>
              </div>
              <div class="dish-info">
                <div class="dish-name">{{ dish.name }}</div>
                <div class="dish-desc" v-if="dish.description">{{ dish.description }}</div>
                <div class="dish-price">¥{{ Number(dish.price).toFixed(2) }}</div>
              </div>
              <div class="dish-ctrl">
                <template v-if="dish.available && !dish.sold_out">
                  <button v-if="cartQty(dish.id) > 0" class="btn-minus tap-shrink" @click="removeFromCart(dish)">－</button>
                  <span v-if="cartQty(dish.id) > 0" class="qty-num">{{ cartQty(dish.id) }}</span>
                  <button class="btn-plus tap-shrink" @click="addToCart(dish)">＋</button>
                </template>
                <span v-else class="sold-out">已售罄</span>
              </div>
            </div>
          </div>
          <div style="height:80px"></div>
        </template>
      </div>
    </div>

    <!-- 购物车底栏 -->
    <div class="cart-bar tap-shrink" v-if="cartCount > 0 && !showCart && !showSuccess" @click="showCart = true">
      <div class="cart-icon-wrap">
        <span class="cart-icon">🛒</span>
        <span class="cart-badge">{{ cartCount }}</span>
      </div>
      <div class="cart-total">¥{{ cartTotal.toFixed(2) }}</div>
      <button class="checkout-btn tap-shrink" @click.stop="goCheckout">去下单</button>
    </div>

    <!-- 购物车详情页 -->
    <div class="cart-detail" v-if="showCart && !showSuccess">
      <div class="cart-header">
        <span class="cart-title">已选商品</span>
        <span class="cart-clear tap-shrink" @click="clearCart">清空</span>
      </div>
      <div v-if="cartItems.length === 0" class="cart-empty-state">
        <span class="cart-empty-icon">🛒</span>
        <p>购物车是空的</p>
        <span>回去挑几道喜欢的菜吧</span>
      </div>
      <div class="cart-items" v-else>
        <div v-for="item in cartItems" :key="item.id" class="cart-item-row">
          <span class="ci-name">{{ item.name }}</span>
          <div class="ci-ctrl">
            <button class="btn-minus tap-shrink" @click="removeFromCart(item)">－</button>
            <span class="qty-num">{{ item.qty }}</span>
            <button class="btn-plus tap-shrink" @click="addToCartById(item)">＋</button>
          </div>
          <span class="ci-price">¥{{ (item.price * item.qty).toFixed(2) }}</span>
        </div>
      </div>
      <div class="cart-remark">
        <input v-model="remark" placeholder="备注（口味、忌口等）" class="remark-input" maxlength="50" />
      </div>
      <div class="cart-summary">
        合计 <strong>¥{{ cartTotal.toFixed(2) }}</strong>
      </div>
      <button class="submit-btn tap-shrink" :disabled="submitting" @click="submitOrder">
        {{ submitting ? '提交中…' : '提交订单' }}
      </button>
      <div class="back-link tap-shrink" @click="showCart = false">← 继续点餐</div>
    </div>

    <!-- 成功页 -->
    <div class="success-page" v-if="showSuccess">
      <div class="success-icon">✓</div>
      <div class="success-title">{{ successTitle }}</div>
      <div class="success-meta">{{ tableNo ? `桌号 ${tableNo} · ` : '' }}共 {{ successCount }} 份 · ¥{{ successTotal }}</div>
      <div class="success-hint">{{ successHint }}</div>
      <div class="pay-hint">
        <span class="pay-hint-icon">💳</span>
        {{ payHint }}
      </div>

      <div class="status-card">
        <div class="status-label">订单状态</div>
        <div class="status-val" :class="`status-${orderStatus}`">{{ statusLabel }}</div>
      </div>

      <button v-if="orderStatus === 'pending_payment'" class="reorder-btn tap-shrink" :disabled="paying" @click="payCurrentOrder()">{{ paying ? '正在拉起支付…' : '继续支付' }}</button>
      <button v-else class="reorder-btn tap-shrink" @click="reorder">再点一单</button>
    </div>

    <!-- 错误提示 -->
    <div class="toast" v-if="toast" @click="toast = ''">{{ toast }}</div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { formatOrderStatusText } from '../utils/orderStatusText'

const route = useRoute()
const shopId = computed(() => route.params.shopId)
const tableNo = computed(() => route.query.table || '')

const shop = ref({ name: '', is_open: true })
const dishes = ref([])
const cart = reactive({})
const remark = ref('')
const showCart = ref(false)
const showSuccess = ref(false)
const submitting = ref(false)
const paying = ref(false)
const toast = ref('')
const orderId = ref('')
const orderStatus = ref('')
const orderStatusText = ref('')
const successCount = ref(0)
const successTotal = ref('0.00')

const catBarRef = ref(null)
const dishListRef = ref(null)
const catSectionRefs = reactive({})

let pollTimer = null

const api = axios.create({ baseURL: '/api' })
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('customer_token') || localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

const showToast = (msg) => {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, 2500)
}

const categories = computed(() => {
  const seen = new Set()
  dishes.value.forEach(d => { if (d.category) seen.add(d.category) })
  return [...seen]
})

const dishesByCategory = computed(() => {
  const map = {}
  categories.value.forEach(c => { map[c] = dishes.value.filter(d => d.category === c) })
  return map
})

const activeCat = ref('')

const cartItems = computed(() =>
  Object.values(cart).filter(i => i.qty > 0).sort((a, b) => a.name.localeCompare(b.name))
)
const cartCount = computed(() => cartItems.value.reduce((s, i) => s + i.qty, 0))
const cartTotal = computed(() => cartItems.value.reduce((s, i) => s + i.price * i.qty, 0))
const cartQty = (id) => cart[id]?.qty || 0

const successTitle = computed(() => orderStatus.value === 'pending_payment' ? '待支付' : '下单成功')
const successHint = computed(() => orderStatus.value === 'pending_payment' ? '请完成微信支付，支付成功后厨房才会收到订单' : '商家正在处理，请稍候…')
const payHint = computed(() => orderStatus.value === 'pending_payment' ? '微信支付未完成，请点击继续支付' : '已完成支付，订单已进入商家接单流程')

const statusLabel = computed(() => formatOrderStatusText(orderStatus.value, orderStatusText.value))

function addToCart(dish) {
  if (!cart[dish.id]) cart[dish.id] = { id: dish.id, name: dish.name, price: Number(dish.price), qty: 0 }
  cart[dish.id].qty++
}
function addToCartById(item) {
  if (cart[item.id]) cart[item.id].qty++
}
function removeFromCart(item) {
  if (cart[item.id] && cart[item.id].qty > 0) cart[item.id].qty--
}
function clearCart() {
  Object.keys(cart).forEach(k => delete cart[k])
  showCart.value = false
}

function scrollToCategory(cat) {
  activeCat.value = cat
  nextTick(() => {
    const el = catSectionRefs[cat]
    if (el && dishListRef.value) {
      dishListRef.value.scrollTo({ top: el.offsetTop - 8, behavior: 'smooth' })
    }
  })
}

function onDishScroll() {
  const listEl = dishListRef.value
  if (!listEl) return
  const scrollTop = listEl.scrollTop
  for (const cat of [...categories.value].reverse()) {
    const el = catSectionRefs[cat]
    if (el && el.offsetTop <= scrollTop + 60) {
      activeCat.value = cat
      break
    }
  }
}

function goCheckout() {
  if (cartCount.value === 0) return
  showCart.value = true
}

async function submitOrder() {
  if (submitting.value || cartCount.value === 0) return
  submitting.value = true
  try {
    const items = cartItems.value.map(i => ({
      dish_id: i.id,
      name: i.name,
      price: i.price,
      qty: i.qty,
    }))
    const res = await api.post('/v1/orders', {
      shop: shopId.value,
      table: tableNo.value || '',
      items,
      total: cartTotal.value,
      remark: remark.value || null,
      source: 'h5',
    })
    if (res.data?.code === 200) {
      const data = res.data.data
      orderId.value = String(data.id)
      orderStatus.value = 'pending_payment'
      orderStatusText.value = formatOrderStatusText('pending_payment', data.status_text)
      successCount.value = cartCount.value
      successTotal.value = cartTotal.value.toFixed(2)
      showCart.value = false
      showSuccess.value = true
      Object.keys(cart).forEach(k => delete cart[k])
      remark.value = ''
      startPoll()
      await payCurrentOrder(data.id)
    } else {
      showToast(res.data?.msg || '下单失败，请重试')
    }
  } catch (e) {
    showToast(e?.response?.data?.msg || '网络异常，请重试')
  } finally {
    submitting.value = false
  }
}

const normalizePayParams = (params = {}) => ({
  timeStamp: String(params.timeStamp || params.timestamp || ''),
  nonceStr: params.nonceStr || params.nonce_str || '',
  package: params.package || '',
  signType: params.signType || params.sign_type || 'RSA',
  paySign: params.paySign || params.pay_sign || '',
})

const requestWxPayment = (params) => new Promise((resolve, reject) => {
  const payParams = normalizePayParams(params)
  const fail = (err) => {
    const msg = err?.errMsg || err?.message || ''
    if (msg.includes('cancel')) reject(new Error('支付已取消'))
    else reject(new Error(msg || '微信支付失败'))
  }

  if (window?.uni?.requestPayment) {
    window.uni.requestPayment({ provider: 'wxpay', ...payParams, success: resolve, fail })
    return
  }
  if (window?.wx?.requestPayment) {
    window.wx.requestPayment({ ...payParams, success: resolve, fail })
    return
  }
  if (window?.WeixinJSBridge?.invoke) {
    window.WeixinJSBridge.invoke('getBrandWCPayRequest', payParams, (res) => {
      const msg = res?.err_msg || ''
      if (msg.includes(':ok')) resolve(res)
      else if (msg.includes(':cancel')) reject(new Error('支付已取消'))
      else reject(new Error(msg || '微信支付失败'))
    })
    return
  }

  reject(new Error('请在微信小程序或微信内打开后完成支付'))
})

async function payCurrentOrder(targetOrderId = orderId.value) {
  if (!targetOrderId || paying.value) return
  paying.value = true
  try {
    const payRes = await api.post(`/v1/orders/${targetOrderId}/pay`, { use_balance: false })
    if (payRes.data?.code !== 200) throw new Error(payRes.data?.msg || '创建支付单失败')
    const payData = payRes.data?.data || {}
    if (payData.free) {
      orderStatus.value = payData.status || 'pending'
      orderStatusText.value = formatOrderStatusText(orderStatus.value, payData.status_text)
      showToast('支付成功')
      return
    }
    if (!payData.pay_params) throw new Error('支付参数缺失，请联系商家')
    await requestWxPayment(payData.pay_params)
    showToast('支付已提交，正在确认订单')
    setTimeout(refreshOrderStatus, 1200)
  } catch (e) {
    showToast(e?.response?.data?.msg || e?.message || '支付未完成，请稍后重试')
  } finally {
    paying.value = false
  }
}

async function refreshOrderStatus() {
  if (!orderId.value) return
  try {
    const res = await api.get('/v1/orders/my', { params: { order_id: orderId.value } })
    if (res.data?.code === 200) {
      orderStatus.value = res.data.data.status
      orderStatusText.value = res.data.data.status_text || ''
    }
  } catch {}
}

function startPoll() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!orderId.value) return
    try {
      const res = await api.get('/v1/orders/my', { params: { order_id: orderId.value } })
      if (res.data?.code === 200) {
        orderStatus.value = res.data.data.status
        orderStatusText.value = res.data.data.status_text || ''
        if (['settled', 'cancelled'].includes(orderStatus.value)) clearInterval(pollTimer)
      }
    } catch {}
  }, 8000)
}

function reorder() {
  showSuccess.value = false
  orderId.value = ''
  orderStatus.value = ''
  orderStatusText.value = ''
  if (pollTimer) clearInterval(pollTimer)
}

async function loadShop() {
  try {
    const res = await api.get('/v1/shop/info', { params: { shop: shopId.value } })
    if (res.data?.code === 200) shop.value = res.data.data
  } catch {}
}

async function loadMenu() {
  try {
    const res = await api.get('/v1/menu/items', { params: { shop: shopId.value } })
    const raw = res.data?.data || res.data || []
    dishes.value = Array.isArray(raw) ? raw.filter(d => d.available !== false || !d.available) : []
    if (categories.value.length) activeCat.value = categories.value[0]
  } catch {}
}

onMounted(() => {
  loadShop()
  loadMenu()
})
onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }

/* ── 进场动效错落延迟（基础 .animate-in/.tap-shrink 用全局 global.scss 定义） ── */
.animate-in--delay-1 { animation-delay: .06s; }

.h5-wrap {
  min-height: 100vh;
  background: var(--bg-page);
  font-family: -apple-system, 'PingFang SC', sans-serif;
  max-width: 480px;
  margin: 0 auto;
  color: var(--text-1);
}

/* 顶栏 */
.top-bar {
  background: linear-gradient(135deg, var(--brand) 0%, var(--brand-dark) 100%);
  padding: 48px 16px 16px;
  color: #fff;
}
.shop-name { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.shop-meta { font-size: 13px; color: rgba(255,255,255,.85); display: flex; align-items: center; gap: 8px; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.status-dot.open { background: #fff; }
.status-dot.closed { background: rgba(255,255,255,.4); }
.table-tag { background: rgba(255,255,255,.2); border-radius: 20px; padding: 2px 10px; font-size: 12px; }

.closed-banner { background: #fef3c7; color: #92400e; text-align: center; padding: 10px; font-size: 13px; }

/* 菜单主体 */
.menu-body { display: flex; flex-direction: column; height: calc(100vh - 120px); }

.cat-bar {
  display: flex;
  gap: 0;
  background: var(--bg-card);
  overflow-x: auto;
  padding: 0 8px;
  border-bottom: 0.5px solid var(--border);
  flex-shrink: 0;
  scrollbar-width: none;
}
.cat-bar::-webkit-scrollbar { display: none; }
.cat-item {
  white-space: nowrap;
  padding: 10px 14px;
  font-size: 13px;
  color: var(--text-2);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color .15s, border-color .15s;
}
.cat-item.active { color: var(--brand); font-weight: 600; border-bottom-color: var(--brand); }

.dish-list { flex: 1; overflow-y: auto; padding: 0 0 16px; }

.cat-section-title {
  padding: 12px 16px 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-3);
  background: var(--bg-page);
  letter-spacing: .5px;
}

/* 菜单加载中 / 菜单为空 */
.menu-loading, .menu-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 72px 24px;
  color: var(--text-2);
  font-size: 14px;
  text-align: center;
}
.menu-loading p, .menu-empty p { margin: 4px 0 0; font-weight: 600; color: var(--text-1); }
.menu-empty span { font-size: 12px; color: var(--text-3); }
.menu-empty-icon { font-size: 32px; }
.menu-loading-spinner {
  width: 28px; height: 28px;
  border-radius: 50%;
  border: 3px solid var(--brand-light);
  border-top-color: var(--brand);
  animation: h5-spin .8s linear infinite;
}
@keyframes h5-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .menu-loading-spinner { animation-duration: 1.6s; }
}

.dish-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-card);
  border-bottom: 0.5px solid var(--border);
}
.dish-row.unavailable { opacity: .5; }

.dish-img { width: 64px; height: 64px; border-radius: var(--radius-card); object-fit: cover; flex-shrink: 0; }
.dish-img-placeholder {
  background: var(--bg-page);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: var(--text-3);
  font-weight: 700;
}

.dish-info { flex: 1; min-width: 0; }
.dish-name { font-size: 14px; font-weight: 600; color: var(--text-1); margin-bottom: 3px; }
.dish-desc { font-size: 12px; color: var(--text-3); margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-price { font-size: 15px; font-weight: 700; color: var(--danger); }

.dish-ctrl { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.btn-plus, .btn-minus {
  width: 28px; height: 28px; border-radius: 50%;
  border: none; font-size: 18px; line-height: 1;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; flex-shrink: 0;
}
.btn-plus { background: var(--brand); color: #fff; }
.btn-minus { background: var(--border); color: var(--text-2); }
.qty-num { font-size: 15px; font-weight: 700; color: var(--text-1); min-width: 18px; text-align: center; }
.sold-out { font-size: 12px; color: var(--text-3); }

/* 购物车底栏 */
.cart-bar {
  position: fixed;
  bottom: 0; left: 50%; transform: translateX(-50%);
  width: 100%; max-width: 480px;
  background: #1f2937;
  border-radius: var(--radius-card) var(--radius-card) 0 0;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  z-index: 100;
}
.cart-icon-wrap { position: relative; }
.cart-icon { font-size: 28px; }
.cart-badge {
  position: absolute; top: -6px; right: -8px;
  background: var(--danger); color: #fff;
  font-size: 10px; font-weight: 700;
  width: 18px; height: 18px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.cart-total { flex: 1; font-size: 18px; font-weight: 700; color: #fff; }
.checkout-btn {
  background: var(--brand); color: #fff;
  border: none; border-radius: 20px;
  padding: 8px 20px; font-size: 14px; font-weight: 700;
  cursor: pointer; flex-shrink: 0;
}

/* 购物车详情 */
.cart-detail { background: var(--bg-card); min-height: calc(100vh - 100px); padding: 0 0 80px; }
.cart-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 0.5px solid var(--border); }
.cart-title { font-size: 16px; font-weight: 700; color: var(--text-1); }
.cart-clear { font-size: 13px; color: var(--text-3); cursor: pointer; }

.cart-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 56px 24px;
  color: var(--text-2);
  font-size: 14px;
  text-align: center;
}
.cart-empty-state p { margin: 4px 0 0; font-weight: 600; color: var(--text-1); }
.cart-empty-state span { font-size: 12px; color: var(--text-3); }
.cart-empty-icon { font-size: 32px; }

.cart-items { padding: 0 16px; }
.cart-item-row { display: flex; align-items: center; gap: 10px; padding: 12px 0; border-bottom: 0.5px solid var(--border); }
.ci-name { flex: 1; font-size: 14px; color: var(--text-1); }
.ci-ctrl { display: flex; align-items: center; gap: 8px; }
.ci-price { font-size: 14px; font-weight: 600; color: var(--text-1); min-width: 56px; text-align: right; }

.cart-remark { padding: 12px 16px; }
.remark-input {
  width: 100%; height: 40px; border: 0.5px solid var(--border);
  border-radius: 8px; padding: 0 12px; font-size: 14px; outline: none;
  background: var(--bg-card); color: var(--text-1);
}
.remark-input:focus { border-color: var(--brand); }

.cart-summary { padding: 12px 16px; font-size: 15px; color: var(--text-2); text-align: right; }
.cart-summary strong { font-size: 20px; color: var(--danger); }

.submit-btn {
  display: block; width: calc(100% - 32px); margin: 0 16px;
  height: 48px; background: var(--brand); color: #fff;
  border: none; border-radius: var(--radius-card); font-size: 16px; font-weight: 700;
  cursor: pointer;
}
.submit-btn:disabled { opacity: .6; }
.back-link { text-align: center; padding: 16px; font-size: 14px; color: var(--text-3); cursor: pointer; }

/* 成功页 */
.success-page {
  display: flex; flex-direction: column; align-items: center;
  padding: 60px 24px 40px;
  min-height: calc(100vh - 100px);
}
.success-icon {
  width: 72px; height: 72px; border-radius: 50%;
  background: var(--brand); color: #fff;
  font-size: 36px; display: flex; align-items: center; justify-content: center;
  margin-bottom: 16px;
}
.success-title { font-size: 22px; font-weight: 700; color: var(--text-1); margin-bottom: 8px; }
.success-meta { font-size: 14px; color: var(--text-2); margin-bottom: 6px; }
.success-hint { font-size: 13px; color: var(--text-3); margin-bottom: 12px; }
.pay-hint {
  font-size: 13px; color: #92400e;
  background: #fef3c7; border-radius: var(--radius-card);
  padding: 10px 14px; margin-bottom: 24px;
  display: flex; align-items: center; gap: 8px; width: 100%;
}
.pay-hint-icon { font-size: 18px; flex-shrink: 0; }

.status-card {
  width: 100%; background: var(--bg-page);
  border-radius: var(--radius-card); padding: 16px;
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 32px;
}
.status-label { font-size: 14px; color: var(--text-2); }
.status-val { font-size: 15px; font-weight: 700; }
.status-val.status-pending { color: var(--warning); }
.status-val.status-preparing { color: #2563eb; }
.status-val.status-done { color: var(--brand); }
.status-val.status-settled { color: var(--text-3); }
.status-val.status-cancelled { color: var(--danger); }

.reorder-btn {
  width: 100%; height: 48px;
  background: var(--brand); color: #fff;
  border: none; border-radius: var(--radius-card);
  font-size: 16px; font-weight: 700; cursor: pointer;
}

/* toast */
.toast {
  position: fixed; bottom: 100px; left: 50%; transform: translateX(-50%);
  background: rgba(0,0,0,.75); color: #fff;
  padding: 10px 20px; border-radius: 20px; font-size: 13px;
  z-index: 999; white-space: nowrap;
}
</style>

