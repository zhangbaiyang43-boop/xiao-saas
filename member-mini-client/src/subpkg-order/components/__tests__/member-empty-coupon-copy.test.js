import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const memberCard = readFileSync(path.resolve(here, '../MemberCard.vue'), 'utf8')
const couponList = readFileSync(
  path.resolve(here, '../../../subpkg-coupon/pages/list.vue'),
  'utf8',
)

describe('zero-coupon copy', () => {
  it('keeps 去点餐 on the member card and drops the 0-available title', () => {
    expect(memberCard).toContain("$emit('go-order')")
    expect(memberCard).toContain('memberActionTitle')
    expect(memberCard).toContain("'去点餐，结算自动用优惠'")
    expect(memberCard).not.toContain('您有{{ bannerInfo.couponCount }}张优惠券可用')
  })

  it('adds StateEmpty 去点餐 only on the unused coupon tab', () => {
    expect(couponList).toContain(':action-text="emptyActionText"')
    expect(couponList).toContain("activeTab.value === 'UNUSED' ? '去点餐' : ''")
    expect(couponList).toContain('@action="goOrder"')
    expect(couponList).toContain('去点餐后，结算会自动用上最划算的一张')
  })
})
