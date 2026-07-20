<template>
  <div class="membership-page">
    <section class="hero-card">
      <div>
        <div class="eyebrow">会员体系</div>
        <h1>一套则管理所有会员</h1>
        <p>手机号、微信身份、优惠券和等级统一管理，顾客从哪个入口来都算同一个会员。</p>
      </div>
      <van-button
        size="small"
        round
        type="primary"
        :loading="loading"
        @click="loadData"
      >
        刷新
      </van-button>
    </section>

    <section class="section-card">
      <div class="section-head">
        <div>
          <h2>统一原则</h2>
          <p>后续接微信、抖音、门店，都沿用这套会员则。</p>
        </div>
      </div>

      <div class="principle-grid">
        <div v-for="item in principles" :key="item.title" class="principle-card">
          <div class="principle-icon">{{ item.icon }}</div>
          <strong>{{ item.title }}</strong>
          <span>{{ item.desc }}</span>
        </div>
      </div>
    </section>

    <section class="section-card">
      <div class="section-head">
        <div>
          <h2>会员等级</h2>
          <p>消费越多等级越高，适合后续做复购和老客权益。</p>
        </div>
      </div>

      <van-loading v-if="loading" class="loading-block" />
      <div v-else class="level-list">
        <div v-for="level in displayLevels" :key="level.code" class="level-card">
          <div class="level-main">
            <van-tag round type="primary">{{ level.code }}</van-tag>
            <div>
              <strong>{{ level.name }}</strong>
              <span>年消费满 {{ formatMoney(level.threshold) }} 元</span>
            </div>
          </div>
          <div class="level-value">{{ level.point_multiplier || 1 }}x 积分</div>
        </div>
      </div>
    </section>

    <section class="section-card">
      <div class="section-head">
        <div>
          <h2>积分则</h2>
          <p>先保持简单，顾客容易理解，商家也容易解释。</p>
        </div>
      </div>

      <div class="rule-list">
        <div v-for="item in pointRules" :key="item.label" class="rule-row">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </section>

    <section class="section-card">
      <div class="section-head">
        <div>
          <h2>权益池</h2>
          <p>所有权益进入会员中心，顾客打开就能看、到店就能用。</p>
        </div>
      </div>

      <div v-if="displayBenefits.length" class="benefit-list">
        <div v-for="benefit in displayBenefits" :key="benefit.id || benefit.name" class="benefit-card">
          <div>
            <div class="benefit-title">
              <van-tag round plain type="success">{{ benefit.level_code || '通用' }}</van-tag>
              <strong>{{ benefit.name }}</strong>
            </div>
            <span>{{ benefit.type || benefit.desc }}</span>
          </div>
          <b>{{ benefit.value }}</b>
        </div>
      </div>
      <van-empty v-else description="暂无权益配置" />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Button as VanButton,
  Empty as VanEmpty,
  Loading as VanLoading,
  Tag as VanTag,
  showToast
} from 'vant'
import { getMembershipConfig } from '../api'

const loading = ref(false)

const config = reactive({
  levels: [],
  benefits: []
})

const principles = [
  { icon: '', title: '一个会员', desc: '手机号和微信身份归一' },
  { icon: '分', title: '一个积分账户', desc: '消费、分享、签到统一入账' },
  { icon: '级', title: '一套等级体系', desc: '微信、门店、抖音共用则' },
  { icon: '券', title: '一套权益池', desc: '领券、查看、核销统一' }
]

const defaultLevels = [
  { code: 'Lv1', name: '普通会员', threshold: 0, point_multiplier: 1 },
  { code: 'Lv2', name: '成长会员', threshold: 299, point_multiplier: 1.2 },
  { code: 'Lv3', name: 'VIP会员', threshold: 999, point_multiplier: 1.5 }
]

const defaultBenefits = [
  { id: 'new-coupon', level_code: '新客', name: '新人券', type: '扫码入会自动领取', value: '拉新' },
  { id: 'after-coupon', level_code: '复购', name: '消费后券', type: '顾客用券后自动发下一张', value: '复购' },
  { id: 'recall-coupon', level_code: '召回', name: '老客召回券', type: '多天没来自动提醒回来', value: '召回' }
]

const pointRules = [
  { label: '消费积分', value: '消费 1 元 = 1 积分' },
  { label: '积分抵扣', value: '100 积分 = 1 元' },
  { label: '积分有效期', value: '默认 365 天' }
]

const displayLevels = computed(() => {
  return config.levels.length ? config.levels : defaultLevels
})

const displayBenefits = computed(() => {
  return config.benefits.length ? config.benefits : defaultBenefits
})

const formatMoney = (num) => Number(num || 0).toLocaleString()

const loadData = async () => {
  loading.value = true
  try {
    const res = await getMembershipConfig()
    const data = res?.data || {}
    if (res?.code === 200 || res?.success) {
      config.levels = data.levels || []
      config.benefits = data.benefits || []
      return
    }
    showToast(res?.message || res?.msg || '会员配置加载失败')
  } catch (error) {
    console.error('加载会员配置失败:', error)
    showToast('会员配置加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.membership-page {
  min-height: 100vh;
  padding: 12px 12px 88px;
  background: #f5f6f8;
}

.hero-card,
.section-card {
  margin-bottom: 12px;
  padding: 16px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
}

.hero-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  background: linear-gradient(135deg, #fff7ed 0%, #ffffff 48%, #ecfdf5 100%);
}

.eyebrow {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #f97316;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 22px;
  line-height: 1.25;
  color: #111827;
}

h2 {
  font-size: 18px;
  color: #111827;
}

p {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #64748b;
}

.section-head {
  margin-bottom: 14px;
}

.principle-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.principle-card {
  min-height: 108px;
  padding: 12px;
  border-radius: 14px;
  background: #f8fafc;
}

.principle-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-bottom: 10px;
  border-radius: 10px;
  background: #1677ff;
  color: #fff;
  font-size: 13px;
  font-weight: 800;
}

.principle-card strong,
.level-main strong,
.benefit-title strong {
  display: block;
  font-size: 15px;
  color: #111827;
}

.principle-card span,
.level-main span,
.benefit-card span {
  display: block;
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
}

.loading-block {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.level-list,
.benefit-list,
.rule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.level-card,
.benefit-card,
.rule-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px;
  border-radius: 14px;
  background: #f8fafc;
}

.level-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.level-value {
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 800;
  color: #16a34a;
}

.rule-row {
  background: #fff7ed;
}

.rule-row span {
  font-size: 14px;
  color: #64748b;
}

.rule-row strong {
  font-size: 14px;
  color: #111827;
}

.benefit-card b {
  flex-shrink: 0;
  color: #ef4444;
  font-size: 15px;
}

.benefit-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
