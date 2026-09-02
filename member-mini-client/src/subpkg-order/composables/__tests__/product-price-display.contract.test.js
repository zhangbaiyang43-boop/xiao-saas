import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { useOrderFormatters } from '../useOrderFormatters.js'

// 商品浏览价格展示合同（PRODUCT_PRICE_DISPLAY / FORMATTER_1）。
//
// 起因：菜单里 ¥128 和 ¥34.80 并排出现，整数价没有小数、非整数价固定两位——
// 同一份菜单两种格式。定向修复引入 formatProductPrice：最多两位有效小数、
// 去掉无意义末尾 0，且先 toFixed(2) 再裁零，不把浮点误差 34.7999999 暴露出来。
//
// 这个文件只保护「商品售价」的展示口径。支付 / 退款 / 应付 / 实付 / 结算等
// 财务金额固定两位小数，由各自的 toFixed(2) 负责，不在这里定义合同。

const here = path.dirname(fileURLToPath(import.meta.url))
const read = (rel) => fs.readFileSync(path.resolve(here, rel), 'utf8')

const { formatProductPrice, dishPriceText } = useOrderFormatters()

describe('formatProductPrice —— 商品价格最多两位有效小数', () => {
  it('formats menu product prices with at most two meaningful decimals', () => {
    // [输入, 期望展示]。直接调用 production formatter，不在测试里复制算法。
    const cases = [
      [158, '158'],
      [158.0, '158'],
      ['158.00', '158'],
      [158.1, '158.1'],
      [158.5, '158.5'],
      [158.8, '158.8'],
      [158.88, '158.88'],
      [49.0, '49'],
      [34.8, '34.8'],
      [49.888, '49.89'],
      [34.7999999, '34.8'],
      [110.0, '110'],
      [0.01, '0.01'],
      [0, '0'],
      [200, '200'],
    ]
    for (const [input, expected] of cases) {
      expect(formatProductPrice(input), `formatProductPrice(${JSON.stringify(input)})`).toBe(expected)
    }
  })

  it('never widens a value back to a fixed two-decimal financial string', () => {
    // 关键退化保护：110.00 必须是 110，不能被裁成 11；整数不得回到 "X.00"。
    expect(formatProductPrice(110.0)).not.toBe('11')
    expect(formatProductPrice(128)).not.toBe('128.00')
    expect(formatProductPrice(34.8)).not.toBe('34.80')
  })
})

describe('dishPriceText —— 菜卡价格走 compact 口径', () => {
  it('dishPriceText uses compact product-price presentation', () => {
    // 整数价 → 无小数；x.80 价 → 一位；多规格取 min_price → compact。
    expect(dishPriceText({ price: 128 })).toBe('128')
    expect(dishPriceText({ price: 34.8 })).toBe('34.8')
    expect(dishPriceText({ min_price: 49.8, has_options: true })).toBe('49.8')
    expect(dishPriceText({ min_price: 49, has_options: true })).toBe('49')
  })
})

describe('SpecSheet / menu 商品价格接线', () => {
  it('SpecSheet product-price bindings use the product formatter, not the financial one', () => {
    const spec = read('../../components/SpecSheet.vue')
    // 规格弹层里的三处「商品价格」都必须走 formatProductPrice。
    expect(spec).toContain('formatProductPrice(specBasePrice)')
    expect(spec).toContain('formatProductPrice(opt.price_delta)')
    expect(spec).toContain('formatProductPrice(extra.price_delta)')
    // 且不得回退成 formatPrice(...)（那是财务口径，会带出 ¥49.80）。
    expect(spec).not.toContain('formatPrice(specBasePrice)')
    expect(spec).not.toContain('formatPrice(opt.price_delta)')
    expect(spec).not.toContain('formatPrice(extra.price_delta)')
  })

  it('menu wires the product formatter into SpecSheet', () => {
    const menu = read('../../pages/menu.vue')
    // 子组件拿到的是 compact formatter。
    expect(menu).toContain(':format-product-price="formatProductPrice"')
    // 且 formatProductPrice 是从 useOrderFormatters() 解构出来的
    // （在「const { … } = useOrderFormatters()」这段解构块内出现，marker-to-marker，
    //  不用固定字符窗口）。
    const call = menu.indexOf('} = useOrderFormatters()')
    expect(call).toBeGreaterThan(-1)
    const blockStart = menu.lastIndexOf('const {', call)
    expect(blockStart).toBeGreaterThan(-1)
    expect(menu.slice(blockStart, call)).toContain('formatProductPrice')
  })
})
