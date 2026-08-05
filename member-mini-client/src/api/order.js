import request from './request'

export const getMenuItems = (shopId) =>
  request({ url: '/v1/menu/items', method: 'GET', data: { shop: shopId } })

export const getShopInfo = (shopId) =>
  request({ url: '/v1/shop/info', method: 'GET', data: { shop: shopId } })

export const createOrder = (data, options = {}) =>
  request({ url: '/v1/orders', method: 'POST', data, authRedirect: options.authRedirect })

// authRedirect:false——这个接口靠 participant_token（扫码进店的会话令牌）鉴权，跟会员
// 登录的 customer_token 是两套完全独立的身份体系。桌台会话过期/participant_token 失效
// 时后端会返回 401/403，这跟"会员登录过期"毫无关系，不该触发 request() 里默认的
// redirectToGuest（清 customer_token、跳转 /pages/mine/mine）。之前没传这个参数，
// 会导致这里轮询到一次 401 就把用户强制踢去"我的"页面，而"我的"页面 onShow 时又会
// 用同一个过期的 participant_token 再拉一次订单状态、再触发一次跳转，死循环刷新。
export const getOrderStatus = (orderId, participantToken) =>
  request({ url: '/v1/orders/my', method: 'GET', data: { order_id: orderId, participant_token: participantToken || undefined }, authRedirect: false })

export const cancelOrder = (orderId, participantToken) => {
  const query = participantToken ? `?participant_token=${encodeURIComponent(participantToken)}` : ''
  return request({ url: `/v1/orders/${orderId}/cancel${query}`, method: 'POST' })
}

export const mockPayOrder = (orderId, useBalance = false, participantToken) =>
  request({ url: `/v1/orders/${orderId}/mock-pay`, method: 'POST', data: { use_balance: useBalance, participant_token: participantToken || undefined } })

export const createWxPayOrder = (orderId, useBalance = false, options = {}) =>
  request({
    url: `/v1/orders/${orderId}/pay`,
    method: 'POST',
    data: { use_balance: useBalance, js_code: options.js_code || undefined, participant_token: options.participant_token || undefined },
    authRedirect: options.authRedirect
  })

export const submitReview = (orderId, data) =>
  request({ url: `/v1/orders/${orderId}/review`, method: 'POST', data })

export const getCurrentDiningOrders = (data) =>
  request({ url: '/v1/dining-sessions/current/orders', method: 'GET', data })

export const requestTableCheckout = (data, options = {}) =>
  request({ url: '/v1/dining-sessions/checkout-request', method: 'POST', data, authRedirect: options.authRedirect })

