import { createRouter, createWebHistory } from 'vue-router'
import { clearSession, getToken, hasValidSession, isTokenExpired } from '../utils/session'
import { useAuthStore } from '../stores/auth'
import { beginPageNavigation, completePageNavigation } from '../utils/adminPerformance'

const Login = () => import('../views/Login.vue')
const ActivationHome = () => import('../views/ActivationHome.vue')
const Layout = () => import('../views/Layout.vue')
const Dashboard = () => import('../views/Dashboard.vue')
const CustomerList = () => import('../views/CustomerList.vue')
const CustomerDetail = () => import('../views/CustomerDetail.vue')
const ConsumptionList = () => import('../views/ConsumptionList.vue')
const CouponCenter = () => import('../views/CouponCenter.vue')
const CouponRecords = () => import('../views/CouponRecords.vue')
const MarketingEffectiveness = () => import('../views/MarketingEffectiveness.vue')
const Distribution = () => import('../views/Distribution.vue')
const StaffReferral = () => import('../views/StaffReferral.vue')
const EntranceCodeList = () => import('../views/EntranceCodeList.vue')
const ChannelEntryList = () => import('../views/ChannelEntryList.vue')
const Verify = () => import('../views/Verify.vue')
const PluginPlaceholder = () => import('../views/PluginPlaceholder.vue')
const MerchantSettings = () => import('../views/MerchantSettings.vue')
const BusinessSettings = () => import('../views/settings/BusinessSettings.vue')
const PaymentSettings = () => import('../views/settings/PaymentSettings.vue')
const DeviceSettings = () => import('../views/settings/DeviceSettings.vue')
const SubscriptionSettings = () => import('../views/settings/SubscriptionSettings.vue')
const NotificationSettings = () => import('../views/settings/NotificationSettings.vue')
const StoreSettings = () => import('../views/settings/StoreSettings.vue')
const WeworkSettings = () => import('../views/WeworkSettings.vue')
const MenuManage = () => import('../views/MenuManage.vue')
const OrderManage = () => import('../views/OrderManage.vue')
const OrderPage = () => import('../views/OrderPage.vue')
const QueueManage = () => import('../views/QueueManage.vue')
const QueueDisplay = () => import('../views/QueueDisplay.vue')
const QueueStatus = () => import('../views/QueueStatus.vue')
const More = () => import('../views/More.vue')
const SuperAdmin = () => import('../views/SuperAdmin.vue')
const WaiterWorkbench = () => import('../views/WaiterWorkbench.vue')
const KitchenWorkbench = () => import('../views/KitchenWorkbench.vue')
const FrontdeskWorkbench = () => import('../views/FrontdeskWorkbench.vue')
const StaffManage = () => import('../views/StaffManage.vue')

const ownerOnly = { requiresPermission: '*' }

const routes = [
  { path: '/login', name: 'Login', component: Login },
  { path: '/activation', name: 'ActivationHome', component: ActivationHome, meta: ownerOnly },
  { path: '/order', name: 'OrderPage', component: OrderPage },
  { path: '/super', name: 'SuperAdmin', component: SuperAdmin },
  { path: '/queue/display', name: 'QueueDisplay', component: QueueDisplay },
  { path: '/queue/status', name: 'QueueStatus', component: QueueStatus },
  {
    path: '/',
    name: 'Layout',
    component: Layout,
    children: [
      { path: '', name: 'Dashboard', component: Dashboard, meta: ownerOnly },
      {
        path: 'frontdesk',
        name: 'FrontdeskWorkbench',
        component: FrontdeskWorkbench,
        meta: { requiresPermission: 'order.view_fulfillment', staffRoles: ['frontdesk'] },
      },
      {
        path: 'waiter',
        name: 'WaiterWorkbench',
        component: WaiterWorkbench,
        meta: { requiresPermission: 'order.view_fulfillment', staffRoles: ['waiter'] },
      },
      {
        path: 'kitchen',
        name: 'KitchenWorkbench',
        component: KitchenWorkbench,
        meta: { requiresPermission: 'kitchen.view', staffRoles: ['kitchen'] },
      },
      { path: 'staff', name: 'StaffManage', component: StaffManage, meta: { requiresPermission: 'staff.manage' } },
      { path: 'entrance-codes', name: 'EntranceCodeList', component: EntranceCodeList, meta: ownerOnly },
      { path: 'channel-entries', name: 'ChannelEntryList', component: ChannelEntryList, meta: ownerOnly },
      { path: 'customers', name: 'CustomerList', component: CustomerList, meta: { requiresPermission: 'member.view' } },
      { path: 'customers/:id', name: 'CustomerDetail', component: CustomerDetail, meta: { requiresPermission: 'member.view' } },
      { path: 'consumptions', name: 'ConsumptionList', component: ConsumptionList, meta: { requiresPermission: 'member.view' } },
      { path: 'coupons', name: 'CouponCenter', component: CouponCenter, meta: { requiresPermission: 'marketing.view' } },
      { path: 'coupon-records', name: 'CouponRecords', component: CouponRecords, meta: { requiresPermission: 'marketing.view' } },
      { path: 'marketing-effectiveness', name: 'MarketingEffectiveness', component: MarketingEffectiveness, meta: { requiresPermission: 'marketing.view' } },
      { path: 'distribution', name: 'Distribution', component: Distribution, meta: ownerOnly },
      { path: 'staff-referral', name: 'StaffReferral', component: StaffReferral, meta: ownerOnly },
      { path: 'coupon-send', redirect: '/coupons' },
      { path: 'coupon-templates', redirect: '/coupons' },
      { path: 'verify', name: 'Verify', component: Verify, meta: ownerOnly },
      { path: 'orders', name: 'OrderManage', component: OrderManage, meta: ownerOnly },
      { path: 'admin/queue', name: 'QueueManage', component: QueueManage, meta: ownerOnly },
      { path: 'more', name: 'More', component: More },
      { path: 'menu', name: 'MenuManage', component: MenuManage, meta: ownerOnly },
      { path: 'membership', redirect: '/settings' },
      { path: 'plugins', redirect: '/settings' },
      { path: 'plugin/:code', name: 'PluginPlaceholder', component: PluginPlaceholder, meta: ownerOnly },
      { path: 'settings', name: 'MerchantSettings', component: MerchantSettings, meta: { requiresPermission: 'settings.store' } },
      { path: 'settings/business', name: 'BusinessSettings', component: BusinessSettings, meta: { requiresPermission: 'settings.store' } },
      { path: 'settings/payment', name: 'PaymentSettings', component: PaymentSettings, meta: { requiresPermission: 'settings.payment' } },
      { path: 'settings/devices', name: 'DeviceSettings', component: DeviceSettings, meta: { requiresPermission: 'settings.printer' } },
      { path: 'subscription', name: 'SubscriptionSettings', component: SubscriptionSettings, meta: ownerOnly },
      { path: 'settings/notifications', name: 'NotificationSettings', component: NotificationSettings, meta: ownerOnly },
      { path: 'settings/store', name: 'StoreSettings', component: StoreSettings, meta: { requiresPermission: 'settings.store' } },
      { path: 'wework-settings', name: 'WeworkSettings', component: WeworkSettings, meta: ownerOnly },
      { path: 'marketing-templates', redirect: '/coupons' },
      { path: 'marketing-templates/:id', redirect: '/coupons' },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

function homeForRole(role) {
  if (role === 'frontdesk') return '/frontdesk'
  if (role === 'waiter') return '/waiter'
  if (role === 'kitchen') return '/kitchen'
  return '/'
}

router.beforeEach((to) => {
  beginPageNavigation(to)
  return true
})

router.afterEach((to, _from, failure) => {
  completePageNavigation(to, failure)
})

router.beforeEach(async (to, from, next) => {
  const isLogin = to.path === '/login'
  const isOrder = to.path === '/order'
  const isSuper = to.path === '/super'
  const isH5 = to.path.startsWith('/h5/')
  const isQueueDisplay = to.path === '/queue/display'
  const isQueueStatus = to.path === '/queue/status'
  const auth = useAuthStore()

  if (isOrder || isSuper || isH5 || isQueueDisplay || isQueueStatus) {
    next()
    return
  }

  // Captured before ensureSession() -- which may attempt a silent trusted-
  // device refresh and, on failure, touch storage -- so the eventual
  // "was this ever a real session" decision below reflects what was
  // actually true when this navigation started, not a state ensureSession
  // could have already changed underneath it (avoids a race).
  const existingToken = getToken()
  const tokenWasExpired = Boolean(existingToken) && isTokenExpired(existingToken)

  let validSession = hasValidSession()
  if (!validSession && !isLogin) {
    validSession = await auth.ensureSession()
  }

  if (isSuper && validSession) {
    next('/')
    return
  }

  if (!isLogin && !validSession) {
    clearSession()
    // Only claim "session expired" when a token actually existed and its
    // own exp had passed -- an anonymous visitor who never had one (no
    // token at all) is not told their nonexistent session "expired".
    next({
      path: '/login',
      query: tokenWasExpired ? { reason: '登录已过期，请重新登录' } : {},
    })
    return
  }

  if (isLogin && validSession) {
    next(auth.homePath || homeForRole(auth.role))
    return
  }

  if (validSession) {
    if (!auth.loaded) {
      await auth.hydrateFromServer()
    }
    const required = to.meta?.requiresPermission
    if (required === '*' && !auth.isOwner) {
      next(homeForRole(auth.role))
      return
    }
    if (required && required !== '*' && !auth.can(required)) {
      next(homeForRole(auth.role))
      return
    }
    const staffRoles = to.meta?.staffRoles
    if (Array.isArray(staffRoles) && staffRoles.length && !auth.isOwner && !staffRoles.includes(auth.role)) {
      next(homeForRole(auth.role))
      return
    }
  }

  next()
})

export default router
