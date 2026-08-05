// 从 menu.vue 拆出来的纯文案常量——点餐页里几个大段的固定 UI 文案对象。纯数据，
// 不是逻辑，跟原来在 menu.vue 里的内容一字未改，只是搬了个位置。

export const orderModeText = {
  dineIn: '堂食',
  delivery: '外卖',
  tableLabel: '桌号',
  unknownTable: '未识别'
}

export const confirmationText = {
  title: '确认订单', tableMissing: '未识别桌号，请重新扫码',
  selectedItems: '已选商品', clear: '清空已选商品',
  remark: '备注', remarkPlaceholder: '其他要求…', goodsAmount: '商品金额', coupon: '优惠券', couponAvailable: '张可用', couponNone: '暂无可用', noThreshold: '无门槛', thresholdPrefix: '满',
  payable: '应付金额', wechatPay: '微信支付', tableAccount: '桌台账单', postpay: '餐后付款', payNow: '立即支付', submitTableAccount: '提交到桌台账单', submitOrder: '提交订单',
  orderRemark: '整单备注', orderRemarkPlaceholder: '例如：一起上菜、全部打包、需要儿童餐具', orderRemarkEmpty: '无', unavailable: '当前不可下单', confirming: '正在确认订单…', paying: '正在发起支付…', currency: '¥', close: 'x', arrow: '>'
}

export const successText = {
  title: '下单成功',
  paidLabel: '实付金额',
  table: '桌号',
  orderNo: '订单号',
  items: '商品',
  itemUnit: '件',
  closeAndWait: '关闭并等待',
  continueOrdering: '继续加菜',
  viewDetail: '查看订单详情',
  safeTip: '订单状态会自动更新，无需重复提交或再次支付。',
  statusPending: '商家已收到订单，正在等待接单',
  statusPreparing: '商家已接单，正在制作',
  statusDone: '餐品已完成，请留意取餐或服务员通知',
  statusRejected: '订单状态异常，请联系商家处理',
  statusFallback: '订单已提交，可在订单详情中查看状态',
  detailOpened: '已打开订单详情',
  closed: '已关闭，请安心等待',
  backToMenu: '已返回点餐页',
}

export const specText = {
  defaultDesc: '选好口味后加入购物车', required: '必选', optional: '可选', multi: '可多选', extras: '附加要求', itemRemark: '单品备注', itemRemarkPlaceholder: '例如：少盐、不要香菜、对花生过敏',
  dish: '菜品', spec: '规格', qty: '数量', none: '无', prev: '返回上一步', next: '下一步', add: '加入购物车', chooseTaste: '选口味', chooseSpec: '选规格', selectedKinds: '已选', kindUnit: '种', separator: '、', dotSeparator: '·'
}

export const authSheetText = {
  title: '继续支付',
  desc: '微信授权后，将自动继续提交本次订单，无需重复操作。',
  auto: '授权成功后，系统将自动创建订单并拉起微信支付。',
  store: '门店',
  table: '桌号',
  amount: '应付金额',
  unknownTable: '未识别',
  confirm: '授权并支付',
  confirmSubmit: '授权并提交订单',
  confirmFree: '授权并完成订单',
  authorizing: '正在授权…',
  submitting: '正在提交订单…',
  paying: '正在发起支付…',
  cancel: '暂不支付',
  member: '支付成功后自动成为本店会员，可在“我的”中查看订单与权益。',
  privacy: '授权仅用于识别本次订单与会员身份，不会发布内容。',
}
