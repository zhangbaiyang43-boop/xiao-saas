<template>
  <div class="wework-page">
    <PageHeader title="企业微信" />

    <div class="page-content">
    <section class="hero-card animate-in">
      <div>
        <p class="eyebrow">企业微信</p>
        <h1>把顾客加到员工企微</h1>
        <p>先测试连接，再生成“联系我”二维码，顾客扫码后可进入后续会员运营。</p>
      </div>
      <van-tag :type="isConnected ? 'success' : 'danger'" round>
        {{ isConnected ? '已连接' : '未连接' }}
      </van-tag>
    </section>

    <section class="panel animate-in" style="animation-delay:.04s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">第一步</p>
          <h2>连接检测</h2>
          <span>确认 Corp、Agent、Secret 配置正确，后端能获取 access_token。</span>
        </div>
      </div>

      <div class="config-list">
        <div>
          <span>Corp</span>
          <strong>{{ config.corpId || '-' }}</strong>
        </div>
        <div>
          <span>Agent</span>
          <strong>{{ config.agentId || '-' }}</strong>
        </div>
        <div>
          <span>员工 User</span>
          <strong>{{ config.userId || '-' }}</strong>
        </div>
      </div>

      <van-button block round type="primary" :loading="testing" @click="testConnection">
        测试企业微信连接
      </van-button>
      <p v-if="lastTestMessage" :class="['test-message', { success: isConnected }]">{{ lastTestMessage }}</p>
    </section>

    <section class="panel animate-in" style="animation-delay:.08s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">第二步</p>
          <h2>生成联系我二维码</h2>
          <span>顾客扫码后添加员工，适合放在桌贴、海报、收银台。</span>
        </div>
        <button class="text-btn tap-shrink" @click="showCreatePopup = true">生成</button>
      </div>

      <div v-if="qrLoading" class="state-card">
        <van-loading size="24px">正在加载二维码</van-loading>
      </div>

      <div v-else-if="qrList.length === 0" class="state-card">
        <van-empty description="暂无企微二维码">
          <van-button round type="primary" size="small" @click="showCreatePopup = true">生成二维码</van-button>
        </van-empty>
      </div>

      <div v-else class="qr-list">
        <article v-for="qr in qrList" :key="qr.config_id || qr.id" class="qr-card tap-shrink">
          <div class="qr-preview">
            <img v-if="qrImage(qr)" :src="qrImage(qr)" alt="企业微信二维码" />
            <van-icon v-else name="qr" size="32" />
          </div>
          <div class="qr-main">
            <strong>{{ qr.remark || qr.scene || '联系我二维码' }}</strong>
            <span>员工：{{ qr.userid || config.userId || '-' }}</span>
            <span>时间：{{ formatTime(qr.created_at) }}</span>
          </div>
          <van-button round plain type="primary" size="small" @click="openQR(qr)">查看</van-button>
        </article>
      </div>
    </section>

    <section class="panel animate-in" style="animation-delay:.12s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">第三步</p>
          <h2>最近企微事件</h2>
          <span>这里显示客户添加员工、删除客户、扫码联系我等事件。</span>
        </div>
        <button class="text-btn tap-shrink" @click="loadEvents">刷新</button>
      </div>

      <div v-if="eventLoading" class="state-card">
        <van-loading size="24px">正在加载事件</van-loading>
      </div>

      <div v-else-if="events.length === 0" class="state-card">
        <van-empty description="暂无企微事件" />
      </div>

      <div v-else class="event-list">
        <article v-for="event in events" :key="event.id" class="event-card tap-shrink">
          <div class="event-icon">
            <van-icon :name="getEventIcon(event.event_type)" size="20" />
          </div>
          <div class="event-main">
            <strong>{{ getEventText(event.event_type) }}</strong>
            <span>客户：{{ event.external_userid || '-' }}</span>
            <span>员工：{{ event.userid || '-' }}</span>
          </div>
          <time>{{ formatTime(event.event_time || event.created_at) }}</time>
        </article>
      </div>
    </section>
    </div>

    <van-popup v-model:show="showCreatePopup" position="bottom" round>
      <div class="popup">
        <h2>生成企微二维码</h2>
        <p>场景名称用于区分这个二维码放在哪里。</p>
        <van-field v-model.trim="newQR.scene" label="场景" placeholder="例如：收银台、1号桌、抖音主页" />
        <van-field v-model.trim="newQR.remark" label="备注" placeholder="可选" />
        <van-cell title="扫码后自动通过好友" center>
          <template #right-icon>
            <van-switch v-model="newQR.skip_verify" size="24" />
          </template>
        </van-cell>
        <van-button block round type="primary" :loading="creating" @click="createQR">生成二维码</van-button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import {
  Button as VanButton,
  Cell as VanCell,
  Empty as VanEmpty,
  Field as VanField,
  Icon as VanIcon,
  Loading as VanLoading,
  Popup as VanPopup,
  Switch as VanSwitch,
  Tag as VanTag,
  showToast
} from 'vant'
import PageHeader from '../components/PageHeader.vue'
import {
  createWeworkContactWay,
  getWeworkConfigStatus,
  getWeworkContactWays,
  getWeworkEvents,
  testWeworkAccessToken
} from '../api'

const isConnected = ref(false)
const testing = ref(false)
const creating = ref(false)
const qrLoading = ref(false)
const eventLoading = ref(false)
const lastTestMessage = ref('')
const showCreatePopup = ref(false)

const config = ref({
  corpId: '-',
  agentId: '-',
  userId: '-'
})

const newQR = ref({
  scene: '',
  remark: '',
  skip_verify: true
})
const qrList = ref([])
const events = ref([])

const rowsFrom = (payload) => {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.results)) return payload.results
  if (Array.isArray(payload?.data)) return payload.data
  return []
}

const getEventIcon = (type) => {
  const map = {
    add_user: 'friends-o',
    add_external_contact: 'friends-o',
    delete_user: 'close',
    del_external_contact: 'close',
    scan_qr: 'scan',
    contact_way: 'qr'
  }
  return map[type] || 'user-o'
}

const getEventText = (type) => {
  const map = {
    add_user: '添加客户',
    add_external_contact: '添加客户',
    delete_user: '删除客户',
    del_external_contact: '删除客户',
    scan_qr: '扫联系我二维码',
    contact_way: '联系我事件'
  }
  return map[type] || type || '企微事件'
}

const formatTime = (time) => {
  if (!time) return '-'
  const d = new Date(time)
  if (Number.isNaN(d.getTime())) return '-'
  const pad = (value) => String(value).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const qrImage = (qr) => qr.qr_url || qr.qr_code || ''

const loadConfig = async () => {
  try {
    const res = await getWeworkConfigStatus()
    if (res.code === 200 && res.data) {
      isConnected.value = !!res.data.connected
      config.value.corpId = res.data.corp_id || '-'
      config.value.agentId = res.data.agent_id || '-'
      config.value.userId = res.data.user_id || '-'
    }
  } catch (error) {
    lastTestMessage.value = '配置加载失败，请检查后端服务'
  }
}

const loadQRList = async () => {
  qrLoading.value = true
  try {
    const res = await getWeworkContactWays({ page: 1, page_size: 20 })
    if (res.code === 200 && res.data) {
      qrList.value = rowsFrom(res.data)
    }
  } catch (error) {
    showToast({ message: '二维码加载失败', icon: 'fail' })
  } finally {
    qrLoading.value = false
  }
}

const loadEvents = async () => {
  eventLoading.value = true
  try {
    const res = await getWeworkEvents({ page: 1, page_size: 20 })
    if (res.code === 200 && res.data) {
      events.value = rowsFrom(res.data)
    }
  } catch (error) {
    showToast({ message: '事件加载失败', icon: 'fail' })
  } finally {
    eventLoading.value = false
  }
}

const testConnection = async () => {
  testing.value = true
  lastTestMessage.value = ''
  try {
    const res = await testWeworkAccessToken()
    if (res.code === 200) {
      isConnected.value = true
      const expires = res.data?.expires_in ? `，有效期 ${res.data.expires_in} 秒` : ''
      lastTestMessage.value = `企业微信连接成功${expires}`
      showToast({ message: '连接成功', icon: 'success' })
      await loadConfig()
      return
    }
    isConnected.value = false
    lastTestMessage.value = res.msg || '连接失败，请检查配置'
    showToast({ message: lastTestMessage.value, icon: 'fail' })
  } catch (error) {
    isConnected.value = false
    lastTestMessage.value = error?.response?.data?.msg || error?.message || '连接失败，请检查 Corp、Secret 或可信 IP'
    showToast({ message: lastTestMessage.value, icon: 'fail' })
  } finally {
    testing.value = false
  }
}

const createQR = async () => {
  if (!newQR.value.scene) {
    showToast({ message: '请输入场景名称', icon: 'fail' })
    return
  }
  creating.value = true
  try {
    const res = await createWeworkContactWay({
      scene: newQR.value.scene,
      remark: newQR.value.remark,
      skip_verify: newQR.value.skip_verify
    })
    if (res.code === 200) {
      showToast({ message: '二维码已生成', icon: 'success' })
      showCreatePopup.value = false
      newQR.value = { scene: '', remark: '', skip_verify: true }
      await loadQRList()
      return
    }
    showToast({ message: res.msg || '生成失败', icon: 'fail' })
  } catch (error) {
    showToast({ message: '生成失败，请检查企微配置', icon: 'fail' })
  } finally {
    creating.value = false
  }
}

const openQR = (qr) => {
  const url = qrImage(qr)
  if (!url) {
    showToast({ message: '暂无二维码图片', icon: 'fail' })
    return
  }
  window.open(url, '_blank')
}

onMounted(() => {
  loadConfig()
  loadQRList()
  loadEvents()
})
</script>

<style scoped>
.wework-page {
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
.panel,
.state-card,
.qr-card,
.event-card {
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
.popup h2 {
  margin: 0;
  color: var(--text-1);
  font-weight: 900;
  letter-spacing: 0;
}

.hero-card h1 {
  font-size: 22px;
}

.hero-card p:not(.eyebrow),
.panel-head span,
.popup p {
  display: block;
  margin: 6px 0 0;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.45;
}

.panel {
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

.config-list {
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
}

.config-list div {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}

.config-list div:last-child {
  border-bottom: 0;
}

.config-list span,
.config-list strong {
  display: block;
}

.config-list span {
  color: var(--text-2);
  font-size: 13px;
}

.config-list strong {
  min-width: 0;
  word-break: break-all;
  font-size: 13px;
  color: var(--text-1);
}

.test-message {
  margin: 10px 0 0;
  color: var(--danger);
  font-size: 13px;
}

.test-message.success {
  color: var(--success);
}

.state-card {
  padding: 32px 12px;
  text-align: center;
  box-shadow: none;
}

.qr-list,
.event-list {
  display: grid;
  gap: 10px;
}

.qr-card,
.event-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border);
  box-shadow: none;
}

.qr-preview {
  width: 74px;
  height: 74px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 16px;
  background: var(--bg-page);
  color: var(--text-3);
}

.qr-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.qr-main,
.event-main {
  min-width: 0;
  flex: 1;
}

.qr-main strong,
.qr-main span,
.event-main strong,
.event-main span {
  display: block;
}

.qr-main strong,
.event-main strong {
  overflow: hidden;
  color: var(--text-1);
  font-size: 16px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qr-main span,
.event-main span {
  margin-top: 4px;
  color: var(--text-2);
  font-size: 12px;
}

.event-icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 14px;
  background: var(--brand-light);
  color: var(--brand);
}

.event-card time {
  max-width: 78px;
  color: var(--text-3);
  font-size: 12px;
  text-align: right;
}

.popup {
  padding: 22px 16px 28px;
  background: var(--bg-card);
}

.popup h2 {
  font-size: 20px;
}

.popup p {
  margin-bottom: 12px;
}

.popup :deep(.van-button) {
  margin-top: 14px;
}

@media (min-width: 768px) {
  .wework-page {
    max-width: 760px;
    margin: 0 auto;
  }
}
</style>
