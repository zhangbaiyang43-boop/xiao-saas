<template>
  <view class="page">

    <!-- 首次加载态：还没有任何数据时才整页占用 -->
    <view v-if="initialLoading" class="state-wrap">
      <state-loading text="正在加载邀请数据" />
    </view>

    <!-- 商户没开邀请奖励：可能是通过旧分享链接进来的，给个安静的提示，不展示一套
         看起来在正常运作、其实点了也没用的邀请流程。 -->
    <view v-else-if="rewardDisabled" class="state-wrap">
      <state-empty icon="🔔" title="该店暂未开启邀请奖励" desc="活动可能已下线，稍后再来看看。" />
    </view>

    <view v-else class="content">

      <!-- 顶部英雄卡：先出，跟好友列表的加载互不影响 -->
      <view class="hero-card">
        <text class="hc-title">邀请朋友到店，双方得奖励</text>
        <text class="hc-desc">{{ summary.inviter_reward_text || '邀请朋友到店用券，朋友首次到店后，你们都能获得奖励。' }}</text>

        <view v-if="summaryError" class="summary-error">
          <text class="summary-error-text">{{ summaryError }}</text>
          <text class="summary-retry-btn tap-shrink" @click="loadSummary">点击重试</text>
        </view>
        <view v-else class="stats-row">
          <view class="stat-item">
            <text class="stat-num">{{ summary.invited_count || 0 }}</text>
            <text class="stat-label">已邀请</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-num">{{ summary.visited_count || 0 }}</text>
            <text class="stat-label">已到店</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-num">{{ summary.reward_count || 0 }}</text>
            <text class="stat-label">已奖励</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-num">{{ summary.pending_count || 0 }}</text>
            <text class="stat-label">待到店</text>
          </view>
        </view>
      </view>

      <!-- 邀请方式卡：分享按钮是真正的转化入口——99% 的人会直接点它转发出去，
           邀请码本身没人会去手动念/输入，所以把视觉重点让给按钮，邀请码收成
           底部一条不起眼的备用说明。 -->
      <view class="card invite-card">
        <text class="card-title">邀请好友入会</text>
        <button class="btn-primary" open-type="share">邀请好友入会</button>
        <text class="card-tip">{{ summary.invitee_reward_text || '好友通过你的链接入会，首次到店核销后，双方均可获得奖励。' }}</text>
        <view class="code-box-mini">
          <text class="code-mini-label">链接打不开时，可以让朋友手动输入邀请码</text>
          <text class="code-mini-val">{{ summary.invite_code || '-' }}</text>
        </view>
      </view>

      <!-- 好友记录卡：独立的加载/错误态，不受英雄卡影响 -->
      <view class="card">
        <view class="card-header">
          <text class="card-title">好友记录</text>
          <text class="refresh-btn" @click="loadRecords">刷新</text>
        </view>

        <view v-if="recordsLoading" class="records-loading">
          <state-loading text="正在加载好友记录" size="small" />
        </view>

        <view v-else-if="recordsError" class="records-error">
          <state-error :title="recordsError" retry-text="重试" @retry="loadRecords" />
        </view>

        <view v-else-if="records.length === 0" class="empty-wrap">
          <state-empty icon="🎁" title="暂无好友记录" desc="好友通过你的邀请入会后会显示在这里。" />
        </view>

        <template v-else>
          <view v-for="item in records" :key="item.invitee_id" class="record-item">
            <view class="ri-left">
              <text class="ri-name">{{ item.invitee_name }}</text>
              <view class="ri-meta-row">
                <text class="ri-meta">加入：{{ item.joined_at || '-' }}</text>
                <text v-if="item.has_visited" class="ri-meta visited-text">到店：{{ item.visited_at || '-' }}</text>
              </view>
            </view>
            <view class="ri-right">
              <view :class="['status-badge', item.has_visited ? 'badge-visited' : 'badge-pending']">
                {{ item.has_visited ? '已到店' : '未到店' }}
              </view>
              <text :class="['ri-reward', item.reward_status === '奖励已发放' ? 'reward-done' : item.has_visited ? 'reward-pending' : 'reward-wait']">
                {{ item.reward_status }}
              </text>
            </view>
          </view>
        </template>

      </view>

    </view>
  </view>
</template>

<script>
import { computed, ref } from 'vue'
import { getInviteRecords, getInviteSummary } from '@/api/invite'
import StateLoading from '@/components/state-loading/state-loading.vue'
import StateError from '@/components/state-error/state-error.vue'
import StateEmpty from '@/components/state-empty/state-empty.vue'

export default {
  components: { StateLoading, StateError, StateEmpty },
  setup() {
    const initialLoading = ref(true)
    const summary = ref({})
    const summaryError = ref('')
    const records = ref([])
    const recordsLoading = ref(false)
    const recordsError = ref('')
    // 严格等于 false 才算"确认关闭"——summary 还没加载成功时是 undefined，
    // 不能把请求失败也误判成"该店没开这功能"，那种情况仍走原来的 summaryError 提示。
    const rewardDisabled = computed(() => summary.value?.invite_reward_enabled === false)

    const loadSummary = async () => {
      summaryError.value = ''
      try {
        const res = await getInviteSummary()
        if (res.code === 200) summary.value = res.data || {}
        else summaryError.value = res.msg || '加载失败'
      } catch (err) {
        summaryError.value = '网络异常'
      }
    }

    const loadRecords = async () => {
      recordsLoading.value = true
      recordsError.value = ''
      try {
        const res = await getInviteRecords()
        if (res.code === 200) records.value = Array.isArray(res.data) ? res.data : []
        else recordsError.value = res.msg || '加载失败'
      } catch (err) {
        recordsError.value = '网络异常'
      } finally {
        recordsLoading.value = false
      }
    }

    const loadData = async () => {
      await Promise.all([loadSummary(), loadRecords()])
      initialLoading.value = false
    }

    return {
      initialLoading, summary, summaryError, records, recordsLoading, recordsError,
      loadData, loadSummary, loadRecords, rewardDisabled
    }
  },
  onShow() {
    this.loadData()
  },
  onShareAppMessage() {
    const tenantId = this.summary.tenant_id || uni.getStorageSync('tenant_id') || ''
    const inviteCode = this.summary.invite_code || ''
    const storeName = uni.getStorageSync('tenant_name') || ''
    // 分享卡片才是真正的转化入口——对方不会先打开小程序看邀请页本身，只看聊天窗口里
    // 这张卡片。之前没指定 imageUrl，微信会拿当前页面自动截图当封面，截出来的是
    // "0 已邀请 0 已到店" 这种看起来像"没人用"的画面。这里换成专门做的静态封面图
    // （不含具体券面额——各商户客单价不同，面额是动态算的，写死数字会跟实际发的券
    // 对不上），标题带上店名，让对方一眼知道是"这家店在邀请我"而不是系统群发消息。
    return {
      title: storeName ? `${storeName}请你来吃饭，到店立减` : '我送你一张优惠券，到店可用',
      path: `/pages/entry/index?tenant_id=${encodeURIComponent(tenantId)}&invite_code=${encodeURIComponent(inviteCode)}`,
      imageUrl: '/static/share/invite-card.png',
    }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #F7F8FA;
}

/* ── 状态区 ──────────────────────────────── */
.state-wrap {
  margin: 120rpx 24rpx 0;
  padding: 64rpx 32rpx;
  background: var(--bg-card);
  border-radius: 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ── 内容区 ──────────────────────────────── */
.content {
  padding-bottom: 32rpx;
}

/* ── 英雄卡 ──────────────────────────────── */
.hero-card {
  padding: 48rpx 32rpx 40rpx;
  background: var(--brand);
}

.hc-title {
  display: block;
  color: var(--text-inverse);
  font-size: 40rpx;
  font-weight: bold;
  line-height: 1.35;
}

.hc-desc {
  display: block;
  margin-top: 12rpx;
  color: rgba(255, 255, 255, 0.88);
  font-size: 26rpx;
  line-height: 1.6;
}

.stats-row {
  display: flex;
  align-items: center;
  margin-top: 32rpx;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 24rpx;
  padding: 24rpx 0;
}

.stat-item {
  flex: 1;
  text-align: center;
}

.stat-num {
  display: block;
  color: var(--text-inverse);
  font-size: 36rpx;
  font-weight: bold;
  line-height: 1.2;
}

.stat-label {
  display: block;
  margin-top: 8rpx;
  color: rgba(255, 255, 255, 0.8);
  font-size: 24rpx;
}

.stat-divider {
  width: 2rpx;
  height: 56rpx;
  background: rgba(255, 255, 255, 0.3);
}

.summary-error {
  margin-top: 32rpx;
  padding: 24rpx 0;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 24rpx;
  text-align: center;
}

.summary-error-text {
  display: block;
  color: var(--text-inverse);
  font-size: 26rpx;
}

.summary-retry-btn {
  display: inline-block;
  margin-top: 12rpx;
  color: var(--text-inverse);
  font-size: 26rpx;
  font-weight: 600;
  text-decoration: underline;
}

/* ── 通用卡片 ─────────────────────────────── */
.card {
  margin: 24rpx 24rpx 0;
  padding: 32rpx;
  background: var(--bg-card);
  border-radius: 32rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
}

.card-title {
  display: block;
  color: #111;
  font-size: 32rpx;
  font-weight: 600;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24rpx;
}

.refresh-btn {
  color: var(--brand);
  font-size: 28rpx;
}

/* ── 邀请码区 ─────────────────────────────── */
.invite-card .card-title {
  margin-bottom: 24rpx;
}

.code-box-mini {
  margin-top: 20rpx;
  padding: 16rpx 20rpx;
  background: #F7F8FA;
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.code-mini-label {
  color: #B0B3BA;
  font-size: 20rpx;
  flex: 1;
  margin-right: 12rpx;
}

.code-mini-val {
  color: #999;
  font-size: 26rpx;
  font-weight: 600;
  letter-spacing: 2rpx;
}

/* ── 通用按钮 ─────────────────────────────── */
.btn-primary {
  display: block;
  width: 100%;
  height: 96rpx;
  line-height: 96rpx;
  background: var(--brand);
  color: var(--text-inverse);
  font-size: 34rpx;
  font-weight: 600;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}

.card-tip {
  display: block;
  margin-top: 16rpx;
  color: #999;
  font-size: 24rpx;
  line-height: 1.6;
}

/* ── 好友记录加载 / 错误态 ─────────────────── */
.records-loading {
  padding: 48rpx 0 16rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.records-error {
  padding: 40rpx 0 16rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ── 空态 ────────────────────────────────── */
.empty-wrap {
  padding: 48rpx 0 16rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ── 好友记录 ─────────────────────────────── */
.record-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 24rpx 0;
  border-bottom: 2rpx solid #F7F8FA;
}

.record-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.ri-left {
  flex: 1;
  min-width: 0;
}

.ri-name {
  display: block;
  color: #111;
  font-size: 30rpx;
  font-weight: 600;
}

.ri-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
  margin-top: 8rpx;
}

.ri-meta {
  color: #999;
  font-size: 24rpx;
}

.visited-text {
  color: var(--brand);
}

.ri-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
  margin-left: 16rpx;
  gap: 10rpx;
}

.status-badge {
  display: inline-block;
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
  font-size: 22rpx;
  font-weight: 600;
}

.badge-visited {
  background: #e8f9ef;
  color: var(--brand);
}

.badge-pending {
  background: #f5f5f5;
  color: #999;
}

.ri-reward {
  display: block;
  font-size: 24rpx;
}

.reward-done {
  color: var(--brand);
}

.reward-pending {
  color: #F5A623;
}

.reward-wait {
  color: #999;
}
</style>
