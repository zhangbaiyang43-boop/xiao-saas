<template>
  <base-sheet layer="blocking" title="本桌订单" @close="$emit('close')">
      <scroll-view v-if="currentTableOrder" class="orders-list" scroll-y>
        <view v-if="currentTableOrder.refundRequired" class="refund-attention-card">
          <text class="refund-attention-title">订单已取消，付款已成功，请联系商家处理退款</text>
          <text class="refund-attention-sub">请保留订单信息并联系商家处理退款。</text>
        </view>

        <view class="to-card" :class="'to-card--' + cardTone">
          <view class="to-plate">
            <text class="to-plate-table">{{ tableNo || orderModeText.unknownTable }}</text>
            <text class="to-plate-unit">桌</text>
            <template v-if="currentTableOrder.pickupNo">
              <view class="to-plate-sep"></view>
              <text class="to-plate-pickup">桌牌 {{ currentTableOrder.pickupNo }} 号</text>
            </template>
          </view>

          <!-- 只有需要顾客动手时才出文字（这里就是"钱还没付"）。
               正常流程的状态由每道菜左边的四个点表达，不配解释句。 -->
          <view v-if="isAwaitingPayment" class="to-head-status">
            <text class="to-badge">{{ tableOrderStatusBadge }}</text>
            <text class="to-desc">{{ tableOrderNextAction }}</text>
          </view>

          <view class="to-divider"></view>

          <!-- 顾客问的是"这一桌点了多少菜、花了多少钱"，所以这里是全桌合并清单，
               不是"当前这一笔"。哪道菜属于哪一单，是系统的组织方式，收在详情里。 -->
          <view v-if="mergedItems.length" class="to-list">
            <view
              v-for="row in mergedItems"
              :key="row.key"
              class="to-drow"
              :class="{ 'to-drow--muted': row.isInvalid }"
            >
              <view class="to-stage" :class="{ 'to-stage--void': row.stage < 0 }">
                <view
                  v-for="n in stageCount"
                  :key="n"
                  class="to-stage-dot"
                  :class="{ on: row.stage >= n }"
                ></view>
              </view>
              <image
                v-if="row.image && !orderItemImageFailed[row.key]"
                class="to-drow-img"
                :src="row.image"
                mode="aspectFill"
                @error="$emit('mark-image-failed', row.key)"
              />
              <view v-else class="to-drow-img to-drow-img--ph">
                <image class="to-drow-img-ph" src="/static/order/dish-placeholder.png" mode="aspectFit" />
              </view>
              <view class="to-drow-main">
                <text class="to-drow-name">{{ row.name }}</text>
                <text v-if="row.spec" class="to-drow-spec">{{ row.spec }}</text>
                <text v-if="row.isInvalid" class="to-drow-mark">{{ row.invalidText }}</text>
              </view>
              <view
                v-if="row.participantNo"
                class="to-drow-who"
                :style="{ background: row.participantColor }"
              >{{ row.participantNo }}</view>
              <text class="to-drow-qty">×{{ row.qty }}</text>
              <text class="to-drow-amt">¥{{ formatPrice(row.amount) }}</text>
            </view>
          </view>
          <view v-else class="to-list">
            <view class="to-drow to-drow--muted">
              <text class="to-drow-name">{{ currentOrderMainItemText }}</text>
            </view>
          </view>

          <view class="to-foot">
            <text class="to-foot-l">共 {{ orderHistoryItemCount }} 份</text>
            <text class="to-foot-v"><text class="to-cur">¥</text>{{ formatPrice(orderHistoryTotal) }}</text>
          </view>
        </view>

        <!-- 详细数据一直都在，只是默认不推给顾客。想看再展开。 -->
        <view v-if="orderHistoryGroups.length" class="to-detail">
          <view class="to-detail-head" @click="$emit('toggle-history')">
            <text class="to-detail-t">订单详情</text>
            <text class="to-detail-a">{{ showAllOrders ? '收起' : '展开' }}</text>
          </view>
          <view v-if="showAllOrders" class="to-detail-body">
            <view class="history-orders-summary">
              <text>本桌共点 {{ orderHistoryItemCount }} 份</text>
              <text>¥{{ formatPrice(orderHistoryTotal) }}</text>
            </view>
            <view v-for="group in orderHistoryGroups" :key="group.id" class="to-group">
              <view class="to-round">
                <view class="to-round-left">
                  <text class="to-round-t">{{ group.title }} · #{{ group.orderNo }}</text>
                  <text v-if="group.discountAmount > 0" class="to-round-discount">优惠 -¥{{ formatPrice(group.discountAmount) }}</text>
                </view>
                <text class="to-round-tag" :class="'to-round-tag--' + group.tone">{{ group.statusText }}</text>
              </view>
              <view
                v-for="(item, idx) in group.items"
                :key="item.specKey || item.id || item.name || idx"
                class="to-drow to-drow--plain"
                :class="{ 'to-drow--muted': item.isInvalid }"
              >
                <view class="to-drow-main">
                  <text class="to-drow-name">{{ orderItemName(item) }}</text>
                  <text v-if="orderItemSpecText(item)" class="to-drow-spec">{{ orderItemSpecText(item) }}</text>
                </view>
                <text class="to-drow-qty">×{{ orderItemQty(item) }}</text>
                <text class="to-drow-amt">¥{{ formatPrice(orderItemAmount(item)) }}</text>
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
    // 全桌分单流水（当前这一笔 + 历史订单），只在「订单详情」折叠区里渲染。
    orderHistoryGroups: { type: Array, default: () => [] },
    // 这一单的钱还没收到（pending_payment 等）——决定卡片配色。
    isAwaitingPayment: { type: Boolean, default: false },
    // 进度点的个数，跟 useTableBillView.orderStageIndex 的档数同源，避免两处各写一个 4。
    stageCount: { type: Number, default: 4 },
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
    // 全桌菜品合并成一行一道菜。跟 TableBillSheet.mergedItems 同一套规则，
    // 只是这边的数据源是 orderHistoryGroups（prepay 每单各自付清，没有"已付/待付"
    // 之分，所以合并键不带 paid 维度）。
    mergedItems() {
      const rows = []
      const index = new Map()
      for (const group of this.orderHistoryGroups) {
        for (const item of group.items) {
          const name = this.orderItemName(item)
          const spec = this.orderItemSpecText(item) || ''
          const stage = item.isInvalid ? -1 : group.stage
          const key = [item.specKey || name, spec, group.participantNo || '', stage, item.isInvalid ? 'void' : ''].join('|')
          const existing = index.get(key)
          if (existing) {
            existing.qty += this.orderItemQty(item)
            existing.amount += Number(this.orderItemAmount(item)) || 0
            continue
          }
          const row = {
            key,
            name,
            spec,
            stage,
            qty: this.orderItemQty(item),
            amount: Number(this.orderItemAmount(item)) || 0,
            image: this.orderItemImage(item),
            participantNo: group.participantNo,
            participantColor: group.participantColor,
            isInvalid: item.isInvalid,
            invalidText: item.invalidText,
          }
          index.set(key, row)
          rows.push(row)
        }
      }
      return rows
    },
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
