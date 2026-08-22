import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useCouponPicker } from '../useCouponPicker.js'

function setup({ coupons = [], totalPrice = 100, loggedIn = true } = {}) {
  const availableCoupons = ref(coupons)
  const isCustomerLoggedIn = ref(loggedIn)
  const formatPrice = (n) => n.toFixed(2)
  const getTotalPrice = () => totalPrice
  const picker = useCouponPicker({ availableCoupons, getTotalPrice, isCustomerLoggedIn, formatPrice })
  return { availableCoupons, isCustomerLoggedIn, picker }
}

describe('useCouponPicker', () => {
  describe('couponBarVisible', () => {
    it('未登录时不展示优惠券横幅，即使有券', () => {
      const { picker } = setup({ coupons: [{ id: 'c1', value: 5 }], loggedIn: false })
      expect(picker.couponBarVisible.value).toBe(false)
    })

    it('登录了但没有可用券时不展示', () => {
      const { picker } = setup({ coupons: [], loggedIn: true })
      expect(picker.couponBarVisible.value).toBe(false)
    })

    it('登录且有券时展示，文案里带最高减免金额', () => {
      const { picker } = setup({ coupons: [{ id: 'c1', value: 5 }, { id: 'c2', value: 15 }] })
      expect(picker.couponBarVisible.value).toBe(true)
      expect(picker.bestCouponValue.value).toBe(15)
      expect(picker.couponBarText.value).toBe('您有2张优惠券，最高减¥15.00')
    })
  })

  describe('discountAmount / finalPrice', () => {
    it('没有选中优惠券时折扣为 0', () => {
      const { picker } = setup({ totalPrice: 100 })
      expect(picker.discountAmount.value).toBe(0)
      expect(picker.finalPrice.value).toBe(100)
    })

    it('订单金额没达到优惠券门槛时折扣为 0', () => {
      const { availableCoupons, picker } = setup({
        coupons: [{ id: 'c1', value: 20, min_amount: 200 }],
        totalPrice: 100,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === availableCoupons.value[0].id))
      expect(picker.discountAmount.value).toBe(0)
    })

    it('折扣金额超过订单总价 20% 时按封顶算，不是券面值', () => {
      const { availableCoupons, picker } = setup({
        coupons: [{ id: 'c1', value: 50, min_amount: 0 }],
        totalPrice: 100,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === availableCoupons.value[0].id))
      // 20% of 100 = 20，比券面值 50 小，应该按 20 算
      expect(picker.discountAmount.value).toBe(20)
      expect(picker.finalPrice.value).toBe(80)
    })

    it('券面值本来就低于封顶时按券面值算', () => {
      const { availableCoupons, picker } = setup({
        coupons: [{ id: 'c1', value: 5, min_amount: 0 }],
        totalPrice: 100,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === availableCoupons.value[0].id))
      expect(picker.discountAmount.value).toBe(5)
      expect(picker.finalPrice.value).toBe(95)
    })

    it('finalPrice 不会因为折扣计算误差变成负数', () => {
      const { availableCoupons, picker } = setup({
        coupons: [{ id: 'c1', value: 5, min_amount: 0 }],
        totalPrice: 0,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === availableCoupons.value[0].id))
      expect(picker.finalPrice.value).toBe(0)
    })
  })

  describe('couponPickerList 排序', () => {
    it('面额不同时按面额从高到低排，够门槛的优先于不够门槛的', () => {
      const { picker } = setup({
        coupons: [
          { id: 'low', value: 5, min_amount: 0 },
          { id: 'high-ineligible', value: 100, min_amount: 9999 },
          { id: 'high-eligible', value: 20, min_amount: 0 },
        ],
        totalPrice: 100,
      })
      const ids = picker.couponPickerList.value.map((c) => c.id)
      expect(ids).toEqual(['high-eligible', 'low', 'high-ineligible'])
      expect(picker.couponPickerList.value.find((c) => c.id === 'high-ineligible').eligible).toBe(false)
    })

    it('面额相同时，快过期的排在前面，不能被后端返回顺序摆布', () => {
      const { picker } = setup({
        coupons: [
          { id: 'later', value: 10, min_amount: 0, expire_time: '2026-12-31' },
          { id: 'sooner', value: 10, min_amount: 0, expire_time: '2026-06-01' },
        ],
        totalPrice: 100,
      })
      const ids = picker.couponPickerList.value.map((c) => c.id)
      expect(ids).toEqual(['sooner', 'later'])
    })

    it('required member refresh 会覆盖仍 eligible 的旧券 A，强制选择实际折扣更高的 B', () => {
      const { picker } = setup({
        coupons: [
          { id: 'A', type: 'FIXED', value: 5, min_amount: 0 },
          { id: 'B', type: 'FIXED', value: 10, min_amount: 0 },
        ],
        totalPrice: 100,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((coupon) => coupon.id === 'A'))

      const best = picker.selectBestEligibleCoupon()

      expect(best.id).toBe('B')
      expect(picker.selectedCouponId.value).toBe('B')
    })

    it('折扣与到期时间仍相同时按 id 稳定排序', () => {
      const { picker } = setup({
        coupons: [
          { id: 'B', value: 10, min_amount: 0, expire_time: '2026-12-31' },
          { id: 'A', value: 10, min_amount: 0, expire_time: '2026-12-31' },
        ],
      })

      expect(picker.couponPickerList.value.map((coupon) => coupon.id)).toEqual(['A', 'B'])
    })
  })

  describe('PERCENT 优惠券折扣计算（跟后端 orders.py 的 _apply_coupon 语义对齐）', () => {
    it('PERCENT 类型按订单实际金额算折扣，不是直接拿 value 当金额', () => {
      const { picker } = setup({
        coupons: [{ id: 'c1', type: 'PERCENT', value: 10, min_amount: 0 }],
        totalPrice: 200,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === 'c1'))
      // 200 * 10% = 20，未触发 20% 封顶（40）
      expect(picker.discountAmount.value).toBe(20)
      expect(picker.finalPrice.value).toBe(180)
    })

    it('PERCENT 折扣同样受 20% 封顶限制，不会超过订单总价的 20%', () => {
      const { picker } = setup({
        coupons: [{ id: 'c1', type: 'PERCENT', value: 30, min_amount: 0 }],
        totalPrice: 200,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === 'c1'))
      // 200 * 30% = 60，超过封顶 40，应该按 40 算
      expect(picker.discountAmount.value).toBe(40)
    })

    it('CASE 4: ¥200 订单，FIXED ¥15 vs PERCENT 10%，实际折扣 20 > 15，PERCENT 应排在前面被选中', () => {
      const { picker } = setup({
        coupons: [
          { id: 'fixed', type: 'FIXED', value: 15, min_amount: 0 },
          { id: 'percent', type: 'PERCENT', value: 10, min_amount: 0 },
        ],
        totalPrice: 200,
      })
      const ids = picker.couponPickerList.value.map((c) => c.id)
      expect(ids).toEqual(['percent', 'fixed'])

      const best = picker.couponPickerList.value.find((c) => c.eligible)
      picker.pickCoupon(best)
      expect(picker.selectedCouponId.value).toBe('percent')
      expect(picker.discountAmount.value).toBe(20)
    })

    it('calculateCouponDiscount 对未达门槛的 PERCENT 券返回 0，不是打折打得少', () => {
      const { picker } = setup({
        coupons: [{ id: 'c1', type: 'PERCENT', value: 10, min_amount: 300 }],
        totalPrice: 200,
      })
      expect(picker.calculateCouponDiscount({ type: 'PERCENT', value: 10, min_amount: 300 }, 200)).toBe(0)
    })
  })

  describe('pickCoupon / openCouponPicker / closeCouponPicker', () => {
    it('选中不够门槛的券时忽略，不选中也不关闭弹层', () => {
      const { picker } = setup({
        coupons: [{ id: 'c1', value: 20, min_amount: 9999 }],
        totalPrice: 100,
      })
      picker.openCouponPicker()
      const ineligible = { id: 'c1', value: 20, min_amount: 9999, eligible: false }

      picker.pickCoupon(ineligible)

      expect(picker.selectedCouponId.value).toBe(null)
      expect(picker.showCouponPicker.value).toBe(true)
    })

    it('选中合法优惠券后 selectedCoupon 能查到对应的券，并关闭弹层', () => {
      const { availableCoupons, picker } = setup({
        coupons: [{ id: 'c1', value: 20, min_amount: 0 }],
        totalPrice: 100,
      })
      picker.openCouponPicker()

      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === availableCoupons.value[0].id))

      expect(picker.selectedCouponId.value).toBe('c1')
      expect(picker.selectedCoupon.value).toMatchObject({ id: 'c1' })
      expect(picker.showCouponPicker.value).toBe(false)
    })

    it('传 null 取消选择，同时关闭弹层', () => {
      const { availableCoupons, picker } = setup({
        coupons: [{ id: 'c1', value: 20, min_amount: 0 }],
        totalPrice: 100,
      })
      picker.pickCoupon(picker.couponPickerList.value.find((c) => c.id === availableCoupons.value[0].id))

      picker.pickCoupon(null)

      expect(picker.selectedCouponId.value).toBe(null)
      expect(picker.selectedCoupon.value).toBe(null)
      expect(picker.showCouponPicker.value).toBe(false)
    })
  })
})
