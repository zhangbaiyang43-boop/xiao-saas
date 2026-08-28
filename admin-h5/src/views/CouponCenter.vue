<template>
  <div class="coupon-page">
    <!-- 与同一营销流程内的 MarketingEffectiveness.vue、CouponRecords.vue 保持一致的
         导航层：这三个页面深度相同、都是从"更多"或 Dashboard 卡片进入的二级页，
         之前唯独这一页没有返回入口（Phase-04 PART_05 PageHeader 治理）。PageHeader
         必须在 .page-content 的内边距之外，跟两个姊妹页的结构完全一致。 -->
    <PageHeader title="智能营销" />

    <div class="page-content">
    <!-- 顶部：强度选择器，跟"今日"页是同一个决策，不是另一套系统 -->
    <section class="hero-card animate-in">
      <!-- "自动运行中"只在真正确认成功后才展示；加载中/失败必须说真话，不能预先
           假定系统在跑（Constitution §4、Phase-02 状态合同）。 -->
      <div v-if="previewLoaded && !previewError" class="hero-badge"><span class="live-dot"></span>自动运行中</div>
      <div v-else class="hero-badge hero-badge--unknown">{{ previewError ? '状态未知，请重试' : '状态确认中…' }}</div>
      <h1>智能营销已为你开启</h1>

      <div class="intensity-switch">
        <div
          v-for="opt in intensityOptions"
          :key="opt.key"
          class="intensity-pill tap-shrink"
          :class="{
            'intensity-pill--on': previewLoaded && !previewError && opt.key === currentIntensity,
            'intensity-pill--disabled': switchingIntensity || !previewLoaded || previewError,
          }"
          @click="switchIntensity(opt.key)"
        >{{ opt.label }}</div>
      </div>

      <div
        v-if="previewLoaded && !previewError"
        class="industry-row tap-shrink"
        :class="{ 'industry-row--unset': currentIndustry === 'default', 'industry-row--disabled': switchingIndustry }"
        @click="!switchingIndustry && (showIndustryPicker = true)"
      >
        <span class="industry-row-label">业态</span>
        <span class="industry-row-value">{{ industryText }}</span>
        <van-icon name="arrow" />
      </div>

      <p class="hero-desc">{{ heroDesc }}</p>

      <div v-if="previewLoaded && !previewError" class="hero-stat-row">
        <div class="hero-stat">
          <span class="stat-num">{{ preview.issued_this_month ?? 0 }}</span>
          <span class="stat-label">本月已发券</span>
        </div>
        <div class="hero-stat">
          <span class="stat-num">{{ redemptionRateText }}</span>
          <span class="stat-label">核销率（{{ preview.redeemed_this_month ?? 0 }}张已用）</span>
        </div>
      </div>
      <div v-else-if="previewError" class="hero-error-row">
        <span>营销状态加载失败</span>
        <van-button size="small" plain class="hero-retry-btn" @click="loadPreview">重试</van-button>
      </div>
    </section>

    <!-- 五种发券时机：只说明系统在做什么，不给参数、不给独立开关 -->
    <section class="panel animate-in" style="animation-delay:.04s">
      <div class="section-header">
        <div>
          <p class="section-eyebrow">全自动</p>
          <h2>五种发券时机</h2>
        </div>
      </div>

      <div class="rule-list">
        <article v-for="card in ruleCards" :key="card.key" class="rule-card">
          <div class="rule-head">
            <div class="rule-icon" :class="card.theme">
              <van-icon :name="card.icon" />
            </div>
            <div class="rule-meta">
              <h3>{{ card.title }}</h3>
              <p>{{ card.desc }}</p>
            </div>
          </div>
        </article>
      </div>

      <p class="section-tip">具体门槛和面额由算法根据你的客单价自动匹配，不需要你操心，绝不会让你亏本。</p>
    </section>

    <!-- 效果 + 系统调参：只在有数据时出现 -->
    <section
      v-if="previewLoaded && !previewError && (attributionReady || tuningLogText)"
      class="panel animate-in"
      style="animation-delay:.06s"
    >
      <div class="section-header">
        <div>
          <p class="section-eyebrow">近 30 天</p>
          <h2>发券效果</h2>
        </div>
      </div>

      <div v-if="attributionReady" class="effect-grid">
        <div class="effect-cell">
          <span class="effect-num">{{ repeatUsersText }}</span>
          <span class="effect-label">用券客人回头率</span>
        </div>
        <div class="effect-cell">
          <span class="effect-num">{{ repeatNonUsersText }}</span>
          <span class="effect-label">未用券客人回头率</span>
        </div>
        <div class="effect-cell">
          <span class="effect-num">¥{{ money(attribution.auto_discount_total) }}</span>
          <span class="effect-label">优惠成本</span>
        </div>
        <div class="effect-cell">
          <span class="effect-num">{{ roiText }}</span>
          <span class="effect-label">粗略 ROI</span>
        </div>
      </div>
      <p v-else class="section-tip">数据积累中，满足样本量后展示用券 vs 未用券的对比。</p>

      <p v-if="tuningLogText" class="section-tip effect-tuning">{{ tuningLogText }}</p>
    </section>

    <!-- 高级设置：给真的想自己管的商家，默认折叠，不占主视图 -->
    <van-collapse v-model="activeCollapse" class="advanced-collapse animate-in" style="animation-delay:.08s">
      <van-collapse-item title="高级设置" name="advanced">
        <div class="advanced-block">
          <div class="section-header">
            <div>
              <p class="section-eyebrow">可选</p>
              <h2>手动建券</h2>
            </div>
            <div style="display:flex;gap:8px">
              <van-button plain size="small" type="primary" @click="router.push('/verify')">扫码核销</van-button>
              <van-button plain size="small" type="primary" @click="router.push('/coupon-records')">发券记录</van-button>
            </div>
          </div>
          <p class="section-tip">核销已并入支付流程自动完成，扫码核销只用于极少数需要手动处理的场景。节假日促销、特定活动可手动建券，与系统自动券互不影响。</p>
          <div class="quick-actions">
            <van-button round plain type="primary" @click="openCreate('new_customer_coupon')">建新客券</van-button>
            <van-button round plain type="primary" @click="openCreate('consumption_coupon')">建复购券</van-button>
            <van-button round plain type="primary" @click="openCreate('recall_coupon')">建召回券</van-button>
          </div>
        </div>

        <div class="advanced-block">
          <div class="section-header">
            <div>
              <p class="section-eyebrow">活动券</p>
              <h2>已建的券</h2>
            </div>
          </div>
          <div v-if="loadingTemplates" class="empty-state">加载中…</div>
          <div v-else-if="templatesError" class="empty-state empty-state--error">
            加载失败，请重试
            <div style="margin-top:8px"><van-button size="small" plain type="primary" @click="loadTemplates">重试</van-button></div>
          </div>
          <div v-else-if="templates.length === 0" class="empty-state">还没有手动建券，需要时随时可以建一张。</div>
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
        </div>
      </van-collapse-item>
    </van-collapse>
    </div>

    <van-popup v-model:show="showIndustryPicker" position="bottom" round>
      <van-picker
        title="选择业态"
        :columns="industryColumns"
        @confirm="onIndustrySelect"
        @cancel="showIndustryPicker = false"
      />
    </van-popup>

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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showFailToast, showSuccessToast } from 'vant'
import PageHeader from '../components/PageHeader.vue'
import {
  createCouponTemplate,
  getCouponTemplates,
  getMarketingPreview,
  updateTenantSettings,
} from '../api'

const router = useRouter()

// ── 则卡片配置（只做说明，不再挂独立开关/参数） ────────────
const ruleCards = [
  {
    key: 'entry_coupon',
    title: '进店券',
    desc: '扫码进店当场抽一张，多数是加菜小券，少数抽中大额券，当日有效。',
    icon: 'shop-collect-o',
    theme: 'purple',
  },
  {
    key: 'new_customer_coupon',
    title: '新客券',
    desc: '首单后自动送一张，门槛低于客单价，21 天有效，留住下次。',
    icon: 'friends-o',
    theme: 'green',
  },
  {
    key: 'consumption_coupon',
    title: '复购券',
    desc: '每次结账后自动送下次用的券，常规小券保底，偶尔抽中大额回馈。',
    icon: 'shop-o',
    theme: 'blue',
  },
  {
    key: 'recall_coupon',
    title: '老客召回券',
    desc: '7 天没来的老客，自动发一张低门槛大额券唤回。',
    icon: 'replay',
    theme: 'orange',
  },
  {
    key: 'points_reward_coupon',
    title: '积分好礼券',
    desc: '顾客攒够积分自动兑换一张，面额比其他自动券更慷慨，奖励长期熟客。',
    icon: 'point-gift-o',
    theme: 'gold',
  },
]

const intensityOptions = [
  { key: 'conservative', label: '保守' },
  { key: 'standard', label: '标准' },
  { key: 'aggressive', label: '激进' },
]

// ── 状态 ────────────────────────────────────────────────
const preview = ref({})           // 来自 /marketing-preview 的系统计算结果
const previewLoaded = ref(false)  // 是否已经拿到一次确定结果（成功或失败）
const previewError = ref(false)   // 加载失败/无法确认，禁止假定"运行中"
const templates = ref([])
const loadingTemplates = ref(false)
const templatesError = ref(false)
const switchingIntensity = ref(false)
const showIndustryPicker = ref(false)
const switchingIndustry = ref(false)
const activeCollapse = ref([])
const showForm = ref(false)
const savingForm = ref(false)

const form = reactive({ name: '', value: 5, min_amount: 30, total_stock: 100, valid_days: 7 })

const currentIntensity = computed(() => preview.value?.intensity_outcomes?.current_intensity || 'standard')

// ── 业态：冷启动客单价"连菜单都没有"时的兜底来源，商家选一次即可 ──────
const industryOptions = computed(() => preview.value?.industry_options || [])
const currentIndustry = computed(() => preview.value?.industry || 'default')
const industryText = computed(() => {
  const opt = industryOptions.value.find((o) => o.key === currentIndustry.value)
  return opt ? opt.label : '未选择'
})
const industryColumns = computed(() => industryOptions.value.map((o) => ({ text: o.label, value: o.key })))

// ── 效果 / 归因 ──────────────────────────────────────────
const attribution = computed(() => preview.value?.attribution || null)
const attributionReady = computed(() => {
  const a = attribution.value
  return !!a && (a.cohorts?.coupon_users?.n || 0) > 0 && (a.cohorts?.non_users?.n || 0) > 0
})
const pctText = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`)
const repeatUsersText = computed(() => pctText(attribution.value?.cohorts?.coupon_users?.repeat_rate))
const repeatNonUsersText = computed(() => pctText(attribution.value?.cohorts?.non_users?.repeat_rate))
const roiText = computed(() => {
  const r = attribution.value?.roi
  return r === null || r === undefined ? '数据不足' : `${r >= 0 ? '+' : ''}${r.toFixed(1)}×`
})

// ── 系统调参日志（说人话，最多两条） ──────────────────────
const TUNING_RULE_LABEL = {
  entry_coupon: '进店券', new_customer_coupon: '新客券',
  consumption_coupon: '复购券', recall_coupon: '召回券',
}
const tuningLogText = computed(() => {
  const log = preview.value?.tuning?.log || []
  const lines = log.slice(-2).reverse().map((e) => {
    const name = TUNING_RULE_LABEL[e.rule] || e.rule
    const tFrom = e.from?.threshold_mult ?? 1
    const tTo = e.to?.threshold_mult ?? 1
    const aFrom = e.from?.amount_mult ?? 1
    const aTo = e.to?.amount_mult ?? 1
    const rr = e.redemption_rate === null || e.redemption_rate === undefined
      ? '' : `（核销率 ${(e.redemption_rate * 100).toFixed(0)}%）`
    if (String(e.reason || '').startsWith('roi_rollback')) return `系统回调了${name}的力度${rr}`
    if (tTo < tFrom) return `系统把${name}门槛下调了 ${Math.round((1 - tTo / tFrom) * 100)}%${rr}`
    if (aTo < aFrom) return `系统把${name}面额收了 ${Math.round((1 - aTo / aFrom) * 100)}%${rr}`
    if (aTo > aFrom) return `系统把${name}面额加了 ${Math.round((aTo / aFrom - 1) * 100)}%${rr}`
    return `系统微调了${name}${rr}`
  })
  return lines.join('；')
})

const redemptionRateText = computed(() => {
  const rate = preview.value?.redemption_rate
  if (rate === null || rate === undefined) return '暂无数据'
  return `${(rate * 100).toFixed(0)}%`
})

const heroDesc = computed(() => {
  // 未确认（首次加载中）和确认失败必须先说清楚，不能沿用"系统正在配置"这类
  // 听起来一切正常的文案——那句话只应该在"确认成功但细项还没算出来"时出现。
  if (previewError.value) return '暂时无法确认营销运行状态，请点击重试'
  if (!previewLoaded.value) return '正在确认营销运行状态…'
  const outcomes = preview.value?.intensity_outcomes
  if (!outcomes) return '系统正在为你自动配置营销参数…'
  if (!outcomes.has_enough_data) return '数据积累中，当前用安全参数自动运行，满 5 单后为你精算'
  const cur = (outcomes.outcomes || []).find(o => o.is_current)
  if (!cur) return '系统已自动为你配置营销参数'
  const ratio = ((cur.estimated_cost_ratio || 0) * 100).toFixed(1)
  return `预计本月自动发放约 ${cur.estimated_monthly_coupons} 张券，成本约 ¥${cur.estimated_cost_per_month}（约占营业额 ${ratio}%）`
})

// ── 数据加载 ─────────────────────────────────────────────
async function loadPreview() {
  previewLoaded.value = false
  try {
    const res = await getMarketingPreview()
    if (res?.code !== 200) throw new Error(res?.msg || '营销状态加载失败')
    preview.value = res?.data?.data || res?.data || {}
    previewError.value = false
  } catch {
    // 失败不清空 preview.value：若之前已经成功加载过，旧数据仍保留，只是
    // previewError 会让模板不再假定它仍然是"运行中"的确定证据。
    previewError.value = true
  } finally {
    previewLoaded.value = true
  }
}

async function loadTemplates() {
  loadingTemplates.value = true
  templatesError.value = false
  try {
    const res = await getCouponTemplates({ page: 1, page_size: 100 })
    if (res?.code !== 200) throw new Error(res?.msg || '优惠券加载失败')
    const data = res?.data?.data || res?.data || []
    templates.value = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []
  } catch {
    // 失败不清空 templates：保留上一次正确列表，由 templatesError 触发独立错误态，
    // 不落入"还没有手动建券"的空态文案。
    templatesError.value = true
    showFailToast('优惠券加载失败')
  } finally {
    loadingTemplates.value = false
  }
}

// ── 强度切换：跟"今日"页调用同一个接口，选中即生效 ──────────
async function switchIntensity(key) {
  if (switchingIntensity.value || key === currentIntensity.value) return
  switchingIntensity.value = true
  try {
    const res = await updateTenantSettings({ marketing_intensity: key })
    if (res?.code !== 200) { showFailToast(res?.msg || '切换失败'); return }
    await loadPreview()
    showSuccessToast('已切换')
  } catch {
    showFailToast('切换失败，请稍后重试')
  } finally {
    switchingIntensity.value = false
  }
}

async function onIndustrySelect({ selectedOptions }) {
  showIndustryPicker.value = false
  const key = selectedOptions?.[0]?.value
  if (!key || key === currentIndustry.value || switchingIndustry.value) return
  switchingIndustry.value = true
  try {
    const res = await updateTenantSettings({ industry: key })
    if (res?.code !== 200) { showFailToast(res?.msg || '保存失败'); return }
    await loadPreview()
    showSuccessToast('已更新')
  } catch {
    showFailToast('保存失败，请稍后重试')
  } finally {
    switchingIndustry.value = false
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
    const res = await createCouponTemplate({
      name: form.name,
      type: 'FIXED',
      value: Number(form.value || 0),
      min_amount: Number(form.min_amount || 0),
      total_stock: Number(form.total_stock || 100),
      start_time: now.toISOString(),
      end_time: end.toISOString(),
      status: 1,
    })
    // 后端就算校验不通过（比如触发了亏本红线）也会返回 HTTP 200，
    // 必须看 code 才知道是不是真的建成功——不然商家会看到"已上架"，
    // 但券其实根本没建出来。
    if (res?.code !== 200) { showFailToast(res?.msg || '创建失败'); return }
    showSuccessToast('券已上架')
    showForm.value = false
    loadTemplates()
  } catch {
    showFailToast('创建失败，请稍后重试')
  } finally {
    savingForm.value = false
  }
}

// ── 工具函数 ─────────────────────────────────────────────
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
  background: var(--bg-page);
  color: var(--text-1);
}
.page-content {
  padding: 12px 12px 84px;
}

/* ── 顶部状态卡 ─────────────────── */
.hero-card {
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
.hero-badge--unknown { background: rgba(255,255,255,.14); }
.hero-card h1 { font-size: 20px; margin: 0 0 12px; }

.hero-error-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  opacity: .95;
}
.hero-retry-btn { flex-shrink: 0; }
.empty-state--error { color: #dc2626; }

.intensity-switch {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.intensity-pill {
  flex: 1;
  text-align: center;
  padding: 9px 0;
  border-radius: 10px;
  background: rgba(255,255,255,.16);
  color: rgba(255,255,255,.85);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.intensity-pill--on {
  background: #fff;
  color: #07C160;
}
.intensity-pill--disabled {
  opacity: .6;
  pointer-events: none;
}

.industry-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 9px 12px;
  border-radius: 10px;
  background: rgba(255,255,255,.16);
  font-size: 13px;
  cursor: pointer;
}
.industry-row-label { color: rgba(255,255,255,.75); font-weight: 700; }
.industry-row-value { flex: 1; color: #fff; font-weight: 700; }
.industry-row--unset .industry-row-value { color: rgba(255,255,255,.7); font-weight: 400; }
.industry-row .van-icon { color: rgba(255,255,255,.7); font-size: 14px; }
.industry-row--disabled { opacity: .6; pointer-events: none; }

.hero-desc { font-size: 13px; opacity: .9; margin: 0 0 14px; line-height: 1.5; }

.hero-stat-row { display: flex; gap: 22px; }
.hero-stat { display: flex; align-items: baseline; gap: 8px; }
.stat-num   { font-size: 22px; font-weight: 900; }
.stat-label { font-size: 12px; opacity: .8; }

/* ── 通用面 ───────────────────── */
.panel {
  background: var(--bg-card);
  border-radius: 18px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: var(--card-shadow);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.section-eyebrow { margin: 0 0 4px; color: #07C160; font-size: 12px; font-weight: 700; }
.section-header h2 { margin: 0; font-size: 20px; color: var(--text-1); }
.section-tip {
  margin: 10px 0 0;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.6;
}

.effect-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 8px;
}
.effect-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px;
  border-radius: 12px;
  background: var(--fill-2, #f6f7f9);
}
.effect-num { font-size: 20px; font-weight: 800; color: var(--text-1); }
.effect-label { font-size: 12px; color: var(--text-3); }
.effect-tuning { color: #07C160; font-weight: 600; }

/* ── 则卡片：只做说明，无开关无参数 ─────────── */
.rule-list { display: grid; gap: 10px; }
.rule-card {
  padding: 14px;
  border: 1.5px solid var(--border);
  border-radius: 16px;
}

.rule-head {
  display: grid;
  grid-template-columns: 44px 1fr;
  align-items: center;
  gap: 12px;
}
.rule-icon {
  display: grid; place-items: center;
  width: 44px; height: 44px;
  border-radius: 14px;
  color: #fff;
  font-size: 22px;
  flex-shrink: 0;
}
.rule-icon.purple { background: #8b5cf6; }
.rule-icon.green  { background: #10b981; }
.rule-icon.blue   { background: #3b82f6; }
.rule-icon.orange { background: #f59e0b; }
.rule-icon.gold   { background: #ca8a04; }

.rule-meta h3 { margin: 0 0 3px; font-size: 17px; color: var(--text-1); }
.rule-meta p  { margin: 0; color: var(--text-2); font-size: 12px; line-height: 1.5; }

/* ── 高级设置折叠区 ───────────────── */
.advanced-collapse {
  border-radius: 18px;
  overflow: hidden;
  margin-bottom: 12px;
}
.advanced-collapse :deep(.van-collapse-item__title) {
  font-weight: 700;
  color: var(--text-1);
  background: var(--bg-card);
}
.advanced-collapse :deep(.van-collapse-item__content) {
  background: var(--bg-card);
  color: var(--text-2);
}
.advanced-block + .advanced-block { margin-top: 16px; }

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
  border: 1px solid var(--border);
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
.coupon-info h3 { margin: 0 0 4px; font-size: 16px; color: var(--text-1); }
.coupon-info p  { margin: 0; color: var(--text-2); font-size: 12px; line-height: 1.6; }

.status-pill {
  padding: 4px 8px;
  border-radius: 999px;
  background: #ecfdf5;
  color: #059669;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.status-pill.off { background: var(--bg-page); color: var(--text-2); }

/* ── 空状态 ─────────────────────── */
.empty-state {
  padding: 28px 12px;
  border-radius: 14px;
  background: var(--bg-page);
  color: var(--text-2);
  text-align: center;
  font-size: 14px;
}

/* ── 建券弹窗 ───────────────────── */
.form-sheet { padding: 18px 12px 32px; background: var(--bg-card); }
.form-sheet h2 { padding: 0 8px 14px; font-size: 20px; color: var(--text-1); }
.save-btn { margin-top: 16px; }

@media (max-width: 380px) {
  .quick-actions { grid-template-columns: 1fr; }
  .template-card { grid-template-columns: 80px 1fr auto; }
}
</style>
