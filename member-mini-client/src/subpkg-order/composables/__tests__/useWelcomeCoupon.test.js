import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useWelcomeCoupon } from '../useWelcomeCoupon.js'

describe('useWelcomeCoupon', () => {
  beforeEach(() => {
    uni.getStorageSync.mockReturnValue('')
  })

  describe('welcomeCouponCondText', () => {
    it('有门槛金额时展示"满X元可用"', () => {
      const { welcomeCouponData, welcomeCouponCondText } = useWelcomeCoupon()
      welcomeCouponData.value = { min_amount: 30 }
      expect(welcomeCouponCondText.value).toBe('满30元可用')
    })

    it('没有门槛金额时展示"无门槛可用"', () => {
      const { welcomeCouponData, welcomeCouponCondText } = useWelcomeCoupon()
      welcomeCouponData.value = { min_amount: 0 }
      expect(welcomeCouponCondText.value).toBe('无门槛可用')
    })

    it('还没有券数据时也展示"无门槛可用"，不报错', () => {
      const { welcomeCouponCondText } = useWelcomeCoupon()
      expect(welcomeCouponCondText.value).toBe('无门槛可用')
    })
  })

  describe('consumeWelcomeCoupon', () => {
    it('coupon_modal_shown 不是精确的字符串 "false" 时直接返回 null，不消费', () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'coupon_modal_shown' ? '' : ''))
      const { consumeWelcomeCoupon } = useWelcomeCoupon()

      const result = consumeWelcomeCoupon()

      expect(result).toBe(null)
      expect(uni.setStorageSync).not.toHaveBeenCalled()
    })

    it('coupon_modal_shown 为 "true" 时同样视为已经消费过，不再弹', () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'coupon_modal_shown' ? 'true' : ''))
      const { consumeWelcomeCoupon } = useWelcomeCoupon()

      expect(consumeWelcomeCoupon()).toBe(null)
    })

    it('coupon_modal_shown 为 "false" 且本地有新人券数据时，消费掉并标记为已展示', () => {
      uni.getStorageSync.mockImplementation((key) => {
        if (key === 'coupon_modal_shown') return 'false'
        if (key === 'welcome_coupon') return JSON.stringify({ id: 'wc1', min_amount: 20 })
        return ''
      })
      const { consumeWelcomeCoupon } = useWelcomeCoupon()

      const result = consumeWelcomeCoupon()

      expect(result).toEqual({ id: 'wc1', min_amount: 20 })
      expect(uni.setStorageSync).toHaveBeenCalledWith('coupon_modal_shown', 'true')
    })

    it('coupon_modal_shown 为 "false" 但本地没有新人券数据时返回 null', () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'coupon_modal_shown' ? 'false' : ''))
      const { consumeWelcomeCoupon } = useWelcomeCoupon()

      expect(consumeWelcomeCoupon()).toBe(null)
      expect(uni.setStorageSync).toHaveBeenCalledWith('coupon_modal_shown', 'true')
    })

    it('本地新人券数据损坏（不是合法 JSON）时捕获异常返回 null，不抛出', () => {
      uni.getStorageSync.mockImplementation((key) => {
        if (key === 'coupon_modal_shown') return 'false'
        if (key === 'welcome_coupon') return '{not valid json'
        return ''
      })
      const { consumeWelcomeCoupon } = useWelcomeCoupon()

      expect(() => consumeWelcomeCoupon()).not.toThrow()
      expect(consumeWelcomeCoupon()).toBe(null)
    })
  })

  describe('checkWelcomeCoupon', () => {
    it('能消费到新人券时展示弹层并填充数据', () => {
      uni.getStorageSync.mockImplementation((key) => {
        if (key === 'coupon_modal_shown') return 'false'
        if (key === 'welcome_coupon') return JSON.stringify({ id: 'wc1', min_amount: 0 })
        return ''
      })
      const { showWelcomeCoupon, welcomeCouponData, checkWelcomeCoupon } = useWelcomeCoupon()

      checkWelcomeCoupon()

      expect(showWelcomeCoupon.value).toBe(true)
      expect(welcomeCouponData.value).toEqual({ id: 'wc1', min_amount: 0 })
    })

    it('消费不到新人券时不展示弹层', () => {
      const { showWelcomeCoupon, checkWelcomeCoupon } = useWelcomeCoupon()

      checkWelcomeCoupon()

      expect(showWelcomeCoupon.value).toBe(false)
    })
  })

  describe('closeWelcomeCoupon / goOrderFromWelcomeCoupon', () => {
    it('closeWelcomeCoupon 直接关闭弹层', () => {
      const { showWelcomeCoupon, closeWelcomeCoupon } = useWelcomeCoupon()
      showWelcomeCoupon.value = true

      closeWelcomeCoupon()

      expect(showWelcomeCoupon.value).toBe(false)
    })

    it('goOrderFromWelcomeCoupon 关闭弹层并回调 onGoOrder 切到点餐 Tab', () => {
      const onGoOrder = vi.fn()
      const { showWelcomeCoupon, goOrderFromWelcomeCoupon } = useWelcomeCoupon(onGoOrder)
      showWelcomeCoupon.value = true

      goOrderFromWelcomeCoupon()

      expect(showWelcomeCoupon.value).toBe(false)
      expect(onGoOrder).toHaveBeenCalledTimes(1)
    })

    it('没有传 onGoOrder 时也不会报错', () => {
      const { goOrderFromWelcomeCoupon } = useWelcomeCoupon()
      expect(() => goOrderFromWelcomeCoupon()).not.toThrow()
    })
  })
})
