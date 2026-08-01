import { createRouter, createWebHistory } from 'vue-router'
import { clearSession, hasValidSession } from '../utils/session'

const Login = () => import('../views/Login.vue')
const Layout = () => import('../views/Layout.vue')
const Dashboard = () => import('../views/Dashboard.vue')
const CustomerList = () => import('../views/CustomerList.vue')
const CustomerDetail = () => import('../views/CustomerDetail.vue')
const ConsumptionList = () => import('../views/ConsumptionList.vue')
const CouponCenter = () => import('../views/CouponCenter.vue')
const CouponRecords = () => import('../views/CouponRecords.vue')
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
// H5Order.vue（/h5/:shopId）已下线：这是早期独立于 dining_session/participant_token
// 体系之外的匿名点餐入口，下的单没有任何身份凭证可供后续接口校验归属。正式点餐
// 走小程序（member-mini-client）的桌台扫码流程，不要重新挂载这个路由。

const routes = [
  { path: '/login', name: 'Login', component: Login },
  { path: '/order', name: 'OrderPage', component: OrderPage },
  { path: '/super', name: 'SuperAdmin', component: SuperAdmin },
  { path: '/queue/display', name: 'QueueDisplay', component: QueueDisplay },
  { path: '/queue/status', name: 'QueueStatus', component: QueueStatus },
  {
    path: '/',
    name: 'Layout',
    component: Layout,
    children: [
      { path: '', name: 'Dashboard', component: Dashboard },
      { path: 'entrance-codes', name: 'EntranceCodeList', component: EntranceCodeList },
      { path: 'channel-entries', name: 'ChannelEntryList', component: ChannelEntryList },
      { path: 'customers', name: 'CustomerList', component: CustomerList },
      { path: 'customers/:id', name: 'CustomerDetail', component: CustomerDetail },
      { path: 'consumptions', name: 'ConsumptionList', component: ConsumptionList },
      { path: 'coupons', name: 'CouponCenter', component: CouponCenter },
      { path: 'coupon-records', name: 'CouponRecords', component: CouponRecords },
      { path: 'distribution', name: 'Distribution', component: Distribution },
      { path: 'staff-referral', name: 'StaffReferral', component: StaffReferral },
      { path: 'coupon-send', redirect: '/coupons' },
      { path: 'coupon-templates', redirect: '/coupons' },
      { path: 'verify', name: 'Verify', component: Verify },
      { path: 'orders', name: 'OrderManage', component: OrderManage },
      { path: 'admin/queue', name: 'QueueManage', component: QueueManage },
      { path: 'more', name: 'More', component: More },
      { path: 'menu', name: 'MenuManage', component: MenuManage },
      { path: 'membership', redirect: '/settings' },
      { path: 'plugins', redirect: '/settings' },
      { path: 'plugin/:code', name: 'PluginPlaceholder', component: PluginPlaceholder },
      { path: 'settings', name: 'MerchantSettings', component: MerchantSettings },
      { path: 'settings/business', name: 'BusinessSettings', component: BusinessSettings },
      { path: 'settings/payment', name: 'PaymentSettings', component: PaymentSettings },
      { path: 'settings/devices', name: 'DeviceSettings', component: DeviceSettings },
      { path: 'settings/notifications', name: 'NotificationSettings', component: NotificationSettings },
      { path: 'settings/store', name: 'StoreSettings', component: StoreSettings },
      { path: 'wework-settings', name: 'WeworkSettings', component: WeworkSettings },
      { path: 'marketing-templates', redirect: '/coupons' },
      { path: 'marketing-templates/:id', redirect: '/coupons' }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const isLogin = to.path === '/login'
  const isOrder = to.path === '/order'
  const isSuper = to.path === '/super'
  const isH5 = to.path.startsWith('/h5/')
  const isQueueDisplay = to.path === '/queue/display'
  const isQueueStatus = to.path === '/queue/status'
  const validSession = hasValidSession()

  if (isSuper && validSession) {
    next('/')
    return
  }

  if (isOrder || isSuper || isH5 || isQueueDisplay || isQueueStatus) {
    next()
    return
  }

  if (!isLogin && !validSession) {
    clearSession()
    next({ path: '/login', query: { reason: '\u767b\u5f55\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u767b\u5f55' } })
    return
  }

  if (isLogin && validSession) {
    next('/')
    return
  }

  next()
})

export default router
