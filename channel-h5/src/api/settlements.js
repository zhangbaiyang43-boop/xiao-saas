import request from './request'

export const getSettlements = (params) => request.get('/v1/channel/settlements', { params })
export const getSettlement = (id) => request.get(`/v1/channel/settlements/${id}`)
