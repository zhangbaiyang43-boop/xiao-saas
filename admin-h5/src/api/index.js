import request from './request'

export const api = request

export const login = (data) => request.post('/v1/login', data)
export const sendLoginCode = (data) => request.post('/v1/login/code', data)
export const registerTenant = (data) => request.post('/v1/register', data)
export const logoutTenant = () => request.post('/v1/tenant/logout')
export const getTenantProfile = () => request.get('/v1/tenant/profile')
export const updateTenantProfile = (data) => request.put('/v1/tenant/profile', data)
export const getTenantSettings = () => request.get('/v1/tenant/settings')
export const updateTenantSettings = (data) => request.put('/v1/tenant/settings', data)
export const getMarketingPreview = () => request.get('/v1/tenant/marketing-preview')
export const changeTenantPassword = (data) => request.put('/v1/tenant/password', data)
export const getPrinterConfig = () => request.get('/v1/tenant/printer')
export const updatePrinterConfig = (data) => request.patch('/v1/tenant/printer', data)

export const getCustomers = (params) => request.get('/v1/customers/', { params })
export const createCustomer = (data) => request.post('/v1/customers/', data)
export const updateCustomer = (id, data) => request.put(`/v1/customers/${id}`, data)
export const updateCustomerStatus = (id, data) => request.put(`/v1/customers/${id}/status`, data)
export const restoreCustomer = (id) => request.post(`/v1/customers/${id}/restore`)
export const deleteCustomer = (id) => request.delete(`/v1/customers/${id}`)
export const mergeCustomers = (data) => request.post('/v1/customers/merge', data)
export const getCustomer = (id) => request.get(`/v1/customers/${id}`)
export const getCustomerIdentities = (id) => request.get(`/v1/customers/${id}/identities`)
export const getCustomerOperationLogs = (id, params) => request.get(`/v1/customers/${id}/operation-logs`, { params })
export const getCustomerTimeline = (id) => request.get(`/v1/customers/${id}/timeline`)
export const getCustomerTags = () => request.get('/v1/customers/tags')
export const getCustomerStats = () => request.get('/v1/customers/stats')

export const getConsumptions = (params) => request.get('/v1/consumptions/', { params })
export const createConsumption = (data) => request.post('/v1/consumptions/', data)

export const getCouponTemplates = (params) => request.get('/v1/coupon-templates/', { params })
export const createCouponTemplate = (data) => request.post('/v1/coupon-templates/', data)
export const updateCouponTemplate = (id, data) => request.put(`/v1/coupon-templates/${id}`, data)
export const deleteCouponTemplate = (id) => request.delete(`/v1/coupon-templates/${id}`)
export const getCouponTemplate = (id) => request.get(`/v1/coupon-templates/${id}`)

export const sendCoupons = (data) => request.post('/v1/coupons/send', data)
export const batchRecallCoupons = (params) => request.post('/v1/coupons/recall-batch', null, { params })
export const getCustomerCoupons = (params) => request.get('/v1/coupons/', { params })
export const getIssuedCoupons = (params) => request.get('/v1/coupons/issued', { params })
export const recallCoupon = (id, data) => request.post(`/v1/coupons/${id}/recall`, data)

export const verifyCoupon = (data) => request.post('/v1/verify', data)
export const getVerifyRecords = (params) => request.get('/v1/verify/records', { params })
export const revokeVerifyRecord = (id, data) => request.post(`/v1/verify/${id}/revoke`, data)
export const markVerifyRecordAbnormal = (id, data) => request.post(`/v1/verify/${id}/abnormal`, data)
export const getPosVerifyConfig = () => request.get('/v1/pos/config')
export const resetPosApiKey = () => request.post('/v1/pos/api-key/reset')

export const getEntranceCodes = (params) => request.get('/v1/entrance-codes/', { params })
export const createEntranceCode = (data) => request.post('/v1/entrance-codes/', data)
export const updateEntranceCodeStatus = (id, data) => request.put(`/v1/entrance-codes/${id}/status`, data)
export const deleteEntranceCode = (id) => request.delete(`/v1/entrance-codes/${id}`)
export const getEntranceCodeSummary = () => request.get('/v1/entrance-codes/summary')
export const regenerateEntranceCode = (id) => request.put(`/v1/entrance-codes/${id}/regenerate`)

export const getChannelEntries = (params) => request.get('/v1/channel-entries/', { params })
export const getChannelEntry = (id) => request.get(`/v1/channel-entries/${id}`)
export const createChannelEntry = (data) => request.post('/v1/channel-entries/', data)
export const updateChannelEntry = (id, data) => request.put(`/v1/channel-entries/${id}`, data)
export const deleteChannelEntry = (id) => request.delete(`/v1/channel-entries/${id}`)
export const toggleChannelEntryStatus = (id) => request.patch(`/v1/channel-entries/${id}/status`)
export const getChannelOptions = () => request.get('/v1/channel-entries/options/channels')

export const getWeworkConfigStatus = () => request.get('/v1/wework/config/status')
export const testWeworkAccessToken = () => request.post('/v1/wework/access-token/test')
export const createWeworkContactWay = (data) => request.post('/v1/wework/contact-way', data)
export const getWeworkContactWays = (params) => request.get('/v1/wework/contact-way', { params })
export const getWeworkEvents = (params) => request.get('/v1/wework/events', { params })

export const getDashboardStats = () => request.get('/v1/stats/dashboard')
export const getMerchantSystemStatus = () => request.get('/v1/merchant/system-status')

export const getDistributionSettings = () => request.get('/v1/distribution/settings')
export const updateDistributionSettings = (data) => request.put('/v1/distribution/settings', data)
export const getDistributionRecords = (params) => request.get('/v1/distribution/records', { params })
export const settleDistributionRecord = (id) => request.post(`/v1/distribution/records/${id}/settle`)

export const getMembershipConfig = () => request.get('/v1/membership/config')
export const getCustomerMembership = (id) => request.get(`/v1/membership/customers/${id}`)

export const getShopInfo = (shopId) => request.get('/v1/shop/info', { params: { shop: shopId } })

export const getMenuItems = (params) => request.get('/v1/menu/items', { params })
export const createMenuItem = (data) => request.post('/v1/menu/items', data)
export const updateMenuItem = (id, data) => request.put(`/v1/menu/items/${id}`, data)
export const deleteMenuItem = (id) => request.delete(`/v1/menu/items/${id}`)
export const updateMenuItemStock = (id, stock) => request.patch(`/v1/menu/items/${id}/stock`, { stock })
export const parseMenuText = (text) => request.post('/v1/menu/parse-text', { text })
export const importMenuBatch = (items) => request.post('/v1/menu/import-batch', { items })
export const generateDishDesc = (data) => request.post('/v1/menu/generate-desc', data)
export const getAiDailyAnalysis = () => request.post('/v1/stats/ai-analysis')
export const uploadDishImage = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return request.post('/v1/menu/upload-image', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export const createOrder = (data) => request.post('/v1/orders', data)
export const getOrders = (params, config = {}) => request.get('/v1/orders', { ...config, params })
export const updateOrderStatus = (id, status) => request.patch(`/v1/orders/${id}/status`, { status })
export const mockPayOrder = (id) => request.post(`/v1/orders/${id}/mock-pay`)
export const createWxPayOrder = (id, data = {}) => request.post(`/v1/orders/${id}/pay`, data)
export const updateMerchantNote = (id, note) => request.patch(`/v1/orders/${id}/note`, { note })
export const settleTable = (table_no) => request.post('/v1/orders/settle-table', { table_no })
export const getReviews = () => request.get('/v1/orders/reviews')

export const getAvailablePlugins = () => request.get('/v1/plugins/available')
export const getInstalledPlugins = () => request.get('/v1/plugins/installed')
export const getPluginLifecycle = () => request.get('/v1/plugins/lifecycle')
export const getPluginMenus = () => request.get('/v1/plugins/menus')
export const installPlugin = (data) => request.post('/v1/plugins/install', data)
export const enablePlugin = (data) => request.post('/v1/plugins/enable', data)
export const disablePlugin = (data) => request.post('/v1/plugins/disable', data)
export const uninstallPlugin = (data) => request.post('/v1/plugins/uninstall', data)
export const updatePluginConfig = (pluginCode, data) => request.put(`/v1/plugins/${pluginCode}/config`, data)

export const createQueueTicket = (data) => request.post('/queue/tickets', data)
export const getQueueTickets = (params) => request.get('/queue/tickets', { params })
export const callNextQueueTicket = (data) => request.post('/queue/call-next', data)
export const seatQueueTicket = (id, params) => request.post(`/queue/tickets/${id}/seat`, null, { params })
export const skipQueueTicket = (id, params) => request.post(`/queue/tickets/${id}/skip`, null, { params })
export const getQueueStatus = (params, config = {}) => request.get('/queue/status', { ...config, params })
export const getQueueTicketStatusByToken = (token, config = {}) => request.get('/queue/status', { ...config, params: { token } })
export const printTestQueueTicket = () => request.post('/queue/print-test')


