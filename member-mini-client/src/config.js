const ENV_CONFIG = {
  development: {
    apiBaseUrl: 'https://api.zhangbaiyang.com/api'
  },
  lan: {
    apiBaseUrl: 'http://192.168.1.2:9898/api'
  },
  production: {
    apiBaseUrl: 'https://api.zhangbaiyang.com/api'
  }
}

const ACTIVE_ENV = 'production'

export const config = {
  env: ACTIVE_ENV,
  ...ENV_CONFIG[ACTIVE_ENV]
}
