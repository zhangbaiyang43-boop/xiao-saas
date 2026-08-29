import axios from 'axios'

import { clearDemoSession, DEMO_SESSION_KEY, readDemoSession } from '../demo/session'
import { resolveApiBaseURL } from './apiBaseUrl'


const demoRequest = axios.create({
  baseURL: resolveApiBaseURL(),
  timeout: 10000,
})

demoRequest.interceptors.request.use((config) => {
  const session = readDemoSession(sessionStorage)
  if (session?.demoToken) {
    config.headers.Authorization = `Bearer ${session.demoToken}`
  }
  return config
})

demoRequest.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if ([401, 403].includes(error.response?.status)) {
      clearDemoSession(sessionStorage)
    }
    return Promise.reject(error)
  },
)

export { DEMO_SESSION_KEY }
export default demoRequest
