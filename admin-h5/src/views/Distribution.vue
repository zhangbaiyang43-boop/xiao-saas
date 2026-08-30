<template>
  <div class="distribution-page">
    <PageHeader title="会员分销" />

    <div class="page-content">
    <section class="hero-card animate-in">
      <div class="hero-badge"><span class="live-dot" v-if="settings.invite_reward_enabled"></span>{{ settings.invite_reward_enabled ? '自动运行中' : '已关闭' }}</div>
      <h1>让老顾客带新顾客到店</h1>
      <p class="hero-intro">好友扫码成为会员，首次到店核销后，系统按你选的强度自动给邀请人和新顾客发奖励，具体金额由算法按你的客单价实时计算，绝不会让你亏本。</p>

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

    <section v-if="showIntro" class="panel intro-card animate-in">
      <div class="intro-head">
        <strong>还没试过邀请奖励？</strong>
        <span class="intro-close tap-shrink" @click="dismissIntro">✕</span>
      </div>
      <p>老顾客带一位朋友到店消费，双方各得一张小额优惠券——门槛和金额已经按"保守"档配置好，成本可控，先开一周看看效果。</p>
      <div class="intro-actions">
        <van-button size="small" round type="primary" @click="focusToggle">现在开启</van-button>
        <span class="intro-dismiss tap-shrink" @click="dismissIntro">先不用了</span>
      </div>
    </section>

    <section ref="toggleSectionRef" class="panel animate-in" style="animation-delay:.04s">
      <div class="switch-row">
        <span>
          <strong>开启邀请奖励</strong>
          <em>只在好友完成第一次核销后发放，避免无效薅券。</em>
        </span>
        <van-switch v-model="settings.invite_reward_enabled" size="26" :loading="saving" @change="saveEnabled" />
      </div>
    </section>

    <section class="panel animate-in" style="animation-delay:.08s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">三档强度</p>
          <h2>消费后才奖励</h2>
          <span>金额、门槛、有效期都由算法按客单价自动匹配，不需要你操心具体数字，选一档就行。</span>
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
              <span>邀请人得</span>
              <strong>¥{{ o.inviter_reward_amount }}</strong>
            </div>
            <div>
              <span>新顾客得</span>
              <strong>¥{{ o.invitee_reward_amount }}</strong>
            </div>
          </div>
          <p class="tier-cond">满¥{{ o.invite_reward_min_spend }}可用 · {{ o.invite_reward_valid_days }}天内有效</p>
        </article>
      </div>
    </section>

    <section class="panel animate-in" style="animation-delay:.12s">
      <div class="panel-head">
        <div>
          <p class="eyebrow">邀请记录</p>
          <h2>谁带来了新顾客</h2>
          <span>记录会在被邀请人入会、到店、奖励发放后更新。</span>
        </div>
        <button class="text-btn tap-shrink" :disabled="loading" @click="loadRecords">刷新</button>
      </div>

      <div class="record-summary">
        <div>
          <strong>{{ total }}</strong>
          <span>邀请记录</span>
        </div>
        <div>
          <strong>{{ visitedCount }}</strong>
          <span>已到店</span>
        </div>
        <div>
          <strong>{{ pendingCount }}</strong>
          <span>待发放</span>
        </div>
      </div>

      <div v-if="loading" class="state-card">
        <van-loading size="24px">正在加载邀请记录</van-loading>
      </div>

      <div v-else-if="records.length === 0" class="state-card">
        <van-empty description="暂无邀请记录" />
      </div>

      <div v-else class="record-list">
        <article v-for="row in records" :key="row.record_id || row.invitee_id" class="record-card tap-shrink">
          <div class="record-top">
            <div>
              <strong>{{ row.invitee_name || '新顾客' }}</strong>
              <span>{{ maskPhone(row.invitee_phone) }}</span>
            </div>
            <van-tag :type="row.has_visited ? 'success' : 'default'" round>
              {{ row.has_visited ? '已到店' : '未到店' }}
            </van-tag>
          </div>

          <div class="relation-box">
            <div>
              <span>邀请人</span>
              <strong>{{ row.inviter_name || '-' }}</strong>
              <em>{{ maskPhone(row.inviter_phone) }}</em>
            </div>
            <div>
              <span>加入时间</span>
              <strong>{{ fmtDate(row.joined_at) || '-' }}</strong>
              <em>核销：{{ fmtDate(row.first_verify_at) || '-' }}</em>
            </div>
          </div>

          <div class="reward-row">
            <span :class="['reward-status', rewardClass(row.reward_status)]">
              {{ rewardText(row.reward_status) }}
            </span>
            <van-button
              v-if="row.reward_status === 'PENDING'"
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
import { formatBeijingDateTime } from '../utils/beijingTime'
import {
  getDistributionPreview,
  getDistributionRecords,
  getDistributionSettings,
  settleDistributionRecord,
  updateDistributionSettings,
  updateTenantSettings
} from '../api'

const settings = ref({ invite_reward_enabled: false })
const preview = ref({})   // /v1/distribution/preview 的三档强度结果
const records = ref([])
const total = ref(0)
const saving = ref(false)
const loading = ref(false)
const switchingIntensity = ref(false)
const toggleSectionRef = ref(null)

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
  return '选中的档位立即生效，下方是这一档实际会发放的金额'
})

// 一次性引导卡：商户没开过这功能时提醒它存在，开启后或手动关掉就不再出现——
// 按 tenant 维度记忆，避免同一浏览器登过多个商户号时互相影响。
const introDismissKey = computed(() => `distribution_intro_dismissed_${localStorage.getItem('tenant_id') || 'default'}`)
const introDismissed = ref(localStorage.getItem(introDismissKey.value) === '1')
const showIntro = computed(() => !settings.value.invite_reward_enabled && !introDismissed.value)
const dismissIntro = () => {
  introDismissed.value = true
  localStorage.setItem(introDismissKey.value, '1')
}
const focusToggle = () => {
  toggleSectionRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
}

// 强度切换：跟 CouponCenter.vue 调的是同一个"通用设置"接口，选中即生效，
// 这个强度只影响邀请奖励，不会牵动进店券/复购券/新客券那几个各自的强度。
const switchIntensity = async (key) => {
  if (switchingIntensity.value || key === currentIntensity.value) return
  switchingIntensity.value = true
  try {
    const res = await updateTenantSettings({ distribution_intensity: key })
    if (res.code !== 200) { showToast(res.msg || '切换失败'); return }
    await loadPreview()
    showToast('已切换')
  } catch (error) {
    showToast({ message: '切换失败，请稍后重试', icon: 'fail' })
  } finally {
    switchingIntensity.value = false
  }
}

const visitedCount = computed(() => records.value.filter((item) => item.has_visited).length)
const pendingCount = computed(() => records.value.filter((item) => item.reward_status === 'PENDING').length)

const fmtDate = (iso) => formatBeijingDateTime(iso) || String(iso || '').slice(0, 16).replace('T', ' ')

const maskPhone = (phone) => {
  if (!phone) return '-'
  return String(phone).replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')
}

const extractRows = (data) => {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.rows)) return data.rows
  if (Array.isArray(data?.results)) return data.results
  return []
}

const rewardText = (status) => {
  const map = {
    PENDING: '待发放',
    SETTLED: '已发放',
    PA: '已发放'
  }
  return map[status] || '未触发'
}

const rewardClass = (status) => {
  if (status === 'PENDING') return 'pending'
  if (status === 'SETTLED' || status === 'PA') return 'done'
  return 'none'
}

const loadSettings = async () => {
  try {
    const res = await getDistributionSettings()
    if (res.code === 200 && res.data) {
      settings.value = { ...settings.value, invite_reward_enabled: Boolean(res.data.invite_reward_enabled) }
    }
  } catch (error) {
    showToast({ message: '分销配置加载失败', icon: 'fail' })
  }
}

const loadPreview = async () => {
  try {
    const res = await getDistributionPreview()
    if (res.code === 200) preview.value = res.data || {}
  } catch (error) {
    // 加载失败不阻断页面，tierDesc 会退回默认文案
  }
}

// 商户现在只能改这一个开关，金额/门槛已经不接受手填
const saveEnabled = async () => {
  saving.value = true
  try {
    const res = await updateDistributionSettings({ invite_reward_enabled: settings.value.invite_reward_enabled })
    if (res.code === 200) {
      settings.value = { ...settings.value, invite_reward_enabled: Boolean(res.data?.invite_reward_enabled) }
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

const loadRecords = async (append = false) => {
  loading.value = !append
  try {
    const skip = append ? records.value.length : 0
    const res = await getDistributionRecords({ skip, limit: 50 })
    if (res.code === 200) {
      const rows = extractRows(res.data)
      records.value = append ? [...records.value, ...rows] : rows
      total.value = Number(res.data?.total ?? rows.length)
    }
  } catch (error) {
    showToast({ message: '邀请记录加载失败', icon: 'fail' })
  } finally {
    loading.value = false
  }
}

const loadMore = () => loadRecords(true)

const settle = async (row) => {
  if (!row.record_id) {
    showToast({ message: '缺少记录 ，无法标记', icon: 'fail' })
    return
  }
  try {
    const res = await settleDistributionRecord(row.record_id)
    if (res.code === 200) {
      showToast('已标记发放')
      row.reward_status = 'SETTLED'
      row.settled_at = res.data?.settled_at || new Date().toISOString()
      return
    }
    showToast(res.msg || '操作失败')
  } catch (error) {
    showToast({ message: '操作失败', icon: 'fail' })
  }
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadPreview(), loadRecords()])
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
.record-card {
  border-radius: 18px;
  background: var(--bg-card);
  box-shadow: var(--card-shadow);
}

/* 顶部强度卡：跟"今日"页同一个绿色渐变(--hero-bg)，同一套"选一档立即生效"的决策方式 */
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

.intro-card {
  border: 1px solid var(--brand);
  background: color-mix(in srgb, var(--brand) 8%, var(--bg-card));
}

.intro-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.intro-head strong {
  color: var(--text-1);
  font-size: 15px;
  font-weight: 900;
}

.intro-close {
  color: var(--text-3);
  font-size: 14px;
  padding: 4px;
}

.intro-card p {
  margin: 8px 0 0;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.5;
}

.intro-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
}

.intro-dismiss {
  color: var(--text-3);
  font-size: 13px;
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

.tier-cond {
  margin: 8px 0 0;
  color: var(--text-3);
  font-size: 11px;
  text-align: center;
  line-height: 1.4;
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
  font-size: 22px;
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
.record-top span,
.relation-box span,
.relation-box strong,
.relation-box em {
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

.relation-box {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.relation-box div {
  padding: 12px;
  border-radius: 14px;
  background: var(--bg-page);
}

.relation-box span {
  color: var(--text-2);
  font-size: 12px;
}

.relation-box strong {
  margin-top: 6px;
  overflow: hidden;
  color: var(--text-1);
  font-size: 15px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.relation-box em {
  margin-top: 4px;
  color: var(--text-3);
  font-size: 12px;
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
  font-size: 12px;
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

.reward-status.none {
  background: var(--bg-page);
  color: var(--text-2);
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
