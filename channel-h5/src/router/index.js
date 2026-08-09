import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/auth/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    children: [
      { path: '', redirect: '/home' },
      { path: 'home', name: 'home', component: () => import('../views/home/Home.vue') },
      { path: 'leads', redirect: '/merchants' },
      { path: 'leads/new', name: 'lead-submit', component: () => import('../views/leads/LeadSubmit.vue') },
      { path: 'leads/:id', name: 'lead-detail', component: () => import('../views/leads/LeadDetail.vue') },
      { path: 'merchants', name: 'merchants', component: () => import('../views/merchants/MerchantList.vue') },
      { path: 'merchants/:id', name: 'merchant-detail', component: () => import('../views/merchants/MerchantDetail.vue') },
      { path: 'earnings', name: 'earnings', component: () => import('../views/earnings/Earnings.vue') },
      { path: 'settlements', name: 'settlements', component: () => import('../views/settlements/SettlementList.vue') },
      { path: 'settlements/:id', name: 'settlement-detail', component: () => import('../views/settlements/SettlementDetail.vue') },
      { path: 'profile', name: 'profile', component: () => import('../views/profile/Profile.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.restoreSession()
  if (!to.meta.public && !auth.isAuthenticated) return '/login'
  if (to.meta.public && auth.isAuthenticated) return '/home'
  return true
})

export default router
