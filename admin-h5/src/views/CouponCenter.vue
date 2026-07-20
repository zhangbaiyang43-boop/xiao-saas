<template>
  <div class="coupon-page">

    <!-- 顶部：系统运行状态 -->
    <section class="hero-card">
      <div class="hero-left">
        <div class="hero-badge">自动运行中</div>
        <h1>智能营销已为你开启</h1>
        <p>系统根据你的客单价自动计算券的门槛和面额，顾客感觉赚了，你实际多卖了。</p>
      </div>
      <div class="hero-stats">
        <div class="stat-item">
          <span class="stat-num">{{ preview.issued_this_month ?? '—' }}</span>
          <span class="stat-label">本月已发券</span>
        </div>
        <div class="stat-item">
          <span class="stat-num">{{ preview.aov ? ('¥' + preview.aov) : '计算中' }}</span>
          <span class="stat-label">你的客单价</span>
        </div>
      </div>
    </section>

    <!-- 三个自动则卡片 -->
    <section class="panel">
      <div class="section-header">
        <div>
          <p class="section-eyebrow">全自动</p>
          <h2>三种发券时机</h2>
        </div>
      </div>
      <p class="section-tip">门槛和面额由系统按你的客单价实时计算，每次发券前自动匹配最合适的档位。</p>

      <div class="rule-list">
        <article v-for="card in ruleCards" :key="card.key" class="rule-card" :class="{ disabled: !preview[card.key]?.enabled }">
          <div class="rule-head">
            <div class="rule-icon" :class="card.theme">
              <van-icon :name="card.icon" />
            </div>
            <div class="rule-meta">
              <h3>{{ card.title }}</h3>
              <p>{{ card.desc }}</p>
            </div>
            <van-switch
              :model-value="preview[card.key]?.enabled ?? true"
              size="24px"
              :loading="togglingKey === card.key"
              @change="(v) => toggleRule(card.key, v)"
            />
          </div>

          <!-- 加权档位只读展示 -->
          <div v-if="preview[card.key]?.weighted_coupons?.length" class="tiers">
            <div
              v-for="(tier, i) in preview[card.key].weighted_coupons"
              :key="i"
              class="tier-chip"
              :class="tierClass(i)"
            >
              <span class="tier-name">{{ tier.name }}</span>
              <span class="tier-val">满{{ tier.threshold }}减{{ tier.amount }}</span>
              <span class="tier-prob">{{ tier.weight }}% 概率</span>
            </div>
          </div>

          <!-- 无历史订单兜底提示 -->
          <div v-else-if="!preview.aov" class="no-data-tip">
            <van-icon name="info-o" />
            <span>收到5单后系统自动计算门槛，现在用默认参数运行</span>
          </div>

          <div class="rule-footer">
            <span class="footer-tag">顾客随机看到不同券 · 保持新鲜感</span>
            <span class="footer-tag green">商家成本可控</span>
          </div>
        </article>
      </div>
    </section>

    <!-- 手动建券区：给有特殊需求的商家 -->
    <section class="panel">
      <div class="section-header">
        <div>
          <p class="section-eyebrow">可选</p>
          <h2>手动建券</h2>
        </div>
        <van-button plain size="small" type="primary" @click="router.push('/coupon-records')">发券记录</van-button>
      </div>
      <p class="section-tip">节假日促销、特定活动可手动建券，与系统自动券互不影响。</p>
      <div class="quick-actions">
        <van-button round plain type="primary" @click="openCreate('new_customer_coupon')">建新客券</van-button>
        <van-button round plain type="primary" @click="openCreate('consumption_coupon')">建复购券</van-button>
        <van-button round plain type="primary" @click="openCreate('recall_coupon')">建召回券</van-button>
      </div>
    </section>

    <!-- 已建的券列表 -->
    <section class="panel">
      <div class="section-header">
        <div>
          <p class="section-eyebrow">活动券</p>
          <h2>已建的券</h2>
        </div>
      </div>
      <div v-if="loadingTemplates" class="empty-state">加载中…</div>
      <div v-else-if="templates.length === 0" class="empty-state">还没有手动建券，系统自动券已在运行。</div>
      <div v-else class="template-list">
        <article v-for="item in templates" :key="item.id" class="template-card">
          <div class="coupon-face">
            <strong>¥{{ money(item.value) }}</strong>
            <span>满{{ money(item.min_amount) }}用</span>
          </div>
          <div class="coupon-info">
            <h3>{{ item.name }}</h3>
            <p>库存 {{ item.total_stock - item.used_stock }}/{{ item.total_stock }}</p>
            <p>{{ formatDate(item.end_time) }} 到期</p>
          </div>
          <span class="status-pill" :class="{ off: item.status !== 1 }">{{ item.status === 1 ? '上架' : '下架' }}</span>
        </article>
      </div>
    </section>

    <!-- 手动建券弹窗 -->
    <van-popup v-model:show="showForm" round position="bottom" :style="{ maxHeight: '90vh' }">
      <div class="form-sheet">
        <h2>建一张券</h2>
        <van-cell-group inset>
          <van-field v-model="form.name" label="券名称" placeholder="例如：国庆特惠券" />
          <van-field v-model.number="form.value" type="number" label="减多少钱" placeholder="例如：5" />
          <van-field v-model.number="form.min_amount" type="number" label="满多少能用" placeholder="例如：30" />
          <van-field v-model.number="form.total_stock" type="number" label="发多少张" placeholder="例如：100" />
          <van-field v-model.number="form.valid_days" type="number" label="几天内有效" placeholder="例如：7" />
        </van-cell-group>
        <van-button class="save-btn" type="primary" block round :loading="savingForm" @click="saveTemplate">
          建并上架
        </van-button>
      </div>
    </van-popup>

  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showFailToast, showSuccessToast } from 'vant'
import {
  createCouponTemplate,
  getCouponTemplates,
  getMarketingPreview,
  getTenantSettings,
  updateTenantSettings,
} from '../api'

const router = useRouter()

// ── 则卡片配置 ──────────────────────────────────────────
const ruleCards = [
  {
    key: 'new_customer_coupon',
    title: '新客券',
    desc: '首次下单后系统自动送一张，门槛略低于客单价，让新客觉得赚到了。',
    icon: 'friends-o',
    theme: 'green',
  },
  {
    key: 'consumption_coupon',
    title: '复购券',
    desc: '每次下单后自动推送下次用的券，门槛贴近客单价，自然带动回头。',
    icon: 'shop-o',
    theme: 'blue',
  },
  {
    key: 'recall_coupon',
    title: '老客召回券',
    desc: '7天没来的顾客，系统自动发券提醒，唤回沉睡客户。',
    icon: 'replay',
    theme: 'orange',
  },
]

// ── 状态 ────────────────────────────────────────────────
const preview = ref({})           // 来自 /marketing-preview 的系统计算结果
const templates = ref([])
const loadingTemplates = ref(false)
const togglingKey = ref(null)     // 正在切换开关的 rule key
const showForm = ref(false)
const savingForm = ref(false)

const form = reactive({ name: '', value: 5, min_amount: 30, total_stock: 100, valid_days: 7 })

// ── 数据加载 ─────────────────────────────────────────────
async function loadPreview() {
  try {
    const res = await getMarketingPreview()
    preview.value = res?.data?.data || res?.data || {}
  } catch {
    // 加载失败不阻断页面
  }
}

async function loadTemplates() {
  loadingTemplates.value = true
  try {
    const res = await getCouponTemplates({ page: 1, page_size: 100 })
    const data = res?.data?.data || res?.data || []
    templates.value = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []
  } catch {
    showFailToast('优惠券加载失败')
  } finally {
    loadingTemplates.value = false
  }
}

// ── 开关切换（只保存 enabled 字段） ──────────────────────
async function toggleRule(key, enabled) {
  togglingKey.value = key
  try {
    await updateTenantSettings({ coupon_rules: { [key]: { enabled } } })
    if (preview.value[key]) preview.value[key].enabled = enabled
  } catch {
    showFailToast('开关更新失败')
  } finally {
    togglingKey.value = null
  }
}

// ── 手动建券 ──────────────────────────────────────────────
const ruleDefaults = {
  new_customer_coupon: { name: '新客专享券', value: 5, min_amount: 25, valid_days: 3 },
  consumption_coupon:  { name: '下次专享券', value: 5, min_amount: 30, valid_days: 7 },
  recall_coupon:       { name: '回来有礼券', value: 8, min_amount: 40, valid_days: 7 },
}

function openCreate(ruleKey) {
  const d = ruleDefaults[ruleKey] || {}
  // 如果系统已有计算值，优先用系统值作为预填
  const sys = preview.value[ruleKey]
  const wc = sys?.weighted_coupons
  Object.assign(form, {
    name: d.name,
    value: (wc?.[1]?.amount ?? sys?.amount ?? d.value),
    min_amount: (wc?.[1]?.threshold ?? sys?.threshold ?? d.min_amount),
    total_stock: 100,
    valid_days: (wc?.[1]?.valid_days ?? d.valid_days),
  })
  showForm.value = true
}

async function saveTemplate() {
  if (!form.name) { showFailToast('请填写券名称'); return }
  savingForm.value = true
  try {
    const now = new Date()
    const end = new Date(now.getTime() + Number(form.valid_days || 7) * 86400000)
    await createCouponTemplate({
      name: form.name,
      type: 'FIXED',
      value: Number(form.value || 0),
      min_amount: Number(form.min_amount || 0),
      total_stock: Number(form.total_stock || 100),
      start_time: now.toISOString(),
      end_time: end.toISOString(),
      status: 1,
    })
    showSuccessToast('券已建上架')
    showForm.value = false
    loadTemplates()
  } catch {
    showFailToast('建失败，请重试')
  } finally {
    savingForm.value = false
  }
}

// ── 工具函数 ─────────────────────────────────────────────
function tierClass(i) {
  return ['tier-low', 'tier-mid', 'tier-high'][i] || 'tier-low'
}

function money(v) {
  const n = Number(v || 0)
  return Number.isInteger(n) ? n : n.toFixed(1)
}

function formatDate(v) {
  if (!v) return '-'
  const d = new Date(v)
  return isNaN(d.getTime()) ? '-' : `${d.getMonth() + 1}/${d.getDate()}`
}

onMounted(() => { loadPreview(); loadTemplates() })
</script>

<style scoped>
.coupon-page {
  min-height: 100vh;
  padding: 12px 12px 84px;
  background: #f5f6fa;
  color: #111827;
}

/* ── 顶部状态卡 ─────────────────── */
.hero-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  margin-bottom: 12px;
  border-radius: 18px;
  background: linear-gradient(135deg, #07C160 0%, #06a550 100%);
  color: #fff;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,.2);
  font-size: 12px;
  font-weight: 700;
}
.hero-badge::before {
  content: '';
  display: block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #fff;
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0%,100% { opacity: 1 } 50% { opacity: .4 }
}
.hero-left h1 { font-size: 20px; margin: 0 0 6px; }
.hero-left p  { font-size: 13px; opacity: .85; margin: 0; line-height: 1.5; }
.hero-stats {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex-shrink: 0;
  text-align: right;
}
.stat-num   { display: block; font-size: 22px; font-weight: 900; }
.stat-label { display: block; font-size: 11px; opacity: .8; }

/* ── 通用面 ───────────────────── */
.panel {
  background: #fff;
  border-radius: 18px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,.04);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.section-eyebrow { margin: 0 0 4px; color: #07C160; font-size: 12px; font-weight: 700; }
.section-header h2 { margin: 0; font-size: 20px; }
.section-tip {
  margin: 0 0 14px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

/* ── 则卡片 ───────────────────── */
.rule-list { display: grid; gap: 10px; }
.rule-card {
  padding: 14px;
  border: 1.5px solid #e5e7eb;
  border-radius: 16px;
  transition: opacity .2s;
}
.rule-card.disabled { opacity: .55; }

.rule-head {
  display: grid;
  grid-template-columns: 44px 1fr auto;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.rule-icon {
  display: grid; place-items: center;
  width: 44px; height: 44px;
  border-radius: 14px;
  color: #fff;
  font-size: 22px;
  flex-shrink: 0;
}
.rule-icon.green  { background: #10b981; }
.rule-icon.blue   { background: #3b82f6; }
.rule-icon.orange { background: #f59e0b; }

.rule-meta h3 { margin: 0 0 3px; font-size: 17px; }
.rule-meta p  { margin: 0; color: #64748b; font-size: 12px; line-height: 1.5; }

/* ── 加权档位展示 ────────────────── */
.tiers { display: grid; gap: 8px; margin-bottom: 10px; }
.tier-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 13px;
}
.tier-low  { background: #f0fdf4; border: 1px solid #bbf7d0; }
.tier-mid  { background: #eff6ff; border: 1px solid #bfdbfe; }
.tier-high { background: #fefce8; border: 1px solid #fde68a; }
.tier-name { flex: 1; font-weight: 600; color: #374151; }
.tier-val  { color: #374151; font-weight: 700; }
.tier-prob { margin-left: auto; color: #9ca3af; font-size: 12px; flex-shrink: 0; }

.no-data-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
  margin-bottom: 10px;
}

.rule-footer {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 6px;
}
.footer-tag {
  padding: 3px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
}
.footer-tag.green {
  background: #ecfdf5;
  color: #059669;
}

/* ── 快速建券 ───────────────────── */
.quick-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

/* ── 已建券列表 ────────────────── */
.template-list { display: grid; gap: 10px; }
.template-card {
  display: grid;
  grid-template-columns: 90px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid #eef2f7;
  border-radius: 14px;
}
.coupon-face {
  display: grid; place-items: center;
  min-height: 72px;
  border-radius: 12px;
  background: linear-gradient(135deg, #ff4d4f, #ff7a45);
  color: #fff;
}
.coupon-face strong { font-size: 22px; }
.coupon-face span   { font-size: 11px; }
.coupon-info h3 { margin: 0 0 4px; font-size: 16px; }
.coupon-info p  { margin: 0; color: #64748b; font-size: 12px; line-height: 1.6; }

.status-pill {
  padding: 4px 8px;
  border-radius: 999px;
  background: #ecfdf5;
  color: #059669;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.status-pill.off { background: #f1f5f9; color: #64748b; }

/* ── 空状态 ─────────────────────── */
.empty-state {
  padding: 28px 12px;
  border-radius: 14px;
  background: #f8fafc;
  color: #64748b;
  text-align: center;
  font-size: 14px;
}

/* ── 建券弹窗 ───────────────────── */
.form-sheet { padding: 18px 12px 32px; }
.form-sheet h2 { padding: 0 8px 14px; font-size: 20px; }
.save-btn { margin-top: 16px; }

@media (max-width: 380px) {
  .quick-actions { grid-template-columns: 1fr; }
  .template-card { grid-template-columns: 80px 1fr auto; }
  .hero-card { flex-direction: column; }
}
</style>
