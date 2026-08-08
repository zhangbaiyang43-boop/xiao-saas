import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getAuthMe } from '../api'
import { clearSession, getSession, saveSession } from '../utils/session'

const ROLE_HOME = {
  owner: '/',
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
    // Legacy owner SMS sessions (no staff account_id) keep full access.
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

    role.value = nextRole
    permissions.value = nextPerms
    accountId.value = data.account_id ? String(data.account_id) : null
    displayName.value = data.name || data.tenant_name || ''
    username.value = data.username || ''
    homePath.value = nextHome
    loaded.value = true

    saveSession({
      token: data.token,
      tenant_id: data.tenant_id,
      name: data.tenant_name || data.name,
      phone: data.phone,
    })
    localStorage.setItem('role', nextRole)
    localStorage.setItem('permissions', JSON.stringify(nextPerms))
    localStorage.setItem('home_path', nextHome)
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
    loaded.value = false
    clearSession()
    ;['role', 'permissions', 'home_path', 'account_id', 'account_name', 'account_username'].forEach((k) => {
      localStorage.removeItem(k)
    })
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
    loaded,
    isOwner,
    can,
    applySession,
    clearAuth,
    hydrateFromServer,
  }
})
