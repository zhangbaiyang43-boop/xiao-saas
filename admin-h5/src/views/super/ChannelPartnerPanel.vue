<template>
  <div class="channel-panel">
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-num">{{ totalCount }}</div>
        <div class="stat-label">渠道伙伴总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-num green">{{ activeCount }}</div>
        <div class="stat-label">合作中</div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">新建渠道伙伴</div>
      <div class="create-form">
        <input v-model.trim="form.name" class="form-input" placeholder="* 姓名" />
        <input v-model.trim="form.mobile" class="form-input" inputmode="numeric" maxlength="11" placeholder="* 手机号" />
        <select v-model="form.partner_type" class="form-input">
          <option v-for="item in partnerTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <select v-model="form.status" class="form-input">
          <option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <button class="create-btn tap-shrink" :disabled="creating" @click="submitPartner">
          {{ creating ? '创建中...' : '+ 新建渠道伙伴' }}
        </button>
      </div>
      <div v-if="formMessage" class="create-result" :class="formMessage.ok ? 'ok' : 'err'">{{ formMessage.msg }}</div>
      <div v-if="createdPartner" class="created-code">系统编号：{{ createdPartner.partner_code }}</div>
    </div>

    <div class="section">
      <div class="section-title title-row">
        <span>渠道伙伴列表（{{ partners.length }}）</span>
        <button class="refresh-btn tap-shrink" :disabled="loading" @click="loadPartners">{{ loading ? '刷新中...' : '刷新' }}</button>
      </div>

      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="loadError" class="empty error-state">
        <div>{{ loadError }}</div>
        <button class="refresh-btn tap-shrink" @click="loadPartners">重新加载</button>
      </div>
      <div v-else-if="!partners.length" class="empty">暂无渠道伙伴</div>
      <div v-else class="partner-list">
        <div v-for="partner in partners" :key="partner.id" class="partner-card">
          <div class="partner-main">
            <div class="partner-name">{{ partner.name || '未命名渠道' }}</div>
            <div class="partner-meta">{{ maskPhone(partner.mobile) }} · {{ partnerTypeText(partner.partner_type) }}</div>
            <div class="partner-meta">编号 {{ partner.partner_code || '-' }}</div>
            <div class="partner-meta">创建 {{ formatDateTime(partner.created_at) }}</div>
          </div>
          <span class="status-pill" :class="statusClass(partner.status)">{{ statusText(partner.status) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { createChannelPartner, listChannelPartners } from '../../api/superChannel'

const props = defineProps({
  superToken: { type: String, required: true },
})

const partnerTypeOptions = [
  { value: 'WINE_SALES', label: '酒水渠道' },
  { value: 'PAYMENT_AGENT', label: '支付/POS' },
  { value: 'PRINTING', label: '打印设备' },
  { value: 'FOOD_SUPPLIER', label: '食材供应' },
  { value: 'ADVERTISING', label: '广告物料' },
  { value: 'EQUIPMENT', label: '餐饮设备' },
  { value: 'DECORATION', label: '装修' },
  { value: 'FINANCE_TAX', label: '财税' },
  { value: 'KITCHEN_SUPPLIER', label: '本地生活服务' },
  { value: 'OTHER', label: '其他' },
]

const statusOptions = [
  { value: 'ACTIVE', label: '合作中' },
  { value: 'SUSPENDED', label: '暂停新增' },
  { value: 'DISABLED', label: '已停用' },
]

const partners = ref([])
const loading = ref(false)
const creating = ref(false)
const loadError = ref('')
const formMessage = ref(null)
const createdPartner = ref(null)
const form = reactive({
  name: '',
  mobile: '',
  partner_type: 'OTHER',
  status: 'ACTIVE',
})

const totalCount = computed(() => partners.value.length)
const activeCount = computed(() => partners.value.filter(item => item.status === 'ACTIVE').length)

function statusText(status) {
  return { ACTIVE: '合作中', SUSPENDED: '暂停新增', DISABLED: '已停用' }[status] || status || '-'
}

function statusClass(status) {
  return { ACTIVE: 'on', SUSPENDED: 'warn', DISABLED: 'off' }[status] || 'off'
}

function partnerTypeText(type) {
  return partnerTypeOptions.find(item => item.value === type)?.label || '其他'
}

function maskPhone(value) {
  const phone = String(value || '').trim()
  if (phone.length !== 11) return phone ? `${phone.slice(0, 3)}****` : '-'
  return `${phone.slice(0, 3)}****${phone.slice(-4)}`
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16).replace('T', ' ')
  const pad = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function validateForm() {
  if (!form.name.trim()) return '请填写姓名'
  if (!/^1\d{10}$/.test(form.mobile)) return '请输入 11 位中国大陆手机号'
  if (!partnerTypeOptions.some(item => item.value === form.partner_type)) return '请选择渠道类型'
  if (!statusOptions.some(item => item.value === form.status)) return '请选择状态'
  return ''
}

async function loadPartners() {
  if (!props.superToken) {
    loadError.value = '请先登录平台中控台'
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const res = await listChannelPartners(props.superToken)
    if (res.data?.code === 200) partners.value = res.data.data || []
    else loadError.value = res.data?.msg || '渠道伙伴加载失败'
  } catch (e) {
    loadError.value = e?.response?.data?.msg || '渠道伙伴加载失败，请重试'
  } finally {
    loading.value = false
  }
}

async function submitPartner() {
  const error = validateForm()
  if (error) {
    formMessage.value = { ok: false, msg: error }
    return
  }
  creating.value = true
  formMessage.value = null
  createdPartner.value = null
  try {
    const res = await createChannelPartner(props.superToken, {
      name: form.name.trim(),
      mobile: form.mobile.trim(),
      partner_type: form.partner_type,
      status: form.status,
    })
    if (res.data?.code === 200) {
      createdPartner.value = res.data.data
      formMessage.value = { ok: true, msg: '渠道伙伴已创建' }
      form.name = ''
      form.mobile = ''
      form.partner_type = 'OTHER'
      form.status = 'ACTIVE'
      await loadPartners()
    } else {
      formMessage.value = { ok: false, msg: res.data?.msg || '创建失败' }
    }
  } catch (e) {
    formMessage.value = { ok: false, msg: e?.response?.data?.msg || '创建失败，请重试' }
  } finally {
    creating.value = false
  }
}

onMounted(loadPartners)
</script>

<style scoped>
.channel-panel { display: block; }
.stat-row { display: grid; grid-template-columns: repeat(2, 1fr); padding: 12px 16px; gap: 8px; }
.stat-card, .section { background: var(--bg-card); border-radius: var(--radius-card); }
.stat-card { padding: 12px 8px; text-align: center; }
.stat-num { font-size: 20px; font-weight: 900; color: var(--text-1); }
.stat-num.green { color: var(--brand); }
.stat-label { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.section { margin: 0 16px 16px; padding: 16px; }
.section-title { font-size: 15px; font-weight: 800; margin-bottom: 12px; color: var(--text-1); }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.create-form { display: grid; gap: 8px; }
.form-input { width: 100%; height: 44px; border: 1px solid var(--border); border-radius: 8px; padding: 0 12px; font-size: 14px; outline: none; background: var(--bg-card); color: var(--text-1); }
.form-input:focus { border-color: var(--hero-dark); box-shadow: 0 0 0 2px rgba(26,26,46,.12); }
.create-btn { height: 44px; background: var(--brand); color: #fff; border: 0; border-radius: 8px; font-size: 15px; font-weight: 800; cursor: pointer; }
.create-btn:disabled, .refresh-btn:disabled { opacity: .55; cursor: not-allowed; }
.refresh-btn { border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-2); cursor: pointer; padding: 5px 12px; font-size: 13px; white-space: nowrap; }
.create-result { margin-top: 10px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.create-result.ok { background: var(--brand-light); color: var(--success); }
.create-result.err { background: #fef2f2; color: var(--danger); }
.created-code { margin-top: 8px; color: var(--text-2); font-size: 12px; }
.loading, .empty { text-align: center; color: var(--text-3); padding: 24px 0; font-size: 14px; }
.error-state { display: grid; justify-items: center; gap: 10px; }
.partner-list { display: grid; gap: 10px; }
.partner-card { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; padding: 12px; background: var(--bg-page); border-radius: 10px; }
.partner-main { min-width: 0; }
.partner-name { font-size: 15px; font-weight: 800; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.partner-meta { font-size: 12px; color: var(--text-2); margin-top: 3px; word-break: break-all; }
.status-pill { flex-shrink: 0; font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 20px; white-space: nowrap; }
.status-pill.on { background: var(--brand-light); color: var(--success); }
.status-pill.warn { background: #fef9c3; color: #92400e; }
.status-pill.off { background: #f3f4f6; color: var(--text-2); }
@media (max-width: 420px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
