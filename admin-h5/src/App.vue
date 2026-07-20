<template>
  <a-config-provider
    :theme="{
      token: {
        colorPrimary: '#07C160',
        colorLink: '#07C160',
        colorSuccess: '#16a34a',
        colorWarning: '#f59e0b',
        colorError: '#ef4444',
        borderRadius: 8,
        fontFamily: '-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Arial, sans-serif',
      },
    }"
  >
    <router-view />
  </a-config-provider>
</template>

<script setup>
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f5f6fa;
}
</style>
