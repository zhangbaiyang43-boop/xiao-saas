<template>
  <div class="page-wrap">
    <div class="page-header">
      <span class="page-title">更多</span>
    </div>

    <!-- 店铺信息 -->
    <div style="padding:12px 16px 0">
      <a-card :bordered="false" style="cursor:pointer" @click="router.push('/settings')">
        <div style="display:flex;align-items:center;gap:14px">
          <div class="store-avatar">
            <ShopOutlined style="font-size:24px;color:#07C160" />
          </div>
          <div style="flex:1">
            <div style="font-size:16px;font-weight:800;color:#111">{{ merchant.name || '我的门店' }}</div>
            <div style="font-size:12px;color:#9ca3af;margin-top:2px">店铺资料 · 营业 · 打印 · 收银</div>
          </div>
          <RightOutlined style="color:#d1d5db" />
        </div>
      </a-card>
    </div>

    <!-- 核心经营 -->
    <div class="section-title">核心经营</div>
    <div style="padding:0 16px">
      <a-card :bordered="false" :body-style="{ padding: 0 }">
        <div v-for="(item, idx) in operationItems" :key="item.label" class="menu-item" :style="idx > 0 ? 'border-top:1px solid #f0f0f0' : ''" @click="router.push(item.path)">
          <div class="menu-icon" :style="{ background: item.bg }">
            <component :is="item.icon" :style="{ color: item.color, fontSize: '18px' }" />
          </div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:#111">{{ item.label }}</div>
            <div style="font-size:12px;color:#9ca3af;margin-top:1px">{{ item.desc }}</div>
          </div>
          <a-badge v-if="item.badge" :count="item.badge" style="margin-right:8px" />
          <RightOutlined style="color:#d1d5db;font-size:12px" />
        </div>
      </a-card>
    </div>

    <!-- 顾客增长 -->
    <div class="section-title">顾客增长</div>
    <div style="padding:0 16px">
      <a-card :bordered="false" :body-style="{ padding: 0 }">
        <div v-for="(item, idx) in marketingItems" :key="item.label" class="menu-item" :style="idx > 0 ? 'border-top:1px solid #f0f0f0' : ''" @click="router.push(item.path)">
          <div class="menu-icon" :style="{ background: item.bg }">
            <component :is="item.icon" :style="{ color: item.color, fontSize: '18px' }" />
          </div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:#111">{{ item.label }}</div>
            <div style="font-size:12px;color:#9ca3af;margin-top:1px">{{ item.desc }}</div>
          </div>
          <RightOutlined style="color:#d1d5db;font-size:12px" />
        </div>
      </a-card>
    </div>

    <!-- 系统设置 -->
    <div class="section-title">系统设置</div>
    <div style="padding:0 16px">
      <a-card :bordered="false" :body-style="{ padding: 0 }">
        <div class="menu-item" @click="router.push('/settings')">
          <div class="menu-icon" style="background:#f3f4f6"><SettingOutlined style="color:#6b7280;font-size:18px" /></div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:#111">店铺设置</div>
            <div style="font-size:12px;color:#9ca3af;margin-top:1px">营业时间 · 收银 API · 打印机 · 通知</div>
          </div>
          <RightOutlined style="color:#d1d5db;font-size:12px" />
        </div>
        <div class="menu-item" style="border-top:1px solid #f0f0f0" @click="logout">
          <div class="menu-icon" style="background:#fef2f2"><LogoutOutlined style="color:#ef4444;font-size:18px" /></div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:#ef4444">退出登录</div>
            <div style="font-size:12px;color:#fca5a5;margin-top:1px">退出当前商家后台</div>
          </div>
        </div>
      </a-card>
    </div>

    <div style="text-align:center;padding:24px 0 8px;font-size:12px;color:#d1d5db">技术支持：15936889988</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ShopOutlined, OrderedListOutlined, AppstoreOutlined, QrcodeOutlined, GiftOutlined, ScanOutlined, TeamOutlined, FileTextOutlined, SettingOutlined, LogoutOutlined, RightOutlined, FieldTimeOutlined } from '@ant-design/icons-vue'
import { getTenantProfile, getOrders } from '../api'
import { clearSession } from '../utils/session'

const router = useRouter()
const merchant = ref({ name: '' })
const pendingCount = ref(0)

function logout() { clearSession(); router.push('/login') }

const operationItems = computed(() => [
  { label: '接单管理', desc: '查看订单 · 接单 · 出餐 · 结账', path: '/orders', icon: OrderedListOutlined, bg: '#e8f9f0', color: '#07C160', badge: pendingCount.value },
  { label: '排位管理', desc: '取号、叫号、入座、过号', path: '/admin/queue', icon: FieldTimeOutlined, bg: '#fff7ed', color: '#f97316', badge: 0 },
  { label: '菜单管理', desc: '添加菜品、上下架控制', path: '/menu', icon: AppstoreOutlined, bg: '#eff6ff', color: '#2563eb', badge: 0 },
  { label: '桌码生成', desc: '每桌一个码，打印贴桌上', path: '/entrance-codes', icon: QrcodeOutlined, bg: '#f0fdfa', color: '#0d9488', badge: 0 },
])

const marketingItems = [
  { label: '优惠券管理', desc: '发券规则 · 领券活动', path: '/coupons', icon: GiftOutlined, bg: '#fdf4ff', color: '#9333ea' },
  { label: '扫码核销', desc: '顾客出示券码，扫码核销', path: '/verify', icon: ScanOutlined, bg: '#f5f3ff', color: '#7c3aed' },
  { label: '会员列表', desc: '查看所有会员及消费记录', path: '/customers', icon: TeamOutlined, bg: '#f0fdf4', color: '#16a34a' },
  // 核销记录页待迁移 Ant Design，暂隐藏避免风格割裂
  // { label: '核销记录', desc: '查看历史核销明细', path: '/coupon-records', icon: FileTextOutlined, bg: '#f8fafc', color: '#475569' },
]

onMounted(async () => {
  try { const r = await getTenantProfile(); if (r?.code === 200) merchant.value = { name: r.data?.name || '' } } catch {}
  try {
    const r = await getOrders({ date_str: 'today' })
    const raw = r?.data?.data || r?.data || []
    if (Array.isArray(raw)) pendingCount.value = raw.filter(o => o.status === 'pending').length
  } catch {}
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  padding: 52px 16px 12px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}
.page-title { font-size: 18px; font-weight: 700; color: #111; }

.store-avatar {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: #e8f9f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  transition: background .15s;
  &:active { background: #f9fafb; }
}

.menu-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
</style>


