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
  selectedItems: '已选商品', clear: '清空',
  remark: '备注', remarkPlaceholder: '其他要求…', goodsAmount: '商品金额', coupon: '优惠券', couponAvailable: '张可用', couponNone: '暂无可用', noThreshold: '无门槛', thresholdPrefix: '满',
  payable: '应付金额', wechatPay: '微信支付', tableAccount: '桌台账单', postpay: '餐后付款', payNow: '立即支付', submitTableAccount: '提交到桌台账单', submitOrder: '提交订单',
  orderRemark: '整单备注', orderRemarkPlaceholder: '例如：一起上菜、全部打包、需要儿童餐具', orderRemarkEmpty: '无', unavailable: '当前不可下单', confirming: '正在确认订单…', paying: '正在发起支付…', paymentConfirming: '支付确认中…', queryPaymentResult: '重新查询支付结果', currency: '¥', close: 'x', arrow: '>',
  memberSummaryMember: '{level} · 本单预计+{points}积分',
  memberSummaryMemberCoupons: ' · {count}张可用',
  memberSummaryGuest: '本单预计可得 {points} 积分，加入会员解锁专属券',
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
  statusPendingPayment: '订单待支付，请完成微信支付',
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
  defaultDesc: '选好口味后加入购物车', required: '必选', optional: '可选', multi: '可多选', extras: '附加要求', itemRemark: '单品备注', // "不要香菜"这类口味类例子经常已经是这道菜自己的"附加要求"选项（filteredRemarkChips
  // 会把这类重复词从快捷标签里过滤掉，但这句静态占位符文案不会跟着过滤），顾客会
  // 疑惑到底该点选项还是自己打字。这里换成不会跟规格/附加要求撞的例子：过敏原和
  // 打包分装是这道菜的结构化选项永远覆盖不到的信息。
  itemRemarkPlaceholder: '例如：少盐、对花生过敏、帮忙分开装',
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

// P0-A: 结算前"加入会员/直接支付"选择层的文案。跟 authSheetText 是两套不同
// 的场景——authSheetText 是"已经在下单/支付中途遇到授权失效，必须重新授权
// 才能继续"的被动补救话术；这里是顾客点结算时主动看到的、会员是可选项的引导
// 话术，不能共用同一份文案（措辞、语气、允许的退出方式完全不同）。
export const memberChoiceText = {
  title: '加入会员，享受本单权益',
  // P0-A-13: 未授权身份前不能断言"你是新会员"（可能是没登录的老会员），
  // 也不能编造具体省了多少钱（没识别身份前拿不到顾客名下真实的券）。
  descGeneric: '加入会员可领取本店会员权益，支付后还能获得积分',
  joinAction: '加入会员并继续',
  joining: '正在加入会员…',
  // P0-A-14: 会员身份在手机号授权成功那一刻就建立了，不是"支付成功后"，
  // 文案时序必须跟真实发生的顺序一致。
  joinDesc: '授权成功后将加入/登录本店会员，并自动继续结算。',
  guestPayPrefix: '直接支付',
  agreementPrefix: '授权即表示同意',
  agreementLink: '《会员协议》',
  privacy: '授权仅用于识别本次订单与会员身份，不会发布内容。',
}

// Toast / Modal 反馈文案字典（ROI #4）。
// 点餐子包内 showToast / showModal 的固定中文只从这里取，禁止业务文件再手写同义句。
// 对照知识库：OPPO 禁用裸「失败」；客如云要求失败带下一步（重试 / 重新扫码 / 联系服务员）。
export const toastText = {
  authIncomplete: '未完成授权，请重试',
  joinMemberFailed: '加入会员失败，请重试',
  memberBenefitsLoadFailed: '会员权益加载失败，请重试',
  loggedIn: '已登录',

  tableBillEnded: '本桌账单已结束，不能继续加菜',
  tableSessionEnded: '本桌已结束，请重新扫码点餐',
  tableSessionUnavailable: '本桌点餐会话不可用，请重新扫码',
  tableBillMissing: '缺少桌台账单信息，请重新加载',
  callWaiterOk: '已通知服务员，请稍候为您结账',
  callWaiterFailed: '呼叫失败，请重试',
  newParticipant: '有新伙伴扫码加入了本桌',

  payCancelled: '已取消支付',
  createOrderFailed: '订单创建失败，请重试',
  submitOrderFailed: '下单失败，请告知服务员',
  // P0-15-02: network/timeout during submit -- outcome is unknown, not a
  // definitive failure (the request may have already reached the server).
  submitOrderUnknown: '网络异常，订单状态待确认，请重新确认',
  // P0-15 closure Gap A: local durable-storage write failed BEFORE the
  // create-order request was ever sent -- this is a definitively local,
  // nothing-sent-yet failure, distinct from "网络异常，订单状态待确认" above.
  submitIntentSaveFailed: '暂时无法保存订单状态，请重试',
  // P0-15 closure Gap A: a prior pending-intent record for this table exists
  // but can't be read back reliably -- fail closed rather than guess.
  submitIntentUnrecoverable: '订单状态异常，请重新确认后再试',

  dishUnavailable: '菜品已下架或售罄',
  specChanged: '规格已变更，请重新选择',
  reorderEmpty: '没有可重新加入的菜品',
  reorderPartialUnavailable: '，部分菜品已下架或售罄',
  reorderPartialSpec: '，部分规格已变更，请重新选择',
  reorderAdded(count) {
    return '已加入' + count + '件'
  },

  orderCancelled: '订单已取消',
  cancelOrderFailed: '取消失败，请重试',

  merchantAccepted: '商家已接单，正在备餐',

  reminderOk: '好的，到期前会提醒你',
  reminderFailed: '设置失败，请重试',
  deliveryUnavailable: '外卖配送正在完善，当前先支持堂食点餐',
  entryCoupon(amountText, thresholdText) {
    return '已发放进店券 ¥' + amountText + '，满' + thresholdText + '元可用'
  },
}

export const modalText = {
  tableHintTitle: '桌号提示',
  tableHintContent(tableLabel) {
    return '当前桌号：' + tableLabel + '\n请确认桌号后继续点餐'
  },
  tableHintConfirm: '知道了',

  tableSettledTitle: '本桌已结账',
  tableSettledContent: '本次用餐账单已经结清，如需明细请联系服务员。',
  tableSettledConfirm: '知道了',

  clearCartTitle: '清空购物车',
  clearCartContent(count) {
    return '确定要清空已选的' + count + '件商品吗？'
  },
  clearCartConfirm: '清空',

  cancelOrderTitle: '取消订单',
  cancelOrderContent: '确认取消此订单吗？商家接单后无法取消。',

  orderRejectedTitle: '订单已被拒绝',
  orderRejectedContent: '商家暂时无法处理此订单，请联系服务员',
}
