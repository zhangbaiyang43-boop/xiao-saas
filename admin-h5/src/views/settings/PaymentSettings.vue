<template>
  <div class="sub-page payment-page">
    <PageHeader title="微信支付" />
    <div class="page-body">
      <section class="safe-card">
        <div class="safe-head">
          <div>
            <p>收款安全</p>
            <h1>{{ statusText }}</h1>
          </div>
          <a-tag :class="['state-tag', statusClass]">{{ statusText }}</a-tag>
        </div>
        <div class="safe-copy">订单款项进入商家自己的微信支付商户号，收款账户已锁定，平台不能私自改成其他收款账户。</div>
      </section>

      <section class="info-card">
        <div class="info-row"><span class="info-label">收款主体</span><span class="info-value">{{ merchant.receiver_name || merchant.name || '-' }}</span></div>
        <div class="info-row"><span class="info-label">微信支付商户号</span><span class="info-value">{{ merchant.wx_mchid_masked || '-' }}</span></div>
        <div class="info-row"><span class="info-label">配置状态</span><span class="info-value">{{ statusText }}</span></div>
        <div class="info-row"><span class="info-label">最后验证时间</span><span class="info-value">{{ merchant.verified_time || '未验证' }}</span></div>
        <div class="info-row last"><span class="info-label">收款账户</span><span class="info-value lock">{{ merchant.payment_locked === false ? '未锁定' : '已锁定' }}</span></div>
      </section>

      <section class="plain-card">
        <strong>看不懂也没关系</strong>
        <span>微信支付由平台管理员在中控后台配置。商家后台只显示与你日常经营相关的收款状态。</span>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import PageHeader from '../../components/PageHeader.vue'
import { getTenantProfile } from '../../api'

const merchant = ref({})
const statusMap = { unconfigured: '未配置', pending: '待验证', verified: '已验证', paused: '暂停' }
const statusText = computed(() => statusMap[merchant.value.payment_status] || '未配置')
const statusClass = computed(() => `state-${merchant.value.payment_status || 'unconfigured'}`)

async function loadProfile() {
  try {
    const res = await getTenantProfile()
    if (res.code === 200 && res.data) merchant.value = res.data
  } catch { message.error('收款信息加载失败') }
}

onMounted(loadProfile)
</script>

<style scoped>
.payment-page { min-height: 100vh; background: #f5f6f8; }
.page-body { padding: 12px 16px 28px; }
.safe-card, .info-card, .plain-card { background: #fff; border: 1px solid #eef2f7; border-radius: 14px; }
.safe-card { padding: 16px; }
.safe-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.safe-head p, .safe-head h1 { margin: 0; }
.safe-head p { color: #16a34a; font-size: 12px; font-weight: 900; }
.safe-head h1 { margin-top: 5px; color: #111827; font-size: 22px; font-weight: 900; }
.safe-copy { margin-top: 12px; padding: 12px; border-radius: 10px; background: #f0fdf4; color: #15803d; font-size: 13px; line-height: 1.7; }
.state-tag { margin: 0; border-radius: 14px; font-size: 11px; font-weight: 800; }
.state-verified { color: #16a34a; background: #f0fdf4; border-color: #bbf7d0; }
.state-pending { color: #2563eb; background: #eff6ff; border-color: #bfdbfe; }
.state-paused { color: #6b7280; background: #f8fafc; border-color: #e5e7eb; }
.state-unconfigured { color: #92400e; background: #fffbeb; border-color: #fde68a; }
.info-card { margin-top: 12px; overflow: hidden; }
.info-row.last { border-bottom: 0; }
.lock { color: #16a34a !important; font-weight: 900; }
.plain-card { margin-top: 12px; padding: 14px; }
.plain-card strong, .plain-card span { display: block; }
.plain-card strong { color: #111827; font-size: 15px; font-weight: 900; }
.plain-card span { margin-top: 6px; color: #64748b; font-size: 13px; line-height: 1.6; }
</style>
