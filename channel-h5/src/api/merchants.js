import request from './request'

export const getMerchants = (params) => request.get('/v1/channel/merchants', { params })
export const getMerchant = (id) => request.get(`/v1/channel/merchants/${id}`)
