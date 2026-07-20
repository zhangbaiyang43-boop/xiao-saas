<template>
  <div class="sub-page settings-detail">
    <PageHeader title="经营设置" />
    <div class="page-body">
      <section class="summary-card">
        <p>顾客现在看到</p>
        <h1>{{ opSettings.is_open ? '正常营业' : '休息中' }}</h1>
        <span>{{ opSettings.business_hours || '未设置营业时间' }}</span>
      </section>

      <section class="panel-card">
        <div class="switch-row">
          <div><strong>营业状态</strong><span>{{ opSettings.is_open ? '顾客可以正常下单' : '顾客会看到休息提示' }}</span></div>
          <a-switch v-model:checked="opSettings.is_open" checked-children="营业" un-checked-children="休息" @change="saveOpSettings" />
        </div>
        <div class="info-row" @click="openOpDrawer">
          <span class="info-label">营业时间</span>
          <span class="info-value">{{ opSettings.business_hours || '点击设置' }} <RightOutlined /></span>
        </div>
        <div class="switch-row">
          <div><strong>到店堂食</strong><span>顾客扫码在店内点餐</span></div>
          <a-switch v-model:checked="opSettings.dine_in_enabled" @change="saveOpSettings" />
        </div>
        <div class="switch-row">
          <div><strong>自提服务</strong><span>顾客线上下单，到店取餐</span></div>
          <a-switch v-model:checked="opSettings.pickup_enabled" @change="saveOpSettings" />
        </div>
        <div class="switch-row" :class="{ last: !opSettings.delivery_enabled }">
          <div><strong>外卖配送</strong><span>{{ opSettings.delivery_enabled ? deliverySummary : '开启后可接收外卖订单' }}</span></div>
          <a-switch v-model:checked="opSettings.delivery_enabled" @change="saveOpSettings" />
        </div>
        <div v-if="opSettings.delivery_enabled" class="delivery-form">
          <a-row :gutter="10">
            <a-col :span="12">
              <a-form-item label="配送费（元）" style="margin:0">
                <a-input-number v-model:value="opSettings.delivery_fee" :min="0" :step="0.5" prefix="¥" style="width:100%" @change="saveOpSettings" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="起送价（元）" style="margin:0">
                <a-input-number v-model:value="opSettings.min_delivery_amount" :min="0" prefix="¥" style="width:100%" @change="saveOpSettings" />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </section>

      <section class="panel-card remark-card">
        <div class="panel-title">下单备注</div>
        <p>顾客下单时点击即可选择，减少反复沟通。</p>
        <div class="chip-list">
          <span v-for="(chip, idx) in opSettings.remark_chips" :key="chip + idx" class="remark-chip">
            {{ chip }} <button @click="removeRemarkChip(idx)">×</button>
          </span>
        </div>
        <div class="add-row">
          <a-input v-model:value="newChipInput" placeholder="输入快捷备注" :maxlength="10" @pressEnter="addRemarkChip" />
          <a-button type="primary" @click="addRemarkChip">添加</a-button>
        </div>
      </section>
    </div>

    <a-drawer v-model:open="showOpDrawer" title="营业时间" placement="bottom" height="auto">
      <div class="drawer-section">
        <div class="drawer-label">常用时段</div>
        <div class="preset-list">
          <span v-for="p in hourPresets" :key="p.value" class="preset-chip" :class="{ active: opForm.open_time + '-' + opForm.close_time === p.value }" @click="applyPreset(p.value)">{{ p.label }}</span>
        </div>
      </div>
      <div class="drawer-section">
        <div class="drawer-label">营业时间</div>
        <div class="time-row">
          <input v-model="opForm.open_time" type="time" class="time-input" />
          <span>至</span>
          <input v-model="opForm.close_time" type="time" class="time-input" />
        </div>
      </div>
      <div class="drawer-section">
        <div class="drawer-label">每周休息</div>
        <div class="day-list">
          <span v-for="d in weekDays" :key="d.value" class="day-chip" :class="{ active: opForm.rest_days.includes(d.value) }" @click="toggleRestDay(d.value)">{{ d.label }}</span>
        </div>
      </div>
      <div class="preview-box"><span>顾客将看到</span><strong>{{ previewHours }}</strong></div>
      <a-button type="primary" block size="large" @click="saveOpDrawer">保存</a-button>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { RightOutlined } from '@ant-design/icons-vue'
import PageHeader from '../../components/PageHeader.vue'
import { getTenantProfile, updateTenantSettings } from '../../api'

const showOpDrawer = ref(false)
const newChipInput = ref('')
const opSettings = ref({
  is_open: true,
  business_hours: '',
  closed_notice: '',
  dine_in_enabled: true,
  pickup_enabled: false,
  delivery_enabled: false,
  delivery_fee: 0,
  min_delivery_amount: 0,
  remark_chips: ['不要辣', '微辣', '不要香菜', '不要葱', '少盐', '打包'],
})
const opForm = ref({ open_time: '10:00', close_time: '22:00', rest_days: [] })
const hourPresets = [
  { label: '10:00-22:00', value: '10:00-22:00' },
  { label: '09:00-21:00', value: '09:00-21:00' },
  { label: '11:00-21:00', value: '11:00-21:00' },
  { label: '08:00-20:00', value: '08:00-20:00' },
  { label: '全天营业', value: '00:00-23:59' },
]
const weekDays = [
  { label: '一', value: '周一' }, { label: '二', value: '周二' }, { label: '三', value: '周三' }, { label: '四', value: '周四' },
  { label: '五', value: '周五' }, { label: '六', value: '周六' }, { label: '日', value: '周日' },
]
const deliverySummary = computed(() => `配送费 ¥${opSettings.value.delivery_fee || 0}，满 ¥${opSettings.value.min_delivery_amount || 0} 起送`)
const previewHours = computed(() => {
  const rest = opForm.value.rest_days.length ? `，${opForm.value.rest_days.join('/')}休息` : '，全周营业'
  return `${opForm.value.open_time}-${opForm.value.close_time}${rest}`
})

async function loadProfile() {
  try {
    const res = await getTenantProfile()
    if (res.code === 200 && res.data) {
      opSettings.value = {
        is_open: res.data.is_open ?? true,
        business_hours: res.data.business_hours || '',
        closed_notice: res.data.closed_notice || '',
        dine_in_enabled: res.data.dine_in_enabled ?? true,
        pickup_enabled: res.data.pickup_enabled ?? false,
        delivery_enabled: res.data.delivery_enabled ?? false,
        delivery_fee: res.data.delivery_fee ?? 0,
        min_delivery_amount: res.data.min_delivery_amount ?? 0,
        remark_chips: res.data.remark_chips ?? ['不要辣', '微辣', '不要香菜', '不要葱', '少盐', '打包'],
      }
    }
  } catch { message.error('经营设置加载失败') }
}

async function saveOpSettings() {
  try {
    const res = await updateTenantSettings(opSettings.value)
    if (res.code === 200) { message.success('已保存'); return }
    message.error(res.msg || '保存失败')
  } catch { message.error('保存失败') }
}

function openOpDrawer() {
  const hours = opSettings.value.business_hours || ''
  const match = hours.match(/(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})/)
  opForm.value.open_time = match ? match[1].padStart(5, '0') : '10:00'
  opForm.value.close_time = match ? match[2].padStart(5, '0') : '22:00'
  const allDays = weekDays.map(d => d.value)
  opForm.value.rest_days = allDays.filter(d => (opSettings.value.closed_notice || '').includes(d))
  showOpDrawer.value = true
}
function applyPreset(value) {
  const [open, close] = value.split('-')
  opForm.value.open_time = open
  opForm.value.close_time = close
}
function toggleRestDay(day) {
  const idx = opForm.value.rest_days.indexOf(day)
  if (idx >= 0) opForm.value.rest_days.splice(idx, 1)
  else opForm.value.rest_days.push(day)
}
async function saveOpDrawer() {
  opSettings.value.business_hours = `${opForm.value.open_time}-${opForm.value.close_time}`
  opSettings.value.closed_notice = opForm.value.rest_days.length ? `${opForm.value.rest_days.join('/')}休息` : ''
  await saveOpSettings()
  showOpDrawer.value = false
}
async function addRemarkChip() {
  const v = newChipInput.value.trim()
  if (!v) return
  if (opSettings.value.remark_chips.includes(v)) { message.warning('已存在'); return }
  opSettings.value.remark_chips.push(v)
  newChipInput.value = ''
  await saveOpSettings()
}
async function removeRemarkChip(idx) {
  opSettings.value.remark_chips.splice(idx, 1)
  await saveOpSettings()
}

onMounted(loadProfile)
</script>

<style scoped>
.settings-detail { min-height: 100vh; background: #f5f6f8; }
.page-body { padding: 12px 16px 28px; }
.summary-card, .panel-card { background: #fff; border: 1px solid #eef2f7; border-radius: 14px; }
.summary-card { padding: 18px; }
.summary-card p, .summary-card h1, .summary-card span { display: block; margin: 0; }
.summary-card p { color: #16a34a; font-size: 12px; font-weight: 900; }
.summary-card h1 { margin-top: 5px; color: #111827; font-size: 22px; font-weight: 900; }
.summary-card span { margin-top: 6px; color: #64748b; font-size: 13px; }
.panel-card { margin-top: 12px; overflow: hidden; }
.switch-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid #f1f5f9; }
.switch-row.last { border-bottom: 0; }
.switch-row strong, .switch-row span { display: block; }
.switch-row strong { color: #111827; font-size: 14px; font-weight: 800; }
.switch-row span { margin-top: 3px; color: #64748b; font-size: 12px; }
.info-row { cursor: pointer; }
.delivery-form { padding: 14px 16px; border-bottom: 1px solid #f1f5f9; }
.panel-title { padding: 14px 16px 0; color: #111827; font-size: 15px; font-weight: 900; }
.remark-card p { margin: 5px 16px 0; color: #64748b; font-size: 12px; }
.chip-list { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 16px; }
.remark-chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 16px; background: #f0fdf4; color: #16a34a; font-size: 13px; font-weight: 700; }
.remark-chip button { border: 0; background: transparent; color: #94a3b8; font-size: 15px; line-height: 1; }
.add-row { display: flex; gap: 8px; padding: 0 16px 16px; }
.drawer-section { margin-bottom: 18px; }
.drawer-label { margin-bottom: 10px; color: #64748b; font-size: 12px; font-weight: 800; }
.preset-list { display: flex; flex-wrap: wrap; gap: 8px; }
.preset-chip { padding: 7px 12px; border: 1px solid #e5e7eb; border-radius: 18px; background: #f8fafc; font-size: 13px; }
.preset-chip.active { border-color: #07c160; background: #f0fdf4; color: #16a34a; font-weight: 800; }
.time-row { display: grid; grid-template-columns: 1fr 32px 1fr; align-items: center; gap: 8px; text-align: center; }
.time-input { width: 100%; height: 46px; border: 1px solid #e5e7eb; border-radius: 10px; padding: 0 10px; font-size: 18px; font-weight: 800; text-align: center; }
.day-list { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }
.day-chip { height: 36px; border: 1px solid #e5e7eb; border-radius: 18px; background: #f8fafc; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; }
.day-chip.active { border-color: #fecaca; background: #fef2f2; color: #ef4444; }
.preview-box { margin-bottom: 18px; padding: 12px; border-radius: 10px; background: #f0fdf4; }
.preview-box span, .preview-box strong { display: block; }
.preview-box span { color: #64748b; font-size: 11px; }
.preview-box strong { margin-top: 4px; color: #111827; font-size: 15px; }
</style>
