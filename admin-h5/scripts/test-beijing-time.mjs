/**
 * 时区契约：后端 naive UTC 时间戳（无 Z）必须按 UTC 解析、按北京时间(+08:00)展示。
 *
 * 现场问题：北京时间 11:13 下的单，界面显示成 03:13——整整差 8 小时。
 * 根因：saas-base 的 created_at = datetime.utcnow().isoformat()，没有 Z；
 * JS 里"带时间不带时区"的串按设备本地时区解析。
 */
import assert from 'node:assert/strict'
import {
  parseServerTime,
  formatBeijingTime,
  formatBeijingDate,
  formatBeijingDateTime,
  formatBeijingLong,
  formatBeijingClock,
  minutesSince,
  isBeijingToday,
  isBeijingThisMonth,
} from '../src/utils/beijingTime.js'

// 一笔北京时间 2026-08-27 11:13:45 下的单，后端存成 UTC 03:13:45，isoformat 无 Z
const NAIVE = '2026-08-27T03:13:45.123456'
const UTC_MS = Date.UTC(2026, 7, 27, 3, 13, 45)

assert.equal(parseServerTime(NAIVE).getTime(), UTC_MS + 123, 'naive 串必须按 UTC 解析')
assert.equal(parseServerTime('2026-08-27 03:13:45').getTime(), UTC_MS, '空格分隔的 naive 串同样处理')
assert.equal(parseServerTime('2026-08-27T03:13:45Z').getTime(), UTC_MS, '带 Z 不再补 Z')
assert.equal(parseServerTime('2026-08-27T11:13:45+08:00').getTime(), UTC_MS, '带 +08:00 落到同一时刻')
for (const bad of [null, undefined, '', '   ', 'not-a-date']) {
  assert.equal(parseServerTime(bad), null, `非法值 ${JSON.stringify(bad)} 返回 null`)
}

// 展示一律按北京时间，不受 process.env.TZ / 设备时区影响
assert.equal(formatBeijingTime(NAIVE), '11:13', 'formatBeijingTime = 北京 11:13，不是 03:13')
assert.equal(formatBeijingDate(NAIVE), '2026-08-27', 'formatBeijingDate')
assert.equal(formatBeijingDateTime(NAIVE), '2026-08-27 11:13', 'formatBeijingDateTime')
assert.equal(formatBeijingLong(NAIVE), '2026年8月27日 11:13', 'formatBeijingLong')

// 跨天：北京时间昨天 23:30（= UTC 15:30）下的单，不能显示成"刚下的"
const now = new Date(Date.UTC(2026, 7, 27, 2, 0, 0)) // 北京 08-27 10:00
assert.equal(formatBeijingClock('2026-08-26T15:30:00', now), '昨天 23:30', 'formatBeijingClock 跨天补「昨天」')
assert.equal(formatBeijingClock('2026-08-27T01:00:00', now), '09:00', '同一北京日只给 HH:mm')

// minutesSince 按真实时刻算
assert.equal(minutesSince('2026-08-27T01:30:00', now), 30, 'minutesSince = 30 分钟')
assert.equal(minutesSince(null), null, 'minutesSince 非法值 null')

// isBeijingToday / isBeijingThisMonth 按北京日历判断
assert.equal(isBeijingToday('2026-08-27T01:00:00', now), true, '北京同一天')
assert.equal(isBeijingToday('2026-08-26T15:30:00', now), false, '北京昨天不算今天')
assert.equal(isBeijingThisMonth('2026-08-01T00:00:00', now), true, '北京本月')
// UTC 07-31 20:00 = 北京 08-01 04:00 → 属于 8 月（这正是修复要的效果）
assert.equal(isBeijingThisMonth('2026-07-31T20:00:00', now), true, 'naive 串按 UTC → 北京已跨到 8 月')
// UTC 07-31 10:00 = 北京 07-31 18:00 → 仍是 7 月，不是本月
assert.equal(isBeijingThisMonth('2026-07-31T10:00:00', now), false, '北京 7 月不算本月')

console.log('TEST-FE beijingTime: passed')
