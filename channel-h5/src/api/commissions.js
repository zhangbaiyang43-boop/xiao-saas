import request from './request'

export const getCommissions = (params) => request.get('/v1/channel/commissions', { params })
export const getCommission = (id) => request.get(`/v1/channel/commissions/${id}`)
