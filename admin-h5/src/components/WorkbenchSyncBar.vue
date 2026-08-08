<template>
  <div
    class="wb-sync-bar"
    :class="{
      offline: !networkOnline,
      failed: networkOnline && syncFailed,
      dark: variant === 'dark',
    }"
  >
    <span class="seg">
      <span class="dot" :class="networkOnline ? 'on' : 'off'" />
      {{ networkOnline ? '在线' : '网络已断开' }}
    </span>
    <span class="sep">·</span>
    <span class="seg">
      <template v-if="soundReady">声音已开启</template>
      <template v-else>
        声音未开启
        <button type="button" class="sound-btn" @click="$emit('enable-sound')">开启</button>
      </template>
    </span>
    <span class="sep">·</span>
    <span class="seg muted">{{ lastSyncLabel }}</span>
  </div>
</template>

<script setup>
defineProps({
  networkOnline: { type: Boolean, default: true },
  syncFailed: { type: Boolean, default: false },
  soundReady: { type: Boolean, default: false },
  lastSyncLabel: { type: String, default: '' },
  variant: { type: String, default: 'light' },
})
defineEmits(['enable-sound'])
</script>

<style scoped>
.wb-sync-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #fff;
  font-size: 12px;
  color: #444;
  line-height: 1.4;
}
.wb-sync-bar.dark {
  background: #1f2937;
  color: #e5e7eb;
}
.wb-sync-bar.offline,
.wb-sync-bar.failed {
  background: #fff7ed;
  color: #9a3412;
}
.wb-sync-bar.dark.offline,
.wb-sync-bar.dark.failed {
  background: #422006;
  color: #fdba74;
}
.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
.dot.on { background: #16a34a; }
.dot.off { background: #ea580c; }
.sep { color: #bbb; }
.wb-sync-bar.dark .sep { color: #4b5563; }
.muted { color: #888; }
.wb-sync-bar.dark .muted { color: #9ca3af; }
.wb-sync-bar.offline .muted,
.wb-sync-bar.failed .muted { color: inherit; opacity: 0.9; }
.sound-btn {
  margin-left: 4px;
  border: 1px solid #d97706;
  background: #fff;
  color: #b45309;
  border-radius: 999px;
  font-size: 12px;
  padding: 0 8px;
  height: 22px;
  line-height: 20px;
  cursor: pointer;
}
.wb-sync-bar.dark .sound-btn {
  border-color: #f59e0b;
  background: #111827;
  color: #fbbf24;
}
</style>
