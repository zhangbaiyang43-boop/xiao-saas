<template>
  <div class="activation-home">
    <div class="ah-header">
      <div class="ah-brand">开心点单</div>
      <div class="ah-trial">{{ trialText }}</div>
    </div>

    <template v-if="status.activated">
      <div class="ah-success animate-in">
        <div class="ah-success-icon">🎉</div>
        <h2>开店成功</h2>
        <p>第一笔订单已收到</p>
        <button class="ah-primary-btn tap-shrink" @click="router.push('/orders')">进入订单</button>
      </div>
    </template>

    <template v-else>
      <h1 class="ah-title">开店只差 3 步</h1>

      <div class="ah-step tap-shrink" :class="{ done: status.has_dishes }" @click="router.push('/menu')">
        <div class="ah-step-num">{{ status.has_dishes ? '✓' : '1' }}</div>
        <div class="ah-step-body">
          <div class="ah-step-title">添加一道菜</div>
          <div class="ah-step-sub">{{ status.has_dishes ? '已完成' : '只需菜名和价格' }}</div>
        </div>
        <div class="ah-step-cta">{{ status.has_dishes ? '' : '去添加' }}</div>
      </div>

      <div class="ah-step tap-shrink" :class="{ done: status.has_entrance_codes }" @click="router.push('/entrance-codes')">
        <div class="ah-step-num">{{ status.has_entrance_codes ? '✓' : '2' }}</div>
        <div class="ah-step-body">
          <div class="ah-step-title">生成一个桌码</div>
          <div class="ah-step-sub">{{ status.has_entrance_codes ? '已完成' : '一键生成，无需打印即可扫码测试' }}</div>
        </div>
        <div class="ah-step-cta">{{ status.has_entrance_codes ? '' : '去生成' }}</div>
      </div>

      <div
        class="ah-step tap-shrink"
        :class="{ disabled: !readyForStep3 }"
        @click="readyForStep3 && startTestOrder()"
      >
        <div class="ah-step-num">3</div>
        <div class="ah-step-body">
          <div class="ah-step-title">手机扫码试单</div>
          <div class="ah-step-sub">{{ readyForStep3 ? '用另一台手机扫码，提交一笔真实订单' : '完成前两步后开始' }}</div>
        </div>
        <div class="ah-step-cta">{{ readyForStep3 ? '开始试单' : '' }}</div>
      </div>

      <div v-if="showScanPanel" class="ah-scan-panel animate-in">
        <img v-if="testQrUrl" :src="testQrUrl" alt="桌码二维码" class="ah-qr" />
        <p v-else class="ah-scan-fallback">去「桌码」页面查看这张码的二维码</p>
        <ol class="ah-scan-steps">
          <li>用另一台手机扫这个码（或截图后用微信「扫一扫」）——不用先打印</li>
          <li>添加刚才创建的菜品</li>
          <li>提交订单，回到这里看结果</li>
        </ol>
      </div>
    </template>

    <button class="ah-skip" @click="router.push('/')">进入后台</button>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getActivationStatus, getCurrentSubscription, getEntranceCodes } from '../api'

const router = useRouter()
const status = ref({ has_dishes: false, has_entrance_codes: false, has_orders: false, activated: false })
const trialText = ref('免费试用 30 天')
const showScanPanel = ref(false)
const testQrUrl = ref('')

const readyForStep3 = computed(() => status.value.has_dishes && status.value.has_entrance_codes)

const resolveAssetUrl = (url) => {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return `${import.meta.env.VITE_API_ORIGIN || 'https://api.zhangbaiyang.com'}${url}`
}

async function loadStatus() {
  try {
    const res = await getActivationStatus()
    if (res?.code === 200 && res.data) status.value = res.data
  } catch {
    // keep defaults -- Activation Home degrading to "step 1" is safe,
    // never blocking (the skip CTA is always available regardless)
  }
}

async function loadTrial() {
  try {
    const res = await getCurrentSubscription()
    if (res?.code === 200 && res.data?.is_trial) {
      trialText.value = `专业版试用中 · 剩余${res.data.days_remaining ?? 0}天`
    }
  } catch {
    // keep the static "免费试用 30 天" fallback copy
  }
}

async function startTestOrder() {
  showScanPanel.value = true
  if (testQrUrl.value) return
  try {
    const res = await getEntranceCodes({ page: 1, page_size: 20 })
    const raw = res?.data
    const list = Array.isArray(raw) ? raw : (raw?.items || raw?.results || raw?.data || [])
    const tableCode = list.find(
      (c) => (c.entry_type === 'table' || c.channel === 'TABLE') && c.status !== 0 && c.image_url
    )
    if (tableCode) testQrUrl.value = resolveAssetUrl(tableCode.image_url)
  } catch {
    // fallback copy ("去桌码页面查看") already covers this
  }
}

onMounted(() => {
  loadStatus()
  loadTrial()
})
</script>

<style scoped>
.activation-home {
  min-height: 100vh;
  padding: 24px 20px max(24px, env(safe-area-inset-bottom));
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ah-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ah-brand { font-size: 18px; font-weight: 700; color: var(--text-1); }
.ah-trial { font-size: 12px; color: #64748b; }
.ah-title { font-size: 20px; font-weight: 700; margin: 4px 0 4px; color: var(--text-1); }
.ah-step {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-card);
  border-radius: 16px;
  padding: 16px;
  box-shadow: var(--card-shadow);
  cursor: pointer;
}
.ah-step.disabled { opacity: .5; cursor: default; }
.ah-step.done { border: 1px solid #07C160; }
.ah-step-num {
  width: 32px; height: 32px; border-radius: 50%;
  background: #f1f5f9; color: #475569;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; flex-shrink: 0;
}
.ah-step.done .ah-step-num { background: #07C160; color: #fff; }
.ah-step-body { flex: 1; min-width: 0; }
.ah-step-title { font-size: 15px; font-weight: 600; color: var(--text-1); }
.ah-step-sub { font-size: 12px; color: #64748b; margin-top: 2px; }
.ah-step-cta { font-size: 13px; font-weight: 600; color: #07C160; white-space: nowrap; }
.ah-scan-panel {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 20px;
  text-align: center;
  box-shadow: var(--card-shadow);
}
.ah-qr { width: 200px; height: 200px; object-fit: contain; margin: 0 auto 12px; display: block; }
.ah-scan-fallback { color: #64748b; font-size: 13px; margin-bottom: 12px; }
.ah-scan-steps {
  text-align: left;
  font-size: 13px;
  color: var(--text-1);
  line-height: 1.8;
  margin: 0;
  padding-left: 20px;
}
.ah-success {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
}
.ah-success-icon { font-size: 48px; }
.ah-success h2 { margin: 0; font-size: 22px; color: var(--text-1); }
.ah-success p { margin: 0 0 12px; color: #64748b; }
.ah-primary-btn {
  border: none;
  border-radius: 12px;
  padding: 13px 32px;
  background: #07C160;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}
.ah-skip {
  margin-top: auto;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 13px;
  padding: 12px;
  text-align: center;
}
</style>
