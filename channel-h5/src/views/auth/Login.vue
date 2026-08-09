<template>
  <main class="login-page">
    <section class="login-panel">
      <div class="brand">开心点单</div>
      <h1>渠道伙伴</h1>
      <van-field v-model="mobile" type="tel" label="手机号" placeholder="请输入手机号" clearable />
      <van-field v-model="code" type="text" label="验证码" placeholder="请输入验证码" clearable>
        <template #button>
          <van-button size="small" type="primary" :disabled="sending || cooldown > 0" @click="sendCode">
            {{ cooldown > 0 ? `${cooldown}s` : '获取验证码' }}
          </van-button>
        </template>
      </van-field>
      <button class="strong-button" type="button" :disabled="loading" @click="submit">登录</button>
      <div v-if="debugCode" class="dev-code">测试验证码：{{ debugCode }}</div>
    </section>
  </main>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { showFailToast, showSuccessToast } from 'vant'
import { useRouter } from 'vue-router'
import { requestCode } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const mobile = ref('')
const code = ref('')
const loading = ref(false)
const sending = ref(false)
const cooldown = ref(0)
const debugCode = ref('')
let timer = null

function tick() {
  clearInterval(timer)
  timer = setInterval(() => {
    cooldown.value -= 1
    if (cooldown.value <= 0) clearInterval(timer)
  }, 1000)
}

async function sendCode() {
  if (!mobile.value.trim()) return showFailToast('请输入手机号')
  sending.value = true
  try {
    const res = await requestCode({ mobile: mobile.value.trim() })
    if (res.code !== 200) return showFailToast(res.msg || '验证码发送失败')
    cooldown.value = Number(res.data?.retry_after || 60)
    debugCode.value = import.meta.env.PROD ? '' : (res.data?.debug_code || '')
    tick()
    showSuccessToast('验证码已发送')
  } catch (error) {
    showFailToast(error.response?.data?.msg || '验证码发送失败')
  } finally {
    sending.value = false
  }
}

async function submit() {
  if (!mobile.value.trim() || !code.value.trim()) return showFailToast('请输入手机号和验证码')
  loading.value = true
  try {
    const res = await auth.login({ mobile: mobile.value.trim(), code: code.value.trim() })
    if (res.code !== 200) return showFailToast(res.msg || '登录失败')
    router.replace('/home')
  } catch (error) {
    showFailToast(error.response?.data?.msg || '登录失败')
  } finally {
    loading.value = false
  }
}

onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  padding: 42px 16px;
  background: #f6f7f9;
}
.login-panel {
  background: #fff;
  border-radius: 8px;
  padding: 22px 14px 18px;
}
.brand {
  color: #ff5a1f;
  font-weight: 800;
}
h1 {
  margin: 6px 0 22px;
  font-size: 28px;
}
.strong-button {
  margin-top: 18px;
}
.dev-code {
  margin-top: 12px;
  color: #76808f;
  font-size: 13px;
  text-align: center;
}
</style>
