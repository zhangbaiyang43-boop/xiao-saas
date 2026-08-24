<template>
  <div class="sub-page">
    <PageHeader title="会员列表">
      <a-button type="text" size="small" @click="loadCustomers" :loading="loading" style="color:var(--brand)">刷新</a-button>
    </PageHeader>

    <!-- 搜索 -->
    <div class="search-bar animate-in">
      <a-input-search
        v-model:value="keyword"
        placeholder="搜手机号或姓名"
        allow-clear
        @search="loadCustomers"
        @keyup.enter="loadCustomers"
      />
    </div>

    <!-- 内容 -->
    <div class="page-body">
      <template v-if="loading && customers.length === 0">
        <a-skeleton active avatar :paragraph="{ rows: 2 }" class="customer-skeleton" />
        <a-skeleton active avatar :paragraph="{ rows: 2 }" class="customer-skeleton" />
        <a-skeleton active avatar :paragraph="{ rows: 2 }" class="customer-skeleton" style="margin-bottom:0" />
      </template>

      <div v-else-if="loadError" class="error-state">
        <ExclamationCircleOutlined style="font-size:40px;color:#d1d5db" />
        <div>加载失败，请检查网络</div>
        <a-button type="primary" ghost @click="loadCustomers">重新加载</a-button>
      </div>

      <a-empty v-else-if="customers.length === 0" description="还没有会员，去生成桌贴码让顾客扫码入会吧">
        <a-button type="primary" @click="router.push('/entrance-codes')">去生码</a-button>
      </a-empty>

      <template v-else>
        <div class="customer-list animate-in" style="animation-delay:.04s">
          <div v-for="customer in visibleCustomers" :key="customer.id" class="customer-card tap-shrink" @click="goToDetail(customer.id)">
            <div class="avatar">
              <UserOutlined style="font-size:20px;color:var(--brand)" />
            </div>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <span style="font-size:15px;font-weight:700;color:var(--text-1)">{{ customer.name }}</span>
                <a-tag :color="isActive(customer) ? 'success' : 'error'" size="small" style="font-size:11px">
                  {{ isActive(customer) ? '正常' : '已停用' }}
                </a-tag>
              </div>
              <div style="font-size:13px;color:var(--text-2);margin-bottom:6px">
                {{ formatPhone(customer.phone) }}<span v-if="customer.store_member_no"> · 会员卡号 {{ formatMemberNo(customer.store_member_no) }}</span>
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                <span class="c-tag">{{ customer.source }}</span>
                <span class="c-tag">{{ customer.last_consume_time ? '最近到店' : '还未消费' }}</span>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;flex-shrink:0" @click.stop>
              <a-button size="small" type="primary" ghost @click="sendCoupon(customer)">发券</a-button>
              <a-dropdown trigger="click" placement="bottomRight">
                <a-button size="small" style="padding:0 6px"><EllipsisOutlined /></a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item v-if="isActive(customer)" danger @click="disableCustomer(customer)">停用会员</a-menu-item>
                    <a-menu-item v-else @click="restore(customer)" style="color:var(--success)">恢复会员</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>
          </div>
        </div>
        <!-- 加载更多 -->
        <div v-if="customers.length > pageSize" style="text-align:center;padding:12px 0">
          <a-button v-if="visibleCustomers.length < customers.length" ghost type="primary" @click="pageSize += 30">
            加载更多（还有 {{ customers.length - visibleCustomers.length }} 位）
          </a-button>
          <span v-else style="font-size:12px;color:var(--text-3)">已显示全部 {{ customers.length }} 位会员</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { UserOutlined, EllipsisOutlined, ExclamationCircleOutlined } from '@ant-design/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { deleteCustomer, getCustomers, restoreCustomer } from '../api'
import { markPageContentReady } from '../utils/adminPerformance'

const router = useRouter()
const customers = ref([])
const keyword = ref('')
const loading = ref(false)
const loadError = ref(false)
const pageSize = ref(30)
const visibleCustomers = computed(() => customers.value.slice(0, pageSize.value))

function apiData(res) { return res?.data || res || {} }
function extractRows(data) {
  if (Array.isArray(data)) return data
  return data?.items || data?.results || data?.list || data?.data || []
}
function sourceText(item) {
  const s = item.source_name || item.entrance_name || item.source || item.channel
  return { miniapp: '小程序入会', WECHAT_MINI: '小程序入会', PHONE: '手机号', WEWORK: '企业微信', DOUYIN: '抖音' }[s] || s || '扫码入会'
}
function isActive(c) { return Number(c.status) === 1 }
function formatPhone(p) { if (!p) return '未留手机号'; return String(p).replace(/(\d{3})\d{4}(\d{4})/, '$1****$2') }
function formatMemberNo(no) { return String(no).padStart(6, '0') }

async function loadCustomers() {
  loading.value = true
  loadError.value = false
  pageSize.value = 30
  let resultStatus = 'success'
  try {
    const params = { page: 1, page_size: 100, skip: 0, limit: 100 }
    if (keyword.value) { params.search = keyword.value; params.keyword = keyword.value }
    const res = await getCustomers(params)
    if (res.code !== 200) {
      resultStatus = 'error'
      message.error(res.msg || '会员加载失败')
      customers.value = []
      return
    }
    const rows = extractRows(apiData(res))
    customers.value = rows.map(item => ({
      id: item.id,
      name: item.name || item.nickname || '微信会员',
      phone: item.phone,
      source: sourceText(item),
      last_consume_time: item.last_consume_time,
      status: item.status,
    }))
    resultStatus = customers.value.length ? 'success' : 'empty'
  } catch {
    customers.value = []
    loadError.value = true
    resultStatus = 'error'
  } finally {
    loading.value = false
    markPageContentReady({
      page: 'MemberManage',
      status: resultStatus,
      data_count: customers.value.length,
    })
  }
}

function goToDetail(id) { router.push(`/customers/${id}`) }
function sendCoupon(customer) { router.push({ path: '/coupons', query: { customerId: customer.id, customerName: customer.name } }) }

function disableCustomer(customer) {
  Modal.confirm({
    title: '停用会员',
    content: `停用后，${customer.name || '这位会员'} 将无法扫码入会或使用优惠券，历史消费和积分记录会保留。`,
    okText: '停用',
    okType: 'danger',
    onOk: async () => {
      const res = await deleteCustomer(customer.id)
      if (res.code === 200) { message.success('已停用'); await loadCustomers() }
      else message.error(res.msg || '停用失败')
    },
  })
}

function restore(customer) {
  Modal.confirm({
    title: '恢复会员',
    content: `恢复 ${customer.name || '这位会员'} 后，顾客可以重新登录小程序并正常核销优惠券。`,
    okText: '恢复',
    onOk: async () => {
      const res = await restoreCustomer(customer.id)
      if (res.code === 200) { message.success('已恢复'); await loadCustomers() }
      else message.error(res.msg || '恢复失败')
    },
  })
}

onMounted(loadCustomers)
</script>

<style scoped>
.search-bar {
  padding: 12px 16px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.customer-skeleton {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 14px;
  margin-bottom: 10px;
}
.customer-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 14px;
  margin-bottom: 10px;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: background .1s;
  &:last-child { margin-bottom: 0; }
  &:active { background: var(--brand-light); }
}
.avatar {
  width: 46px; height: 46px; border-radius: 14px;
  background: var(--brand-light);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.c-tag {
  font-size: 11px; color: var(--text-2);
  background: var(--bg-page); border-radius: 20px;
  padding: 2px 8px;
}
</style>
