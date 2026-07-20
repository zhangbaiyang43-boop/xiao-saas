<template>
  <nav class="navbar">
    <div class="navbar-content">
      <div v-if="showUser" class="navbar-left">
        <div class="user-avatar"><ShopOutlined style="font-size:20px;color:#fff" /></div>
        <div class="user-info">
          <div class="user-name">{{ userName }}</div>
          <div class="user-role">{{ userRole }}</div>
        </div>
      </div>
      <div v-if="title" class="navbar-center"><h1 class="navbar-title">{{ title }}</h1></div>
      <div class="navbar-right">
        <slot name="right">
          <a-button type="text" @click="goSettings"><template #icon><SettingOutlined style="font-size:20px;color:#6b7280" /></template></a-button>
        </slot>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ShopOutlined, SettingOutlined } from '@ant-design/icons-vue'
defineProps({ title: String, showUser: { type: Boolean, default: true } })
const userName = computed(() => localStorage.getItem('tenant_name') || '商家管理员')
const userRole = computed(() => localStorage.getItem('tenant_role') || localStorage.getItem('role') || '管理员')
const router = useRouter()
const goSettings = () => router.push('/settings')
</script>

<style scoped>
.navbar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  padding: env(safe-area-inset-top) 16px 0;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}
.navbar-content {
  display: flex; align-items: center; justify-content: space-between;
  height: 52px;
}
.navbar-left { display: flex; align-items: center; gap: 10px; }
.user-avatar {
  width: 38px; height: 38px; border-radius: 12px;
  background: var(--brand);
  display: flex; align-items: center; justify-content: center;
}
.user-name { font-size: 14px; font-weight: 700; color: #111; }
.user-role { font-size: 11px; color: #9ca3af; margin-top: 1px; }
.navbar-title { font-size: 17px; font-weight: 700; color: #111; margin: 0; }
.navbar-right { display: flex; align-items: center; }
</style>
