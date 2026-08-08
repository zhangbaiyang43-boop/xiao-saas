import request from './request'
import { config } from '../config'

/** 顾客自助取号（需 customer_token；openid 由服务端从 token 读取） */
export const createCustomerQueueTicket = (data, options = {}) =>
  request({
    // apiBaseUrl 已带 /api，这里不要再写 /api 前缀，否则会打成 /api/api/queue/... 导致 404
    url: '/queue/customer-tickets',
    method: 'POST',
    data,
    authRedirect: options.authRedirect !== false,
  })

/**
 * 按 query_token 查排队进度。
 * /queue/status 返回 {success,data}，与 v1 的 {code:200} 不同，这里单独适配。
 */
export const getQueueTicketStatusByToken = (token) =>
  new Promise((resolve, reject) => {
    uni.request({
      url: `${config.apiBaseUrl}/queue/status`,
      method: 'GET',
      data: { token },
      success: (res) => {
        const body = res.data || {}
        if (res.statusCode >= 200 && res.statusCode < 300 && body.success && body.data) {
          resolve({ code: 200, data: body.data, msg: body.message || 'ok' })
          return
        }
        reject(new Error(body.message || '排队查询已失效'))
      },
      fail: (err) => reject(new Error(err?.errMsg || '网络不稳定，请再试一次')),
    })
  })