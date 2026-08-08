<template>
  <div class="sub-page store-page">
    <PageHeader title="店铺资料" />
    <div class="page-body">
      <section class="summary-card animate-in">
        <img v-if="storeForm.logo_url" class="store-logo" :src="storeForm.logo_url" alt="门店 Logo" />
        <div v-else class="store-icon"><ShopOutlined /></div>
        <div>
          <h1>{{ storeForm.name || '商家名称' }}</h1>
          <span>{{ storeForm.phone || '未填写手机号' }}</span>
        </div>
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
            <div class="logo-upload-box" @click="triggerLogoUpload">
              <img v-if="storeForm.logo_url" :src="storeForm.logo_url" class="logo-upload-preview" alt="Logo 预览" />
              <div v-else class="logo-upload-placeholder">
                <span class="logo-upload-plus">+</span>
                <span>上传 Logo</span>
              </div>
              <div v-if="logoUploading" class="logo-upload-loading">上传中…</div>
              <div
                v-if="storeForm.logo_url"
                class="logo-delete-badge"
                role="button"
                aria-label="移除 Logo"
                @click.stop="clearLogo"
              >×</div>
            </div>
            <input
              ref="logoInputRef"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              class="logo-file-input"
              @change="onLogoSelected"
            />
            <div class="logo-upload-hint">支持 jpg/png/webp/gif，上传后自动压缩；点下方保存才生效</div>
          </a-form-item>
          <a-button type="primary" html-type="submit" block size="large" :loading="savingStore">保存门店资料</a-button>
        </a-form>
      </section>
      <section class="panel-card animate-in" style="animation-delay:.06s">
        <a-form :model="pickupForm" layout="vertical" @finish="savePickupSettings">
          <a-form-item label="启用数字桌牌">
            <a-switch v-model:checked="pickupForm.pickup_no_enabled" />
            <div class="logo-upload-hint">开启后：顾客可见桌牌号；可要求分牌后再打厨房票</div>
          </a-form-item>
          <a-form-item label="桌牌数量（1-999）">
            <a-input-number v-model:value="pickupForm.pickup_no_count" :min="1" :max="999" style="width:100%" />
          </a-form-item>
          <a-form-item label="打印前必须分牌">
            <a-switch v-model:checked="pickupForm.pickup_no_required_before_print" :disabled="!pickupForm.pickup_no_enabled" />
            <div class="logo-upload-hint">仅在启用桌牌时生效；未分牌时暂缓厨房票</div>
          </a-form-item>
          <a-button type="primary" html-type="submit" block size="large" :loading="savingPickup">保存桌牌设置</a-button>
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
import { getTenantProfile, updateTenantProfile, updateTenantSettings, uploadShopLogo } from '../../api'

const merchant = ref({})
const savingStore = ref(false)
const savingPickup = ref(false)
const logoUploading = ref(false)
const logoInputRef = ref(null)
const storeForm = ref({ name: '', address: '', phone: '', logo_url: '' })
const pickupForm = ref({
  pickup_no_enabled: false,
  pickup_no_count: 30,
  pickup_no_required_before_print: true,
})
const tenantId = computed(() => merchant.value.tenant_id || merchant.value.id || '')

async function loadProfile() {
  try {
    const res = await getTenantProfile()
    if (res.code === 200 && res.data) {
      merchant.value = res.data
      storeForm.value = {
        name: res.data.name || '',
        address: res.data.address || '',
        phone: res.data.phone || '',
        logo_url: res.data.logo_url || '',
      }
      pickupForm.value = {
        pickup_no_enabled: !!res.data.pickup_no_enabled,
        pickup_no_count: Number(res.data.pickup_no_count || 30),
        pickup_no_required_before_print: res.data.pickup_no_required_before_print !== false,
      }
    }
  } catch {
    message.error('店铺资料加载失败')
  }
}

function triggerLogoUpload() {
  if (logoUploading.value) return
  logoInputRef.value?.click()
}

function clearLogo() {
  storeForm.value.logo_url = ''
}

async function onLogoSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  logoUploading.value = true
  try {
    const res = await uploadShopLogo(file)
    const url = res?.data?.url || res?.data?.data?.url
    if (url) {
      storeForm.value.logo_url = url
      message.success('Logo 已上传，点保存按钮生效')
    } else {
      message.error(res?.msg || '上传失败')
    }
  } catch {
    message.error('上传失败，请重试')
  } finally {
    logoUploading.value = false
    e.target.value = ''
  }
}

async function saveStoreProfile() {
  if (!storeForm.value.name) {
    message.error('请填写门店名称')
    return
  }
  savingStore.value = true
  try {
    const res = await updateTenantProfile(storeForm.value)
    if (res.code === 200 && res.data) {
      merchant.value = { ...merchant.value, ...res.data }
      message.success('门店资料已保存')
      return
    }
    message.error(res.msg || '保存失败')
  } catch {
    message.error('保存失败，请检查后端接口')
  } finally {
    savingStore.value = false
  }
}

async function savePickupSettings() {
  const count = Number(pickupForm.value.pickup_no_count || 30)
  if (!Number.isFinite(count) || count < 1 || count > 999) {
    message.error('桌牌数量须在 1-999 之间')
    return
  }
  savingPickup.value = true
  try {
    // 桌牌配置在 business_info，必须走 /tenant/settings；
    // /tenant/profile 只接受店名/电话等基础字段，会静默丢掉 pickup_no_*。
    const res = await updateTenantSettings({
      pickup_no_enabled: !!pickupForm.value.pickup_no_enabled,
      pickup_no_count: count,
      pickup_no_required_before_print: !!pickupForm.value.pickup_no_required_before_print,
    })
    if (res.code === 200) {
      pickupForm.value = {
        pickup_no_enabled: !!res.data?.pickup_no_enabled,
        pickup_no_count: Number(res.data?.pickup_no_count || count),
        pickup_no_required_before_print: res.data?.pickup_no_required_before_print !== false,
      }
      message.success('桌牌设置已保存')
      return
    }
    message.error(res.msg || '保存失败')
  } catch {
    message.error('保存失败，请检查后端接口')
  } finally {
    savingPickup.value = false
  }
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
.store-icon, .store-logo {
  width: 50px;
  height: 50px;
  border-radius: 15px;
  flex-shrink: 0;
}
.store-icon {
  background: var(--brand);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 25px;
}
.store-logo { object-fit: cover; background: #f0f2f5; }
.summary-card h1, .summary-card span { display: block; margin: 0; }
.summary-card h1 { color: var(--text-1); font-size: 19px; font-weight: 900; }
.summary-card span { margin-top: 4px; color: var(--text-2); font-size: 13px; }
.panel-card { margin-top: 12px; padding: 16px; }
.plain-card { margin-top: 12px; padding: 14px; }
.plain-card strong, .plain-card span { display: block; }
.plain-card strong { color: var(--text-1); font-size: 14px; font-weight: 900; }
.plain-card span { margin-top: 6px; color: var(--text-2); font-size: 13px; font-family: monospace; }
.plain-card .tenant-id { cursor: pointer; }

.logo-upload-box {
  position: relative;
  width: 96px;
  height: 96px;
  border-radius: 16px;
  border: 1px dashed var(--border);
  background: #f7f8fa;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.logo-upload-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.logo-upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--text-3);
  font-size: 12px;
}
.logo-upload-plus { font-size: 22px; line-height: 1; color: var(--text-2); }
.logo-upload-loading {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-2);
}
.logo-delete-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 14px;
  line-height: 22px;
  text-align: center;
}
.logo-file-input { display: none; }
.logo-upload-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.4;
}
</style>
