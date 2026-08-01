<template>
  <div class="sub-page">
    <PageHeader :title="pluginTitle" />

    <div class="page-body">
      <section class="section-block animate-in">
        <p class="section-desc">插件已启用，具体业务页面可按插件约定继续扩展。</p>

        <div class="empty-card">
          <van-icon name="apps" size="48" color="var(--text-3)" />
          <div class="empty-text">插件页面占位</div>
          <van-button type="primary" round class="tap-shrink" @click="$router.push('/plugins')">返回插件中心</van-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Button as VanButton, Icon as VanIcon } from 'vant'
import PageHeader from '../components/PageHeader.vue'

const route = useRoute()
const pluginTitle = computed(() => `${route.params.code || '插件'} 管理`)
</script>

<style scoped>
.section-block {
  padding-top: 4px;
}

.section-desc {
  font-size: 13px;
  color: var(--text-2);
  margin: 0 0 16px;
  line-height: 1.5;
}

.empty-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}

.empty-text {
  font-size: 15px;
  color: var(--text-2);
}

</style>
