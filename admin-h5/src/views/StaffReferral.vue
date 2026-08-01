<template>
  <div class="distribution-page">
    <PageHeader title="员工推荐" />

    <div class="page-content">
    <section class="hero-card animate-in">
      <div class="hero-badge"><span class="live-dot" v-if="settings.enabled"></span>{{ settings.enabled ? '自动运行中' : '已关闭' }}</div>
      <h1>员工/亲友带客到店，自动记佣金</h1>
      <p class="hero-intro">员工或亲友把新顾客带到店里，顾客首次到店消费后，系统按你选的强度自动给推荐人记一笔待发放佣金——这笔是现金，不是优惠券，需要你线下实际打款后手动标记已发放。</p>

      <div class="intensity-switch">
        <div
          v-for="opt in intensityOptions"
          :key="opt.key"
          class="intensity-pill tap-shrink"
          :class="{ 'intensity-pill--on': opt.key === currentIntensity, 'intensity-pill--disabled': switchingIntensity }"
          @click="switchIntensity(opt.key)"
        >{{ opt.label }}</div>
      </div>

      <p class="hero-desc">{{ tierDesc }}</p>
    </section>

    <section ref="toggleSectionRef" class="panel animate-in" style="animation-delay:.04s">
      <div class="switch-row">
        <span>
          <strong>开启员工推荐</strong>
          <em>只在被推荐顾客完成第一次核销/消费后记账，不是持续按单抽成。</em>
        </span>
        <van-switch v-model="settings.enabled" size="26" :loading="saving" @change="saveEnabled" />
      </div>
    </section>

    <section class="panel animate-in" style="animation-delay:.08s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">三档强度</p>
          <h2>首单消费后才记佣金</h2>
          <span>金额由算法按客单价自动匹配，不需要你操心具体数字，选一档就行。</span>
        </div>
      </div>

      <div class="tier-list">
        <article
          v-for="o in tierOptions"
          :key="o.intensity"
          class="tier-card tap-shrink"
          :class="{ 'tier-card--on': o.is_current }"
          @click="switchIntensity(o.intensity)"
        >
          <div class="tier-card-head">
            <strong>{{ o.label }}</strong>
            <van-tag v-if="o.is_current" type="primary" round size="small">使用中</van-tag>
          </div>
          <div class="tier-amounts">
            <div>
              <span>推荐人得</span>
              <strong>¥{{ o.staff_commission_amount }}</strong>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="panel animate-in" style="animation-delay:.1s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">员工管理</p>
          <h2>给员工/亲友生成专属推荐码</h2>
          <span>员工不需要登录小程序，把推荐码转发给他，顾客注册时填这个码就能和这位员工关联上。</span>
        </div>
      </div>

      <div class="staff-add-row">
        <input v-model="newStaffName" class="staff-add-input" placeholder="员工姓名，例如：小王" maxlength="20" />
        <van-button size="small" type="primary" round :loading="creatingStaff" @click="addStaff">生成推荐码</van-button>
      </div>

      <div v-if="staffList.length === 0" class="state-card">
        <van-empty description="还没有员工，先在上面加一个" />
      </div>
      <div v-else class="staff-list">
        <article v-for="s in staffList" :key="s.id" class="staff-card">
          <div
            v-if="s.share_image_url"
            class="staff-share-image tap-shrink"
            role="button"
            aria-label="查看分享码"
            @click="downloadShareCode(s)"
          >
            <img :src="resolveAssetUrl(s.share_image_url)" alt="员工分享码" />
          </div>
          <div class="staff-card-main">
            <strong>{{ s.name }}</strong>
            <span class="staff-code" @click="copyCode(s.invite_code)">推荐码：{{ s.invite_code }}（点击复制）</span>
            <span v-if="s.share_image_url" class="staff-share-tip">下载这张码发给员工，员工扫码后点右上角"转发"即可邀请</span>
            <span v-else-if="s.share_generation_status === 'FAILED'" class="staff-share-error">
              分享码生成失败{{ s.share_generation_error ? '：' + s.share_generation_error : '' }}
              <a class="staff-share-retry" @click="regenerateShareCode(s)">重新生成</a>
            </span>
          </div>
          <van-switch
            :model-value="s.status === 1"
            size="22"
            @update:model-value="(val) => toggleStaffStatus(s, val)"
          />
        </article>
      </div>
    </section>

    <section class="panel animate-in" style="animation-delay:.14s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">待发放佣金</p>
          <h2>谁带来了新顾客</h2>
          <span>记录会在被推荐顾客首次到店核销后生成，金额由你线下打款给对应的人。</span>
        </div>
        <button class="text-btn tap-shrink" :disabled="loading" @click="loadRecords">刷新</button>
      </div>

      <div class="record-summary">
        <div>
          <strong>{{ total }}</strong>
          <span>推荐记录</span>
        </div>
        <div>
          <strong>{{ pendingCount }}</strong>
          <span>待发放</span>
        </div>
        <div>
          <strong>¥{{ pendingAmount }}</strong>
          <span>待发放金额</span>
        </div>
      </div>

      <div v-if="loading" class="state-card">
        <van-loading size="24px">正在加载推荐记录</van-loading>
      </div>

      <div v-else-if="records.length === 0" class="state-card">
        <van-empty description="暂无推荐记录" />
      </div>

      <div v-else class="record-list">
        <article v-for="row in records" :key="row.record_id" class="record-card tap-shrink">
          <div class="record-top">
            <div>
              <strong>{{ row.staff_name }}</strong>
              <span>带来顾客：{{ row.invitee_name }}</span>
            </div>
            <van-tag :type="row.status === 'SETTLED' ? 'success' : 'default'" round>
              {{ row.status === 'SETTLED' ? '已发放' : '待发放' }}
            </van-tag>
          </div>

          <div class="reward-row">
            <span class="reward-status" :class="row.status === 'SETTLED' ? 'done' : 'pending'">
              ¥{{ row.commission_amount }}
            </span>
            <van-button
              v-if="row.status !== 'SETTLED'"
              round
              plain
              type="primary"
              size="small"
              @click="settle(row)"
            >
              标记已发放
            </van-button>
          </div>
        </article>
      </div>

      <van-button
        v-if="total > records.length"
        block
        round
        plain
        type="primary"
        class="load-more tap-shrink"
        @click="loadMore"
      >
        加载更多（{{ records.length }} / {{ total }}）
      </van-button>
    </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  Button as VanButton,
  Empty as VanEmpty,
  Loading as VanLoading,
  Switch as VanSwitch,
  Tag as VanTag,
  showToast
} from 'vant'
import PageHeader from '../components/PageHeader.vue'
import {
  createStaff,
  getStaffList,
  getStaffReferralPreview,
  getStaffReferralRecords,
  getStaffReferralSettings,
  regenerateEntranceCode,
  settleStaffReferralRecord,
  updateStaffReferralSettings,
  updateStaffStatus,
  updateTenantSettings
} from '../api'

const settings = ref({ enabled: false })
const preview = ref({})
const records = ref([])
const total = ref(0)
const saving = ref(false)
const loading = ref(false)
const switchingIntensity = ref(false)
const toggleSectionRef = ref(null)
const staffList = ref([])
const newStaffName = ref('')
const creatingStaff = ref(false)

const intensityOptions = [
  { key: 'conservative', label: '保守' },
  { key: 'standard', label: '标准' },
  { key: 'aggressive', label: '激进' },
]

const currentIntensity = computed(() => preview.value?.current_intensity || 'standard')
const tierOptions = computed(() => preview.value?.outcomes || [])
const tierDesc = computed(() => {
  if (!preview.value?.outcomes) return '系统正在为你计算金额…'
  if (!preview.value.has_enough_data) return '数据积累中，当前用安全参数自动运行，满 5 单后为你精算'
  return '选中的档位立即生效，下方是这一档实际会记的佣金金额'
})

const switchIntensity = async (key) => {
  if (switchingIntensity.value || key === currentIntensity.value) return
  switchingIntensity.value = true
  try {
    const res = await updateTenantSettings({ staff_referral_intensity: key })
    if (res.code !== 200) { showToast(res.msg || '切换失败'); return }
    await loadPreview()
    showToast('已切换')
  } catch (error) {
    showToast({ message: '切换失败，请稍后重试', icon: 'fail' })
  } finally {
    switchingIntensity.value = false
  }
}

const pendingCount = computed(() => records.value.filter((item) => item.status !== 'SETTLED').length)
const pendingAmount = computed(() => records.value
  .filter((item) => item.status !== 'SETTLED')
  .reduce((sum, item) => sum + Number(item.commission_amount || 0), 0)
  .toFixed(1))

const extractRows = (data) => {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.rows)) return data.rows
  if (Array.isArray(data?.results)) return data.results
  return []
}

const loadSettings = async () => {
  try {
    const res = await getStaffReferralSettings()
    if (res.code === 200 && res.data) {
      settings.value = { ...settings.value, enabled: Boolean(res.data.enabled) }
    }
  } catch (error) {
    showToast({ message: '员工推荐配置加载失败', icon: 'fail' })
  }
}

const loadPreview = async () => {
  try {
    const res = await getStaffReferralPreview()
    if (res.code === 200) preview.value = res.data || {}
  } catch (error) {
    // 加载失败不阻断页面，tierDesc 会退回默认文案
  }
}

const saveEnabled = async () => {
  saving.value = true
  try {
    const res = await updateStaffReferralSettings({ enabled: settings.value.enabled })
    if (res.code === 200) {
      settings.value = { ...settings.value, enabled: Boolean(res.data?.enabled) }
      showToast('设置已保存')
      return
    }
    showToast(res.msg || '保存失败')
  } catch (error) {
    showToast({ message: '保存失败，请检查后端服务', icon: 'fail' })
  } finally {
    saving.value = false
  }
}

const loadStaffList = async () => {
  try {
    const res = await getStaffList()
    if (res.code === 200) staffList.value = extractRows(res.data)
  } catch (error) {
    showToast({ message: '员工列表加载失败', icon: 'fail' })
  }
}

const addStaff = async () => {
  const name = newStaffName.value.trim()
  if (!name) { showToast('请填写员工姓名'); return }
  creatingStaff.value = true
  try {
    const res = await createStaff({ name })
    if (res.code === 200) {
      showToast('已生成推荐码')
      newStaffName.value = ''
      await loadStaffList()
      return
    }
    showToast(res.msg || '创建失败')
  } catch (error) {
    showToast({ message: '创建失败，请稍后重试', icon: 'fail' })
  } finally {
    creatingStaff.value = false
  }
}

const toggleStaffStatus = async (staff, enabled) => {
  const nextStatus = enabled ? 1 : 0
  try {
    const res = await updateStaffStatus(staff.id, { status: nextStatus })
    if (res.code === 200) {
      staff.status = nextStatus
      return
    }
    showToast(res.msg || '操作失败')
  } catch (error) {
    showToast({ message: '操作失败', icon: 'fail' })
  }
}

const resolveAssetUrl = (url) => {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return `${import.meta.env.VITE_API_ORIGIN || 'https://api.zhangbaiyang.com'}${url}`
}

const downloadShareCode = (staff) => {
  const url = resolveAssetUrl(staff.share_image_url)
  if (!url) { showToast('这张码还没有图片'); return }
  window.open(url, '_blank')
}

const regenerateShareCode = async (staff) => {
  if (!staff.share_code_id) { showToast('缺少分享码记录，无法重新生成'); return }
  try {
    const res = await regenerateEntranceCode(staff.share_code_id)
    if (res.code === 200) {
      showToast('已重新生成')
      await loadStaffList()
      return
    }
    showToast(res.msg || '生成失败')
  } catch (error) {
    showToast({ message: '生成失败，请稍后重试', icon: 'fail' })
  }
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

const copyCode = async (code) => {
  if (!code) return
  try {
    await copyText(code)
    showToast('已复制推荐码')
  } catch (error) {
    showToast({ message: '复制失败，请手动复制', icon: 'fail' })
  }
}

const loadRecords = async (append = false) => {
  loading.value = !append
  try {
    const skip = append ? records.value.length : 0
    const res = await getStaffReferralRecords({ skip, limit: 50 })
    if (res.code === 200) {
      const rows = extractRows(res.data)
      records.value = append ? [...records.value, ...rows] : rows
      total.value = Number(res.data?.total ?? rows.length)
    }
  } catch (error) {
    showToast({ message: '推荐记录加载失败', icon: 'fail' })
  } finally {
    loading.value = false
  }
}

const loadMore = () => loadRecords(true)

const settle = async (row) => {
  if (!row.record_id) {
    showToast({ message: '缺少记录，无法标记', icon: 'fail' })
    return
  }
  try {
    const res = await settleStaffReferralRecord(row.record_id)
    if (res.code === 200) {
      showToast('已标记发放')
      row.status = 'SETTLED'
      row.settled_at = res.data?.settled_at || new Date().toISOString()
      return
    }
    showToast(res.msg || '操作失败')
  } catch (error) {
    showToast({ message: '操作失败', icon: 'fail' })
  }
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadPreview(), loadRecords(), loadStaffList()])
})
</script>

<style scoped>
.distribution-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding-bottom: calc(96px + env(safe-area-inset-bottom));
  background: var(--bg-page);
  color: var(--text-1);
}

.page-content {
  padding: 14px 14px 0;
}

.panel,
.state-card,
.record-card,
.staff-card {
  border-radius: 18px;
  background: var(--bg-card);
  box-shadow: var(--card-shadow);
}

.hero-card {
  padding: 20px;
  border-radius: 18px;
  background: var(--hero-bg);
  color: #fff;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, .2);
  font-size: 12px;
  font-weight: 700;
}

.hero-card h1 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 900;
  letter-spacing: 0;
}

.hero-intro {
  margin: 0 0 16px;
  color: rgba(255, 255, 255, .88);
  font-size: 13px;
  line-height: 1.5;
}

.intensity-switch {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.intensity-pill {
  flex: 1;
  text-align: center;
  padding: 9px 0;
  border-radius: 10px;
  background: rgba(255, 255, 255, .16);
  color: rgba(255, 255, 255, .85);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s, color .15s;
}

.intensity-pill--on {
  background: #fff;
  color: #06a550;
}

.intensity-pill--disabled {
  opacity: .6;
  pointer-events: none;
}

.hero-desc {
  margin: 0;
  color: rgba(255, 255, 255, .9);
  font-size: 13px;
  line-height: 1.5;
}

.eyebrow {
  margin: 0 0 5px;
  color: var(--brand);
  font-size: 12px;
  font-weight: 900;
}

.panel-head h2 {
  margin: 0;
  color: var(--text-1);
  font-weight: 900;
  letter-spacing: 0;
  font-size: 20px;
}

.panel-head span {
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

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.switch-row strong,
.switch-row em {
  display: block;
  font-style: normal;
}

.switch-row strong {
  color: var(--text-1);
  font-size: 17px;
  font-weight: 900;
}

.switch-row em {
  margin-top: 5px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.45;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.text-btn {
  border: 0;
  background: transparent;
  color: var(--brand);
  font-weight: 900;
}

.tier-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.tier-card {
  padding: 12px 10px;
  border: 1.5px solid var(--border);
  border-radius: 16px;
  background: var(--bg-page);
  cursor: pointer;
}

.tier-card--on {
  border-color: var(--brand);
  background: var(--brand-light);
}

.tier-card-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-bottom: 8px;
}

.tier-card-head strong {
  font-size: 15px;
  font-weight: 900;
  color: var(--text-1);
}

.tier-amounts {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tier-amounts div {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.tier-amounts span {
  font-size: 11px;
  color: var(--text-2);
}

.tier-amounts strong {
  font-size: 17px;
  font-weight: 900;
  color: var(--text-1);
}

.staff-add-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.staff-add-input {
  flex: 1;
  min-width: 0;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-page);
  color: var(--text-1);
  font-size: 14px;
}

.staff-list {
  display: grid;
  gap: 8px;
}

.staff-card {
  padding: 12px;
  border: 1px solid var(--border);
  box-shadow: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.staff-card-main {
  flex: 1;
  min-width: 0;
}

.staff-card-main strong {
  display: block;
  font-size: 15px;
  font-weight: 900;
  color: var(--text-1);
}

.staff-code {
  display: block;
  margin-top: 4px;
  color: var(--brand);
  font-size: 12px;
  cursor: pointer;
}

.staff-share-image {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 10px;
  background: var(--bg-page);
  overflow: hidden;
  cursor: pointer;
}

.staff-share-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.staff-share-tip {
  display: block;
  margin-top: 4px;
  color: var(--text-3);
  font-size: 11px;
  line-height: 1.4;
}

.staff-share-error {
  display: block;
  margin-top: 4px;
  color: var(--danger);
  font-size: 11px;
  line-height: 1.4;
}

.staff-share-retry {
  color: var(--brand);
  font-weight: 700;
  margin-left: 4px;
  cursor: pointer;
}

.record-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.record-summary div {
  min-height: 68px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  background: var(--bg-page);
  text-align: center;
}

.record-summary strong,
.record-summary span {
  display: block;
}

.record-summary strong {
  font-size: 20px;
  font-weight: 900;
  color: var(--text-1);
}

.record-summary span {
  margin-top: 3px;
  color: var(--text-2);
  font-size: 12px;
}

.state-card {
  padding: 32px 12px;
  text-align: center;
  box-shadow: none;
}

.record-list {
  display: grid;
  gap: 10px;
}

.record-card {
  padding: 15px;
  border: 1px solid var(--border);
  box-shadow: none;
}

.record-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.record-top strong,
.record-top span {
  display: block;
  font-style: normal;
}

.record-top strong {
  font-size: 17px;
  font-weight: 900;
  color: var(--text-1);
}

.record-top span {
  margin-top: 4px;
  color: var(--text-2);
  font-size: 13px;
}

.reward-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-top: 12px;
}

.reward-status {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 900;
}

.reward-status.pending {
  background: rgba(245, 158, 11, .14);
  color: var(--warning);
}

.reward-status.done {
  background: var(--brand-light);
  color: var(--success);
}

.load-more {
  margin-top: 12px;
}

@media (min-width: 768px) {
  .distribution-page {
    max-width: 760px;
    margin: 0 auto;
  }
}
</style>
