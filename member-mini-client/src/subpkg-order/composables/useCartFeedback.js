import { ref, nextTick } from 'vue'

// 从 menu.vue 拆出来的购物车"手感反馈"——加号按下去的按压态、加入购物车后数量
// 气泡的跳动、购物车图标/角标/金额的一次性脉冲动画。都是纯 UI 定时器状态，不碰
// 网络、不碰存储、也不改购物车本身的数据。逻辑跟原来在 menu.vue 里的一字未改，
// 只是搬了个位置。
//
// 之所以是 MEDIUM 而不是 LOW：这里有真正的副作用（setTimeout 定时器、nextTick
// 之后再改一次值来强制触发 CSS 动画重播），不是纯粹的输入→输出计算。
export function useCartFeedback() {
  const addPressKey = ref('')
  const qtyPulseKey = ref('')
  const cartIconPulse = ref(false)
  const cartBadgePulse = ref(false)
  const amountPulse = ref(false)
  const microTimers = {}

  const restartMicroTimer = (key, done, duration = 180) => {
    if (microTimers[key]) clearTimeout(microTimers[key])
    microTimers[key] = setTimeout(() => {
      done()
      microTimers[key] = null
    }, duration)
  }
  const pulseKey = (target, key, timerKey, duration = 160) => {
    target.value = ''
    nextTick(() => {
      target.value = key
      restartMicroTimer(timerKey, () => { target.value = '' }, duration)
    })
  }
  const pulseFlag = (target, timerKey, duration = 180) => {
    target.value = false
    nextTick(() => {
      target.value = true
      restartMicroTimer(timerKey, () => { target.value = false }, duration)
    })
  }
  const triggerAddPress = (key) => pulseKey(addPressKey, key, 'add-' + key, 160)
  const triggerCartSuccessFeedback = (key) => {
    pulseKey(qtyPulseKey, key, 'qty-' + key, 160)
    pulseFlag(cartIconPulse, 'cart-icon', 180)
    pulseFlag(cartBadgePulse, 'cart-badge', 180)
    pulseFlag(amountPulse, 'cart-amount', 220)
  }
  const triggerCartValueFeedback = (key) => {
    pulseKey(qtyPulseKey, key, 'qty-' + key, 150)
    pulseFlag(amountPulse, 'cart-amount', 200)
  }

  return {
    addPressKey,
    qtyPulseKey,
    cartIconPulse,
    cartBadgePulse,
    amountPulse,
    triggerAddPress,
    triggerCartSuccessFeedback,
    triggerCartValueFeedback,
  }
}
