import { ref } from 'vue'
import { getQueueStatus, getQueueTickets } from '@/api/queue'

const unwrap = (res) => {
  if (res?.success === false) throw new Error(res.message || '加载失败')
  return res?.data || res
}

// 排队小票状态：index.vue（等位中查看）和 result.vue（取号成功后展示）共用同一套取数逻辑，
// 只是"前方还有几桌"统计要不要把已叫号的算进去不一样，所以用 aheadStatuses 参数化。
export function useQueueTicket({ aheadStatuses = ['waiting'] } = {}) {
  const tenantId = ref(uni.getStorageSync('tenant_id') || '')
  const ticketId = ref('')
  const ticket = ref({})
  const queueStatus = ref({})
  const aheadCount = ref(0)
  const loading = ref(true)
  const error = ref('')

  const load = async () => {
    loading.value = true
    error.value = ''
    try {
      const local = uni.getStorageSync('queue_ticket')
      if (local) ticket.value = JSON.parse(local) || {}
      const [statusRes, listRes] = await Promise.all([
        getQueueStatus({ tenant_id: tenantId.value }),
        getQueueTickets({ tenant_id: tenantId.value })
      ])
      queueStatus.value = unwrap(statusRes) || {}
      const list = unwrap(listRes) || []
      const current = list.find(item => String(item.id) === String(ticketId.value || ticket.value.id))
      if (current) {
        ticket.value = current
        uni.setStorageSync('queue_ticket', JSON.stringify(current))
      }
      aheadCount.value = list.filter(item =>
        item.queue_type === ticket.value.queue_type &&
        aheadStatuses.includes(item.status) &&
        Number(item.id) !== Number(ticket.value.id)
      ).length
    } catch (err) {
      error.value = err.message || '加载失败'
      uni.showToast({ title: error.value, icon: 'none' })
    } finally {
      loading.value = false
    }
  }

  return { tenantId, ticketId, ticket, queueStatus, aheadCount, loading, error, load }
}
