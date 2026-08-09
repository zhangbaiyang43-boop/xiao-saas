import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import router from '../router'
import { login as loginApi, logout as logoutApi, me } from '../api/auth'
import { stopActivePollers } from '../utils/polling'

const TOKEN_KEY = 'channel_access_token'
const PROFILE_KEY = 'channel_profile'
const CACHE_KEYS = [
  'channel_dashboard_cache',
  'channel_lead_cache',
  'channel_merchant_cache',
  'channel_commission_cache',
  'channel_settlement_cache',
]

function readProfile() {
  try {
    return JSON.parse(localStorage.getItem(PROFILE_KEY) || 'null')
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('channelAuth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const profile = ref(readProfile())
  const isAuthenticated = computed(() => Boolean(token.value))
  const isSuspended = computed(() => profile.value?.status === 'SUSPENDED')

  function setSession(data) {
    token.value = data?.token || ''
    profile.value = data?.partner || null
    if (token.value) localStorage.setItem(TOKEN_KEY, token.value)
    if (profile.value) localStorage.setItem(PROFILE_KEY, JSON.stringify(profile.value))
  }

  function clearSession() {
    token.value = ''
    profile.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(PROFILE_KEY)
    CACHE_KEYS.forEach((key) => localStorage.removeItem(key))
    stopActivePollers()
  }

  function restoreSession() {
    token.value = localStorage.getItem(TOKEN_KEY) || ''
    profile.value = readProfile()
  }

  async function login(payload) {
    const res = await loginApi(payload)
    if (res?.code === 200) setSession(res.data)
    return res
  }

  async function refreshProfile() {
    if (!token.value) return null
    const res = await me()
    if (res?.code === 200) {
      profile.value = res.data
      localStorage.setItem(PROFILE_KEY, JSON.stringify(res.data))
    }
    return res
  }

  async function logout() {
    try {
      if (token.value) await logoutApi()
    } finally {
      clearSession()
      router.replace('/login')
    }
  }

  function handleUnauthorized() {
    clearSession()
    router.replace('/login')
  }

  return {
    token,
    profile,
    isAuthenticated,
    isSuspended,
    login,
    logout,
    restoreSession,
    refreshProfile,
    clearSession,
    handleUnauthorized,
  }
})
