<template>
  <div class="custom-checkbox" @click="toggle">
    <div class="checkbox-box" :class="{ checked: modelValue }">
      <van-icon v-if="modelValue" name="success" size="14" />
    </div>
    <span v-if="label" class="checkbox-label">{{ label }}</span>
  </div>
</template>

<script setup>
import { Icon as VanIcon } from 'vant'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  label: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const toggle = () => {
  const newValue = !props.modelValue
  emit('update:modelValue', newValue)
  emit('change', newValue)
}
</script>

<style scoped>
.custom-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox-box {
  width: 20px;
  height: 20px;
  border: 2px solid #d1d5db;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.checkbox-box.checked {
  background: #6d5dfb;
  border-color: #6d5dfb;
  color: #fff;
}

.checkbox-label {
  font-size: 14px;
  color: #111827;
}
</style>
