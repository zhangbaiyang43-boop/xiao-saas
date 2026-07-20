<template>
  <div class="template-list-page">
    <section class="section-block">
      <div class="section-head">
        <div>
          <h2 class="section-title">优惠券模</h2>
          <p class="section-desc">制作优惠券，维护库存、有效期和上下架状态。</p>
        </div>
        <van-button type="primary" :loading="saving" @click="openCreate">建模</van-button>
      </div>

      <div class="template-list">
        <div v-for="template in templates" :key="template.id" class="template-card">
          <div class="template-left">
            <div class="template-value">
              <span class="symbol">¥</span>
              <span class="amount">{{ template.value }}</span>
            </div>
            <div class="template-condition" v-if="template.minAmount > 0">满{{ template.minAmount }}元可用</div>
          </div>
          <div class="template-right">
            <div class="template-header">
              <span class="template-name">{{ template.name }}</span>
              <van-tag :type="template.status === 1 ? 'success' : 'default'">
                {{ template.status === 1 ? '上架' : '下架' }}
              </van-tag>
            </div>
            <div class="template-stats">
              <span>库存 {{ template.used_stock || 0 }}/{{ template.total_stock || 0 }}</span>
              <span>已核销 {{ template.redeemed || 0 }}</span>
            </div>
            <div class="template-footer">
              <span class="template-expire">{{ formatDate(template.start_time) }} 至 {{ formatDate(template.end_time) }}</span>
            </div>
          </div>
          <div class="template-actions">
            <van-button text type="primary" @click="openEdit(template)">编辑</van-button>
            <van-button text :type="template.status === 1 ? 'default' : 'success'" @click="toggleStatus(template)">
              {{ template.status === 1 ? '下架' : '上架' }}
            </van-button>
          </div>
        </div>
      </div>
    </section>

    <van-dialog v-model="showCreateDialog" :title="editingId ? '编辑优惠券' : '建优惠券'" show-cancel-button>
      <van-form @submit="onSubmit">
        <van-field v-model="form.name" label="叫什么" placeholder="输入优惠券名称" />
        <van-field v-model="form.amount" label="减多少钱" type="number" placeholder="优惠金额" />
        <van-field v-model="form.minAmount" label="满多少能用" type="number" placeholder="最低消费金额" />
        <van-field v-model="form.stock" label="发多少张" type="number" placeholder="库存数量" />
        <van-field v-model="form.validDays" label="几天内用" type="number" placeholder="有效期天数" />
        <template #footer>
          <van-button type="primary" native-type="submit" :loading="saving">{{ editingId ? '保存' : '建' }}</van-button>
        </template>
      </van-form>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Button as VanButton, Tag as VanTag, Dialog as VanDialog, Form as VanForm, Field as VanField, Toast as VanToast } from 'vant'
import { getCouponTemplates, createCouponTemplate, updateCouponTemplate, updateEntranceCodeStatus } from '../api'

const loading = ref(false)
const saving = ref(false)
const showCreateDialog = ref(false)
const editingId = ref(null)

const form = reactive({
  name: '',
  amount: '',
  minAmount: '',
  stock: '',
  validDays: ''
})

const templates = ref([])

const formatDate = (date) => {
  if (!date) return '-'
  const d = new Date(date)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const formatMoney = (num) => {
  return Number(num).toFixed(2)
}

const remainingStock = (template) => {
  return (template.total_stock || 0) - (template.used_stock || 0)
}

const isExpired = (template) => {
  return new Date(template.end_time) < new Date()
}

const loadTemplates = async () => {
  loading.value = true
  try {
    const res = await getCouponTemplates({ page: 1, page_size: 100 })
    if (res.code === 200) {
      templates.value = res.data?.results || res.data?.items || []
    }
  } catch (error) {
    console.error('加载优惠券模失败:', error)
    VanToast.fail('加载失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  Object.keys(form).forEach(key => form[key] = '')
  showCreateDialog.value = true
}

const openEdit = (template) => {
  editingId.value = template.id
  Object.assign(form, {
    name: template.name,
    amount: template.value,
    minAmount: template.min_amount || template.minAmount || 0,
    stock: template.total_stock || template.stock || 0,
    validDays: template.valid_days || 30
  })
  showCreateDialog.value = true
}

const toggleStatus = async (template) => {
  try {
    const newStatus = template.status === 1 ? 0 : 1
    template.status = newStatus
    await updateCouponTemplate(template.id, { status: newStatus })
    VanToast.success(newStatus === 1 ? '已上架' : '已下架')
  } catch (error) {
    console.error('更新状态失败:', error)
    template.status = template.status === 1 ? 0 : 1
    VanToast.fail('操作失败')
  }
}

const onSubmit = async () => {
  if (!form.name || !form.amount || !form.stock || !form.validDays) {
    VanToast.fail('请填写完整信息')
    return
  }
  
  saving.value = true
  try {
    const data = {
      name: form.name,
      value: Number(form.amount),
      min_amount: Number(form.minAmount) || 0,
      total_stock: Number(form.stock),
      valid_days: Number(form.validDays)
    }
    
    let res
    if (editingId.value) {
      res = await updateCouponTemplate(editingId.value, data)
    } else {
      res = await createCouponTemplate(data)
    }
    
    if (res.code === 200) {
      VanToast.success(editingId.value ? '修改成功' : '建成功')
      showCreateDialog.value = false
      Object.keys(form).forEach(key => form[key] = '')
      editingId.value = null
      loadTemplates()
    }
  } catch (error) {
    console.error(editingId.value ? '修改失败' : '建失败', error)
    VanToast.fail(editingId.value ? '修改失败' : '建失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<style scoped>
.template-list-page {
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

.template-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-card {
  background: #fff;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}

.template-left {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.template-value {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.symbol {
  font-size: 14px;
  font-weight: 600;
  color: #8b5cf6;
}

.amount {
  font-size: 32px;
  font-weight: 800;
  color: #8b5cf6;
}

.template-condition {
  font-size: 12px;
  color: #8a8f9c;
}

.template-right {
  margin-bottom: 12px;
}

.template-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.template-name {
  font-size: 15px;
  font-weight: 700;
}

.template-stats {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #8a8f9c;
}

.template-footer {
  margin-top: 8px;
}

.template-expire {
  font-size: 12px;
  color: #9ca3af;
}

.template-actions {
  display: flex;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid #f3f4f6;
}
</style>
