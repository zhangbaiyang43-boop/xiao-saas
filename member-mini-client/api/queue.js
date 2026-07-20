import request from './request'

export const createQueueTicket = (data) => request({ url: '/queue/tickets', method: 'POST', data })
export const getQueueTickets = (params) => request({ url: '/queue/tickets', method: 'GET', data: params })
export const getQueueStatus = (params) => request({ url: '/queue/status', method: 'GET', data: params })