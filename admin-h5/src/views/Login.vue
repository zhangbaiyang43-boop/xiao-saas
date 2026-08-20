<template>
  <div class="login-page">
    <div class="login-card animate-in">
      <div class="brand-top">
        <div class="brand-icon"><ShopOutlined style="font-size:28px;color:#fff" /></div>
        <h1>开心点单商家后台</h1>
        <p>老板验证码登录 · 员工账号密码登录</p>
      </div>

      <a-alert
        v-if="route.query.reason"
        :message="route.query.reason"
        type="error"
        show-icon
        closable
        style="margin:0 20px 12px;border-radius:10px"
      />

      <div class="mode-tabs mode-tabs--three">
        <button type="button" :class="{ active: mode === 'owner' }" @click="mode = 'owner'">老板登录</button>
        <button type="button" :class="{ active: mode === 'staff' }" @click="mode = 'staff'">员工登录</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <div v-if="mode === 'owner'" style="padding:8px 20px 16px">
        <div style="margin-bottom:12px">
          <input
            v-model="loginForm.phone"
            class="native-input"
            type="tel"
            placeholder="请输入商家手机号"
            maxlength="11"
            autocomplete="tel"
          />
          <div v-if="phoneError" class="field-error">{{ phoneError }}</div>
        </div>
        <div style="margin-bottom:12px">
          <div style="position:relative">
            <input
              v-model="loginForm.code"
              class="native-input code-input"
              type="text"
              placeholder="验证码"
              maxlength="6"
              autocomplete="one-time-code"
            />
            <button
              type="button"
              class="code-btn tap-shrink"
              :disabled="codeSending || codeCountdown > 0"
              @click="handleSendCode"
            >
              {{ codeButtonText }}
            </button>
          </div>
          <div v-if="codeError" class="field-error">{{ codeError }}</div>
        </div>
        <div class="hint-card">
          <strong>没有账号？</strong>
          <span>账号由平台统一开通。手机号不存在时，请联系服务商：15936889988。</span>
        </div>
        <button class="submit-btn tap-shrink" :disabled="loading" @click="handleLogin" style="margin-top:16px">
          {{ loading ? '登录中...' : '登录进入后台' }}
        </button>
      </div>

      <div v-else-if="mode === 'register'" style="padding:8px 20px 16px">
        <div style="margin-bottom:12px">
          <input
            v-model="registerForm.name"
            class="native-input"
            type="text"
            placeholder="请输入门店名称"
            maxlength="64"
          />
          <div v-if="registerNameError" class="field-error">{{ registerNameError }}</div>
        </div>
        <div style="margin-bottom:12px">
          <input
            v-model="registerForm.phone"
            class="native-input"
            type="tel"
            placeholder="请输入手机号"
            maxlength="11"
            autocomplete="tel"
          />
          <div v-if="registerPhoneError" class="field-error">
            {{ registerPhoneError }}
            <button
              v-if="registerPhoneAlreadyRegistered"
              type="button"
              class="inline-link-btn"
              @click="goToLoginWithPhone"
            >去登录</button>
          </div>
        </div>
        <div style="margin-bottom:12px">
          <div style="position:relative">
            <input
              v-model="registerForm.code"
              class="native-input code-input"
              type="text"
              placeholder="验证码"
              maxlength="6"
              autocomplete="one-time-code"
            />
            <button
              type="button"
              class="code-btn tap-shrink"
              :disabled="registerCodeSending || registerCodeCountdown > 0"
              @click="handleSendRegisterCode"
            >
              {{ registerCodeButtonText }}
            </button>
          </div>
          <div v-if="registerCodeError" class="field-error">{{ registerCodeError }}</div>
        </div>
        <div class="hint-card">
          <strong>免费试用 30 天</strong>
          <span>注册后自动开通专业版试用，先添加菜品、生成桌码，体验完整点餐流程。</span>
        </div>
        <button class="submit-btn tap-shrink" :disabled="loading" @click="handleRegister" style="margin-top:16px">
          {{ loading ? '注册中...' : '注册并进入后台' }}
        </button>
      </div>

      <div v-else style="padding:8px 20px 16px">
        <form class="staff-form" @submit.prevent="handleStaffLogin">
          <div style="margin-bottom:12px">
            <input v-model="staffForm.shop_phone" class="native-input" type="tel" placeholder="请输入门店手机号" maxlength="11" autocomplete="tel" />
          </div>
          <div style="margin-bottom:12px">
            <input v-model="staffForm.username" class="native-input" placeholder="请输入员工账号" autocomplete="username" />
          </div>
          <div style="margin-bottom:12px">
            <input v-model="staffForm.password" class="native-input" type="password" placeholder="请输入密码" autocomplete="current-password" />
          </div>
          <button type="submit" class="submit-btn tap-shrink" :disabled="loading" style="margin-top:8px;background:#334155">
            {{ loading ? '登录中...' : '登录' }}
          </button>
        </form>
      </div>

      <div style="height:max(24px, env(safe-area-inset-bottom))" />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ShopOutlined } from '@ant-design/icons-vue'
import {
  login,
  registerTenant,
  sendLoginCode,
  sendRegisterCode,
  staffLogin,
} from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const mode = ref(route.query.mode === 'staff' ? 'staff' : 'owner')
const loading = ref(false)
const codeSending = ref(false)
const codeCountdown = ref(0)
const loginForm = ref({ phone: '', code: '' })
const staffForm = ref({ shop_phone: '', username: '', password: '' })
const registerForm = ref({ name: '', phone: '', code: '' })
const phoneError = ref('')
const codeError = ref('')
const registerNameError = ref('')
const registerPhoneError = ref('')
const registerCodeError = ref('')
const registerPhoneAlreadyRegistered = ref(false)
const registerCodeSending = ref(false)
const registerCodeCountdown = ref(0)
let countdownTimer = null
let registerCountdownTimer = null

const isPhone = (v) => /^1\d{10}$/.test(v || '')
const supportMessage = '账号不存在，请联系服务商：15936889988'

const codeButtonText = computed(() => {
  if (codeCountdown.value > 0) return `${codeCountdown.value}s后重发`
  return codeSending.value ? '发送中...' : '获取验证码'
})

const registerCodeButtonText = computed(() => {
  if (registerCodeCountdown.value > 0) return `${registerCodeCountdown.value}s后重发`
  return registerCodeSending.value ? '发送中...' : '获取验证码'
})

const clearCountdown = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

const startCountdown = (seconds = 60) => {
  clearCountdown()
  codeCountdown.value = Number(seconds) || 60
  countdownTimer = setInterval(() => {
    codeCountdown.value -= 1
    if (codeCountdown.value <= 0) {
      codeCountdown.value = 0
      clearCountdown()
    }
  }, 1000)
}

const clearRegisterCountdown = () => {
  if (registerCountdownTimer) {
    clearInterval(registerCountdownTimer)
    registerCountdownTimer = null
  }
}

const startRegisterCountdown = (seconds = 60) => {
  clearRegisterCountdown()
  registerCodeCountdown.value = Number(seconds) || 60
  registerCountdownTimer = setInterval(() => {
    registerCodeCountdown.value -= 1
    if (registerCodeCountdown.value <= 0) {
      registerCodeCountdown.value = 0
      clearRegisterCountdown()
    }
  }, 1000)
}

const validatePhone = () => {
  phoneError.value = ''
  if (!loginForm.value.phone) {
    phoneError.value = '请输入手机号'
    return false
  }
  if (!isPhone(loginForm.value.phone)) {
    phoneError.value = '请输入正确的11位手机号'
    return false
  }
  return true
}

const handleSendCode = async () => {
  codeError.value = ''
  if (!validatePhone()) return
  codeSending.value = true
  try {
    const res = await sendLoginCode({ phone: loginForm.value.phone })
    if (res?.code === 200) {
      message.success(res?.msg || '验证码已发送')
      startCountdown(res?.data?.retry_after || 60)
      return
    }
    const msg = res?.msg || '验证码发送失败，请稍后再试'
    if (msg === supportMessage) phoneError.value = msg
    message.error(msg)
  } catch (e) {
    const msg = e?.response?.data?.msg || '验证码发送失败，请稍后再试'
    if (msg === supportMessage) phoneError.value = msg
    message.error(msg)
  } finally {
    codeSending.value = false
  }
}

const persistAndEnter = (data, msg) => {
  auth.applySession(data)
  message.success(msg)
  const home =
    data.home_path ||
    (data.role === 'frontdesk'
      ? '/frontdesk'
      : data.role === 'waiter'
        ? '/waiter'
        : data.role === 'kitchen'
          ? '/kitchen'
          : '/')
  setTimeout(() => router.replace(home), 350)
}

const handleLogin = async () => {
  codeError.value = ''
  if (!validatePhone()) return
  if (!loginForm.value.code) {
    codeError.value = '请输入验证码'
    return
  }
  loading.value = true
  try {
    const res = await login(loginForm.value)
    if (res?.code === 200 && res?.data?.token) {
      persistAndEnter(res.data, '登录成功')
      return
    }
    const msg = res?.msg || '登录失败，请检查手机号和验证码'
    if (msg === supportMessage) phoneError.value = msg
    message.error(msg)
  } catch (e) {
    const msg = e?.response?.data?.msg || '登录失败，网络异常'
    if (msg === supportMessage) phoneError.value = msg
    message.error(msg)
  } finally {
    loading.value = false
  }
}

const validateRegisterPhone = () => {
  registerPhoneError.value = ''
  registerPhoneAlreadyRegistered.value = false
  if (!registerForm.value.phone) {
    registerPhoneError.value = '请输入手机号'
    return false
  }
  if (!isPhone(registerForm.value.phone)) {
    registerPhoneError.value = '请输入正确的11位手机号'
    return false
  }
  return true
}

const applyRegisterError = (msg) => {
  const text = msg || '注册失败，请稍后重试'
  registerPhoneAlreadyRegistered.value = text.includes('已注册')
  if (registerPhoneAlreadyRegistered.value || text.includes('暂未开放')) {
    registerPhoneError.value = text
  } else if (text.includes('验证码')) {
    registerCodeError.value = text
  }
  message.error(text)
}

const goToLoginWithPhone = () => {
  loginForm.value.phone = registerForm.value.phone
  mode.value = 'owner'
}

const handleSendRegisterCode = async () => {
  registerCodeError.value = ''
  registerNameError.value = ''
  if (!registerForm.value.name || !registerForm.value.name.trim()) {
    registerNameError.value = '请输入门店名称'
    return
  }
  if (!validateRegisterPhone()) return
  registerCodeSending.value = true
  try {
    const res = await sendRegisterCode({ phone: registerForm.value.phone })
    if (res?.code === 200) {
      message.success(res?.msg || '验证码已发送')
      startRegisterCountdown(res?.data?.retry_after || 60)
      return
    }
    applyRegisterError(res?.msg)
  } catch (e) {
    applyRegisterError(e?.response?.data?.msg || '验证码发送失败，请稍后再试')
  } finally {
    registerCodeSending.value = false
  }
}

const handleRegister = async () => {
  registerNameError.value = ''
  registerCodeError.value = ''
  if (!registerForm.value.name || !registerForm.value.name.trim()) {
    registerNameError.value = '请输入门店名称'
    return
  }
  if (!validateRegisterPhone()) return
  if (!registerForm.value.code) {
    registerCodeError.value = '请输入验证码'
    return
  }
  loading.value = true
  try {
    const res = await registerTenant({
      name: registerForm.value.name.trim(),
      phone: registerForm.value.phone,
      code: registerForm.value.code,
    })
    if (res?.code === 200 && res?.data?.token) {
      auth.applySession(res.data)
      message.success('注册成功')
      setTimeout(() => router.replace('/activation'), 350)
      return
    }
    applyRegisterError(res?.msg)
  } catch (e) {
    applyRegisterError(e?.response?.data?.msg || '注册失败，网络异常')
  } finally {
    loading.value = false
  }
}

const handleStaffLogin = async () => {
  // Staff H5 password login is user-initiated only. Never auto-call /login/staff.
  const shop_phone = String(staffForm.value.shop_phone || '').trim()
  const username = String(staffForm.value.username || '').trim()
  const password = String(staffForm.value.password || '')

  if (!shop_phone) {
    message.error('请输入门店手机号')
    return
  }
  if (!isPhone(shop_phone)) {
    message.error('请输入正确的门店手机号')
    return
  }
  if (!username) {
    message.error('请输入员工账号')
    return
  }
  if (!password) {
    message.error('请输入密码')
    return
  }

  loading.value = true
  try {
    const res = await staffLogin({ shop_phone, username, password })
    if (res?.code === 200 && res?.data?.token) {
      persistAndEnter(res.data, '登录成功')
      return
    }
    message.error(res?.msg || '登录失败')
  } catch (e) {
    if (e?.code === 'STAFF_LOGIN_INCOMPLETE') {
      message.error('请输入员工账号和密码')
      return
    }
    message.error(e?.response?.data?.msg || '登录失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (route.query.mode === 'staff') {
    mode.value = 'staff'
  }
  // Trusted-device auto-login only. Never auto-start 公众号 OAuth.
  const ok = await auth.ensureSession()
  if (ok) {
    router.replace(auth.homePath || '/')
  }
})

onBeforeUnmount(clearCountdown)
onBeforeUnmount(clearRegisterCountdown)
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: var(--bg-page);
}
.login-card {
  width: 100%;
  max-width: 420px;
  border-radius: 20px;
  background: var(--bg-card);
  box-shadow: var(--card-shadow);
  overflow: hidden;
}
.brand-top {
  position: relative;
  padding: 32px 24px 20px;
  text-align: center;
  background: var(--hero-bg);
  color: #fff;
  overflow: hidden;
  isolation: isolate;
}
.brand-top h1 { margin: 12px 0 6px; font-size: 22px; }
.brand-top p { margin: 0; opacity: .9; font-size: 13px; }
.brand-icon {
  width: 56px; height: 56px; margin: 0 auto; border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.18);
}
.mode-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 20px 0;
}
.mode-tabs--three {
  grid-template-columns: 1fr 1fr 1fr;
}
.mode-tabs button {
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 10px;
  padding: 8px;
  font-size: 14px;
}
.inline-link-btn {
  border: none;
  background: transparent;
  color: #07C160;
  font-size: 12px;
  font-weight: 600;
  margin-left: 8px;
  padding: 0;
  text-decoration: underline;
}
.mode-tabs button.active {
  background: #07C160;
  border-color: #07C160;
  color: #fff;
  font-weight: 600;
}
.native-input {
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 15px;
  outline: none;
  box-sizing: border-box;
}
.code-input { padding-right: 110px; }
.code-btn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  border: none;
  background: transparent;
  color: #07C160;
  font-size: 13px;
}
.field-error { color: #ef4444; font-size: 12px; margin-top: 6px; }
.hint-card {
  background: #f8fafc;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}
.submit-btn {
  width: 100%;
  border: none;
  border-radius: 12px;
  padding: 13px;
  background: #07C160;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}
.submit-btn:disabled { opacity: .6; }
.divider {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #94a3b8;
  font-size: 12px;
  margin: 8px 0 14px;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #e2e8f0;
}
.staff-form { margin: 0; }
.shop-choices { margin-bottom: 14px; }
.shop-choice {
  width: 100%;
  text-align: left;
  border: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.shop-choice span { font-size: 12px; color: #64748b; }
</style>
