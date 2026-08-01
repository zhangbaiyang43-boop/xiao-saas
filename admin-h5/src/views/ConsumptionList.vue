<template>
  <div class="consumption-page">
    <PageHeader title="消费记录" />

    <div class="page-content">
      <section class="hero-card animate-in" style="animation-delay:.02s">
        <div>
          <p class="eyebrow">消费记录</p>
          <h1>顾客到店，记一笔消费</h1>
          <p>录入消费后，系统可继续触发消费后券、积分或后续营销则。</p>
        </div>
        <van-button round type="primary" class="tap-shrink" :loading="saving" @click="openCreate">新增消费</van-button>
      </section>

      <section class="quick-card animate-in" style="animation-delay:.06s">
        <div class="panel-head">
          <div>
            <p class="eyebrow">快速记账</p>
            <h2>常用金额</h2>
          </div>
        </div>
        <div class="quick-grid">
          <button v-for="amount in quickAmounts" :key="amount" class="tap-shrink" @click="openCreate({ amount })">
            ￥{{ amount }}
          </button>
        </div>
      </section>

      <section class="filter-card animate-in" style="animation-delay:.1s">
        <div class="panel-head">
          <div>
            <p class="eyebrow">筛选</p>
            <h2>查某个顾客的消费</h2>
          </div>
          <button class="text-btn tap-shrink" @click="resetQuery">重置</button>
        </div>

        <van-field
          v-model="query.customer_name"
          label="顾客"
          placeholder="选择顾客"
          readonly
          is-link
          @click="openCustomerPicker('filter')"
        />
        <div class="date-row">
          <van-field v-model="query.start_date" type="date" label="开始" placeholder="开始日期" />
          <van-field v-model="query.end_date" type="date" label="结束" placeholder="结束日期" />
        </div>
        <van-button block round type="primary" class="tap-shrink" :loading="loading" @click="submitSearch">查询消费</van-button>
      </section>

      <section class="list-panel animate-in" style="animation-delay:.14s">
        <div class="panel-head">
          <div>
            <p class="eyebrow">最近消费</p>
            <h2>门店记账流水</h2>
          </div>
          <button class="text-btn tap-shrink" :disabled="loading" @click="loadConsumptions">刷新</button>
        </div>

        <div v-if="loading" class="state-card">
          <van-loading size="24px" color="var(--brand)">正在加载消费记录</van-loading>
        </div>

        <div v-else-if="consumptions.length === 0" class="state-card">
          <van-empty description="暂无消费记录">
            <van-button round type="primary" size="small" class="tap-shrink" @click="openCreate">新增第一笔消费</van-button>
          </van-empty>
        </div>

        <div v-else class="record-list">
          <article v-for="item in consumptions" :key="item.id" class="record-card tap-shrink">
            <div class="record-main">
              <strong>{{ item.project || '到店消费' }}</strong>
              <span>{{ customerName(item.customer_id) }} · {{ formatDateTime(item.consume_time || item.created_at) }}</span>
              <em v-if="item.remark">{{ item.remark }}</em>
            </div>
            <div class="record-amount">￥{{ formatMoney(item.amount) }}</div>
          </article>
        </div>

        <van-pagination
          v-if="pagination.total > pagination.pageSize"
          v-model="pagination.page"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          @change="handlePageChange"
        />
      </section>
    </div>

    <van-popup v-model:show="showCreatePopup" position="bottom" round :style="{ height: '82%' }">
      <div class="form-popup">
        <div class="form-header">
          <h2>新增消费</h2>
          <p>选择顾客，填写消费项目和金额。</p>
        </div>

        <div class="form-body">
          <van-field
            v-model="form.customer_name"
            label="顾客"
            placeholder="选择顾客"
            readonly
            is-link
            @click="openCustomerPicker('form')"
          />
          <van-field v-model.trim="form.project" label="项目" placeholder="例如：羊肉汤、套餐、洗头" />
          <van-field v-model="form.amount" label="金额" type="number" placeholder="输入消费金额" />
          <div class="quick-projects">
            <button v-for="item in quickProjects" :key="item" class="tap-shrink" @click="form.project = item">{{ item }}</button>
          </div>
          <van-field v-model.trim="form.remark" label="备注" placeholder="可选" />
        </div>

        <div class="form-footer">
          <van-button block round @click="showCreatePopup = false">取消</van-button>
          <van-button block round type="primary" class="tap-shrink" :loading="saving" @click="onSubmit">保存消费</van-button>
        </div>
      </div>
    </van-popup>

    <van-popup v-model:show="showCustomerPicker" position="bottom" round>
      <van-picker
        title="选择顾客"
        :columns="customerColumns"
        @confirm="onCustomerSelect"
        @cancel="showCustomerPicker = false"
      />
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  Button as VanButton,
  Empty as VanEmpty,
  Field as VanField,
  Loading as VanLoading,
  Pagination as VanPagination,
  Picker as VanPicker,
  Popup as VanPopup,
  showToast
} from 'vant'
import PageHeader from '../components/PageHeader.vue'
import { createConsumption, getCustomers, getConsumptions } from '../api'

const route = useRoute()

const loading = ref(false)
const saving = ref(false)
const showCreatePopup = ref(false)
const showCustomerPicker = ref(false)
const customerPickerMode = ref('filter')

const quickAmounts = [10, 15, 20, 30, 50, 100]
const quickProjects = ['羊肉汤', '套餐', '加菜', '到店消费']

const query = ref({
  customer_id: '',
  customer_name: '',
  start_date: '',
  end_date: ''
})

const pagination = ref({
  page: 1,
  pageSize: 10,
  total: 0
})

const form = ref({
  project: '',
  customer_id: '',
  customer_name: '',
  amount: '',
  remark: ''
})

const customers = ref([])
const consumptions = ref([])

const customerColumns = computed(() =>
  customers.value.map((item) => ({
    text: customerLabel(item),
    value: String(item.id)
  }))
)

const rowsFrom = (payload) => {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.results)) return payload.results
  if (Array.isArray(payload?.data)) return payload.data
  return []
}

const totalFrom = (payload) => {
  return Number(payload?.total ?? payload?.count ?? payload?.pagination?.total ?? rowsFrom(payload).length)
}

const maskPhone = (phone) => {
  if (!phone) return '-'
  return String(phone).replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')
}

const customerLabel = (customer) => {
  return `${customer.name || '会员用户'} ${maskPhone(customer.phone)}`
}

const customerName = (id) => {
  const customer = customers.value.find((item) => String(item.id) === String(id))
  return customer ? customer.name || '会员用户' : '会员用户'
}

const formatMoney = (num) => {
  return Number(num || 0).toFixed(2)
}

const formatDateTime = (date) => {
  if (!date) return '-'
  const d = new Date(date)
  if (Number.isNaN(d.getTime())) return '-'
  const pad = (value) => String(value).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const loadCustomers = async () => {
  try {
    const res = await getCustomers({ page: 1, page_size: 200, include_disabled: true })
    if (res.code === 200 && res.data) {
      customers.value = rowsFrom(res.data)
    }
  } catch (error) {
    showToast({ message: '客户列表加载失败', icon: 'fail' })
  }
}

const loadConsumptions = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.value.page,
      page_size: pagination.value.pageSize
    }
    if (query.value.customer_id) params.customer_id = query.value.customer_id
    if (query.value.start_date) params.start_date = query.value.start_date
    if (query.value.end_date) params.end_date = query.value.end_date

    const res = await getConsumptions(params)
    if (res.code === 200 && res.data) {
      consumptions.value = rowsFrom(res.data)
      pagination.value.total = totalFrom(res.data)
      return
    }
    showToast({ message: res.msg || '消费记录加载失败', icon: 'fail' })
  } catch (error) {
    showToast({ message: '消费记录加载失败', icon: 'fail' })
  } finally {
    loading.value = false
  }
}

const submitSearch = () => {
  pagination.value.page = 1
  loadConsumptions()
}

const resetQuery = () => {
  query.value = {
    customer_id: '',
    customer_name: '',
    start_date: '',
    end_date: ''
  }
  pagination.value.page = 1
  loadConsumptions()
}

const handlePageChange = (page) => {
  pagination.value.page = page
  loadConsumptions()
}

const openCreate = (preset = {}) => {
  form.value = {
    project: preset.project || '到店消费',
    customer_id: '',
    customer_name: '',
    amount: preset.amount ? String(preset.amount) : '',
    remark: ''
  }
  showCreatePopup.value = true
}

const openCustomerPicker = (mode) => {
  customerPickerMode.value = mode
  showCustomerPicker.value = true
}

const onCustomerSelect = ({ selectedOptions }) => {
  const selectedId = selectedOptions[0]?.value
  const selected = customers.value.find((item) => String(item.id) === String(selectedId))
  if (!selected) {
    showCustomerPicker.value = false
    return
  }

  if (customerPickerMode.value === 'form') {
    form.value.customer_id = selected.id
    form.value.customer_name = customerLabel(selected)
  } else {
    query.value.customer_id = selected.id
    query.value.customer_name = customerLabel(selected)
  }
  showCustomerPicker.value = false
}

const onSubmit = async () => {
  if (!form.value.customer_id) {
    showToast({ message: '请选择顾客', icon: 'fail' })
    return
  }
  if (!form.value.project) {
    showToast({ message: '请输入消费项目', icon: 'fail' })
    return
  }
  if (!form.value.amount || Number(form.value.amount) <= 0) {
    showToast({ message: '请输入有效金额', icon: 'fail' })
    return
  }

  saving.value = true
  try {
    const res = await createConsumption({
      project: form.value.project,
      customer_id: form.value.customer_id,
      amount: Number(form.value.amount),
      remark: form.value.remark
    })

    if (res.code === 200) {
      showToast({ message: '消费已保存', icon: 'success' })
      showCreatePopup.value = false
      pagination.value.page = 1
      await loadConsumptions()
      return
    }
    showToast({ message: res.msg || '保存失败', icon: 'fail' })
  } catch (error) {
    showToast({ message: '保存失败', icon: 'fail' })
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadCustomers()
  const customerId = route.query.customer_id
  if (customerId) {
    const selected = customers.value.find((item) => String(item.id) === String(customerId))
    query.value.customer_id = String(customerId)
    query.value.customer_name = selected ? customerLabel(selected) : String(customerId)
  }
  loadConsumptions()
})
</script>

<style scoped>
.consumption-page {
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
.quick-card,
.filter-card,
.list-panel,
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

.hero-card h1,
.panel-head h2,
.form-header h2 {
  margin: 0;
  color: var(--text-1);
  font-weight: 900;
  letter-spacing: 0;
}

.hero-card h1 {
  font-size: 22px;
}

.hero-card p:not(.eyebrow),
.form-header p {
  margin: 6px 0 0;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.45;
}

.quick-card,
.filter-card,
.list-panel {
  margin-top: 12px;
  padding: 16px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.panel-head h2 {
  font-size: 20px;
}

.text-btn {
  border: 0;
  background: transparent;
  color: var(--brand-dark);
  font-weight: 900;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.quick-grid button,
.quick-projects button {
  border: 0;
  border-radius: 14px;
  background: var(--brand-light);
  color: var(--brand-dark);
  font-weight: 900;
}

.quick-grid button {
  height: 48px;
  font-size: 18px;
}

.date-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.state-card {
  padding: 32px 12px;
  text-align: center;
  box-shadow: none;
}

.record-list {
  display: grid;
  gap: 10px;
}

.record-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 15px;
  border: 1px solid var(--border);
  box-shadow: none;
}

.record-main {
  min-width: 0;
  flex: 1;
}

.record-main strong,
.record-main span,
.record-main em {
  display: block;
  font-style: normal;
}

.record-main strong {
  overflow: hidden;
  color: var(--text-1);
  font-size: 17px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.record-main span {
  margin-top: 6px;
  color: var(--text-2);
  font-size: 13px;
}

.record-main em {
  margin-top: 4px;
  color: var(--text-3);
  font-size: 12px;
}

.record-amount {
  color: var(--success);
  font-size: 20px;
  font-weight: 900;
  white-space: nowrap;
}

:deep(.van-pagination) {
  margin-top: 14px;
}

.form-popup {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.form-header {
  padding: 20px 16px 12px;
}

.form-header h2 {
  font-size: 20px;
}

.form-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 12px;
}

.quick-projects {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 8px 6px 10px;
}

.quick-projects button {
  height: 36px;
  font-size: 13px;
}

.form-footer {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 12px 16px 18px;
  border-top: 1px solid var(--border);
}

@media (min-width: 768px) {
  .consumption-page {
    max-width: 760px;
    margin: 0 auto;
  }
}
</style>
