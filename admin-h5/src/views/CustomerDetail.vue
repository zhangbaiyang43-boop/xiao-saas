<template>
  <div class="sub-page">
    <PageHeader title="会员详情">
      <a-button type="text" size="small" @click="loadAll" :loading="loading" style="color:var(--brand)">刷新</a-button>
    </PageHeader>

    <template v-if="loading">
      <div class="member-card member-card--skeleton">
        <a-skeleton active avatar :title="{ width: '40%' }" :paragraph="{ rows: 1, width: '60%' }" />
      </div>
      <div class="page-body">
        <a-skeleton active :paragraph="{ rows: 2 }" style="background:var(--bg-card);border-radius:var(--radius-card);padding:16px;margin-bottom:12px" />
        <a-skeleton active :paragraph="{ rows: 3 }" style="background:var(--bg-card);border-radius:var(--radius-card);padding:16px" />
      </div>
    </template>

    <template v-else>
      <!-- 会员卡 -->
      <div class="member-card animate-in" :class="{ 'member-card--inactive': !isActive }">
        <div class="m-avatar"><UserOutlined style="font-size:28px;color:#fff" /></div>
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:22px;font-weight:800;color:#fff">{{ customer.name || '微信会员' }}</span>
            <a-tag :color="isActive ? 'success' : 'error'" size="small">{{ isActive ? '正常' : '已停用' }}</a-tag>
          </div>
          <div style="font-size:14px;color:rgba(255,255,255,.7);margin-bottom:8px">{{ customer.phone || '未留手机号' }}</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <span class="m-tag">{{ account.level_name || '普通会员' }}</span>
            <span class="m-tag">{{ sourceText }}</span>
          </div>
        </div>
      </div>

      <div class="page-body">
        <!-- 停用提醒 -->
        <a-alert v-if="!isActive" type="error" message="这个会员当前已停用" description="顾客扫码或手机号登录时会提示会员已停用，请联系商家。" show-icon style="margin-bottom:12px;border-radius:10px" />

        <!-- 统计数字 -->
        <a-card :bordered="false" class="animate-in" style="margin-bottom:12px">
          <div class="stat-grid">
            <div class="stat-cell"><span class="stat-num" style="color:var(--brand)">{{ availableCouponCount }}</span><span class="stat-label">可用券</span></div>
            <div class="stat-cell"><span class="stat-num">{{ account.points_balance || 0 }}</span><span class="stat-label">积分</span></div>
            <div class="stat-cell"><span class="stat-num">¥{{ money(account.total_consumption) }}</span><span class="stat-label">累计消费</span></div>
          </div>
        </a-card>

        <!-- 操作按钮 -->
        <a-card :bordered="false" class="animate-in" style="margin-bottom:12px;animation-delay:.04s">
          <div style="display:grid;gap:8px">
            <a-button type="primary" block size="large" @click="openSendDialog">
              <template #icon><GiftOutlined /></template>给他发券
            </a-button>
            <a-button block @click="router.push({ path: '/consumptions', query: { customer_id: route.params.id } })">
              <template #icon><ShoppingCartOutlined /></template>看消费记录
            </a-button>
            <a-button v-if="isActive" danger block @click="disableCustomer">停用会员</a-button>
            <a-button v-else block @click="restore" style="color:var(--success);border-color:var(--success)">恢复会员</a-button>
          </div>
        </a-card>

        <!-- 基础信息 -->
        <a-card :bordered="false" title="基础信息" class="animate-in" style="margin-bottom:12px;animation-delay:.08s" :body-style="{ padding: 0 }">
          <div class="info-row"><span class="info-label">会员卡号</span><span class="info-value">{{ customer.store_member_no ? formatMemberNo(customer.store_member_no) : '-' }}</span></div>
          <div class="info-row"><span class="info-label">会员 </span><span class="info-value">{{ customer.id || '-' }}</span></div>
          <div class="info-row"><span class="info-label">手机号</span><span class="info-value">{{ customer.phone || '-' }}</span></div>
          <div class="info-row"><span class="info-label">来源入口</span><span class="info-value">{{ sourceText }}</span></div>
          <div class="info-row"><span class="info-label">加入时间</span><span class="info-value">{{ formatDate(customer.created_at) }}</span></div>
          <div class="info-row"><span class="info-label">最近消费</span><span class="info-value">{{ formatDate(customer.last_consume_time || account.last_consume_time) }}</span></div>
        </a-card>

        <!-- 他的券 -->
        <a-card :bordered="false" title="他的优惠券" class="animate-in" style="margin-bottom:12px;animation-delay:.12s" :body-style="{ padding: 0 }">
          <div v-if="couponError" @click="loadCoupons" style="padding:20px;text-align:center;color:var(--danger);cursor:pointer;font-size:13px">优惠券加载失败，点这里重试</div>
          <a-empty v-else-if="customerCoupons.length === 0" description="暂无优惠券" style="padding:24px 0" />
          <template v-else>
            <div v-for="coupon in customerCoupons.slice(0,20)" :key="coupon.id" class="coupon-row">
              <div class="coupon-face" :class="{ 'coupon-face--used': coupon.status !== 'UNUSED' }">
                <div style="font-size:20px;font-weight:900">¥{{ money(coupon.value || coupon.amount || coupon.coupon_amount) }}</div>
                <div style="font-size:10px;opacity:.9">优惠券</div>
              </div>
              <div style="flex:1;min-width:0">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
                  <span style="font-size:14px;font-weight:600;color:var(--text-1)">{{ coupon.template_name || coupon.name || '优惠券' }}</span>
                  <a-tag v-if="coupon.rule_type" size="small" :color="ruleTypeColor(coupon.rule_type)">{{ ruleTypeLabel(coupon.rule_type) }}</a-tag>
                </div>
                <div style="font-size:12px;color:var(--text-2);margin-bottom:2px">
                  {{ coupon.min_amount > 0 ? `满¥${coupon.min_amount}减¥${money(coupon.value || coupon.amount)}` : `无门槛减¥${money(coupon.value || coupon.amount)}` }}
                </div>
                <div style="font-size:11px;color:var(--text-3)">
                  发放 {{ formatDate(coupon.created_at) }}
                  <span v-if="coupon.expire_time"> · 到期 {{ formatDate(coupon.expire_time) }}</span>
                  <span v-if="coupon.use_time"> · 使用于 {{ formatDate(coupon.use_time) }}</span>
                </div>
                <div style="font-size:11px;color:var(--text-3);margin-top:1px">券码 {{ coupon.code || coupon.coupon_code || '-' }}</div>
              </div>
              <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
                <a-tag :color="coupon.status === 'UNUSED' ? 'success' : 'default'" size="small">{{ couponStatusText(coupon.status) }}</a-tag>
                <a-button
                  v-if="coupon.status === 'UNUSED'"
                  danger size="small" type="text"
                  @click="doRecallCoupon(coupon)"
                >作废</a-button>
              </div>
            </div>
          </template>
        </a-card>

        <!-- 消费记录 -->
        <a-card :bordered="false" title="消费记录" class="animate-in" style="margin-bottom:12px;animation-delay:.16s" :body-style="{ padding: 0 }">
          <div v-if="consumptionError" @click="loadConsumptions" style="padding:20px;text-align:center;color:var(--danger);cursor:pointer;font-size:13px">消费记录加载失败，点这里重试</div>
          <a-empty v-else-if="consumptions.length === 0" description="暂无消费记录" style="padding:24px 0" />
          <template v-else>
            <div v-for="item in consumptions.slice(0,5)" :key="item.id" class="info-row">
              <div>
                <div style="font-size:14px;font-weight:600;color:var(--text-1)">{{ item.project || '到店消费' }}</div>
                <div style="font-size:12px;color:var(--text-2);margin-top:2px">{{ formatDate(item.consume_time || item.created_at) }}</div>
              </div>
              <span style="font-size:16px;font-weight:700;color:var(--danger)">¥{{ money(item.amount) }}</span>
            </div>
          </template>
        </a-card>

        <!-- 操作记录 -->
        <a-card :bordered="false" title="操作记录" class="animate-in" style="margin-bottom:12px;animation-delay:.2s" :body-style="{ padding: 0 }">
          <div v-if="operationLogError" @click="loadOperationLogs" style="padding:20px;text-align:center;color:var(--danger);cursor:pointer;font-size:13px">加载失败，点这里重试</div>
          <a-empty v-else-if="operationLogs.length === 0" description="暂无操作记录" style="padding:24px 0" />
          <template v-else>
            <div v-for="log in operationLogs" :key="log.id" class="timeline-row">
              <div class="timeline-dot" />
              <div style="flex:1">
                <div style="font-size:14px;font-weight:600;color:var(--text-1)">{{ operationTitle(log) }}</div>
                <div style="font-size:12px;color:var(--text-2);margin-top:2px">{{ operationDesc(log) }}</div>
                <div style="font-size:11px;color:var(--text-3);margin-top:4px">{{ formatDate(log.created_at) }}</div>
              </div>
            </div>
          </template>
        </a-card>
      </div>

      <!-- 发券 Drawer -->
      <a-drawer v-model:open="showSendDrawer" title="给会员发券" placement="bottom" height="auto"
        @afterOpenChange="v => { document.body.style.overflow = v ? 'hidden' : '' }">
        <div style="margin-bottom:16px">
          <div style="font-size:13px;color:var(--text-2);margin-bottom:8px">选择优惠券</div>
          <a-select v-model:value="sendData.couponId" placeholder="请选择一张优惠券" style="width:100%" size="large">
            <a-select-option v-for="t in availableTemplates" :key="t.id" :value="String(t.id)">
              {{ t.name }} - ¥{{ money(t.value || t.amount) }}
            </a-select-option>
          </a-select>
        </div>
        <div class="info-row" style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:16px">
          <span class="info-label">发给</span>
          <span class="info-value">{{ customer.name || '微信会员' }} · {{ customer.phone || '未留手机号' }}</span>
        </div>
        <a-button type="primary" block size="large" :loading="sending" @click="submitSend">确认发给这个会员</a-button>
      </a-drawer>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { UserOutlined, GiftOutlined, ShoppingCartOutlined } from '@ant-design/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import {
  getConsumptions, getCouponTemplates, getCustomer, getCustomerCoupons,
  getCustomerMembership, getCustomerOperationLogs, recallCoupon, restoreCustomer, sendCoupons, updateCustomerStatus,
} from '../api'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const customer = ref({})
const membership = ref({ account: {} })
const customerCoupons = ref([])
const consumptions = ref([])
const templates = ref([])
const operationLogs = ref([])
const couponError = ref(false)
const consumptionError = ref(false)
const operationLogError = ref(false)
const showSendDrawer = ref(false)
const sending = ref(false)
const sendData = reactive({ couponId: '' })

const account = computed(() => membership.value.account || {})
const isActive = computed(() => Number(customer.value.status) === 1)
const availableCouponCount = computed(() => customerCoupons.value.filter(i => i.status === 'UNUSED').length)
const availableTemplates = computed(() => templates.value.filter(i => Number(i.status) === 1))

const sourceText = computed(() => {
  const s = customer.value.source_name || customer.value.entrance_name || customer.value.source || customer.value.source_channel
  return { miniapp: '小程序入会', WECHAT_MINI: '小程序入会', wechat_mini: '小程序入会', PHONE: '手机号', WEWORK: '企业微信', DOUYIN: '抖音' }[s] || s || '扫码入会'
})

function apiData(res) { return res?.data || res || {} }
function extractRows(data) {
  if (Array.isArray(data)) return data
  return data?.items || data?.results || data?.list || data?.data || []
}
function money(v) { const n = Number(v || 0); return Number.isInteger(n) ? n : n.toFixed(2) }
function formatMemberNo(no) { return String(no).padStart(6, '0') }
function formatDate(v) {
  if (!v) return '-'
  const d = new Date(v)
  if (isNaN(d.getTime())) return String(v).substring(0, 16)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
function couponStatusText(s) { return { UNUSED: '可用', USED: '已使用', EXPIRED: '已过期', REVOKED: '已收回' }[s] || s || '-' }
function ruleTypeLabel(r) { return { entry_coupon: '进店券', consumption_coupon: '复购券', new_customer_coupon: '新客券', recall_coupon: '召回券' }[r] || r }
function ruleTypeColor(r) { return { entry_coupon: 'blue', consumption_coupon: 'green', new_customer_coupon: 'orange', recall_coupon: 'purple' }[r] || 'default' }
function operationTitle(log) {
  return { merchant_create_customer: '后台新增会员', merchant_update_customer: '修改会员资料', merchant_disable_customer: '停用会员', merchant_restore_customer: '恢复会员', miniapp_join_success: '小程序入会' }[log.action] || log.detail?.message || log.action || '会员操作'
}
function operationDesc(log) {
  const d = log.detail || {}
  if (d.message) return d.message
  if (d.before_status !== undefined || d.after_status !== undefined) return `状态从 ${d.before_status ?? '-'} 改为 ${d.after_status ?? '-'}`
  return log.actor_name || log.source || '-'
}

async function loadCustomer() {
  const res = await getCustomer(route.params.id)
  if (res.code !== 200) { message.error(res.msg || '会员资料加载失败'); return }
  customer.value = apiData(res)
  if (Array.isArray(customer.value.operation_logs)) operationLogs.value = customer.value.operation_logs
}
async function loadMembership() { try { const res = await getCustomerMembership(route.params.id); membership.value = res.code === 200 ? apiData(res) : { account: {} } } catch { membership.value = { account: {} } } }
async function loadCoupons() { couponError.value = false; try { const res = await getCustomerCoupons({ customer_id: route.params.id, page: 1, page_size: 100 }); customerCoupons.value = res.code === 200 ? extractRows(apiData(res)) : [] } catch { couponError.value = true } }
async function loadConsumptions() { consumptionError.value = false; try { const res = await getConsumptions({ customer_id: route.params.id, page: 1, page_size: 20 }); consumptions.value = res.code === 200 ? extractRows(apiData(res)) : [] } catch { consumptionError.value = true } }
async function loadOperationLogs() { operationLogError.value = false; try { const res = await getCustomerOperationLogs(route.params.id, { skip: 0, limit: 50 }); operationLogs.value = res.code === 200 ? extractRows(apiData(res)) : [] } catch { operationLogError.value = true } }
async function loadTemplates() { try { const res = await getCouponTemplates({ page: 1, page_size: 100 }); templates.value = res.code === 200 ? extractRows(apiData(res)) : [] } catch { templates.value = [] } }

async function doRecallCoupon(coupon) {
  Modal.confirm({
    title: '确认作废这张券？',
    content: `${coupon.template_name || '优惠券'} ¥${money(coupon.value || coupon.amount || coupon.coupon_amount)}，作废后不可恢复`,
    okText: '作废', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      const res = await recallCoupon(coupon.id, { reason: '后台手动作废' })
      if (res.code === 200) { message.success('已作废'); await loadCoupons() }
      else message.error(res.msg || '作废失败')
    },
  })
}

async function loadAll() {
  loading.value = true
  await Promise.allSettled([loadCustomer(), loadMembership(), loadCoupons(), loadConsumptions(), loadTemplates(), loadOperationLogs()])
  loading.value = false
}

function openSendDialog() { sendData.couponId = ''; showSendDrawer.value = true }

async function submitSend() {
  if (!sendData.couponId) { message.warning('请选择优惠券'); return }
  sending.value = true
  try {
    const res = await sendCoupons({ template_id: String(sendData.couponId), customer_ids: [String(route.params.id)] })
    const data = apiData(res)
    if (res.code === 200 && Number(data.success_count || data.count || 0) > 0) { message.success('发券成功'); showSendDrawer.value = false; await loadCoupons(); return }
    message.error(data.reason || res.msg || '发券失败')
  } catch { message.error('发券失败，请检查优惠券是否上架') }
  finally { sending.value = false }
}

function disableCustomer() {
  Modal.confirm({
    title: '停用会员',
    content: '停用后顾客将无法扫码入会或使用优惠券，历史消费和积分记录会完整保留。',
    okText: '停用',
    okType: 'danger',
    onOk: async () => {
      const res = await updateCustomerStatus(route.params.id, { status: -1 })
      if (res.code === 200) { message.success('已停用'); await loadAll() }
      else message.error(res.msg || '停用失败')
    },
  })
}

function restore() {
  Modal.confirm({
    title: '恢复会员',
    content: '恢复后，顾客可以重新登录小程序、查看优惠券并正常核销。',
    okText: '恢复',
    onOk: async () => {
      const res = await restoreCustomer(route.params.id)
      if (res.code === 200) { message.success('已恢复'); await loadAll() }
      else message.error(res.msg || '恢复失败')
    },
  })
}

onMounted(loadAll)
</script>

<style scoped lang="scss">
.member-card {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 24px 16px 32px;
  margin-bottom: -20px;
  background: linear-gradient(135deg, #2b2b48 0%, var(--hero-dark) 55%, #101020 100%);
  border-radius: 0 0 28px 28px;
  overflow: hidden;
  isolation: isolate;
  &::before {
    // 跟主页 hero-header 同款柔光，两处的"卡片头部"要看起来是同一套语言
    content: '';
    position: absolute;
    top: -40%; right: -20%;
    width: 70%; height: 140%;
    background: radial-gradient(circle, rgba(255,255,255,.14) 0%, transparent 65%);
    pointer-events: none;
    z-index: -1;
  }
  &--inactive {
    background: linear-gradient(135deg, #5b6472 0%, #475569 55%, #2f3947 100%);
  }
  &--skeleton {
    display: block;
    padding: 24px 16px 32px;
    :deep(.ant-skeleton-avatar) { width: 54px; height: 54px; border-radius: 18px; }
  }
}
// page-body 紧跟在会员卡后面时叠上去，复现主页 hero 的悬浮卡片效果
.member-card + .page-body { position: relative; z-index: 1; }
.m-avatar {
  width: 54px; height: 54px; border-radius: 18px;
  background: rgba(255,255,255,.2);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.m-tag { padding: 3px 8px; border-radius: 20px; background: rgba(255,255,255,.18); color: #fff; font-size: 12px; }

.coupon-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.coupon-face {
  width: 72px; height: 54px; border-radius: 10px;
  // 跟优惠券中心的券面同一个渐变，保证同一张券在两处看起来是同一个东西
  background: linear-gradient(135deg, #ff4d4f, #ff7a45);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0;
  &--used { background: linear-gradient(135deg, #c8ccd4, #9aa5b5); }
}

.timeline-row {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.timeline-dot {
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--brand); flex-shrink: 0; margin-top: 5px;
}
</style>
