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
        <view v-else class="spec-detail-placeholder" :style="dishPlaceholderStyle(specDish)">
          <text>{{ specDish.name ? specDish.name[0] : '菜' }}</text>
        </view>
      </view>
      <view class="spec-sheet-head">
        <text class="spec-sheet-title">{{ specDish.name }}</text>
        <text v-if="specDishDesc" class="spec-sheet-desc">{{ specDishDesc }}</text>
        <view class="spec-sheet-price">
          <text class="spec-price-symbol">{{ currency }}</text>
          <text class="spec-price-num">{{ formatPrice(specBasePrice) }}</text>
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
              <text v-if="opt.price_delta > 0" class="spec-price">+{{ currency }}{{ formatPrice(opt.price_delta) }}</text>
            </view>
          </view>
        </view>
        <view v-if="specExtraOptions.length" class="spec-group-block">
          <view class="spec-group-label"><text class="spec-group-name">{{ specText.extras }}</text><text class="spec-optional">{{ specText.multi }}</text></view>
          <view class="spec-option-list">
            <view v-for="extra in specExtraOptions" :key="extra.name" class="spec-option" :class="{ 'spec-option--on': selectedExtras.includes(extra.name) }" @click="$emit('toggle-extra', extra.name)">
              <text>{{ extra.name }}</text>
              <text v-if="extra.price_delta > 0" class="spec-price">+{{ currency }}{{ formatPrice(extra.price_delta) }}</text>
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
        <view class="spec-qty-row"><text class="spec-group-name">{{ specText.qty }}</text><view class="spec-counter-row"><view class="counter-btn minus" @click="decreaseQty"><text class="iconfont icon-move"></text></view><text class="counter-num">{{ specQty }}</text><view class="counter-btn plus" @click="$emit('qty-increase')"><text class="iconfont icon-add"></text></view></view></view>
      </scroll-view>
      <view class="spec-footer">
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
export default {
  name: 'SpecSheet',
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
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑），
    // 保证跟父组件其它地方用到的结果 100% 一致。
    dishImage: { type: Function, required: true },
    dishPlaceholderStyle: { type: Function, required: true },
    formatPrice: { type: Function, required: true },
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
