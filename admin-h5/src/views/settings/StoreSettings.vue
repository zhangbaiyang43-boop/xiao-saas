<template>
  <div class="sub-page store-page">
    <PageHeader title="店铺资料" />
    <div class="page-body">
      <section class="summary-card animate-in">
        <div class="store-icon"><ShopOutlined /></div>
        <div><h1>{{ storeForm.name || '商家名称' }}</h1><span>{{ storeForm.phone || '未填写手机号' }}</span></div>
      </section>
      <section class="panel-card animate-in" style="animation-delay:.04s">
        <a-form :model="storeForm" layout="vertical" @finish="saveStoreProfile">
          <a-form-item label="门店名称" name="name" :rules="[{ required: true, message: '请输入门店名称' }]">
            <a-input v-model:value="storeForm.name" placeholder="例如：大掌柜火锅店" />
          </a-form-item>
          <a-form-item label="门店地址">
            <a-input v-model:value="storeForm.address" placeholder="例如：门店所在街道和门牌号" />
          </a-form-item>
          <a-form-item label="联系电话">
            <a-input v-model:value="storeForm.phone" placeholder="顾客咨询电话" />
          </a-form-item>
          <a-form-item label="门店 Logo">
            <a-input v-model:value="storeForm.logo_url" placeholder="可选，填写图片地址" />
          </a-form-item>
          <a-button type="primary" html-type="submit" block size="large" :loading="savingStore">保存门店资料</a-button>
        </a-form>
      </section>
      <section class="plain-card animate-in" style="animation-delay:.08s">
        <strong>商家 ID</strong>
        <span class="tenant-id tap-shrink" @click="copyTenantId">{{ tenantId ? tenantId.slice(0, 4) + '****' + tenantId.slice(-4) : '-' }}</span>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ShopOutlined } from '@ant-design/icons-vue'
import PageHeader from '../../components/PageHeader.vue'
import { getTenantProfile, updateTenantProfile } from '../../api'

const merchant = ref({})
const savingStore = ref(false)
const storeForm = ref({ name: '', address: '', phone: '', logo_url: '' })
const tenantId = computed(() => merchant.value.tenant_id || merchant.value.id || '')

async function loadProfile() {
  try {
    const res = await getTenantProfile()
    if (res.code === 200 && res.data) {
      merchant.value = res.data
      storeForm.value = { name: res.data.name || '', address: res.data.address || '', phone: res.data.phone || '', logo_url: res.data.logo_url || '' }
    }
  } catch { message.error('店铺资料加载失败') }
}
async function saveStoreProfile() {
  if (!storeForm.value.name) { message.error('请填写门店名称'); return }
  savingStore.value = true
  try {
    const res = await updateTenantProfile(storeForm.value)
    if (res.code === 200 && res.data) { merchant.value = { ...merchant.value, ...res.data }; message.success('门店资料已保存'); return }
    message.error(res.msg || '保存失败')
  } catch { message.error('保存失败，请检查后端接口') }
  finally { savingStore.value = false }
}
function copyTenantId() {
  if (!tenantId.value) return
  navigator.clipboard.writeText(tenantId.value).then(() => message.success('商家 ID 已复制')).catch(() => message.info(tenantId.value))
}

onMounted(loadProfile)
</script>

<style scoped>
.store-page { min-height: 100vh; background: var(--bg-page); }
.page-body { padding: 12px 16px 28px; }
.summary-card, .panel-card, .plain-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--card-shadow); }
.summary-card { display: flex; align-items: center; gap: 12px; padding: 16px; }
.store-icon { width: 50px; height: 50px; border-radius: 15px; background: var(--brand); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 25px; flex-shrink: 0; }
.summary-card h1, .summary-card span { display: block; margin: 0; }
.summary-card h1 { color: var(--text-1); font-size: 19px; font-weight: 900; }
.summary-card span { margin-top: 4px; color: var(--text-2); font-size: 13px; }
.panel-card { margin-top: 12px; padding: 16px; }
.plain-card { margin-top: 12px; padding: 14px; }
.plain-card strong, .plain-card span { display: block; }
.plain-card strong { color: var(--text-1); font-size: 14px; font-weight: 900; }
.plain-card span { margin-top: 6px; color: var(--text-2); font-size: 13px; font-family: monospace; }
.plain-card .tenant-id { cursor: pointer; }
</style>
