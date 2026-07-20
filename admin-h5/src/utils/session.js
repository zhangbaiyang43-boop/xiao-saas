const TOKEN_KEY = 'token'
const TENANT__KEY = 'tenant_id'
const TENANT_NAME_KEY = 'tenant_name'
const TENANT_PHONE_KEY = 'tenant_phone'

const decodeJwtPayload = (token) => {
  try {
    const [, payload] = token.split('.')
    if (!payload) return null
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(window.atob(normalized))
  } catch (error) {
    return null
  }
}

export const saveSession = (data = {}) => {
  if (data.token) localStorage.setItem(TOKEN_KEY, data.token)
  if (data.tenant_id) localStorage.setItem(TENANT__KEY, data.tenant_id)
  if (data.name) localStorage.setItem(TENANT_NAME_KEY, data.name)
  if (data.phone) localStorage.setItem(TENANT_PHONE_KEY, data.phone)
}

export const clearSession = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(TENANT__KEY)
  localStorage.removeItem(TENANT_NAME_KEY)
  localStorage.removeItem(TENANT_PHONE_KEY)
}

export const getToken = () => localStorage.getItem(TOKEN_KEY)

export const getSession = () => ({
  token: localStorage.getItem(TOKEN_KEY),
  tenantId: localStorage.getItem(TENANT__KEY),
  tenantName: localStorage.getItem(TENANT_NAME_KEY),
  tenantPhone: localStorage.getItem(TENANT_PHONE_KEY)
})

export const isTokenExpired = (token = getToken()) => {
  if (!token) return true
  const payload = decodeJwtPayload(token)
  if (!payload?.exp) return true
  return payload.exp * 1000 <= Date.now()
}

export const hasValidSession = () => {
  const token = getToken()
  return Boolean(token) && !isTokenExpired(token)
}

export const redirectToLogin = (reason = '登录已过期，请重新登录') => {
  clearSession()
  const loginPath = `/login?reason=${encodeURIComponent(reason)}`
  if (window.location.pathname !== '/login') {
    window.location.href = loginPath
  }
}
