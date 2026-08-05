<template>
  <view class="mask" @click="$emit('close')">
    <view class="orders-sheet" @click.stop>
      <view class="orders-sheet-head">
        <text class="orders-sheet-title">本桌订单</text>
        <text class="orders-sheet-close iconfont icon-close" @click="$emit('close')"></text>
      </view>

      <scroll-view v-if="currentTableOrder" class="orders-list" scroll-y>
        <view class="table-status-card" :class="'table-status-card--' + tableOrderStatusTone">
          <view class="table-status-top">
            <view class="table-status-badge">
              <text class="table-status-badge-icon iconfont" :class="tableOrderStatusIcon"></text>
              <text>{{ tableOrderStatusBadge }}</text>
            </view>
            <text class="table-status-order-no">#{{ currentTableOrder.orderNo }}</text>
          </view>
          <text class="table-status-main">{{ tableOrderStatusTitle }}</text>
          <text class="table-status-sub">{{ tableOrderStatusHint }}</text>
          <view class="table-status-action">
            <text class="table-status-action-icon iconfont icon-roundright"></text>
            <text class="table-status-action-text">{{ tableOrderNextAction }}</text>
          </view>
        </view>

        <view class="order-core-strip">
          <view class="order-core-item">
            <text class="order-core-icon iconfont icon-zuowei"></text>
            <text class="order-core-value">{{ tableNo || orderModeText.unknownTable }}</text>
          </view>
          <view class="order-core-item">
            <text class="order-core-icon order-core-icon--amount iconfont icon-pay"></text>
            <text class="order-core-value order-core-value--amount">{{ '¥' + formatPrice(currentTableOrder.total || 0) }}</text>
          </view>
          <view class="order-core-item">
            <text class="order-core-icon iconfont icon-timefill"></text>
            <text class="order-core-value">{{ currentTableOrder.createdAt || '-' }}</text>
          </view>
          <view class="order-core-item">
            <text class="order-core-icon iconfont icon-form"></text>
            <text class="order-core-value">{{ currentOrderItemCount + '份' }}</text>
          </view>
        </view>

        <view class="order-progress-card">
          <view class="order-progress-head">
            <text class="order-progress-card-title">订单进度</text>
            <text class="order-progress-card-sub">{{ tableOrderProgressSub }}</text>
          </view>
          <view class="order-progress-steps">
            <view v-for="step in tableOrderTimeline" :key="step.key" class="order-progress-step" :class="{ active: step.active, done: step.done }">
              <view class="order-progress-dot"><text class="iconfont" :class="step.icon"></text></view>
              <view v-if="step.key !== 'settled'" class="order-progress-line"></view>
              <text class="order-progress-title">{{ step.label }}</text>
            </view>
          </view>
        </view>

        <view class="current-order-card">
          <view class="current-order-head">
            <view>
              <view class="current-order-title-line">
                <text class="current-order-title-icon iconfont icon-list"></text>
                <text class="current-order-title">菜品明细</text>
              </view>
              <text class="current-order-no">#{{ currentTableOrder.orderNo }}</text>
            </view>
            <text class="current-order-total">{{ '¥' + formatPrice(currentTableOrder.total || 0) }}</text>
          </view>
          <view class="current-order-summary">
            <text>{{ '下单时间 ' + (currentTableOrder.createdAt || '-') }}</text>
            <text>{{ '共' + currentOrderItemCount + '份' }}</text>
          </view>
          <view v-if="currentTableOrder.items && currentTableOrder.items.length" class="current-order-items current-order-items--visible">
            <view v-for="(item, idx) in currentTableOrder.items" :key="item.specKey || item.id || item.name || idx" class="order-detail-row">
              <view class="order-detail-main">
                <text class="order-detail-name">{{ orderItemName(item) }}</text>
                <text v-if="orderItemSpecText(item)" class="order-detail-spec">{{ orderItemSpecText(item) }}</text>
              </view>
              <text class="order-detail-qty">{{ '×' + orderItemQty(item) }}</text>
              <text class="order-detail-amount">{{ '¥' + formatPrice(orderItemAmount(item)) }}</text>
            </view>
          </view>
          <view v-else class="current-order-empty-detail">
            <text>{{ currentOrderMainItemText }}</text>
          </view>
        </view>

        <view v-if="historyTableOrders.length" class="history-orders-card">
          <view class="history-orders-head" @click="$emit('toggle-history')">
            <text>历史订单</text>
            <text>{{ showAllOrders ? '收起' : '查看全部 ' + historyTableOrders.length }}</text>
          </view>
          <view v-if="showAllOrders">
            <view v-for="order in historyTableOrders" :key="order.id" class="history-order-block">
              <view class="history-order-row">
                <text>#{{ order.orderNo }} 共{{ orderItemCount(order) }}份</text>
                <text>¥{{ Number(order.total || 0).toFixed(2) }}</text>
              </view>
              <view v-if="(order.items || []).length" class="history-order-items">
                <view v-for="(item, idx) in order.items" :key="item.specKey || item.id || item.name || idx" class="history-order-item-row">
                  <text>{{ orderItemName(item) }} ×{{ orderItemQty(item) }}</text>
                  <text>¥{{ formatPrice(orderItemAmount(item)) }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>
      </scroll-view>

      <view v-else class="table-status-empty">
        <text class="table-status-empty-icon iconfont icon-list"></text>
        <text class="table-status-empty-title">暂无本桌订单</text>
        <text class="table-status-empty-desc">选好菜品，点击下单即可开始</text>
      </view>

      <view class="orders-actions">
        <view class="orders-secondary-btn" :class="'orders-secondary-btn--' + tableOrderStatusTone" @click="$emit('close')">
          <text>{{ tableOrderPrimaryButtonText }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的本桌订单弹层（原来是 showOrders && !isSharedBillMode 那一段
// 模板，非分账模式下的订单状态 + 历史订单视图）。纯展示组件，不带任何业务逻
// 辑——关闭、展开/收起历史订单都只 emit 出去，真正的状态还是父组件的
// showOrders/showAllOrders，一行逻辑都没有改。
export default {
  name: 'OrderHistorySheet',
  props: {
    currentTableOrder: { type: Object, default: null },
    historyTableOrders: { type: Array, default: () => [] },
    showAllOrders: { type: Boolean, default: false },
    tableOrderStatusTone: { type: String, default: '' },
    tableOrderStatusIcon: { type: String, default: '' },
    tableOrderStatusBadge: { type: String, default: '' },
    tableOrderNextAction: { type: String, default: '' },
    tableOrderStatusTitle: { type: String, default: '' },
    tableOrderStatusHint: { type: String, default: '' },
    tableOrderProgressSub: { type: String, default: '' },
    tableOrderTimeline: { type: Array, default: () => [] },
    currentOrderItemCount: { type: Number, default: 0 },
    currentOrderMainItemText: { type: String, default: '' },
    tableOrderPrimaryButtonText: { type: String, default: '' },
    tableNo: { type: [String, Number], default: '' },
    orderModeText: { type: Object, required: true },
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑）。
    formatPrice: { type: Function, required: true },
    orderItemName: { type: Function, required: true },
    orderItemSpecText: { type: Function, required: true },
    orderItemQty: { type: Function, required: true },
    orderItemAmount: { type: Function, required: true },
    orderItemCount: { type: Function, required: true },
  },
  emits: ['close', 'toggle-history'],
}
</script>

<style lang="scss">
.orders-list {
  flex: 1;
  width: 100%;
  padding: 8rpx 32rpx 20rpx;
  box-sizing: border-box;
}




.table-status-card {
  padding: 30rpx;
  border-radius: var(--radius-card);
  border: 2rpx solid var(--order-status-border, #bae6fd);
  background: var(--order-status-bg, #eff8ff);
  box-sizing: border-box;
}



.table-status-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  min-width: 0;
}



.table-status-badge {
  height: 52rpx;
  padding: 0 22rpx;
  border-radius: 999rpx;
  background: var(--order-status-main, var(--brand));
  display: inline-flex;
  align-items: center;
  gap: 8rpx;
  color: #fff;
  font-size: 24rpx;
  font-weight: 900;
  white-space: nowrap;
}



.table-status-badge-icon {
  font-size: 24rpx;
  line-height: 1;
}



.table-status-order-no {
  min-width: 0;
  color: var(--text-3);
  font-size: 24rpx;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.table-status-main {
  display: block;
  margin-top: 22rpx;
  color: var(--order-status-main, var(--brand));
  font-size: 42rpx;
  line-height: 50rpx;
  font-weight: 900;
  letter-spacing: 0;
}



.table-status-sub {
  display: block;
  margin-top: 12rpx;
  color: var(--text-2);
  font-size: 26rpx;
  line-height: 38rpx;
  font-weight: 600;
}



.table-status-action {
  margin-top: 20rpx;
  min-height: 64rpx;
  padding: 14rpx 18rpx;
  border-radius: 18rpx;
  background: rgba(255,255,255,.72);
  display: flex;
  align-items: center;
  gap: 14rpx;
  box-sizing: border-box;
}



.table-status-action-icon {
  flex-shrink: 0;
  color: var(--order-status-main, var(--brand));
  font-size: 26rpx;
  line-height: 1;
}



.table-status-action-text {
  min-width: 0;
  color: var(--order-status-main, var(--brand));
  font-size: 26rpx;
  font-weight: 900;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.order-core-strip {
  margin-top: 16rpx;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10rpx;
}



.order-core-item {
  min-width: 0;
  height: 104rpx;
  border-radius: 18rpx;
  background: #f8fafb;
  border: 1rpx solid #edf0f2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}



.order-core-icon {
  color: var(--text-3);
  font-size: 30rpx;
  line-height: 1;
}



.order-core-icon--amount {
  color: var(--brand);
}



.order-core-value {
  max-width: 100%;
  margin-top: 10rpx;
  color: var(--text-1);
  font-size: 26rpx;
  line-height: 30rpx;
  font-weight: 900;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.order-core-value--amount {
  color: var(--brand);
}



.order-progress-card,
.current-order-card,
.history-orders-card {
  margin-top: 20rpx;
  padding: 24rpx;
  border-radius: var(--radius-card);
  background: #fff;
  border: 2rpx solid #f1f5f9;
}



.order-progress-head,
.current-order-head,
.current-order-summary,
.history-orders-head,
.history-order-row {
  display: flex;
  justify-content: space-between;
  gap: 20rpx;
  align-items: center;
}



.order-progress-card-title {
  font-size: 30rpx;
  font-weight: 900;
  color: var(--text-1);
}



.order-progress-card-sub {
  min-width: 0;
  color: var(--text-3);
  font-size: 23rpx;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.order-progress-steps {
  margin-top: 24rpx;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8rpx;
}



.order-progress-step {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  color: var(--text-3);
}



.order-progress-dot {
  position: relative;
  z-index: 2;
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  background: #eef0f2;
  color: #9aa1aa;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26rpx;
}



.order-progress-line {
  position: absolute;
  z-index: 1;
  top: 23rpx;
  left: calc(50% + 28rpx);
  right: calc(-50% + 28rpx);
  height: 3rpx;
  border-radius: 3rpx;
  background: #e5e7eb;
}



.order-progress-title {
  display: block;
  width: 100%;
  margin-top: 14rpx;
  font-size: 22rpx;
  line-height: 30rpx;
  font-weight: 800;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.current-order-title-line {
  display: flex;
  align-items: center;
  gap: 8rpx;
}



.current-order-title-icon {
  color: var(--brand);
  font-size: 28rpx;
  line-height: 1;
}



.current-order-title {
  display: block;
  font-size: 30rpx;
  font-weight: 900;
  color: var(--text-1);
}



.current-order-no {
  display: block;
  margin-top: 4rpx;
  font-size: 24rpx;
  color: var(--text-3);
}



.current-order-total {
  font-size: 36rpx;
  font-weight: 900;
  color: var(--brand);
}



.current-order-summary {
  margin-top: 20rpx;
  padding-top: 18rpx;
  border-top: 2rpx solid #f1f5f9;
  text { font-size: 26rpx; color: var(--text-2); }
  text:first-child { color: var(--text-1); font-weight: 900; }
}



.current-order-items {
  margin-top: 10rpx;
  padding-top: 0;
}



.current-order-items--visible {
  display: block;
}



.current-order-empty-detail {
  margin-top: 14rpx;
  padding: 18rpx 0 4rpx;
  border-top: 1rpx solid #f1f5f9;
  text { font-size: 26rpx; color: var(--text-3); }
}



.order-detail-row {
  display: flex;
  align-items: flex-start;
  gap: 16rpx;
  padding: 16rpx 0;
  border-top: 1rpx solid #f1f5f9;
}



.order-detail-main {
  flex: 1;
  min-width: 0;
}



.order-detail-name,
.order-detail-spec {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}



.order-detail-name {
  font-size: 28rpx;
  color: var(--text-1);
  font-weight: 700;
}



.order-detail-spec {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--text-3);
}



.order-detail-qty {
  width: 72rpx;
  text-align: right;
  font-size: 26rpx;
  color: var(--text-3);
}



.order-detail-amount {
  width: 110rpx;
  text-align: right;
  font-size: 26rpx;
  color: var(--text-1);
  font-weight: 800;
}



.history-orders-head {
  text:first-child { font-size: 28rpx; font-weight: 800; color: var(--text-1); }
  text:last-child { font-size: 24rpx; color: var(--brand); font-weight: 700; }
}



.history-order-block {
  margin-top: 18rpx;
  padding-top: 18rpx;
  border-top: 2rpx solid #f1f5f9;
}



.history-order-row {
  text { font-size: 25rpx; color: var(--text-3); }
  text:last-child { color: var(--text-1); font-weight: 800; }
}



.history-order-items {
  margin-top: 10rpx;
}



.history-order-item-row {
  display: flex;
  justify-content: space-between;
  gap: 16rpx;
  padding: 8rpx 0;
  text { font-size: 23rpx; color: var(--text-3); }
  text:first-child { flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  text:last-child { color: var(--text-2); font-weight: 700; }
}



.orders-actions {
  flex-shrink: 0;
  padding: 8rpx 32rpx 0;
  background: #fff;
}



.orders-secondary-btn {
  height: 88rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  text { font-size: 30rpx; font-weight: 900; }
  background: var(--brand);
  text { color: #fff; }
}
</style>
