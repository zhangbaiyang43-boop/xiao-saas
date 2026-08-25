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

    <!-- 已有会员数据仍在展示，仅提示这次同步失败；不清空上一次真实加载的结果 -->
    <div v-if="loadError && customers.length > 0 && loadedKeyword === keyword" class="section-block" style="padding:0 16px 12px">
      <a-alert type="warning" show-icon message="会员同步失败，当前显示的是上次数据" style="border-radius:10px">
        <template #action>
          <a-button size="small" :loading="loading" @click="loadCustomers">重试</a-button>
        </template>
      </a-alert>
    </div>

    <!-- 内容 -->
    <div class="page-body">
      <template v-if="loading && customers.length === 0">
        <a-skeleton active avatar :paragraph="{ rows: 2 }" class="customer-skeleton" />
        <a-skeleton active avatar :paragraph="{ rows: 2 }" class="customer-skeleton" />
        <a-skeleton active avatar :paragraph="{ rows: 2 }" class="customer-skeleton" style="margin-bottom:0" />
      </template>

      <!-- 没有旧数据可退回（首次加载失败），或者旧数据是上一个关键词的结果（不能
           冒充成这次搜索的结果）：两种情况都必须显式失败，不能落入空会员列表。 -->
      <div v-else-if="loadError && (customers.length === 0 || loadedKeyword !== keyword)" class="error-state">
        <ExclamationCircleOutlined style="font-size:40px;color:#d1d5db" />
        <div>加载失败，请检查网络</div>
        <a-button type="primary" ghost @click="loadCustomers">重新加载</a-button>
      </div>

      <a-empty v-else-if="customers.length === 0" description="还没有会员，去生成桌贴码让顾客扫码入会吧">
        <a-button type="primary" @click="router.push('/entrance-codes')">去生码</a-button>
      </a-empty>

      <template v-else>
        <div class="customer-list animate-in" style="animation-delay:.04s">
          <div v-for="customer in customers" :key="customer.id" class="customer-card tap-shrink" @click="goToDetail(customer.id)">
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
        <!-- 加载更多：真实翻页，向后端请求下一页，不是展开本地已拉取数据 -->
        <div v-if="customers.length > 0" style="text-align:center;padding:12px 0">
          <a-button v-if="customers.length < total" ghost type="primary" :loading="loadingMore" @click="loadMore">
            加载更多（共 {{ total }} 位，还有 {{ total - customers.length }} 位）
          </a-button>
          <span v-else style="font-size:12px;color:var(--text-3)">已显示全部 {{ total }} 位会员</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { UserOutlined, EllipsisOutlined, ExclamationCircleOutlined } from '@ant-design/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { deleteCustomer, getCustomers, restoreCustomer } from '../api'
import { markPageContentReady } from '../utils/adminPerformance'

const router = useRouter()
// 真实分页状态：page/total 来自后端，不是前端切片。PAGE_SIZE 是每次真实请求
// 后端的行数，不是"从已拉取数据里展示多少条"的本地上限。
const PAGE_SIZE = 30
// 从详情页返回时，一次性把"已经翻到第几页"补回来，用一个更大的 page_size 单次
// 请求真实数据（依然是后端分页合同，只是这一次的行数更大），而不是连续发起
// N 次"加载更多"。后端 PAGE_MAX_LIMIT=200（saas-base app/config.py），这里封顶，
// 超出部分只能少恢复几页，好过恢复失败或干脆不恢复。
const RESTORE_PAGE_SIZE_CAP = 200
const customers = ref([])
const total = ref(0)
const page = ref(1)
const keyword = ref('')
// customers.value 是为哪个关键词加载的——搜索失败时用它判断能不能把旧数据当作
// "当前查询的上次结果"继续展示，还是必须整块进入错误态（不能把上一次搜索的结果
// 冒充成这次搜索的结果）。null 表示还没有任何成功加载过。
const loadedKeyword = ref(null)
const loading = ref(false)
const loadingMore = ref(false)
const loadError = ref(false)

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
function mapCustomer(item) {
  return {
    id: item.id,
    name: item.name || item.nickname || '微信会员',
    phone: item.phone,
    source: sourceText(item),
    last_consume_time: item.last_consume_time,
    status: item.status,
  }
}

// ── 会员详情往返的工作上下文保持（Phase-05C）──────────────────────────
// 只保存"老板刚才在找什么"（关键词 + 翻到第几页），不保存会员数据本身——
// 返回后永远用这两个值发起一次真实请求重新拿数据，不复用旧数组、不假装
// 详情页里可能做的停用/恢复不存在。sessionStorage 不写手机号进 URL（不进
// 浏览器历史/服务端日志/Referer/截图），且天然只活在这个标签页内，比
// localStorage 生命周期短。identity 用 tenant_id+token 拼接（跟
// useWorkbenchSync.js 的 currentIdentity() 同一种做法），读取时必须完全
// 匹配当前登录身份才采信——换租户、退出登录后重新登录，identity 必然不同，
// 旧上下文永远不会被错误恢复。
const CUSTOMER_LIST_CONTEXT_KEY = 'admin_customer_list_context'

function currentContextIdentity() {
  return `${localStorage.getItem('tenant_id') || ''}:${localStorage.getItem('token') || ''}`
}

function saveListContext() {
  try {
    sessionStorage.setItem(CUSTOMER_LIST_CONTEXT_KEY, JSON.stringify({
      identity: currentContextIdentity(),
      keyword: keyword.value,
      page: page.value,
    }))
  } catch { /* sessionStorage 不可用时静默降级为不保存，不影响正常导航 */ }
}

// 消费型读取：读到就立刻删除。只有"从详情页返回"这一条路径会写入这个
// key，读到即代表这次是回程；读完清空可以保证下一次普通进入（点底部
// 导航、从 Dashboard 进来）不会被更早一次的查询劫持。
function consumeSavedListContext() {
  let raw = null
  try {
    raw = sessionStorage.getItem(CUSTOMER_LIST_CONTEXT_KEY)
    sessionStorage.removeItem(CUSTOMER_LIST_CONTEXT_KEY)
  } catch { return null }
  if (!raw) return null
  let saved
  try { saved = JSON.parse(raw) } catch { return null }
  if (!saved || saved.identity !== currentContextIdentity()) return null
  return saved
}

// 首次加载 / 刷新 / 换关键词搜索：始终请求真实第 1 页。失败时不清空 customers，
// 交给模板的 loadError 分支决定是保留旧数据加横幅，还是（关键词已经变了）整块
// 进入错误态——两种情况都不能显示成"没有会员"。
//
// restorePage/restorePageSize 仅在从详情页返回、需要一次性把之前翻到的深度补
// 回来时才会被传真实值；平时调用（首次进入/手动刷新/换关键词）用默认值，行为
// 和这两个参数加入之前完全一样。不管是不是在恢复，这里始终发起一次真实请求，
// 不会把上一次的旧内存数组直接当结果用（详情页可能已经改了会员状态）。
async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {
  loading.value = true
  page.value = 1
  let resultStatus = 'success'
  try {
    const params = { page: 1, page_size: restorePageSize }
    if (keyword.value) params.search = keyword.value
    const res = await getCustomers(params)
    if (res.code !== 200) throw new Error(res.msg || '会员加载失败')
    const data = apiData(res)
    const rows = extractRows(data)
    customers.value = rows.map(mapCustomer)
    total.value = Number(data?.total ?? customers.value.length)
    page.value = restorePage
    loadedKeyword.value = keyword.value
    loadError.value = false
    resultStatus = customers.value.length ? 'success' : 'empty'
  } catch (e) {
    loadError.value = true
    resultStatus = 'error'
    if (e?.message) message.error(e.message)
  } finally {
    loading.value = false
    markPageContentReady({
      page: 'MemberManage',
      status: resultStatus,
      data_count: customers.value.length,
    })
  }
}

// 从详情返回时调用：把保存的 keyword/page 接回来，用一次更大的 page_size 请求
// 补齐已经翻过的深度（封顶 RESTORE_PAGE_SIZE_CAP），而不是连续点 N 次"加载更多"。
async function restoreListContext(saved) {
  keyword.value = saved.keyword || ''
  const cappedPage = Math.max(1, Math.min(Number(saved.page) || 1, Math.floor(RESTORE_PAGE_SIZE_CAP / PAGE_SIZE)))
  await loadCustomers({ restorePage: cappedPage, restorePageSize: cappedPage * PAGE_SIZE })
}

// 翻页：真实请求后端下一页，追加到已有列表；失败不回退已加载的行、不推进
// page，方便原地重试，且已经正确显示的会员不受影响。
async function loadMore() {
  if (loadingMore.value || loading.value) return
  if (customers.value.length >= total.value) return
  const nextPage = page.value + 1
  loadingMore.value = true
  try {
    const params = { page: nextPage, page_size: PAGE_SIZE }
    if (keyword.value) params.search = keyword.value
    const res = await getCustomers(params)
    if (res.code !== 200) throw new Error(res.msg || '加载更多失败')
    const data = apiData(res)
    const rows = extractRows(data)
    customers.value = customers.value.concat(rows.map(mapCustomer))
    total.value = Number(data?.total ?? total.value)
    page.value = nextPage
    loadError.value = false
  } catch (e) {
    message.error(e?.message || '加载更多失败，请重试')
  } finally {
    loadingMore.value = false
  }
}

function goToDetail(id) {
  saveListContext()
  router.push(`/customers/${id}`)
}
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

// 正常进入（底部导航、从 Dashboard 点进来、刷新页面）不会有可消费的历史上下文，
// 走跟以前完全一样的路径；只有从详情页返回时 consumeSavedListContext() 才会
// 返回非空值。
onMounted(() => {
  const saved = consumeSavedListContext()
  if (saved) restoreListContext(saved)
  else loadCustomers()
})
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
