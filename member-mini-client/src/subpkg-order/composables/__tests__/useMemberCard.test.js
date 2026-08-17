import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useMemberCard } from '../useMemberCard.js'

function setup(overrides = {}) {
  const shopCreatedAt = ref('2022-03-01T00:00:00Z')
  const formatPrice = (n) => n.toFixed(2)
  const onGoOrder = vi.fn()
  const onUseCoupon = vi.fn()
  const card = useMemberCard({ shopCreatedAt, formatPrice, onGoOrder, onUseCoupon, ...overrides })
  return { shopCreatedAt, onGoOrder, onUseCoupon, card }
}

describe('useMemberCard', () => {
  describe('memberSinceText', () => {
    it('店铺创建时间合法时展示"会员自 X 年"', () => {
      const { card } = setup()
      expect(card.memberSinceText.value).toBe('会员自 2022 年')
    })

    it('店铺创建时间是非法日期时返回空字符串，不展示脏文案', () => {
      const shopCreatedAt = ref('')
      const { card } = setup({ shopCreatedAt })
      expect(card.memberSinceText.value).toBe('')
    })
  })

  describe('memberLevelLabel / memberLevelBadgeSrc', () => {
    it('还没有 bannerInfo 时按普通会员/LV1 兜底', () => {
      const { card } = setup()
      expect(card.memberLevelLabel.value).toBe('普通会员')
      expect(card.memberLevelBadgeSrc.value).toBe('/static/member-levels/level-lv1.png')
    })

    it('bannerInfo 有等级信息时展示对应文案和徽章', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelLabel: '黄金会员', levelCode: 'LV3' }
      expect(card.memberLevelLabel.value).toBe('黄金会员')
      expect(card.memberLevelBadgeSrc.value).toBe('/static/member-levels/level-lv3.png')
    })

    it('等级码不在已知映射里时按 LV1 兜底，不留空图', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelLabel: '神秘等级', levelCode: 'LV99' }
      expect(card.memberLevelBadgeSrc.value).toBe('/static/member-levels/level-lv1.png')
    })
  })

  describe('memberIdentityCardBgSrc / memberIdentityCardTintStyle', () => {
    // 真机微信运行时证实：动态 inline style 里 background-image: url('/static/...jpg')
    // 加载不出来，改成真正的 <image :src>，tint 单独出一份不含 url(...) 的纯色渐变。
    it('返回对象里存在 memberIdentityCardBgSrc 和 memberIdentityCardTintStyle', () => {
      const { card } = setup()
      expect(card.memberIdentityCardBgSrc).toBeDefined()
      expect(card.memberIdentityCardTintStyle).toBeDefined()
    })

    it('LV1 会员卡背景 src 是 card-bg-lv1.jpg，tint 是对应 rgba，不含 url(', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV1' }
      expect(card.memberIdentityCardBgSrc.value).toBe('/static/member-levels/card-bg-lv1.jpg')
      expect(card.memberIdentityCardTintStyle.value).toContain('rgba(6,163,94')
      expect(card.memberIdentityCardTintStyle.value).not.toContain('url(')
      expect(card.memberIdentityCardTintStyle.value).not.toContain('background-image')
    })

    it('LV2 会员卡背景 src 是 card-bg-lv2.jpg，tint 是对应 rgba，不含 url(', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV2' }
      expect(card.memberIdentityCardBgSrc.value).toBe('/static/member-levels/card-bg-lv2.jpg')
      expect(card.memberIdentityCardTintStyle.value).toContain('rgba(100,112,128')
      expect(card.memberIdentityCardTintStyle.value).not.toContain('url(')
      expect(card.memberIdentityCardTintStyle.value).not.toContain('background-image')
    })

    it('LV3 会员卡背景 src 是 card-bg-lv3.jpg，tint 是对应 rgba，不含 url(', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV3' }
      expect(card.memberIdentityCardBgSrc.value).toBe('/static/member-levels/card-bg-lv3.jpg')
      expect(card.memberIdentityCardTintStyle.value).toContain('rgba(176,130,32')
      expect(card.memberIdentityCardTintStyle.value).not.toContain('url(')
      expect(card.memberIdentityCardTintStyle.value).not.toContain('background-image')
    })

    it('还没有 bannerInfo 时按 LV1 兜底', () => {
      const { card } = setup()
      expect(card.memberIdentityCardBgSrc.value).toBe('/static/member-levels/card-bg-lv1.jpg')
      expect(card.memberIdentityCardTintStyle.value).toContain('rgba(6,163,94')
    })

    it('等级码不在已知映射里时按 LV1 兜底，不留空背景', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV99' }
      expect(card.memberIdentityCardBgSrc.value).toBe('/static/member-levels/card-bg-lv1.jpg')
      expect(card.memberIdentityCardTintStyle.value).toContain('rgba(6,163,94')
    })
  })

  describe('memberIdentityCardForegroundStyle', () => {
    // 真机验证：原来跨等级统一用的浅金色文字（#f3e6cf 系）在 LV1 的亮绿底上
    // 对比度不够，发虚。改成每个等级各自一套深色文字，通过 CSS 变量单一入口下发。
    it('返回对象里存在 memberIdentityCardForegroundStyle', () => {
      const { card } = setup()
      expect(card.memberIdentityCardForegroundStyle).toBeDefined()
    })

    it('LV1 前景色变量：primary #123B2A / secondary #35634F / tertiary #527563', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV1' }
      const style = card.memberIdentityCardForegroundStyle.value
      expect(style).toContain('--member-text-primary:#123B2A')
      expect(style).toContain('--member-text-secondary:#35634F')
      expect(style).toContain('--member-text-tertiary:#527563')
    })

    it('LV2 前景色变量：primary #26323A / secondary #53616B / tertiary #6F7B83', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV2' }
      const style = card.memberIdentityCardForegroundStyle.value
      expect(style).toContain('--member-text-primary:#26323A')
      expect(style).toContain('--member-text-secondary:#53616B')
      expect(style).toContain('--member-text-tertiary:#6F7B83')
    })

    it('LV3 前景色变量：primary #4A3210 / secondary #715224 / tertiary #8A6A37', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV3' }
      const style = card.memberIdentityCardForegroundStyle.value
      expect(style).toContain('--member-text-primary:#4A3210')
      expect(style).toContain('--member-text-secondary:#715224')
      expect(style).toContain('--member-text-tertiary:#8A6A37')
    })

    it('还没有 bannerInfo 时按 LV1 兜底', () => {
      const { card } = setup()
      expect(card.memberIdentityCardForegroundStyle.value).toContain('--member-text-primary:#123B2A')
    })

    it('等级码不在已知映射里时按 LV1 兜底', () => {
      const { card } = setup()
      card.bannerInfo.value = { levelCode: 'LV99' }
      expect(card.memberIdentityCardForegroundStyle.value).toContain('--member-text-primary:#123B2A')
    })
  })

  describe('memberProgressPercent', () => {
    it('没有下一级门槛时进度为 0，不做除以 0 的运算', () => {
      const { card } = setup()
      card.bannerInfo.value = { growth: 50, nextGrowth: 0 }
      expect(card.memberProgressPercent.value).toBe(0)
    })

    it('正常按 growth/nextGrowth 算百分比并四舍五入', () => {
      const { card } = setup()
      card.bannerInfo.value = { growth: 300, nextGrowth: 1000 }
      expect(card.memberProgressPercent.value).toBe(30)
    })

    it('已经超过下一级门槛时封顶在 100，不超百分百', () => {
      const { card } = setup()
      card.bannerInfo.value = { growth: 1500, nextGrowth: 1000 }
      expect(card.memberProgressPercent.value).toBe(100)
    })
  })

  describe('memberUpgradeText', () => {
    it('还差一定金额升级时展示提示文案', () => {
      const { card } = setup()
      card.bannerInfo.value = { nextUpgradeAmount: 88.5 }
      expect(card.memberUpgradeText.value).toBe('再消费 ¥88.50 升级')
    })

    it('已经不需要再升级（金额为 0）时不展示文案', () => {
      const { card } = setup()
      card.bannerInfo.value = { nextUpgradeAmount: 0 }
      expect(card.memberUpgradeText.value).toBe('')
    })
  })

  describe('usableMemberCoupons', () => {
    it('最多只展示前 3 张券，不管后端实际返回多少张', () => {
      const { card } = setup()
      card.bannerInfo.value = { coupons: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }] }
      expect(card.usableMemberCoupons.value).toHaveLength(3)
      expect(card.usableMemberCoupons.value.map((c) => c.id)).toEqual([1, 2, 3])
    })

    it('没有券时返回空数组，不报错', () => {
      const { card } = setup()
      expect(card.usableMemberCoupons.value).toEqual([])
    })
  })

  describe('goOrderFromMember / useMemberCoupon', () => {
    it('goOrderFromMember 会回调 onGoOrder 切到点餐 Tab', () => {
      const { onGoOrder, card } = setup()
      card.goOrderFromMember()
      expect(onGoOrder).toHaveBeenCalledTimes(1)
    })

    it('useMemberCoupon 会先应用券再跳转点餐，用 coupon_id 兜底 id 字段', () => {
      const { onGoOrder, onUseCoupon, card } = setup()
      card.useMemberCoupon({ coupon_id: 'c9' })
      expect(onUseCoupon).toHaveBeenCalledWith('c9')
      expect(onGoOrder).toHaveBeenCalledTimes(1)
    })

    it('useMemberCoupon 传 null 时也不报错，onUseCoupon 收到 null', () => {
      const { onUseCoupon, card } = setup()
      expect(() => card.useMemberCoupon(null)).not.toThrow()
      expect(onUseCoupon).toHaveBeenCalledWith(null)
    })
  })
})
