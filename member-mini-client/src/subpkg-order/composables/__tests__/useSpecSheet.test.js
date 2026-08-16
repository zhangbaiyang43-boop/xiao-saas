import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { useSpecSheet } from '../useSpecSheet.js'

// P0-03: dish with one radio spec group (份量) and one checkbox addon group
// (加料, options 鸡蛋/豆腐 in this exact config order) -- matches the real
// shape normalizeSpecGroups() expects (dish.spec_groups).
const DISH = {
  id: 'dish_1',
  name: '宫保鸡丁',
  price: 28,
  spec_groups: [
    { name: '份量', type: 'single', options: [{ name: '大份', price_delta: 10 }] },
    { name: '加料', type: 'checkbox', options: [{ name: '鸡蛋', price_delta: 2 }, { name: '豆腐', price_delta: 1 }] },
  ],
}

function setup() {
  const state = {
    itemRemark: ref(''),
    showItemRemarkExtra: ref(false),
    itemRemarkExtra: ref(''),
    remarkChips: ref([]),
    specCartItems: ref([]),
    isSoldOut: vi.fn(() => false),
    formatPrice: (n) => Number(n).toFixed(2),
    triggerCartSuccessFeedback: vi.fn(),
    ordering: ref(false),
  }
  const sheet = useSpecSheet(state)
  return { state, sheet }
}

// Drives the sheet through one full "open -> pick 大份 + given addons -> confirm" cycle.
function openAndSelect(sheet, { addons = [] } = {}) {
  sheet.openSpecSheet(DISH)
  sheet.toggleSpec(sheet.specRadioGroups.value[0], sheet.specRadioGroups.value[0].options[0])
  for (const name of addons) {
    const opt = sheet.specExtraOptions.value.find((o) => o.name === name)
    sheet.toggleExtra(opt.name)
  }
}

describe('useSpecSheet', () => {
  describe('T03/T04: spec-sheet confirm commit guard', () => {
    it('T03: 同一次 sheet 打开周期内，confirmSpec 被调用两次只提交一次', () => {
      const { state, sheet } = setup()
      openAndSelect(sheet, { addons: ['鸡蛋'] })

      sheet.confirmSpec()
      sheet.confirmSpec() // simulated double-tap within the same sheet opening

      expect(state.specCartItems.value).toHaveLength(1)
      expect(state.specCartItems.value[0].qty).toBe(1)
    })

    it('T04: 关闭后重新打开 sheet 再次 confirm 是合法的新增，不被永久锁死', () => {
      const { state, sheet } = setup()

      openAndSelect(sheet, { addons: ['鸡蛋'] })
      sheet.confirmSpec()
      expect(state.specCartItems.value[0].qty).toBe(1)

      openAndSelect(sheet, { addons: ['鸡蛋'] })
      sheet.confirmSpec()

      expect(state.specCartItems.value).toHaveLength(1)
      expect(state.specCartItems.value[0].qty).toBe(2)
    })
  })

  describe('T05/T07: addon identity is order-independent but distinguishes different sets', () => {
    it('T05: 相同 addon 集合，不同点选顺序，合并为同一条 line qty=2', () => {
      const { state, sheet } = setup()

      openAndSelect(sheet, { addons: ['鸡蛋', '豆腐'] })
      sheet.confirmSpec()

      openAndSelect(sheet, { addons: ['豆腐', '鸡蛋'] })
      sheet.confirmSpec()

      expect(state.specCartItems.value).toHaveLength(1)
      expect(state.specCartItems.value[0].qty).toBe(2)
    })

    it('T07: 不同 addon 集合（["鸡蛋"] vs ["豆腐"]）必须是两条独立 line', () => {
      const { state, sheet } = setup()

      openAndSelect(sheet, { addons: ['鸡蛋'] })
      sheet.confirmSpec()

      openAndSelect(sheet, { addons: ['豆腐'] })
      sheet.confirmSpec()

      expect(state.specCartItems.value).toHaveLength(2)
      expect(state.specCartItems.value.map((i) => i.qty)).toEqual([1, 1])
    })
  })

  describe('T06: canonical identity must not force-reorder display data', () => {
    it('display 的 extras/orderName 保留用户实际点选顺序，不被 identity 改写', () => {
      const { state, sheet } = setup()

      openAndSelect(sheet, { addons: ['豆腐', '鸡蛋'] }) // clicked out of config order
      sheet.confirmSpec()

      const line = state.specCartItems.value[0]
      expect(line.extras).toEqual(['豆腐', '鸡蛋']) // display/payload extras: click order preserved
      expect(line.orderName).toContain('豆腐、鸡蛋') // display text: click order preserved
    })
  })

  describe('T08/T09: remark participates in identity', () => {
    it('T08: 相同 dish/spec/addon，不同 remark，必须是两条独立 line（不能 merge）', () => {
      const { state, sheet } = setup()

      openAndSelect(sheet, { addons: ['鸡蛋'] })
      state.itemRemark.value = '不要香菜'
      sheet.confirmSpec()

      openAndSelect(sheet, { addons: ['鸡蛋'] })
      state.itemRemark.value = '多放香菜'
      sheet.confirmSpec()

      expect(state.specCartItems.value).toHaveLength(2)
      expect(state.specCartItems.value.map((i) => i.itemRemark)).toEqual(['不要香菜', '多放香菜'])
      expect(state.specCartItems.value.map((i) => i.qty)).toEqual([1, 1])
    })

    it('T09: 相同 dish/spec/addon/remark，两次添加合并为一条 line qty=2', () => {
      const { state, sheet } = setup()

      openAndSelect(sheet, { addons: ['鸡蛋'] })
      state.itemRemark.value = '不要香菜'
      sheet.confirmSpec()

      openAndSelect(sheet, { addons: ['鸡蛋'] })
      state.itemRemark.value = '不要香菜'
      sheet.confirmSpec()

      expect(state.specCartItems.value).toHaveLength(1)
      expect(state.specCartItems.value[0].qty).toBe(2)
    })
  })

  describe('P0-04 C02/C03: cart is locked while a submit is in flight', () => {
    it('C02: ordering=true 时 confirmSpec 不产生任何 cart mutation', () => {
      const { state, sheet } = setup()
      openAndSelect(sheet, { addons: ['鸡蛋'] })
      state.ordering.value = true

      sheet.confirmSpec()

      expect(state.specCartItems.value).toHaveLength(0)
    })

    it('C02: ordering=false 恢复后，同一次 sheet 状态仍能正常 confirm', () => {
      const { state, sheet } = setup()
      openAndSelect(sheet, { addons: ['鸡蛋'] })
      state.ordering.value = true
      sheet.confirmSpec()
      expect(state.specCartItems.value).toHaveLength(0)

      state.ordering.value = false
      sheet.confirmSpec()

      expect(state.specCartItems.value).toHaveLength(1)
    })

    it('C03: ordering 未设置（如独立单测场景）时不抛错，正常放行', () => {
      const state = {
        itemRemark: ref(''), showItemRemarkExtra: ref(false), itemRemarkExtra: ref(''),
        remarkChips: ref([]), specCartItems: ref([]), isSoldOut: vi.fn(() => false),
        formatPrice: (n) => Number(n).toFixed(2), triggerCartSuccessFeedback: vi.fn(),
        // ordering deliberately omitted
      }
      const sheet = useSpecSheet(state)
      openAndSelect(sheet, { addons: ['鸡蛋'] })

      expect(() => sheet.confirmSpec()).not.toThrow()
      expect(state.specCartItems.value).toHaveLength(1)
    })
  })
})
