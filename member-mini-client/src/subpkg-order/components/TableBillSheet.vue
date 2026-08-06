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

<style lang="scss">
@import '../styles/_shared.scss';

.table-account-sheet {
  background: #f6f7f8;
  padding-bottom: 0;
}



.table-account-head {
  position: relative;
  justify-content: center;
  min-height: 88rpx;
}



.table-account-back {
  position: absolute;
  left: 18rpx;
  top: 12rpx;
  width: 64rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-2);
}



.table-account-back text {
  font-size: 34rpx;
}



.table-account-list {
  max-height: calc(82vh - 176rpx - env(safe-area-inset-bottom));
  padding: 0 24rpx 188rpx;
  box-sizing: border-box;
}



.table-account-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18rpx 24rpx 20rpx;
  text-align: center;
}



.table-account-status-icon {
  width: 56rpx;
  height: 56rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}



.table-account-status-icon text {
  font-size: 30rpx;
}

// 顶部大状态图标和下面每笔子订单的状态标签用同一套语义色：
// active=还在等（下单/制作中），served=菜已上齐可以结账，settled=已结账/归档。
.table-account-status-icon--active {
  background: #fff7e6;
  color: var(--warning);
}

.table-account-status-icon--served {
  background: #ecfbf3;
  color: var(--brand);
}

.table-account-status-icon--settled {
  background: #f3f4f6;
  color: var(--text-3);
}



.table-account-status-title {
  margin-top: 12rpx;
  color: var(--text-1);
  font-size: 44rpx;
  font-weight: 900;
  line-height: 1.25;
}



.table-account-status-desc {
  margin-top: 8rpx;
  color: var(--text-3);
  font-size: 28rpx;
  line-height: 1.45;
}



.table-account-status-note {
  display: block;
  margin-top: 4rpx;
  color: var(--text-3);
  font-size: 24rpx;
  line-height: 1.4;
}



.table-account-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  margin-top: 8rpx;
  padding: 26rpx 28rpx;
  border-radius: 24rpx;
  background: #fff;
  box-sizing: border-box;
}



.table-account-summary-left,
.table-account-summary-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
}



.table-account-table,
.table-account-total {
  color: var(--text-1);
  font-size: 40rpx;
  font-weight: 900;
  line-height: 1.25;
}



.table-account-sub,
.table-account-count {
  margin-top: 8rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 1.4;
}



.table-account-summary-right {
  flex-shrink: 0;
  align-items: flex-end;
  text-align: right;
}



.table-account-total {
  color: var(--brand);
}



.table-account-section {
  margin-top: 18rpx;
  padding: 24rpx;
  border-radius: 24rpx;
  background: #fff;
  box-sizing: border-box;
}



.table-account-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18rpx;
}



.table-account-section-title {
  color: var(--text-1);
  font-size: 34rpx;
  font-weight: 900;
  line-height: 1.35;
}



.table-account-group + .table-account-group {
  margin-top: 26rpx;
  padding-top: 22rpx;
  border-top: 1rpx solid #eef1f3;
}



.table-account-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18rpx;
  margin-bottom: 16rpx;
}



.table-account-group-left {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12rpx;
}



/* 拼桌时标出"这一单是第几位点的"，纯展示编号，不关联真实身份 */
.participant-badge {
  flex-shrink: 0;
  width: 34rpx;
  height: 34rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20rpx;
  font-weight: 800;
}



.table-account-group-time {
  color: var(--text-2);
  font-size: 28rpx;
  font-weight: 800;
}



/* 服务员代客加的单也标出来，让顾客知道这道菜是谁帮加的，结账时不会觉得莫名其妙 */
.table-account-staff-badge {
  flex-shrink: 0;
  color: #a21caf;
  background: #fdf4ff;
  border-radius: 8rpx;
  padding: 2rpx 10rpx;
  font-size: 20rpx;
  font-weight: 700;
}



.table-account-group-discount {
  flex-shrink: 0;
  color: #ef4444;
  font-size: 24rpx;
  font-weight: 700;
}



.table-account-group-status {
  flex-shrink: 0;
  color: var(--warning);
  font-size: 24rpx;
  line-height: 34rpx;
}

.table-account-group-status--served {
  color: var(--brand);
}

.table-account-group-status--settled {
  color: var(--text-3);
}

.table-account-group-status--muted {
  color: #9aa1aa;
}



.table-account-item {
  min-height: 128rpx;
  display: flex;
  align-items: center;
  gap: 18rpx;
  padding: 12rpx 0;
  box-sizing: border-box;
}



.table-account-item--muted {
  opacity: .58;
}



.table-account-item-img-wrap,
.table-account-item-img,
.table-account-item-placeholder {
  width: 112rpx;
  height: 112rpx;
  border-radius: 20rpx;
  flex-shrink: 0;
  overflow: hidden;
}



.table-account-item-placeholder {
  background: #f2f4f5;
  display: flex;
  align-items: center;
  justify-content: center;
}



.table-account-item-placeholder text {
  color: var(--text-3);
  font-size: 34rpx;
  font-weight: 800;
}



.table-account-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}



.table-account-item-name {
  color: var(--text-1);
  font-size: 32rpx;
  font-weight: 800;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.table-account-item-spec,
.table-account-item-mark {
  margin-top: 6rpx;
  color: var(--text-3);
  font-size: 25rpx;
  line-height: 1.35;
}



.table-account-item-mark {
  color: #9a6a21;
}



.table-account-item-qty {
  flex-shrink: 0;
  min-width: 52rpx;
  color: var(--text-2);
  font-size: 28rpx;
  font-weight: 800;
  text-align: right;
}



.table-account-item-amount {
  flex-shrink: 0;
  min-width: 118rpx;
  color: var(--text-1);
  font-size: 29rpx;
  font-weight: 900;
  text-align: right;
}



.table-account-empty {
  padding: 56rpx 20rpx;
  text-align: center;
}



.table-account-empty-title {
  display: block;
  color: var(--text-1);
  font-size: 32rpx;
  font-weight: 900;
}



.table-account-empty-desc {
  display: block;
  margin-top: 10rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 1.5;
}



.table-account-tip {
  margin: 18rpx 0 0;
  padding: 18rpx 22rpx;
  border-radius: 18rpx;
  background: #eef2f0;
  color: var(--text-3);
  font-size: 25rpx;
  line-height: 1.45;
}



.table-account-retry {
  width: 220rpx;
  height: 76rpx;
  margin: 24rpx auto 0;
  border-radius: 38rpx;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
}



.table-account-retry text {
  color: #fff;
  font-size: 28rpx;
  font-weight: 900;
}



.table-account-actions {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  display: flex;
  gap: 18rpx;
  padding: 18rpx 24rpx calc(18rpx + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1rpx solid #edf0f2;
  box-sizing: border-box;
}



.table-account-action {
  height: 92rpx;
  border-radius: 46rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}



.table-account-action text {
  font-size: 29rpx;
  font-weight: 900;
  white-space: nowrap;
}



.table-account-action--secondary {
  flex: 0 0 236rpx;
  border: 2rpx solid var(--brand);
  background: #fff;
  color: var(--brand);
}



.table-account-action--secondary text {
  color: var(--brand);
}



.table-account-action--primary {
  flex: 1;
  min-width: 0;
  background: var(--brand);
  color: #fff;
}



.table-account-action--primary text {
  color: #fff;
}



.table-account-action--ghost {
  background: #f1f4f3;
}



.table-account-action--ghost text {
  color: var(--text-2);
}



.table-account-action--disabled {
  opacity: .5;
}



/* 餐后付款没有可点击的"去结账"——结账动作在商家手里，这里只是一句提示，
   不能长得跟旁边的按钮一样可点，字号、字重都调低，允许换行。 */
.table-account-action--info {
  height: auto;
  min-height: 92rpx;
  background: #f6f7f8;
  padding: 12rpx 20rpx;
}



.table-account-action--info text {
  color: var(--text-2);
  font-size: 24rpx;
  font-weight: 600;
  white-space: normal;
  line-height: 1.4;
  text-align: center;
}
</style>
