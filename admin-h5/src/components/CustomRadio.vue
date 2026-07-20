<template>
  <div class="custom-radio">
    <div 
      v-for="item in options" 
      :key="item.value"
      class="radio-item"
      :class="{ active: modelValue === item.value, disabled: item.disabled }"
      @click="handleSelect(item)"
    >
      <div class="radio-circle">
        <div v-if="modelValue === item.value" class="radio-inner"></div>
      </div>
      <span v-if="item.label" class="radio-label">{{ item.label }}</span>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: ''
  },
  options: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const handleSelect = (item) => {
  if (item.disabled) return
  emit('update:modelValue', item.value)
  emit('change', item.value)
}
</script>

<style scoped>
.custom-radio {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 8px 0;
  transition: all 0.2s;
}

.radio-item:not(.disabled):active {
  opacity: 0.8;
}

.radio-item.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.radio-circle {
  width: 20px;
  height: 20px;
  border: 2px solid #d1d5db;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.radio-item.active .radio-circle {
  border-color: #6d5dfb;
}

.radio-inner {
  width: 10px;
  height: 10px;
  background: linear-gradient(135deg, #6d5dfb, #a855f7);
  border-radius: 50%;
}

.radio-label {
  font-size: 14px;
  color: #111827;
}
</style>
