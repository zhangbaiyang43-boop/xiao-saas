﻿﻿﻿﻿﻿<template>
  <div class="settings-home sub-page">
    <PageHeader title="设置" no-back>
      <a-button type="text" danger size="small" @click="handleLogout">退出</a-button>
    </PageHeader>

    <div class="page-body">
      <section class="store-card">
        <div class="store-main">
          <div class="store-icon"><ShopOutlined /></div>
          <div class="store-copy">
            <strong>{{ merchant.name || '商家名称' }}</strong>
            <span>{{ merchant.phone || '未填写手机号' }}</span>
          </div>
        </div>
        <button class="mini-btn" @click="router.push('/settings/store')">店铺资料</button>
      </section>

      <section class="hero-card">
        <div>
          <p>今日经营状态</p>
          <h1>{{ opSettings.is_open ? '正常营业中' : '当前休息中' }}</h1>
          <span>{{ operationSummary }}</span>
        </div>
        <button class="primary-btn" @click="router.push('/settings/business')">修改经营</button>
      </section>

      <div class="status-grid">
        <section class="status-card" @click="router.push('/settings/payment')">
          <div class="card-head">
            <div class="card-icon pay"><WalletOutlined /></div>
            <a-tag :class="['state-tag', wxpayStatusClass]">{{ wxpayStatusText }}</a-tag>
          </div>
          <h2>收款安全</h2>
          <p>{{ paymentSummary }}</p>
          <div class="card-row"><span>商户号</span><strong>{{ merchant.wx_mchid_masked || '-' }}</strong></div>
          <div class="lock-tip">收款账户已锁定</div>
        </section>

        <section class="status-card" @click="router.push('/settings/devices')">
          <div class="card-head">
            <div class="card-icon device"><PrinterOutlined /></div>
            <a-tag :class="printerConfig.configured ? 'tag-ok' : 'tag-warn'">{{ printerConfig.configured ? '已配置' : '未配置' }}</a-tag>
          </div>
          <h2>订单设备</h2>
          <p>{{ printerConfig.configured ? '订单可自动打印，排位小票可用' : '建议配置打印机，减少手工接单' }}</p>
          <div class="card-row"><span>打印机</span><strong>{{ printerStatusText }}</strong></div>
          <div class="card-row"><span>大屏</span><strong>{{ queueDisplayUrl ? '可用' : '待加载' }}</strong></div>
        </section>
      </div>

      <section class="menu-card">
        <div class="menu-title">常用设置</div>
        <div class="menu-item" @click="router.push('/settings/business')">
          <div><strong>经营方式</strong><span>营业时间、堂食、自提、外卖、备注</span></div>
          <RightOutlined />
        </div>
        <div class="menu-item" @click="router.push('/settings/payment')">
          <div><strong>微信支付</strong><span>查看收款主体、商户号、验证状态</span></div>
          <RightOutlined />
        </div>
        <div class="menu-item" @click="router.push('/settings/devices')">
          <div><strong>设备与收银</strong><span>打印机、排位小票、收银 API、碰一碰</span></div>
          <RightOutlined />
        </div>
        <div class="menu-item" @click="router.push('/settings/notifications')">
          <div><strong>通知提醒</strong><span>核销提醒、新会员提醒</span></div>
          <RightOutlined />
        </div>
      </section>

      <section class="menu-card quiet-card">
        <div class="menu-title">业务入口</div>
        <div class="quick-grid">
          <button v-for="item in businessItems" :key="item.path" @click="router.push(item.path)">
            <component :is="item.icon" />
            <span>{{ item.label }}</span>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Modal, message } from 'ant-design-vue'
import {
  AppstoreOutlined, ClusterOutlined, GiftOutlined, LinkOutlined, PrinterOutlined,
  QrcodeOutlined, RightOutlined, ShopOutlined, TeamOutlined, WalletOutlined,
} from '@ant-design/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { getPrinterConfig, getTenantProfile, logoutTenant } from '../api'
import { clearSession } from '../utils/session'

const router = useRouter()
const merchant = ref({})
const printerConfig = ref({ configured: false })
const opSettings = ref({ is_open: true, business_hours: '', dine_in_enabled: true, pickup_enabled: false, delivery_enabled: false })

const wxpayStatusMap = { unconfigured: '未配置', pending: '待验证', verified: '已验证', paused: '暂停' }
const wxpayStatusText = computed(() => wxpayStatusMap[merchant.value.payment_status] || '未配置')
const wxpayStatusClass = computed(() => `wxpay-${merchant.value.payment_status || 'unconfigured'}`)
const operationSummary = computed(() => {
  const modes = []
  if (opSettings.value.dine_in_enabled) modes.push('堂食')
  if (opSettings.value.pickup_enabled) modes.push('自提')
  if (opSettings.value.delivery_enabled) modes.push('外卖')
  return `${opSettings.value.business_hours || '未设置营业时间'} · ${modes.length ? modes.join('/') : '未开启点餐方式'}`
})
const paymentSummary = computed(() => {
  if (merchant.value.payment_status === 'verified') return `${merchant.value.receiver_name || merchant.value.name || '收款主体'} 已完成验证`
  if (merchant.value.payment_status === 'paused') return '微信支付已暂停，顾客暂不能在线支付'
  if (merchant.value.payment_status === 'pending') return '已保存配置，等待平台验证'
  return '还未配置微信支付收款信息'
})
const printerStatusText = computed(() => {
  if (!printerConfig.value.configured) return '未配置'
  return printerConfig.value.printer_provider === 'kuaimai' ? '快麦已配置' : '飞鹅云已配置'
})
const tenantId = computed(() => merchant.value.tenant_id || merchant.value.id || '')
const publicBaseUrl = computed(() => (import.meta.env.VITE_PUBLIC_BASE_URL || window.location.origin).replace(/\/$/, ''))
const queueDisplayUrl = computed(() => tenantId.value ? `${publicBaseUrl.value}/queue/display?tenant_id=${encodeURIComponent(tenantId.value)}` : '')

const businessItems = [
  { label: '桌码', path: '/entrance-codes', icon: QrcodeOutlined },
  { label: '领券页', path: '/channel-entries', icon: LinkOutlined },
  { label: '优惠券', path: '/coupons', icon: GiftOutlined },
  { label: '分销', path: '/distribution', icon: ClusterOutlined },
  { label: '会员', path: '/customers', icon: TeamOutlined },
  { label: '菜单', path: '/menu', icon: AppstoreOutlined },
]

async function loadData() {
  try {
    const [profileRes, printerRes] = await Promise.allSettled([getTenantProfile(), getPrinterConfig()])
    if (profileRes.status === 'fulfilled' && profileRes.value.code === 200) {
      const data = profileRes.value.data || {}
      merchant.value = data
      opSettings.value = {
        is_open: data.is_open ?? true,
        business_hours: data.business_hours || '',
        dine_in_enabled: data.dine_in_enabled ?? true,
        pickup_enabled: data.pickup_enabled ?? false,
        delivery_enabled: data.delivery_enabled ?? false,
      }
    }
    if (printerRes.status === 'fulfilled' && printerRes.value.code === 200) printerConfig.value = printerRes.value.data || { configured: false }
  } catch {
    message.error('设置加载失败')
  }
}

function handleLogout() {
  Modal.confirm({
    title: '退出登录',
    content: '确认退出当前商家后台吗？',
    okText: '退出',
    okType: 'danger',
    onOk: async () => { try { await logoutTenant() } catch {} finally { clearSession(); router.replace('/login') } },
  })
}

onMounted(loadData)
</script>

<style scoped>
.settings-home { min-height: 100vh; background: #f5f6f8; }
.page-body { padding: 12px 16px 28px; }
.store-card, .hero-card, .status-card, .menu-card { background: #fff; border-radius: 14px; border: 1px solid #eef2f7; }
.store-card { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px; }
.store-main { display: flex; align-items: center; gap: 12px; min-width: 0; }
.store-icon { width: 48px; height: 48px; border-radius: 14px; background: #07c160; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 24px; flex-shrink: 0; }
.store-copy { min-width: 0; }
.store-copy strong, .store-copy span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.store-copy strong { color: #111827; font-size: 17px; font-weight: 900; }
.store-copy span { margin-top: 4px; color: #64748b; font-size: 12px; }
.mini-btn { height: 34px; border: 1px solid #bbf7d0; color: #16a34a; background: #f0fdf4; border-radius: 8px; padding: 0 12px; font-weight: 800; }
.hero-card { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 12px; padding: 16px; }
.hero-card p, .hero-card h1, .hero-card span { display: block; margin: 0; }
.hero-card p { color: #16a34a; font-size: 12px; font-weight: 900; }
.hero-card h1 { margin-top: 5px; color: #111827; font-size: 22px; font-weight: 900; letter-spacing: 0; }
.hero-card span { margin-top: 6px; color: #64748b; font-size: 12px; line-height: 1.5; }
.primary-btn { height: 42px; border: 0; border-radius: 10px; background: #07c160; color: #fff; padding: 0 16px; font-weight: 900; flex-shrink: 0; }
.status-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.status-card { padding: 14px; cursor: pointer; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-icon { width: 38px; height: 38px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 21px; }
.card-icon.pay { color: #16a34a; background: #f0fdf4; }
.card-icon.device { color: #f97316; background: #fff7ed; }
.status-card h2 { margin: 12px 0 0; color: #111827; font-size: 16px; font-weight: 900; }
.status-card p { min-height: 38px; margin: 6px 0 12px; color: #64748b; font-size: 12px; line-height: 1.55; }
.card-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding-top: 8px; border-top: 1px solid #f1f5f9; font-size: 12px; }
.card-row + .card-row { margin-top: 8px; }
.card-row span { color: #94a3b8; }
.card-row strong { color: #111827; font-weight: 800; }
.lock-tip { margin-top: 10px; padding: 8px 10px; border-radius: 10px; background: #f0fdf4; color: #15803d; font-size: 12px; font-weight: 800; }
.state-tag, .tag-ok, .tag-warn { margin: 0; border-radius: 12px; font-size: 11px; font-weight: 800; }
.wxpay-verified, .tag-ok { color: #16a34a; background: #f0fdf4; border-color: #bbf7d0; }
.wxpay-pending { color: #2563eb; background: #eff6ff; border-color: #bfdbfe; }
.wxpay-paused { color: #6b7280; background: #f8fafc; border-color: #e5e7eb; }
.wxpay-unconfigured, .tag-warn { color: #92400e; background: #fffbeb; border-color: #fde68a; }
.menu-card { margin-top: 12px; overflow: hidden; }
.menu-title { padding: 14px 14px 4px; color: #111827; font-size: 15px; font-weight: 900; }
.menu-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px; border-top: 1px solid #f1f5f9; cursor: pointer; }
.menu-item strong, .menu-item span { display: block; }
.menu-item strong { color: #111827; font-size: 14px; font-weight: 800; }
.menu-item span { margin-top: 4px; color: #64748b; font-size: 12px; line-height: 1.4; }
.quiet-card { margin-bottom: 0; }
.quick-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 12px 14px 14px; }
.quick-grid button { height: 64px; border: 1px solid #eef2f7; border-radius: 12px; background: #f8fafc; color: #111827; font-weight: 800; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; }
.quick-grid button span { font-size: 12px; }
@media (max-width: 390px) {
  .status-grid { grid-template-columns: 1fr; }
  .hero-card { align-items: flex-start; flex-direction: column; }
  .primary-btn { width: 100%; }
}
</style>
