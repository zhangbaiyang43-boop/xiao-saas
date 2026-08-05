<template>
  <view class="mask" @click="$emit('close')">
    <view class="orders-sheet table-account-sheet" @click.stop>
      <view class="orders-sheet-head table-account-head">
        <view class="table-account-back" @click="$emit('close')">
          <text class="iconfont icon-back"></text>
        </view>
        <text class="orders-sheet-title">已点菜品</text>
        <text class="orders-sheet-close iconfont icon-close" @click="$emit('close')"></text>
      </view>

      <scroll-view v-if="!loadError" class="table-account-list" scroll-y :scroll-into-view="tableAccountScrollInto" scroll-with-animation>
        <view id="table-account-status-anchor" class="table-account-status">
          <view class="table-account-status-icon" :class="'table-account-status-icon--' + tableStatusView.tone">
            <text class="iconfont" :class="tableStatusView.icon"></text>
          </view>
          <text class="table-account-status-title">{{ tableStatusView.title }}</text>
          <text class="table-account-status-desc">{{ tableStatusView.desc }}</text>
          <text v-if="tableStatusView.note" class="table-account-status-note">{{ tableStatusView.note }}</text>
        </view>

        <view class="table-account-summary">
          <view class="table-account-summary-left">
            <text class="table-account-table">{{ tableNo || orderModeText.unknownTable }}桌</text>
            <text class="table-account-sub">{{ sharedBillSubLabel }}</text>
          </view>
          <view class="table-account-summary-right">
            <text class="table-account-total">¥{{ formatPrice(tableTotal) }}</text>
            <text class="table-account-count">共 {{ tableItemCount }} 份</text>
          </view>
        </view>

        <view class="table-account-section">
          <view class="table-account-section-head">
            <text class="table-account-section-title">本桌已点菜品</text>
          </view>

          <view v-if="tableOrderGroups.length" class="table-account-groups">
            <view v-for="group in tableOrderGroups" :key="group.id" class="table-account-group">
              <view class="table-account-group-head">
                <view class="table-account-group-left">
                  <view v-if="group.participantNo" class="participant-badge" :style="{ background: group.participantColor }">{{ group.participantNo }}</view>
                  <text v-if="group.isStaff" class="table-account-staff-badge">服务员代点{{ group.staffNote ? ' · ' + group.staffNote : '' }}</text>
                  <text class="table-account-group-time">{{ group.title }}</text>
                  <text v-if="group.discountAmount > 0" class="table-account-group-discount">优惠 -¥{{ formatPrice(group.discountAmount) }}</text>
                </view>
                <text class="table-account-group-status" :class="'table-account-group-status--' + group.tone">{{ group.statusText }}</text>
              </view>
              <view v-for="(item, idx) in group.items" :key="item.specKey || item.dish_id || item.id || item.name || idx" class="table-account-item" :class="{ 'table-account-item--muted': item.isInvalid }">
                <view class="table-account-item-img-wrap">
                  <image
                    v-if="orderItemImage(item) && !orderItemImageFailed[group.id + '_' + idx]"
                    class="table-account-item-img"
                    :src="orderItemImage(item)"
                    mode="aspectFill"
                    @error="$emit('mark-image-failed', group.id + '_' + idx)"
                  />
                  <view v-else class="table-account-item-placeholder">
                    <text>{{ orderItemName(item).slice(0, 1) }}</text>
                  </view>
                </view>
                <view class="table-account-item-main">
                  <text class="table-account-item-name">{{ orderItemName(item) }}</text>
                  <text v-if="orderItemSpecText(item)" class="table-account-item-spec">{{ orderItemSpecText(item) }}</text>
                  <text v-if="item.isInvalid" class="table-account-item-mark">{{ item.invalidText }}</text>
                </view>
                <text class="table-account-item-qty">×{{ orderItemQty(item) }}</text>
                <text class="table-account-item-amount">¥{{ formatPrice(orderItemAmount(item)) }}</text>
              </view>
            </view>
          </view>

          <view v-else class="table-account-empty">
            <text class="table-account-empty-title">本桌还没有已点菜品</text>
            <text class="table-account-empty-desc">可以先去点菜，后续加菜会自动合并到本桌账单</text>
          </view>
        </view>

        <view class="table-account-tip">
          <text>同桌后续加菜会自动合并，不需要每次付款。</text>
        </view>
      </scroll-view>

      <view v-else class="table-status-empty">
        <text class="table-status-empty-icon iconfont icon-warnfill"></text>
        <text class="table-status-empty-title">本桌订单加载失败</text>
        <text class="table-status-empty-desc">请重新加载后再查看本桌账单</text>
        <view class="table-account-retry" @click="$emit('retry-load')"><text>重新加载</text></view>
      </view>

      <view class="table-account-actions">
        <view
          class="table-account-action table-account-action--secondary"
          :class="{ 'table-account-action--disabled': !canContinueOrder }"
          @click="$emit('continue-order')"
        >
          <text>{{ tableOrderGroups.length ? '继续加菜' : '去点菜' }}</text>
        </view>
        <view
          v-if="canCheckout"
          class="table-account-action table-account-action--primary"
          :class="{ 'table-account-action--disabled': tableCheckouting || checkoutRequested }"
          @click="$emit('checkout')"
        >
          <text>{{ tableCheckouting ? '呼叫中...' : (checkoutRequested ? '已呼叫服务员，等待确认' : '吃好了，去结账') }}</text>
        </view>
        <view
          v-else-if="isTableSettled"
          class="table-account-action table-account-action--primary table-account-action--ghost"
          @click="$emit('scroll-to-top')"
        >
          <text>查看结账详情</text>
        </view>
        <view
          v-else-if="stillPreparing"
          class="table-account-action table-account-action--primary table-account-action--disabled"
        >
          <text>制作中，暂不能结账</text>
        </view>
        <view
          v-else-if="postpayReadyToSettle"
          class="table-account-action table-account-action--info"
        >
          <text>用餐结束请到收银台或联系服务员结账</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的桌台账单弹层（原来是 showOrders && isSharedBillMode 那一段
// 模板，"已点菜品"分账/桌台账单视图）。纯展示组件，不带任何业务逻辑——所有需要
// 改父组件状态的动作（关闭、重新加载、继续加菜、去结账、滚动到顶部、图片加载
// 失败）都只 emit 出去，真正的处理函数还是原来 menu.vue 里那几个
// （loadMenu/handleTableContinueOrder/handleTableCheckout/
// scrollTableAccountToTop/markOrderItemImageFailed），一行都没有改。
export default {
  name: 'TableBillSheet',
  props: {
    loadError: { type: Boolean, default: false },
    tableStatusView: { type: Object, required: true },
    tableNo: { type: [String, Number], default: '' },
    orderModeText: { type: Object, required: true },
    sharedBillSubLabel: { type: String, default: '' },
    tableTotal: { type: Number, default: 0 },
    tableItemCount: { type: Number, default: 0 },
    tableOrderGroups: { type: Array, default: () => [] },
    orderItemImageFailed: { type: Object, default: () => ({}) },
    canContinueOrder: { type: Boolean, default: false },
    canCheckout: { type: Boolean, default: false },
    isTableSettled: { type: Boolean, default: false },
    stillPreparing: { type: Boolean, default: false },
    postpayReadyToSettle: { type: Boolean, default: false },
    tableCheckouting: { type: Boolean, default: false },
    checkoutRequested: { type: Boolean, default: false },
    tableAccountScrollInto: { type: String, default: '' },
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑），
    // 保证跟父组件其它地方用到的结果 100% 一致。
    formatPrice: { type: Function, required: true },
    orderItemImage: { type: Function, required: true },
    orderItemName: { type: Function, required: true },
    orderItemSpecText: { type: Function, required: true },
    orderItemQty: { type: Function, required: true },
    orderItemAmount: { type: Function, required: true },
  },
  emits: ['close', 'retry-load', 'continue-order', 'checkout', 'scroll-to-top', 'mark-image-failed'],
}
</script>
