<template>
  <div class="uni-header">
    <a-button v-if="!noBack" type="text" class="back-btn" @click="router.back()">
      <template #icon><ArrowLeftOutlined /></template>
    </a-button>
    <span class="uni-header-title">{{ title }}</span>
    <div class="uni-header-right">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
defineProps({ title: String, noBack: Boolean })
const router = useRouter()
</script>

<style scoped>
.uni-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  height: calc(52px + env(safe-area-inset-top));
  padding: env(safe-area-inset-top) 12px 0 4px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.back-btn { color: var(--text-1) !important; flex-shrink: 0; }
.uni-header-title {
  flex: 1;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-1);
  padding-left: 4px;
}
.uni-header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
</style>
