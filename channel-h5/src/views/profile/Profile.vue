<template>
  <main class="page">
    <div v-if="auth.isSuspended" class="suspended-tip">当前暂停新增商户，历史收益和结算不受影响。</div>
    <section class="card">
      <div class="item-title">{{ displayName }}</div>
      <div class="item-meta">手机号 {{ profile.mobile || '-' }}</div>
      <div class="item-meta">渠道编号 {{ profile.partner_code || '-' }}</div>
      <div v-if="displayPartnerType" class="item-meta">渠道类型 {{ displayPartnerType }}</div>
      <div class="item-meta">合作状态 {{ partnerStatusText(profile.status) }}</div>
    </section>

    <section class="card section">
      <div class="row rule"><span>软件服务费</span><strong>20%</strong></div>
      <div class="row rule"><span>最长</span><strong>36个月</strong></div>
      <div class="item-meta">商户付款后实时计佣</div>
      <div class="item-meta">T+7 可结算</div>
    </section>

    <section class="section">
      <button class="soft-button" type="button" @click="auth.logout">退出登录</button>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { partnerStatusText, partnerTypeText } from '../../utils/status'

const auth = useAuthStore()
const profile = computed(() => auth.profile || {})
const displayName = computed(() => {
  const value = String(profile.value.name || '').trim()
  return value && !['??', 'null', 'undefined', '-'].includes(value) ? value : '渠道伙伴'
})
const displayPartnerType = computed(() => partnerTypeText(profile.value.partner_type))

onMounted(() => {
  auth.refreshProfile()
})
</script>

<style scoped>
.rule {
  padding: 8px 0;
}
.rule strong {
  color: #ff5a1f;
}
</style>
