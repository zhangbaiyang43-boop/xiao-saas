<template>
  <div class="order-page">
    <!-- 店铺头部 -->
    <header class="shop-header animate-in">
      <div class="shop-info">
        <h1>{{ shopName }}</h1>
        <p>营业中 · 桌号 {{ tableNo }} · 人均 ¥{{ avgPrice }}</p>
      </div>
      <div v-if="todayActivity" class="activity-bar">
        <van-icon name="fire-o" />
        今日活动：{{ todayActivity }}
      </div>
    </header>

    <!-- 主体：左边分类 + 右边菜品 -->
    <div class="menu-body animate-in animate-in--delay-1">
      <nav class="category-nav">
        <button
          v-for="cat in categories"
          :key="cat"
          class="cat-item tap-shrink"
          :class="{ active: activeCategory === cat }"
          type="button"
          @click="switchCategory(cat)"
        >
          {{ cat }}
        </button>
      </nav>

      <section class="dish-list" ref="dishListRef" @scroll="onDishScroll">
        <div v-for="cat in categories" :key="cat" :data-cat="cat">
          <p class="cat-title">{{ cat }}</p>
          <div
            v-for="dish in dishesByCategory(cat)"
            :key="dish.id"
            class="dish-item"
          >
            <div class="dish-emoji">{{ dish.emoji }}</div>
            <div class="dish-info">
              <strong>{{ dish.name }}</strong>
              <span>{{ dish.desc }}</span>
              <b>¥{{ dish.price }}</b>
            </div>
            <div class="dish-counter">
              <button
                v-if="cartCount(dish.id) > 0"
                class="counter-btn minus tap-shrink"
                type="button"
                @click="removeFromCart(dish)"
              >
                <van-icon name="minus" />
              </button>
              <span v-if="cartCount(dish.id) > 0" class="counter-num">
                {{ cartCount(dish.id) }}
              </span>
              <button
                class="counter-btn plus tap-shrink"
                type="button"
                @click="addToCart(dish)"
              >
                <van-icon name="plus" />
              </button>
            </div>
          </div>
        </div>
        <div class="dish-list-bottom-pad" />
      </section>
    </div>

    <!-- 底部购物车栏 -->
    <footer class="cart-bar animate-in animate-in--delay-2" :class="{ 'has-items': totalCount > 0 }">
      <button class="cart-icon-wrap tap-shrink" type="button" @click="totalCount > 0 && (showCartDetail = true)">
        <van-icon name="shopping-cart-o" size="26" />
        <span v-if="totalCount > 0" class="cart-badge">{{ totalCount }}</span>
      </button>
      <div class="cart-price">
        <template v-if="totalCount > 0">
          <b>¥{{ totalPrice }}</b>
          <span>下单后可领优惠券</span>
        </template>
        <template v-else>
          <span class="cart-empty-hint">请选择商品</span>
        </template>
      </div>
      <button
        class="checkout-btn tap-shrink"
        type="button"
        :disabled="totalCount === 0"
        @click="goCheckout"
      >
        去结算
      </button>
    </footer>

    <!-- 购物车详情 -->
    <van-popup v-model:show="showCartDetail" round position="bottom">
      <div class="cart-sheet">
        <div class="cart-sheet-header">
          <h3>已选商品</h3>
          <button type="button" class="clear-btn tap-shrink" @click="clearCart">清空</button>
        </div>
        <div class="cart-items">
          <div v-for="item in cartItems" :key="item.id" class="cart-row">
            <span class="cart-row-emoji">{{ item.emoji }}</span>
            <span class="cart-row-name">{{ item.name }}</span>
            <div class="cart-row-right">
              <button class="counter-btn minus tap-shrink" type="button" @click="removeFromCart(item)">
                <van-icon name="minus" />
              </button>
              <span class="counter-num">{{ item.qty }}</span>
              <button class="counter-btn plus tap-shrink" type="button" @click="addToCart(item)">
                <van-icon name="plus" />
              </button>
              <b class="cart-row-price">¥{{ (item.price * item.qty).toFixed(0) }}</b>
            </div>
          </div>
        </div>
        <div class="cart-sheet-total">
          <span>合计</span>
          <b>¥{{ totalPrice }}</b>
        </div>
        <van-button class="checkout-btn-full" type="primary" block round size="large" @click="goCheckout">
          去结算 · ¥{{ totalPrice }}
        </van-button>
      </div>
    </van-popup>

    <!-- 手机号弹层（结算前） -->
    <van-popup v-model:show="showPhoneSheet" round position="bottom" :close-on-click-overlay="false">
      <div class="phone-sheet">
        <div class="phone-sheet-top">
          <h3>领取下单优惠券</h3>
          <p>留个手机号，下单后系统自动把券发到您手机，下次来直接用。</p>
        </div>
        <van-field
          v-model="phone"
          type="tel"
          class="phone-field"
          placeholder="输入手机号（选填）"
          maxlength="11"
          clearable
        />
        <van-button type="primary" block round size="large" :loading="ordering" class="phone-submit-btn" @click="submitOrder">
          {{ phone ? '领券并下单' : '直接下单（不领券）' }}
        </van-button>
        <button type="button" class="phone-skip-btn tap-shrink" @click="showPhoneSheet = false">返回修改</button>
      </div>
    </van-popup>

    <!-- 下单成功 -->
    <van-popup v-model:show="showSuccess" :close-on-click-overlay="false" round>
      <div class="success-sheet">
        <div class="success-anim">
          <svg viewBox="0 0 80 80" class="success-svg">
            <circle class="svg-circle" cx="40" cy="40" r="34" />
            <polyline class="svg-check" points="22,41 33,52 58,27" />
          </svg>
        </div>
        <h2>下单成功</h2>
        <p class="success-table">桌号 {{ tableNo }}，厨房已收到</p>

        <div v-if="earnedCoupon" class="coupon-reward">
          <div class="coupon-reward-tag">🎉 已自动领取优惠券</div>
          <div class="coupon-reward-amount">{{ earnedCoupon.amount }}</div>
          <div class="coupon-reward-desc">满 ¥{{ earnedCoupon.threshold }} 可用 · {{ earnedCoupon.validDays }} 天内有效</div>
          <div class="coupon-reward-name">{{ earnedCoupon.name }}</div>
        </div>
        <div v-else-if="phone" class="coupon-reward no-coupon">
          <p>暂无可用优惠券，下次消费留意系统推送。</p>
        </div>

        <van-button type="primary" block round @click="resetOrder">继续点餐</van-button>
      </div>
    </van-popup>

    <!-- 菜单加载中 -->
    <div v-if="loadingMenu" class="loading-mask">
      <van-loading type="spinner" color="var(--brand)" size="36" />
      <p>菜单加载中，马上就好…</p>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { showFailToast } from 'vant'
import { getMenuItems, createOrder, createWxPayOrder, getShopInfo } from '../api'

const route = useRoute()
const tableNo = computed(() => route.query.table || 'A01')
const shopId = computed(() => route.query.shop || '')

const shopName = ref('小碗菜')
const avgPrice = ref(18)
const todayActivity = ref('')
const loadingMenu = ref(false)
const ordering = ref(false)
const showCartDetail = ref(false)
const showPhoneSheet = ref(false)
const showSuccess = ref(false)
const earnedCoupon = ref(null)
const activeCategory = ref('')
const dishListRef = ref(null)
const phone = ref('')

const allDishes = ref([])

const categories = computed(() => {
  const cats = []
  for (const d of allDishes.value) {
    if (!cats.includes(d.category)) cats.push(d.category)
  }
  return cats
})

function dishesByCategory(cat) {
  return allDishes.value.filter((d) => d.category === cat && d.available !== false)
}

// ── 购物车 ──────────────────────────────────────────
const cart = ref({})

function cartCount(id) {
  return cart.value[id] || 0
}

function addToCart(dish) {
  cart.value = { ...cart.value, [dish.id]: (cart.value[dish.id] || 0) + 1 }
}

function removeFromCart(dish) {
  const cur = cart.value[dish.id] || 0
  if (cur <= 1) {
    const next = { ...cart.value }
    delete next[dish.id]
    cart.value = next
  } else {
    cart.value = { ...cart.value, [dish.id]: cur - 1 }
  }
}

function clearCart() {
  cart.value = {}
  showCartDetail.value = false
}

const cartItems = computed(() =>
  allDishes.value
    .filter((d) => cart.value[d.id] > 0)
    .map((d) => ({ ...d, qty: cart.value[d.id] }))
)

const totalCount = computed(() => Object.values(cart.value).reduce((s, n) => s + n, 0))
const totalPrice = computed(() =>
  cartItems.value.reduce((s, item) => s + item.price * item.qty, 0).toFixed(0)
)

// ── 分类联动 ────────────────────────────────────────
function switchCategory(cat) {
  activeCategory.value = cat
  const el = dishListRef.value?.querySelector(`[data-cat="${cat}"]`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onDishScroll() {
  if (!dishListRef.value) return
  const sections = dishListRef.value.querySelectorAll('[data-cat]')
  const scrollTop = dishListRef.value.scrollTop
  for (let i = sections.length - 1; i >= 0; i--) {
    if (sections[i].offsetTop <= scrollTop + 8) {
      activeCategory.value = sections[i].dataset.cat
      break
    }
  }
}

// ── 结算流程 ────────────────────────────────────────
function goCheckout() {
  if (totalCount.value === 0) return
  showCartDetail.value = false
  showPhoneSheet.value = true
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
  const fail = (err) => reject(new Error(err?.errMsg || err?.message || '微信支付失败'))
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
      else reject(new Error(msg || '微信支付未完成'))
    })
    return
  }
  reject(new Error('请在微信小程序或微信内打开后完成支付'))
})

async function payOrder(orderId) {
  const payRes = await createWxPayOrder(orderId, { use_balance: false })
  const payData = payRes?.data?.data || payRes?.data || {}
  if (payData.free) return
  if (!payData.pay_params) throw new Error(payRes?.data?.msg || '支付参数缺失')
  await requestWxPayment(payData.pay_params)
}

async function submitOrder() {
  ordering.value = true
  try {
    const payload = {
      table: tableNo.value,
      shop: shopId.value,
      phone: phone.value.trim() || null,
      total: Number(totalPrice.value),
      items: cartItems.value.map((item) => ({
        dish_id: item.id,
        name: item.name,
        price: item.price,
        qty: item.qty,
      })),
    }
    const res = await createOrder(payload)
    const data = res?.data?.data || res?.data || {}
    if (data.id) {
      await payOrder(data.id)
    }
    earnedCoupon.value = data.coupon
      ? {
          amount: data.coupon.value ?? data.coupon.amount,
          threshold: data.coupon.min_amount ?? data.coupon.threshold,
          validDays: data.coupon.valid_days,
          name: data.coupon.name || '下单券',
        }
      : null
    showPhoneSheet.value = false
    showSuccess.value = true
  } catch {
    showFailToast('下单失败，请告知服务员')
  } finally {
    ordering.value = false
  }
}

function resetOrder() {
  cart.value = {}
  phone.value = ''
  earnedCoupon.value = null
  showSuccess.value = false
}

// ── 加载数据 ────────────────────────────────────────
const FALLBACK_MENU = [
  { id: 1, name: '炸鸡排', desc: '外酥里嫩，现炸现卖', price: 10, category: '热销推荐', emoji: '🍗', available: true },
  { id: 2, name: '冰镇柠檬茶', desc: '清爽解腻', price: 6, category: '热销推荐', emoji: '🥤', available: true },
  { id: 3, name: '红烧肉套餐', desc: '红烧肉 + 米饭 + 汤', price: 22, category: '主食套餐', emoji: '🍖', available: true },
  { id: 4, name: '番茄蛋汤面', desc: '自制汤底，暖胃', price: 14, category: '主食套餐', emoji: '🍜', available: true },
  { id: 5, name: '炸鸡排', desc: '外酥里嫩', price: 10, category: '小吃饮品', emoji: '🍗', available: true },
  { id: 6, name: '冰镇柠檬茶', desc: '清爽解腻', price: 6, category: '小吃饮品', emoji: '🥤', available: true },
]

async function loadShopInfo() {
  if (!shopId.value) return
  try {
    const res = await getShopInfo(shopId.value)
    const data = res?.data?.data || res?.data || {}
    if (data.name) shopName.value = data.name
    if (data.avg_price) avgPrice.value = data.avg_price
    if (data.today_activity) todayActivity.value = data.today_activity
  } catch {
    // 降级用默认值，不影响主流程
  }
}

async function loadMenu() {
  loadingMenu.value = true
  try {
    const res = await getMenuItems({ shop: shopId.value || undefined })
    const items = res?.data?.data?.items || res?.data?.items || res?.data || []
    allDishes.value = Array.isArray(items) && items.length > 0 ? items : FALLBACK_MENU
  } catch {
    allDishes.value = FALLBACK_MENU
  } finally {
    loadingMenu.value = false
    if (categories.value.length) activeCategory.value = categories.value[0]
  }
}

onMounted(() => {
  loadShopInfo()
  loadMenu()
})
</script>

<style scoped>
* { box-sizing: border-box; }

/* ── 进场动效错落延迟（基础 .animate-in/.tap-shrink 用全局 global.scss 定义） ── */
.animate-in--delay-1 { animation-delay: .06s; }
.animate-in--delay-2 { animation-delay: .12s; }

.order-page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg-page);
  font-family: -apple-system, 'PingFang SC', sans-serif;
  color: var(--text-1);
}

.shop-header {
  background: linear-gradient(135deg, var(--brand) 0%, var(--brand-dark) 100%);
  padding: 18px 16px 14px;
  color: #fff;
}

.shop-info h1 { margin: 0 0 4px; font-size: 22px; font-weight: 900; }
.shop-info p { margin: 0; font-size: 13px; opacity: 0.88; }

.activity-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-card);
  background: rgba(255,255,255,0.2);
  font-size: 13px;
  font-weight: 600;
}

.menu-body {
  display: flex;
  flex: 1;
  height: calc(100vh - 116px - 68px);
  overflow: hidden;
}

.category-nav {
  width: 88px;
  flex: none;
  overflow-y: auto;
  background: var(--bg-page);
  padding: 8px 0;
}

.cat-item {
  display: block;
  width: 100%;
  padding: 14px 10px;
  border: 0;
  background: transparent;
  color: var(--text-2);
  font-size: 13px;
  font-weight: 600;
  text-align: center;
  cursor: pointer;
  border-left: 3px solid transparent;
  line-height: 1.3;
}

.cat-item.active {
  background: var(--bg-card);
  color: var(--brand);
  border-left-color: var(--brand);
}

.dish-list {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-card);
  padding: 0 12px;
}

.cat-title {
  margin: 14px 0 8px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-3);
}

.dish-item {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}

.dish-emoji {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-card);
  background: var(--brand-light);
  display: grid;
  place-items: center;
  font-size: 28px;
}

.dish-info { display: flex; flex-direction: column; gap: 3px; }
.dish-info strong { font-size: 15px; font-weight: 700; color: var(--text-1); }
.dish-info span { font-size: 12px; color: var(--text-3); }
.dish-info b { font-size: 16px; font-weight: 900; color: var(--brand); }

.dish-counter { display: flex; align-items: center; gap: 6px; }

.counter-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 0;
  display: grid;
  place-items: center;
  cursor: pointer;
  font-size: 14px;
}

.counter-btn.plus { background: var(--brand); color: #fff; }
.counter-btn.minus { background: var(--border); color: var(--text-2); }

.counter-num {
  min-width: 18px;
  text-align: center;
  font-size: 15px;
  font-weight: 800;
}

.dish-list-bottom-pad { height: 80px; }

/* 购物车栏 */
.cart-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: grid;
  grid-template-columns: 64px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
  background: #1f2937;
  min-height: 68px;
}

.cart-bar.has-items { background: #111827; }

.cart-icon-wrap {
  position: relative;
  width: 50px;
  height: 50px;
  border-radius: 50%;
  border: 0;
  background: #374151;
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.cart-bar.has-items .cart-icon-wrap { background: var(--brand); }

.cart-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  border-radius: 10px;
  background: var(--danger);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  display: grid;
  place-items: center;
}

.cart-price { display: flex; flex-direction: column; gap: 2px; }
.cart-price b { color: #fff; font-size: 22px; font-weight: 900; }
.cart-price span { color: #9ca3af; font-size: 11px; }
.cart-empty-hint { color: #6b7280; font-size: 14px; }

.checkout-btn {
  padding: 0 24px;
  height: 46px;
  border-radius: 23px;
  border: 0;
  background: var(--brand);
  color: #fff;
  font-size: 16px;
  font-weight: 900;
  cursor: pointer;
}

.checkout-btn:disabled { background: #4b5563; cursor: not-allowed; }

/* 购物车弹层 */
.cart-sheet { padding: 16px 16px calc(16px + env(safe-area-inset-bottom)); }

.cart-sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.cart-sheet-header h3 { font-size: 18px; font-weight: 800; margin: 0; color: var(--text-1); }

.clear-btn { border: 0; background: transparent; color: var(--text-3); font-size: 14px; cursor: pointer; }

.cart-items { display: grid; gap: 12px; margin-bottom: 16px; }

.cart-row {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 10px;
}

.cart-row-emoji { font-size: 22px; }
.cart-row-name { font-size: 15px; font-weight: 600; color: var(--text-1); }
.cart-row-right { display: flex; align-items: center; gap: 8px; }
.cart-row-price { min-width: 40px; text-align: right; font-size: 15px; font-weight: 800; color: var(--brand); }

.cart-sheet-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid var(--border);
  margin-bottom: 14px;
}

.cart-sheet-total span { font-size: 15px; color: var(--text-2); }
.cart-sheet-total b { font-size: 24px; font-weight: 900; color: var(--brand); }
.checkout-btn-full { height: 50px; font-size: 17px; font-weight: 900; }

/* 手机号弹层 */
.phone-sheet {
  padding: 24px 16px calc(20px + env(safe-area-inset-bottom));
}

.phone-sheet-top { margin-bottom: 18px; }

.phone-sheet-top h3 {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 800;
  color: var(--text-1);
}

.phone-sheet-top p {
  margin: 0;
  font-size: 14px;
  color: var(--text-2);
  line-height: 1.6;
}

.phone-field {
  margin-bottom: 14px;
  border-radius: var(--radius-card);
  background: var(--bg-page);
  overflow: hidden;
  font-size: 17px;
}

.phone-submit-btn { height: 52px; font-size: 17px; font-weight: 900; }

.phone-skip-btn {
  display: block;
  width: 100%;
  margin-top: 12px;
  border: 0;
  background: transparent;
  color: var(--text-3);
  font-size: 14px;
  cursor: pointer;
  text-align: center;
}

/* 下单成功 */
.success-sheet {
  padding: 28px 20px calc(24px + env(safe-area-inset-bottom));
  text-align: center;
}

.success-anim { display: flex; justify-content: center; margin-bottom: 14px; }

.success-svg { width: 72px; height: 72px; overflow: visible; }

.svg-circle {
  fill: none;
  stroke: var(--success);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 214;
  stroke-dashoffset: 214;
  transform-origin: center;
  transform: rotate(-90deg);
  animation: draw-circle 0.5s cubic-bezier(0.4,0,0.2,1) forwards;
}

.svg-check {
  fill: none;
  stroke: var(--success);
  stroke-width: 5;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 55;
  stroke-dashoffset: 55;
  animation: draw-check 0.35s ease forwards 0.45s;
}

@keyframes draw-circle { to { stroke-dashoffset: 0; } }
@keyframes draw-check { to { stroke-dashoffset: 0; } }

.success-sheet h2 { margin: 0 0 6px; font-size: 26px; font-weight: 900; color: var(--text-1); }
.success-table { margin: 0 0 18px; font-size: 14px; color: var(--text-2); }

.coupon-reward {
  margin-bottom: 20px;
  padding: 16px;
  border-radius: var(--radius-card);
  background: var(--brand-light);
  border: 1px solid var(--brand-mid);
}

.coupon-reward.no-coupon {
  background: var(--bg-page);
  border-color: var(--border);
}

.coupon-reward.no-coupon p { margin: 0; color: var(--text-2); font-size: 14px; }

.coupon-reward-tag { font-size: 13px; color: #9a3412; font-weight: 700; margin-bottom: 8px; }

.coupon-reward-amount {
  font-size: 40px;
  font-weight: 900;
  color: var(--brand);
  line-height: 1;
  margin-bottom: 6px;
}

.coupon-reward-amount::before { content: '¥'; font-size: 20px; vertical-align: super; }
.coupon-reward-desc { font-size: 12px; color: #b45309; margin-bottom: 4px; }
.coupon-reward-name { font-size: 13px; color: #92400e; font-weight: 600; }

/* 加载遮罩 */
.loading-mask {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(255,255,255,0.88);
  z-index: 999;
}

.loading-mask p { color: var(--text-2); font-size: 14px; margin: 0; }
</style>

