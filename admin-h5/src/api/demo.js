import demoRequest from './demoRequest'


export const startDemoSession = (launchCode) => (
  demoRequest.post('/v1/demo/sessions/start', { launchCode })
)

export const getDemoSession = () => demoRequest.get('/v1/demo/session')

export const updateDemoOrderStatus = (orderId, status) => (
  demoRequest.patch(`/v1/demo/orders/${orderId}/status`, { status })
)

export const serveDemoOrder = (orderId) => (
  demoRequest.post(`/v1/demo/orders/${orderId}/serve`)
)
