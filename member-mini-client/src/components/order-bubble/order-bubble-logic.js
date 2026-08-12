// 从 order-bubble.vue 拆出来的纯判断逻辑，方便直接单测（vitest 这边没有接 Vue SFC
// 编译插件，.vue 文件本身没法被测试直接 import，见 vitest.config.js 里的注释）。
// 只吃 visible/tone 的新旧值，不碰 uni.* 或组件状态。
//
// 调用方对"没有真实订单"时 tone 占位值的约定并不统一（menu.vue 的
// useTableBillView.js 用 'empty'，mine.vue 复用了 orderStatusTone(undefined)
// 的兜底值 'paid'），所以两个判断都不看 tone 的具体占位字符串，只看 visible
// 本身的翻转——这是唯一在两个调用方都成立的信号。

export function shouldShowInitialHint(visible, prevVisible) {
  return Boolean(visible && !prevVisible)
}

export function shouldShowStatusCallout(visible, prevVisible, tone, prevTone) {
  return Boolean(prevVisible && visible && tone !== prevTone)
}
