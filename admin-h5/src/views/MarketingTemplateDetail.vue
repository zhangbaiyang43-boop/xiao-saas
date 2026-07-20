<template>
  <div class="marketing-template-detail">
    <NavBar :title="template.template_name || '模详情'" showBack />
    
    <div class="template-header-card">
      <div class="template-icon">
        <van-icon name="magic" size="32" />
      </div>
      <div class="template-info">
        <div class="template-name">{{ template.template_name }}</div>
        <div class="template-industry">{{ template.industry }}</div>
        <div class="price-range">
          <van-icon name="wallet" size="12" />
          <span>适合客单价：¥{{ template.target_customer_price_min }}-{{ template.target_customer_price_max }}</span>
        </div>
      </div>
    </div>

    <div class="template-desc">
      <div class="desc-title">模目标</div>
      <div class="desc-text">{{ template.description }}</div>
    </div>

    <div class="rules-section">
      <div class="section-title">
        <van-icon name="list-o" size="16" />
        <span>包含则</span>
      </div>
      
      <div class="rules-list">
        <div 
          v-for="(rule, index) in template.rules" 
          :key="rule.id" 
          class="rule-card"
        >
          <div class="rule-number">{{ index + 1 }}</div>
          <div class="rule-content">
            <div class="rule-header">
              <span class="rule-name">{{ rule.rule_name }}</span>
              <span class="rule-type">{{ getCouponTypeText(rule.coupon_type) }}</span>
            </div>
            <div class="rule-discount">
              <span v-if="rule.discount_type === 'amount_threshold'">
                满{{ rule.threshold_amount }}减{{ rule.discount_amount }}
              </span>
              <span v-else>
                无门槛减{{ rule.discount_amount }}
              </span>
            </div>
            <div class="rule-info">
              <span class="valid-days">有效期{{ rule.valid_days }}天</span>
              <span class="trigger-desc">{{ getTriggerDesc(rule) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="action-section">
      <div class="status-bar">
        <span class="status-label">当前状态</span>
        <span class="status-badge" :class="statusClass">{{ statusText }}</span>
      </div>
      
      <button 
        class="action-btn" 
        :class="isEnabled ? 'disabled' : ''"
        @click="handleAction"
      >
        {{ isEnabled ? '已启用' : '一键启用' }}
      </button>
      
      <div v-if="isEnabled" class="action-tip">
        <van-icon name="info-o" size="14" />
        <span>停用模后将不再自动发券，但已发放的优惠券仍可使用</span>
      </div>
    </div>

    <van-dialog 
      v-model:show="showConfirmDialog" 
      title="确认启用"
      :message="confirmMessage"
      confirm-button-text="确认启用"
      cancel-button-text="取消"
      @confirm="confirmEnable"
    />

    <van-toast id="toast" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import NavBar from '../components/NavBar.vue'
import { api } from '../api'

const template = ref({
  id: '',
  template_name: '',
  industry: '',
  target_customer_price_min: 0,
  target_customer_price_max: 0,
  description: '',
  rules: []
})

const isEnabled = ref(false)
const merchantTemplateId = ref(null)
const showConfirmDialog = ref(false)
const confirmMessage = ref('')

const statusClass = computed(() => {
  return isEnabled.value ? 'enabled' : 'disabled'
})

const statusText = computed(() => {
  return isEnabled.value ? '已启用' : '未启用'
})

const getCouponTypeText = (type) => {
  const map = {
    'new_customer': '新客券',
    'after_consumption': '消费后券',
    'recall': '召回券'
  }
  return map[type] || type
}

const getTriggerDesc = (rule) => {
  if (rule.trigger_type === 'first_scan') {
    return '首次扫码触发'
  } else if (rule.trigger_type === 'after_verify') {
    return '核销后自动触发'
  } else if (rule.trigger_type === 'no_verify_after_days') {
    return `${rule.trigger_delay_days}天未核销触发`
  }
  return ''
}

const fetchTemplate = async () => {
  const path = window.location.hash
  const match = path.match(/\/marketing-templates\/(\d+)/)
  if (!match) return
  
  const templateId = match[1]
  
  try {
    const res = await api.get(`/api/admin/marketing-templates/${templateId}`)
    if (res.code === 0) {
      template.value = res.data
    }
    
    await fetchMerchantStatus(templateId)
  } catch (error) {
    console.error('获取模详情失败', error)
  }
}

const fetchMerchantStatus = async (templateId) => {
  try {
    const res = await api.get('/api/admin/marketing-templates/merchant-templates')
    if (res.code === 0) {
      const found = res.data.find(item => item.template_id == templateId)
      if (found) {
        isEnabled.value = true
        merchantTemplateId.value = found.id
      }
    }
  } catch (error) {
    console.error('获取商家模状态失败', error)
  }
}

const handleAction = () => {
  if (isEnabled.value) {
    handleDisable()
  } else {
    confirmMessage.value = `启用"${template.value.template_name}"后，系统会自动建4张优惠券，并绑定自动发券则。商家只需要核销，系统会自动发下一张券。`
    showConfirmDialog.value = true
  }
}

const confirmEnable = async () => {
  try {
    const res = await api.post(`/api/admin/marketing-templates/${template.value.id}/enable`)
    if (res.code === 0) {
      vanToast.success('启用成功')
      isEnabled.value = true
      merchantTemplateId.value = res.data.merchant_template_id
    } else {
      vanToast.fail(res.msg)
    }
  } catch (error) {
    vanToast.fail('启用失败')
  } finally {
    showConfirmDialog.value = false
  }
}

const handleDisable = async () => {
  if (!merchantTemplateId.value) return
  
  try {
    const res = await api.patch(`/api/admin/marketing-templates/merchant-templates/${merchantTemplateId.value}/disable`)
    if (res.code === 0) {
      vanToast.success('停用成功')
      isEnabled.value = false
      merchantTemplateId.value = null
    } else {
      vanToast.fail(res.msg)
    }
  } catch (error) {
    vanToast.fail('停用失败')
  }
}

onMounted(() => {
  fetchTemplate()
})
</script>

<style lang="scss" scoped>
.marketing-template-detail {
  min-height: 100vh;
  background: #f5f5f5;
  padding-bottom: 80px;
}

.template-header-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  
  .template-icon {
    width: 56px;
    height: 56px;
    background: rgba(255,255,255,0.2);
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
  }
  
  .template-info {
    flex: 1;
    
    .template-name {
      font-size: 20px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 6px;
    }
    
    .template-industry {
      font-size: 14px;
      color: rgba(255,255,255,0.8);
      margin-bottom: 8px;
    }
    
    .price-range {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: rgba(255,255,255,0.9);
    }
  }
}

.template-desc {
  margin: 16px;
  padding: 16px;
  background: #fff;
  border-radius: 12px;
  
  .desc-title {
    font-size: 14px;
    font-weight: 600;
    color: #333;
    margin-bottom: 8px;
  }
  
  .desc-text {
    font-size: 13px;
    color: #666;
    line-height: 1.6;
  }
}

.rules-section {
  margin: 0 16px;
  
  .section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 600;
    color: #333;
    margin-bottom: 12px;
  }
  
  .rules-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  
  .rule-card {
    background: #fff;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    gap: 12px;
    
    .rule-number {
      width: 28px;
      height: 28px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 600;
      flex-shrink: 0;
    }
    
    .rule-content {
      flex: 1;
      
      .rule-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
        
        .rule-name {
          font-size: 14px;
          font-weight: 600;
          color: #333;
        }
        
        .rule-type {
          font-size: 11px;
          padding: 2px 8px;
          background: #f0f0f0;
          border-radius: 10px;
          color: #666;
        }
      }
      
      .rule-discount {
        font-size: 15px;
        font-weight: 600;
        color: #ef4444;
        margin-bottom: 6px;
      }
      
      .rule-info {
        display: flex;
        align-items: center;
        gap: 12px;
        
        .valid-days, .trigger-desc {
          font-size: 12px;
          color: #999;
        }
        
        .trigger-desc {
          color: #667eea;
        }
      }
    }
  }
}

.action-section {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: #fff;
  padding: 16px;
  border-top: 1px solid #f0f0f0;
  
  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    
    .status-label {
      font-size: 13px;
      color: #999;
    }
    
    .status-badge {
      font-size: 12px;
      padding: 4px 12px;
      border-radius: 20px;
      
      &.enabled {
        background: #dcfce7;
        color: #16a34a;
      }
      
      &.disabled {
        background: #fef3c7;
        color: #f59e0b;
      }
    }
  }
  
  .action-btn {
    width: 100%;
    padding: 14px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
    border: none;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 600;
    
    &.disabled {
      background: #e5e7eb;
      color: #9ca3af;
    }
  }
  
  .action-tip {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    margin-top: 12px;
    font-size: 12px;
    color: #999;
  }
}
</style>