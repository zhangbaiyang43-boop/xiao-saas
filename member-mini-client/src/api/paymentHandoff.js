import request from './request'

export const resolvePaymentHandoff = (token) =>
  request({ url: `/v1/payment-handoffs/${encodeURIComponent(token)}`, method: 'GET', authRedirect: false })

export const claimPaymentHandoff = (token) =>
  request({ url: `/v1/payment-handoffs/${encodeURIComponent(token)}/claim`, method: 'POST', authRedirect: false })

export const payPaymentHandoff = (token, jsCode) =>
  request({
    url: `/v1/payment-handoffs/${encodeURIComponent(token)}/pay`,
    method: 'POST',
    data: { js_code: jsCode || undefined },
    authRedirect: false,
  })
