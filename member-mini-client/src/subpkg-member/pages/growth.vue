<template>
  <view class="page">
    <view v-if="loading" class="state-wrap">
      <state-loading text="正在加载会员成长信息" />
    </view>

    <view v-else-if="error" class="state-wrap">
      <state-error :title="error" retry-text="刷新重试" @retry="load" />
    </view>

    <view v-else>
      <view class="level-card" :style="levelCardStyle">
        <view class="level-head">
          <view class="level-head-main">
            <image v-if="levelBadgeSrc" class="level-badge" :src="levelBadgeSrc" mode="aspectFit" />
            <text class="level-name">{{ data.level_name }}</text>
          </view>
          <text v-if="nextLevel" class="level-rule-btn tap-shrink" @click="showRules">等级规则</text>
        </view>

        <view class="progress-row">
          <text class="progress-label">{{ progressLabel }}</text>
        </view>
        <view class="progress-track">
          <view class="progress-fill" :style="{ width: progressPercent + '%' }"></view>
        </view>
        <text class="progress-desc">{{ progressDesc }}</text>
      </view>

      <view class="points-card tap-shrink" @click="goPoints">
        <view class="points-main">
          <text class="points-label">我的积分</text>
          <text class="points-value">{{ data.points_balance }}</text>
        </view>
        <text class="card-arrow">›</text>
      </view>

      <view class="benefits-card">
        <view class="benefits-title-row">
          <text class="iconfont icon-quanyix benefits-title-icon"></text>
          <text class="benefits-title">{{ data.level_name }}会员可享{{ benefits.length }}项权益</text>
        </view>
        <view class="benefits-grid">
          <view v-for="b in benefits" :key="b.id" class="benefit-item" :class="{ locked: !b.unlocked }">
            <view class="benefit-icon">
              <text class="iconfont benefit-icon-glyph" :class="benefitIconClass(b)"></text>
              <text v-if="!b.unlocked" class="benefit-lock-badge">🔒</text>
            </view>
            <text class="benefit-name">{{ b.name }}</text>
            <text class="benefit-desc">{{ b.condition || (b.unlocked ? '已解锁' : '升级解锁') }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { getMembershipGrowth } from '@/api/auth'
import StateLoading from '@/components/state-loading/state-loading.vue'
import StateError from '@/components/state-error/state-error.vue'

export default {
  components: { StateLoading, StateError },
  setup() {
    const loading = ref(false)
    const error = ref('')
    const data = ref({ level_name: '普通会员', points_balance: 0, yearly_consumption: 0, levels: [], next_level: null, benefits: [] })

    const nextLevel = computed(() => data.value.next_level)
    const benefits = computed(() => data.value.benefits || [])

    const LEVEL_BADGES = { LV1: '/static/member-levels/level-lv1.webp', LV2: '/static/member-levels/level-lv2.webp', LV3: '/static/member-levels/level-lv3.webp' }
    const levelBadgeSrc = computed(() => LEVEL_BADGES[data.value.level_code] || LEVEL_BADGES.LV1)

    // 三张底图本身偏浅色(尤其银色几乎纯白)，直接铺上去白色文字会看不清，
    // 所以叠一层跟等级色调匹配的半透明渐变，既保留背景图的光泽纹理，又保证
    // 白色文字在任何一张图上都读得清楚。
    const LEVEL_CARD_META = {
      LV1: { bg: '/static/member-levels/card-bg-lv1.jpg', tint: '6,163,94' },
      LV2: { bg: '/static/member-levels/card-bg-lv2.jpg', tint: '100,112,128' },
      LV3: { bg: '/static/member-levels/card-bg-lv3.jpg', tint: '176,130,32' },
    }
    const levelCardStyle = computed(() => {
      const meta = LEVEL_CARD_META[data.value.level_code] || LEVEL_CARD_META.LV1
      return `background-image: linear-gradient(135deg, rgba(${meta.tint},0.68), rgba(${meta.tint},0.42)), url('${meta.bg}'); background-size: cover; background-position: center;`
    })

    const progressPercent = computed(() => {
      if (!nextLevel.value) return 100
      const target = Number(nextLevel.value.threshold || 0)
      if (target <= 0) return 100
      const current = Number(data.value.yearly_consumption || 0)
      return Math.max(0, Math.min(100, (current / target) * 100))
    })

    const progressLabel = computed(() => {
      const current = Number(data.value.yearly_consumption || 0).toFixed(0)
      if (!nextLevel.value) return `年度消费 ¥${current}`
      return `年度消费 ¥${current} / ¥${Number(nextLevel.value.threshold).toFixed(0)}`
    })

    const progressDesc = computed(() => {
      if (!nextLevel.value) return '已是最高等级，尽享全部专属权益'
      const remain = Math.max(0, Number(nextLevel.value.threshold) - Number(data.value.yearly_consumption || 0))
      return `再消费¥${remain.toFixed(0)}即可升级为「${nextLevel.value.name}」，解锁更多权益`
    })

    const load = async () => {
      loading.value = true
      error.value = ''
      try {
        const res = await getMembershipGrowth()
        if (res.code === 200) {
          data.value = res.data || data.value
        } else {
          error.value = res.msg || '加载失败'
        }
      } catch (e) {
        error.value = e.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    const showRules = () => {
      const levels = data.value.levels || []
      const content = levels.map((l) => `${l.name}：年度消费满¥${l.threshold}`).join('\n') || '暂无等级规则'
      uni.showModal({ title: '等级规则', content, showCancel: false, confirmText: '知道了' })
    }

    const goPoints = () => uni.navigateTo({ url: '/subpkg-member/pages/points' })

    // 权益类型跟 iconfont 图标的对应关系——积分加速目前 iconfont 里没有贴切的
    // 图标(倍速/闪电类)，先用"折扣"顶替，等找到合适的图标再换。
    const benefitIconClass = (b) => {
      const name = b.name || ''
      const type = b.type || ''
      if (name.includes('生日') || type === 'gift') return 'icon-shengrix'
      if (type === 'coupon') return 'icon-youhuiquan'
      if (type === 'points_multiplier') return 'icon-zhekou'
      return 'icon-quanyix'
    }

    return { loading, error, data, nextLevel, benefits, levelBadgeSrc, levelCardStyle, progressPercent, progressLabel, progressDesc, load, showRules, goPoints, benefitIconClass }
  },
  onShow() { this.load() }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #f5f7fb;
  padding-bottom: 40rpx;
}

.state-wrap {
  padding: 160rpx 40rpx;
  text-align: center;
}

.level-card {
  margin: 24rpx 28rpx 0;
  padding: 36rpx 32rpx;
  background: var(--brand-gradient);
  border-radius: 24rpx;
  color: #fff;
}

.level-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.level-head-main {
  display: flex;
  align-items: center;
  gap: 16rpx;
  min-width: 0;
}

.level-badge {
  width: 72rpx;
  height: 72rpx;
  flex-shrink: 0;
}

.level-name {
  font-size: 40rpx;
  font-weight: 800;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.level-rule-btn {
  padding: 8rpx 20rpx;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 999rpx;
  font-size: 24rpx;
}

.progress-row {
  margin-top: 28rpx;
}

.progress-label {
  font-size: 26rpx;
  color: rgba(255, 255, 255, 0.9);
}

.progress-track {
  margin-top: 16rpx;
  height: 12rpx;
  background: rgba(255, 255, 255, 0.25);
  border-radius: 999rpx;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #fff;
  border-radius: 999rpx;
  transition: width 0.3s;
}

.progress-desc {
  display: block;
  margin-top: 16rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.85);
}

.points-card {
  margin: 20rpx 28rpx 0;
  padding: 28rpx 32rpx;
  background: #fff;
  border-radius: 20rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.points-main {
  display: flex;
  align-items: center;
  gap: 16rpx;
}

.points-label {
  font-size: 28rpx;
  color: #111827;
  font-weight: 600;
}

.points-value {
  font-size: 30rpx;
  color: #07C160;
  font-weight: 800;
}

.card-arrow {
  color: #9ca3af;
  font-size: 40rpx;
}

.benefits-card {
  margin: 20rpx 28rpx 0;
  padding: 28rpx 32rpx;
  background: #fff;
  border-radius: 20rpx;
}

.benefits-title-row {
  display: flex;
  align-items: center;
  gap: 10rpx;
  margin-bottom: 24rpx;
}

.benefits-title-icon {
  color: #07C160;
  font-size: 32rpx;
}

.benefits-title {
  font-size: 30rpx;
  font-weight: 700;
  color: #111827;
}

.benefits-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 24rpx;
}

.benefit-item {
  width: calc((100% - 48rpx) / 3);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.benefit-icon {
  position: relative;
  width: 88rpx;
  height: 88rpx;
  border-radius: 20rpx;
  background: #e8f9ef;
  display: flex;
  align-items: center;
  justify-content: center;
}

.benefit-icon-glyph {
  color: #07C160;
  font-size: 40rpx;
}

.benefit-lock-badge {
  position: absolute;
  right: -6rpx;
  bottom: -6rpx;
  font-size: 24rpx;
  line-height: 1;
}

.benefit-item.locked .benefit-icon {
  background: #f0f1f3;
}

.benefit-item.locked .benefit-icon-glyph {
  color: #b0b4bb;
}

.benefit-item.locked .benefit-name,
.benefit-item.locked .benefit-desc {
  color: #9ca3af;
}

.benefit-name {
  display: block;
  margin-top: 12rpx;
  font-size: 26rpx;
  color: #111827;
  font-weight: 600;
}

.benefit-desc {
  display: block;
  margin-top: 4rpx;
  font-size: 22rpx;
  color: #9ca3af;
}
</style>
