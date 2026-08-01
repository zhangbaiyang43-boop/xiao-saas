<template>
  <div class="page-wrap">
    <div class="page-header">
      <span class="page-title">更多</span>
    </div>

    <!-- 店铺信息 -->
    <div class="section-block animate-in">
      <a-card :bordered="false" class="tap-shrink" style="cursor:pointer" @click="router.push('/settings')">
        <div style="display:flex;align-items:center;gap:14px">
          <div class="store-avatar">
            <ShopOutlined style="font-size:24px;color:#07C160" />
          </div>
          <div style="flex:1">
            <div style="font-size:16px;font-weight:800;color:var(--text-1)">{{ merchant.name || '我的门店' }}</div>
            <div style="font-size:12px;color:var(--text-3);margin-top:2px">店铺资料 · 营业 · 打印 · 收银</div>
          </div>
          <RightOutlined style="color:var(--text-3)" />
        </div>
      </a-card>
    </div>

    <!-- 桌码生成：全店最高频的入口（新开桌、贴纸损坏都要重来），单独抽成一张
         强调卡片，不跟下面的常规列表条目同一视觉权重，一眼就能看出这是第一优先级。 -->
    <div class="section-block animate-in" style="animation-delay:.02s">
      <a-card :bordered="false" class="highlight-card tap-shrink" style="cursor:pointer" @click="router.push('/entrance-codes')">
        <div style="display:flex;align-items:center;gap:14px">
          <div class="highlight-icon">
            <QrcodeOutlined style="font-size:24px;color:#0d9488" />
          </div>
          <div style="flex:1">
            <div style="font-size:16px;font-weight:800;color:var(--text-1)">桌码生成</div>
            <div style="font-size:12px;color:var(--text-3);margin-top:2px">每桌一个码，打印贴桌上，顾客扫码点餐</div>
          </div>
          <RightOutlined style="color:var(--text-3)" />
        </div>
      </a-card>
    </div>

    <!-- 核心经营：只放 tab 栏没有的功能，"接单""菜单"已经是底部 tab，这里不重复 -->
    <div class="section-title">核心经营</div>
    <div class="page-body animate-in" style="animation-delay:.04s">
      <a-card :bordered="false" :body-style="{ padding: 0 }">
        <div v-for="(item, idx) in operationItems" :key="item.label" class="menu-item tap-shrink" :style="idx > 0 ? 'border-top:1px solid var(--border)' : ''" @click="router.push(item.path)">
          <div class="menu-icon" :style="{ background: item.bg }">
            <component :is="item.icon" :style="{ color: item.color, fontSize: '18px' }" />
          </div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:var(--text-1)">{{ item.label }}</div>
            <div style="font-size:12px;color:var(--text-3);margin-top:1px">{{ item.desc }}</div>
          </div>
          <RightOutlined style="color:var(--text-3);font-size:12px" />
        </div>
      </a-card>
    </div>

    <!-- 顾客增长 -->
    <div class="section-title">顾客增长</div>
    <div class="page-body animate-in" style="animation-delay:.08s">
      <a-card :bordered="false" :body-style="{ padding: 0 }">
        <div v-for="(item, idx) in marketingItems" :key="item.label" class="menu-item tap-shrink" :style="idx > 0 ? 'border-top:1px solid var(--border)' : ''" @click="router.push(item.path)">
          <div class="menu-icon" :style="{ background: item.bg }">
            <component :is="item.icon" :style="{ color: item.color, fontSize: '18px' }" />
          </div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:var(--text-1)">{{ item.label }}</div>
            <div style="font-size:12px;color:var(--text-3);margin-top:1px">{{ item.desc }}</div>
          </div>
          <RightOutlined style="color:var(--text-3);font-size:12px" />
        </div>
      </a-card>
    </div>

    <!-- 系统设置 -->
    <div class="section-title">系统设置</div>
    <div class="page-body animate-in" style="animation-delay:.12s">
      <a-card :bordered="false" :body-style="{ padding: 0 }">
        <div class="menu-item tap-shrink" @click="router.push('/settings')">
          <div class="menu-icon" style="background:var(--bg-page)"><SettingOutlined style="color:var(--text-2);font-size:18px" /></div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:var(--text-1)">店铺设置</div>
            <div style="font-size:12px;color:var(--text-3);margin-top:1px">营业时间 · 收银 API · 打印机 · 通知</div>
          </div>
          <RightOutlined style="color:var(--text-3);font-size:12px" />
        </div>
        <div class="menu-item tap-shrink" style="border-top:1px solid var(--border)" @click="logout">
          <div class="menu-icon" style="background:#fef2f2"><LogoutOutlined style="color:#ef4444;font-size:18px" /></div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:500;color:#ef4444">退出登录</div>
            <div style="font-size:12px;color:#fca5a5;margin-top:1px">退出当前商家后台</div>
          </div>
        </div>
      </a-card>
    </div>

    <div style="text-align:center;padding:24px 0 8px;font-size:12px;color:var(--text-3)">技术支持：15936889988</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ShopOutlined, QrcodeOutlined, GiftOutlined, ClusterOutlined, TeamOutlined, SettingOutlined, LogoutOutlined, RightOutlined, FieldTimeOutlined, UsergroupAddOutlined } from '@ant-design/icons-vue'
import { getTenantProfile } from '../api'
import { clearSession } from '../utils/session'

const router = useRouter()
const merchant = ref({ name: '' })

function logout() { clearSession(); router.push('/login') }

// 接单管理、菜单管理已经是底部 tab 栏的常驻入口，这里不重复放。
// 桌码生成是全店最高频功能，已经抽成上面独立的强调卡片，这里不再重复。
const operationItems = computed(() => [
  { label: '排位管理', desc: '取号、叫号、入座、过号', path: '/admin/queue', icon: FieldTimeOutlined, bg: '#fff7ed', color: '#f97316' },
])

// 扫码核销已并入支付流程，只剩极少数手动场景，收进优惠券管理页的"高级设置"
// 二级入口了，这里不再放一个平级的顶层导航项。
const marketingItems = [
  { label: '优惠券管理', desc: '发券规则 · 领券活动', path: '/coupons', icon: GiftOutlined, bg: '#fdf4ff', color: '#9333ea' },
  { label: '分销', desc: '老带新奖励，分销员管理', path: '/distribution', icon: ClusterOutlined, bg: '#eff6ff', color: '#2563eb' },
  { label: '员工推荐', desc: '员工/亲友带客佣金', path: '/staff-referral', icon: UsergroupAddOutlined, bg: '#fff7ed', color: '#ea580c' },
  { label: '会员列表', desc: '查看所有会员及消费记录', path: '/customers', icon: TeamOutlined, bg: '#f0fdf4', color: '#16a34a' },
]

onMounted(async () => {
  try { const r = await getTenantProfile(); if (r?.code === 200) merchant.value = { name: r.data?.name || '' } } catch {}
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  padding: 52px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.page-title { font-size: 18px; font-weight: 700; color: var(--text-1); }

.store-avatar {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: var(--brand-light);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.highlight-card { border: 1px solid #99f6e4 !important; background: #f0fdfa; }
.highlight-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: #ccfbf1;
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
  &:active { background: var(--bg-page); }
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
