<template>
  <div class="card empty">
    <div class="title">{{ title }}</div>
    <div v-if="description" class="muted">{{ description }}</div>
    <button v-if="actionText" class="soft-button" type="button" @click="$emit('action')">{{ actionText }}</button>
  </div>
</template>

<script setup>
defineEmits(['action'])
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  actionText: { type: String, default: '' },
})
</script>

<style scoped>
.empty {
  text-align: center;
}
.title {
  margin-bottom: 6px;
  font-weight: 720;
}
.soft-button {
  margin-top: 12px;
}
</style>
