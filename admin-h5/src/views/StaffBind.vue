<template>
  <div class="bind-page">
    <div class="card">
      <template v-if="loading">
        <div class="muted">加载中…</div>
      </template>
      <template v-else-if="error">
        <div class="title">无法绑定</div>
        <div class="msg">{{ error }}</div>
        <button class="btn ghost" type="button" @click="goLogin">使用账号密码登录</button>
      </template>
      <template v-else-if="done">
        <div class="ok">✓ 微信绑定成功</div>
        <div class="msg">正在进入工作台…</div>
      </template>
      <template v-else>
        <div class="shop">{{ preview.shop_name }}</div>
        <div class="title">正在绑定员工身份</div>
        <div class="name">{{ preview.staff_name }}</div>
        <div class="role">{{ preview.role_label }}</div>
        <button class="btn" type="button" :disabled="binding" @click="confirm">
          {{ binding ? '绑定中…' : '确认绑定' }}
        </button>
        <div class="hint">仅用于员工身份识别</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  confirmStaffWechatBind,
  getStaffWechatOauthStart,
  getStaffWechatStatus,
  previewStaffWechatBind,
} from '../api'
import { useAuthStore } from '../stores/auth'
import {
  clearOauthAttempted,
  isWechatBrowser,
  markOauthAttempted,
  wasOauthAttemptedRecently,
} from '../utils/deviceAuth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const binding = ref(false)
const error = ref('')
const done = ref(false)
const mockAllowed = ref(false)
const preview = reactive({ shop_name: '', staff_name: '', role_label: '' })

function goLogin() {
  router.replace({ path: '/login', query: { mode: 'staff' } })
}

async function confirm() {
  binding.value = true
  try {
    const t = String(route.query.t || '')
    const sid = String(route.query.sid || '')
    const payload = { bind_token: t }
    if (sid) payload.session_id = sid
    // Local/dev mock path when OAuth session missing.
    if (!sid && mockAllowed.value) {
      payload.mock_openid = String(route.query.mock_openid || `staff_${Date.now()}`)
    }
    const res = await confirmStaffWechatBind(payload)
    if (res?.code !== 200 || !res.data?.token) {
      error.value = res?.msg || '绑定失败'
      return
    }
    clearOauthAttempted()
    auth.applySession(res.data)
    done.value = true
    setTimeout(() => {
      router.replace(res.data.home_path || auth.homePath || '/waiter')
    }, 600)
  } catch (e) {
    error.value = e?.response?.data?.msg || '绑定失败'
  } finally {
    binding.value = false
  }
}

onMounted(async () => {
  const t = String(route.query.t || '')
  if (!t) {
    error.value = '绑定码无效'
    loading.value = false
    return
  }

  try {
    const prev = await previewStaffWechatBind(t)
    if (prev?.code !== 200 || !prev.data?.ok) {
      error.value = prev?.msg || prev?.data?.msg || '绑定码已失效，请让老板重新生成'
      loading.value = false
      return
    }
    Object.assign(preview, prev.data)

    // If already have oauth session, show confirm page.
    if (route.query.sid) {
      loading.value = false
      return
    }

    // Start OAuth when in WeChat and not looping.
    const status = await getStaffWechatStatus()
    const cfg = status?.data || {}
    mockAllowed.value = !!cfg.mock_allowed
    if (isWechatBrowser() && (cfg.configured || cfg.mock_allowed) && !wasOauthAttemptedRecently()) {
      markOauthAttempted()
      const start = await getStaffWechatOauthStart({ purpose: 'bind', t })
      const url = start?.data?.authorize_url
      if (url) {
        window.location.href = url
        return
      }
    }

    if (!isWechatBrowser() && !cfg.mock_allowed) {
      error.value = '请在微信中打开此页面完成绑定'
      loading.value = false
      return
    }

    if (!route.query.sid && !cfg.mock_allowed) {
      error.value = '微信登录失败，请重新扫码或使用账号密码登录'
      loading.value = false
      return
    }

    loading.value = false
  } catch (e) {
    error.value = e?.response?.data?.msg || '加载失败'
    loading.value = false
  }
})
</script>

<style scoped>
.bind-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: linear-gradient(180deg, #f7f4ef 0%, #fff 55%);
}
.card {
  width: 100%;
  max-width: 360px;
  background: #fff;
  border-radius: 16px;
  padding: 28px 22px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
  text-align: center;
}
.shop { font-size: 14px; color: #888; margin-bottom: 8px; }
.title { font-size: 18px; font-weight: 700; margin-bottom: 12px; }
.name { font-size: 28px; font-weight: 700; }
.role { font-size: 15px; color: #666; margin: 6px 0 22px; }
.btn {
  width: 100%;
  height: 46px;
  border: 0;
  border-radius: 12px;
  background: #07c160;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}
.btn.ghost { background: #f3f3f3; color: #333; margin-top: 12px; }
.btn:disabled { opacity: 0.6; }
.hint { margin-top: 14px; font-size: 12px; color: #999; }
.msg { color: #666; margin: 10px 0 18px; line-height: 1.5; }
.ok { font-size: 22px; font-weight: 700; color: #07c160; }
.muted { color: #999; }
</style>
