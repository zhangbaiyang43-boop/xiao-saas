<template>
  <div class="tabs-shell">
    <router-view />
    <AppTabBar />
  </div>
</template>

<script setup>
import AppTabBar from '../components/AppTabBar.vue'
</script>
