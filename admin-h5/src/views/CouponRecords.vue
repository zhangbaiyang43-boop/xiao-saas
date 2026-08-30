<template>
  <div class="coupon-records-page">
    <PageHeader title="发券记录" />

    <div class="page-content">
      <section class="hero-card animate-in" style="animation-delay:.02s">
        <div>
          <p class="eyebrow">发券记录</p>
          <h1>看清每张券发给了谁</h1>
          <p>未使用的券可以收回，已核销的券可追踪到客户。</p>
        </div>
        <button class="refresh-btn tap-shrink" :disabled="loading" @click="refresh">刷新</button>
      </section>

      <section class="summary-grid animate-in" style="animation-delay:.06s">
        <button
          v-for="item in summaryItems"
          :key="item.value"
          :class="['summary-card', 'tap-shrink', { active: filters.status === item.value }]"
          @click="selectStatus(item.value)"
        >
          <strong>{{ item.count }}</strong>
          <span>{{ item.label }}</span>
        </button>
      </section>

      <section class="filter-card animate-in" style="animation-delay:.1s">
        <van-search
          v-model="filters.keyword"
          placeholder="搜手机号、客户名、券码"
          shape="round"
          @search="handleSearch"
          @clear="handleSearch"
        />
        <div class="filter-row">
          <select v-model="filters.status" class="filter-select" @change="handleSearch">
            <option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <select v-model="filters.source" class="filter-select" @change="handleSearch">
            <option v-for="item in sourceOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </div>
      </section>

      <section v-if="loading" class="state-card animate-in" style="animation-delay:.14s">
        <van-loading size="24px" color="var(--brand)">正在加载发券记录</van-loading>
      </section>

      <section v-else-if="hasError" class="state-card animate-in" style="animation-delay:.14s">
        <van-empty :description="errorMsg || '加载失败'">
          <van-button type="primary" size="small" class="tap-shrink" @click="loadRecords">重试</van-button>
        </van-empty>
      </section>

      <section v-else-if="records.length === 0" class="state-card animate-in" style="animation-delay:.14s">
        <van-empty description="暂无发券记录" />
      </section>

      <section v-else class="record-list animate-in" style="animation-delay:.14s">
        <article v-for="record in records" :key="record.id" class="record-card tap-shrink">
          <div class="record-top">
            <div class="customer">
              <strong>{{ record.customer_name || '会员用户' }}</strong>
              <span>{{ record.customer_phone || '-' }}</span>
            </div>
            <CouponStatusTag :status="record.status" />
          </div>

          <div class="coupon-row">
            <div class="coupon-value">
              <strong>￥{{ money(record.value) }}</strong>
              <span>满 {{ money(record.min_amount) }} 可用</span>
            </div>
            <div class="coupon-info">
              <strong>{{ record.template_name || record.coupon_name || '优惠券' }}</strong>
              <span>券码：{{ record.code || '-' }}</span>
            </div>
          </div>

          <div class="record-meta">
            <span><van-icon name="clock-o" /> {{ formatTime(record.created_at) }}</span>
            <span>{{ getSourceText(record.source) }}</span>
          </div>

          <div class="record-actions">
            <van-button
              v-if="record.status === 'UNUSED'"
              round
              plain
              type="danger"
              size="small"
              class="tap-shrink"
              @click="handleRecall(record)"
            >
              收回这张券
            </van-button>
            <van-button round plain type="primary" size="small" class="tap-shrink" @click="goToCustomer(record.customer_id)">
              查看客户
            </van-button>
          </div>
        </article>
      </section>

      <van-pagination
        v-if="pagination.total > pagination.pageSize"
        v-model="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        @change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Button as VanButton,
  Empty as VanEmpty,
  Icon as VanIcon,
  Loading as VanLoading,
  Pagination as VanPagination,
  Search as VanSearch,
  showConfirmDialog,
  showToast
} from 'vant'
import PageHeader from '../components/PageHeader.vue'
import CouponStatusTag from '../components/CouponStatusTag.vue'
import { getIssuedCoupons, recallCoupon } from '../api'
import { formatBeijingDateTime } from '../utils/beijingTime'

const router = useRouter()
const records = ref([])
const loading = ref(false)
const errorMsg = ref('')
const hasError = ref(false)

const pagination = ref({
  page: 1,
  pageSize: 10,
  total: 0
})

const filters = ref({
  keyword: '',
  status: '',
  source: ''
})

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '未使用', value: 'UNUSED' },
  { label: '已使用', value: 'USED' },
  { label: '已过期', value: 'EXPIRED' },
  { label: '已收回', value: 'REVOKED' }
]

const sourceOptions = [
  { label: '全部来源', value: '' },
  { label: '手动发券', value: 'manual' },
  { label: '新客自动发券', value: 'new_customer_coupon' },
  { label: '消费后自动发券', value: 'consumption_coupon' },
  { label: '老客召回券', value: 'recall_coupon' }
]

const summaryItems = computed(() => [
  { label: '全部', value: '', count: pagination.value.total },
  { label: '未使用', value: 'UNUSED', count: countByStatus('UNUSED') },
  { label: '已使用', value: 'USED', count: countByStatus('USED') },
  { label: '已收回', value: 'REVOKED', count: countByStatus('REVOKED') }
])

const countByStatus = (status) => records.value.filter((item) => item.status === status).length

const getApiErrorMessage = (error, fallback = '加载失败，请稍后重试') => {
  const data = error?.response?.data || error?.data
  return data?.msg || data?.message || error?.message || fallback
}

const extractRows = (data) => {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.results)) return data.results
  if (Array.isArray(data?.list)) return data.list
  if (Array.isArray(data?.rows)) return data.rows
  return []
}

const extractTotal = (data) => {
  return Number(data?.total ?? data?.count ?? data?.pagination?.total ?? extractRows(data).length)
}

const money = (value) => Number(value || 0).toFixed(Number(value || 0) % 1 === 0 ? 0 : 2)

const getSourceText = (source) => {
  const map = {
    new_customer_coupon: '新客自动发券',
    consumption_coupon: '消费后自动发券',
    recall_coupon: '老客召回券',
    manual: '手动发券'
  }
  return map[source] || source || '手动发券'
}

const formatTime = (time) => formatBeijingDateTime(time) || '-'

const loadRecords = async () => {
  loading.value = true
  hasError.value = false
  errorMsg.value = ''
  try {
    const params = {
      skip: (pagination.value.page - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize
    }
    if (filters.value.keyword) params.keyword = filters.value.keyword
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.source) params.source = filters.value.source

    const res = await getIssuedCoupons(params)
    if (res.code !== 200) {
      throw new Error(res.msg || '发券记录加载失败')
    }

    records.value = extractRows(res.data)
    pagination.value.total = extractTotal(res.data)
  } catch (error) {
    hasError.value = true
    records.value = []
    pagination.value.total = 0
    errorMsg.value = getApiErrorMessage(error, '发券记录加载失败')
    showToast(errorMsg.value)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.value.page = 1
  loadRecords()
}

const selectStatus = (status) => {
  filters.value.status = status
  handleSearch()
}

const handleRecall = (record) => {
  showConfirmDialog({
    title: '收回优惠券',
    message: '确认收回这张未使用的优惠券吗？收回后顾客将不能再使用。',
    showCancelButton: true
  }).then(async () => {
    try {
      const res = await recallCoupon(record.id, { reason: '商家收回' })
      if (res.code !== 200) {
        throw new Error(res.msg || '收回失败')
      }
      showToast('已收回')
      loadRecords()
    } catch (error) {
      showToast(getApiErrorMessage(error, '收回失败'))
    }
  })
}

const goToCustomer = (customerId) => {
  if (customerId) router.push(`/customers/${customerId}`)
}

const handlePageChange = (page) => {
  pagination.value.page = page
  loadRecords()
}

const refresh = () => {
  pagination.value.page = 1
  loadRecords()
}

onMounted(loadRecords)
</script>

<style scoped>
.coupon-records-page {
  min-height: 100vh;
  box-sizing: border-box;
  background: var(--bg-page);
  color: var(--text-1);
}

.page-content {
  box-sizing: border-box;
  padding: 14px 14px 96px;
}

.hero-card,
.filter-card,
.state-card,
.record-card {
  border-radius: 18px;
  background: var(--bg-card);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 18px;
}

.eyebrow {
  margin: 0 0 5px;
  color: var(--brand-dark);
  font-size: 12px;
  font-weight: 900;
}

.hero-card h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 900;
  letter-spacing: 0;
}

.hero-card p:not(.eyebrow) {
  margin: 6px 0 0;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.45;
}

.refresh-btn {
  height: 34px;
  padding: 0 13px;
  border: 0;
  border-radius: 999px;
  background: var(--brand-light);
  color: var(--brand-dark);
  font-weight: 900;
  flex: 0 0 auto;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.summary-card {
  min-height: 68px;
  border: 1px solid transparent;
  border-radius: 16px;
  background: var(--bg-card);
  text-align: center;
}

.summary-card.active {
  border-color: var(--brand);
  background: var(--brand-light);
}

.summary-card strong,
.summary-card span {
  display: block;
}

.summary-card strong {
  color: var(--text-1);
  font-size: 20px;
  font-weight: 900;
}

.summary-card span {
  margin-top: 4px;
  color: var(--text-2);
  font-size: 12px;
}

.filter-card {
  margin-top: 12px;
  padding: 12px;
}

.filter-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.filter-select {
  width: 100%;
  height: 42px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  color: var(--text-1);
  padding: 0 10px;
  font-size: 14px;
}

.state-card {
  margin-top: 12px;
  padding: 32px 12px;
  text-align: center;
}

.record-list {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.record-card {
  padding: 15px;
}

.record-top,
.record-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.customer {
  min-width: 0;
}

.customer strong,
.customer span,
.coupon-value strong,
.coupon-value span,
.coupon-info strong,
.coupon-info span {
  display: block;
}

.customer strong {
  overflow: hidden;
  color: var(--text-1);
  font-size: 17px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.customer span {
  margin-top: 4px;
  color: var(--text-2);
  font-size: 13px;
}

.coupon-row {
  display: grid;
  grid-template-columns: 118px minmax(0, 1fr);
  margin-top: 14px;
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid #f1e7d7;
  background: #fff8ef;
}
/* .coupon-info 里的文字用 var(--text-1/2)，深色下会变浅；这张卡的暖色底如果不跟着换，
   就会变成浅字配浅底（Phase-06 审计发现）。保留"票券"的暖色识别，只把亮度换到暗色区间。 */
@media (prefers-color-scheme: dark) {
  .coupon-row {
    border-color: rgba(251, 146, 60, .3);
    background: rgba(194, 65, 12, .14);
  }
}

.coupon-value {
  display: grid;
  place-items: center;
  padding: 14px 8px;
  background: linear-gradient(180deg, #ff4d3d, #f5222d);
  color: #fff;
  text-align: center;
}

.coupon-value strong {
  font-size: 28px;
  font-weight: 900;
}

.coupon-value span {
  margin-top: 3px;
  font-size: 12px;
}

.coupon-info {
  min-width: 0;
  padding: 15px 12px;
}

.coupon-info strong {
  overflow: hidden;
  color: var(--text-1);
  font-size: 18px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coupon-info span {
  margin-top: 8px;
  color: var(--text-2);
  font-size: 13px;
  word-break: break-all;
}

.record-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  color: var(--text-2);
  font-size: 12px;
}

.record-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.record-actions {
  justify-content: flex-end;
  margin-top: 12px;
}

:deep(.van-pagination) {
  margin-top: 14px;
}

@media (min-width: 768px) {
  .coupon-records-page {
    max-width: 760px;
    margin: 0 auto;
  }
}
</style>
