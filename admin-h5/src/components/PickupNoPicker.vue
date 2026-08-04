<template>
  <div class="pickup-picker">
    <div class="pickup-trigger" @click="open = !open">
      <span v-if="modelValue" class="pickup-trigger-value">{{ modelValue }}号牌 · 改</span>
      <span v-else class="pickup-trigger-placeholder">{{ placeholder }}</span>
    </div>
    <div v-if="open" class="pickup-grid">
      <div
        v-for="n in count"
        :key="n"
        class="pickup-cell"
        :class="{ 'pickup-cell--active': String(n) === String(modelValue) }"
        @click="pick(n)"
      >{{ n }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// 取餐牌号本质是老板/前台手上一叠实体号牌，登记这个号从来不是"打字"这个动作该做的事——
// 号是数出来的、不是打出来的。改成点一下数字格子直接登记，比弹键盘打字快，也不会
// 出现"12"打成"21"这种手滑打错。号牌范围给到1-30，覆盖绝大多数小餐饮的实际数量。
const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  placeholder: { type: String, default: '登记取餐牌号' },
  count: { type: Number, default: 30 },
})
const emit = defineEmits(['pick'])

const open = ref(false)

function pick(n) {
  open.value = false
  emit('pick', String(n))
}
</script>

<style scoped>
.pickup-trigger {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 14px;
  border-radius: 15px;
  border: 1px solid var(--border);
  background: #fff;
  font-size: 13px;
  cursor: pointer;
}
.pickup-trigger-placeholder { color: var(--text-3); }
.pickup-trigger-value { color: #c2410c; font-weight: 600; }
.pickup-grid {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
}
.pickup-cell {
  height: 40px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #fafafa;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}
.pickup-cell:active { opacity: 0.7; }
.pickup-cell--active {
  border-color: #f59e0b;
  background: #fff7ed;
  color: #c2410c;
}
</style>
