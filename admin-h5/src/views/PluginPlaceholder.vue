<template>
  <div class="plugin-placeholder-page">
    <section class="section-block">
      <div class="section-head">
        <div>
          <h2 class="section-title">{{ pluginTitle }}</h2>
          <p class="section-desc">插件已启用，具体业务页面可按插件约定继续扩展。</p>
        </div>
      </div>

      <div class="empty-card">
        <van-icon name="apps" size="48" color="#d1d5db" />
        <div class="empty-text">插件页面占位</div>
        <van-button type="primary" @click="$router.push('/plugins')">返回插件中心</van-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Button as VanButton, Icon as VanIcon } from 'vant'

const route = useRoute()
const pluginTitle = computed(() => `${route.params.code || '插件'} 管理`)
</script>

<style scoped>
.plugin-placeholder-page {
  min-height: 100vh;
  padding: 16px 16px 88px;
  background: #f6f7fb;
}

.section-block {
  margin-bottom: 20px;
}

.section-head {
  margin-bottom: 16px;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
}

.section-desc {
  font-size: 13px;
  color: #8a8f9c;
  margin-top: 4px;
}

.empty-card {
  background: #fff;
  border-radius: 16px;
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}

.empty-text {
  font-size: 15px;
  color: #6b7280;
}
</style>
