<template>
  <div class="super-wrap">
    <div v-if="!authed" class="login-box">
      <div class="login-logo">中控</div>
      <div class="login-title">平台中控台</div>
      <input v-model="pwd" type="password" class="login-input" placeholder="输入管理密码" @keyup.enter="doLogin" />
      <button class="login-btn" :disabled="logging" @click="doLogin">{{ logging ? '登录中...' : '登录' }}</button>
      <div v-if="loginErr" class="login-err">{{ loginErr }}</div>
    </div>

    <div v-else class="admin-body">
      <div class="top-bar">
        <span class="top-title">平台中控台</span>
        <button class="logout-btn" @click="logout">退出</button>
      </div>

      <div class="stat-row">
        <div class="stat-card"><div class="stat-num">{{ stats.total_merchants }}</div><div class="stat-label">商家总数</div></div>
        <div class="stat-card"><div class="stat-num green">{{ stats.active_merchants }}</div><div class="stat-label">活跃商家</div></div>
        <div class="stat-card"><div class="stat-num blue">{{ stats.today_orders }}</div><div class="stat-label">今日订单</div></div>
        <div class="stat-card"><div class="stat-num green">¥{{ stats.today_revenue?.toFixed(0) }}</div><div class="stat-label">今日营收</div></div>
      </div>

      <div class="section demo-section">
        <div class="section-title">演示账号</div>
        <div class="demo-info">
          <div class="demo-row"><span class="demo-key">登录账号</span><span class="demo-val">demo</span></div>
          <div class="demo-row"><span class="demo-key">密码</span><span class="demo-val">demo123456</span></div>
          <div class="demo-row"><span class="demo-key">店铺名称</span><span class="demo-val">味来餐厅（演示）</span></div>
        </div>
        <div v-if="demoResult" class="create-result" :class="demoResult.ok ? 'ok' : 'err'">{{ demoResult.msg }}</div>
        <button class="demo-reset-btn" :disabled="demoResetting" @click="resetDemo">{{ demoResetting ? '重置中...' : '一键重置演示数据' }}</button>
      </div>

      <div class="section">
        <div class="section-title">开通新商家</div>
        <div class="create-form">
          <input v-model="newMerchant.name" class="form-input" placeholder="* 店铺名称" />
          <input v-model="newMerchant.phone" class="form-input" placeholder="* 手机号（登录账号）" maxlength="11" />
          <input v-model="newMerchant.initial_code" class="form-input" placeholder="初始验证码（默认 123456）" />
          <button class="create-btn" :disabled="creating" @click="createMerchant">{{ creating ? '创建中...' : '+ 立即开通' }}</button>
        </div>
        <div v-if="createResult" class="create-result" :class="createResult.ok ? 'ok' : 'err'">{{ createResult.msg }}</div>
      </div>

      <div class="section">
        <div class="section-title title-row">
          <span>商家列表（{{ merchants.length }}）</span>
          <button class="refresh-btn" @click="loadData">刷新</button>
        </div>
        <div v-if="loadingList" class="loading">加载中...</div>
        <div v-else-if="merchants.length === 0" class="empty">暂无商家</div>
        <div v-else class="merchant-list">
          <div v-for="m in merchants" :key="m.tenant_id" class="merchant-card">
            <div class="mc-left">
              <div class="mc-name">{{ m.name }}</div>
              <div class="mc-meta">{{ m.phone }} · 注册 {{ m.created_at }}</div>
              <div class="mc-meta">今日订单 <b>{{ m.today_orders }}</b> 单</div>
              <div class="mc-pay-row">
                <span class="mc-pay-badge" :class="statusClass(m.payment_status)">{{ statusText(m.payment_status) }} {{ m.wx_mchid_masked || '' }}</span>
                <button class="pay-cfg-btn" @click="openPayConfig(m)">收款配置</button>
              </div>
            </div>
            <div class="mc-right">
              <span class="mc-badge" :class="m.status ? 'on' : 'off'">{{ m.status ? '营业中' : '已停用' }}</span>
              <button class="toggle-btn" :class="m.status ? 'stop' : 'resume'" @click="toggleStatus(m)">{{ m.status ? '停用' : '恢复' }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="payConfigTarget" class="modal-mask" @click.self="closePayConfig">
      <div class="modal-box">
        <div class="modal-title">微信支付收款 — {{ payConfigTarget.name }}</div>

        <div class="receiver-card">
          <div class="receiver-head">
            <div>
              <div class="receiver-kicker">收款安全</div>
              <div class="receiver-title">钱进入商家自己的微信商户号</div>
            </div>
            <span class="status-pill" :class="statusClass(payConfigForm.payment_status)">{{ statusText(payConfigForm.payment_status) }}</span>
          </div>
          <div class="receiver-grid">
            <div><span>收款主体</span><strong>{{ payConfigForm.receiver_name || payConfigTarget.name || '-' }}</strong></div>
            <div><span>微信支付商户号</span><strong>{{ payConfigForm.wx_mchid_masked || maskMchid(payConfigForm.wx_mchid) }}</strong></div>
            <div><span>开户类型</span><strong>{{ receiverTypeText(payConfigForm.receiver_type) }}</strong></div>
            <div><span>最后验证时间</span><strong>{{ payConfigForm.verified_time || '未验证' }}</strong></div>
            <div><span>收款账户锁定状态</span><strong class="lock-text">{{ payConfigForm.payment_locked ? '已锁定' : '未锁定' }}</strong></div>
          </div>
          <div class="safe-tip">平台不能在锁定后把收款商户号改成其他账户；商家后台仅展示收款信息，不展示密钥和私钥。</div>
        </div>

        <button class="fold-btn" @click="techOpen = !techOpen">{{ techOpen ? '收起技术配置' : '展开技术配置（平台管理员）' }}</button>
        <div v-if="techOpen" class="tech-box">
          <div class="modal-label">收款主体</div>
          <input v-model="payConfigForm.receiver_name" class="form-input" placeholder="自动读取失败时可填商户主体名称" />
          <div class="modal-label">开户类型</div>
          <div class="pay-radio-row">
            <button class="pay-radio-btn" :class="payConfigForm.receiver_type === 'enterprise' ? 'selected' : ''" @click="payConfigForm.receiver_type = 'enterprise'">企业</button>
            <button class="pay-radio-btn" :class="payConfigForm.receiver_type === 'individual' ? 'selected' : ''" @click="payConfigForm.receiver_type = 'individual'">个体</button>
          </div>
          <div class="modal-label">商户号</div>
          <input v-model="payConfigForm.wx_mchid" class="form-input" placeholder="商家微信支付商户号" :disabled="payConfigForm.payment_locked && !!payConfigTarget.wx_mchid" />
          <div class="modal-label">APIv3 密钥</div>
          <input v-model="payConfigForm.wx_api_key_v3" class="form-input" placeholder="32位 APIv3 密钥" />
          <div class="modal-label">证书序列号</div>
          <input v-model="payConfigForm.wx_cert_serial" class="form-input" placeholder="证书序列号" />
          <div class="modal-label">私钥</div>
          <textarea v-model="payConfigForm.wx_private_key" class="form-input private-input" rows="4" placeholder="粘贴 apiclient_key.pem 内容（商户私钥，用于请求签名）" />
          <div class="modal-label">微信支付公钥ID</div>
          <input v-model="payConfigForm.wx_public_key_id" class="form-input" placeholder="微信支付公钥ID（从商户平台获取）" />
          <div class="modal-label">微信支付公钥</div>
          <textarea v-model="payConfigForm.wx_public_key" class="form-input private-input" rows="4" placeholder="粘贴微信支付公钥内容（用于验证回调签名）" />
        </div>

        <div v-if="payConfigResult" class="create-result" :class="payConfigResult.ok ? 'ok' : 'err'">{{ payConfigResult.msg }}</div>
        <div class="modal-actions">
          <button class="create-btn" :disabled="savingPay" @click="savePayConfig">{{ savingPay ? '保存中...' : '保存' }}</button>
          <button class="verify-btn" :disabled="verifyingPay || !payConfigTarget.wx_mchid" @click="verifyPayConfig">{{ verifyingPay ? '验证中...' : '验证配置' }}</button>
          <button class="pause-btn" :disabled="pausingPay || !payConfigTarget.wx_mchid" @click="pausePay">暂停支付</button>
        </div>
        <button class="cancel-btn" @click="closePayConfig">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import axios from 'axios'

const BASE = '/api/super'

const authed = ref(false)
const pwd = ref('')
const logging = ref(false)
const loginErr = ref('')
let superToken = ''

const stats = reactive({ total_merchants: 0, active_merchants: 0, today_orders: 0, today_revenue: 0 })
const merchants = ref([])
const loadingList = ref(false)
const newMerchant = reactive({ name: '', phone: '', initial_code: '123456' })
const creating = ref(false)
const createResult = ref(null)
const payConfigTarget = ref(null)
const techOpen = ref(false)
const payConfigForm = reactive({
  wx_mchid: '', wx_mchid_masked: '', wx_api_key_v3: '', wx_cert_serial: '', wx_private_key: '', wx_public_key_id: '', wx_public_key: '', wx_pay_enabled: true,
  receiver_name: '', receiver_type: 'enterprise', receiver_verified: false, payment_locked: true, payment_status: 'unconfigured', verified_time: '',
})
const savingPay = ref(false)
const verifyingPay = ref(false)
const pausingPay = ref(false)
const payConfigResult = ref(null)
const demoResetting = ref(false)
const demoResult = ref(null)

function superHeaders() { return { 'X-Super-Token': superToken } }
function statusText(status) { return { unconfigured: '未配置', pending: '待验证', verified: '已验证', paused: '暂停' }[status] || '未配置' }
function statusClass(status) { return { unconfigured: 'pay-off', pending: 'pay-pending', verified: 'pay-on', paused: 'pay-paused' }[status] || 'pay-off' }
function receiverTypeText(type) { return type === 'individual' ? '个体' : '企业' }
function maskMchid(value) {
  const v = (value || '').trim()
  if (!v) return '-'
  if (v.length <= 6) return v
  return `${v.slice(0, 3)}****${v.slice(-3)}`
}
function applyPaymentData(target, data) {
  if (!data) return
  Object.assign(target, {
    wx_mchid: data.wx_mchid ?? target.wx_mchid,
    wx_mchid_masked: data.wx_mchid_masked ?? maskMchid(data.wx_mchid ?? target.wx_mchid),
    wx_pay_enabled: data.wx_pay_enabled ?? target.wx_pay_enabled,
    receiver_name: data.receiver_name ?? target.receiver_name,
    receiver_type: data.receiver_type ?? target.receiver_type,
    receiver_verified: data.receiver_verified ?? target.receiver_verified,
    payment_locked: data.payment_locked ?? target.payment_locked,
    payment_status: data.payment_status ?? target.payment_status,
    verified_time: data.verified_time ?? target.verified_time,
  })
}
function closePayConfig() { payConfigTarget.value = null }

async function doLogin() {
  if (!pwd.value.trim()) return
  logging.value = true
  loginErr.value = ''
  try {
    const res = await axios.post(`${BASE}/login`, { password: pwd.value })
    if (res.data?.code === 200) { superToken = res.data.data.token; authed.value = true; loadData() }
    else loginErr.value = res.data?.msg || '登录失败'
  } catch { loginErr.value = '网络错误，请重试' }
  finally { logging.value = false }
}

async function loadData() {
  loadingList.value = true
  try {
    const [statsRes, listRes] = await Promise.all([
      axios.get(`${BASE}/stats`, { headers: superHeaders() }),
      axios.get(`${BASE}/merchants`, { headers: superHeaders() }),
    ])
    if (statsRes.data?.code === 200) Object.assign(stats, statsRes.data.data)
    if (listRes.data?.code === 200) merchants.value = listRes.data.data
  } catch (e) {
    if (e?.response?.status === 401) authed.value = false
    else {
      merchants.value = []
      stats.total_merchants = 0
      stats.active_merchants = 0
      stats.today_orders = 0
      stats.today_revenue = 0
      console.error('商户数据加载失败:', e)
    }
  }
  finally { loadingList.value = false }
}

async function createMerchant() {
  if (!newMerchant.name || !newMerchant.phone) { createResult.value = { ok: false, msg: '店铺名称和手机号必填' }; return }
  creating.value = true
  createResult.value = null
  try {
    const res = await axios.post(`${BASE}/merchants`, { ...newMerchant }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      const d = res.data.data
      createResult.value = { ok: true, msg: `已开通「${d.name}」，手机号 ${d.phone}，登录码 ${d.login_code}` }
      newMerchant.name = ''; newMerchant.phone = ''; newMerchant.initial_code = '123456'
      await loadData()
    } else createResult.value = { ok: false, msg: res.data?.msg || '创建失败' }
  } catch { createResult.value = { ok: false, msg: '网络错误，请重试' } }
  finally { creating.value = false }
}

function openPayConfig(m) {
  payConfigTarget.value = m
  techOpen.value = false
  payConfigResult.value = null
  Object.assign(payConfigForm, {
    wx_mchid: m.wx_mchid || '', wx_mchid_masked: m.wx_mchid_masked || maskMchid(m.wx_mchid), wx_api_key_v3: '', wx_cert_serial: '', wx_private_key: '', wx_pay_enabled: m.wx_pay_enabled ?? true,
    receiver_name: m.receiver_name || m.name || '', receiver_type: m.receiver_type || 'enterprise', receiver_verified: !!m.receiver_verified,
    payment_locked: m.payment_locked ?? true, payment_status: m.payment_status || 'unconfigured', verified_time: m.verified_time || '',
  })
}

async function savePayConfig() {
  if (!payConfigForm.wx_mchid.trim() || !payConfigForm.wx_api_key_v3.trim() || !payConfigForm.wx_cert_serial.trim() || !payConfigForm.wx_private_key.trim()) {
    payConfigResult.value = { ok: false, msg: '请完整填写技术配置后保存' }
    techOpen.value = true
    return
  }
  savingPay.value = true
  payConfigResult.value = null
  try {
    const res = await axios.patch(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay`, {
      wx_mchid: payConfigForm.wx_mchid.trim(),
      wx_api_key_v3: payConfigForm.wx_api_key_v3.trim(),
      wx_cert_serial: payConfigForm.wx_cert_serial.trim(),
      wx_private_key: payConfigForm.wx_private_key.trim(),
      wx_public_key_id: payConfigForm.wx_public_key_id.trim() || null,
      wx_public_key: payConfigForm.wx_public_key.trim() || null,
      wx_pay_enabled: true,
      receiver_name: payConfigForm.receiver_name.trim(),
      receiver_type: payConfigForm.receiver_type,
    }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: '保存成功，请继续验证配置' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      applyPaymentData(payConfigForm, res.data.data)
      payConfigForm.wx_api_key_v3 = ''; payConfigForm.wx_cert_serial = ''; payConfigForm.wx_private_key = ''; payConfigForm.wx_public_key = ''
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '保存失败' }
  } catch (e) { payConfigResult.value = { ok: false, msg: e?.response?.data?.msg || e?.response?.data?.detail?.message || '网络错误，请重试' } }
  finally { savingPay.value = false }
}

async function verifyPayConfig() {
  verifyingPay.value = true
  payConfigResult.value = null
  try {
    const res = await axios.post(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay/verify`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: res.data?.msg || '验证通过' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      applyPaymentData(payConfigForm, res.data.data)
      payConfigForm.wx_api_key_v3 = ''; payConfigForm.wx_cert_serial = ''; payConfigForm.wx_private_key = ''; payConfigForm.wx_public_key = ''
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '验证失败' }
  } catch (e) {
    const detail = e?.response?.data?.detail
    const msg = detail?.message || e?.response?.data?.msg || '验证失败'
    payConfigResult.value = { ok: false, msg }
  }
  finally { verifyingPay.value = false }
}

async function pausePay() {
  pausingPay.value = true
  payConfigResult.value = null
  try {
    const res = await axios.patch(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay/pause`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: '已暂停支付' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      applyPaymentData(payConfigForm, res.data.data)
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '暂停失败' }
  } catch (e) { payConfigResult.value = { ok: false, msg: e?.response?.data?.msg || '暂停失败' } }
  finally { pausingPay.value = false }
}

async function resetDemo() {
  demoResetting.value = true
  demoResult.value = null
  try {
    const res = await axios.post(`${BASE}/demo/reset`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) {
      const d = res.data.data
      demoResult.value = { ok: true, msg: `重置成功：${d.menu_items} 道菜 · ${d.customers} 位会员 · 历史 ${d.history_orders} 单 · 今日 ${d.today_orders} 单` }
    } else demoResult.value = { ok: false, msg: res.data?.msg || '重置失败' }
  } catch { demoResult.value = { ok: false, msg: '网络错误，请重试' } }
  finally { demoResetting.value = false }
}

async function toggleStatus(merchant) {
  try {
    const res = await axios.patch(`${BASE}/merchants/${merchant.tenant_id}/status`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) merchant.status = res.data.data.status
  } catch {}
}

function logout() { superToken = ''; authed.value = false; pwd.value = '' }
</script>

<style scoped>
* { box-sizing: border-box; }
.super-wrap { min-height: 100vh; background: #f5f6fa; font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; color: #111827; }
.login-box { max-width: 360px; margin: 0 auto; padding: 80px 24px 0; text-align: center; }
.login-logo { display: inline-flex; align-items: center; justify-content: center; width: 56px; height: 56px; border-radius: 16px; background: #07C160; color: #fff; font-weight: 900; margin-bottom: 10px; }
.login-title { font-size: 22px; font-weight: 900; margin-bottom: 28px; }
.login-input, .form-input { width: 100%; height: 44px; border: 1px solid #e5e7eb; border-radius: 8px; padding: 0 12px; font-size: 14px; outline: none; background: #fff; }
.login-input { height: 48px; margin-bottom: 12px; }
.login-input:focus, .form-input:focus { border-color: #07C160; box-shadow: 0 0 0 2px rgba(7,193,96,.12); }
.login-btn, .create-btn { height: 44px; background: #07C160; color: #fff; border: 0; border-radius: 8px; font-size: 15px; font-weight: 800; cursor: pointer; }
.login-btn { width: 100%; height: 48px; }
.login-btn:disabled, .create-btn:disabled, .verify-btn:disabled, .pause-btn:disabled { opacity: .55; cursor: not-allowed; }
.login-err { color: #ef4444; font-size: 13px; margin-top: 8px; }
.top-bar { display: flex; justify-content: space-between; align-items: center; padding: 52px 16px 12px; background: #fff; border-bottom: 1px solid #f0f0f0; }
.top-title { font-size: 18px; font-weight: 900; }
.logout-btn, .refresh-btn, .pay-cfg-btn, .cancel-btn, .fold-btn { border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; color: #374151; cursor: pointer; }
.logout-btn, .refresh-btn { padding: 5px 12px; font-size: 13px; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); padding: 12px 16px; gap: 8px; }
.stat-card, .section { background: #fff; border-radius: 12px; }
.stat-card { padding: 12px 8px; text-align: center; }
.stat-num { font-size: 20px; font-weight: 900; }
.stat-num.green { color: #07C160; } .stat-num.blue { color: #1677ff; }
.stat-label { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.section { margin: 0 16px 16px; padding: 16px; }
.section-title { font-size: 15px; font-weight: 800; margin-bottom: 12px; }
.title-row { display: flex; align-items: center; justify-content: space-between; }
.create-form { display: grid; gap: 8px; }
.create-result { margin-top: 10px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.create-result.ok { background: #f0fdf4; color: #16a34a; } .create-result.err { background: #fef2f2; color: #dc2626; }
.loading, .empty { text-align: center; color: #9ca3af; padding: 24px 0; font-size: 14px; }
.merchant-list { display: grid; gap: 10px; }
.merchant-card { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 12px; background: #f9fafb; border-radius: 10px; }
.mc-left { min-width: 0; }
.mc-name { font-size: 15px; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mc-meta { font-size: 12px; color: #6b7280; margin-top: 3px; }
.mc-right { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0; }
.mc-badge, .mc-pay-badge, .status-pill { font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 20px; white-space: nowrap; }
.mc-badge.on, .pay-on { background: #dcfce7; color: #16a34a; }
.mc-badge.off { background: #f3f4f6; color: #6b7280; }
.pay-off { background: #fef9c3; color: #92400e; } .pay-pending { background: #eff6ff; color: #2563eb; } .pay-paused { background: #f3f4f6; color: #6b7280; }
.toggle-btn { font-size: 12px; padding: 4px 12px; border-radius: 6px; border: 0; cursor: pointer; font-weight: 700; }
.toggle-btn.stop { background: #fef2f2; color: #ef4444; } .toggle-btn.resume { background: #f0fdf4; color: #16a34a; }
.mc-pay-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
.pay-cfg-btn { font-size: 11px; padding: 3px 10px; }
.demo-section { border: 1px dashed #fbbf24; background: #fffbeb; }
.demo-info { background: #fff; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
.demo-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.demo-key { color: #9ca3af; } .demo-val { font-weight: 800; font-family: monospace; }
.demo-reset-btn { width: 100%; height: 42px; background: #f59e0b; color: #fff; border: 0; border-radius: 8px; font-weight: 800; }
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 999; padding: 18px; }
.modal-box { width: min(520px, 100%); max-height: calc(100vh - 36px); overflow-y: auto; background: #fff; border-radius: 16px; padding: 18px; }
.modal-title { font-size: 17px; font-weight: 900; margin-bottom: 12px; }
.receiver-card { border: 1px solid #d1fae5; background: #f7fef9; border-radius: 12px; padding: 14px; }
.receiver-head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; margin-bottom: 12px; }
.receiver-kicker { font-size: 12px; color: #16a34a; font-weight: 900; }
.receiver-title { font-size: 16px; font-weight: 900; margin-top: 2px; }
.receiver-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.receiver-grid span, .modal-label { display: block; font-size: 12px; color: #6b7280; margin-bottom: 5px; }
.receiver-grid strong { display: block; font-size: 14px; color: #111827; word-break: break-all; }
.lock-text { color: #16a34a !important; }
.safe-tip { margin-top: 12px; padding: 10px; border-radius: 8px; background: #fff; color: #4b5563; font-size: 12px; line-height: 1.6; }
.fold-btn { width: 100%; height: 40px; margin-top: 12px; font-weight: 800; }
.tech-box { display: grid; gap: 8px; margin-top: 12px; padding: 12px; border: 1px solid #eef2f7; border-radius: 12px; background: #fafafa; }
.pay-radio-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.pay-radio-btn { height: 36px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; color: #374151; font-size: 14px; cursor: pointer; }
.pay-radio-btn.selected { border-color: #07C160; background: #f0fdf4; color: #16a34a; font-weight: 800; }
.private-input { height: 86px; padding-top: 10px; resize: vertical; font-size: 12px; line-height: 1.5; }
.modal-actions { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 12px; }
.verify-btn, .pause-btn { height: 44px; border: 0; border-radius: 8px; font-weight: 800; cursor: pointer; }
.verify-btn { background: #1677ff; color: #fff; } .pause-btn { background: #fef2f2; color: #dc2626; }
.cancel-btn { width: 100%; height: 40px; margin-top: 8px; }
@media (max-width: 420px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
  .merchant-card { align-items: flex-start; }
  .receiver-grid, .modal-actions { grid-template-columns: 1fr; }
}
</style>
