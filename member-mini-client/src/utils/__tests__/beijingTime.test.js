import { describe, it, expect } from 'vitest'
import {
  parseServerTime,
  formatBeijingTime,
  formatBeijingDate,
  formatBeijingDateTime,
  formatBeijingClock,
} from '../beijingTime.js'

// 现场问题：北京时间 11:13 下的单，小程序里显示成 03:13——整整差 8 小时。
//
// saas-base 的 created_at 是 Column(DateTime, default=datetime.utcnow)，
// 存 naive UTC，isoformat() 出来没有 Z。JS 规范里"带时间但不带时区"的字符串
// 按本地时间解析，于是 new Date('2026-08-27T03:13:45') 被当成本地 03:13。
//
// 修法两步缺一不可：补 Z 让它按 UTC 解析；再显式按 +08:00 格式化
// （不能用设备本地时区——顾客可能不在中国，但门店只有北京时间一个口径）。

describe('parseServerTime：后端 naive UTC 必须按 UTC 解析', () => {
  it('无时区后缀的 ISO 串按 UTC 解析，不按设备本地时区', () => {
    // 2026-08-27T03:13:45Z 的毫秒时间戳
    const expected = Date.UTC(2026, 7, 27, 3, 13, 45)
    expect(parseServerTime('2026-08-27T03:13:45').getTime()).toBe(expected)
    expect(parseServerTime('2026-08-27T03:13:45.123456').getTime()).toBe(expected + 123)
  })

  it('空格分隔的 naive 串同样处理（部分接口返回这种格式）', () => {
    expect(parseServerTime('2026-08-27 03:13:45').getTime()).toBe(Date.UTC(2026, 7, 27, 3, 13, 45))
  })

  it('已经带时区的串不再补 Z，原样按其自身时区解析', () => {
    expect(parseServerTime('2026-08-27T03:13:45Z').getTime()).toBe(Date.UTC(2026, 7, 27, 3, 13, 45))
    // +08:00 的 11:13 就是 UTC 的 03:13，两者必须落到同一个时刻
    expect(parseServerTime('2026-08-27T11:13:45+08:00').getTime()).toBe(Date.UTC(2026, 7, 27, 3, 13, 45))
  })

  it('Date 对象 / 数字时间戳原样接受', () => {
    const d = new Date(Date.UTC(2026, 7, 27, 3, 13))
    expect(parseServerTime(d).getTime()).toBe(d.getTime())
    expect(parseServerTime(d.getTime()).getTime()).toBe(d.getTime())
  })

  it('空值和非法值返回 null，不抛错也不返回 Invalid Date', () => {
    for (const bad of [null, undefined, '', '   ', 'not-a-date']) {
      expect(parseServerTime(bad)).toBeNull()
    }
  })
})

describe('按北京时间格式化（+08:00），不用设备本地时区', () => {
  // 现场那一单：后端 03:13 UTC，实际是北京 11:13。
  const NAIVE_UTC = '2026-08-27T03:13:45'

  it('formatBeijingTime 把 UTC 03:13 显示成北京 11:13', () => {
    expect(formatBeijingTime(NAIVE_UTC)).toBe('11:13')
  })

  it('formatBeijingDate / formatBeijingDateTime 同一口径', () => {
    expect(formatBeijingDate(NAIVE_UTC)).toBe('2026-08-27')
    expect(formatBeijingDateTime(NAIVE_UTC)).toBe('2026-08-27 11:13')
  })

  it('跨日：UTC 前一天的深夜是北京当天的早上', () => {
    // UTC 2026-08-26 17:00 = 北京 2026-08-27 01:00
    expect(formatBeijingDateTime('2026-08-26T17:00:00')).toBe('2026-08-27 01:00')
  })

  it('跨日：UTC 当天的 16:00 已经是北京次日 00:00', () => {
    expect(formatBeijingDateTime('2026-08-27T16:00:00')).toBe('2026-08-28 00:00')
  })

  it('非法值返回空串，界面不会出现 NaN:NaN', () => {
    expect(formatBeijingTime('')).toBe('')
    expect(formatBeijingTime('not-a-date')).toBe('')
    expect(formatBeijingDateTime(null)).toBe('')
  })
})

describe('formatBeijingClock：跨天的单不能看着像刚下的', () => {
  // 一桌可能跨天（长会话、隔夜测试单）。只给 HH:mm 会让昨晚的单
  // 和刚才的单在界面上分不出来。
  const now = parseServerTime('2026-08-27T03:13:45') // 北京 2026-08-27 11:13

  it('当天的单只给时分', () => {
    expect(formatBeijingClock('2026-08-27T02:00:00', now)).toBe('10:00')
  })

  it('昨天的单补「昨天」', () => {
    // UTC 2026-08-26 11:38 = 北京 2026-08-26 19:38（相对 now 是昨天）
    expect(formatBeijingClock('2026-08-26T11:38:00', now)).toBe('昨天 19:38')
  })

  it('更早的单补月日', () => {
    expect(formatBeijingClock('2026-08-20T11:38:00', now)).toBe('8月20日 19:38')
  })

  it('"昨天"按北京时间的日历日判断，不按 UTC 的', () => {
    // UTC 2026-08-26 17:30 其实已经是北京 2026-08-27 01:30，属于"今天"
    expect(formatBeijingClock('2026-08-26T17:30:00', now)).toBe('01:30')
  })

  it('非法值返回空串', () => {
    expect(formatBeijingClock(null, now)).toBe('')
  })
})
