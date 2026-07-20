<template>
  <div class="marketing-template-list">
    <NavBar title="营销模" />
    
    <div class="page-intro">
      <div class="intro-icon">
        <van-icon name="lightbulb-o" size="24" />
      </div>
      <div class="intro-content">
        <div class="intro-title">系统已经帮你配好的赚钱则</div>
        <div class="intro-text">点击启用模，系统自动建优惠券和发券则，顾客到店消费后自动触发下一张券</div>
      </div>
    </div>

    <div class="template-list">
      <div 
        v-for="template in templates" 
        :key="template.id" 
        class="template-card"
        @click="goToDetail(template.id)"
      >
        <div class="template-header">
          <div class="template-icon">
            <van-icon name="magic" size="24" />
          </div>
          <div class="template-info">
            <div class="template-name">{{ template.template_name }}</div>
            <div class="template-industry">{{ template.industry }}</div>
          </div>
          <van-icon name="arrow-right" size="18" />
        </div>
        
        <div class="template-body">
          <div class="price-range">
            <van-icon name="wallet" size="14" />
            <span>适合客单价：¥{{ template.target_customer_price_min }}-{{ template.target_customer_price_max }}</span>
          </div>
          <div class="template-desc">{{ template.description }}</div>
        </div>
        
        <div class="template-footer">
          <span class="status-badge" :class="getStatusClass(merchantStatus[template.id])">
            {{ getStatusText(merchantStatus[template.id]) }}
          </span>
          <button 
            class="action-btn" 
            :class="merchantStatus[template.id] === 'enabled' ? 'disabled' : ''"
            @click.stop="handleEnable(template)"
          >
            {{ merchantStatus[template.id] === 'enabled' ? '已启用' : '一键启用' }}
          </button>
        </div>
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
import { ref, onMounted } from 'vue'
import NavBar from '../components/NavBar.vue'
import { api } from '../api'

const templates = ref([])
const merchantStatus = ref({})
const showConfirmDialog = ref(false)
const confirmMessage = ref('')
const currentTemplate = ref(null)

const getStatusClass = (status) => {
  return status === 'enabled' ? 'enabled' : 'disabled'
}

const getStatusText = (status) => {
  if (status === 'enabled') return '已启用'
  return '未启用'
}

const fetchTemplates = async () => {
  try {
    const res = await api.get('/api/admin/marketing-templates')
    if (res.code === 0) {
      templates.value = res.data
      await fetchMerchantTemplates()
    }
  } catch (error) {
    console.error('获取模列表失败', error)
  }
}

const fetchMerchantTemplates = async () => {
  try {
    const res = await api.get('/api/admin/marketing-templates/merchant-templates')
    if (res.code === 0) {
      const status = {}
      res.data.forEach(item => {
        status[item.template_id] = 'enabled'
      })
      merchantStatus.value = status
    }
  } catch (error) {
    console.error('获取商家模状态失败', error)
  }
}

const goToDetail = (templateId) => {
  window.location.href = `#/marketing-templates/${templateId}`
}

const handleEnable = (template) => {
  if (merchantStatus.value[template.id] === 'enabled') return
  
  currentTemplate.value = template
  confirmMessage.value = `启用"${template.template_name}"后，系统会自动建4张优惠券，并绑定自动发券则。商家只需要核销，系统会自动发下一张券。`
  showConfirmDialog.value = true
}

const confirmEnable = async () => {
  if (!currentTemplate.value) return
  
  try {
    const res = await api.post(`/api/admin/marketing-templates/${currentTemplate.value.id}/enable`)
    if (res.code === 0) {
      vanToast.success('启用成功')
      merchantStatus.value[currentTemplate.value.id] = 'enabled'
    } else {
      vanToast.fail(res.msg)
    }
  } catch (error) {
    vanToast.fail('启用失败')
  } finally {
    showConfirmDialog.value = false
    currentTemplate.value = null
  }
}

onMounted(() => {
  fetchTemplates()
})
</script>

<style lang="scss" scoped>
.marketing-template-list {
  min-height: 100vh;
  background: #f5f5f5;
  padding-bottom: 60px;
}

.page-intro {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  
  .intro-icon {
    width: 40px;
    height: 40px;
    background: rgba(255,255,255,0.2);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: #fff;
  }
  
  .intro-content {
    flex: 1;
    
    .intro-title {
      font-size: 16px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 4px;
    }
    
    .intro-text {
      font-size: 12px;
      color: rgba(255,255,255,0.8);
      line-height: 1.5;
    }
  }
}

.template-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-card {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  
  .template-header {
    display: flex;
    align-items: center;
    padding: 16px;
    gap: 12px;
    
    .template-icon {
      width: 48px;
      height: 48px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
    }
    
    .template-info {
      flex: 1;
      
      .template-name {
        font-size: 16px;
        font-weight: 600;
        color: #333;
        margin-bottom: 4px;
      }
      
      .template-industry {
        font-size: 12px;
        color: #999;
      }
    }
  }
  
  .template-body {
    padding: 0 16px;
    
    .price-range {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: #666;
      margin-bottom: 8px;
    }
    
    .template-desc {
      font-size: 13px;
      color: #666;
      line-height: 1.5;
      margin-bottom: 12px;
    }
  }
  
  .template-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: #fafafa;
    border-top: 1px solid #f0f0f0;
    
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
    
    .action-btn {
      padding: 8px 20px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      border: none;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      
      &.disabled {
        background: #e5e7eb;
        color: #9ca3af;
      }
    }
  }
}
</style>