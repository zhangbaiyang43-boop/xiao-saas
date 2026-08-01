<template>
  <a-config-provider
    :theme="{
      algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: {
        colorPrimary: '#07C160',
        colorLink: '#07C160',
        colorSuccess: '#16a34a',
        colorWarning: '#f59e0b',
        colorError: '#ef4444',
        borderRadius: 8,
        fontFamily: '-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Arial, sans-serif',
      },
    }"
  >
    <router-view />
  </a-config-provider>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { theme } from 'ant-design-vue'

// 跟随系统深浅色，不做应用内单独的切换开关——Ant 组件自身的配色（卡片/按钮/骨架屏等）
// 靠这里的 algorithm 切换；我们自己写的 CSS（今日页等）靠 global.scss 里 prefers-color-scheme
// 覆盖的那套 token 生效，两边同一个媒体查询条件，不会不同步。
const isDark = ref(false)
let mediaQuery = null
function handleChange(e) { isDark.value = e.matches }

onMounted(() => {
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  isDark.value = mediaQuery.matches
  mediaQuery.addEventListener('change', handleChange)
})
onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', handleChange)
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: var(--bg-page);
}
</style>
