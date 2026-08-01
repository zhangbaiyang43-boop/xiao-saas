<template>
  <div class="settings-home sub-page">
    <PageHeader title="设置" no-back>
      <a-button type="text" danger size="small" @click="handleLogout">退出</a-button>
    </PageHeader>

    <div class="page-body">
      <section class="store-card animate-in">
        <div class="store-main">
          <div class="store-icon"><ShopOutlined /></div>
          <div class="store-copy">
            <strong>{{ merchant.name || '商家名称' }}</strong>
            <span>{{ merchant.phone || '未填写手机号' }}</span>
            <span class="store-op-line">{{ opSettings.is_open ? '营业中' : '休息中' }} · {{ operationSummary }}</span>
          </div>
        </div>
        <button class="mini-btn" @click="router.push('/settings/store')">店铺资料</button>
      </section>

      <!-- 常用设置：唯一的配置入口层，"未配置/待处理"用条目上的小标签提示，
           不再像之前那样单独叠一层状态卡片重复展示同一件事。 -->
      <section class="menu-card animate-in" style="animation-delay:.04s">
        <div class="menu-title">常用设置</div>
        <div class="menu-item" @click="router.push('/settings/business')">
          <div><strong>经营方式</strong><span>营业时间、堂食、自提、外卖、备注</span></div>
          <RightOutlined />
        </div>
        <div class="menu-item" @click="router.push('/settings/payment')">
          <div>
            <strong>微信支付<a-tag v-if="wxpayStatusText !== '已验证'" :class="['inline-tag', wxpayStatusClass]">{{ wxpayStatusText }}</a-tag></strong>
            <span>查看收款主体、商户号、验证状态</span>
          </div>
          <RightOutlined />
        </div>
        <div class="menu-item" @click="router.push('/settings/devices')">
          <div>
            <strong>设备与收银<a-tag v-if="!printerConfig.configured" class="inline-tag tag-warn">未配置打印机</a-tag></strong>
            <span>打印机、排位小票、收银 API、碰一碰</span>
          </div>
          <RightOutlined />
        </div>
        <div class="menu-item" @click="router.push('/settings/notifications')">
          <div><strong>通知提醒</strong><span>核销提醒、新会员提醒</span></div>
          <RightOutlined />
        </div>
      </section>

      <!-- 补充入口：只放"更多"页没有专门入口的功能，避免跟"更多"页重复。
           分销是获客功能，已经挪到"更多"页顾客增长区了，这里不重复放——
           剩下两项都是低频配置类工具，改用跟"常用设置"一致的列表样式，
           不再用宫格（宫格暗示"高频快捷操作"，跟它们的实际使用频率不符）。 -->
      <section class="menu-card animate-in" style="animation-delay:.08s">
        <div class="menu-title">其它工具</div>
        <div v-for="item in businessItems" :key="item.path" class="menu-item" @click="router.push(item.path)">
          <div><strong>{{ item.label }}</strong><span>{{ item.desc }}</span></div>
          <RightOutlined />
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
  LinkOutlined, RightOutlined, ShopOutlined, WechatOutlined,
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
const wxpayStatusClass = computed(() => merchant.value.payment_status === 'pending' ? 'tag-pending' : 'tag-warn')
const operationSummary = computed(() => {
  const modes = []
  if (opSettings.value.dine_in_enabled) modes.push('堂食')
  if (opSettings.value.pickup_enabled) modes.push('自提')
  if (opSettings.value.delivery_enabled) modes.push('外卖')
  return `${opSettings.value.business_hours || '未设置营业时间'} · ${modes.length ? modes.join('/') : '未开启点餐方式'}`
})

// 业务入口只保留"更多"页没有专门菜单项的功能（桌码/优惠券/分销/会员/菜单在"更多"页已有入口，不重复放）
const businessItems = [
  { label: '领券页', path: '/channel-entries', icon: LinkOutlined, desc: '生成链接/海报，分享给顾客领券' },
  { label: '企业微信', path: '/wework-settings', icon: WechatOutlined, desc: '对接企业微信，管理客户联系' },
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
.settings-home { min-height: 100vh; background: var(--bg-page); }
.page-body { padding: 12px 16px 28px; }
.store-card, .menu-card { background: var(--bg-card); border-radius: 14px; border: 1px solid var(--border); }
.store-card { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px; }
.store-main { display: flex; align-items: center; gap: 12px; min-width: 0; }
.store-icon { width: 48px; height: 48px; border-radius: 14px; background: #07c160; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 24px; flex-shrink: 0; }
.store-copy { min-width: 0; }
.store-copy strong, .store-copy span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.store-copy strong { color: var(--text-1); font-size: 17px; font-weight: 900; }
.store-copy span { margin-top: 4px; color: var(--text-2); font-size: 12px; }
.store-op-line { color: var(--text-3) !important; }
.mini-btn { height: 34px; border: 1px solid #bbf7d0; color: #16a34a; background: var(--brand-light); border-radius: 8px; padding: 0 12px; font-weight: 800; }

.menu-card { margin-top: 12px; overflow: hidden; }
.menu-title { padding: 14px 14px 4px; color: var(--text-1); font-size: 15px; font-weight: 900; }
.menu-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px; border-top: 1px solid var(--border); cursor: pointer; transition: background .15s; }
.menu-item:active { background: var(--bg-page); }
.menu-item strong, .menu-item span { display: block; }
.menu-item strong { color: var(--text-1); font-size: 14px; font-weight: 800; display: flex; align-items: center; gap: 6px; }
.menu-item span { margin-top: 4px; color: var(--text-2); font-size: 12px; line-height: 1.4; }
.inline-tag { margin: 0; border-radius: 12px; font-size: 11px; font-weight: 800; line-height: 16px; padding: 0 6px; }
.tag-warn { color: #92400e; background: #fffbeb; border-color: #fde68a; }
.tag-pending { color: #2563eb; background: #eff6ff; border-color: #bfdbfe; }

</style>
