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
