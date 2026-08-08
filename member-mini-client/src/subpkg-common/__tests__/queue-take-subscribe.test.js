import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * 取号页手势链契约：提交前必须 requestSubscribeMessage，且走顾客取号接口。
 * 页面本身是 Vue SFC，这里用源码契约测试锁住关键调用，避免授权被误删。
 */
describe('queue-take subscribe gesture', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('取号页源码包含订阅授权与顾客取号调用', () => {
    const src = readFileSync(
      join(__dirname, '../pages/queue-take.vue'),
      'utf8',
    )
    expect(src).toContain('requestSubscribeMessage')
    expect(src).toContain('createCustomerQueueTicket')
    expect(src).toContain('queue_reminder_template_id')
    expect(src).toContain('tmplIds')
  })

  it('pages.json 注册了排队取号页', () => {
    const pages = JSON.parse(
      readFileSync(join(__dirname, '../../pages.json'), 'utf8'),
    )
    const common = pages.subPackages.find((p) => p.root === 'subpkg-common')
    const paths = (common?.pages || []).map((p) => p.path)
    expect(paths).toContain('pages/queue-take')
  })
})
