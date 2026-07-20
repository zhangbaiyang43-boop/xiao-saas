<template>
  <div class="plugin-page">
    <section class="hero-card">
      <div>
        <div class="eyebrow">功能开关</div>
        <h1>先把常用功能用顺</h1>
        <p>单店 MVP 先保留核心功能，复杂扩展暂时收起，避免商家误操作。</p>
      </div>
      <van-button size="small" round type="primary" :loading="loading" @click="loadPlugins">
        刷新
      </van-button>
    </section>

    <section class="stats-grid">
      <div class="stat-card">
        <strong>{{ stats.total }}</strong>
        <span>功能</span>
      </div>
      <div class="stat-card">
        <strong>{{ stats.enabled }}</strong>
        <span>已开启</span>
      </div>
      <div class="stat-card warning">
        <strong>{{ stats.error }}</strong>
        <span>需处理</span>
      </div>
    </section>

    <section class="section-card">
      <div class="section-head">
        <div>
          <h2>可用功能</h2>
          <p>这里只做开关和简单设置，复杂插件中心后续再开放。</p>
        </div>
      </div>

      <van-loading v-if="loading" class="loading-block" />
      <div v-else-if="features.length" class="feature-list">
        <div v-for="feature in features" :key="feature.plugin_code || feature.id" class="feature-card">
          <div class="feature-top">
            <div class="feature-icon">{{ featureIcon(feature) }}</div>
            <div class="feature-info">
              <div class="feature-title">
                <strong>{{ feature.plugin_name || feature.name || feature.plugin_code }}</strong>
                <van-tag round :type="statusTag(feature)">{{ statusText(feature) }}</van-tag>
              </div>
              <p>{{ feature.description || '该功能暂未填写说明' }}</p>
            </div>
            <van-switch
              :model-value="Boolean(feature.enabled)"
              size="24px"
              :loading="operatingCode === feature.plugin_code"
              :disabled="switchDisabled(feature)"
              @update:model-value="toggleFeature(feature, $event)"
            />
          </div>

          <div class="feature-meta">
            <span>本 {{ feature.installed_version || feature.version || '-' }}</span>
            <span v-if="feature.dependencies_met === false" class="danger">缺少依赖</span>
            <span v-else>可正常使用</span>
          </div>

          <div v-if="feature.last_error" class="error-box">
            {{ feature.last_error }}
          </div>

          <div class="feature-actions">
            <van-button
              v-if="!feature.installed"
              round
              block
              type="primary"
              :loading="operatingCode === feature.plugin_code"
              @click="openFeature(feature)"
            >
              开通这个功能
            </van-button>
            <van-button
              v-else-if="(feature.config_schema || []).length"
              round
              block
              plain
              type="primary"
              @click="openConfig(feature)"
            >
              设置功能
            </van-button>
          </div>
        </div>
      </div>
      <van-empty v-else description="暂无可用功能" />
    </section>

    <van-popup v-model:show="configVisible" round position="bottom" class="config-popup">
      <div class="popup-head">
        <div>
          <h2>{{ currentPlugin?.plugin_name || '功能设置' }}</h2>
          <p>只修改当前功能的基础设置。</p>
        </div>
      </div>

      <van-form v-if="(currentPlugin?.config_schema || []).length">
        <van-cell-group inset>
          <van-field
            v-for="field in currentPlugin?.config_schema || []"
            :key="field.key"
            v-model="configForm[field.key]"
            :label="field.label"
            :type="field.type === 'number' ? 'number' : 'text'"
            :placeholder="field.placeholder || '请输入'"
          />
        </van-cell-group>
      </van-form>
      <van-empty v-else description="该功能暂无可设置项" />

      <div class="popup-actions">
        <van-button round block @click="configVisible = false">取消</van-button>
        <van-button round block type="primary" :loading="savingConfig" @click="saveConfig">
          保存设置
        </van-button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  Button as VanButton,
  CellGroup as VanCellGroup,
  Empty as VanEmpty,
  Field as VanField,
  Form as VanForm,
  Loading as VanLoading,
  Popup as VanPopup,
  Switch as VanSwitch,
  Tag as VanTag,
  showConfirmDialog,
  showToast
} from 'vant'
import {
  disablePlugin,
  enablePlugin,
  getPluginLifecycle,
  installPlugin,
  updatePluginConfig
} from '../api'
import { unwrapList } from '../utils/format'

const loading = ref(false)
const savingConfig = ref(false)
const operatingCode = ref('')
const features = ref([])
const configVisible = ref(false)
const currentPlugin = ref(null)
const configForm = ref({})

const stats = computed(() => {
  return {
    total: features.value.length,
    enabled: features.value.filter((item) => item.enabled).length,
    error: features.value.filter((item) => item.lifecycle_status === 'ERROR' || item.last_error).length
  }
})

const featureIcon = (feature) => {
  const code = String(feature.plugin_code || feature.name || '')
  if (code.includes('coupon') || code.includes('marketing')) return '券'
  if (code.includes('crm') || code.includes('customer')) return '客'
  if (code.includes('point') || code.includes('member')) return '会'
  return '功'
}

const statusText = (feature) => {
  if (feature.lifecycle_status === 'ERROR' || feature.last_error) return '异常'
  if (feature.enabled) return '已开启'
  if (feature.installed) return '未开启'
  return '未开通'
}

const statusTag = (feature) => {
  if (feature.lifecycle_status === 'ERROR' || feature.last_error) return 'danger'
  if (feature.enabled) return 'success'
  if (feature.installed) return 'warning'
  return 'primary'
}

const switchDisabled = (feature) => {
  return !feature.installed || feature.dependencies_met === false
}

const loadPlugins = async () => {
  loading.value = true
  try {
    const res = await getPluginLifecycle()
    features.value = unwrapList(res)
  } catch (error) {
    console.error('加载功能开关失败:', error)
    showToast('功能列表加载失败')
  } finally {
    loading.value = false
  }
}

const runOperation = async (feature, action, successText) => {
  operatingCode.value = feature.plugin_code
  try {
    const res = await action({ plugin_code: feature.plugin_code })
    if (res?.code === 200 || res?.success) {
      showToast(successText)
      await loadPlugins()
      return true
    }
    showToast(res?.message || res?.msg || '操作失败')
    return false
  } catch (error) {
    console.error('功能操作失败:', error)
    showToast('操作失败，请稍后再试')
    return false
  } finally {
    operatingCode.value = ''
  }
}

const openFeature = async (feature) => {
  const installed = await runOperation(feature, installPlugin, '功能已开通')
  if (installed) {
    await runOperation(feature, enablePlugin, '功能已开启')
  }
}

const toggleFeature = async (feature, enabled) => {
  if (enabled) {
    await runOperation(feature, enablePlugin, '功能已开启')
    return
  }

  try {
    await showConfirmDialog({
      title: '关闭功能',
      message: '关闭后不会继续使用该功能，已有业务数据不会删除。',
      confirmButtonText: '确认关闭',
      cancelButtonText: '先不关'
    })
    await runOperation(feature, disablePlugin, '功能已关闭')
  } catch (error) {
    // User cancelled.
  }
}

const openConfig = (feature) => {
  currentPlugin.value = feature
  configForm.value = { ...(feature.config || {}) }
  configVisible.value = true
}

const saveConfig = async () => {
  if (!currentPlugin.value) return
  savingConfig.value = true
  try {
    const res = await updatePluginConfig(currentPlugin.value.plugin_code, { config: configForm.value })
    if (res?.code === 200 || res?.success) {
      showToast('设置已保存')
      configVisible.value = false
      await loadPlugins()
      return
    }
    showToast(res?.message || res?.msg || '保存失败')
  } catch (error) {
    console.error('保存功能设置失败:', error)
    showToast('保存失败，请稍后再试')
  } finally {
    savingConfig.value = false
  }
}

onMounted(loadPlugins)
</script>

<style scoped>
.plugin-page {
  min-height: 100vh;
  padding: 12px 12px 88px;
  background: #f5f6f8;
}

.hero-card,
.section-card {
  margin-bottom: 12px;
  padding: 16px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
}

.hero-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.eyebrow {
  margin-bottom: 8px;
  color: #1677ff;
  font-size: 12px;
  font-weight: 800;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 22px;
  line-height: 1.25;
  color: #111827;
}

h2 {
  font-size: 18px;
  color: #111827;
}

p {
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.stat-card {
  padding: 14px 10px;
  text-align: center;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
}

.stat-card strong {
  display: block;
  font-size: 22px;
  color: #111827;
}

.stat-card span {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.stat-card.warning strong {
  color: #ef4444;
}

.section-head {
  margin-bottom: 14px;
}

.loading-block {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feature-card {
  padding: 14px;
  border-radius: 16px;
  background: #f8fafc;
}

.feature-top {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.feature-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: #1677ff;
  color: #fff;
  font-size: 17px;
  font-weight: 900;
}

.feature-info {
  flex: 1;
  min-width: 0;
}

.feature-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.feature-title strong {
  overflow: hidden;
  color: #111827;
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feature-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #edf2f7;
  color: #64748b;
  font-size: 12px;
}

.feature-meta .danger {
  color: #ef4444;
}

.error-box {
  margin-top: 10px;
  padding: 10px;
  border-radius: 10px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 12px;
  line-height: 1.5;
}

.feature-actions {
  margin-top: 12px;
}

.config-popup {
  padding: 16px 0 max(16px, env(safe-area-inset-bottom));
}

.popup-head,
.popup-actions {
  padding: 0 16px 14px;
}

.popup-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding-top: 14px;
}
</style>
