import { ref } from 'vue'
import { message } from 'ant-design-vue'

// 这份状态必须是模块级单例，不能挂在组件实例上（比如直接 ref() 写在 OrderManage.vue
// 的 <script setup> 里）——后台的 Tab 切换是 <router-view> 不带 keep-alive，每次从
// "菜单"切回"接单"都会把 OrderManage.vue 整个卸载重建。如果 AudioContext 挂在组件
// 实例上，每次重建都会 new 一个新的、浏览器十有八九判定成 suspended 的 AudioContext，
// "解锁"状态就跟着切一次 Tab 丢一次，逼老板反复点"解锁"。放到模块作用域后，这份状态
// 只在真正离开这个 JS 运行时（整页刷新/关闭标签页）才会重置，与 Tab 切换无关。
const _alertPref = localStorage.getItem('orderAlertEnabled')
const alertEnabled = ref(_alertPref === null ? true : _alertPref === '1')
if (_alertPref === null) localStorage.setItem('orderAlertEnabled', '1')

const audioNeedsUnlock = ref(false)
let audioCtx = null
let probed = false
let prevPendingCount = null

function _beep(ctx, freq, startOffset) {
  const gain = ctx.createGain()
  gain.connect(ctx.destination)
  const osc = ctx.createOscillator()
  osc.connect(gain)
  osc.frequency.value = freq
  gain.gain.setValueAtTime(0.4, ctx.currentTime + startOffset)
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startOffset + 0.25)
  osc.start(ctx.currentTime + startOffset)
  osc.stop(ctx.currentTime + startOffset + 0.27)
}

function playNewOrderBeep() {
  if (!alertEnabled.value || !audioCtx) return
  try {
    if (audioCtx.state === 'suspended') audioCtx.resume()
    _beep(audioCtx, 880, 0)
    _beep(audioCtx, 880, 0.3)
    _beep(audioCtx, 1100, 0.6)
  } catch {}
}

function enableAlert() {
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)()
    probed = true
    // 初始化播放一声确认音，同时解锁 AudioContext
    _beep(audioCtx, 880, 0)
    _beep(audioCtx, 1100, 0.25)
    alertEnabled.value = true
    audioNeedsUnlock.value = false
    localStorage.setItem('orderAlertEnabled', '1')
    message.success('接单提醒已开启，有新订单会响铃')
  } catch {
    message.error('当前浏览器不支持语音提醒')
  }
}

function disableAlert() {
  alertEnabled.value = false
  localStorage.setItem('orderAlertEnabled', '0')
  message.info('提醒已关闭')
}

function unlockAudio() {
  if (!audioCtx) return
  try {
    audioCtx.resume()
    _beep(audioCtx, 880, 0)
    audioNeedsUnlock.value = false
    message.success('提醒已解锁，有新订单会响铃')
  } catch {}
}

// 如果之前已开启提醒，静默恢复 AudioContext——但不能只是"等用户下次点击页面时自动
// 解锁"就完事，那个时机对老板不可见，他会以为提醒在正常工作。这里主动检测一下：
// 挂起了就把 audioNeedsUnlock 打开，界面上露出一个明确的"点这里解锁"提示。
// 只探测一次：已经探测过（不管结论是"挂起"还是"没挂起"），或者已经通过 enableAlert/
// unlockAudio 确认解锁过了，组件重新挂载时都不用再 new 一个 AudioContext 重新问一遍。
function ensureAlertProbed() {
  if (probed || !alertEnabled.value) return
  probed = true
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)()
    if (audioCtx.state === 'suspended') audioNeedsUnlock.value = true
  } catch {}
}

function noteNewPendingCount(newPending) {
  if (prevPendingCount !== null && newPending > prevPendingCount) playNewOrderBeep()
  prevPendingCount = newPending
}

export function useOrderAlert() {
  return {
    alertEnabled,
    audioNeedsUnlock,
    enableAlert,
    disableAlert,
    unlockAudio,
    ensureAlertProbed,
    noteNewPendingCount,
  }
}
