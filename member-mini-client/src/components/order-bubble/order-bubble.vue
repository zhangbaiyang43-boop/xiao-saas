<template>
  <view v-if="visible && geometryReady">
    <!-- 可拖区域：明确像素高宽，供贴边与纵向 clamp 使用；pointer-events 透传给气泡本身。 -->
    <view class="ob-area" :style="{ top: topRpx + 'rpx', height: areaHeightPx + 'px' }">
      <view
        class="ob-view"
        :class="{ 'ob-view--snapping': snapping }"
        :style="viewStyle"
        @touchstart.stop.prevent="onTouchStart"
        @touchmove.stop.prevent="onTouchMove"
        @touchend.stop="onTouchEnd"
        @touchcancel.stop="onTouchEnd"
        @transitionend="onSnapTransitionEnd"
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
      </view>
    </view>

    <!-- 首次出现气泡这种新交互时的一次性提示，点了或几秒后自动消失，用 storage 记一下
    不会反复打扰；storage key 是全局共享的，不管气泡先在哪个页面出现，全应用只提示一次。 -->
    <view v-if="showHint" class="ob-hint" :style="{ bottom: hintBottomRpx + 'rpx' }" @click="dismissHint">
      <text>点这里随时看订单进度</text>
    </view>
  </view>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

const HINT_STORAGE_KEY = 'order_bubble_hint_shown'
const BUBBLE_WIDTH_RPX = 190
const BUBBLE_HEIGHT_RPX = 84
const REST_MARGIN_RPX = 20
const TAP_SLOP_PX = 5
const SNAP_MS = 260
// 默认贴左、贴近可拖区域底部——正好停在调用页面通过 bottomClearRpx 预留出的
// 购物车栏/tabbar 上方，不挡住它们，但视觉上"就在旁边"，用户一眼能看出气泡和
// 底部操作栏是一组。仍然可以随手拖到屏幕任意位置。
const DEFAULT_Y_RATIO = 1

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
    const geometryReady = ref(false)
    const bubbleWidthPx = computed(() => BUBBLE_WIDTH_RPX * pxPerRpx.value)
    const bubbleHeightPx = computed(() => BUBBLE_HEIGHT_RPX * pxPerRpx.value)

    // 位置只由 transform 驱动：拖动时无 transition 跟手；松手后一次性改目标 X，
    // 交给 CSS cubic-bezier 在 UI 线程插值，避免 movable-view 的 x/y ↔ change 回环卡顿。
    const posX = ref(0)
    const posY = ref(0)
    const snapping = ref(false)
    const dragging = ref(false)

    let startTouchX = 0
    let startTouchY = 0
    let startPosX = 0
    let startPosY = 0
    let moved = false
    let snapTimer = null
    let activeTouchId = null

    const viewStyle = computed(() => ({
      width: `${bubbleWidthPx.value}px`,
      height: `${bubbleHeightPx.value}px`,
      transform: `translate3d(${posX.value}px, ${posY.value}px, 0)`,
    }))

    const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

    const maxPosX = () => Math.max(0, areaWidthPx.value - bubbleWidthPx.value)
    const maxPosY = () => Math.max(0, areaHeightPx.value - bubbleHeightPx.value)
    const restMarginPx = () => REST_MARGIN_RPX * pxPerRpx.value
    const restMaxX = () => Math.max(0, areaWidthPx.value - bubbleWidthPx.value - restMarginPx())

    const setupGeometry = () => {
      try {
        const info = uni.getSystemInfoSync()
        pxPerRpx.value = info.windowWidth / 750
        const safeBottomPx = Math.max(0, (info.screenHeight || info.windowHeight) - (info.safeArea?.bottom || info.windowHeight))
        const topPx = props.topRpx * pxPerRpx.value
        const bottomClearPx = props.bottomClearRpx * pxPerRpx.value + safeBottomPx * 2
        areaWidthPx.value = info.windowWidth
        areaHeightPx.value = Math.max(0, info.windowHeight - topPx - bottomClearPx)
        posX.value = restMarginPx()
        posY.value = Math.max(0, Math.min(maxPosY(), areaHeightPx.value * DEFAULT_Y_RATIO))
      } catch {
        // 读不到系统信息就用不了自适应定位，气泡保持默认位置，不影响点餐主流程。
      } finally {
        geometryReady.value = true
      }
    }

    onMounted(setupGeometry)

    const onTouchStart = (e) => {
      if (snapping.value) return
      const touch = e.touches?.[0]
      if (!touch) return
      activeTouchId = touch.identifier
      startTouchX = touch.clientX
      startTouchY = touch.clientY
      startPosX = posX.value
      startPosY = posY.value
      moved = false
      dragging.value = true
      snapping.value = false
      clearTimeout(snapTimer)
    }

    const onTouchMove = (e) => {
      if (!dragging.value) return
      const touch = findTouch(e.touches, activeTouchId) || e.touches?.[0]
      if (!touch) return
      const dx = touch.clientX - startTouchX
      const dy = touch.clientY - startTouchY
      if (Math.abs(dx) > TAP_SLOP_PX || Math.abs(dy) > TAP_SLOP_PX) moved = true
      posX.value = clamp(startPosX + dx, 0, maxPosX())
      posY.value = clamp(startPosY + dy, 0, maxPosY())
    }

    const onTouchEnd = (e) => {
      if (!dragging.value) return
      // 多指时忽略非当前手指的结束事件
      if (e.changedTouches?.length && activeTouchId != null) {
        const ended = findTouch(e.changedTouches, activeTouchId)
        if (!ended) return
      }
      dragging.value = false
      activeTouchId = null
      if (!moved) {
        onClick()
        return
      }
      snapToNearestEdge()
    }

    function findTouch(list, id) {
      if (!list || id == null) return null
      for (let i = 0; i < list.length; i += 1) {
        if (list[i].identifier === id) return list[i]
      }
      return null
    }

    function snapToNearestEdge() {
      const nearLeft = posX.value < maxPosX() / 2
      const targetX = nearLeft ? restMarginPx() : restMaxX()
      if (Math.abs(targetX - posX.value) < 0.5) {
        snapping.value = false
        return
      }
      snapping.value = true
      // 等 --snapping 的 transition 挂上后再写目标位，避免首帧瞬移。
      nextTick(() => { posX.value = targetX })
      clearTimeout(snapTimer)
      snapTimer = setTimeout(() => { snapping.value = false }, SNAP_MS + 40)
    }

    const onSnapTransitionEnd = () => {
      snapping.value = false
      clearTimeout(snapTimer)
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
      // 震动只是个反馈锦上添花，设备不支持或权限没开时静默跳过，不影响状态切换本身。
      // eslint-disable-next-line no-empty
      try { uni.vibrateShort({ type: 'light' }) } catch (_) {}
      justChanged.value = false
      showChangeCallout.value = false
      clearTimeout(pulseTimer)
      clearTimeout(calloutTimer)
      if (typeof requestAnimationFrame === 'function') {
        requestAnimationFrame(triggerChangeFeedback)
      } else {
        triggerChangeFeedback()
      }
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
      clearTimeout(snapTimer)
    })

    return {
      geometryReady,
      areaHeightPx, viewStyle, snapping,
      onTouchStart, onTouchMove, onTouchEnd, onSnapTransitionEnd,
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
  overflow: visible;
}

.ob-view {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: auto;
  will-change: transform;
  // 拖动跟手：无过渡；仅在 --snapping 时开 UI 线程补间
  transition: none;
  z-index: 1;
}

.ob-view--snapping {
  transition: transform 0.26s cubic-bezier(0.2, 0.8, 0.2, 1);
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
.ob-bubble--preparing { background: linear-gradient(145deg, #fbbf24, var(--warning)); }
.ob-bubble--served { background: linear-gradient(145deg, #34d399, var(--brand)); }
.ob-bubble--canceled { background: linear-gradient(145deg, #f87171, var(--danger)); }
.ob-bubble--settled { background: linear-gradient(145deg, #cbd5e1, #9ca3af); }

.ob-icon {
  color: var(--text-inverse);
  font-size: 40rpx;
  line-height: 1;
  text-shadow: 0 2rpx 4rpx rgba(0, 0, 0, 0.12);
  flex-shrink: 0;
}

.ob-label {
  color: var(--text-inverse);
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
  background: var(--danger);
  border: 2rpx solid #fff;
  color: var(--text-inverse);
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
  color: var(--text-inverse);
  font-size: 22rpx;
}

.ob-hint {
  position: fixed;
  left: 24rpx;
  z-index: 851;
  padding: 12rpx 20rpx;
  border-radius: 30rpx;
  background: rgba(23, 26, 29, 0.92);
  color: var(--text-inverse);
  font-size: 22rpx;
  white-space: nowrap;
  animation: ob-in 0.25s ease-out both;
}
</style>
