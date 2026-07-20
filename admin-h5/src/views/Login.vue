<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand-top">
        <div class="brand-icon"><ShopOutlined style="font-size:28px;color:#fff" /></div>
        <h1>开心点单商家后台</h1>
        <p>登录后管理菜单、订单、收款和门店配置</p>
      </div>

      <a-alert
        v-if="route.query.reason"
        :message="route.query.reason"
        type="error"
        show-icon
        closable
        style="margin:0 20px 12px;border-radius:8px"
      />

      <div style="padding:16px 20px">
        <div style="margin-bottom:12px">
          <input
            ref="phoneInputRef"
            v-model="loginForm.phone"
            class="native-input"
            type="tel"
            placeholder="请输入商家手机号"
            maxlength="11"
            autocomplete="tel"
          />
          <div v-if="phoneError" style="color:#ff4d4f;font-size:12px;margin-top:4px">{{ phoneError }}</div>
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
              class="code-btn"
              :disabled="codeSending || codeCountdown > 0"
              @click="handleSendCode"
            >
              {{ codeButtonText }}
            </button>
          </div>
          <div v-if="codeError" style="color:#ff4d4f;font-size:12px;margin-top:4px">{{ codeError }}</div>
        </div>
        <div class="hint-card">
          <strong>没有账号？</strong>
          <span>账号由平台统一开通。手机号不存在时，请联系服务商：15936889988。</span>
        </div>
        <button class="submit-btn" :disabled="loading" @click="handleLogin" style="margin-top:16px">
          {{ loading ? '登录中...' : '登录进入后台' }}
        </button>
      </div>

      <div style="height:max(24px, env(safe-area-inset-bottom))" />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ShopOutlined } from '@ant-design/icons-vue'
import { login, sendLoginCode } from '../api'
import { saveSession } from '../utils/session'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const codeSending = ref(false)
const codeCountdown = ref(0)
const loginForm = ref({ phone: '', code: '' })
const phoneError = ref('')
const codeError = ref('')
let countdownTimer = null

const isPhone = v => /^1\d{10}$/.test(v || '')
const supportMessage = '账号不存在，请联系服务商：15936889988'

const codeButtonText = computed(() => {
  if (codeCountdown.value > 0) return `${codeCountdown.value}s后重发`
  return codeSending.value ? '发送中...' : '获取验证码'
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
  saveSession(data)
  message.success(msg)
  setTimeout(() => router.replace('/'), 350)
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

onBeforeUnmount(clearCountdown)
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
  background: #fff;
  box-shadow: 0 12px 40px rgba(0,0,0,.08);
  overflow: hidden;
}

.brand-top {
  padding: 32px 24px 20px;
  text-align: center;
  background: var(--hero-bg);
  color: #fff;
}

.brand-icon {
  width: 60px;
  height: 60px;
  border-radius: 18px;
  background: rgba(255,255,255,.2);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.brand-top h1 {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 900;
  color: #fff;
}

.brand-top p {
  margin: 0;
  font-size: 13px;
  color: rgba(255,255,255,.75);
}

.native-input {
  width: 100%;
  height: 44px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 0 14px;
  font-size: 15px;
  outline: none;
  box-sizing: border-box;
  background: #fff;
  color: #111;
  &:focus { border-color: #07C160; box-shadow: 0 0 0 2px rgba(7,193,96,.1); }
}

.code-input { padding-right: 104px; }

.code-btn {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  min-width: 82px;
  height: 30px;
  border-radius: 15px;
  border: none;
  background: #f0fff6;
  color: #07C160;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  padding: 0 10px;
}
.code-btn:disabled { opacity: .55; cursor: not-allowed; }
.submit-btn {
  width: 100%;
  height: 48px;
  background: #07C160;
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  &:disabled { opacity: .7; cursor: not-allowed; }
  &:active { opacity: .9; }
}
.hint-card {
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--brand-light);
  color: #9a3412;
  margin-top: 8px;
  strong, span { display: block; }
  strong { font-size: 13px; font-weight: 700; }
  span { font-size: 12px; margin-top: 3px; }
}
</style>