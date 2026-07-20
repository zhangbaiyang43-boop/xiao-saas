import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Layout from '../views/Layout.vue'
import Dashboard from '../views/Dashboard.vue'
import CustomerList from '../views/CustomerList.vue'
import CustomerDetail from '../views/CustomerDetail.vue'
import ConsumptionList from '../views/ConsumptionList.vue'
import CouponCenter from '../views/CouponCenter.vue'
import CouponRecords from '../views/CouponRecords.vue'
import Distribution from '../views/Distribution.vue'
import EntranceCodeList from '../views/EntranceCodeList.vue'
import ChannelEntryList from '../views/ChannelEntryList.vue'
import Verify from '../views/Verify.vue'
import PluginPlaceholder from '../views/PluginPlaceholder.vue'
import MerchantSettings from '../views/MerchantSettings.vue'
import BusinessSettings from '../views/settings/BusinessSettings.vue'
import PaymentSettings from '../views/settings/PaymentSettings.vue'
import DeviceSettings from '../views/settings/DeviceSettings.vue'
import NotificationSettings from '../views/settings/NotificationSettings.vue'
import StoreSettings from '../views/settings/StoreSettings.vue'
import WeworkSettings from '../views/WeworkSettings.vue'
import MenuManage from '../views/MenuManage.vue'
import OrderManage from '../views/OrderManage.vue'
import OrderPage from '../views/OrderPage.vue'
import QueueManage from '../views/QueueManage.vue'
import QueueDisplay from '../views/QueueDisplay.vue'
import QueueStatus from '../views/QueueStatus.vue'
import More from '../views/More.vue'
import SuperAdmin from '../views/SuperAdmin.vue'
import H5Order from '../views/H5Order.vue'
import { clearSession, hasValidSession } from '../utils/session'

const routes = [
  { path: '/login', name: 'Login', component: Login },
  { path: '/order', name: 'OrderPage', component: OrderPage },
  { path: '/super', name: 'SuperAdmin', component: SuperAdmin },
  { path: '/h5/:shopId', name: 'H5Order', component: H5Order },
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

  if (isOrder || isSuper || isH5 || isQueueDisplay || isQueueStatus) {
    next()
    return
  }

  if (!isLogin && !validSession) {
    clearSession()
    next({ path: '/login', query: { reason: '登录已过期，请重新登录' } })
    return
  }

  if (isLogin && validSession) {
    next('/')
    return
  }

  next()
})

export default router
