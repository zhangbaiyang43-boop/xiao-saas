import { describe, it, expect, vi, beforeEach } from 'vitest'

// P0-16 Phase B1 -- T09: Mini error reports must carry the X-Request-ID
// response header (when a response exists) and the business client_request_id
// (when the outgoing request body carried one), so a customer-reported error
// can be correlated to the backend's own logs. Must not change P0-15's
// submit/retry/frozen-payload behavior -- this only adds metadata to the
// existing reportError extra objects, nothing else.

vi.mock('../../utils/monitor', () => ({
  reportError: vi.fn(),
}))
vi.mock('../../utils/perf', () => ({
  capturePerformanceContext: vi.fn(() => ({})),
  markEvent: vi.fn(),
  recordInvalidMeasurement: vi.fn(),
  recordSample: vi.fn(),
  validatePerformanceContext: vi.fn(() => 'valid'),
}))
vi.mock('../../config', () => ({ config: { apiBaseUrl: 'https://api.test' } }))

describe('P0-16 B1: request.js correlation metadata', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
    uni.getStorageSync.mockReturnValue('')
    uni.request = vi.fn()
  })

  it('T09a: business error response includes X-Request-ID and client_request_id in the reportError extra', async () => {
    const { reportError } = await import('../../utils/monitor')
    const request = (await import('../request.js')).default

    uni.request.mockImplementation((opts) => {
      opts.success({
        statusCode: 200,
        data: { code: 400, msg: '缺少shop参数' },
        header: { 'X-Request-ID': 'srv-req-abc123' },
      })
    })

    await expect(
      request({ url: '/v1/orders', method: 'POST', data: { request_id: 'client-K1', shop: 'tenant-a' } })
    ).rejects.toThrow()

    expect(reportError).toHaveBeenCalledWith(
      'api.error',
      expect.anything(),
      expect.objectContaining({ requestId: 'srv-req-abc123', clientRequestId: 'client-K1' }),
    )
  })

  it('T09b: a genuine network failure (no response at all) still includes client_request_id, and requestId is null (not an error)', async () => {
    const { reportError } = await import('../../utils/monitor')
    const request = (await import('../request.js')).default

    uni.request.mockImplementation((opts) => {
      opts.fail({ errMsg: 'request:fail timeout' })
    })

    await expect(
      request({ url: '/v1/orders', method: 'POST', data: { request_id: 'client-K2', shop: 'tenant-a' } })
    ).rejects.toThrow()

    expect(reportError).toHaveBeenCalledWith(
      'api.network_fail',
      expect.anything(),
      expect.objectContaining({ clientRequestId: 'client-K2', requestId: null }),
    )
  })

  it('T09c: never includes participant_token, openid, or phone in the correlation metadata', async () => {
    const { reportError } = await import('../../utils/monitor')
    const request = (await import('../request.js')).default

    uni.request.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 400, msg: 'x' }, header: {} })
    })

    await expect(
      request({
        url: '/v1/orders', method: 'POST',
        data: { request_id: 'client-K3', participant_token: 'secret-tok', openid: 'oSECRET' },
      })
    ).rejects.toThrow()

    const [, , extra] = reportError.mock.calls[0]
    expect(JSON.stringify(extra)).not.toContain('secret-tok')
    expect(JSON.stringify(extra)).not.toContain('oSECRET')
  })
})
