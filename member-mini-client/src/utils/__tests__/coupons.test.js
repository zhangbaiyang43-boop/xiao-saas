import { describe, it, expect } from 'vitest'
import { pickUsableCoupons } from '../coupons.js'

// 现场问题：会员页/顶部横幅显示"2 张优惠券可用"，点「去结算」后券选择器"暂无可用"。
// 根因是 availableCoupons 被 loadMemberStatus（不过滤过期）和 refreshAvailableCoupons
// （按 expire_time 过滤）各写一份，谁后跑谁赢。两处统一走 pickUsableCoupons。

describe('pickUsableCoupons', () => {
  const HOUR = 3600 * 1000
  // 裸 UTC（无 Z），跟后端 expire_time 一致
  const naiveUtc = (ms) => new Date(ms).toISOString().replace(/\.\d+Z$/, '').replace('Z', '')

  it('非数组一律返回空数组', () => {
    expect(pickUsableCoupons(null)).toEqual([])
    expect(pickUsableCoupons(undefined)).toEqual([])
    expect(pickUsableCoupons({})).toEqual([])
  })

  it('未来到期的券保留，已过期的剔除（裸 UTC 按 UTC 解析，不差 8 小时）', () => {
    const list = [
      { id: 'future', status: 'UNUSED', expire_time: naiveUtc(Date.now() + 5 * HOUR) },
      { id: 'past', status: 'UNUSED', expire_time: naiveUtc(Date.now() - 1 * HOUR) },
    ]
    expect(pickUsableCoupons(list).map((c) => c.id)).toEqual(['future'])
  })

  it('没有到期时间的券视为不过期，保留（跟旧逻辑的 2099 兜底一致）', () => {
    expect(pickUsableCoupons([{ id: 'x', status: 'UNUSED' }]).map((c) => c.id)).toEqual(['x'])
  })

  it('无 status 字段的券也保留（信任调用方传的是 UNUSED 列表）', () => {
    expect(pickUsableCoupons([{ id: 'x' }]).map((c) => c.id)).toEqual(['x'])
  })

  it('status 明确不是 UNUSED 的剔除', () => {
    const list = [
      { id: 'used', status: 'USED', expire_time: naiveUtc(Date.now() + HOUR) },
      { id: 'ok', status: 'UNUSED', expire_time: naiveUtc(Date.now() + HOUR) },
    ]
    expect(pickUsableCoupons(list).map((c) => c.id)).toEqual(['ok'])
  })

  it('valid_end_time / end_time 也认', () => {
    const list = [
      { id: 'a', valid_end_time: naiveUtc(Date.now() + HOUR) },
      { id: 'b', end_time: naiveUtc(Date.now() - HOUR) },
    ]
    expect(pickUsableCoupons(list).map((c) => c.id)).toEqual(['a'])
  })

  it('到期时间解析不了的不误杀', () => {
    expect(pickUsableCoupons([{ id: 'x', expire_time: '不是日期' }]).map((c) => c.id)).toEqual(['x'])
  })
})
