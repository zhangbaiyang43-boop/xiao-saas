<template>
  <div class="coupon-send-page">
    <section class="section-block">
      <div class="section-head">
        <div>
          <h2 class="section-title">优惠券发放</h2>
          <p class="section-desc">选择券模后，可按客户单独发放或批量发放。</p>
        </div>
        <van-button type="primary" :loading="sending" @click="sendSelected">发放优惠券</van-button>
      </div>

      <div class="form-card">
        <van-field label="券模" placeholder="请选择已上架模" readonly @click="showTemplatePicker = true">
          <template #input>
            {{ selectedTemplate ? selectedTemplate.name : '请选择已上架模' }}
          </template>
        </van-field>
        <van-field v-model="selectedCustomersText" label="选择客户" placeholder="请选择客户" readonly @click="showCustomerPicker = true" />
      </div>

      <van-notice-bar v-if="selectedTemplate" :mode="stockAlertType === 'warning' ? 'closeable' : ''">
        当前模剩余 {{ remainingStock(selectedTemplate) }} 张，已选择 {{ selectedCount }} 位客户。
        <span v-if="stockInsufficient">库存不足，请减少客户或调整模库存。</span>
      </van-notice-bar>

      <div class="toolbar">
        <van-field v-model="query.search" placeholder="搜索姓名或手机号" />
        <van-button type="default" :loading="loading" @click="submitSearch">搜索客户</van-button>
      </div>

      <div class="customer-list">
        <div 
          v-for="customer in customers" 
          :key="customer.id" 
          class="customer-item"
          :class="{ selected: form.customer_ids.includes(customer.id) }"
          @click="toggleCustomer(customer.id)"
        >
          <van-checkbox :checked="form.customer_ids.includes(customer.id)" />
          <div class="customer-info">
            <div class="customer-name">{{ customer.name }}</div>
            <div class="customer-phone">{{ customer.phone }}</div>
          </div>
        </div>
      </div>
    </section>

    <van-popup v-model:show="showTemplatePicker" position="bottom" :style="{ height: '60%' }">
      <div class="picker-header">
        <h3 class="picker-title">选择优惠券</h3>
        <van-button text @click="showTemplatePicker = false">确定</van-button>
      </div>
      <div class="template-list">
        <div 
          v-for="t in templates" 
          :key="t.id" 
          class="template-item"
          :class="{ selected: form.template_id === String(t.id) || form.template_id === t.id }"
          @click="selectTemplate(t)"
        >
          <div class="template-info">
            <div class="template-name">{{ t.name }}</div>
            <div class="template-value">¥{{ t.value }} 元</div>
          </div>
          <van-icon name="success" v-if="form.template_id === String(t.id) || form.template_id === t.id" />
        </div>
      </div>
    </van-popup>

    <van-popup v-model="showCustomerPicker" position="bottom" :style="{ height: '60%' }">
      <van-picker :columns="customerOptions" @confirm="onCustomerSelect" />
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { Button as VanButton, Field as VanField, Checkbox as VanCheckbox, Popup as VanPopup, NoticeBar as VanNoticeBar, Icon as VanIcon } from 'vant'
import { getCustomers, getCouponTemplates, sendCoupons } from '../api'

const route = useRoute()

const loading = ref(false)
const sending = ref(false)
const showTemplatePicker = ref(false)
const showCustomerPicker = ref(false)

const query = ref({
  search: ''
})

const form = ref({
  template_id: '',
  customer_ids: []
})

const templates = ref([])
const customers = ref([])

const templateOptions = computed(() => {
  console.log('templates.value:', templates.value)
  const options = templates.value.map(t => ({ text: `${t.name} ¥${t.value}`, value: t.id }))
  console.log('templateOptions:', options)
  return options
})

const customerOptions = computed(() => {
  return customers.value.map(c => ({ text: `${c.name} ${c.phone}`, value: c.id }))
})

const selectedCustomersText = computed(() => {
  if (form.value.customer_ids.length === 0) return ''
  if (form.value.customer_ids.length === 1) {
    const customer = customers.value.find(c => c.id === form.value.customer_ids[0])
    return customer ? customer.name : ''
  }
  return `已选择 ${form.value.customer_ids.length} 位客户`
})

const selectedTemplate = computed(() => {
  console.log('selectedTemplate called')
  console.log('form.value.template_id:', form.value.template_id)
  console.log('templates.value:', templates.value)
  const found = templates.value.find(t => String(t.id) === String(form.value.template_id))
  console.log('found:', found)
  return found
})

const selectedCount = computed(() => form.value.customer_ids.length)

const remainingStock = (template) => {
  return (template.total_stock || 0) - (template.used_stock || 0)
}

const stockInsufficient = computed(() => {
  if (!selectedTemplate.value) return false
  return selectedCount.value > remainingStock(selectedTemplate.value)
})

const stockAlertType = computed(() => {
  if (stockInsufficient.value) return 'warning'
  return 'success'
})

const loadTemplates = async () => {
  try {
    const res = await getCouponTemplates({ page: 1, page_size: 100 })
    console.log('loadTemplates res:', res)
    if (res.code === 200) {
      templates.value = res.data?.results || res.data?.items || []
      console.log('templates.value after load:', templates.value)
    }
  } catch (error) {
    console.error('加载优惠券模失败:', error)
  }
}

const loadCustomers = async () => {
  try {
    const params = { page: 1, page_size: 100 }
    if (query.value.search) {
      params.search = query.value.search
    }
    const res = await getCustomers(params)
    if (res.code === 200) {
      const items = res.data?.results || res.data?.items || []
      customers.value = items.map(item => ({
        id: item.id,
        name: item.name || '未知会员',
        phone: item.phone ? item.phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2') : '-'
      }))
      // 如果有路由参数，并且客户列表加载完成后，确保客户被选中
      if (route.query.customerId) {
        const customerId = Number(route.query.customerId)
        if (customers.value.find(c => c.id === customerId)) {
          form.value.customer_ids = [customerId]
        }
      }
    }
  } catch (error) {
    console.error('加载客户列表失败:', error)
  }
}

const submitSearch = () => {
  loadCustomers()
}

const selectTemplate = (template) => {
  console.log('selectTemplate called with:', template)
  form.value.template_id = String(template.id) // 确保用字符串存储
  showTemplatePicker.value = false
  console.log('form.value.template_id after select:', form.value.template_id)
}

const onCustomerSelect = (value) => {
  form.value.customer_ids = value.selectedValues
  showCustomerPicker.value = false
}

const toggleCustomer = (id) => {
  const index = form.value.customer_ids.indexOf(id)
  if (index > -1) {
    form.value.customer_ids.splice(index, 1)
  } else {
    form.value.customer_ids.push(id)
  }
}

const sendSelected = async () => {
  if (!form.value.template_id) {
    showToast('请选择优惠券模')
    return
  }
  if (form.value.customer_ids.length === 0) {
    showToast('请选择客户')
    return
  }
  
  sending.value = true
  try {
    // 确保都是字符串，不要转Number，防止精度丢失
    console.log('发送数据:', {
      template_id: String(form.value.template_id),
      customer_ids: form.value.customer_ids.map(id => String(id))
    })
    
    await sendCoupons({
      template_id: String(form.value.template_id),
      customer_ids: form.value.customer_ids.map(id => String(id))
    })
    
    showToast(`成功发放 ${form.value.customer_ids.length} 张优惠券`)
    form.value.customer_ids = []
    form.value.template_id = ''
  } catch (error) {
    console.error('发放失败:', error)
    showToast('发放失败')
  } finally {
    sending.value = false
  }
}

onMounted(() => {
  loadTemplates()
  loadCustomers()
})
</script>

<style scoped>
.coupon-send-page {
  min-height: 100vh;
  padding: 16px 16px 88px;
  background: #f6f7fb;
}

.section-block {
  margin-bottom: 20px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
}

.section-desc {
  font-size: 13px;
  color: #8a8f9c;
  margin-top: 4px;
}

.form-card {
  background: #fff;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.customer-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.customer-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border-radius: 14px;
  padding: 14px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
  
  &.selected {
    background: #f5f3ff;
  }
}

.customer-info {
  flex: 1;
}

.customer-name {
  font-size: 15px;
  font-weight: 600;
}

.customer-phone {
  font-size: 13px;
  color: #8a8f9c;
  margin-top: 2px;
}

.picker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #f3f4f6;
}

.picker-title {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
}

.template-list {
  max-height: 400px;
  overflow-y: auto;
  padding: 8px 16px;
}

.template-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid #f3f4f6;
  &.selected {
    background: #f5f3ff;
  }
}

.template-info {
  flex: 1;
}

.template-name {
  font-size: 15px;
  font-weight: 600;
}

.template-value {
  font-size: 13px;
  color: #6d5dfb;
  margin-top: 4px;
}
</style>
