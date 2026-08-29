import { parseServerTime } from './beijingTime'

// 唯一的"这张券现在能不能用"口径。
//
// 背景（这个坑刚踩过）：availableCoupons 被两个函数各写一份——loadMemberStatus
// 原样塞 /member/coupons 的返回（不看过期），openCart 里的 refreshAvailableCoupons
// 又按 expire_time 过滤一遍。谁后跑谁赢，于是"会员页显示 2 张、结算页 0 张"。
// 两处都改成调这一个函数，会员页 / 顶部横幅 / 确认订单 / 券选择器就永远一致。
//
// 过期判断走 parseServerTime：后端 expire_time 是裸 UTC（没有 Z），
// 直接 new Date() 会按本地时区解析、差 8 小时，把没过期的判成过期。
export function pickUsableCoupons(rawList) {
  if (!Array.isArray(rawList)) return []
  const now = Date.now()
  return rawList.filter((c) => {
    if (!c) return false
    if (c.status && c.status !== 'UNUSED') return false
    const raw = c.expire_time || c.valid_end_time || c.end_time
    if (!raw) return true // 没有到期时间 = 不过期
    const end = parseServerTime(raw)
    return !end || end.getTime() > now // 解析不了就别误杀，交给后端/结算兜底
  })
}
