<template>
  <div style="min-height:100vh;background:#f5f6fa">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
    <TabBar />
  </div>
</template>

<script setup>
import TabBar from '../components/TabBar.vue'
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
