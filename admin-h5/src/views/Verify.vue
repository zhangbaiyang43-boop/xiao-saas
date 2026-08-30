<template>
  <div class="sub-page">
    <PageHeader title="扫码核销">
      <a-button type="text" size="small" @click="loadHistory" :loading="loadingHistory" style="color:var(--brand)">刷新</a-button>
    </PageHeader>

    <div class="page-body">
      <!-- 摄像头扫码 -->
      <a-card :bordered="false" class="animate-in" style="margin-bottom:12px;border:1px solid var(--brand-mid)">
        <div style="font-size:12px;color:var(--brand);font-weight:600;margin-bottom:6px">最快方式</div>
        <div style="font-size:17px;font-weight:700;color:var(--text-1);margin-bottom:12px">打开摄像头扫码</div>
        <a-button type="primary" block size="large" class="tap-shrink" @click="openScanner" style="height:52px;font-size:16px;font-weight:700">
          <template #icon><ScanOutlined /></template>
          使用摄像头扫码
        </a-button>
        <div style="text-align:center;font-size:12px;color:var(--text-2);margin-top:10px">手机浏览器或 HTTPS 域名可直接打开摄像头</div>
      </a-card>

      <!-- 手动输入 -->
      <a-card :bordered="false" class="animate-in" style="margin-bottom:12px;animation-delay:.04s">
        <div style="font-size:12px;color:var(--text-2);font-weight:600;margin-bottom:6px">备用方式</div>
        <div style="font-size:17px;font-weight:700;color:var(--text-1);margin-bottom:12px">手动输入券码</div>
        <a-input
          ref="inputRef"
          v-model:value="verifyCode"
          size="large"
          placeholder="输入顾客券码"
          allow-clear
          @keyup.enter="handleVerify"
          @input="handleInput"
          style="margin-bottom:12px;border-radius:8px"
        />
        <a-button
          type="primary"
          block
          size="large"
          class="tap-shrink"
          :loading="loading"
          :disabled="!verifyCode.trim()"
          @click="handleVerify"
          style="height:50px;font-size:16px;font-weight:700"
        >
          确认用券
        </a-button>
      </a-card>

      <!-- 结果反馈 -->
      <a-alert
        v-if="result"
        :type="result.ok ? 'success' : 'error'"
        :message="result.title"
        :description="result.message"
        show-icon
        class="animate-in"
        style="margin-bottom:12px;border-radius:10px"
      />

      <!-- 核销记录 -->
      <a-card :bordered="false" title="最近核销记录" class="animate-in" :body-style="{ padding: 0 }" style="animation-delay:.08s">
        <div v-if="loadingHistory" style="display:flex;justify-content:center;padding:32px"><a-spin /></div>
        <a-empty v-else-if="historyList.length === 0" description="暂无核销记录" style="padding:32px 0" />
        <template v-else>
          <div v-for="item in historyList" :key="item.id" class="history-row">
            <div style="flex:1">
              <div style="font-size:14px;font-weight:600;color:var(--text-1)">{{ item.name }}</div>
              <div style="font-size:12px;color:var(--text-2);margin-top:2px">{{ item.code ? `券码 ${item.code}` : '已完成核销' }} · {{ item.time }}</div>
            </div>
            <div style="font-size:18px;font-weight:900;color:var(--danger)">¥{{ item.amount }}</div>
          </div>
        </template>
      </a-card>
    </div>

    <!-- 摄像头全屏遮罩 -->
    <teleport to="body">
      <transition name="slide-up">
        <div v-if="scannerVisible" class="scanner-overlay">
          <div class="scanner-header">
            <button type="button" class="tap-shrink" @click="closeScanner">关闭</button>
            <div>
              <strong>对准顾客二维码</strong>
              <span>识别后自动核销</span>
            </div>
          </div>
          <camera-scanner ref="scannerRef" fullscreen auto-start :continuous="true" @scan="handleScannedCode" @error="handleScanError" />
          <div class="scanner-footer">
            <a-button block class="tap-shrink" @click="closeScanner" style="color:#fff;border-color:rgba(255,255,255,.3);background:rgba(255,255,255,.1)">改为手动输入</a-button>
          </div>
        </div>
      </transition>
    </teleport>

    <!-- 核销成功遮罩 -->
    <teleport to="body">
      <transition name="pop">
        <div v-if="successOverlay" class="success-overlay" @click="dismissSuccess">
          <div class="success-card" @click.stop="dismissSuccess">
            <div class="success-anim">
              <svg viewBox="0 0 80 80" class="success-svg" aria-hidden="true">
                <circle class="svg-circle" cx="40" cy="40" r="34" />
                <polyline class="svg-check" points="22,41 33,52 58,27" />
              </svg>
            </div>
            <h2 class="success-title">核 销 成 功</h2>
            <div style="font-size:13px;color:#6b7280;margin-bottom:4px">已优惠</div>
            <div class="success-amount">¥{{ successOverlay.amount }}</div>
            <div class="success-customer">{{ successOverlay.customer }}<span v-if="successOverlay.customerName">（{{ successOverlay.customerName }}）</span></div>
            <div class="success-hint"><span class="blink-dot"></span>{{ countdown }}s 后自动关闭，轻触立即关闭</div>
          </div>
        </div>
      </transition>
    </teleport>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ScanOutlined } from '@ant-design/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import CameraScanner from '../components/CameraScanner.vue'
import { getVerifyRecords, verifyCoupon } from '../api'
import { formatBeijingTime } from '../utils/beijingTime'

const inputRef = ref(null)
const scannerVisible = ref(false)
const scannerRef = ref(null)
const verifyCode = ref('')
const loading = ref(false)
const loadingHistory = ref(false)
const result = ref(null)
const successOverlay = ref(null)
const historyList = ref([])
const countdown = ref(3)

let lastScanCode = '', lastScanAt = 0, countdownTimer = null
const SCAN_DEBOUNCE_MS = 2000

function playSuccessSound() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    const playTone = (freq, start, dur) => {
      const osc = ctx.createOscillator(); const gain = ctx.createGain()
      osc.connect(gain); gain.connect(ctx.destination)
      osc.type = 'sine'; osc.frequency.value = freq
      gain.gain.setValueAtTime(0.28, start); gain.gain.exponentialRampToValueAtTime(0.001, start + dur)
      osc.start(start); osc.stop(start + dur)
    }
    const t = ctx.currentTime; playTone(880, t, 0.18); playTone(1320, t + 0.21, 0.24)
  } catch {}
}

function startCountdown() {
  clearInterval(countdownTimer); countdown.value = 3
  countdownTimer = setInterval(() => { countdown.value -= 1; if (countdown.value <= 0) { clearInterval(countdownTimer); dismissSuccess() } }, 1000)
}

function isDuplicateScan(code) {
  const now = Date.now()
  if (code === lastScanCode && now - lastScanAt < SCAN_DEBOUNCE_MS) return true
  lastScanCode = code; lastScanAt = now; return false
}

function withTimeout(promise, ms = 8000) {
  return Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error('网络较慢，请重试')), ms))])
}

function parseScannedCode(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  try {
    const url = new URL(text)
    return url.searchParams.get('code') || url.searchParams.get('coupon_code') || url.searchParams.get('couponCode') || text
  } catch {
    const match = text.match(/[?&](?:code|coupon_code|couponCode)=([^&]+)/)
    return match ? decodeURIComponent(match[1]) : text
  }
}

function friendlyFailure(msg, reason) {
  const t = String(msg || reason || ''); const c = String(reason || '')
  if (c === 'USED' || t.includes('已核销') || t.includes('已使用')) return '这张券已经用过，不能重复核销。'
  if (c === 'EXPIRED' || t.includes('过期')) return '这张券已经过期，不能再使用。'
  if (c === 'CODE_EXPIRED' || t.includes('核销码已过期')) return '二维码已过期，请让顾客刷新后重试。'
  if (c === 'REVOKED' || t.includes('收回')) return '这张券已经被收回，不能核销。'
  if (c === 'NOT_FOUND' || t.includes('不存在')) return '没有找到这张券，请确认顾客出示的是本店可用券。'
  if (c === 'INVAL' || t.includes('无效')) return '核销码无效，请让顾客重新打开优惠券。'
  return t || '核销失败，请检查券码是否正确。'
}

function extractCouponData(res, code) {
  const data = res?.data || {}; const coupon = data.coupon || data
  const amount = Number(coupon.value ?? coupon.coupon_amount ?? coupon.template_value ?? data.coupon_amount ?? 0)
  const rawName = coupon.customer_name || coupon.customer?.name || data.customer_name || ''
  const phone = coupon.customer_phone || coupon.customer?.phone || data.customer_phone || ''
  const tail = phone ? phone.slice(-4) : String(coupon.customer_id || '').slice(-4)
  const customerDisplay = tail ? `尾号${tail}会员` : (rawName || '会员')
  const customerName = (tail && rawName && rawName !== '会员') ? rawName : ''
  return { code, amount: Number.isInteger(amount) ? amount : amount.toFixed(2), customer: customerDisplay, customerName }
}

async function runVerify(code) {
  const finalCode = String(code || '').trim()
  if (!finalCode || loading.value) return false
  if (!navigator.onLine) { message.error('当前网络不可用'); return false }
  loading.value = true; result.value = null
  try {
    const res = await withTimeout(verifyCoupon({ code: finalCode }))
    if (res?.code === 200 || res?.success === true) {
      const data = extractCouponData(res, finalCode)
      successOverlay.value = data
      result.value = { ok: true, title: '核销成功', message: `${data.customer} 省了 ¥${data.amount}` }
      playSuccessSound(); startCountdown(); verifyCode.value = ''; await loadHistory(); return true
    }
    const desc = friendlyFailure(res?.msg || res?.message, res?.data?.data?.reason || res?.data?.reason)
    result.value = { ok: false, title: '不能核销', message: desc }; message.error(desc); return false
  } catch (error) {
    const desc = friendlyFailure(error?.response?.data?.msg, error?.response?.data?.data?.reason)
    result.value = { ok: false, title: '核销失败', message: desc }; message.error(desc); return false
  } finally { loading.value = false }
}

function handleVerify() { runVerify(verifyCode.value) }
function handleInput() { const v = verifyCode.value.trim(); if (v.length >= 6 && /^[A-Z0-9]{6,12}$/i.test(v)) runVerify(v) }
function openScanner() { result.value = null; scannerVisible.value = true }
function closeScanner() { scannerVisible.value = false }

async function handleScannedCode(raw) {
  const code = parseScannedCode(raw)
  if (!code) { message.warning('没有识别到券码'); return }
  if (isDuplicateScan(code)) return
  const ok = await runVerify(code)
  if (!ok) message.warning('请让顾客刷新二维码后再试')
}

function handleScanError(reason) {
  const msgs = { not_found: '没有检测到摄像头，请手动输入券码。', permission_denied: '摄像头权限被拒绝，请在浏览器里允许摄像头。', unsupported: '当前浏览器不支持摄像头扫码，请手动输入券码。' }
  message.error(msgs[reason] || '摄像头不可用，请手动输入券码。'); closeScanner()
}

function dismissSuccess() { clearInterval(countdownTimer); successOverlay.value = null; nextTick(() => inputRef.value?.focus?.()) }

async function loadHistory() {
  loadingHistory.value = true
  try {
    const res = await getVerifyRecords({ page: 1, page_size: 10 })
    const body = res?.data || res || {}
    const rows = body?.data?.results || body?.data?.items || body?.results || body?.items || []
    historyList.value = rows.map(item => ({
      id: item.id,
      name: item.customer_name || item.customer?.name || '会员用券',
      code: item.code || item.coupon_code || '',
      amount: Number(item.coupon_amount || item.template_value || item.value || 0).toFixed(2),
      time: formatBeijingTime(item.use_time || item.verify_time || item.updated_at || item.created_at) || '-',
    }))
  } catch { historyList.value = [] }
  finally { loadingHistory.value = false }
}

onMounted(() => { loadHistory(); nextTick(() => inputRef.value?.focus?.()) })
onBeforeUnmount(() => { document.body.style.overflow = ''; clearInterval(countdownTimer) })
watch(scannerVisible, v => { document.body.style.overflow = v ? 'hidden' : ''; if (!v) nextTick(() => inputRef.value?.focus?.()) })
</script>

<style scoped>
.history-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}

/* ── 摄像头遮罩 ── */
.scanner-overlay {
  position: fixed; inset: 0; z-index: 3000;
  display: flex; flex-direction: column;
  background: #020617; color: #fff;
}
.scanner-header {
  display: grid; grid-template-columns: 64px 1fr 64px; align-items: center;
  padding: max(16px, env(safe-area-inset-top)) 16px 14px; background: #020617;
  button { border: 0; background: transparent; color: #fff; font-size: 16px; }
  div { text-align: center; strong, span { display: block; } strong { font-size: 18px; } span { margin-top: 4px; color: #cbd5e1; font-size: 13px; } }
}
.scanner-footer { padding: 14px 16px calc(14px + env(safe-area-inset-bottom)); background: #020617; }

/* ── 成功遮罩 ── */
.success-overlay {
  position: fixed; inset: 0; z-index: 9999;
  display: grid; place-items: center; padding: 24px;
  background: rgba(10,16,30,.72); backdrop-filter: blur(4px);
}
.success-card {
  width: min(100%, 360px); padding: 32px 24px 26px;
  border-radius: 24px; background: #fff; text-align: center;
  box-shadow: 0 24px 64px rgba(0,0,0,.28); cursor: pointer; user-select: none;
}
.success-anim { display: flex; justify-content: center; margin-bottom: 18px; }
.success-svg { width: 88px; height: 88px; overflow: visible; }
.svg-circle {
  fill: none; stroke: var(--success); stroke-width: 4; stroke-linecap: round;
  stroke-dasharray: 214; stroke-dashoffset: 214;
  transform-origin: center; transform: rotate(-90deg);
  animation: draw-circle 0.5s cubic-bezier(0.4,0,0.2,1) forwards;
}
.svg-check {
  fill: none; stroke: var(--success); stroke-width: 5; stroke-linecap: round; stroke-linejoin: round;
  stroke-dasharray: 55; stroke-dashoffset: 55;
  animation: draw-check 0.35s ease forwards 0.45s;
}
@keyframes draw-circle { to { stroke-dashoffset: 0; } }
@keyframes draw-check  { to { stroke-dashoffset: 0; } }
.success-title { margin: 0 0 16px; font-size: 26px; font-weight: 900; letter-spacing: .12em; color: #111827; }
.success-amount { font-size: 42px; font-weight: 900; color: var(--danger); line-height: 1.1; margin-bottom: 14px; }
.success-customer { font-size: 16px; color: #374151; margin-bottom: 20px; span { color: #6b7280; } }
.success-hint { display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 13px; color: #9ca3af; }
.blink-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--success); animation: blink 1s step-start infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

/* ── 动画 ── */
.slide-up-enter-active, .slide-up-leave-active, .pop-enter-active, .pop-leave-active { transition: all .22s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(100%); }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: scale(.94); }

</style>
