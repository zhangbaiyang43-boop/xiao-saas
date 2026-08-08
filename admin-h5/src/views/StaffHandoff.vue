<template>
  <div class="handoff-page" referrerpolicy="no-referrer">
    <div class="card">
      <div class="mark">开</div>
      <h1>{{ title }}</h1>
      <p>{{ desc }}</p>
      <button v-if="failed" type="button" class="btn" @click="goLogin">返回登录</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { staffHandoffLogin } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const title = ref('正在进入员工工作台…')
const desc = ref('请稍候')
const failed = ref(false)

function clearFragment() {
  try {
    window.history.replaceState(null, '', '/staff-handoff')
  } catch {
    /* ignore */
  }
}

function readTokenFromFragment() {
  const hash = String(window.location.hash || '')
  if (!hash.startsWith('#')) return ''
  const body = hash.slice(1)
  const params = new URLSearchParams(body.includes('=') ? body : `t=${body}`)
  return String(params.get('t') || '').trim()
}

function goLogin() {
  router.replace('/login?mode=staff')
}

onMounted(async () => {
  document.referrerPolicy = 'no-referrer'
  const token = readTokenFromFragment()
  clearFragment()
  if (!token) {
    failed.value = true
    title.value = '登录已失效'
    desc.value = '请返回微信重新进入'
    return
  }
  try {
    const res = await staffHandoffLogin({ handoff_token: token })
    if (res?.code === 200 && res?.data?.token) {
      auth.applySession(res.data)
      const home = res.data.home_path || (res.data.role === 'kitchen' ? '/kitchen' : '/waiter')
      router.replace(home)
      return
    }
    failed.value = true
    title.value = '登录已失效'
    desc.value = res?.msg || '请返回微信重新进入'
  } catch (e) {
    failed.value = true
    title.value = '登录已失效'
    desc.value = e?.response?.data?.msg || '请返回微信重新进入'
  }
})
</script>

<style scoped>
.handoff-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: #f5f7fb;
}
.card {
  width: 100%;
  max-width: 360px;
  text-align: center;
  background: #fff;
  border-radius: 16px;
  padding: 32px 20px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}
.mark {
  width: 56px;
  height: 56px;
  margin: 0 auto 12px;
  border-radius: 16px;
  background: #07c160;
  color: #fff;
  font-size: 24px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
h1 {
  margin: 0 0 8px;
  font-size: 18px;
  color: #0f172a;
}
p {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}
.btn {
  margin-top: 20px;
  width: 100%;
  border: none;
  border-radius: 12px;
  padding: 12px;
  background: #334155;
  color: #fff;
  font-size: 15px;
}
</style>
