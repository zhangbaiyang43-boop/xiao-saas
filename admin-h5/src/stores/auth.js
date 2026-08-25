import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getAuthMe, staffDeviceLogin, staffLogoutDevice } from '../api'
import {
  clearDeviceCredential,
  getDeviceCredential,
  isCookieDeviceMode,
  saveDeviceCredential,
} from '../utils/deviceAuth'
import { clearSession, getSession, hasValidSession, saveSession } from '../utils/session'

const ROLE_HOME = {
  owner: '/',
  frontdesk: '/frontdesk',
  waiter: '/waiter',
  kitchen: '/kitchen',
}

export const useAuthStore = defineStore('auth', () => {
  const role = ref(localStorage.getItem('role') || 'owner')
  const accountId = ref(localStorage.getItem('account_id') || null)
  const permissions = ref(_readPermissions(role.value, accountId.value))
  const displayName = ref(localStorage.getItem('account_name') || getSession().tenantName || '')
  const username = ref(localStorage.getItem('account_username') || '')
  const homePath = ref(localStorage.getItem('home_path') || ROLE_HOME[role.value] || '/')
  const authMethod = ref(localStorage.getItem('auth_method') || '')
  const loaded = ref(false)

  const isOwner = computed(() => role.value === 'owner' && !accountId.value)

  function _readPermissions(currentRole, currentAccountId) {
    try {
      const raw = localStorage.getItem('permissions')
      const list = raw ? JSON.parse(raw) : []
      if (Array.isArray(list) && list.length) return list
    } catch {
      /* fall through */
    }
    if ((currentRole || 'owner') === 'owner' && !currentAccountId) return ['*']
    return []
  }

  function can(permission) {
    if (!permission) return false
    if (isOwner.value || permissions.value.includes('*')) return true
    return permissions.value.includes(permission)
  }

  function applySession(data = {}) {
    const nextRole = data.role || 'owner'
    const nextPerms = Array.isArray(data.permissions)
      ? data.permissions
      : nextRole === 'owner'
        ? ['*']
        : []
    const nextHome = data.home_path || ROLE_HOME[nextRole] || '/'
    const nextMethod = data.auth_method || authMethod.value || ''

    role.value = nextRole
    permissions.value = nextPerms
    accountId.value = data.account_id ? String(data.account_id) : null
    displayName.value = data.name || data.tenant_name || ''
    username.value = data.username || ''
    homePath.value = nextHome
    authMethod.value = nextMethod
    loaded.value = true

    saveSession({
      token: data.token,
      tenant_id: data.tenant_id,
      name: data.tenant_name || data.name,
      phone: data.phone,
    })
    // Cookie mode: never persist device_credential (and clear any legacy key).
    // JS mode: only then may store opaque credential from response.
    if (isCookieDeviceMode()) {
      clearDeviceCredential()
    } else if (data.device_credential) {
      saveDeviceCredential(data.device_credential)
    }
    localStorage.setItem('role', nextRole)
    localStorage.setItem('permissions', JSON.stringify(nextPerms))
    localStorage.setItem('home_path', nextHome)
    if (nextMethod) localStorage.setItem('auth_method', nextMethod)
    if (accountId.value) localStorage.setItem('account_id', accountId.value)
    else localStorage.removeItem('account_id')
    if (displayName.value) localStorage.setItem('account_name', displayName.value)
    if (username.value) localStorage.setItem('account_username', username.value)
  }

  function clearAuth() {
    role.value = 'owner'
    permissions.value = []
    accountId.value = null
    displayName.value = ''
    username.value = ''
    homePath.value = '/'
    authMethod.value = ''
    loaded.value = false
    clearSession()
    clearDeviceCredential()
    ;['role', 'permissions', 'home_path', 'account_id', 'account_name', 'account_username', 'auth_method'].forEach((k) => {
      localStorage.removeItem(k)
    })
    // CustomerList.vue's saved list context is keyed only by tenant_id (Phase-06-SEC:
    // the raw token was removed from that identity to stop persisting it into
    // sessionStorage). Same-tenant logout/re-login no longer changes the identity on
    // its own, so this must explicitly drop any stale context here.
    sessionStorage.removeItem('admin_customer_list_context')
  }

  async function tryDeviceRefresh() {
    try {
      const payload = isCookieDeviceMode()
        ? {}
        : { device_credential: getDeviceCredential() || undefined }
      if (!isCookieDeviceMode() && !payload.device_credential) return false
      const res = await staffDeviceLogin(payload)
      if (res?.code === 200 && res.data?.token) {
        applySession(res.data)
        return true
      }
    } catch {
      /* fall through */
    }
    if (!isCookieDeviceMode()) clearDeviceCredential()
    return false
  }

  async function ensureSession() {
    if (hasValidSession()) {
      if (!loaded.value) await hydrateFromServer()
      return true
    }
    return tryDeviceRefresh()
  }

  async function logoutCurrentDevice() {
    const payload = isCookieDeviceMode()
      ? {}
      : { device_credential: getDeviceCredential() || undefined }
    try {
      await staffLogoutDevice(payload)
    } catch {
      /* ignore */
    }
    clearAuth()
  }

  async function hydrateFromServer() {
    try {
      const res = await getAuthMe()
      if (res?.code === 200 && res.data) {
        applySession({ ...res.data, token: getSession().token, tenant_id: res.data.tenant_id })
        return true
      }
    } catch {
      /* keep local cache */
    }
    loaded.value = true
    return false
  }

  return {
    role,
    permissions,
    accountId,
    displayName,
    username,
    homePath,
    authMethod,
    loaded,
    isOwner,
    can,
    applySession,
    clearAuth,
    hydrateFromServer,
    tryDeviceRefresh,
    ensureSession,
    logoutCurrentDevice,
  }
})
