import request from './request'

export const getMenuItems = (shopId) =>
  request({ url: '/v1/menu/items', method: 'GET', data: { shop: shopId } })

export const getShopInfo = (shopId) =>
  request({ url: '/v1/shop/info', method: 'GET', data: { shop: shopId } })

export const createOrder = (data, options = {}) =>
  request({ url: '/v1/orders', method: 'POST', data, authRedirect: options.authRedirect })

export const getOrderStatus = (orderId, participantToken) =>
  request({ url: '/v1/orders/my', method: 'GET', data: { order_id: orderId, participant_token: participantToken || undefined } })

export const cancelOrder = (orderId, participantToken) => {
  const query = participantToken ? `?participant_token=${encodeURIComponent(participantToken)}` : ''
  return request({ url: `/v1/orders/${orderId}/cancel${query}`, method: 'POST' })
}

export const mockPayOrder = (orderId, useBalance = false) =>
  request({ url: `/v1/orders/${orderId}/mock-pay`, method: 'POST', data: { use_balance: useBalance } })

export const createWxPayOrder = (orderId, useBalance = false, options = {}) =>
  request({
    url: `/v1/orders/${orderId}/pay`,
    method: 'POST',
    data: { use_balance: useBalance, js_code: options.js_code || undefined },
    authRedirect: options.authRedirect
  })

export const submitReview = (orderId, data) =>
  request({ url: `/v1/orders/${orderId}/review`, method: 'POST', data })

export const getCurrentDiningOrders = (data) =>
  request({ url: '/v1/dining-sessions/current/orders', method: 'GET', data })

export const requestTableCheckout = (data, options = {}) =>
  request({ url: '/v1/dining-sessions/checkout-request', method: 'POST', data, authRedirect: options.authRedirect })

