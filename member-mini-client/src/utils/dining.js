import { resolveDiningSession } from '@/api/auth'

// 建立/校验"本桌匿名身份"的唯一入口。扫码入口页（entry/index.vue）和点餐页
// （subpkg-order/pages/menu.vue）之前各自维护了一份几乎一样的逻辑，其中一份漏写了
// dining_table_no 的持久化——这正是历史上真实发生过的 bug 根源之一。现在两处都必须
// 走这一个函数，身份怎么建立、怎么判断缓存过期、往 storage 写哪些字段，只在这里改一处。

export const getOrCreateDiningClientId = () => {
  let clientId = uni.getStorageSync('dining_client_id') || ''
  if (!clientId) {
    clientId = `dc_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`
    uni.setStorageSync('dining_client_id', clientId)
  }
  return clientId
}

export const persistDiningContext = (data = {}) => {
  if (data.dining_session_id) uni.setStorageSync('dining_session_id', data.dining_session_id)
  if (data.participant_id) uni.setStorageSync('dining_participant_id', data.participant_id)
  if (data.participant_token) uni.setStorageSync('dining_participant_token', data.participant_token)
  if (data.client_id) uni.setStorageSync('dining_client_id', data.client_id)
  if (data.table_no) uni.setStorageSync('dining_table_no', data.table_no)
}

/**
 * @param {{tenantId: string, table: string, force?: boolean}} params
 * @returns {Promise<{ok: true, data: object} | {ok: false, reason: string}>}
 */
export const resolveDiningIdentity = async ({ tenantId, table, force = false } = {}) => {
  tenantId = (tenantId || '').trim()
  table = (table || '').trim()
  if (!tenantId || !table) return { ok: false, reason: 'missing_context' }

  // 缓存的 dining_session_id/participant_token 可能是上一次扫别的桌留下的（比如强制
  // 解析那次请求被打断，没来得及覆盖旧缓存）。如果缓存记录的桌号和当前这一桌对不上，
  // 缓存已经不可信，必须强制重新解析，否则会把这一桌的点单悄悄挂到别的桌的会话上。
  const cachedTable = uni.getStorageSync('dining_table_no') || ''
  const staleForOtherTable = Boolean(cachedTable) && cachedTable !== table
  const cachedSessionId = uni.getStorageSync('dining_session_id') || ''
  const cachedToken = uni.getStorageSync('dining_participant_token') || ''

  if (!force && !staleForOtherTable && cachedSessionId && cachedToken) {
    return {
      ok: true,
      data: {
        dining_session_id: cachedSessionId,
        participant_token: cachedToken,
        client_id: uni.getStorageSync('dining_client_id') || '',
        table_no: cachedTable || table,
      },
    }
  }

  try {
    const res = await resolveDiningSession({
      tenant_id: tenantId,
      table_no: table,
      client_id: getOrCreateDiningClientId(),
      participant_token: staleForOtherTable ? undefined : (cachedToken || undefined),
    })
    if (res?.code !== 200 || !res.data) return { ok: false, reason: res?.msg || 'resolve_failed' }
    const data = { ...res.data, table_no: res.data.table_no || table }
    persistDiningContext(data)
    return { ok: true, data }
  } catch (err) {
    return { ok: false, reason: err?.message || 'network_error' }
  }
}

// 后端对"本桌匿名身份失效/对不上号"统一用 409（跟 401/403 代表的"会员登录过期"
// 严格区分开），客户端据此判断要不要静默重建身份重试，而不是弹会员授权框。
export const isDiningIdentityError = (err) => String(err?.code || '') === '409'
