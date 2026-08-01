<template>
  <a-card
    :bordered="false"
    hoverable
    class="insight-card tap-shrink"
    :class="[tintClass]"
    @click="handleClick"
  >
    <template #title>
      <span class="insight-title">
        <span class="insight-icon-badge"><component :is="icon" /></span>
        {{ title }}
      </span>
    </template>
    <template v-if="to" #extra>
      <span class="insight-more">详情 <RightOutlined /></span>
    </template>

    <a-skeleton v-if="loading" active :title="false" :paragraph="{ rows: 2 }" />
    <slot v-else />
  </a-card>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { RightOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  icon: { type: [Object, Function], required: true },
  title: { type: String, required: true },
  to: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  tint: { type: String, default: 'mint' }, // mint | none
})

const router = useRouter()
const tintClass = props.tint === 'mint' ? 'insight-card--mint' : ''

function handleClick(e) {
  if (!props.to) return
  // 卡片内部的按钮/交互元素自己会 @click.stop，这里只处理"点卡片空白处跳详情"
  router.push(props.to)
}
</script>

<style scoped>
.insight-card {
  cursor: pointer;
}
.insight-card--mint {
  background: linear-gradient(165deg, #f0fdf7 0%, #ffffff 55%);
  border: 1px solid #e3f7ec;
}
.insight-card :deep(.ant-card-body) { padding: 14px 16px; }
.insight-card :deep(.ant-card-head) { border-bottom: none; }

.insight-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-1);
}
.insight-icon-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 8px;
  background: linear-gradient(135deg, #06d16e, #059952);
  color: #fff;
  box-shadow: 0 2px 6px rgba(5,153,82,.3);
}
.insight-icon-badge :deep(svg) { font-size: 13px; }

.insight-more {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 13px;
  color: var(--text-3);
  padding: 4px;
}
.insight-more :deep(svg) { font-size: 11px; }
</style>
