<script setup lang="ts">
import { onLaunch, onShow, onHide } from '@dcloudio/uni-app'
import { markStart } from './utils/perf'

onLaunch(() => {
  // 第0批性能埋点起点："扫码到首屏可交互"要包含小程序冷启动本身的耗时，
  // onLaunch 是能拿到的最早时机。menu.vue 首屏渲染完成后会消费这个起点算出耗时，
  // 不是扫码场景（比如从"我的"页正常打开小程序）时这个起点不会被消费，留在本地
  // 存储里也无所谓，下次真正扫码进来会被覆盖。
  markStart('scan_to_interactive')
})

onShow(() => {
})

onHide(() => {
})
</script>

<style lang="scss">
@import './styles/global.scss';

/* 全局点击反馈：卡片/按钮/图标类可点击元素统一用 .tap-shrink（定义见 styles/global.scss），
   跟列表行的背景色反馈（mine.vue 的 service-row 等）是两种不同但都合理的反馈方式，不用互相替代。 */
</style>
