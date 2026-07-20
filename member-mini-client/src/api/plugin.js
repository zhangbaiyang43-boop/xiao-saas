import request from './request'

export const getAvailablePlugins = () => {
  return request({
    url: '/v1/plugins/available',
    method: 'GET'
  })
}
