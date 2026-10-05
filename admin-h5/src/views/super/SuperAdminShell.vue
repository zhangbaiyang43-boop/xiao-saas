<template>
  <div class="super-shell">
    <aside class="super-sidebar" :class="{ open: mobileNavOpen }">
      <div class="brand-block">
        <div class="brand-mark">开心点单</div>
        <div class="brand-subtitle">平台中控台</div>
      </div>

      <nav class="platform-nav" aria-label="平台导航">
        <RouterLink class="nav-link nav-link--root" :class="{ active: activeDomain === 'overview' }" to="/super" @click="closeMobileNav">
          <span>总览</span>
        </RouterLink>

        <div v-for="group in navGroups" :key="group.domain" class="nav-group">
          <div class="nav-domain" :class="{ active: activeDomain === group.domain }">{{ group.label }}</div>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            class="nav-link"
            :class="{ active: isItemActive(item) }"
            :to="item.to"
            @click="closeMobileNav"
          >
            <span>{{ item.label }}</span>
            <span v-if="item.badge && pendingCount > 0" class="nav-badge">{{ pendingCount }}</span>
          </RouterLink>
        </div>
      </nav>

      <button type="button" class="logout-button" @click="$emit('logout')">退出登录</button>
    </aside>

    <button v-if="mobileNavOpen" type="button" class="nav-backdrop" aria-label="关闭导航" @click="closeMobileNav" />

    <main class="super-main">
      <header class="mobile-header">
        <button type="button" class="menu-button" aria-label="打开平台导航" @click="mobileNavOpen = true">菜单</button>
        <div>
          <div class="mobile-brand">开心点单</div>
          <div class="mobile-console">平台中控台</div>
        </div>
      </header>
      <div class="super-content">
        <slot />
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

defineProps({
  pendingCount: { type: Number, default: 0 },
})

defineEmits(['logout'])

const route = useRoute()
const mobileNavOpen = ref(false)

const navGroups = [
  { domain: 'merchants', label: '商户', items: [
    { label: '商户列表', to: '/super/merchants', match: '/super/merchants' },
    { label: '开通商户', to: '/super/merchants/new', exact: true },
  ] },
  { domain: 'billing', label: '商业化', items: [
    { label: '待确认付款', to: '/super/billing/pending', match: '/super/billing', badge: true },
  ] },
  { domain: 'channels', label: '渠道', items: [
    { label: '渠道伙伴', to: '/super/channels', match: '/super/channels' },
  ] },
  { domain: 'system', label: '系统', items: [
    { label: '性能', to: '/super/system/performance', match: '/super/system' },
  ] },
]

const activeDomain = computed(() => {
  const path = route.path
  if (path === '/super') return 'overview'
  if (path.startsWith('/super/merchants')) return 'merchants'
  if (path.startsWith('/super/billing')) return 'billing'
  if (path.startsWith('/super/channels')) return 'channels'
  if (path.startsWith('/super/system')) return 'system'
  return ''
})

function isItemActive(item) {
  if (item.exact) return route.path === item.to
  if (item.to === '/super/merchants') return route.path.startsWith('/super/merchants') && route.path !== '/super/merchants/new'
  return route.path.startsWith(item.match || item.to)
}

function closeMobileNav() {
  mobileNavOpen.value = false
}
</script>

<style scoped>
* { box-sizing: border-box; }
.super-shell { min-height: 100vh; background: var(--bg-page); color: var(--text-1); }
.super-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 30;
  display: flex;
  width: 232px;
  flex-direction: column;
  padding: 24px 16px 18px;
  background: #171923;
  color: #fff;
}
.brand-block { padding: 0 8px 24px; border-bottom: 1px solid rgba(255,255,255,.1); }
.brand-mark { font-size: 18px; font-weight: 900; letter-spacing: .02em; }
.brand-subtitle { margin-top: 4px; color: rgba(255,255,255,.56); font-size: 12px; }
.platform-nav { flex: 1; overflow-y: auto; padding-top: 18px; }
.nav-group { margin-top: 18px; }
.nav-domain { padding: 0 10px 6px; color: rgba(255,255,255,.46); font-size: 11px; font-weight: 800; letter-spacing: .08em; }
.nav-domain.active { color: rgba(255,255,255,.86); }
.nav-link {
  display: flex;
  min-height: 40px;
  align-items: center;
  justify-content: space-between;
  margin: 2px 0;
  padding: 0 10px;
  border-radius: 8px;
  color: rgba(255,255,255,.7);
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}
.nav-link:hover { background: rgba(255,255,255,.06); color: #fff; }
.nav-link.active { background: rgba(255,255,255,.12); color: #fff; }
.nav-link--root { font-size: 14px; }
.nav-badge { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px; background: var(--danger); color: #fff; font-size: 11px; line-height: 20px; text-align: center; }
.logout-button { height: 40px; border: 1px solid rgba(255,255,255,.16); border-radius: 8px; background: transparent; color: rgba(255,255,255,.75); cursor: pointer; font-weight: 700; }
.super-main { min-height: 100vh; margin-left: 232px; }
.super-content { width: min(1180px, 100%); margin: 0 auto; padding: 28px 28px 48px; }
.mobile-header { display: none; }
.nav-backdrop { display: none; }

@media (max-width: 820px) {
  .super-sidebar { transform: translateX(-100%); transition: transform .18s ease; }
  .super-sidebar.open { transform: translateX(0); }
  .super-main { margin-left: 0; }
  .super-content { padding: 18px 14px 36px; }
  .mobile-header { display: flex; min-height: 56px; align-items: center; gap: 12px; padding: 8px 14px; background: #171923; color: #fff; }
  .menu-button { height: 36px; padding: 0 12px; border: 1px solid rgba(255,255,255,.2); border-radius: 8px; background: rgba(255,255,255,.08); color: #fff; cursor: pointer; }
  .mobile-brand { font-size: 14px; font-weight: 900; }
  .mobile-console { margin-top: 1px; color: rgba(255,255,255,.58); font-size: 10px; }
  .nav-backdrop { display: block; position: fixed; inset: 0; z-index: 20; border: 0; background: rgba(0,0,0,.42); }
}

@media (prefers-reduced-motion: reduce) {
  .super-sidebar { transition: none; }
}
</style>
