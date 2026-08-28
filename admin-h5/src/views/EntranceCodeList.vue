<template>
  <div class="sub-page">
    <PageHeader title="桌码管理">
      <a-button type="primary" size="small" @click="openCreate">
        <template #icon><PlusOutlined /></template>新建码
      </a-button>
    </PageHeader>

    <div v-if="isOnboarding" class="onboarding-banner">
      <span>新手引导 · 生成一个桌码</span>
      <button type="button" class="onboarding-back-link" @click="router.push('/activation')">返回开店引导</button>
    </div>

    <div class="page-body">
      <!-- 统计卡 -->
      <a-card :bordered="false" class="animate-in" style="margin-bottom:12px">
        <div class="stat-grid">
          <div class="stat-cell">
            <span class="stat-num">{{ summary.code_count || 0 }}</span>
            <span class="stat-label">入口码</span>
          </div>
          <div class="stat-cell">
            <span class="stat-num">{{ summary.scan_count || 0 }}</span>
            <span class="stat-label">扫码次数</span>
          </div>
          <div class="stat-cell">
            <span class="stat-num" style="color:var(--brand)">{{ summary.member_count || 0 }}</span>
            <span class="stat-label">新增会员</span>
          </div>
          <div class="stat-cell">
            <span class="stat-num" style="color:var(--brand)">{{ overallConversionText }}</span>
            <span class="stat-label">平均转化率</span>
          </div>
        </div>
      </a-card>

      <!-- 场景筛选 -->
      <a-tabs v-model:activeKey="channelFilter" class="animate-in" style="padding:0 16px;animation-delay:.02s" :tab-bar-style="{ marginBottom: 0 }">
        <a-tab-pane key="ALL" tab="全部" />
        <a-tab-pane key="TABLE" tab="桌贴码" />
        <a-tab-pane key="POSTER" tab="海报码" />
        <a-tab-pane key="DOUYIN" tab="抖音码" />
      </a-tabs>

      <!-- 码列表 -->
      <a-card :bordered="false" :body-style="{ padding: 0 }" class="animate-in" style="animation-delay:.04s;margin-top:12px">
        <template #title>
          我的入口码
          <a-button type="text" size="small" style="font-weight:400;color:var(--text-2)" @click="toggleSort">
            <SortAscendingOutlined />{{ sortLabel }}
          </a-button>
        </template>
        <template #extra>
          <a-button type="text" size="small" @click="loadData" :loading="loading" style="color:var(--brand)">刷新</a-button>
        </template>

        <div v-if="loading" style="display:flex;justify-content:center;padding:40px">
          <a-spin />
        </div>

        <a-empty v-else-if="codes.length === 0" description="还没有入口码，点右上角「新建码」生成" style="padding:40px 0">
          <a-button type="primary" @click="openCreate">生成第一个入口码</a-button>
        </a-empty>

        <a-empty v-else-if="displayCodes.length === 0" description="这个场景下还没有码" style="padding:40px 0" />

        <template v-else>
          <!-- 选择 + 批量操作条 -->
          <div class="bulk-bar">
            <a-checkbox :checked="allSelected" :indeterminate="someSelected" @change="toggleSelectAll">
              全选<span v-if="selectedIds.length"> · 已选 {{ selectedIds.length }}</span>
            </a-checkbox>
            <div class="bulk-actions">
              <a-button size="small" type="primary" :loading="batchBusy === 'download'" :disabled="!selectedIds.length" @click="onBatchDownload">批量下载</a-button>
              <a-button size="small" :loading="batchBusy === 'sticker'" :disabled="!selectedIds.length" @click="openStickerExport">印刷版桌贴</a-button>
              <a-button size="small" :loading="batchBusy === 'disable'" :disabled="!selectedIds.length" @click="onBatchDisable">批量停用</a-button>
              <a-popconfirm title="删除后已张贴的贴纸会失效，且扫码统计一并清除。确定删除选中的码？" ok-text="删除" cancel-text="取消" @confirm="onBatchDelete">
                <a-button size="small" danger :loading="batchBusy === 'delete'" :disabled="!selectedIds.length">批量删除</a-button>
              </a-popconfirm>
            </div>
          </div>
          <div v-if="trialCodes.length" class="bulk-bar" style="border-top:none;padding-top:0">
            <span style="font-size:12px;color:var(--warning)"><WarningOutlined /> 有 {{ trialCodes.length }} 张体验码，顾客扫不开</span>
            <a-button size="small" :loading="batchBusy === 'convert'" @click="onConvertTrial">全部转为正式码</a-button>
          </div>

          <div v-for="code in displayCodes" :key="code.id" class="code-row" :class="{ 'is-disabled': code.status !== 1 }">
            <a-checkbox class="code-check" :checked="selectedIds.includes(code.id)" @change="() => toggleSelect(code.id)" />
            <div class="code-image tap-shrink" role="button" :aria-label="`查看${codeTitle(code)}`" @click="downloadCode(code)">
              <img
                v-if="code.image_url"
                :src="resolveAssetUrl(code.image_url)"
                :alt="codeTitle(code)"
                @error="e => { e.target.style.display='none'; e.target.nextElementSibling.style.display='flex' }"
              />
              <QrcodeOutlined style="font-size:32px;color:var(--text-3)" :style="code.image_url ? 'display:none' : 'display:flex'" />
              <span v-if="code.channel === 'TABLE' && code.table_no" class="code-image-tag">{{ code.table_no }}</span>
            </div>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap">
                <span
                  style="font-size:15px;font-weight:700"
                  :style="code.channel === 'TABLE' && !code.table_no ? 'color:var(--danger)' : 'color:var(--text-1)'"
                >{{ codeTitle(code) }}</span>
                <a-tag style="color:var(--brand);background:var(--brand-light);border-color:var(--brand-mid);font-size:11px">{{ channelText(code.channel) }}</a-tag>
                <a-tag v-if="code.channel === 'TABLE'" style="font-size:11px">{{ zoneText(code.zone_type) }}</a-tag>
                <a-tag v-if="code.status !== 1" style="font-size:11px;color:var(--text-3)">已停用</a-tag>
                <a-tag v-if="conversionTag(code)" :style="conversionTag(code).style">{{ conversionTag(code).label }}</a-tag>
              </div>
              <div v-if="code.channel === 'TABLE' && code.name && code.name !== code.table_no" style="font-size:12px;color:var(--text-3);margin-bottom:2px">备注：{{ code.name }}</div>
              <div style="font-size:13px;color:var(--text-2)">
                扫码 <b style="color:var(--text-1)">{{ code.scan_count || 0 }}</b> 次 · 入会 <b style="color:var(--text-1)">{{ code.register_count || code.member_count || 0 }}</b> 人
              </div>
              <div v-if="(code.scan_count || 0) === 0 && code.status === 1" style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--danger);margin-top:4px"><WarningOutlined />还没人扫码，检查是否已张贴</div>
              <div v-if="code.env_version !== 'release'" style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--warning);margin-top:4px"><WarningOutlined />体验码，需重新生成</div>
              <div v-if="code.generation_error" style="font-size:12px;color:var(--danger);margin-top:4px">{{ code.generation_error }}</div>
              <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
                <a-button size="small" @click="viewCode(code)">查看</a-button>
                <a-button size="small" :loading="regenerating === code.id" @click="onRegenerate(code)">重新生成</a-button>
                <a-button size="small" type="primary" @click="downloadCode(code)">下载</a-button>
                <a-button size="small" :loading="statusBusy === code.id" @click="onToggleStatus(code)">{{ code.status === 1 ? '停用' : '启用' }}</a-button>
                <a-popconfirm
                  title="删除后已张贴的贴纸会失效，扫码统计一并清除。建议先用「停用」。"
                  ok-text="仍要删除" cancel-text="取消" @confirm="onDelete(code)"
                >
                  <a-button size="small" danger :loading="deleteBusy === code.id">删除</a-button>
                </a-popconfirm>
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:6px;padding:12px 16px;font-size:12px;color:var(--brand);background:var(--brand-light);margin:0;border-radius:0 0 12px 12px">
            <InfoCircleOutlined style="margin-top:1px;flex-shrink:0" />
            <span style="color:var(--text-2)">打印前先用两台手机各扫一次，确认进入的是本店、桌号对得上。下载后发微信找附近打印店，剪开贴桌上即可。</span>
          </div>
        </template>
      </a-card>
    </div>

    <!-- 生码 Drawer：场景只在这里选一次，不在主页面重复放一个不联动的选择器 -->
    <a-drawer v-model:open="showCreateDialog" title="生成入口码" placement="bottom" height="auto">
      <a-form layout="vertical" @finish="onSubmit">
        <a-form-item label="码名称" :rules="[{ required: true, message: '请填写码名称' }]">
          <a-input v-model:value="form.name" placeholder="例如：1号桌贴" allow-clear />
        </a-form-item>
        <a-form-item v-if="!isOnboarding" label="使用场景">
          <a-row :gutter="8">
            <a-col :span="8" v-for="item in scenes" :key="item.value">
              <div class="scene-btn tap-shrink" :class="{ active: form.channel === item.value }" @click="pickScene(item)">
                <component :is="item.icon" style="font-size:20px;margin-bottom:4px" />
                <strong>{{ item.title }}</strong>
              </div>
            </a-col>
          </a-row>
        </a-form-item>
        <a-form-item v-if="form.channel === 'TABLE' && !isOnboarding" label="生成方式">
          <a-radio-group v-model:value="createMode" button-style="solid" size="small">
            <a-radio-button value="single">单个</a-radio-button>
            <a-radio-button value="batch">批量（一次建一排）</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="form.channel === 'TABLE' && createMode === 'single'" label="桌号">
          <a-input v-model:value="form.table_no" placeholder="例如：A01（顾客点餐用，要和桌上的桌牌一致）" allow-clear />
        </a-form-item>
        <template v-if="form.channel === 'TABLE' && createMode === 'batch' && !isOnboarding">
          <a-form-item label="桌号规则">
            <a-row :gutter="8">
              <a-col :span="8"><a-input v-model:value="batchForm.prefix" placeholder="前缀 如 A" allow-clear /></a-col>
              <a-col :span="5"><a-input-number v-model:value="batchForm.start" :min="0" :max="999" style="width:100%" placeholder="起" /></a-col>
              <a-col :span="5"><a-input-number v-model:value="batchForm.end" :min="0" :max="999" style="width:100%" placeholder="止" /></a-col>
              <a-col :span="6"><a-input-number v-model:value="batchForm.pad" :min="1" :max="4" style="width:100%" placeholder="补零位数" /></a-col>
            </a-row>
            <div style="margin-top:6px;font-size:12px;color:var(--text-2)">补零位数：2 → 01、02…{{ '　' }}{{ batchPreview }}</div>
          </a-form-item>
        </template>
        <a-form-item v-if="form.channel === 'TABLE'" label="桌台分区">
          <a-row :gutter="8">
            <a-col :span="8" v-for="item in zoneOptions" :key="item.value || 'default'">
              <div class="scene-btn tap-shrink" :class="{ active: form.zone_type === item.value }" @click="form.zone_type = item.value">
                <strong>{{ item.title }}</strong>
              </div>
            </a-col>
          </a-row>
          <div style="margin-top:6px;font-size:12px;color:var(--text-2)">简餐区固定先付款；正餐区固定桌台账单；不选则跟随店铺整体收款模式设置。</div>
        </a-form-item>
        <a-button type="primary" block size="large" :loading="saving" @click="onSubmit">
          {{ submitLabel }}
        </a-button>
      </a-form>
    </a-drawer>

    <TableStickerExportDialog
      v-model:open="showStickerDialog"
      :exportable="stickerExportable"
      :excluded="stickerExcluded"
      :loading="batchBusy === 'sticker'"
      @confirm="onConfirmStickerExport"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, QrcodeOutlined, FileImageOutlined, FireOutlined, WarningOutlined, InfoCircleOutlined, SortAscendingOutlined } from '@ant-design/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import TableStickerExportDialog from '../components/TableStickerExportDialog.vue'
import { classifyTableStickerCode, parseBlobErrorMessage, triggerBlobDownload } from '../utils/tableStickerExport'
import { batchDownloadEntranceCodes, createEntranceCode, deleteEntranceCode, exportTableStickers, getActivationStatus, getEntranceCodeSummary, getEntranceCodes, regenerateEntranceCode, updateEntranceCodeStatus } from '../api'

const route = useRoute()
const router = useRouter()
// Onboarding continuation (Activation Home Step 2). Only active via
// ?onboarding=1 -- normal /entrance-codes navigation is untouched.
const isOnboarding = computed(() => route.query.onboarding === '1')

const loading = ref(false)
const saving = ref(false)
const regenerating = ref(null)
const statusBusy = ref(null)
const deleteBusy = ref(null)
const batchBusy = ref('')
const showCreateDialog = ref(false)
const showStickerDialog = ref(false)
const codes = ref([])
const summary = ref({ code_count: 0, scan_count: 0, member_count: 0 })
const form = reactive({ name: '', channel: 'TABLE', table_no: '', zone_type: '' })
const createMode = ref('single') // 'single' | 'batch'
const batchForm = reactive({ prefix: 'A', start: 1, end: 12, pad: 2 })
const selectedIds = ref([])
const zoneOptions = [
  { title: '跟随店铺默认', value: '' },
  { title: '简餐区', value: 'quick' },
  { title: '正餐区', value: 'full' },
]
const zoneText = z => ({ quick: '简餐区', full: '正餐区' }[z] || '默认分区')
const channelFilter = ref('ALL')
const sortBy = ref('table') // 'table' | 'scan' | 'new'
const sortLabelMap = { table: '按桌号', scan: '扫码最多', new: '最新创建' }
const sortLabel = computed(() => sortLabelMap[sortBy.value])
const toggleSort = () => { sortBy.value = { table: 'scan', scan: 'new', new: 'table' }[sortBy.value] }

// 桌号自然排序：字母段不区分大小写按字典序，数字段按数值（A2 < A10）。
const tableSortKey = c => {
  const s = String(c.table_no || c.name || '').trim()
  const m = s.match(/^(\D*?)(\d*)(\D*)$/) || []
  return [(m[1] || '').toLowerCase(), m[2] === '' ? Number.POSITIVE_INFINITY : parseInt(m[2], 10), (m[3] || '').toLowerCase()]
}
const byTableNo = (a, b) => {
  const ka = tableSortKey(a); const kb = tableSortKey(b)
  if (ka[0] !== kb[0]) return ka[0] < kb[0] ? -1 : 1
  if (ka[1] !== kb[1]) return ka[1] - kb[1]
  return ka[2] < kb[2] ? -1 : ka[2] > kb[2] ? 1 : 0
}

const displayCodes = computed(() => {
  let list = channelFilter.value === 'ALL' ? codes.value : codes.value.filter(c => c.channel === channelFilter.value)
  list = [...list]
  if (sortBy.value === 'scan') list.sort((a, b) => (b.scan_count || 0) - (a.scan_count || 0))
  else if (sortBy.value === 'new') list.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
  else list.sort(byTableNo)
  return list
})

const codeTitle = code => {
  if (code.channel === 'TABLE') return code.table_no ? `${code.table_no} 桌` : '未设桌号'
  return code.name || '入口码'
}

const selectableIds = computed(() => displayCodes.value.map(c => c.id))
const allSelected = computed(() => selectableIds.value.length > 0 && selectableIds.value.every(id => selectedIds.value.includes(id)))
const someSelected = computed(() => selectedIds.value.length > 0 && !allSelected.value)
const trialCodes = computed(() => codes.value.filter(c => c.env_version !== 'release'))

const submitLabel = computed(() => {
  if (form.channel !== 'TABLE') return '生成入口码'
  return createMode.value === 'batch' ? `批量生成${batchCount.value ? ` ${batchCount.value} 张` : ''}` : '生成桌贴码'
})
const batchCount = computed(() => {
  const s = Number(batchForm.start); const e = Number(batchForm.end)
  if (!Number.isInteger(s) || !Number.isInteger(e) || e < s) return 0
  return e - s + 1
})
const batchTableNo = n => `${batchForm.prefix || ''}${String(n).padStart(Math.max(1, Number(batchForm.pad) || 1), '0')}`
const batchPreview = computed(() => {
  if (!batchCount.value) return '填写起止编号，例如 A 1 12 → A01 ~ A12'
  if (batchCount.value > 100) return '一次最多 100 张，请缩小范围'
  return `将生成 ${batchTableNo(batchForm.start)} ~ ${batchTableNo(batchForm.end)}，共 ${batchCount.value} 张`
})

const conversionTag = code => {
  const scan = code.scan_count || 0
  const reg = code.register_count || code.member_count || 0
  if (scan === 0) return null
  const rate = reg / scan
  if (rate >= 0.15) return { label: `高效 ${(rate * 100).toFixed(0)}%`, style: 'color:var(--brand);background:var(--brand-light);border-color:var(--brand-mid);font-size:11px' }
  return { label: `转化 ${(rate * 100).toFixed(0)}%`, style: 'color:var(--text-2);background:var(--bg-page);border-color:var(--border);font-size:11px' }
}

const overallConversionText = computed(() => {
  const scan = summary.value.scan_count || 0
  const member = summary.value.member_count || 0
  if (!scan) return '--'
  return `${((member / scan) * 100).toFixed(0)}%`
})

const scenes = [
  { title: '桌贴码', value: 'TABLE', icon: QrcodeOutlined, desc: '贴在桌上扫码点餐' },
  { title: '海报码', value: 'POSTER', icon: FileImageOutlined, desc: '打印海报，放门口' },
  { title: '抖音码', value: 'DOUYIN', icon: FireOutlined, desc: '放评论、私信' },
]

const channelMap = { TABLE: '桌贴码', POSTER: '海报码', DOUYIN: '抖音码', OTHER: '其它' }
const channelText = c => channelMap[c] || c || '入口码'

const pickScene = item => { form.channel = item.value; if (!form.name || form.name === '桌贴码' || form.name === '海报码' || form.name === '抖音码') form.name = item.title }

const resolveAssetUrl = url => {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return `${import.meta.env.VITE_API_ORIGIN || 'https://api.zhangbaiyang.com'}${url}`
}

const normalizeList = data => Array.isArray(data) ? data : (data?.items || data?.results || data?.data || [])

const loadData = async () => {
  loading.value = true
  try {
    const [summaryRes, codesRes] = await Promise.all([getEntranceCodeSummary(), getEntranceCodes({ page: 1, page_size: 100 })])
    if (summaryRes?.code === 200) summary.value = summaryRes.data || summary.value
    if (codesRes?.code === 200) codes.value = normalizeList(codesRes.data)
  } catch { message.error('入口码加载失败') }
  finally { loading.value = false }
}

const openCreate = () => {
  // Onboarding pre-fills a real table number: the actual scan-resolve
  // contract (entrance_codes.py) hard-rejects entry_type=table with a blank
  // table_no (422 TABLE_CONTEXT_MISSING) -- a blank default here would let a
  // new merchant "complete" Step 2 with a code that can never be scanned.
  // Normal /entrance-codes management keeps the original blank default.
  createMode.value = 'single'
  if (isOnboarding.value) {
    form.name = '1号桌'
    form.channel = 'TABLE'
    form.table_no = '1'
    form.zone_type = ''
  } else {
    form.name = '桌贴码'
    form.channel = 'TABLE'
    form.table_no = ''
    form.zone_type = ''
  }
  showCreateDialog.value = true
}

// Section 7/8: completion is decided by the real activation-status fact
// (has_entrance_codes), never by guessing from the locally-picked channel --
// this also sidesteps the entry_type-always-defaults-to-"table" backend
// quirk noted in the audit. Returns true if it navigated away.
async function checkOnboardingStep2() {
  if (!isOnboarding.value) return false
  try {
    const res = await getActivationStatus()
    if (res?.code === 200 && res?.data?.has_entrance_codes) {
      router.replace('/activation')
      return true
    }
  } catch {
    // stay on this page; onboarding continuation is best-effort only
  }
  return false
}

const onSubmit = async () => {
  if (form.channel === 'TABLE' && createMode.value === 'batch' && !isOnboarding.value) return onBatchCreate()
  if (!form.name) { message.error('请填写码名称'); return }
  // A TABLE code with a blank table_no can never be scanned (backend rejects
  // it at resolve time) -- require it in normal mode too, not just onboarding.
  if (form.channel === 'TABLE' && !String(form.table_no || '').trim()) {
    message.error('请填写桌号')
    return
  }
  saving.value = true
  try {
    const payload = { name: form.name, channel: form.channel }
    if (form.channel === 'TABLE' && form.table_no) payload.table_no = String(form.table_no).trim()
    if (form.channel === 'TABLE' && form.zone_type) payload.zone_type = form.zone_type
    const res = await createEntranceCode(payload)
    if (res?.code === 200) {
      message.success(isOnboarding.value ? '桌码已生成' : '已创建')
      showCreateDialog.value = false
      await loadData()
      if (isOnboarding.value) await checkOnboardingStep2()
      return
    }
    message.error(res?.msg || '创建失败')
  } catch { message.error('创建失败，请稍后再试') }
  finally { saving.value = false }
}

const onBatchCreate = async () => {
  const s = Number(batchForm.start); const e = Number(batchForm.end)
  if (!batchCount.value) { message.error('请检查起止编号'); return }
  if (batchCount.value > 100) { message.error('一次最多批量生成 100 张'); return }
  saving.value = true
  let ok = 0; const fails = []
  try {
    for (let n = s; n <= e; n++) {
      const table_no = batchTableNo(n)
      try {
        const payload = { name: table_no, channel: 'TABLE', table_no }
        if (form.zone_type) payload.zone_type = form.zone_type
        const res = await createEntranceCode(payload)
        if (res?.code === 200) ok++
        else fails.push(`${table_no}（${res?.msg || '失败'}）`)
      } catch { fails.push(`${table_no}（网络错误）`) }
    }
    if (ok) message.success(`已生成 ${ok} 张桌贴码`)
    if (fails.length) message.warning(`${fails.length} 张未生成：${fails.slice(0, 3).join('、')}${fails.length > 3 ? ' …' : ''}`)
    if (ok) { showCreateDialog.value = false; await loadData() }
  } finally { saving.value = false }
}

const downloadCode = code => { const url = resolveAssetUrl(code.image_url); if (!url) { message.warning('这张码还没有图片'); return } window.open(url, '_blank') }
const viewCode = downloadCode

const onRegenerate = async code => {
  regenerating.value = code.id
  try {
    const res = await regenerateEntranceCode(code.id)
    if (res?.code === 200) { message.success('已重新生成正式二维码'); await loadData() }
    else message.error(res?.msg || '重新生成失败')
  } catch { message.error('重新生成失败') }
  finally { regenerating.value = null }
}

const toggleSelect = id => {
  const i = selectedIds.value.indexOf(id)
  if (i >= 0) selectedIds.value.splice(i, 1)
  else selectedIds.value.push(id)
}
const toggleSelectAll = () => {
  selectedIds.value = allSelected.value ? [] : [...selectableIds.value]
}

const saveBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const onBatchDownload = async () => {
  if (!selectedIds.value.length) return
  batchBusy.value = 'download'
  try {
    const res = await batchDownloadEntranceCodes(selectedIds.value)
    const blob = res?.data
    if (!blob) { message.error('下载失败'); return }
    // 出错时后端返回的是 JSON（HTTP 200 + {code,msg}），此处会是一个 json blob
    if (blob.type && blob.type.includes('json')) {
      try { const j = JSON.parse(await blob.text()); message.error(j?.msg || '下载失败') } catch { message.error('下载失败') }
      return
    }
    let fname = '桌贴码.zip'
    const cd = res.headers?.['content-disposition'] || ''
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd)
    if (m) { try { fname = decodeURIComponent(m[1]) } catch { /* keep default */ } }
    saveBlob(blob, fname)
  } catch { message.error('下载失败') }
  finally { batchBusy.value = '' }
}

// ---- 印刷版桌贴导出（服务端渲染 PNG + PDF + ZIP）----
const selectedCodeObjects = computed(() => codes.value.filter(c => selectedIds.value.includes(c.id)))
const stickerExportable = computed(() => selectedCodeObjects.value.filter(c => classifyTableStickerCode(c).valid))
const stickerExcluded = computed(() => selectedCodeObjects.value
  .map(c => ({ code: c, verdict: classifyTableStickerCode(c) }))
  .filter(x => !x.verdict.valid)
  .map(x => ({
    name: x.code.table_no ? `${x.code.table_no} 桌` : (x.code.name || '入口码'),
    reason: x.verdict.reason,
  })))

const openStickerExport = () => {
  if (!selectedIds.value.length) return
  showStickerDialog.value = true
}

const asBlob = async (data) => {
  if (data instanceof Blob) return data
  if (data instanceof ArrayBuffer) return new Blob([data])
  if (data && typeof data === 'object' && typeof data.arrayBuffer !== 'function') {
    // axios 的自定义 transformResponse 偶发把 body 当字符串/对象透传
    return new Blob([typeof data === 'string' ? data : JSON.stringify(data)], { type: 'application/json' })
  }
  return data ?? null
}

const onConfirmStickerExport = async () => {
  const ids = stickerExportable.value.map(c => c.id)
  if (!ids.length) { message.warning('没有可导出的桌贴码'); return }
  batchBusy.value = 'sticker'
  try {
    const res = await exportTableStickers(ids)
    const blob = await asBlob(res?.data)
    if (!blob || typeof blob.size !== 'number') {
      console.error('[sticker-export] unexpected response', res)
      message.error('桌贴生成失败：响应异常')
      return
    }
    // 后端出错时是 HTTP 200 + 一小段 JSON（error_response 语义）；成功的 zip 至少几百 KB。
    if (blob.size < 50 * 1024) {
      const text = await blob.text().catch(() => '')
      let parsed = null
      try { parsed = JSON.parse(text) } catch { /* not json */ }
      console.error('[sticker-export] small response body', { size: blob.size, type: blob.type, text: text.slice(0, 500) })
      message.error((parsed && (parsed.msg || parsed.message)) || '桌贴生成失败，请稍后重试')
      return
    }
    let fname = '桌贴.zip'
    const cd = res.headers?.['content-disposition'] || res.headers?.get?.('content-disposition') || ''
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd) || /filename="?([^";]+)"?/i.exec(cd)
    if (m) { try { fname = decodeURIComponent(m[1]) } catch { /* keep default */ } }
    triggerBlobDownload(blob, fname)
    showStickerDialog.value = false
    message.success('桌贴已生成，开始下载')
  } catch (e) {
    console.error('[sticker-export] request failed', e)
    const status = e?.response?.status
    const body = e?.response?.data
    let msg = ''
    if (body && typeof body.text === 'function') msg = await parseBlobErrorMessage(body)
    if (!msg || msg === '桌贴生成失败，请稍后重试') {
      msg = status ? `桌贴生成失败（${status}），请稍后重试` : '桌贴生成失败，请检查网络后重试'
    }
    message.error(msg)
  } finally { batchBusy.value = '' }
}

const onToggleStatus = async code => {
  statusBusy.value = code.id
  try {
    const next = code.status === 1 ? 0 : 1
    const res = await updateEntranceCodeStatus(code.id, { status: next })
    if (res?.code === 200) { message.success(next ? '已启用' : '已停用'); await loadData() }
    else message.error(res?.msg || '操作失败')
  } catch { message.error('操作失败') }
  finally { statusBusy.value = null }
}

const onDelete = async code => {
  deleteBusy.value = code.id
  try {
    const res = await deleteEntranceCode(code.id)
    if (res?.code === 200) {
      message.success('已删除')
      selectedIds.value = selectedIds.value.filter(id => id !== code.id)
      await loadData()
    } else message.error(res?.msg || '删除失败')
  } catch (e) { message.error(e?.response?.data?.msg || '删除失败') }
  finally { deleteBusy.value = null }
}

const onBatchDisable = async () => {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  batchBusy.value = 'disable'
  let ok = 0
  try {
    for (const id of ids) {
      try { const r = await updateEntranceCodeStatus(id, { status: 0 }); if (r?.code === 200) ok++ } catch { /* skip */ }
    }
    message.success(`已停用 ${ok} 张`)
    await loadData()
  } finally { batchBusy.value = '' }
}

const onBatchDelete = async () => {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  batchBusy.value = 'delete'
  let ok = 0; const blocked = []
  try {
    for (const id of ids) {
      try {
        const r = await deleteEntranceCode(id)
        if (r?.code === 200) ok++
        else blocked.push(r?.msg || '')
      } catch (e) { blocked.push(e?.response?.data?.msg || '') }
    }
    if (ok) message.success(`已删除 ${ok} 张`)
    if (blocked.length) message.warning(`${blocked.length} 张未删除（多为已有扫码记录，请改用停用）`)
    selectedIds.value = []
    await loadData()
  } finally { batchBusy.value = '' }
}

const onConvertTrial = async () => {
  const list = [...trialCodes.value]
  if (!list.length) return
  batchBusy.value = 'convert'
  let ok = 0
  try {
    for (const c of list) {
      try { const r = await regenerateEntranceCode(c.id); if (r?.code === 200) ok++ } catch { /* skip */ }
    }
    message.success(`已转为正式码 ${ok} 张`)
    await loadData()
  } finally { batchBusy.value = '' }
}

onMounted(async () => {
  await loadData()
  if (isOnboarding.value) {
    const done = await checkOnboardingStep2()
    if (!done) openCreate()
  }
})
</script>

<style scoped lang="scss">
.onboarding-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: var(--brand-light);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  color: var(--brand);
}
.onboarding-back-link {
  border: none;
  background: transparent;
  color: var(--text-2);
  font-size: 12px;
  font-weight: 600;
  text-decoration: underline;
  flex-shrink: 0;
}

.scene-btn {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-page);
  padding: 14px 8px;
  text-align: center;
  cursor: pointer;
  transition: transform .15s, background .15s, border-color .15s;
  strong { display: block; font-style: normal; font-size: 13px; font-weight: 700; color: var(--text-1); }
  &.active { border-color: var(--brand); background: var(--brand-light); color: var(--brand); strong { color: var(--brand); } }
}

.bulk-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-page);
  font-size: 13px;
}
.bulk-actions { display: flex; gap: 6px; flex-wrap: wrap; }

.code-row {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
  &.is-disabled { opacity: .55; }
}
.code-check { align-self: center; flex-shrink: 0; }

.code-image {
  position: relative;
  width: 76px;
  height: 76px;
  border-radius: 10px;
  background: var(--bg-page);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  cursor: pointer;
  img { width: 100%; height: 100%; object-fit: contain; }
}
.code-image-tag {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 1px 0;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.3;
  text-align: center;
  color: #fff;
  background: rgba(0, 0, 0, .55);
}
</style>
