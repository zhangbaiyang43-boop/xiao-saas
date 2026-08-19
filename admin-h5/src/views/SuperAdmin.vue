<template>
  <div class="super-wrap">
    <div v-if="!authed" class="login-box">
      <div class="login-card animate-in">
        <div class="login-hero">
          <div class="login-logo">中控</div>
          <div class="login-title">平台中控台</div>
          <div class="login-sub">OPERATOR CONSOLE</div>
        </div>
        <div class="login-form">
          <input v-if="!needTotp" v-model="pwd" type="password" class="login-input" placeholder="输入管理密码" @keyup.enter="doLogin" />
          <template v-else>
            <div class="totp-hint">请输入认证器 App 里的 6 位动态口令</div>
            <input v-model="totpCode" type="text" inputmode="numeric" maxlength="6" class="login-input" placeholder="6位动态口令" @keyup.enter="doLogin" />
          </template>
          <button class="login-btn tap-shrink" :disabled="logging || (!needTotp && !pwd.trim()) || (needTotp && !totpCode.trim())" @click="doLogin">{{ logging ? '登录中...' : (needTotp ? '验证' : '登录') }}</button>
          <div v-if="loginErr" class="login-err">{{ loginErr }}</div>
        </div>
      </div>
    </div>

    <div v-else class="admin-body">
      <div class="top-bar animate-in">
        <span class="top-title">平台中控台</span>
        <button class="logout-btn tap-shrink" @click="logout">退出</button>
      </div>

      <div class="console-tabs animate-in">
        <button class="tab-btn tap-shrink" :class="{ active: activeTab === 'merchants' }" @click="activeTab = 'merchants'">商家管理</button>
        <button class="tab-btn tap-shrink" :class="{ active: activeTab === 'billing' }" @click="activeTab = 'billing'">
          待确认付款<span v-if="pendingPaymentCount > 0" class="tab-badge">{{ pendingPaymentCount }}</span>
        </button>
        <button class="tab-btn tap-shrink" :class="{ active: activeTab === 'channel' }" @click="activeTab = 'channel'">渠道管理</button>
      </div>

      <div v-if="activeTab === 'merchants'">
      <div class="stat-row animate-in">
        <div class="stat-card"><div class="stat-num">{{ stats.total_merchants }}</div><div class="stat-label">商家总数</div></div>
        <div class="stat-card"><div class="stat-num green">{{ stats.active_merchants }}</div><div class="stat-label">活跃商家</div></div>
        <div class="stat-card"><div class="stat-num blue">{{ stats.today_orders }}</div><div class="stat-label">今日订单</div></div>
        <div class="stat-card"><div class="stat-num green">¥{{ stats.today_revenue?.toFixed(0) }}</div><div class="stat-label">今日营收</div></div>
      </div>

      <div class="section animate-in">
        <div class="section-title">性能监控（P50/P95）</div>
        <div v-if="perfStatsLoading" class="loading">加载中...</div>
        <div v-else-if="perfStatsError" class="empty">加载失败</div>
        <div v-else-if="!perfStats.length" class="empty">暂无采样数据</div>
        <table v-else class="perf-table">
          <thead>
            <tr>
              <th>指标</th>
              <th class="num">样本数</th>
              <th class="num">均值</th>
              <th class="num">P50</th>
              <th class="num">P95</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in perfStats" :key="row.metric">
              <td>{{ row.metric }}</td>
              <td class="num">{{ row.count }}</td>
              <td class="num">{{ row.avg }} ms</td>
              <td class="num">{{ row.p50 }} ms</td>
              <td class="num">{{ row.p95 }} ms</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="section animate-in">
        <div class="section-title">开通新商家</div>
        <div class="create-form">
          <input v-model="newMerchant.name" class="form-input" placeholder="* 店铺名称" />
          <input v-model="newMerchant.phone" class="form-input" placeholder="* 手机号（登录账号）" maxlength="11" />
          <input v-model="newMerchant.initial_code" class="form-input" placeholder="初始验证码（默认 123456）" />
          <button class="create-btn tap-shrink" :disabled="creating" @click="createMerchant">{{ creating ? '创建中...' : '+ 立即开通' }}</button>
        </div>
        <div v-if="createResult" class="create-result" :class="createResult.ok ? 'ok' : 'err'">{{ createResult.msg }}</div>
      </div>

      <div class="section animate-in">
        <div class="section-title title-row">
          <span>商家列表（{{ filteredMerchants.length }}/{{ merchants.length }}）</span>
          <button class="refresh-btn tap-shrink" @click="loadData">刷新</button>
        </div>
        <input v-model="searchQuery" class="form-input search-input" placeholder="搜索店铺名称或手机号" />
        <div class="filter-row">
          <button
            v-for="f in statusFilters"
            :key="f.value"
            class="filter-chip tap-shrink"
            :class="{ active: statusFilter === f.value }"
            @click="statusFilter = f.value"
          >{{ f.label }}</button>
        </div>
        <div v-if="loadingList" class="loading">加载中...</div>
        <div v-else-if="merchants.length === 0" class="empty">暂无商家</div>
        <div v-else-if="filteredMerchants.length === 0" class="empty">没有匹配的商家</div>
        <div v-else class="merchant-list">
          <div v-for="m in filteredMerchants" :key="m.tenant_id" class="merchant-card">
            <div class="mc-left">
              <div class="mc-name">{{ m.name }}</div>
              <div class="mc-meta">
                <span class="phone-reveal tap-shrink" @click="togglePhone(m.tenant_id)">{{ revealedPhones.has(m.tenant_id) ? m.phone : maskPhone(m.phone) }}</span>
                · 注册 {{ m.created_at }}
              </div>
              <div class="mc-meta">今日订单 <b>{{ m.today_orders }}</b> 单</div>
              <div class="mc-pay-row">
                <span class="mc-pay-badge" :class="statusClass(m.payment_status)">{{ statusText(m.payment_status) }} {{ m.wx_mchid_masked || '' }}</span>
                <button class="pay-cfg-btn tap-shrink" @click="openPayConfig(m)">收款配置</button>
                <button class="pay-cfg-btn tap-shrink" :disabled="seedingId === m.tenant_id" @click="seedTestData(m)">{{ seedingId === m.tenant_id ? '填充中...' : '填充测试数据' }}</button>
              </div>
              <div v-if="seedResult && seedResult.tenant_id === m.tenant_id" class="create-result" :class="seedResult.ok ? 'ok' : 'err'">{{ seedResult.msg }}</div>
            </div>
            <div class="mc-right">
              <span class="mc-badge" :class="m.status ? 'on' : 'off'">{{ m.status ? '营业中' : '已停用' }}</span>
              <button class="toggle-btn tap-shrink" :class="m.status ? 'stop' : 'resume'" @click="toggleStatus(m)">{{ m.status ? '停用' : '恢复' }}</button>
            </div>
          </div>
        </div>
      </div>
      </div>

      <ManualPaymentPanel v-else-if="activeTab === 'billing'" :super-token="superToken" @update:count="pendingPaymentCount = $event" />

      <ChannelPartnerPanel v-else :super-token="superToken" />
    </div>

    <div v-if="payConfigTarget" class="modal-mask" @click.self="closePayConfig">
      <div class="modal-box animate-in">
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

        <button class="fold-btn tap-shrink" @click="techOpen = !techOpen">{{ techOpen ? '收起技术配置' : '展开技术配置（平台管理员）' }}</button>
        <div v-if="techOpen" class="tech-box animate-in">
          <div v-if="copySources.length" class="copy-box">
            <div class="modal-label">从其它商户复制配置</div>
            <div class="field-hint">已验证过的商户可以直接复制过来，不用逐字段重新抄一遍</div>
            <div class="copy-row">
              <select v-model="copySourceId" class="form-input copy-select">
                <option value="">选择源商户...</option>
                <option v-for="s in copySources" :key="s.tenant_id" :value="s.tenant_id">{{ s.name }}（{{ statusText(s.payment_status) }}）</option>
              </select>
              <button class="copy-btn tap-shrink" :disabled="!copySourceId || copyingPay" @click="confirmCopyPayConfig">{{ copyingPay ? '复制中...' : '复制' }}</button>
            </div>
          </div>
          <div class="modal-label">收款主体</div>
          <input v-model="payConfigForm.receiver_name" class="form-input" placeholder="自动读取失败时可填商户主体名称" />
          <div class="modal-label">开户类型</div>
          <div class="pay-radio-row">
            <button class="pay-radio-btn tap-shrink" :class="payConfigForm.receiver_type === 'enterprise' ? 'selected' : ''" @click="payConfigForm.receiver_type = 'enterprise'">企业</button>
            <button class="pay-radio-btn tap-shrink" :class="payConfigForm.receiver_type === 'individual' ? 'selected' : ''" @click="payConfigForm.receiver_type = 'individual'">个体</button>
          </div>
          <div class="modal-label">商户号</div>
          <div class="field-hint">商户平台首页右上角，或「账户中心 → 商户信息」可查看</div>
          <input v-model="payConfigForm.wx_mchid" class="form-input" placeholder="商家微信支付商户号" :disabled="payConfigForm.payment_locked && !!payConfigTarget.wx_mchid" />
          <div class="modal-label">APIv3 密钥</div>
          <div class="field-hint">「账户中心 → API安全 → 设置/重置 APIv3 密钥」；这是自己设定的 32 位密钥，忘记了要在那里重置</div>
          <input v-model="payConfigForm.wx_api_key_v3" class="form-input" placeholder="32位 APIv3 密钥" />
          <div class="modal-label">证书序列号</div>
          <div class="field-hint">「账户中心 → API安全 → API证书」，证书详情页可见</div>
          <input v-model="payConfigForm.wx_cert_serial" class="form-input" placeholder="证书序列号" />
          <div class="modal-label">私钥</div>
          <div class="field-hint">申请 API 证书后下载的压缩包里，apiclient_key.pem 文件的全部内容</div>
          <textarea v-model="payConfigForm.wx_private_key" class="form-input private-input" rows="6" placeholder="粘贴 apiclient_key.pem 内容（商户私钥，用于请求签名）" />
          <div class="modal-label">微信支付公钥ID</div>
          <div class="field-hint">「账户中心 → API安全 → 微信支付公钥」，下载后可见</div>
          <input v-model="payConfigForm.wx_public_key_id" class="form-input" placeholder="微信支付公钥ID（从商户平台获取）" />
          <div class="modal-label">微信支付公钥</div>
          <div class="field-hint">同样在「账户中心 → API安全 → 微信支付公钥」下载获取</div>
          <textarea v-model="payConfigForm.wx_public_key" class="form-input private-input" rows="6" placeholder="粘贴微信支付公钥内容（用于验证回调签名）" />
        </div>

        <div v-if="payConfigResult" class="create-result" :class="payConfigResult.ok ? 'ok' : 'err'">{{ payConfigResult.msg }}</div>
        <div class="modal-actions">
          <button class="create-btn tap-shrink" :disabled="savingPay" @click="savePayConfig">{{ savingPay ? '保存中...' : '保存' }}</button>
          <button class="verify-btn tap-shrink" :class="{ 'verify-btn--pending': payConfigTarget.wx_mchid && !payConfigForm.receiver_verified }" :disabled="verifyingPay || !payConfigTarget.wx_mchid" @click="verifyPayConfig">{{ verifyingPay ? '验证中...' : '验证配置' }}</button>
        </div>
        <button class="cancel-btn tap-shrink" @click="closePayConfig">关闭</button>

        <div class="danger-zone">
          <div class="danger-zone-label">危险操作</div>
          <button class="pause-btn tap-shrink" :disabled="pausingPay || !payConfigTarget.wx_mchid" @click="confirmPausePay">{{ pausingPay ? '暂停中...' : '暂停支付' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import axios from 'axios'
import ChannelPartnerPanel from './super/ChannelPartnerPanel.vue'
import ManualPaymentPanel from './super/ManualPaymentPanel.vue'

const BASE = '/api/super'

const authed = ref(false)
const pwd = ref('')
const logging = ref(false)
const loginErr = ref('')
const needTotp = ref(false)
const totpCode = ref('')
const totpEnabled = ref(false)
let superToken = ''
const activeTab = ref('merchants')
const pendingPaymentCount = ref(0)

const stats = reactive({ total_merchants: 0, active_merchants: 0, today_orders: 0, today_revenue: 0 })
const merchants = ref([])
const loadingList = ref(false)
const searchQuery = ref('')
const statusFilter = ref('')
const statusFilters = [
  { value: '', label: '全部' },
  { value: 'unconfigured', label: '未配置' },
  { value: 'pending', label: '待验证' },
  { value: 'verified', label: '已验证' },
  { value: 'paused', label: '暂停' },
]
const filteredMerchants = computed(() => {
  const q = searchQuery.value.trim()
  return merchants.value.filter(m => {
    if (statusFilter.value && (m.payment_status || 'unconfigured') !== statusFilter.value) return false
    if (q && !m.name.includes(q) && !(m.phone || '').includes(q)) return false
    return true
  })
})
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
const seedingId = ref('')
const seedResult = ref(null)
const perfStats = ref([])
const perfStatsLoading = ref(false)
const perfStatsError = ref(false)
const revealedPhones = reactive(new Set())
const copySourceId = ref('')
const copyingPay = ref(false)

const copySources = computed(() => merchants.value.filter(m =>
  m.tenant_id !== payConfigTarget.value?.tenant_id && m.wx_mchid_masked && m.wx_mchid_masked !== '-'
))

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
function maskPhone(value) {
  const v = (value || '').trim()
  if (v.length !== 11) return v || '-'
  return `${v.slice(0, 3)}****${v.slice(-4)}`
}
function togglePhone(tenantId) {
  if (revealedPhones.has(tenantId)) revealedPhones.delete(tenantId)
  else revealedPhones.add(tenantId)
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
  if (!needTotp.value && !pwd.value.trim()) return
  if (needTotp.value && !totpCode.value.trim()) return
  logging.value = true
  loginErr.value = ''
  try {
    const res = await axios.post(`${BASE}/login`, { password: pwd.value, totp_code: totpCode.value.trim() || undefined })
    if (res.data?.code === 200) {
      superToken = res.data.data.token
      totpEnabled.value = !!res.data.data.totp_enabled
      authed.value = true
      loadData()
    } else if (res.data?.data?.require_totp) {
      needTotp.value = true
      totpCode.value = ''
      loginErr.value = res.data?.msg || '请输入动态口令'
    } else {
      needTotp.value = false
      totpCode.value = ''
      loginErr.value = res.data?.msg || '登录失败'
    }
  } catch { loginErr.value = '网络错误，请重试' }
  finally { logging.value = false }
}

async function loadPerfStats() {
  perfStatsLoading.value = true
  perfStatsError.value = false
  try {
    const res = await axios.get(`${BASE}/perf-stats`, { params: { days: 7 }, headers: superHeaders() })
    if (res.data?.code === 200) {
      perfStats.value = res.data.data?.stats || []
    } else {
      perfStats.value = []
      perfStatsError.value = true
    }
  } catch (e) {
    if (e?.response?.status === 401) authed.value = false
    else {
      perfStats.value = []
      perfStatsError.value = true
    }
  } finally {
    perfStatsLoading.value = false
  }
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
    loadPerfStats()
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
  copySourceId.value = ''
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

function _promptTotpCode() {
  if (!totpEnabled.value) return ''
  const code = window.prompt('请输入认证器 App 里的 6 位动态口令完成二次验证') || ''
  return code.trim()
}

function confirmCopyPayConfig() {
  if (!copySourceId.value) return
  const source = merchants.value.find(m => m.tenant_id === copySourceId.value)
  const sourceName = source?.name || copySourceId.value
  const targetName = payConfigTarget.value.name
  if (!window.confirm(`确定要把「${sourceName}」的支付配置复制到「${targetName}」吗？\n复制后需要重新点击"验证配置"。`)) return
  const totp = _promptTotpCode()
  if (totpEnabled.value && !totp) return
  copyPayConfig(totp)
}

async function copyPayConfig(totpCodeInput = '') {
  copyingPay.value = true
  payConfigResult.value = null
  try {
    const res = await axios.post(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay/copy-from`, {
      source_tenant_id: copySourceId.value,
      totp_code: totpCodeInput || undefined,
    }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: res.data?.msg || '复制成功，请继续验证配置' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      applyPaymentData(payConfigForm, res.data.data)
      copySourceId.value = ''
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '复制失败' }
  } catch (e) {
    payConfigResult.value = { ok: false, msg: e?.response?.data?.msg || '网络错误，请重试' }
  }
  finally { copyingPay.value = false }
}

function confirmPausePay() {
  if (!window.confirm(`确定要暂停「${payConfigTarget.value.name}」的收款吗？暂停后顾客将无法在线支付。`)) return
  const totp = _promptTotpCode()
  if (totpEnabled.value && !totp) return
  pausePay(totp)
}

async function pausePay(totpCodeInput = '') {
  pausingPay.value = true
  payConfigResult.value = null
  try {
    const res = await axios.patch(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay/pause`, { totp_code: totpCodeInput || undefined }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: '已暂停支付' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      applyPaymentData(payConfigForm, res.data.data)
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '暂停失败' }
  } catch (e) { payConfigResult.value = { ok: false, msg: e?.response?.data?.msg || '暂停失败' } }
  finally { pausingPay.value = false }
}

async function seedTestData(merchant) {
  if (!window.confirm(`确定要给「${merchant.name}」填充测试数据吗？\n会生成菜品、会员、优惠券和近30天的历史订单。`)) return
  seedingId.value = merchant.tenant_id
  seedResult.value = null
  try {
    const res = await axios.post(`${BASE}/merchants/${merchant.tenant_id}/seed-test-data`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) {
      const d = res.data.data
      seedResult.value = { tenant_id: merchant.tenant_id, ok: true, msg: `填充成功：${d.menu_items} 道菜 · ${d.customers} 位会员 · 历史 ${d.history_orders} 单 · 今日 ${d.today_orders} 单` }
    } else seedResult.value = { tenant_id: merchant.tenant_id, ok: false, msg: res.data?.msg || '填充失败' }
  } catch (e) {
    seedResult.value = { tenant_id: merchant.tenant_id, ok: false, msg: e?.response?.data?.msg || '网络错误，请重试' }
  }
  finally { seedingId.value = '' }
}

async function toggleStatus(merchant) {
  try {
    const res = await axios.patch(`${BASE}/merchants/${merchant.tenant_id}/status`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) merchant.status = res.data.data.status
  } catch {}
}

function logout() { superToken = ''; authed.value = false; pwd.value = ''; needTotp.value = false; totpCode.value = '' }
</script>

<style scoped>
* { box-sizing: border-box; }

.super-wrap { min-height: 100vh; background: var(--bg-page); font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; color: var(--text-1); }

/* ─── Login ─────────────────────────────────────────────────── */
.login-box { max-width: 380px; margin: 0 auto; padding: 64px 20px 0; }
.login-card { border-radius: var(--radius-card); background: var(--bg-card); box-shadow: 0 12px 40px rgba(0,0,0,.16); overflow: hidden; }
.login-hero {
  position: relative;
  overflow: hidden;
  padding: 36px 24px 26px;
  text-align: center;
  background: linear-gradient(135deg, var(--hero-dark) 0%, #33335c 100%);
  color: #fff;
}
.login-hero::before {
  content: '';
  position: absolute;
  top: -70px; right: -50px;
  width: 200px; height: 200px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.14), transparent 70%);
}
.login-logo {
  position: relative;
  display: inline-flex; align-items: center; justify-content: center;
  width: 52px; height: 52px; border-radius: 14px;
  background: rgba(255,255,255,.14); color: #fff; font-weight: 900;
  margin-bottom: 12px;
}
.login-title { position: relative; font-size: 20px; font-weight: 900; margin-bottom: 4px; }
.login-sub { position: relative; font-size: 11px; letter-spacing: .12em; color: rgba(255,255,255,.55); font-weight: 700; }
.login-form { padding: 22px 22px 24px; }
.login-input, .form-input { width: 100%; height: 44px; border: 1px solid var(--border); border-radius: 8px; padding: 0 12px; font-size: 14px; outline: none; background: var(--bg-card); color: var(--text-1); }
.login-input { height: 48px; margin-bottom: 12px; }
.totp-hint { font-size: 13px; color: var(--text-2); margin-bottom: 10px; text-align: center; }
.login-input:focus, .form-input:focus { border-color: var(--hero-dark); box-shadow: 0 0 0 2px rgba(26,26,46,.12); }
.login-btn { width: 100%; height: 48px; background: var(--hero-dark); color: #fff; border: 0; border-radius: 8px; font-size: 15px; font-weight: 800; cursor: pointer; }
.create-btn { height: 44px; background: var(--brand); color: #fff; border: 0; border-radius: 8px; font-size: 15px; font-weight: 800; cursor: pointer; }
.login-btn:disabled, .create-btn:disabled, .verify-btn:disabled, .pause-btn:disabled { opacity: .55; cursor: not-allowed; }
.login-err { color: var(--danger); font-size: 13px; margin-top: 8px; }

/* ─── Console body ──────────────────────────────────────────── */
.top-bar { display: flex; justify-content: space-between; align-items: center; padding: 52px 16px 12px; background: var(--hero-dark); color: #fff; }
.top-title { font-size: 18px; font-weight: 900; }
.logout-btn { border: 1px solid rgba(255,255,255,.25); border-radius: 8px; background: rgba(255,255,255,.08); color: #fff; cursor: pointer; padding: 5px 12px; font-size: 13px; }
.console-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 12px 16px 0; background: var(--hero-dark); }
.tab-btn { position: relative; height: 40px; border: 1px solid rgba(255,255,255,.22); border-radius: 8px 8px 0 0; background: rgba(255,255,255,.08); color: rgba(255,255,255,.72); font-weight: 800; cursor: pointer; font-size: 13px; padding: 0 4px; }
.tab-btn.active { background: var(--bg-page); border-color: var(--bg-page); color: var(--text-1); }
.tab-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 16px; height: 16px; margin-left: 4px; padding: 0 4px; border-radius: 999px; background: var(--danger); color: #fff; font-size: 10px; font-weight: 800; vertical-align: middle; }
.refresh-btn, .pay-cfg-btn, .cancel-btn, .fold-btn { border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-2); cursor: pointer; }
.refresh-btn { padding: 5px 12px; font-size: 13px; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); padding: 12px 16px; gap: 8px; }
.stat-card, .section { background: var(--bg-card); border-radius: var(--radius-card); }
.stat-card { padding: 12px 8px; text-align: center; }
.stat-num { font-size: 20px; font-weight: 900; color: var(--text-1); }
.stat-num.green { color: var(--brand); } .stat-num.blue { color: #1677ff; }
.stat-label { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.section { margin: 0 16px 16px; padding: 16px; }
.section-title { font-size: 15px; font-weight: 800; margin-bottom: 12px; color: var(--text-1); }
.title-row { display: flex; align-items: center; justify-content: space-between; }
.create-form { display: grid; gap: 8px; }
.create-result { margin-top: 10px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.create-result.ok { background: var(--brand-light); color: var(--success); } .create-result.err { background: #fef2f2; color: var(--danger); }
.search-input { margin-bottom: 10px; }
.filter-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.filter-chip { height: 30px; padding: 0 12px; border: 1px solid var(--border); border-radius: 999px; background: var(--bg-card); color: var(--text-2); font-size: 12px; font-weight: 700; cursor: pointer; }
.filter-chip.active { border-color: var(--brand); background: var(--brand-light); color: var(--success); }
.loading, .empty { text-align: center; color: var(--text-3); padding: 24px 0; font-size: 14px; }
.perf-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.perf-table th, .perf-table td { padding: 8px 6px; border-bottom: 1px solid var(--border); text-align: left; }
.perf-table th.num, .perf-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.perf-table th { color: var(--text-3); font-weight: 700; font-size: 12px; }
.merchant-list { display: grid; gap: 10px; }
.merchant-card { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 12px; background: var(--bg-page); border-radius: 10px; }
.mc-left { min-width: 0; }
.mc-name { font-size: 15px; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-1); }
.mc-meta { font-size: 12px; color: var(--text-2); margin-top: 3px; }
.phone-reveal { border-bottom: 1px dashed var(--text-3); cursor: pointer; }
.mc-right { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0; }
.mc-badge, .mc-pay-badge, .status-pill { font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 20px; white-space: nowrap; }
.mc-badge.on, .pay-on { background: var(--brand-light); color: var(--success); }
.mc-badge.off { background: #f3f4f6; color: var(--text-2); }
.pay-off { background: #fef9c3; color: #92400e; } .pay-pending { background: #eff6ff; color: #2563eb; } .pay-paused { background: #f3f4f6; color: var(--text-2); }
.toggle-btn { font-size: 12px; padding: 4px 12px; border-radius: 6px; border: 0; cursor: pointer; font-weight: 700; }
.toggle-btn.stop { background: #fef2f2; color: var(--danger); } .toggle-btn.resume { background: var(--brand-light); color: var(--success); }
.mc-pay-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
.pay-cfg-btn { font-size: 11px; padding: 3px 10px; }
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 999; padding: 18px; }
.modal-box { width: min(520px, 100%); max-height: calc(100vh - 36px); overflow-y: auto; background: var(--bg-card); border-radius: 16px; padding: 18px; }
.modal-title { font-size: 17px; font-weight: 900; margin-bottom: 12px; color: var(--text-1); }
.receiver-card { border: 1px solid var(--brand-mid); background: var(--brand-light); border-radius: var(--radius-card); padding: 14px; }
.receiver-head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; margin-bottom: 12px; }
.receiver-kicker { font-size: 12px; color: var(--success); font-weight: 900; }
.receiver-title { font-size: 16px; font-weight: 900; margin-top: 2px; color: var(--text-1); }
.receiver-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.receiver-grid span, .modal-label { display: block; font-size: 12px; color: var(--text-2); margin-bottom: 5px; }
.field-hint { font-size: 11.5px; color: var(--text-3); margin-bottom: 6px; line-height: 1.5; }
.receiver-grid strong { display: block; font-size: 14px; color: var(--text-1); word-break: break-all; }
.lock-text { color: var(--success) !important; }
.safe-tip { margin-top: 12px; padding: 10px; border-radius: 8px; background: var(--bg-card); color: var(--text-2); font-size: 12px; line-height: 1.6; }
.fold-btn { width: 100%; height: 40px; margin-top: 12px; font-weight: 800; }
.tech-box { display: grid; gap: 8px; margin-top: 12px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-card); background: var(--bg-page); }
.copy-box { padding: 10px; margin-bottom: 4px; border: 1px dashed var(--brand-mid); border-radius: 10px; background: var(--brand-light); }
.copy-row { display: flex; gap: 8px; }
.copy-select { flex: 1; height: 40px; }
.copy-btn { flex: none; height: 40px; padding: 0 16px; border: 0; border-radius: 8px; background: var(--brand); color: #fff; font-weight: 800; font-size: 13px; cursor: pointer; }
.copy-btn:disabled { opacity: .55; cursor: not-allowed; }
.pay-radio-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.pay-radio-btn { height: 36px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-2); font-size: 14px; cursor: pointer; }
.pay-radio-btn.selected { border-color: var(--brand); background: var(--brand-light); color: var(--success); font-weight: 800; }
.private-input { height: 148px; padding-top: 10px; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.6; }
.modal-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
.verify-btn, .pause-btn { height: 44px; border: 0; border-radius: 8px; font-weight: 800; cursor: pointer; }
.verify-btn { background: #1677ff; color: #fff; }
.verify-btn--pending { box-shadow: 0 0 0 3px rgba(22,119,255,.28); }
.pause-btn { width: 100%; background: #fef2f2; color: #dc2626; }
.cancel-btn { width: 100%; height: 40px; margin-top: 8px; }
.danger-zone { margin-top: 20px; padding: 12px; border: 1px solid #fecaca; border-radius: var(--radius-card); background: #fff5f5; }
.danger-zone-label { font-size: 11px; font-weight: 800; letter-spacing: .04em; color: #dc2626; margin-bottom: 8px; }
@media (max-width: 420px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
  .merchant-card { align-items: flex-start; }
  .receiver-grid { grid-template-columns: 1fr; }
}
</style>
