<template>
  <web-view v-if="src" :src="src" />
  <view v-else class="empty">正在打开工作台…</view>
</template>

<script>
export default {
  data() {
    return { src: '' }
  },
  onLoad(options) {
    let url = options.url || ''
    try {
      url = decodeURIComponent(String(url))
    } catch {
      url = String(url || '')
    }
    this.src = url
  },
}
</script>

<style scoped>
.empty {
  padding: 80rpx 40rpx;
  text-align: center;
  color: #94a3b8;
}
</style>
