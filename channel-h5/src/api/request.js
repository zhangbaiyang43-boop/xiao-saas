import axios from 'axios'
import { showFailToast } from 'vant'
import { useAuthStore } from '../stores/auth'
import { sanitizeSelfParams } from '../utils/selfScope'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

const request = axios.create({
  baseURL,
  timeout: 10000,
})

request.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  if (config.params) config.params = sanitizeSelfParams(config.params)
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore().handleUnauthorized()
      return Promise.reject(error)
    }
    if (error.response?.status === 403) {
      showFailToast(error.response?.data?.msg || '当前账号无此权限')
    }
    return Promise.reject(error)
  },
)

export default request
