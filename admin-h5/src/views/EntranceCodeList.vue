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
            <SortAscendingOutlined />{{ sortBy === 'scan' ? '扫码最多' : '最新创建' }}
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
          <div v-for="code in displayCodes" :key="code.id" class="code-row">
            <div class="code-image tap-shrink" role="button" :aria-label="`查看${code.name || '入口码'}`" @click="downloadCode(code)">
              <img
                v-if="code.image_url"
                :src="resolveAssetUrl(code.image_url)"
                :alt="code.name"
                @error="e => { e.target.style.display='none'; e.target.nextElementSibling.style.display='flex' }"
              />
              <QrcodeOutlined style="font-size:32px;color:var(--text-3)" :style="code.image_url ? 'display:none' : 'display:flex'" />
            </div>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap">
                <span style="font-size:15px;font-weight:700;color:var(--text-1)">{{ code.name || '入口码' }}</span>
                <a-tag style="color:var(--brand);background:var(--brand-light);border-color:var(--brand-mid);font-size:11px">{{ channelText(code.channel) }}</a-tag>
                <a-tag v-if="code.channel === 'TABLE'" style="font-size:11px">{{ zoneText(code.zone_type) }}</a-tag>
                <a-tag v-if="conversionTag(code)" :style="conversionTag(code).style">{{ conversionTag(code).label }}</a-tag>
              </div>
              <div style="font-size:13px;color:var(--text-2)">
                扫码 <b style="color:var(--text-1)">{{ code.scan_count || 0 }}</b> 次 · 入会 <b style="color:var(--text-1)">{{ code.register_count || code.member_count || 0 }}</b> 人
              </div>
              <div v-if="(code.scan_count || 0) === 0" style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--danger);margin-top:4px"><WarningOutlined />还没人扫码，检查是否已张贴</div>
              <div v-if="code.env_version !== 'release'" style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--warning);margin-top:4px"><WarningOutlined />体验码，需重新生成</div>
              <div v-if="code.generation_error" style="font-size:12px;color:var(--danger);margin-top:4px">{{ code.generation_error }}</div>
              <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
                <a-button size="small" @click="viewCode(code)">查看</a-button>
                <a-button size="small" :loading="regenerating === code.id" @click="onRegenerate(code)">重新生成</a-button>
                <a-button size="small" type="primary" @click="downloadCode(code)">下载</a-button>
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:6px;padding:12px 16px;font-size:12px;color:var(--brand);background:var(--brand-light);margin:0;border-radius:0 0 12px 12px">
            <InfoCircleOutlined style="margin-top:1px;flex-shrink:0" />
            <span style="color:var(--text-2)">下载图片后，发到微信找附近打印店打印，剪开贴桌上即可。</span>
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
        <a-form-item v-if="form.channel === 'TABLE'" label="桌号">
          <a-input v-model:value="form.table_no" placeholder="例如：A01（顾客点餐用）" allow-clear />
        </a-form-item>
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
          {{ form.channel === 'TABLE' ? '生成桌贴码' : '生成入口码' }}
        </a-button>
      </a-form>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, QrcodeOutlined, FileImageOutlined, FireOutlined, WarningOutlined, InfoCircleOutlined, SortAscendingOutlined } from '@ant-design/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { createEntranceCode, getActivationStatus, getEntranceCodeSummary, getEntranceCodes, regenerateEntranceCode } from '../api'

const route = useRoute()
const router = useRouter()
// Onboarding continuation (Activation Home Step 2). Only active via
// ?onboarding=1 -- normal /entrance-codes navigation is untouched.
const isOnboarding = computed(() => route.query.onboarding === '1')

const loading = ref(false)
const saving = ref(false)
const regenerating = ref(null)
const showCreateDialog = ref(false)
const codes = ref([])
const summary = ref({ code_count: 0, scan_count: 0, member_count: 0 })
const form = reactive({ name: '', channel: 'TABLE', table_no: '', zone_type: '' })
const zoneOptions = [
  { title: '跟随店铺默认', value: '' },
  { title: '简餐区', value: 'quick' },
  { title: '正餐区', value: 'full' },
]
const zoneText = z => ({ quick: '简餐区', full: '正餐区' }[z] || '默认分区')
const channelFilter = ref('ALL')
const sortBy = ref('scan') // 'scan' | 'new'

const toggleSort = () => { sortBy.value = sortBy.value === 'scan' ? 'new' : 'scan' }

const displayCodes = computed(() => {
  let list = channelFilter.value === 'ALL' ? codes.value : codes.value.filter(c => c.channel === channelFilter.value)
  list = [...list]
  if (sortBy.value === 'scan') list.sort((a, b) => (b.scan_count || 0) - (a.scan_count || 0))
  else list.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
  return list
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
  if (!form.name) { message.error('请填写码名称'); return }
  // Even with the onboarding pre-fill above, guard the actual submission --
  // a user could still clear the field. A TABLE code with a blank table_no
  // can never be scanned (backend hard-rejects it at resolve time), so it
  // must never be allowed to reach "created" in onboarding mode.
  if (isOnboarding.value && form.channel === 'TABLE' && !String(form.table_no || '').trim()) {
    message.error('请填写桌号')
    return
  }
  saving.value = true
  try {
    const payload = { name: form.name, channel: form.channel }
    if (form.channel === 'TABLE' && form.table_no) payload.table_no = form.table_no
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

.code-row {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}

.code-image {
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
</style>
