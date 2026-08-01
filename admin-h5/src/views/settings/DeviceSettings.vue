<template>
  <div class="sub-page device-page">
    <PageHeader title="设备与收银" />
    <div class="page-body">
      <section class="summary-card animate-in">
        <p>订单设备</p>
        <h1>{{ printerConfig.configured ? '打印已就绪' : '建议配置打印机' }}</h1>
        <span>{{ printerConfig.configured ? '订单和排位小票可自动打印' : '配置后减少人工接单和手写小票' }}</span>
      </section>

      <section class="panel-card animate-in" style="animation-delay:.04s">
        <div class="panel-head"><div><strong>小票打印机</strong><span>订单提交后自动推送到后厨</span></div><a-tag :class="printerConfig.configured ? 'tag-ok' : 'tag-warn'">{{ printerConfig.configured ? '已配置' : '未配置' }}</a-tag></div>
        <div class="form-block">
          <a-form layout="vertical">
            <a-form-item label="打印机类型" style="margin-bottom:10px">
              <a-radio-group v-model:value="printerForm.printer_provider" button-style="solid" style="width:100%">
                <a-radio-button value="feieyun" style="width:50%;text-align:center">飞鹅云</a-radio-button>
                <a-radio-button value="kuaimai" style="width:50%;text-align:center">快麦</a-radio-button>
              </a-radio-group>
            </a-form-item>
            <template v-if="printerForm.printer_provider === 'kuaimai'">
              <a-form-item label="快麦 appId"><a-input v-model:value="printerForm.kuaimai_app_id" placeholder="快麦开放平台 appId" allow-clear /></a-form-item>
              <a-form-item label="快麦 appSecret"><a-input-password v-model:value="printerForm.kuaimai_app_secret" placeholder="快麦开放平台 appSecret" allow-clear /></a-form-item>
              <a-form-item label="快麦 shareCode"><a-input v-model:value="printerForm.kuaimai_share_code" placeholder="快麦开放平台 shareCode" allow-clear /></a-form-item>
              <a-form-item label="快麦打印机 SN"><a-input v-model:value="printerForm.kuaimai_sn" placeholder="打印机序列号 SN" allow-clear /></a-form-item>
              <a-form-item label="设备密钥（可选）"><a-input v-model:value="printerForm.kuaimai_device_key" placeholder="机身贴有设备密钥时填写" allow-clear /></a-form-item>
            </template>
            <template v-else>
              <a-form-item label="打印机编号（SN）"><a-input v-model:value="printerForm.feieyun_sn" placeholder="打印机底部标签上的 SN 号" allow-clear /></a-form-item>
              <a-form-item label="打印机识别码（KEY）"><a-input v-model:value="printerForm.feieyun_key" placeholder="打印机底部标签上的 KEY" allow-clear /></a-form-item>
            </template>
            <a-button type="primary" block size="large" :loading="savingPrinter" @click="savePrinter">保存打印机配置</a-button>
          </a-form>
        </div>
      </section>

      <section class="panel-card animate-in" style="animation-delay:.08s">
        <div class="panel-head"><div><strong>排位设备</strong><span>排位小票和大屏叫号</span></div></div>
        <div class="queue-block">
          <div class="queue-row"><span>排位小票打印</span><a-tag v-if="printerConfig.configured" color="green">{{ queuePrinterStatusText }}</a-tag><a-tag v-else>未配置</a-tag></div>
          <a-button type="primary" block :disabled="!printerConfig.configured" :loading="testingQueuePrint" @click="testQueuePrint">测试打印排位小票</a-button>
          <div class="queue-link">{{ queueDisplayUrl || '加载商户信息后生成大屏链接' }}</div>
          <div class="queue-actions"><a-button type="primary" @click="copyQueueDisplayUrl">复制大屏链接</a-button><a-button @click="openQueueDisplay">打开大屏</a-button></div>
          <img v-if="queueDisplayQr" class="queue-display-qr" :src="queueDisplayQr" alt="排位大屏二维码" />
        </div>
      </section>

      <section class="panel-card animate-in" style="animation-delay:.12s">
        <div class="panel-head"><div><strong>收银 API</strong><span>给自动扫码收银机对接使用</span></div></div>
        <template v-if="posConfig">
          <div class="info-row"><span class="info-label">接口地址</span><span class="info-value">{{ posConfig.verify_url }}</span></div>
          <div class="info-row"><span class="info-label">商户</span><span class="info-value">{{ posConfig.tenant_id || tenantId }}</span></div>
          <div class="info-row"><span class="info-label">API Key</span><span class="info-value">{{ posConfig.masked_api_key }}</span></div>
        </template>
        <div v-else class="empty-tip">点击刷新加载收银对接参数</div>
        <div class="action-row"><a-button @click="loadPosConfig">刷新</a-button><a-button type="primary" @click="copyPosExample">复制参数</a-button><a-button danger @click="handleResetPosKey">重置密钥</a-button></div>
      </section>

      <section class="panel-card animate-in" style="animation-delay:.16s">
        <div class="panel-head"><div><strong>碰一碰标签</strong><span>手机一碰打开入会、领券或加微信</span></div></div>
        <div class="touch-grid">
          <button v-for="item in touchActions" :key="item.value" class="tap-shrink" :class="{ active: touchForm.action === item.value }" @click="touchForm.action = item.value"><strong>{{ item.label }}</strong><span>{{ item.desc }}</span></button>
        </div>
        <div class="form-block compact">
          <a-input v-model:value="touchForm.remark" placeholder="放在哪里，例如：1号桌" style="margin-bottom:8px" />
          <a-input v-if="touchForm.action === 'custom'" v-model:value="touchForm.customUrl" placeholder="自定义跳转链接" style="margin-bottom:8px" />
          <div class="touch-url">{{ touchUrl || touchUrlTip }}</div>
          <div class="touch-actions"><a-button :disabled="!touchUrl" type="primary" @click="copyTouchUrl">复制链接</a-button><a-button @click="refreshTouchSources">刷新链接</a-button></div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import QRCode from 'qrcode'
import { Modal, message } from 'ant-design-vue'
import PageHeader from '../../components/PageHeader.vue'
import {
  getChannelEntries, getPosVerifyConfig, getPrinterConfig, getTenantProfile, getWeworkContactWays,
  printTestQueueTicket, resetPosApiKey, updatePrinterConfig,
} from '../../api'

const router = useRouter()
const merchant = ref({})
const posConfig = ref(null)
const printerConfig = ref({ configured: false })
const channelEntries = ref([])
const weworkContactWays = ref([])
const queueDisplayQr = ref('')
const savingPrinter = ref(false)
const testingQueuePrint = ref(false)
const touchForm = ref({ action: 'member', remark: '收银台', customUrl: '' })
const printerForm = ref({
  printer_provider: 'feieyun', feieyun_sn: '', feieyun_key: '', kuaimai_app_id: '', kuaimai_app_secret: '', kuaimai_share_code: '', kuaimai_sn: '', kuaimai_device_key: '',
  queue_query_enabled: true, queue_ticket_qrcode_enabled: true, queue_qrcode_tip: '扫码查看实时排队进度',
})
const touchActions = [
  { value: 'member', label: '注册会员', desc: '碰一下入会领券' },
  { value: 'coupon', label: '领优惠券', desc: '碰一下领券' },
  { value: 'wework', label: '加微信', desc: '碰一下加员工' },
  { value: 'custom', label: '自定义', desc: '点评/点餐/笔记' },
]
const tenantId = computed(() => merchant.value.tenant_id || merchant.value.id || '')
const publicBaseUrl = computed(() => (import.meta.env.VITE_PUBLIC_BASE_URL || window.location.origin).replace(/\/$/, ''))
const queueDisplayUrl = computed(() => tenantId.value ? `${publicBaseUrl.value}/queue/display?tenant_id=${encodeURIComponent(tenantId.value)}` : '')
const queuePrinterStatusText = computed(() => printerConfig.value.printer_provider === 'kuaimai' ? '快麦已配置' : '飞鹅云已配置')
const firstH5Entry = computed(() => channelEntries.value.find(i => i.status === 1 && i.h5_url) || channelEntries.value.find(i => i.h5_url) || null)
const firstWeworkWay = computed(() => weworkContactWays.value.find(i => i.qr_url || i.qr_code) || null)
const touchUrlTip = computed(() => {
  if (touchForm.value.action === 'custom') return '请先粘贴要跳转的链接'
  if (touchForm.value.action === 'wework') return '请先到企业微信页面生成二维码'
  return '请先建一个 H5 领券页'
})
const touchUrl = computed(() => {
  if (touchForm.value.action === 'custom') return touchForm.value.customUrl.trim()
  if (touchForm.value.action === 'wework') return normalizeUrl(firstWeworkWay.value?.qr_url || firstWeworkWay.value?.qr_code || '')
  return withTouchParams(firstH5Entry.value?.h5_url || '')
})

function rowsFrom(payload) {
  if (!payload) return []
  if (Array.isArray(payload)) return payload
  return payload.items || payload.results || payload.data || []
}
function normalizeUrl(url) {
  if (!url) return ''
  if (url.startsWith('http') || url.includes('://')) return url
  if (url.startsWith('/')) return `${window.location.origin}${url}`
  return url
}
function withTouchParams(url) {
  const resolved = normalizeUrl(url)
  if (!resolved || !tenantId.value) return resolved
  try {
    const target = new URL(resolved)
    target.searchParams.set('touch', '1')
    target.searchParams.set('tenant_id', tenantId.value)
    if (touchForm.value.remark) target.searchParams.set('touch_place', touchForm.value.remark)
    return target.toString()
  } catch { return resolved }
}
async function copyText(text) {
  if (navigator?.clipboard?.writeText) { await navigator.clipboard.writeText(text); return }
  const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px'
  document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta)
}
async function loadProfile() {
  const res = await getTenantProfile()
  if (res.code === 200 && res.data) merchant.value = res.data
}
async function loadPrinterConfig() {
  const res = await getPrinterConfig()
  if (res.code === 200 && res.data) {
    printerConfig.value = res.data
    printerForm.value = {
      printer_provider: res.data.printer_provider || 'feieyun', feieyun_sn: res.data.feieyun_sn || '', feieyun_key: res.data.feieyun_key || '',
      kuaimai_app_id: res.data.kuaimai_app_id || '', kuaimai_app_secret: res.data.kuaimai_app_secret || '', kuaimai_share_code: res.data.kuaimai_share_code || '',
      kuaimai_sn: res.data.kuaimai_sn || '', kuaimai_device_key: res.data.kuaimai_device_key || '', queue_query_enabled: res.data.queue_query_enabled ?? true,
      queue_ticket_qrcode_enabled: res.data.queue_ticket_qrcode_enabled ?? true, queue_qrcode_tip: res.data.queue_qrcode_tip || '扫码查看实时排队进度',
    }
  }
}
async function loadPosConfig() {
  try {
    const res = await getPosVerifyConfig()
    if (res.code === 200) { posConfig.value = res.data; return }
    message.error(res.msg || '收银 API 加载失败')
  } catch { message.error('收银 API 加载失败') }
}
async function loadTouchSources() {
  const [h5Res, weworkRes] = await Promise.allSettled([getChannelEntries({ page: 1, page_size: 100 }), getWeworkContactWays({ page: 1, page_size: 20 })])
  if (h5Res.status === 'fulfilled' && h5Res.value.code === 200) channelEntries.value = rowsFrom(h5Res.value.data)
  if (weworkRes.status === 'fulfilled' && weworkRes.value.code === 200) weworkContactWays.value = rowsFrom(weworkRes.value.data)
}
async function savePrinter() {
  savingPrinter.value = true
  try {
    const res = await updatePrinterConfig(printerForm.value)
    if (res.code === 200) { message.success('打印机配置已保存'); await loadPrinterConfig(); return }
    message.error(res.msg || '保存失败')
  } catch { message.error('保存失败') }
  finally { savingPrinter.value = false }
}
async function testQueuePrint() {
  if (!printerConfig.value.configured) { message.warning('请先配置打印机'); return }
  testingQueuePrint.value = true
  try {
    const res = await printTestQueueTicket()
    if (res?.success === false) throw new Error(res.message || '测试打印失败')
    message.success('排位小票测试打印已发送')
  } catch (err) { message.error(err?.message || '测试打印失败') }
  finally { testingQueuePrint.value = false }
}
async function copyQueueDisplayUrl() {
  if (!queueDisplayUrl.value) { message.warning('请先加载商户信息'); return }
  try { await copyText(queueDisplayUrl.value); message.success('排位大屏链接已复制') } catch { message.error('复制失败，请手动复制') }
}
function openQueueDisplay() {
  if (!queueDisplayUrl.value) { message.warning('请先加载商户信息'); return }
  window.open(queueDisplayUrl.value, '_blank')
}
async function buildQueueDisplayQr() {
  if (!queueDisplayUrl.value) { queueDisplayQr.value = ''; return }
  try { queueDisplayQr.value = await QRCode.toDataURL(queueDisplayUrl.value, { width: 180, margin: 1 }) }
  catch { queueDisplayQr.value = '' }
}
async function copyTouchUrl() {
  if (!touchUrl.value) { message.warning(touchUrlTip.value); return }
  try { await copyText(touchUrl.value); message.success('碰一碰链接已复制') } catch { message.error('复制失败，请手动复制') }
}
async function refreshTouchSources() { await loadTouchSources(); message.success('可用链接已刷新') }
async function copyPosExample() {
  if (!posConfig.value) await loadPosConfig()
  if (!posConfig.value) return
  const text = [`收银系统对接接口`, `URL: ${posConfig.value.verify_url}`, `Method: POST`, `Body:`, JSON.stringify(posConfig.value.example || {}, null, 2)].join('\n')
  try { await copyText(text); message.success('收银对接参数已复制') } catch { message.error('复制失败') }
}
function handleResetPosKey() {
  Modal.confirm({
    title: '重置 API Key',
    content: '重置后，收银系统需要同步新密钥，否则无法核销。',
    okText: '确认重置', okType: 'danger',
    onOk: async () => {
      const res = await resetPosApiKey()
      if (res.code === 200) { posConfig.value = res.data; message.success('密钥已重置') }
      else message.error(res.msg || '密钥重置失败')
    },
  })
}

watch(queueDisplayUrl, buildQueueDisplayQr, { immediate: true })
onMounted(async () => {
  try { await Promise.all([loadProfile(), loadPrinterConfig(), loadPosConfig(), loadTouchSources()]) }
  catch { message.error('设备设置加载失败') }
})
</script>

<style scoped>
.device-page { min-height: 100vh; background: var(--bg-page); }
.page-body { padding: 12px 16px 28px; }
.summary-card, .panel-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--card-shadow); }
.summary-card { padding: 18px; }
.summary-card p, .summary-card h1, .summary-card span { display: block; margin: 0; }
.summary-card p { color: var(--warning); font-size: 12px; font-weight: 900; }
.summary-card h1 { margin-top: 5px; color: var(--text-1); font-size: 22px; font-weight: 900; }
.summary-card span { margin-top: 6px; color: var(--text-2); font-size: 13px; }
.panel-card { margin-top: 12px; overflow: hidden; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 14px 16px 10px; border-bottom: 1px solid var(--border); }
.panel-head strong, .panel-head span { display: block; }
.panel-head strong { color: var(--text-1); font-size: 15px; font-weight: 900; }
.panel-head span { margin-top: 4px; color: var(--text-2); font-size: 12px; }
.tag-ok, .tag-warn { margin: 0; border-radius: 12px; font-size: 11px; font-weight: 800; }
.tag-ok { color: #16a34a; background: #f0fdf4; border-color: #bbf7d0; }
.tag-warn { color: #92400e; background: #fffbeb; border-color: #fde68a; }
.form-block { padding: 14px 16px 16px; }
.form-block.compact { padding-top: 0; }
.queue-block { padding: 14px 16px 16px; }
.queue-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; color: var(--text-1); font-size: 14px; font-weight: 800; }
.queue-link, .touch-url { margin-top: 12px; padding: 10px 12px; border-radius: 10px; background: var(--bg-page); color: var(--text-1); font-size: 12px; line-height: 1.5; word-break: break-all; }
.queue-actions, .touch-actions, .action-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 10px; }
.action-row { grid-template-columns: repeat(3, 1fr); padding: 12px 16px; border-top: 1px solid var(--border); }
.queue-display-qr { display: block; width: 128px; height: 128px; margin: 12px auto 0; }
.empty-tip { padding: 16px; color: var(--text-2); font-size: 13px; background: var(--bg-page); }
.touch-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; padding: 14px 16px; }
.touch-grid button { border: 1px solid var(--border); border-radius: 10px; background: var(--bg-page); color: var(--text-1); padding: 10px 12px; text-align: left; }
.touch-grid button.active { border-color: var(--brand); background: var(--brand-light); }
.touch-grid strong, .touch-grid span { display: block; }
.touch-grid strong { color: var(--text-1); font-size: 14px; font-weight: 800; }
.touch-grid span { margin-top: 3px; color: var(--text-2); font-size: 11px; }
@media (max-width: 390px) { .action-row { grid-template-columns: 1fr; } }
</style>
