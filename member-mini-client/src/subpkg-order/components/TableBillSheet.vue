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
            <view class="to-head-status">
              <text class="to-badge">{{ tableStatusView.title }}</text>
              <text class="to-desc">{{ tableStatusView.desc }}</text>
              <text v-if="tableStatusView.note" class="to-desc to-desc--sub">{{ tableStatusView.note }}</text>
            </view>
            <view class="to-ident">
              <text class="to-ident-main">店内 {{ tableNo || orderModeText.unknownTable }} 桌</text>
              <text v-if="pickupNoEnabled && tablePickupNo" class="to-ident-line">桌牌 {{ tablePickupNo }} 号</text>
            </view>
          </view>

          <view v-if="tableBillTimeline.length" class="to-track">
            <view class="to-track-bar">
              <text class="to-track-end">{{ tableBillTimeline[0].label }}</text>
              <view class="to-track-rail">
                <view
                  v-for="(step, i) in tableBillTimeline"
                  :key="step.key"
                  class="to-track-step"
                  :class="{ done: step.done, now: step.active }"
                >
                  <view class="to-track-node"></view>
                  <view v-if="i < tableBillTimeline.length - 1" class="to-track-seg"></view>
                </view>
              </view>
              <text class="to-track-end">{{ tableBillTimeline[tableBillTimeline.length - 1].label }}</text>
            </view>
            <text v-if="tableBillWaitText" class="to-track-wait">{{ tableBillWaitText }}</text>
          </view>

          <view class="to-divider"></view>

          <view class="to-list">
            <view v-for="group in tableOrderGroups" :key="group.id" class="to-group">
              <view class="to-round">
                <view class="to-round-left">
                  <view
                    v-if="group.participantNo"
                    class="to-round-badge"
                    :style="{ background: group.participantColor }"
                  >{{ group.participantNo }}</view>
                  <text class="to-round-t">{{ group.title }} · #{{ group.orderNo }}</text>
                  <text v-if="group.discountAmount > 0" class="to-round-discount">优惠 -¥{{ formatPrice(group.discountAmount) }}</text>
                </view>
                <!-- 单批次时顶部胶囊已经说了状态，这里的批次标签就是重复信息，隐掉。 -->
                <text v-if="tableOrderGroups.length > 1" class="to-round-tag" :class="'to-round-tag--' + group.tone">{{ group.statusText }}</text>
              </view>
              <text v-if="group.isStaff" class="to-round-staff">服务员代点{{ group.staffNote ? ' · ' + group.staffNote : '' }}</text>

              <view
                v-for="(item, idx) in group.items"
                :key="item.specKey || item.dish_id || item.id || item.name || idx"
                class="to-drow"
                :class="{ 'to-drow--muted': item.isInvalid }"
              >
                <image
                  v-if="orderItemImage(item) && !orderItemImageFailed[group.id + '_' + idx]"
                  class="to-drow-img"
                  :src="orderItemImage(item)"
                  mode="aspectFill"
                  @error="$emit('mark-image-failed', group.id + '_' + idx)"
                />
                <view v-else class="to-drow-img to-drow-img--ph">
                  <image class="to-drow-img-ph" src="/static/order/dish-placeholder.png" mode="aspectFit" />
                </view>
                <view class="to-drow-main">
                  <text class="to-drow-name">{{ orderItemName(item) }}</text>
                  <text v-if="orderItemSpecText(item)" class="to-drow-spec">{{ orderItemSpecText(item) }}</text>
                  <text v-if="item.isInvalid" class="to-drow-mark">{{ item.invalidText }}</text>
                </view>
                <text class="to-drow-qty">×{{ orderItemQty(item) }}</text>
                <text class="to-drow-amt">¥{{ formatPrice(orderItemAmount(item)) }}</text>
              </view>
            </view>
          </view>

          <view class="to-foot">
            <text class="to-foot-l">共 {{ tableItemCount }} 份 · {{ isTableSettled ? '已结账' : tableBillPayStateText }}</text>
            <text class="to-foot-v"><text class="to-cur">¥</text>{{ formatPrice(tableTotal) }}</text>
          </view>
        </view>

        <view v-else class="to-empty">
          <state-empty
            padded
            icon="🍽️"
            title="本桌还没有已点菜品"
            desc="可以先去点菜，后续加菜会自动合并到本桌账单"
          />
        </view>

        <view v-if="tableOrderGroups.length" class="to-submeta">{{ (tableOrderGroups[0] && tableOrderGroups[0].title ? tableOrderGroups[0].title + ' · ' : '') + sharedBillSubLabel }}</view>

        <!-- 加菜合并提示：只在第一单（还没加过菜）时给；加过一次之后顾客已经知道会合并，
             常驻反而是噪音。 -->
        <view v-if="tableOrderGroups.length === 1 && !isTableSettled" class="to-hint-note">
          <text>同桌后续加菜会自动合并，不需要每次付款。</text>
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
          <text>{{ tableCheckouting ? '呼叫中...' : (checkoutRequested ? '已呼叫服务员，等待确认' : '吃好了，去结账') }}</text>
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
      </template>
  </base-sheet>
</template>

<script>
// 从 menu.vue 拆出来的桌台账单弹层（原来是 showOrders && isSharedBillMode 那一段
// 模板）。纯展示组件，不带任何业务逻辑——所有需要改父组件状态的动作都只 emit 出去。
//
// 方案B（聚合式）改版：状态胶囊 + 身份信息同框，压缩进度条（tableBillTimeline），
// 菜品按下单批次平铺，卡底压合计。跟 OrderHistorySheet 用同一套 `.to-*` 卡片结构，
// 两个「本桌订单类」弹层的顾客端展示自此统一。
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
    // 方案B：餐后付款 / 桌台账单的压缩进度条（4 步）+ 结账状态短语 + 已等待时长。
    tableBillTimeline: { type: Array, default: () => [] },
    tableBillPayStateText: { type: String, default: '' },
    tableBillWaitText: { type: String, default: '' },
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
    formatPrice: { type: Function, required: true },
    orderItemImage: { type: Function, required: true },
    orderItemName: { type: Function, required: true },
    orderItemSpecText: { type: Function, required: true },
    orderItemQty: { type: Function, required: true },
    orderItemAmount: { type: Function, required: true },
  },
  emits: ['close', 'finish', 'retry-load', 'continue-order', 'checkout', 'mark-image-failed'],
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
