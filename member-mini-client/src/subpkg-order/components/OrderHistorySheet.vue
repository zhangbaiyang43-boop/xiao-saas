<template>
  <base-sheet layer="blocking" title="本桌订单" @close="$emit('close')">
      <scroll-view v-if="currentTableOrder" class="orders-list" scroll-y>
        <view v-if="currentTableOrder.refundRequired" class="refund-attention-card">
          <text class="refund-attention-title">订单已取消，付款已成功，请联系商家处理退款</text>
          <text class="refund-attention-sub">请保留订单信息并联系商家处理退款。</text>
        </view>

        <view class="to-card" :class="'to-card--' + cardTone">
          <view class="to-head">
            <view class="to-head-status">
              <text class="to-badge">{{ tableOrderStatusBadge }}</text>
              <text class="to-desc">{{ tableOrderNextAction }}</text>
            </view>
            <view class="to-ident">
              <text class="to-ident-main">店内 {{ tableNo || orderModeText.unknownTable }} 桌</text>
              <text v-if="currentTableOrder.pickupNo" class="to-ident-line">桌牌 {{ currentTableOrder.pickupNo }} 号</text>
              <text class="to-ident-line">#{{ currentTableOrder.orderNo }}</text>
            </view>
          </view>

          <!-- 未支付的单不画进度条：进度条断言的是一条"已经开始走"的出餐流程，
               而这一单还卡在付款，画出来等于告诉顾客"正在处理中，你不用管"。 -->
          <view v-if="tableOrderTimeline.length && !isAwaitingPayment" class="to-track">
            <view class="to-track-bar">
              <text class="to-track-end">{{ tableOrderTimeline[0].label }}</text>
              <view class="to-track-rail">
                <view
                  v-for="(step, i) in tableOrderTimeline"
                  :key="step.key"
                  class="to-track-step"
                  :class="{ done: step.done, now: step.active }"
                >
                  <view class="to-track-node"></view>
                  <view v-if="i < tableOrderTimeline.length - 1" class="to-track-seg"></view>
                </view>
              </view>
              <text class="to-track-end">{{ tableOrderTimeline[tableOrderTimeline.length - 1].label }}</text>
            </view>
          </view>

          <view class="to-divider"></view>

          <view v-if="currentTableOrder.items && currentTableOrder.items.length" class="to-list">
            <view
              v-for="(item, idx) in currentTableOrder.items"
              :key="item.specKey || item.id || item.name || idx"
              class="to-drow"
            >
              <image
                v-if="orderItemImage(item) && !orderItemImageFailed['cur_' + idx]"
                class="to-drow-img"
                :src="orderItemImage(item)"
                mode="aspectFill"
                @error="$emit('mark-image-failed', 'cur_' + idx)"
              />
              <view v-else class="to-drow-img to-drow-img--ph">
                <image class="to-drow-img-ph" src="/static/order/dish-placeholder.png" mode="aspectFit" />
              </view>
              <view class="to-drow-main">
                <text class="to-drow-name">{{ orderItemName(item) }}</text>
                <text v-if="orderItemSpecText(item)" class="to-drow-spec">{{ orderItemSpecText(item) }}</text>
              </view>
              <text class="to-drow-qty">×{{ orderItemQty(item) }}</text>
              <text class="to-drow-amt">¥{{ formatPrice(orderItemAmount(item)) }}</text>
            </view>
          </view>
          <view v-else class="to-list">
            <view class="to-drow to-drow--muted">
              <text class="to-drow-name">{{ currentOrderMainItemText }}</text>
            </view>
          </view>

          <view class="to-foot">
            <text class="to-foot-l">共 {{ currentOrderItemCount }} 份 · {{ paidStateText }}</text>
            <text class="to-foot-v"><text class="to-cur">¥</text>{{ formatPrice(currentTableOrder.total || 0) }}</text>
          </view>
        </view>

        <view class="to-submeta">{{ (currentTableOrder.createdAt || '-') }} 下单 · 先付后厨</view>

        <view v-if="historyTableOrders.length" class="history-orders-card">
          <!-- P1：本桌合计（当前这一笔 + 历史订单加总），纯展示性小结，不是应付金额——
          prepay 每一笔都已经各自付清，不存在欠款。 -->
          <view class="history-orders-summary">
            <text>本桌共点 {{ orderHistoryItemCount }} 份</text>
            <text>¥{{ formatPrice(orderHistoryTotal) }}</text>
          </view>
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
        <state-empty
          padded
          icon="🧾"
          title="暂无本桌订单"
          desc="选好菜品，点击下单即可开始"
        />
      </view>

      <template #footer>
      <view class="orders-actions">
        <view class="orders-secondary-btn" :class="'orders-secondary-btn--' + tableOrderStatusTone" @click="$emit('close')">
          <text>{{ tableOrderPrimaryButtonText }}</text>
        </view>
      </view>
      </template>
  </base-sheet>
</template>

<script>
// 从 menu.vue 拆出来的本桌订单弹层（非分账模式 / 先付后厨下的订单状态 + 历史订单
// 视图）。纯展示组件，不带任何业务逻辑——关闭、展开/收起历史订单都只 emit 出去。
//
// 方案B（聚合式）改版：状态胶囊 + 右侧身份栏（桌号/桌牌/单号）+ 压缩进度条 +
// 平铺菜品清单 + 卡底合计。四宫格信息条、独立的「订单进度」大卡都收进这张卡里。
// 跟 TableBillSheet 用同一套 `.to-*` 结构。退款提醒卡、历史订单/本桌合计卡是
// 先付后厨专属信息，保留。
import StateEmpty from '@/components/state-empty/state-empty.vue'
import BaseSheet from '@/components/base-sheet/base-sheet.vue'

export default {
  name: 'OrderHistorySheet',
  components: { StateEmpty, BaseSheet },
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
    // 这一单的钱还没收到（pending_payment 等）——决定卡片配色、要不要画进度条。
    isAwaitingPayment: { type: Boolean, default: false },
    currentOrderItemCount: { type: Number, default: 0 },
    currentOrderMainItemText: { type: String, default: '' },
    // 菜品行缩略图——跟 TableBillSheet 对齐，取不到落占位图。
    orderItemImageFailed: { type: Object, default: () => ({}) },
    // P1 修复：本桌合计（当前这一笔 + 历史订单加总），纯展示性小结，不是应付
    // 金额——prepay 每一笔都已经各自付清，不存在欠款。
    orderHistoryTotal: { type: Number, default: 0 },
    orderHistoryItemCount: { type: Number, default: 0 },
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
    orderItemImage: { type: Function, required: true },
  },
  emits: ['close', 'toggle-history', 'mark-image-failed'],
  computed: {
    // 颜色即优先级：未支付是顾客当下唯一需要动手的状态，必须跟"待接单"
    // （同样是琥珀色的等待态）区分开，不能长得一样。
    cardTone() {
      if (this.isAwaitingPayment) return 'unpaid'
      return this.tableOrderStatusTone === 'paid' ? 'wait' : this.tableOrderStatusTone
    },
    // 卡底的收款状态——先付后厨绝大多数是"已在线支付"，但不能对
    // pending_payment / 已结账 的单也这么写死。
    paidStateText() {
      if (this.isAwaitingPayment) return '待支付'
      const raw = String((this.currentTableOrder && this.currentTableOrder.status) || '')
      if (raw === 'settled') return '已结账'
      return '已在线支付'
    },
  },
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';
@import './table-order-card.scss';

.orders-list {
  flex: 1;
  width: 100%;
  padding: 8rpx 32rpx 20rpx;
  box-sizing: border-box;
}

.refund-attention-card {
  margin-top: 12rpx;
  padding: 22rpx 24rpx;
  border: 2rpx solid #fecaca;
  border-radius: 18rpx;
  background: #fef2f2;
}

.refund-attention-title,
.refund-attention-sub {
  display: block;
}

.refund-attention-title {
  color: #b91c1c;
  font-size: 28rpx;
  font-weight: 900;
  line-height: 40rpx;
}

.refund-attention-sub {
  margin-top: 8rpx;
  color: #7f1d1d;
  font-size: 24rpx;
  line-height: 34rpx;
}

.history-orders-card {
  margin-top: 20rpx;
  padding: 24rpx;
  border-radius: var(--radius-card);
  background: var(--bg-card);
  border: 2rpx solid #f1f5f9;
}

.history-orders-summary {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-bottom: 14rpx;
  margin-bottom: 14rpx;
  border-bottom: 2rpx solid #f1f5f9;

  text:first-child { font-size: 25rpx; color: var(--text-3); font-weight: 700; }
  text:last-child { font-size: 32rpx; color: var(--brand); font-weight: 900; }
}

.history-orders-head {
  display: flex;
  justify-content: space-between;
  align-items: center;

  text:first-child { font-size: 28rpx; font-weight: 800; color: var(--text-1); }
  text:last-child { font-size: 24rpx; color: var(--brand); font-weight: 700; }
}

.history-order-block {
  margin-top: 18rpx;
  padding-top: 18rpx;
  border-top: 2rpx solid #f1f5f9;
}

.history-order-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16rpx;

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
  background: var(--bg-card);
}

.orders-secondary-btn {
  height: 88rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand);

  text { font-size: 30rpx; font-weight: 900; color: var(--text-inverse); }
}

.orders-secondary-btn--canceled {
  background: var(--text-1);
}

.orders-secondary-btn--completed,
.orders-secondary-btn--settled {
  background: #f3f5f7;

  text { color: var(--text-2); }
}
</style>
