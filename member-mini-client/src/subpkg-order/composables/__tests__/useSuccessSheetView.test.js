import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ref } from 'vue'
import { useSuccessSheetView } from '../useSuccessSheetView.js'

// P0 修复：postpay/table_account 下单成功时没有实际收款（后端 need_payment=false，
// 前端从没调起过微信支付），成功页此前不分模式地沿用 prepay 那句"实付金额"，
// 是在断言一笔没发生过的收款。这里锁定：文案跟这一笔订单自己的 payment_mode
// 绑定，而不是随便哪个页面级状态。

function setup(paymentMode) {
  return useSuccessSheetView({
    successItems: ref([]),
    orderNo: ref('1234'),
    orderId: ref('1234'),
    orderStatus: ref('pending'),
    successPaymentMode: ref(paymentMode),
  })
}

describe('useSuccessSheetView successPaidLabel', () => {
  it('prepay：已经实际收款，用"实付金额"', () => {
    expect(setup('prepay').successPaidLabel.value).toBe('实付金额')
  })

  it('postpay：钱还没收，不能用"实付金额"', () => {
    expect(setup('postpay').successPaidLabel.value).toBe('本单金额')
  })

  it('table_account：钱还没收，不能用"实付金额"', () => {
    expect(setup('table_account').successPaidLabel.value).toBe('本单金额')
  })

  it('未传 successPaymentMode 时，不默认断言"已收款"（安全侧失败方向）', () => {
    const view = useSuccessSheetView({
      successItems: ref([]),
      orderNo: ref('1234'),
      orderId: ref('1234'),
      orderStatus: ref('pending'),
    })
    expect(view.successPaidLabel.value).toBe('本单金额')
  })
})

describe('P0 static contract：PaymentSuccessSheet.vue 不再自己判断该显示哪句金额文案', () => {
  it('组件模板只渲染 paidLabel prop，不直接引用 successText.paidLabel', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../../components/PaymentSuccessSheet.vue'), 'utf8')
    expect(source).toContain('{{ paidLabel }}')
    expect(source).not.toContain('{{ successText.paidLabel }}')
    expect(source).toContain("paidLabel: { type: String, required: true }")
  })
})

describe('P0 static contract：hydratePaidSuccessPresentation 按订单自身 payment_mode 写入 successPaymentMode', () => {
  it('优先读 data.payment_mode，退回页面当前 paymentMode.value 只是兜底', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../useCheckout.js'), 'utf8')
    const fnBody = source.slice(
      source.indexOf('const hydratePaidSuccessPresentation ='),
      source.indexOf('const cartItemFingerprint ='),
    )
    expect(fnBody).toContain('successPaymentMode.value = normalizePaymentMode(data.payment_mode || paymentMode.value)')
  })
})
