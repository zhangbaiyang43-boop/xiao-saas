<template>
  <view class="mask" @click="$emit('cancel')">
    <view class="spec-sheet option-sheet" @click.stop>
      <view class="spec-detail-hero">
        <image
          v-if="dishImage(specDish) && !detailImageFailed"
          class="spec-detail-img"
          :src="dishImage(specDish, 750)"
          mode="aspectFill"
          @error="$emit('image-error')"
        />
        <view v-else class="spec-detail-placeholder">
          <image class="spec-detail-placeholder-img" src="/static/order/dish-placeholder.png" mode="aspectFit" />
        </view>
      </view>
      <view class="spec-sheet-head">
        <text class="spec-sheet-title">{{ specDish.name }}</text>
        <text v-if="specDishDesc" class="spec-sheet-desc">{{ specDishDesc }}</text>
        <view class="spec-sheet-price">
          <price-text size="lg" :amount="formatProductPrice(specBasePrice)" />
        </view>
        <view class="spec-sheet-close" @click="$emit('cancel')"><text class="iconfont icon-close"></text></view>
      </view>
      <scroll-view class="spec-sheet-body" scroll-y>
        <view v-for="group in specRadioGroups" :key="group.name" class="spec-group-block">
          <view class="spec-group-label">
            <text class="spec-group-name">{{ group.name }}</text>
            <text v-if="group.required" class="spec-required">{{ specText.required }}</text>
            <text v-else class="spec-optional">{{ specText.optional }}</text>
          </view>
          <view class="spec-option-list spec-option-list--single">
            <view v-for="opt in group.options" :key="opt.name" class="spec-option" :class="{ 'spec-option--on': isSpecSelected(group, opt) }" @click="$emit('toggle-spec', group, opt)">
              <text>{{ opt.name }}</text>
              <text v-if="opt.price_delta > 0" class="spec-price">+{{ currency }}{{ formatProductPrice(opt.price_delta) }}</text>
            </view>
          </view>
        </view>
        <view v-if="specExtraOptions.length" class="spec-group-block">
          <view class="spec-group-label"><text class="spec-group-name">{{ specText.extras }}</text><text class="spec-optional">{{ specText.multi }}</text></view>
          <view class="spec-option-list">
            <view v-for="extra in specExtraOptions" :key="extra.name" class="spec-option" :class="{ 'spec-option--on': selectedExtras.includes(extra.name) }" @click="$emit('toggle-extra', extra.name)">
              <text>{{ extra.name }}</text>
              <text v-if="extra.price_delta > 0" class="spec-price">+{{ currency }}{{ formatProductPrice(extra.price_delta) }}</text>
            </view>
          </view>
        </view>
        <view class="spec-group-block spec-remark-block">
          <view class="spec-group-label"><view class="spec-group-title-line"><text class="spec-group-icon iconfont icon-form"></text><text class="spec-group-name">{{ specText.itemRemark }}</text></view><text class="spec-optional">{{ specText.optional }}</text></view>
          <view v-if="filteredRemarkChips.length" class="remark-chip-list">
            <view
              v-for="chip in filteredRemarkChips"
              :key="chip"
              class="remark-chip-option"
              :class="{ 'remark-chip-option--on': itemRemark.includes(chip) }"
              @click="$emit('toggle-remark-chip', chip)"
            >{{ chip }}</view>
          </view>
          <text v-if="!showItemRemarkExtra" class="item-remark-extra-toggle" @click="$emit('show-remark-extra')">+ 其他要求</text>
          <template v-else>
            <textarea class="item-remark-input" v-model="itemRemarkModel" maxlength="50" :placeholder="specText.itemRemarkPlaceholder" />
            <text class="item-remark-count">{{ itemRemark.length }}/50</text>
          </template>
        </view>
        <view class="spec-qty-row"><text class="spec-group-name">{{ specText.qty }}</text><view class="spec-counter-row"><view class="counter-btn minus" @click="decreaseQty"><text class="iconfont icon-move"></text></view><text class="counter-num">{{ specQty }}</text><add-btn size="md" @click="$emit('qty-increase')" /></view></view>
      </scroll-view>
      <view class="spec-footer">
        <!-- 顾客选完辣度/做法/附加要求要一路滚回顶部才能确认自己到底选了什么——这里在
        提交前把已选项汇总成一行，不用再往上翻。已选空的时候（还没选完必选项）不
        显示，避免在还没什么可总结的时候占地方、跟上面的必选提示语义重复。 -->
        <text v-if="selectedSpecSummary" class="spec-selected-summary">已选：{{ selectedSpecSummary }}</text>
        <view class="spec-confirm-btn" :class="{ 'spec-confirm-btn--disabled': !canGoNextSpec }" @click="$emit('confirm')"><text>{{ specPrimaryText }}</text></view>
      </view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的规格选择弹层（原来是 showSpecSheet 那一段模板）。
// 纯展示组件，不带任何业务逻辑——所有需要改父组件状态的动作（切换规格/附加项、
// 备注快捷词、展开备注输入框、加减数量、关闭/确认）都只 emit 出去，真正的处理
// 函数还是原来 menu.vue 里那几个（toggleSpec/toggleExtra/toggleItemRemarkChip/
// cancelSpec/handleSpecPrimary），一行都没有改，只是从内联模板换成了从父组件
// 监听事件调用。价格计算、必选校验等逻辑全部留在父组件，这里只读取父组件算好
// 的结果（specBasePrice/canGoNextSpec/specPrimaryText 等）。
import PriceText from './PriceText.vue'
import AddBtn from './AddBtn.vue'

export default {
  name: 'SpecSheet',
  components: { PriceText, AddBtn },
  props: {
    specDish: { type: Object, default: () => ({}) },
    detailImageFailed: { type: Boolean, default: false },
    currency: { type: String, default: '' },
    specDishDesc: { type: String, default: '' },
    specBasePrice: { type: Number, default: 0 },
    specRadioGroups: { type: Array, default: () => [] },
    specExtraOptions: { type: Array, default: () => [] },
    specText: { type: Object, required: true },
    selectedExtras: { type: Array, default: () => [] },
    itemRemark: { type: String, default: '' },
    filteredRemarkChips: { type: Array, default: () => [] },
    showItemRemarkExtra: { type: Boolean, default: false },
    specQty: { type: Number, default: 1 },
    canGoNextSpec: { type: Boolean, default: false },
    specPrimaryText: { type: String, default: '' },
    selectedSpecSummary: { type: String, default: '' },
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑），
    // 保证跟父组件其它地方用到的结果 100% 一致。
    dishImage: { type: Function, required: true },
    formatPrice: { type: Function, required: true },
    // 商品浏览价格用 compact 口径（¥49.8 起，不是 ¥49.80），跟菜单卡片一致。
    formatProductPrice: { type: Function, required: true },
    isSpecSelected: { type: Function, required: true },
  },
  emits: [
    'cancel',
    'confirm',
    'image-error',
    'toggle-spec',
    'toggle-extra',
    'toggle-remark-chip',
    'show-remark-extra',
    'update:item-remark',
    'qty-increase',
    'qty-decrease',
  ],
  computed: {
    itemRemarkModel: {
      get() { return this.itemRemark },
      set(v) { this.$emit('update:item-remark', v) },
    },
  },
  methods: {
    decreaseQty() {
      if (this.specQty > 1) this.$emit('qty-decrease')
    },
  },
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';

.spec-sheet {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100%;
  max-height: 90vh;
  background: var(--bg-card);
  border-radius: 40rpx 40rpx 0 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  animation: slide-up 0.25s ease;
}

.spec-detail-hero {
  width: 100%;
  height: 460rpx;
  min-height: 460rpx;
  max-height: 460rpx;
  background: var(--bg-subtle);
  overflow: hidden;
  flex-shrink: 0;
}



.spec-detail-img {
  width: 100%;
  height: 100%;
  display: block;
}



.spec-detail-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F5F3EE;
}

.spec-detail-placeholder-img {
  width: 40%;
  height: 40%;
}



.spec-sheet-head {
  position: relative;
  padding: 32rpx;
  background: var(--bg-card);
  box-sizing: border-box;
  flex-shrink: 0;
}



.spec-sheet-title {
  display: -webkit-box;
  padding-right: 88rpx;
  color: var(--text-1);
  font-size: 40rpx;
  font-weight: 700;
  line-height: 56rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}



.spec-sheet-close {
  position: absolute;
  right: 16rpx;
  top: 16rpx;
  z-index: 2;
  width: 88rpx;
  height: 88rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
}



.spec-sheet-close text {
  font-size: 38rpx;
  line-height: 44rpx;
}



.spec-sheet-desc {
  display: -webkit-box;
  margin-top: 8rpx;
  color: var(--text-3);
  font-size: 28rpx;
  line-height: 40rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}



.spec-sheet-price {
  margin-top: 16rpx;
}



.spec-sheet-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 32rpx 32rpx;
  box-sizing: border-box;
}



.spec-group-block {
  margin-top: 28rpx;
}



.spec-group-label {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 20rpx;
}



.spec-group-title-line {
  display: flex;
  align-items: center;
  gap: 8rpx;
  min-width: 0;
}



.spec-group-icon {
  flex-shrink: 0;
  color: var(--brand);
  font-size: 28rpx;
  line-height: 32rpx;
}



.spec-group-name {
  color: var(--text-1);
  font-size: 32rpx;
  font-weight: 600;
  line-height: 44rpx;
}



.spec-required {
  color: var(--brand);
  font-size: 22rpx;
  font-weight: 400;
  line-height: 32rpx;
}



.spec-optional {
  color: var(--text-3);
  font-size: 24rpx;
  font-weight: 400;
  line-height: 34rpx;
}



.spec-option-list {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}



.spec-option {
  min-height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  padding: 0 28rpx;
  border: 1rpx solid transparent;
  border-radius: 36rpx;
  background: #f5f6f7;
  color: var(--text-2);
  font-size: 28rpx;
  line-height: 40rpx;
  box-sizing: border-box;
  transition: background 0.15s, color 0.15s, border-color 0.15s;

  &--on {
    border-color: var(--brand);
    background: var(--brand-light);
    color: var(--brand);
    font-weight: 600;
  }
}



.spec-option-list--single .spec-option {
  min-width: 148rpx;
}



.spec-price {
  color: var(--text-3);
  font-size: 24rpx;
  line-height: 34rpx;
  .spec-option--on & { color: var(--brand); }
}



.spec-remark-block {
  margin-top: 32rpx;
}



.remark-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
  margin-top: 20rpx;
}



.remark-chip-option {
  min-height: 64rpx;
  display: flex;
  align-items: center;
  padding: 0 26rpx;
  border: 1rpx solid transparent;
  border-radius: 32rpx;
  background: #f5f6f7;
  color: var(--text-2);
  font-size: 26rpx;
  line-height: 36rpx;
  box-sizing: border-box;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}



.remark-chip-option--on {
  border-color: var(--brand);
  background: var(--brand-light);
  color: var(--brand);
  font-weight: 600;
}



.item-remark-input {
  width: 100%;
  min-height: 152rpx;
  margin-top: 20rpx;
  max-height: 176rpx;
  padding: 24rpx;
  border: 1rpx solid #e5e7ea;
  border-radius: 20rpx;
  background: var(--bg-card);
  box-sizing: border-box;
  color: var(--text-1);
  font-size: 28rpx;
  line-height: 40rpx;
}



.item-remark-count {
  display: block;
  margin-top: 8rpx;
  color: #a8adb4;
  font-size: 22rpx;
  line-height: 32rpx;
  text-align: right;
}



.spec-qty-row {
  min-height: 104rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24rpx;
  margin-top: 32rpx;
}



.spec-counter-row {
  max-width: 216rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  gap: 8rpx;
  flex-shrink: 0;
}

.spec-counter-row .counter-btn.minus {
  width: 64rpx;
  height: 64rpx;
  background: #f5f6f7;
  color: var(--text-2);
}

.spec-counter-row .counter-btn.minus text {
  font-size: 36rpx;
  font-weight: 600;
  line-height: 1;
}

.spec-counter-row .counter-btn.minus .iconfont {
  font-size: 30rpx;
  font-weight: 400;
}

.spec-counter-row .counter-num {
  width: 56rpx;
  color: var(--text-1);
  font-size: 32rpx;
  font-weight: 600;
  line-height: 44rpx;
  text-align: center;
}



.spec-footer {
  flex-shrink: 0;
  padding: 24rpx 32rpx calc(24rpx + env(safe-area-inset-bottom));
  border-top: 1rpx solid #f0f1f2;
  background: var(--bg-card);
  box-sizing: border-box;
}

.spec-selected-summary {
  display: block;
  margin-bottom: 16rpx;
  color: var(--text-2);
  font-size: 24rpx;
  line-height: 34rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.spec-confirm-btn {
  width: 100%;
  height: var(--btn-primary-height);
  border-radius: var(--btn-primary-radius);
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-inverse);

  text {
    color: var(--text-inverse);
    font-size: var(--btn-primary-font-size);
    font-weight: var(--btn-primary-font-weight);
    line-height: 1.2;
  }
}



.spec-confirm-btn--disabled {
  background: #cfd6dc;
  opacity: .95;
}
</style>
