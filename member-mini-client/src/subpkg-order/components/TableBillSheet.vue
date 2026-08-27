<template>
  <base-sheet
    class="table-order-sheet"
    layer="blocking"
    title="本桌订单"
    @close="emitCloseOrFinish"
  >
      <template #header-left>
        <view class="to-back" @click="emitCloseOrFinish">
          <text class="iconfont icon-back"></text>
        </view>
      </template>

      <scroll-view v-if="!loadError" class="to-scroll" scroll-y>
        <view v-if="tableOrderGroups.length" id="table-account-status-anchor" class="to-card" :class="'to-card--' + tableStatusView.tone">
          <view class="to-head">
            <view class="to-ident">
              <text class="to-ident-main">{{ tableNo || orderModeText.unknownTable }} 桌</text>
              <text v-if="pickupNoEnabled && tablePickupNo" class="to-ident-line">桌牌 {{ tablePickupNo }} 号</text>
            </view>
          </view>

          <!-- 进度图例：四个点各代表哪一步，出现一次。之后每道菜左侧的点
               自己说话，不再逐条配文字。 -->
          <view class="to-legend">
            <view v-for="(label, i) in stageLabels" :key="label" class="to-legend-item">
              <view class="to-legend-dot" :class="{ on: i === 0 }"></view>
              <text class="to-legend-t">{{ label }}</text>
            </view>
          </view>

          <view class="to-divider"></view>

          <!-- 默认视图只回答顾客真正在问的两件事：点了多少菜、要付多少钱。
               同一道菜跨批次合并成一行，不按"第几单"拆开——分单是系统的组织方式。 -->
          <view class="to-list">
            <view
              v-for="row in mergedItems"
              :key="row.key"
              class="to-drow"
              :class="{ 'to-drow--muted': row.isInvalid }"
            >
              <!-- 这道菜走到哪一步，四个点自己说，不配文字。 -->
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
              <!-- 谁点的：拼桌时顾客要确认"这道菜是我点的还是同桌点的" -->
              <view
                v-if="row.participantNo"
                class="to-drow-who"
                :style="{ background: row.participantColor }"
              >{{ row.participantNo }}</view>
              <text class="to-drow-qty">×{{ row.qty }}</text>
              <view class="to-drow-money">
                <text class="to-drow-amt">¥{{ formatPrice(row.amount) }}</text>
                <!-- 这道菜已经单独付过款，不在本次结账里。标在金额旁边，
                     合计就自己解释得通，不需要底部再加一句说明。 -->
                <text v-if="row.isPrepaid" class="to-drow-paid">已付</text>
              </view>
            </view>
          </view>

          <view v-if="tableDiscountTotal > 0" class="to-line">
            <text class="to-line-l">优惠</text>
            <text class="to-line-v">-¥{{ formatPrice(tableDiscountTotal) }}</text>
          </view>

          <view class="to-foot">
            <text class="to-foot-l">共 {{ displayItemCount }} 份</text>
            <text class="to-foot-v"><text class="to-cur">¥</text>{{ formatPrice(tableTotal) }}</text>
          </view>
        </view>

        <!-- 详细数据一直都在，只是默认不推给顾客。想看再展开。 -->
        <view v-if="tableOrderGroups.length" class="to-detail">
          <view class="to-detail-head" @click="showDetail = !showDetail">
            <text class="to-detail-t">订单详情</text>
            <text class="to-detail-a">{{ showDetail ? '收起' : '展开' }}</text>
          </view>
          <view v-if="showDetail" class="to-detail-body">
            <view v-for="group in tableOrderGroups" :key="group.id" class="to-group">
              <view class="to-round">
                <view class="to-round-left">
                  <view
                    v-if="group.participantNo"
                    class="to-round-badge"
                    :style="{ background: group.participantColor }"
                  >{{ group.participantNo }}</view>
                  <text class="to-round-t">{{ group.title }} · #{{ group.orderNo }}</text>
                  <text v-if="group.isPrepaid" class="to-round-paid">已单独付款</text>
                  <text v-if="group.discountAmount > 0" class="to-round-discount">优惠 -¥{{ formatPrice(group.discountAmount) }}</text>
                </view>
                <text class="to-round-tag" :class="'to-round-tag--' + group.tone">{{ group.statusText }}</text>
              </view>
              <text v-if="group.isStaff" class="to-round-staff">服务员代点{{ group.staffNote ? ' · ' + group.staffNote : '' }}</text>
              <view
                v-for="(item, idx) in group.items"
                :key="item.specKey || item.dish_id || item.id || item.name || idx"
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

        <view v-else class="to-empty">
          <state-empty
            padded
            icon="🍽️"
            title="本桌还没点菜"
            desc="选好菜品加入购物车即可下单"
          />
        </view>

        <!-- 加菜合并提示：只在第一单（还没加过菜）时给；加过一次之后顾客已经知道会合并，
             常驻反而是噪音。原来是一整句解释，缩到只留结论。 -->
        <view v-if="tableOrderGroups.length === 1 && !isTableSettled" class="to-hint-note">
          <text>加菜自动并入本单，无需重复付款</text>
        </view>
      </scroll-view>

      <view v-else class="table-status-empty">
        <state-error
          padded
          title="本桌订单加载失败"
          desc="请重新加载后再查看本桌账单"
          retry-text="重新加载"
          @retry="$emit('retry-load')"
        />
      </view>

      <template #footer>
      <!-- SETTLED：只保留「完成」；ACTIVE：继续加菜 + 结账相关操作 -->
      <view v-if="isTableSettled" class="table-account-actions">
        <view class="table-account-action table-account-action--primary" @click="$emit('finish')">
          <text>完成</text>
        </view>
      </view>
      <view v-else class="table-account-actions">
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
          <text>{{ tableCheckouting ? '呼叫中…' : (checkoutRequested ? '已呼叫服务员' : '去结账') }}</text>
        </view>
        <view
          v-else-if="stillPreparing"
          class="table-account-action table-account-action--primary table-account-action--disabled"
        >
          <!-- 说"什么时候能结"比说"为什么现在不能结"更有用，也更短 -->
          <text>上齐后可结账</text>
        </view>
        <view
          v-else-if="postpayReadyToSettle"
          class="table-account-action table-account-action--info"
        >
          <text>请到收银台结账</text>
        </view>
      </view>
      </template>
  </base-sheet>
</template>

<script>
// 从 menu.vue 拆出来的桌台账单弹层（原来是 showOrders && isSharedBillMode 那一段
// 模板）。纯展示组件，不带任何业务逻辑——所有需要改父组件状态的动作都只 emit 出去。
//
// 默认视图只回答顾客真正在问的两件事：点了多少菜、要付多少钱。
// 状态只用一个胶囊 + 一句提示表达（没有进度条——同一件事不做两种表达）；
// 订单号、下单时间、分单、每单各自的状态都是系统数据，收在「订单详情」折叠区，
// 顾客想看再展开。跟 OrderHistorySheet 用同一套 `.to-*` 卡片结构。
import StateEmpty from '@/components/state-empty/state-empty.vue'
import StateError from '@/components/state-error/state-error.vue'
import BaseSheet from '@/components/base-sheet/base-sheet.vue'

export default {
  name: 'TableBillSheet',
  components: { StateEmpty, StateError, BaseSheet },
  props: {
    loadError: { type: Boolean, default: false },
    tableStatusView: { type: Object, required: true },
    tableNo: { type: [String, Number], default: '' },
    // P1 修复：menu.vue 一直在传这两个 prop，桌牌号在方案B里放进右侧身份栏。
    pickupNoEnabled: { type: Boolean, default: false },
    tablePickupNo: { type: [String, Number], default: '' },
    orderModeText: { type: Object, required: true },
    sharedBillSubLabel: { type: String, default: '' },
    tableBillPayStateText: { type: String, default: '' },
    tableTotal: { type: Number, default: 0 },
    // 展示口径的份数（这一桌一共点了多少菜），不是结算口径的 tableItemCount。
    displayItemCount: { type: Number, default: 0 },
    // PRODUCT_RULES 第4条：优惠一眼可见，不藏在分单里。
    tableDiscountTotal: { type: Number, default: 0 },
    tableOrderGroups: { type: Array, default: () => [] },
    orderItemImageFailed: { type: Object, default: () => ({}) },
    canContinueOrder: { type: Boolean, default: false },
    canCheckout: { type: Boolean, default: false },
    isTableSettled: { type: Boolean, default: false },
    stillPreparing: { type: Boolean, default: false },
    postpayReadyToSettle: { type: Boolean, default: false },
    tableCheckouting: { type: Boolean, default: false },
    checkoutRequested: { type: Boolean, default: false },
    formatPrice: { type: Function, required: true },
    orderItemImage: { type: Function, required: true },
    orderItemName: { type: Function, required: true },
    orderItemSpecText: { type: Function, required: true },
    orderItemQty: { type: Function, required: true },
    orderItemAmount: { type: Function, required: true },
  },
  emits: ['close', 'finish', 'retry-load', 'continue-order', 'checkout', 'mark-image-failed'],
  data() {
    // 纯 UI 展开态，不是业务状态，所以留在组件本地，不往父组件抬。
    return { showDetail: false, stageLabels: ['下单', '接单', '上齐', '完成'] }
  },
  computed: {
    stageCount() {
      return this.stageLabels.length
    },
    // 同一道菜合并成一行——顾客问的是"点了什么"，不是"这道菜分几次点的"。
    // 合并键的每一个维度都是顾客会区分的东西：
    //   规格不同 = 不同的菜；谁点的不同 = 不能混；进度不同 = 点点要能分别表达；
    //   已单独付款的不进本次结账；已退菜/已取消的单独成行。
    // 「第几单、几点下的」不在键里——那是系统的组织方式，顾客不关心。
    mergedItems() {
      const rows = []
      const index = new Map()
      for (const group of this.tableOrderGroups) {
        for (const item of group.items) {
          const name = this.orderItemName(item)
          const spec = this.orderItemSpecText(item) || ''
          const stage = item.isInvalid ? -1 : group.stage
          const key = [
            item.specKey || name,
            spec,
            group.participantNo || '',
            stage,
            group.isPrepaid ? 'paid' : '',
            item.isInvalid ? 'void' : '',
          ].join('|')
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
            isPrepaid: group.isPrepaid,
            isInvalid: item.isInvalid,
            invalidText: item.invalidText,
          }
          index.set(key, row)
          rows.push(row)
        }
      }
      return rows
    },
  },
  methods: {
    emitCloseOrFinish() {
      if (this.isTableSettled) this.$emit('finish')
      else this.$emit('close')
    },
  },
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';
@import './table-order-card.scss';

.table-order-sheet {
  background: var(--bg-subtle);
  padding-bottom: 0;
}

.to-back {
  position: absolute;
  left: 18rpx;
  top: 12rpx;
  width: 64rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-2);

  text {
    font-size: 34rpx;
  }
}

.to-scroll {
  max-height: calc(82vh - 176rpx - env(safe-area-inset-bottom));
  padding: 8rpx 24rpx 188rpx;
  box-sizing: border-box;
}

.to-empty {
  padding: 24rpx 0;
}

/* footer 动作区沿用原样式（模板未改），只是状态类前缀保持 table-account-* */
.table-account-actions {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  display: flex;
  gap: 18rpx;
  padding: 18rpx 24rpx calc(18rpx + env(safe-area-inset-bottom));
  background: var(--bg-card);
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

  text {
    font-size: 29rpx;
    font-weight: 900;
    white-space: nowrap;
  }
}

.table-account-action--secondary {
  flex: 0 0 236rpx;
  border: 2rpx solid var(--brand);
  background: var(--bg-card);
  color: var(--brand);

  text {
    color: var(--brand);
  }
}

.table-account-action--primary {
  flex: 1;
  min-width: 0;
  background: var(--brand);
  color: var(--text-inverse);

  text {
    color: var(--text-inverse);
  }
}

.table-account-action--disabled {
  opacity: .5;
}

/* 餐后付款没有可点击的"去结账"——结账动作在商家手里，这里只是一句提示，
   不能长得跟旁边的按钮一样可点，字号、字重都调低，允许换行。 */
.table-account-action--info {
  height: auto;
  min-height: 92rpx;
  background: var(--bg-subtle);
  padding: 12rpx 20rpx;

  text {
    color: var(--text-2);
    font-size: 24rpx;
    font-weight: 600;
    white-space: normal;
    line-height: 1.4;
    text-align: center;
  }
}
</style>
