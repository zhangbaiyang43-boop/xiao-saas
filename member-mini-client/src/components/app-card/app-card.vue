<template>
  <view class="app-card">
    <slot />
  </view>
</template>

<script>
export default {
  name: 'AppCard',
  options: {
    virtualHost: true,
  },
}
</script>

<style lang="scss" scoped>
.app-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  box-shadow: var(--card-shadow);
  box-sizing: border-box;
}
</style>
