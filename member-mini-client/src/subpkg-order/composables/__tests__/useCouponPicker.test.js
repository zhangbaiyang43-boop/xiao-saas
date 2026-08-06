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
