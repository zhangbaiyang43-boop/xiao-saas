import request from './request'

export const createLead = (data) => request.post('/v1/channel/leads', data)
export const getLeads = (params) => request.get('/v1/channel/leads', { params })
export const getLead = (id) => request.get(`/v1/channel/leads/${id}`)
