<script setup lang="ts">
import { onLaunch, onShow, onHide } from '@dcloudio/uni-app'
import {
  handleAppHide,
  handleAppShow,
  markEvent,
  markStart,
  startPerformanceSession,
} from './utils/perf'

onLaunch(() => {
  // This is the earliest app-internal point. QR recognition and WeChat platform time remain external.
  startPerformanceSession('cold')
  markEvent('app_launch', { scope: 'APP_INTERNAL_TIME' })
  markStart('launch_to_entry')
})

onShow(() => {
  handleAppShow()
})

onHide(() => {
  handleAppHide()
})
</script>

<style lang="scss">
@import './styles/global.scss';

/* 全局点击反馈：卡片/按钮/图标类可点击元素统一用 .tap-shrink（定义见 styles/global.scss），
   跟列表行的背景色反馈（mine.vue 的 service-row 等）是两种不同但都合理的反馈方式，不用互相替代。 */
</style>
