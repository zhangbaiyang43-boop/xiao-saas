<template>
  <div class="distribution-page">
    <section class="hero-card">
      <div>
        <p class="eyebrow">会员分销</p>
        <h1>让老顾客带新顾客到店</h1>
        <p>好友扫码成为会员，首次到店核销后，再给邀请人和新顾客发奖励。</p>
      </div>
      <van-tag :type="settings.invite_reward_enabled ? 'success' : 'default'" round>
        {{ settings.invite_reward_enabled ? '已开启' : '已关闭' }}
      </van-tag>
    </section>

    <section class="panel">
      <div class="switch-row">
        <span>
          <strong>开启邀请奖励</strong>
          <em>只在好友完成第一次核销后发放，避免无效薅券。</em>
        </span>
        <van-switch v-model="settings.invite_reward_enabled" size="26" :loading="saving" @change="saveSettings" />
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">奖励设置</p>
          <h2>消费后才奖励</h2>
          <span>建议县城单店先用小额奖励，一级 1-3 元，二级后续再放开。</span>
        </div>
      </div>

      <div class="settings-grid">
        <label class="input-card">
          <span>邀请人奖励</span>
          <div>
            <em>￥</em>
            <input v-model.number="settings.inviter_reward_amount" type="number" min="0" step="0.5" />
          </div>
        </label>
        <label class="input-card">
          <span>新顾客奖励</span>
          <div>
            <em>￥</em>
            <input v-model.number="settings.invitee_reward_amount" type="number" min="0" step="0.5" />
          </div>
        </label>
        <label class="input-card">
          <span>最低消费</span>
          <div>
            <em>￥</em>
            <input v-model.number="settings.invite_reward_min_spend" type="number" min="0" step="1" />
          </div>
        </label>
        <label class="input-card">
          <span>有效期</span>
          <div>
            <input v-model.number="settings.invite_reward_valid_days" type="number" min="1" step="1" />
            <em>天</em>
          </div>
        </label>
      </div>

      <van-button block round type="primary" :loading="saving" @click="saveSettings">保存奖励设置</van-button>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">邀请记录</p>
          <h2>谁带来了新顾客</h2>
          <span>记录会在被邀请人入会、到店、奖励发放后更新。</span>
        </div>
        <button class="text-btn" :disabled="loading" @click="loadRecords">刷新</button>
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
        <article v-for="row in records" :key="row.record_id || row.invitee_id" class="record-card">
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
        class="load-more"
        @click="loadMore"
      >
        加载更多（{{ records.length }} / {{ total }}）
      </van-button>
    </section>
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
import {
  getDistributionRecords,
  getDistributionSettings,
  settleDistributionRecord,
  updateDistributionSettings
} from '../api'

const settings = ref({
  invite_reward_enabled: false,
  inviter_reward_amount: 2,
  invitee_reward_amount: 2,
  invite_reward_min_spend: 0,
  invite_reward_valid_days: 30
})
const records = ref([])
const total = ref(0)
const saving = ref(false)
const loading = ref(false)

const visitedCount = computed(() => records.value.filter((item) => item.has_visited).length)
const pendingCount = computed(() => records.value.filter((item) => item.reward_status === 'PENDING').length)

const fmtDate = (iso) => {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return String(iso).slice(0, 16).replace('T', ' ')
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

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
      settings.value = { ...settings.value, ...res.data }
    }
  } catch (error) {
    showToast({ message: '分销配置加载失败', icon: 'fail' })
  }
}

const saveSettings = async () => {
  saving.value = true
  try {
    const res = await updateDistributionSettings(settings.value)
    if (res.code === 200) {
      settings.value = { ...settings.value, ...res.data }
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
  await Promise.all([loadSettings(), loadRecords()])
})
</script>

<style scoped>
.distribution-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 14px 14px 96px;
  background: #f5f6f8;
  color: #111827;
}

.hero-card,
.panel,
.state-card,
.record-card {
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
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
  color: #1677ff;
  font-size: 12px;
  font-weight: 900;
}

.hero-card h1,
.panel-head h2 {
  margin: 0;
  color: #111827;
  font-weight: 900;
  letter-spacing: 0;
}

.hero-card h1 {
  font-size: 22px;
}

.hero-card p:not(.eyebrow),
.panel-head span {
  display: block;
  margin: 6px 0 0;
  color: #64748b;
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
  color: #111827;
  font-size: 17px;
  font-weight: 900;
}

.switch-row em {
  margin-top: 5px;
  color: #64748b;
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

.panel-head h2 {
  font-size: 20px;
}

.text-btn {
  border: 0;
  background: transparent;
  color: #1677ff;
  font-weight: 900;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.input-card {
  padding: 12px;
  border: 1px solid #edf1f7;
  border-radius: 16px;
  background: #f8fafc;
}

.input-card span {
  display: block;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.input-card div {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.input-card em {
  color: #1677ff;
  font-style: normal;
  font-weight: 900;
}

.input-card input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: #111827;
  font-size: 20px;
  font-weight: 900;
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
  background: #f8fafc;
  text-align: center;
}

.record-summary strong,
.record-summary span {
  display: block;
}

.record-summary strong {
  font-size: 22px;
  font-weight: 900;
}

.record-summary span {
  margin-top: 3px;
  color: #64748b;
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
  border: 1px solid #edf1f7;
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
}

.record-top span {
  margin-top: 4px;
  color: #64748b;
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
  background: #f8fafc;
}

.relation-box span {
  color: #64748b;
  font-size: 12px;
}

.relation-box strong {
  margin-top: 6px;
  overflow: hidden;
  color: #111827;
  font-size: 15px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.relation-box em {
  margin-top: 4px;
  color: #94a3b8;
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
  background: #fff7ed;
  color: #c2410c;
}

.reward-status.done {
  background: #ecfdf5;
  color: #059669;
}

.reward-status.none {
  background: #f1f5f9;
  color: #64748b;
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
