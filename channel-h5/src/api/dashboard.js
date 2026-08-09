import request from './request'

export const getDashboard = () => request.get('/v1/channel/dashboard')
