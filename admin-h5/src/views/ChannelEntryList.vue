<template>
  <div class="channel-entry-page">
    <PageHeader title="H5领券页" />

    <div class="page-content">
    <section class="hero-card animate-in">
      <div>
        <p class="eyebrow">H5领券页</p>
        <h1>给不同平台生成领券链接</h1>
        <p>抖音评论、朋友圈、短信、外卖袋，都可以放同一个可追踪入口。</p>
      </div>
      <van-button round type="primary" class="tap-shrink" @click="openCreate">新建</van-button>
    </section>

    <section class="stats-grid animate-in" style="animation-delay:.04s">
      <div class="stat-card">
        <strong>{{ entries.length }}</strong>
        <span>入口数</span>
      </div>
      <div class="stat-card">
        <strong>{{ totalVisits }}</strong>
        <span>访问量</span>
      </div>
      <div class="stat-card">
        <strong>{{ activeEntries }}</strong>
        <span>启用中</span>
      </div>
    </section>

    <section class="tips-card animate-in" style="animation-delay:.08s">
      <strong>怎么用</strong>
      <p>1. 新建一个入口，选择来源平台。</p>
      <p>2. 复制链接发到抖音、朋友圈或短信。</p>
      <p>3. 顾客打开后领券，后台会记录来源。</p>
    </section>

    <section class="list-panel animate-in" style="animation-delay:.12s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">我的入口</p>
          <h2>复制出去就能用</h2>
        </div>
        <button class="text-btn tap-shrink" :disabled="loading" @click="loadData">刷新</button>
      </div>

      <div v-if="loading" class="state-card">
        <van-loading size="24px">正在加载入口</van-loading>
      </div>

      <div v-else-if="entries.length === 0" class="state-card">
        <van-empty description="暂无入口">
          <van-button round type="primary" size="small" @click="openCreate">新建领券入口</van-button>
        </van-empty>
      </div>

      <div v-else class="entry-list">
        <article v-for="entry in entries" :key="entry.id" class="entry-card tap-shrink">
          <div class="entry-top">
            <div class="entry-title">
              <strong>{{ entry.name || '领券入口' }}</strong>
              <span>{{ getChannelName(entry.channel_code) }}</span>
            </div>
            <van-tag :type="entry.status === 1 ? 'success' : 'default'" round>
              {{ entry.status === 1 ? '启用中' : '已停用' }}
            </van-tag>
          </div>

          <div class="entry-link">
            <span>领券链接</span>
            <strong>{{ entry.h5_url || '暂无链接' }}</strong>
          </div>

          <div class="entry-data">
            <div>
              <strong>{{ entry.visit_count || 0 }}</strong>
              <span>访问</span>
            </div>
            <div>
              <strong>{{ entry.scan_count || 0 }}</strong>
              <span>扫码</span>
            </div>
            <div>
              <strong>{{ entry.coupon_name || '未绑定' }}</strong>
              <span>优惠券</span>
            </div>
          </div>

          <div class="entry-actions">
            <van-button round size="small" type="primary" @click="copyLink(entry)">复制链接</van-button>
            <van-button round size="small" plain type="primary" :disabled="!entry.qrcode_url" @click="downloadQr(entry)">
              查看二维码
            </van-button>
            <van-button round size="small" plain @click="openEdit(entry)">编辑</van-button>
            <van-button round size="small" plain type="danger" @click="confirmDelete(entry)">删除</van-button>
          </div>
        </article>
      </div>
    </section>
    </div>

    <van-popup v-model:show="showFormDialog" position="bottom" round :style="{ height: '88%' }" closeable>
      <div class="form-popup">
        <div class="form-header">
          <h2>{{ isEditing ? '编辑领券入口' : '新建领券入口' }}</h2>
          <p>入口名称和来源用于后台识别顾客从哪里来。</p>
        </div>

        <div class="form-body">
          <van-field v-model.trim="form.name" label="入口名称" placeholder="例如：抖音评论领券" />

          <van-field
            :model-value="selectedChannelName"
            label="来源平台"
            placeholder="请选择"
            readonly
            is-link
            @click="showChannelPicker = true"
          />

          <van-field v-model.trim="form.landing_title" label="页面标题" placeholder="例如：进店领优惠券" />
          <van-field v-model.trim="form.landing_subtitle" label="页面说明" placeholder="例如：新客进店先领券" />

          <van-field
            :model-value="selectedCouponName"
            label="绑定优惠券"
            placeholder="可不选"
            readonly
            is-link
            @click="showCouponPicker = true"
          />

          <van-field
            v-model.trim="form.mini_program_qrcode_url"
            label="小程序码"
            placeholder="可选，填写图片地址"
          />

          <van-cell title="是否启用" center>
            <template #right-icon>
              <van-switch v-model="form.status" :active-value="1" :inactive-value="0" />
            </template>
          </van-cell>
        </div>

        <div class="form-footer">
          <van-button block round @click="showFormDialog = false">取消</van-button>
          <van-button block round type="primary" :loading="saving" @click="onSubmit">
            {{ isEditing ? '保存入口' : '建入口' }}
          </van-button>
        </div>
      </div>
    </van-popup>

    <van-popup v-model:show="showChannelPicker" position="bottom" round>
      <van-picker
        title="选择来源平台"
        :columns="channelColumns"
        @confirm="onChannelSelect"
        @cancel="showChannelPicker = false"
      />
    </van-popup>

    <van-popup v-model:show="showCouponPicker" position="bottom" round>
      <van-picker
        title="选择优惠券"
        :columns="couponColumns"
        @confirm="onCouponSelect"
        @cancel="showCouponPicker = false"
      />
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Button as VanButton,
  Cell as VanCell,
  Empty as VanEmpty,
  Field as VanField,
  Loading as VanLoading,
  Picker as VanPicker,
  Popup as VanPopup,
  Switch as VanSwitch,
  Tag as VanTag,
  showConfirmDialog,
  showToast
} from 'vant'
import PageHeader from '../components/PageHeader.vue'
import {
  createChannelEntry,
  deleteChannelEntry,
  getChannelEntries,
  getChannelOptions,
  getCouponTemplates,
  updateChannelEntry
} from '../api'

const loading = ref(false)
const saving = ref(false)
const showFormDialog = ref(false)
const showChannelPicker = ref(false)
const showCouponPicker = ref(false)
const isEditing = ref(false)
const editingId = ref(null)

const entries = ref([])
const channelOptions = ref([])
const coupons = ref([])

const form = reactive({
  name: '',
  channel_code: '',
  landing_title: '',
  landing_subtitle: '',
  coupon_template_id: '',
  mini_program_qrcode_url: '',
  status: 1
})

const channelColumns = computed(() =>
  channelOptions.value.map((item) => ({ text: item.name, value: item.code }))
)

const couponColumns = computed(() => [
  { text: '不绑定优惠券', value: '' },
  ...coupons.value.map((item) => ({ text: `${item.name}（￥${money(item.value)}）`, value: String(item.id) }))
])

const selectedChannelName = computed(() => getChannelName(form.channel_code))

const selectedCouponName = computed(() => {
  if (!form.coupon_template_id) return ''
  const coupon = coupons.value.find((item) => String(item.id) === String(form.coupon_template_id))
  return coupon ? `${coupon.name}（￥${money(coupon.value)}）` : ''
})

const totalVisits = computed(() =>
  entries.value.reduce((sum, item) => sum + Number(item.visit_count || 0), 0)
)

const activeEntries = computed(() =>
  entries.value.filter((item) => item.status === 1).length
)

const money = (value) => Number(value || 0).toFixed(Number(value || 0) % 1 === 0 ? 0 : 2)

const rowsFrom = (payload) => {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.results)) return payload.results
  if (Array.isArray(payload?.data)) return payload.data
  return []
}

const getChannelName = (code) => {
  if (!code) return ''
  const channel = channelOptions.value.find((item) => item.code === code)
  return channel ? channel.name : code
}

const resolveAssetUrl = (url) => {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  return `${import.meta.env.VITE_API_ORIGIN || 'https://api.zhangbaiyang.com'}${url}`
}

const loadChannelOptions = async () => {
  try {
    const res = await getChannelOptions()
    if (res.code === 200 && res.data) {
      channelOptions.value = res.data
      return
    }
  } catch (error) {
    // Use defaults below.
  }
  channelOptions.value = [
    { code: 'douyin', name: '抖音' },
    { code: 'kuaishou', name: '快手' },
    { code: 'meituan', name: '美团' },
    { code: 'eleme', name: '饿了么' },
    { code: 'moments', name: '朋友圈' },
    { code: 'offline', name: '线下门店' },
    { code: 'custom', name: '自定义' }
  ]
}

const loadCoupons = async () => {
  try {
    const res = await getCouponTemplates({ page: 1, page_size: 100 })
    if (res.code === 200 && res.data) {
      coupons.value = rowsFrom(res.data)
    }
  } catch (error) {
    showToast({ message: '优惠券加载失败', icon: 'fail' })
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await getChannelEntries({ page: 1, page_size: 100 })
    if (res.code === 200 && res.data) {
      entries.value = rowsFrom(res.data)
      return
    }
    showToast({ message: res.msg || '入口加载失败', icon: 'fail' })
  } catch (error) {
    showToast({ message: '入口加载失败', icon: 'fail' })
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  isEditing.value = false
  editingId.value = null
  Object.assign(form, {
    name: '',
    channel_code: '',
    landing_title: '',
    landing_subtitle: '',
    coupon_template_id: '',
    mini_program_qrcode_url: '',
    status: 1
  })
  showFormDialog.value = true
}

const openEdit = (entry) => {
  isEditing.value = true
  editingId.value = entry.id
  Object.assign(form, {
    name: entry.name || '',
    channel_code: entry.channel_code || '',
    landing_title: entry.landing_title || '',
    landing_subtitle: entry.landing_subtitle || '',
    coupon_template_id: entry.coupon_template_id ? String(entry.coupon_template_id) : '',
    mini_program_qrcode_url: entry.mini_program_qrcode_url || '',
    status: entry.status ?? 1
  })
  showFormDialog.value = true
}

const onChannelSelect = ({ selectedOptions }) => {
  form.channel_code = selectedOptions[0]?.value || ''
  showChannelPicker.value = false
}

const onCouponSelect = ({ selectedOptions }) => {
  form.coupon_template_id = selectedOptions[0]?.value || ''
  showCouponPicker.value = false
}

const copyText = async (text) => {
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

const copyLink = async (entry) => {
  if (!entry.h5_url) {
    showToast({ message: '暂无链接', icon: 'fail' })
    return
  }
  try {
    await copyText(entry.h5_url)
    showToast({ message: '链接已复制', icon: 'success' })
  } catch (error) {
    showToast({ message: '复制失败，请手动复制', icon: 'fail' })
  }
}

const downloadQr = (entry) => {
  if (!entry.qrcode_url) {
    showToast({ message: '暂无二维码', icon: 'fail' })
    return
  }
  window.open(resolveAssetUrl(entry.qrcode_url), '_blank')
}

const confirmDelete = async (entry) => {
  try {
    await showConfirmDialog({
      title: '删除入口',
      message: '删除后，这个链接将不能再用于领券。确认删除吗？'
    })
    const res = await deleteChannelEntry(entry.id)
    if (res.code === 200 || res.success) {
      showToast({ message: '已删除', icon: 'success' })
      await loadData()
      return
    }
    showToast({ message: res.msg || '删除失败', icon: 'fail' })
  } catch (error) {
    if (error !== 'cancel') {
      showToast({ message: '删除失败', icon: 'fail' })
    }
  }
}

const onSubmit = async () => {
  if (!form.name) {
    showToast({ message: '请输入入口名称', icon: 'fail' })
    return
  }
  if (!form.channel_code) {
    showToast({ message: '请选择来源平台', icon: 'fail' })
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.name,
      channel_code: form.channel_code,
      landing_title: form.landing_title,
      landing_subtitle: form.landing_subtitle,
      coupon_template_id: form.coupon_template_id ? Number(form.coupon_template_id) : null,
      mini_program_qrcode_url: form.mini_program_qrcode_url,
      status: form.status
    }

    const res = isEditing.value && editingId.value
      ? await updateChannelEntry(editingId.value, payload)
      : await createChannelEntry(payload)

    if (res.code === 200) {
      showToast({ message: isEditing.value ? '已保存' : '已建', icon: 'success' })
      showFormDialog.value = false
      await loadData()
      return
    }
    showToast({ message: res.msg || '操作失败', icon: 'fail' })
  } catch (error) {
    showToast({ message: '操作失败', icon: 'fail' })
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadData()
  loadChannelOptions()
  loadCoupons()
})
</script>

<style scoped>
.channel-entry-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding-bottom: calc(96px + env(safe-area-inset-bottom));
  background: var(--bg-page);
  color: var(--text-1);
}

.page-content {
  padding: 14px 14px 0;
}

.hero-card,
.stat-card,
.tips-card,
.list-panel,
.state-card,
.entry-card {
  border-radius: 18px;
  background: var(--bg-card);
  box-shadow: var(--card-shadow);
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
  color: var(--brand);
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.stat-card {
  min-height: 72px;
  display: grid;
  place-items: center;
  text-align: center;
}

.stat-card strong,
.stat-card span,
.tips-card strong,
.tips-card p,
.entry-title strong,
.entry-title span,
.entry-link span,
.entry-link strong,
.entry-data strong,
.entry-data span {
  display: block;
}

.stat-card strong {
  font-size: 23px;
  font-weight: 900;
  color: var(--text-1);
}

.stat-card span {
  margin-top: 4px;
  color: var(--text-2);
  font-size: 12px;
}

.tips-card {
  margin-top: 12px;
  padding: 14px;
  background: var(--brand-light);
  color: var(--brand-dark);
}

.tips-card strong {
  margin-bottom: 6px;
  font-size: 15px;
}

.tips-card p {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.45;
}

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
  color: var(--brand);
  font-weight: 900;
}

.state-card {
  padding: 32px 12px;
  text-align: center;
  box-shadow: none;
}

.entry-list {
  display: grid;
  gap: 12px;
}

.entry-card {
  padding: 15px;
  border: 1px solid var(--border);
  box-shadow: none;
}

.entry-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.entry-title {
  min-width: 0;
}

.entry-title strong {
  overflow: hidden;
  color: var(--text-1);
  font-size: 18px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-title span {
  margin-top: 5px;
  color: var(--text-2);
  font-size: 13px;
}

.entry-link {
  margin-top: 12px;
  padding: 12px;
  border-radius: 14px;
  background: var(--bg-page);
}

.entry-link span {
  color: var(--text-2);
  font-size: 12px;
}

.entry-link strong {
  margin-top: 6px;
  color: var(--text-1);
  font-size: 13px;
  word-break: break-all;
}

.entry-data {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.entry-data div {
  min-height: 58px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: var(--bg-page);
  text-align: center;
}

.entry-data strong {
  max-width: 100%;
  overflow: hidden;
  font-size: 16px;
  font-weight: 900;
  color: var(--text-1);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-data span {
  margin-top: 3px;
  color: var(--text-2);
  font-size: 12px;
}

.entry-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.form-popup {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
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

.form-footer {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 12px 16px 18px;
  border-top: 1px solid var(--border);
}

@media (min-width: 768px) {
  .channel-entry-page {
    max-width: 760px;
    margin: 0 auto;
  }
}
</style>
