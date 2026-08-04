<template>
  <view v-if="visible">
    <!-- movable-area 必须有明确的像素高/宽，拖动组件靠这个容器的具体尺寸算"能拖多远"——
    写成 CSS 百分比或 top+bottom 撑开那种模糊写法量不出范围，会拖不动（menu.vue 踩过这个坑）。
    areaHeightPx 用真实屏幕尺寸算出来，宽度直接用 windowWidth，允许左右贴边。 -->
    <movable-area class="ob-area" :style="{ top: topRpx + 'rpx', height: areaHeightPx + 'px' }">
      <movable-view
        class="ob-view"
        direction="all"
        damping="30"
        :x="x"
        :y="y"
        :style="{ width: bubbleWidthPx + 'px', height: bubbleHeightPx + 'px' }"
        @change="onChange"
        @click="onClick"
      >
        <view class="ob-bubble" :class="['ob-bubble--' + tone, { 'ob-bubble--pulse': justChanged }]">
          <text class="ob-icon iconfont" :class="icon"></text>
          <text v-if="badge" class="ob-label">{{ badge }}</text>
          <text v-if="count > 1" class="ob-count">{{ count }}</text>
        </view>
        <!-- 状态变化时的临时提示条：比单纯放大动画信息量更大，说清楚"现在该干嘛"，
        自动消失，不需要用户点掉。 -->
        <view v-if="showChangeCallout" class="ob-callout">
          <text>{{ actionText }}</text>
        </view>
      </movable-view>
    </movable-area>

    <!-- 首次出现气泡这种新交互时的一次性提示，点了或几秒后自动消失，用 storage 记一下
    不会反复打扰；storage key 是全局共享的，不管气泡先在哪个页面出现，全应用只提示一次。 -->
    <view v-if="showHint" class="ob-hint" :style="{ bottom: hintBottomRpx + 'rpx' }" @click="dismissHint">
      <text>点这里随时看订单进度</text>
    </view>
  </view>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

const HINT_STORAGE_KEY = 'order_bubble_hint_shown'
const BUBBLE_WIDTH_RPX = 190
const BUBBLE_HEIGHT_RPX = 84
const REST_MARGIN_RPX = 20

export default {
  name: 'OrderBubble',
  props: {
    visible: { type: Boolean, default: false },
    tone: { type: String, default: 'paid' },
    icon: { type: String, default: 'icon-pay' },
    badge: { type: String, default: '' },
    actionText: { type: String, default: '' },
    count: { type: Number, default: 0 },
    // 气泡可拖动范围的上边界/下边界留白，不同页面布局不同（比如 menu.vue 底部有购物车栏，
    // mine.vue 没有），由调用页面按自己的布局传入。
    topRpx: { type: Number, default: 320 },
    bottomClearRpx: { type: Number, default: 160 },
  },
  emits: ['click'],
  setup(props, { emit }) {
    const pxPerRpx = ref(1)
    const areaWidthPx = ref(0)
    const areaHeightPx = ref(0)
    const bubbleWidthPx = computed(() => BUBBLE_WIDTH_RPX * pxPerRpx.value)
    const bubbleHeightPx = computed(() => BUBBLE_HEIGHT_RPX * pxPerRpx.value)

    const x = ref(0)
    const y = ref(0)

    const setupGeometry = () => {
      try {
        const info = uni.getSystemInfoSync()
        pxPerRpx.value = info.windowWidth / 750
        const safeBottomPx = Math.max(0, (info.screenHeight || info.windowHeight) - (info.safeArea?.bottom || info.windowHeight))
        const topPx = props.topRpx * pxPerRpx.value
        const bottomClearPx = props.bottomClearRpx * pxPerRpx.value + safeBottomPx * 2
        areaWidthPx.value = info.windowWidth
        areaHeightPx.value = Math.max(0, info.windowHeight - topPx - bottomClearPx)
        const marginPx = REST_MARGIN_RPX * pxPerRpx.value
        x.value = Math.max(0, areaWidthPx.value - bubbleWidthPx.value - marginPx)
        y.value = Math.max(0, areaHeightPx.value - bubbleHeightPx.value - marginPx)
      } catch {}
    }

    onMounted(setupGeometry)

    // movable-view 拖动过程中把实时位置同步回 x/y，松手后如果只改 x 做贴边动画、
    // 不同步 y，movable-view 会用我们这边缓存的旧 y 值去插值，导致贴边瞬间垂直方向跳一下。
    //
    // 贴边判定不靠 touchend——movable-view 自己接管了拖拽手势，直接绑在它上面的
    // touchend 不保证会被派发（这也是上一版"松手不贴边"的根因）。change 事件在拖拽
    // 过程中会连续触发，只要连续 120ms 没收到新的 change，就说明手指已经松开，
    // 这个判断只依赖 movable-view 一定会发的事件，比等 touchend 可靠。
    let dragEndTimer = null
    const onChange = (e) => {
      x.value = e.detail.x
      y.value = e.detail.y
      clearTimeout(dragEndTimer)
      dragEndTimer = setTimeout(snapToNearestEdge, 120)
    }

    function snapToNearestEdge() {
      const marginPx = REST_MARGIN_RPX * pxPerRpx.value
      const maxX = Math.max(0, areaWidthPx.value - bubbleWidthPx.value - marginPx)
      const nearLeft = x.value < (areaWidthPx.value - bubbleWidthPx.value) / 2
      x.value = nearLeft ? marginPx : maxX
    }

    const onClick = () => {
      dismissHint()
      emit('click')
    }

    // 首次提示
    const showHint = ref(false)
    let hintTimer = null
    const dismissHint = () => {
      showHint.value = false
      clearTimeout(hintTimer)
    }
    const hintBottomRpx = computed(() => props.bottomClearRpx + BUBBLE_HEIGHT_RPX + 40)

    watch(() => props.visible, (val, oldVal) => {
      if (val && !oldVal && !uni.getStorageSync(HINT_STORAGE_KEY)) {
        showHint.value = true
        uni.setStorageSync(HINT_STORAGE_KEY, '1')
        hintTimer = setTimeout(dismissHint, 4000)
      }
    })

    // 状态变化：震动 + 短暂脉冲 + 临时提示条，说明"进入了新阶段、现在该干嘛"
    const justChanged = ref(false)
    const showChangeCallout = ref(false)
    let pulseTimer = null
    let calloutTimer = null
    watch(() => props.tone, (val, oldVal) => {
      if (!oldVal || val === oldVal) return
      try { uni.vibrateShort({ type: 'light' }) } catch (_) {}
      justChanged.value = false
      showChangeCallout.value = false
      clearTimeout(pulseTimer)
      clearTimeout(calloutTimer)
      requestAnimationFrame ? requestAnimationFrame(triggerChangeFeedback) : triggerChangeFeedback()
    })
    function triggerChangeFeedback() {
      justChanged.value = true
      pulseTimer = setTimeout(() => { justChanged.value = false }, 700)
      if (props.actionText) {
        showChangeCallout.value = true
        calloutTimer = setTimeout(() => { showChangeCallout.value = false }, 2200)
      }
    }

    onBeforeUnmount(() => {
      clearTimeout(hintTimer)
      clearTimeout(pulseTimer)
      clearTimeout(calloutTimer)
      clearTimeout(dragEndTimer)
    })

    return {
      areaHeightPx, bubbleWidthPx, bubbleHeightPx, x, y,
      onChange, onClick,
      showHint, dismissHint, hintBottomRpx,
      justChanged, showChangeCallout,
    }
  },
}
</script>

<style lang="scss" scoped>
.ob-area {
  position: fixed;
  left: 0;
  width: 100%;
  z-index: 850;
  pointer-events: none;
}

.ob-view {
  pointer-events: auto;
}

.ob-bubble {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  box-sizing: border-box;
  padding: 0 22rpx;
  border: 4rpx solid rgba(255, 255, 255, 0.92);
  box-shadow:
    0 2rpx 6rpx rgba(0, 0, 0, 0.16),
    0 10rpx 28rpx rgba(0, 0, 0, 0.20);
  transition: transform 0.12s ease-out;
  animation: ob-in 0.25s ease-out both;
}

.ob-bubble:active {
  transform: scale(0.94);
}

@keyframes ob-in {
  from { transform: scale(0.4); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.ob-bubble--pulse {
  animation: ob-pulse 0.7s ease-out;
}

@keyframes ob-pulse {
  0% { transform: scale(1); }
  40% { transform: scale(1.08); box-shadow: 0 0 0 16rpx rgba(255, 255, 255, 0); }
  100% { transform: scale(1); }
}

.ob-bubble--paid { background: linear-gradient(145deg, #38bdf8, #0ea5e9); }
.ob-bubble--preparing { background: linear-gradient(145deg, #fbbf24, #f59e0b); }
.ob-bubble--served { background: linear-gradient(145deg, #34d399, var(--brand)); }
.ob-bubble--canceled { background: linear-gradient(145deg, #f87171, #ef4444); }
.ob-bubble--settled { background: linear-gradient(145deg, #cbd5e1, #9ca3af); }

.ob-icon {
  color: #fff;
  font-size: 40rpx;
  line-height: 1;
  text-shadow: 0 2rpx 4rpx rgba(0, 0, 0, 0.12);
  flex-shrink: 0;
}

.ob-label {
  color: #fff;
  font-size: 24rpx;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  flex-shrink: 0;
}

.ob-count {
  position: absolute;
  top: -10rpx;
  right: -10rpx;
  min-width: 32rpx;
  height: 32rpx;
  padding: 0 8rpx;
  border-radius: 16rpx;
  background: #ef4444;
  border: 2rpx solid #fff;
  color: #fff;
  font-size: 20rpx;
  line-height: 28rpx;
  text-align: center;
  font-weight: 800;
  box-sizing: border-box;
}

.ob-callout {
  position: absolute;
  right: 0;
  bottom: calc(100% + 14rpx);
  padding: 12rpx 20rpx;
  border-radius: 20rpx;
  background: rgba(23, 26, 29, 0.92);
  white-space: nowrap;
  animation: ob-in 0.2s ease-out both;
}

.ob-callout text {
  color: #fff;
  font-size: 22rpx;
}

.ob-hint {
  position: fixed;
  right: 24rpx;
  z-index: 851;
  padding: 12rpx 20rpx;
  border-radius: 30rpx;
  background: rgba(23, 26, 29, 0.92);
  color: #fff;
  font-size: 22rpx;
  white-space: nowrap;
  animation: ob-in 0.25s ease-out both;
}
</style>
