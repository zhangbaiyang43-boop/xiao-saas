<template>
  <view
    class="dish-item"
    :class="{ 'dish-item--featured': model.featured, 'dish-item--soldout': model.soldOut }"
    @click="$emit('open-detail', model.dish)"
  >
    <view class="dish-thumb">
      <image
        v-if="model.imageSrc && !model.imageFailed"
        class="dish-img"
        :src="model.imageSrc"
        mode="aspectFill"
        lazy-load
        @error="$emit('image-error', model.id)"
      />
      <view v-else class="dish-placeholder">
        <image class="dish-placeholder-img" src="/static/order/dish-placeholder.png" mode="aspectFit" />
      </view>
      <view v-if="model.soldOut" class="dish-soldout-mask"><text>已售罄</text></view>
    </view>
    <view class="dish-info">
      <view class="dish-title-row">
        <text class="dish-name">{{ model.name }}</text>
        <view v-if="model.tags.length" class="dish-tags">
          <text
            v-for="tag in model.tags"
            :key="tag.text"
            class="dish-tag"
            :class="tag.emphasis === 'strong' ? 'dish-tag--strong' : 'dish-tag--plain'"
          >{{ tag.text }}</text>
        </view>
      </view>
      <view class="dish-meta">
        <text v-if="model.description" class="dish-desc">{{ model.description }}</text>
        <text v-if="model.salesText" class="dish-sales">{{ model.salesText }}</text>
      </view>
      <view class="dish-bottom-row">
        <price-text
          class="dish-price-wrap"
          size="md"
          block
          :amount="model.priceAmount"
          :suffix="model.priceSuffix"
        />
        <view class="dish-counter" @click.stop>
          <view v-if="model.soldOut" class="soldout-touch" @click.stop>
            <view class="soldout-action"><text>已售罄</text></view>
          </view>
          <template v-else-if="model.hasSpecs">
            <view v-if="model.optionKindCount > 0" class="option-count-touch" @click.stop="$emit('open-cart')">
              <view class="option-count-pill">
                <text>{{ model.optionCountText }}</text>
              </view>
            </view>
            <view class="choose-option-touch" @click.stop="$emit('open-spec', model.dish)">
              <view class="choose-option-btn">
                <text>选规格</text>
              </view>
            </view>
          </template>
          <template v-else>
            <view v-if="model.quantity > 0" class="dish-qty-touch">
              <view class="dish-qty-control">
                <view class="counter-touch counter-touch--minus" @click.stop="$emit('remove', model.dish)"><view class="counter-btn minus"><text class="iconfont icon-move"></text></view></view>
                <text class="counter-num" :class="{ 'counter-num--pulse': model.qtyPulsing }">{{ model.quantity }}</text>
                <view class="counter-touch counter-touch--plus" @click.stop="$emit('add', model.dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': model.addPressing }"><text class="iconfont icon-add"></text></view></view>
              </view>
            </view>
            <view v-else class="counter-touch" @click.stop="$emit('add', model.dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': model.addPressing }"><text class="iconfont icon-add"></text></view></view>
          </template>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import PriceText from './PriceText.vue'

export default {
  name: 'DishCard',
  components: { PriceText },
  props: {
    model: { type: Object, required: true },
  },
  emits: ['open-detail', 'add', 'remove', 'open-spec', 'open-cart', 'image-error'],
}
</script>

<style lang="scss" scoped>
.dish-item {
  display: flex;
  align-items: stretch;
  min-width: 0;
  height: 236rpx;
  min-height: 236rpx;
  max-height: 236rpx;
  margin: 0 20rpx 16rpx;
  padding: 20rpx 20rpx 20rpx 24rpx;
  box-sizing: border-box;
  background: #fff;
  border-radius: var(--radius-card);
  box-shadow: var(--card-shadow);
  position: relative;
  overflow: hidden;
  transition: background 120ms ease, opacity 120ms ease;
}

.dish-item:active { background: #f8faf9; }

.dish-item--featured { border-left-color: transparent; }

.dish-item--soldout { opacity: .76; }

.dish-thumb {
  position: relative;
  width: 192rpx;
  height: 192rpx;
  border-radius: 20rpx;
  overflow: hidden;
  background: #F5F3EE;
  flex-shrink: 0;
  box-sizing: border-box;
  box-shadow: 0 2rpx 8rpx rgba(17,24,39,0.08);
}

.dish-img { width: 100%; height: 100%; display: block; }

.dish-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: #F5F3EE; }

.dish-placeholder-img { width: 60%; height: 60%; }

.dish-soldout-mask { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(31,41,55,.42); }

.dish-soldout-mask text { min-width: 104rpx; height: 48rpx; padding: 0 18rpx; border-radius: 999rpx; display: flex; align-items: center; justify-content: center; background: rgba(17,24,39,.76); color: #fff; font-size: 24rpx; font-weight: 700; }

.dish-info { flex: 1; min-width: 0; display: flex; flex-direction: column; margin-left: 18rpx; box-sizing: border-box; overflow: hidden; }

.dish-title-row { display: flex; align-items: flex-start; gap: 8rpx; min-width: 0; }

.dish-name { flex: 1; min-width: 0; font-size: 32rpx; font-weight: 700; line-height: 44rpx; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.dish-tags { display: flex; flex-shrink: 0; flex-wrap: nowrap; max-width: 88rpx; overflow: hidden; }

.dish-tag { max-width: 88rpx; height: 34rpx; padding: 0 8rpx; border-radius: 8rpx; box-sizing: border-box; font-size: 20rpx; font-weight: 500; line-height: 34rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-tag--strong { color: #078546; background: #e9f9f0; }
.dish-tag--plain { display: none; }

.dish-meta { flex: 1; min-width: 0; min-height: 0; padding-top: 6rpx; }

.dish-desc { display: block; min-width: 0; font-size: 26rpx; color: var(--text-3); line-height: 36rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.dish-sales { display: block; min-width: 0; margin-top: 2rpx; margin-left: 0; font-size: 24rpx; line-height: 34rpx; color: #A8ADB4; font-weight: 400; }

.dish-bottom-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 0; margin-top: auto; min-width: 0; }

.dish-price-wrap { flex: 1; min-width: 104rpx; overflow: hidden; }

.dish-counter { flex: none; display: flex; align-items: center; justify-content: flex-end; flex-shrink: 0; margin-left: 6rpx; min-width: 60rpx; max-width: 176rpx; padding-right: 0; box-sizing: border-box; }

.dish-qty-touch { width: 176rpx; max-width: 176rpx; height: 72rpx; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; }

.dish-qty-control { position: relative; width: 164rpx; max-width: 164rpx; height: 58rpx; padding: 0; display: flex; align-items: center; justify-content: center; gap: 0; overflow: visible; flex-shrink: 0; box-sizing: border-box; border-radius: 29rpx; background: #F3F4F6; }

.counter-touch { width: 72rpx; height: 72rpx; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; }

.dish-qty-control .counter-touch { position: absolute; top: 50%; width: 72rpx; height: 72rpx; transform: translateY(-50%); }

.dish-qty-control .counter-touch--minus { left: -6rpx; }

.dish-qty-control .counter-touch--plus { right: -6rpx; }

.dish-counter > .counter-touch { width: 76rpx; height: 76rpx; }

.dish-qty-control .counter-btn--pressing { animation: none; transform: none; }

.dish-counter .counter-btn { width: 60rpx; height: 60rpx; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-sizing: border-box; flex-shrink: 0; }
.dish-qty-control .counter-btn { width: 50rpx; height: 50rpx; }
.dish-counter .counter-btn text { font-size: 30rpx; font-weight: 800; line-height: 1; }
.dish-counter .counter-btn .iconfont { font-size: 27rpx; font-weight: 400; line-height: 1; }
.dish-counter .counter-btn.plus { background: var(--brand); }
.dish-counter .counter-btn.plus text { color: #fff; }
.dish-counter .counter-btn.minus { border: none; background: #E5E7EB; }
.dish-qty-control .counter-btn.minus { background: #EAEDF1; }
.dish-counter .counter-btn.minus text { color: #4B5563; }
.dish-counter .counter-num { width: 36rpx; min-width: 36rpx; text-align: center; font-size: 30rpx; line-height: 32rpx; font-weight: 600; color: var(--text-1); }
.dish-qty-control .counter-num { width: 32rpx; min-width: 32rpx; font-size: 30rpx; line-height: 32rpx; }

.counter-num--pulse {
  animation: dishCardQtyPulse 150ms ease-out;
}

.soldout-touch,
.choose-option-touch,
.option-count-touch {
  width: 72rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-sizing: border-box;
}

.soldout-touch,
.choose-option-touch {
  width: auto;
  min-width: 104rpx;
}

.soldout-action { height: 60rpx; min-width: 104rpx; padding: 0 20rpx; border-radius: 30rpx; display: flex; align-items: center; justify-content: center; background: #eef1f4; box-sizing: border-box; flex-shrink: 0; }

.soldout-action text { font-size: 24rpx; font-weight: 600; color: #9aa1aa; white-space: nowrap; }

.choose-option-btn { height: 60rpx; padding: 0 20rpx; border-radius: 30rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; transition: transform 180ms var(--bounce-ease); text { color: #fff; font-size: 24rpx; font-weight: 600; white-space: nowrap; } }

.choose-option-touch:active .choose-option-btn { transform: scale(.97); }

.option-count-pill { position: static; min-width: 34rpx; height: 34rpx; padding: 0 10rpx; border-radius: 999rpx; background: #fff; border: 2rpx solid var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; text { color: var(--brand); font-size: 20rpx; font-weight: 800; white-space: nowrap; } }

.counter-btn--pressing {
  animation: addButtonPress 220ms var(--bounce-ease);
}

@keyframes addButtonPress {
  0% { transform: scale(1); }
  40% { transform: scale(.9); }
  75% { transform: scale(1.08); }
  100% { transform: scale(1); }
}

@keyframes dishCardQtyPulse {
  0% { opacity: .75; transform: scale(.9); }
  100% { opacity: 1; transform: scale(1); }
}
</style>
