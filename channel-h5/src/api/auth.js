import request from './request'

export const requestCode = (data) => request.post('/v1/channel/auth/request-code', data)
export const login = (data) => request.post('/v1/channel/auth/login', data)
export const logout = () => request.post('/v1/channel/auth/logout')
export const me = () => request.get('/v1/channel/me')
