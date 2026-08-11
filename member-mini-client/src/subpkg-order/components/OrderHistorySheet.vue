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
            <view class="table-status-badge" :class="{ 'table-status-badge--live': tableOrderStatusTone === 'preparing' }">
              <text class="table-status-badge-icon iconfont" :class="tableOrderStatusIcon"></text>
              <text>{{ tableOrderStatusBadge }}</text>
            </view>
            <text class="table-status-order-no">#{{ currentTableOrder.orderNo }}</text>
          </view>
          <!-- 之前这里连着堆了标题+副标题(tableOrderStatusHint)+下面的"下一步"提示条
          (tableOrderNextAction) 三层，preparing/paid 状态下三层说的其实是同一件事
          （"别管了，等着就行"），顾客要花时间确认这不是三条不同的信息。只留标题
          （"当前是什么状态"）和下一步提示条（"接下来该干嘛，逐状态都不一样、信息量
          更大"），去掉纯重复的副标题层。 -->
          <text class="table-status-main">{{ tableOrderStatusTitle }}</text>
          <view class="table-status-action">
            <text class="table-status-action-icon iconfont icon-roundright"></text>
            <text class="table-status-action-text">{{ tableOrderNextAction }}</text>
          </view>
        </view>

        <!-- 取餐牌号是顾客用来对上自己那份餐的实体凭证，比金额/时间更重要，之前跟其它
        四个小方块挤在同一个四列网格里、权重一样大，pickupNo 有值时还会多出第五个格子
        撑破网格排版、单独换行显得像排版错误。这里单独拎出来做成一整条、字号明显更大，
        网格永远固定桌号/金额/时间/份数四项，不会再因为桌牌号有没有而错位。 -->
        <view v-if="currentTableOrder.pickupNo" class="pickup-no-banner">
          <text class="pickup-no-banner-icon iconfont icon-form"></text>
          <text class="pickup-no-banner-text">桌牌 {{ currentTableOrder.pickupNo }} 号</text>
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
          <!-- 订单号/下单时间/份数上面状态卡和信息条已经露过一次了，这里只保留这个
          区块真正独有的信息——菜品清单本身，标题旁边留总价方便对着清单核对金额。 -->
          <view class="current-order-head">
            <view class="current-order-title-line">
              <text class="current-order-title-icon iconfont icon-list"></text>
              <text class="current-order-title">菜品明细</text>
            </view>
            <text class="current-order-total">{{ '¥' + formatPrice(currentTableOrder.total || 0) }}</text>
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
        <state-empty
          padded
          icon="🧾"
          title="暂无本桌订单"
          desc="选好菜品，点击下单即可开始"
        />
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
import StateEmpty from '@/components/state-empty/state-empty.vue'

export default {
  name: 'OrderHistorySheet',
  components: { StateEmpty },
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
@import '../styles/_shared.scss';

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

.table-status-card--canceled {
  --order-status-main: var(--danger);
  --order-status-soft: #fee2e2;
  --order-status-bg: #fff1f2;
  --order-status-border: #fecdd3;
}

.table-status-card--paid {
  --order-status-main: #0ea5e9;
  --order-status-soft: #e0f2fe;
  --order-status-bg: #eff8ff;
  --order-status-border: #bae6fd;
}

.table-status-card--accepted {
  --order-status-main: var(--warning);
  --order-status-soft: #fef3c7;
  --order-status-bg: #fffbeb;
  --order-status-border: #fde68a;
}

.table-status-card--served,
.table-status-card--completed {
  --order-status-main: var(--brand);
  --order-status-soft: #dcfce7;
  --order-status-bg: #ecfdf5;
  --order-status-border: #bbf7d0;
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
  color: var(--text-inverse);
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



@keyframes order-status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: .55; }
}

.table-status-badge--live .table-status-badge-icon {
  animation: order-status-pulse 1.6s ease-in-out infinite;
}

.pickup-no-banner {
  margin-top: 16rpx;
  padding: 16rpx 20rpx;
  border-radius: 16rpx;
  background: rgba(255,255,255,.85);
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.pickup-no-banner-icon {
  color: var(--order-status-main, var(--brand));
  font-size: 32rpx;
  line-height: 1;
}

.pickup-no-banner-text {
  color: var(--order-status-main, var(--brand));
  font-size: 34rpx;
  font-weight: 900;
  letter-spacing: 1rpx;
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
  background: var(--bg-card);
  border: 2rpx solid #f1f5f9;
}



.order-progress-head,
.current-order-head,
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

.order-progress-step.done .order-progress-line {
  background: var(--brand);
}

.order-progress-step.done .order-progress-dot,
.order-progress-step.active .order-progress-dot {
  background: var(--brand);
  color: var(--text-inverse);
}

@keyframes order-progress-ring-pulse {
  0%, 100% { box-shadow: 0 0 0 8rpx #dcfce7; }
  50% { box-shadow: 0 0 0 14rpx #dcfce7; }
}

.order-progress-step.active .order-progress-dot {
  animation: order-progress-ring-pulse 1.8s ease-in-out infinite;
}

.order-progress-step.done .order-progress-title,
.order-progress-step.active .order-progress-title {
  color: var(--text-1);
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



.current-order-total {
  font-size: 36rpx;
  font-weight: 900;
  color: var(--brand);
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
  background: var(--bg-card);
}



.orders-secondary-btn {
  height: 88rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  text { font-size: 30rpx; font-weight: 900; }
  background: var(--brand);
  text { color: var(--text-inverse); }
}

.orders-secondary-btn--canceled {
  background: var(--text-1);
}

.orders-secondary-btn--completed {
  background: #f3f5f7;
  text { color: var(--text-2); }
}
</style>
