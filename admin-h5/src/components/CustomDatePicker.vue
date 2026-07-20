<template>
  <div class="custom-date-picker">
    <input 
      type="date" 
      :value="modelValue" 
      :min="minDate" 
      :max="maxDate" 
      :disabled="disabled"
      :placeholder="placeholder"
      @input="handleInput"
      class="date-input"
    />
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  minDate: {
    type: String,
    default: ''
  },
  maxDate: {
    type: String,
    default: ''
  },
  disabled: {
    type: Boolean,
    default: false
  },
  placeholder: {
    type: String,
    default: '选择日期'
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const handleInput = (e) => {
  const value = e.target.value
  emit('update:modelValue', value)
  emit('change', value)
}
</script>

<style scoped>
.custom-date-picker {
  width: 100%;
}

.date-input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  font-size: 14px;
  color: #111827;
  background: #fff;
  transition: all 0.2s;
  box-sizing: border-box;
}

.date-input:focus {
  outline: none;
  border-color: #6d5dfb;
  box-shadow: 0 0 0 3px rgba(109, 93, 251, 0.1);
}

.date-input:disabled {
  background: #f3f4f6;
  color: #9ca3af;
  cursor: not-allowed;
}
</style>
