<template>
  <div class="sub-page notify-page">
    <PageHeader title="通知提醒" />
    <div class="page-body">
      <section class="summary-card animate-in">
        <p>消息提醒</p>
        <h1>{{ enabledCount }} 项已开启</h1>
        <span>只保留和日常经营强相关的提醒，减少打扰。</span>
      </section>
      <section class="panel-card animate-in" style="animation-delay:.04s">
        <div class="switch-row">
          <div><strong>核销提醒</strong><span>顾客用券后通知商家</span></div>
          <a-switch v-model:checked="notificationSettings.redeem" @change="saveNotifications" />
        </div>
        <div class="switch-row last">
          <div><strong>新会员提醒</strong><span>顾客扫码入会后通知商家</span></div>
          <a-switch v-model:checked="notificationSettings.newMember" @change="saveNotifications" />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import PageHeader from '../../components/PageHeader.vue'
import { getTenantProfile, updateTenantSettings } from '../../api'

const notificationSettings = ref({ redeem: true, newMember: true })
const enabledCount = computed(() => Number(notificationSettings.value.redeem) + Number(notificationSettings.value.newMember))

async function loadProfile() {
  try {
    const res = await getTenantProfile()
    if (res.code === 200 && res.data) {
      notificationSettings.value.redeem = res.data.notification_redeem ?? true
      notificationSettings.value.newMember = res.data.notification_new_member ?? true
    }
  } catch { message.error('通知设置加载失败') }
}
async function saveNotifications() {
  try {
    const res = await updateTenantSettings({ notification_redeem: notificationSettings.value.redeem, notification_new_member: notificationSettings.value.newMember })
    if (res.code === 200) { message.success('设置已保存'); return }
    message.error(res.msg || '保存失败')
  } catch { message.error('保存失败，请稍后再试') }
}

onMounted(loadProfile)
</script>

<style scoped>
.notify-page { min-height: 100vh; background: var(--bg-page); }
.page-body { padding: 12px 16px 28px; }
.summary-card, .panel-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--card-shadow); }
.summary-card { padding: 18px; }
.summary-card p, .summary-card h1, .summary-card span { display: block; margin: 0; }
.summary-card p { color: #7c3aed; font-size: 12px; font-weight: 900; }
.summary-card h1 { margin-top: 5px; color: var(--text-1); font-size: 22px; font-weight: 900; }
.summary-card span { margin-top: 6px; color: var(--text-2); font-size: 13px; }
.panel-card { margin-top: 12px; overflow: hidden; }
.switch-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border); }
.switch-row.last { border-bottom: 0; }
.switch-row strong, .switch-row span { display: block; }
.switch-row strong { color: var(--text-1); font-size: 14px; font-weight: 800; }
.switch-row span { margin-top: 3px; color: var(--text-2); font-size: 12px; }
</style>
