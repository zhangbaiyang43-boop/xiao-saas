<template>
  <view class="order-page">


    <view class="shop-header">
      <view class="shop-header-row">
        <image v-if="shopLogo" class="shop-logo" :src="shopLogo" mode="aspectFill" />
        <view class="shop-title-main">
          <text class="shop-name">{{ shopName }}</text>
          <view class="shop-meta-row" @click="showTableHint">
            <text class="shop-table-text">{{ tableDisplayText }}</text>
            <text class="shop-meta-dot">·</text>
            <text class="shop-mode-text">{{ orderModeDisplayText }}</text>
            <text class="shop-meta-arrow iconfont icon-roundright"></text>
          </view>
        </view>
      </view>
    </view>


    <view v-if="activeTab === 'order' && couponBarVisible" class="coupon-bar tap-shrink" @click="openCouponPicker">
      <text class="coupon-bar-icon iconfont icon-youhuiquan"></text>
      <text class="coupon-bar-text">{{ couponBarPrefix }}<text class="coupon-bar-amount">{{ couponBarAmount }}</text></text>
      <text class="coupon-bar-arrow iconfont icon-roundright"></text>
    </view>
    <button
      v-else-if="activeTab === 'order' && !isCustomerLoggedIn && newCustomerCouponPreview"
      class="coupon-bar new-customer-bar tap-shrink"
      open-type="getPhoneNumber"
      :disabled="memberAuthorizing"
      @getphonenumber="handleMemberCardAuth"
    >
      <text class="coupon-bar-icon iconfont icon-youhuiquan"></text>
      <text class="coupon-bar-text">{{ newCustomerHookText }}</text>
      <text class="coupon-bar-arrow iconfont icon-roundright"></text>
    </button>

    <view class="menu-body" v-show="activeTab === 'order'">


      <scroll-view class="category-nav" scroll-y scroll-with-animation :scroll-top="categoryScrollTop">
        <view
          v-for="(cat, catIdx) in categories"
          :key="cat"
          :id="`cat-nav-${catIdx}`"
          class="cat-item"
          :class="{ active: activeCategory === cat }"
          @click="switchCategory(cat)"
        >
          <view class="cat-icon-wrap"><text :class="['cat-icon', 'iconfont', categoryIconClass(cat)]"></text></view>
          <text class="cat-name">{{ categoryDisplayName(cat) }}</text>
        </view>
      </scroll-view>


      <scroll-view
        class="dish-scroll"
        scroll-y
        :scroll-into-view="scrollTarget"
        scroll-with-animation
        @scroll="onDishScroll"
      >

        <view v-if="lastOrderItems.length" class="reorder-bar">
          <text class="reorder-label">再来一单</text>
          <scroll-view scroll-x class="reorder-scroll">
            <view class="reorder-chips">
              <view
                v-for="item in lastOrderItems"
                :key="item.name"
                class="reorder-chip"
                @click="reorderItem(item)"
              >
                <text class="reorder-chip-name">{{ item.name }}</text>
                <text class="reorder-chip-add">+</text>
              </view>
            </view>
          </scroll-view>
          <view class="reorder-all-btn" @click="reorderAll">
            <text class="reorder-all-text">全部再来一份</text>
          </view>
        </view>

        <view v-if="!loading && !loadError && !allDishes.length" class="empty-menu">
          <image class="empty-menu-img" src="/static/order/empty-menu.png" mode="aspectFit" />
          <text class="empty-title">暂无菜品</text>
          <text class="empty-desc">菜单加载失败</text>
          <view class="empty-retry" @click="loadMenu"><text>重新加载</text></view>
        </view>
        <view v-for="(cat, catIdx) in categories" :key="cat" :id="`cat-sec-${catIdx}`">
          <view class="cat-divider"><view class="cat-divider-line"></view><view class="cat-divider-main"><text :class="['cat-divider-icon', 'iconfont', categoryIconClass(cat)]"></text><text class="cat-divider-text">{{ categoryDisplayName(cat) }}</text></view><view class="cat-divider-line"></view></view>
          <view
            v-for="(dish, dishIdx) in dishesByCategory(cat)"
            :key="dish.id"
            class="dish-item"
            :class="{ 'dish-item--featured': isFeatured(dish), 'dish-item--soldout': isSoldOut(dish) }"
            @click="openProductDetail(dish)"
          >
            <view class="dish-thumb">
              <image
                v-if="dishImage(dish) && !imageLoadFailed[dish.id]"
                class="dish-img"
                :src="dishImage(dish)"
                mode="aspectFill"
                lazy-load
                @error="markDishImageFailed(dish.id)"
              />
              <view v-else class="dish-placeholder">
                <image class="dish-placeholder-img" src="/static/order/dish-placeholder.png" mode="aspectFit" />
              </view>
              <view v-if="isSoldOut(dish)" class="dish-soldout-mask"><text>已售罄</text></view>
            </view>
            <view class="dish-info">
              <view class="dish-title-row">
                <text class="dish-name">{{ dish.name }}</text>
                <view v-if="dishCardTags(dish).length" class="dish-tags">
                  <text
                    v-for="tag in dishCardTags(dish)"
                    :key="tag"
                    class="dish-tag"
                    :class="isStrongDishTag(tag) ? 'dish-tag--strong' : 'dish-tag--plain'"
                  >{{ tag }}</text>
                </view>
              </view>
              <view class="dish-meta">
                <text v-if="dishCardDesc(dish)" class="dish-desc">{{ dishCardDesc(dish) }}</text>
                <text v-if="showDishSales(dish)" class="dish-sales">月售{{ dish.sales_count }}</text>
              </view>
              <view class="dish-bottom-row">
                <view class="dish-price-wrap">
                  <text class="dish-price-currency">¥</text>
                  <text class="dish-price-amount">{{ dishPriceText(dish) }}</text>
                  <text v-if="dishPriceSuffix(dish)" class="dish-price-suffix">{{ dishPriceSuffix(dish) }}</text>
                </view>
                <view class="dish-counter" @click.stop>
                  <view v-if="isSoldOut(dish)" class="soldout-action" @click.stop><text>已售罄</text></view>
                  <template v-else-if="hasSpecs(dish)">
                    <view v-if="dishOptionKindCount(dish.id) > 0" class="option-count-pill" @click.stop="openCart">
                      <text>{{ optionCountText(dish.id) }}</text>
                    </view>
                    <view class="choose-option-btn" @click.stop="openSpecSheet(dish)">
                      <text>选规格</text>
                    </view>
                  </template>
                  <template v-else>
                    <view v-if="cartCount(dish.id) > 0" class="dish-qty-control">
                      <view class="counter-touch" @click.stop="removeFromCart(dish)"><view class="counter-btn minus"><text class="iconfont icon-move"></text></view></view>
                      <text class="counter-num" :class="{ 'counter-num--pulse': qtyPulseKey === dish.id }">{{ cartCount(dish.id) }}</text>
                      <view class="counter-touch" @click.stop="addToCart(dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': addPressKey === dish.id }"><text class="iconfont icon-add"></text></view></view>
                    </view>
                    <view v-else class="counter-touch" @click.stop="addToCart(dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': addPressKey === dish.id }"><text class="iconfont icon-add"></text></view></view>
                  </template>
                </view>
              </view>
            </view>
          </view>
        </view>
        <view class="list-pad" />
      </scroll-view>

    </view>


    <scroll-view v-show="activeTab === 'home'" class="tab-scroll" scroll-y>
      <view class="home-tab">
        <view class="ht-status-card">
          <view class="ht-status-main">
            <text class="ht-store-name">{{ shopName }}</text>
            <text class="ht-status-desc">{{ homeStatusDesc }}</text>
          </view>
          <view :class="['ht-status-badge', storeClosed ? 'ht-status-badge--closed' : 'ht-status-badge--open']">
            <text>{{ storeClosed ? '\u4f11\u606f\u4e2d' : '\u8425\u4e1a\u4e2d' }}</text>
          </view>
        </view>

        <view class="ht-order-card" :class="{ 'ht-order-card--disabled': !canStartOrdering }" @click="handleHomeStartOrder">
          <text class="ht-order-kicker">今日推荐</text>
          <text class="ht-order-title">立即点餐</text>
          <text class="ht-order-desc">{{ homeStatusDesc }}</text>
          <text v-if="homeCouponHint" class="ht-order-coupon">{{ homeCouponHint }}</text>
          <view class="ht-order-btn" :class="{ 'ht-order-btn--disabled': !canStartOrdering }" @click.stop="handleHomeStartOrder">
            <text>{{ homeOrderButtonText }}</text>
          </view>
        </view>

        <view v-if="featuredDish" class="ht-section">
          <view class="ht-section-head">
            <text class="ht-section-title">店长推荐</text>
            <text class="ht-section-sub">精选招牌菜品</text>
          </view>
          <view class="ht-feature-card" @click="openProductDetail(featuredDish)">
            <view class="ht-feature-img-wrap">
              <image
                v-if="dishImage(featuredDish) && !imageLoadFailed[featuredDish.id]"
                class="ht-feature-img"
                :src="dishImage(featuredDish)"
                mode="aspectFill"
                @error="markDishImageFailed(featuredDish.id)"
              />
              <view v-else class="ht-feature-placeholder">
                <image class="ht-feature-placeholder-img" src="/static/order/dish-placeholder.png" mode="aspectFit" />
              </view>
            </view>
            <view class="ht-feature-info">
              <view class="ht-feature-title-row">
                <text class="ht-feature-name">{{ featuredDish.name }}</text>
                <text v-if="featuredDishTag" class="ht-feature-tag">{{ featuredDishTag }}</text>
              </view>
              <text v-if="dishCardDesc(featuredDish)" class="ht-feature-desc">{{ dishCardDesc(featuredDish) }}</text>
              <view class="ht-feature-bottom">
                <view class="ht-feature-price">
                  <text class="ht-feature-yen">¥</text>
                  <text class="ht-feature-amount">{{ dishPriceText(featuredDish) }}</text>
                  <text v-if="dishPriceSuffix(featuredDish)" class="ht-feature-suffix">{{ dishPriceSuffix(featuredDish) }}</text>
                </view>
                <view
                  class="ht-feature-add"
                  :class="{ 'ht-feature-add--disabled': !canHomeAdd }"
                  @click.stop="handleFeaturedAdd"
                >
                  <text>{{ hasSpecs(featuredDish) ? '\u9009\u89c4\u683c' : '\u76f4\u63a5\u52a0\u5165' }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <view v-if="homeLastOrderItems.length" class="ht-section">
          <view class="ht-section-head ht-section-head--row">
            <text class="ht-section-title">再来一单</text>
            <text class="ht-section-action" @click="handleHomeReorderAll">全部再来一份</text>
          </view>
          <view class="ht-last-list">
            <view
              v-for="item in homeLastOrderItems"
              :key="item.key"
              class="ht-last-chip"
              :class="{ 'ht-last-chip--disabled': storeClosed }"
              @click="handleHomeReorderItem(item)"
            >
              <text class="ht-last-name">{{ item.name }}</text>
              <text class="ht-last-add">+</text>
            </view>
          </view>
        </view>

      </view>
    </scroll-view>


    <scroll-view v-show="activeTab === 'card'" class="tab-scroll" scroll-y>
      <view v-if="bannerInfo" class="card-tab member-center">
        <view class="member-identity-card tap-shrink" @click="uni.navigateTo({ url: '/subpkg-member/pages/growth' })">
          <view class="mic-glow"></view>
          <view class="mic-issuer"><text>{{ shopName }} · 甄选会员</text></view>
          <view class="mic-body">
            <view class="member-avatar">
              <image v-if="bannerInfo.avatar" class="member-avatar-img" :src="bannerInfo.avatar" mode="aspectFill" />
              <image v-else class="member-avatar-badge" :src="memberLevelBadgeSrc" mode="aspectFit" />
            </view>
            <view class="member-identity-main">
              <view class="mic-crest-row">
                <text class="member-level">{{ memberLevelLabel }}</text>
              </view>
              <text class="mic-sub">MEMBER</text>
            </view>
            <text class="mic-chevron iconfont icon-roundright"></text>
          </view>
          <view v-if="memberUpgradeText" class="member-progress-wrap">
            <view class="member-progress-track"><view class="member-progress-fill" :style="{ width: memberProgressPercent + '%' }"></view></view>
            <text class="member-upgrade-text">{{ memberUpgradeText }}</text>
          </view>
          <view v-if="bannerInfo.memberNo || memberSinceText" class="mic-footer">
            <text v-if="bannerInfo.memberNo" class="mic-number">{{ 'NO. ' + bannerInfo.memberNo }}</text>
            <text v-if="memberSinceText" class="mic-since">{{ memberSinceText }}</text>
          </view>
        </view>

        <view class="member-assets-card">
          <view class="member-asset-item" @click="uni.navigateTo({ url: '/subpkg-member/pages/points' })">
            <text class="member-asset-value">{{ bannerInfo.points || 0 }}</text>
            <text class="member-asset-label">积分</text>
          </view>
          <view class="member-asset-divider"></view>
          <view class="member-asset-item" @click="uni.navigateTo({ url: '/subpkg-coupon/pages/list' })">
            <text class="member-asset-value">{{ bannerInfo.couponCount }}</text>
            <text class="member-asset-label">优惠券</text>
          </view>
        </view>

        <view class="member-main-action-card">
          <text class="member-action-title">您有{{ bannerInfo.couponCount }}张优惠券可用</text>
          <view class="member-action-btn" @click="goOrderFromMember"><text>去点餐</text></view>
        </view>

        <view v-if="usableMemberCoupons.length" class="member-section">
          <text class="member-section-title">可用优惠券</text>
          <view class="member-coupon-list">
            <view v-for="coupon in usableMemberCoupons" :key="coupon.id || coupon.coupon_id || coupon.name" class="member-coupon-card" @click="useMemberCoupon(coupon)">
              <view class="member-coupon-value">
                <text class="member-coupon-yen">¥</text>
                <text class="member-coupon-amount">{{ couponAmountText(coupon) }}</text>
              </view>
              <view class="member-coupon-info">
                <text class="member-coupon-condition">{{ couponConditionText(coupon) }}</text>
                <text class="member-coupon-time">{{ couponValidityText(coupon) }}</text>
              </view>
              <view class="member-coupon-use"><text>立即使用</text></view>
            </view>
          </view>
        </view>

        <view class="member-service-card">
          <view class="member-service-row" @click="uni.navigateTo({ url: '/subpkg-member/pages/points' })">
            <view class="member-service-icon"><text class="iconfont icon-timefill"></text></view>
            <text class="member-service-label">积分明细</text>
            <text class="member-service-arrow iconfont icon-roundright"></text>
          </view>
          <view class="member-service-row" @click="uni.navigateTo({ url: '/subpkg-coupon/pages/list' })">
            <view class="member-service-icon"><text class="iconfont icon-youhuiquan"></text></view>
            <text class="member-service-label">优惠券</text>
            <text class="member-service-arrow iconfont icon-roundright"></text>
          </view>
        </view>
      </view>
      <view v-else-if="hasCustomerIdentity" class="card-tab-empty">
        <text class="cte-title">会员中心</text>
        <text class="cte-desc">普通会员</text>
        <view class="cte-btn cte-btn-plain" @click="loadMemberStatus">
          <text>{{ memberLoading ? '\u52a0\u8f7d\u4e2d...' : '\u91cd\u65b0\u52a0\u8f7d' }}</text>
        </view>
        <text class="cte-secondary" @click="goOrderFromMember">去点餐</text>
      </view>
      <view v-else class="card-tab-empty">
        <text class="cte-title">会员中心</text>
        <text class="cte-desc">{{ newCustomerHookText }}</text>
        <button
          class="cte-btn"
          open-type="getPhoneNumber"
          :disabled="memberAuthorizing"
          @getphonenumber="handleMemberCardAuth"
        >
          <text>{{ memberAuthorizing ? '\u6388\u6743\u4e2d...' : '\u67e5\u770b\u4f1a\u5458\u6743\u76ca' }}</text>
        </button>
        <text class="cte-secondary" @click="goOrderFromMember">去点餐</text>
      </view>
    </scroll-view>

    <view v-show="activeTab === 'mine'" class="tab-scroll tab-mine-redirect">
    </view>

    <!-- 悬浮气泡，参考美团/饿了么外卖的订单进度气泡：贴边可拖动，图标+文字传达状态，
    点开看详情。只在订单还没到 settled/cancelled/rejected 终态时出现（复用
    pendingOrderCount，跟结账后自动收起是同一个判断）。拖动/贴边/首次提示/状态变化的
    震动和提示条都封装在 order-bubble 组件里，这个页面只负责给数据。 -->
    <order-bubble
      :visible="activeTab === 'order' && pendingOrderCount > 0"
      :tone="tableOrderStatusTone"
      :icon="tableOrderStatusIcon"
      :badge="tableOrderStatusBadge"
      :action-text="tableOrderNextAction"
      :count="pendingOrderCount"
      :top-rpx="320"
      :bottom-clear-rpx="268"
      @click="viewOrderDetail"
    />


    <view
      v-if="activeTab === 'order' && couponNudgeState.visible"
      class="coupon-nudge-bar"
      :class="{ 'coupon-nudge-bar--done': couponNudgeState.satisfied }"
    >
      <view class="coupon-nudge-main" @click="couponNudgeState.satisfied ? openCouponPicker() : goCouponAddOn()">
        <text class="coupon-nudge-icon iconfont icon-youhuiquan"></text>
        <view class="coupon-nudge-copy">
          <template v-if="couponNudgeState.satisfied">
            <text class="coupon-nudge-title">已享满{{ couponNudgeState.thresholdText }}减{{ couponNudgeState.discountText }}优惠</text>
          </template>
          <template v-else>
            <text class="coupon-nudge-title">再加 <text class="coupon-nudge-strong">¥{{ couponNudgeState.diffText }}</text>，立享满{{ couponNudgeState.thresholdText }}减{{ couponNudgeState.discountText }}</text>
          </template>
          <text class="coupon-nudge-sub">当前 ¥{{ formatPrice(totalPrice) }} / 门槛 ¥{{ couponNudgeState.thresholdText }}</text>
        </view>
      </view>
      <view v-if="!couponNudgeState.satisfied" class="coupon-nudge-action" @click="goCouponAddOn">
        <text>去凑单</text>
      </view>
      <view v-else class="coupon-nudge-action coupon-nudge-action--plain" @click="openCouponPicker">
        <text>换券</text>
      </view>
    </view>

    <view v-show="activeTab === 'order'" class="cart-bar" :class="{ 'has-items': totalCount > 0 }">
      <view class="cart-main" @click="totalCount > 0 ? openCart() : null">

        <view class="cart-icon-wrap" :class="{ 'cart-icon-wrap--pulse': cartIconPulse }">
          <text :class="['cart-iconfont', 'iconfont', totalCount > 0 ? 'icon-cartfill' : 'icon-cart']"></text>
          <view v-if="totalCount > 0" class="cart-badge" :class="{ 'cart-badge--pulse': cartBadgePulse }">
            <text>{{ cartBadgeText }}</text>
          </view>
        </view>


        <view class="cart-info">
          <template v-if="totalCount > 0">
            <text class="cart-price" :class="{ 'cart-price--highlight': amountPulse }">¥{{ formatPrice(totalPrice) }}</text>
            <text class="cart-tip">共{{ totalCount }}份</text>
          </template>
          <template v-else>
            <text class="cart-empty">未选择商品</text>
          </template>
        </view>
      </view>


      <view class="cart-right">
        <view
          class="checkout-btn"
          :class="{ disabled: totalCount === 0 }"
          @click.stop="totalCount > 0 && openCart()"
        >
          <text>去结算</text>
        </view>
      </view>
    </view>


    <view class="bottom-nav">
      <view :class="['bn-item', { active: activeTab === 'home' }]" @click="activeTab = 'home'">
        <text :class="['bn-icon', 'iconfont', activeTab === 'home' ? 'icon-homefill' : 'icon-home']"></text>
      </view>
      <view :class="['bn-item', { active: activeTab === 'order' }]" @click="activeTab = 'order'">
        <text :class="['bn-icon', 'iconfont', activeTab === 'order' ? 'icon-shopfill' : 'icon-shop']"></text>
        <view v-if="totalCount > 0 && activeTab !== 'order'" class="bn-dot"></view>
      </view>
      <view :class="['bn-item', { active: activeTab === 'card' }]" @click="switchToCard">
        <text :class="['bn-icon', 'iconfont', activeTab === 'card' ? 'icon-likefill' : 'icon-like']"></text>
        <view v-if="bannerInfo && bannerInfo.couponCount > 0 && activeTab !== 'card'" class="bn-dot"></view>
      </view>
      <view :class="['bn-item', { active: activeTab === 'mine' }]" @click="goMine">
        <text :class="['bn-icon', 'iconfont', activeTab === 'mine' ? 'icon-myfill' : 'icon-my']"></text>
      </view>
    </view>


    <!-- Order confirmation sheet -->
    <view v-if="showCart" class="mask" @click="closeOrderConfirm">
      <view class="cart-sheet order-confirm-sheet" @click.stop>
        <view class="order-confirm-head">
          <text class="order-confirm-title">{{ confirmationText.title }}</text>
          <text class="order-confirm-close iconfont icon-close" @click="closeOrderConfirm"></text>
        </view>

        <scroll-view class="order-confirm-content" scroll-y>
          <view class="order-summary-card" :class="{ 'order-summary-card--missing': !tableNo }" @click="showTableHint">
            <view class="summary-mode-pill"><text>{{ orderModeText.dineIn }}</text></view>
            <text class="summary-table-no">{{ (tableNo || orderModeText.unknownTable) + '桌' }}</text>
            <text v-if="!tableNo" class="summary-table-tip">{{ confirmationText.tableMissing }}</text>
          </view>

          <view class="confirm-card selected-items-section">
            <view class="selected-items-summary" @click="toggleItemsExpanded">
              <view class="selected-items-title-wrap">
                <view class="confirm-title-line"><text class="confirm-title-icon iconfont icon-list"></text><text class="selected-items-title">{{ confirmationText.selectedItems }}({{ totalCount }})</text></view>
              </view>
              <view class="selected-items-action">
                <text class="selected-items-amount">{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text>
                <text :class="['selected-items-toggle-icon', 'iconfont', itemsExpanded ? 'icon-pullup' : 'icon-unfold']"></text>
              </view>
            </view>
            <view v-if="itemsExpanded" class="cart-items-panel">
              <scroll-view class="cart-items" scroll-y>
                <view v-for="item in cartItems" :key="item.specKey || item.id" class="cart-row">
                  <view class="cart-row-main">
                    <text class="cart-row-name">{{ item.name }}</text>
                    <text v-if="item.specLabel" class="cart-row-spec">{{ item.specLabel }}</text>
                  </view>
                  <view class="cart-row-right">
                    <view class="counter-btn minus sm" @click="removeFromCart(item)"><text class="iconfont icon-move"></text></view>
                    <text class="counter-num" :class="{ 'counter-num--pulse': qtyPulseKey === (item.specKey || item.id) }">{{ item.qty }}</text>
                    <view class="counter-btn plus sm" @click="increaseCartItem(item)"><text class="iconfont icon-add"></text></view>
                    <text class="cart-row-price">{{ confirmationText.currency }}{{ formatPrice(item.price * item.qty) }}</text>
                  </view>
                </view>
              </scroll-view>
              <view class="cart-clear-line" @click="clearCart"><text class="iconfont icon-delete"></text><text>{{ confirmationText.clear }}</text></view>
            </view>
          </view>

          <view class="confirm-card order-preference-section">
            <view class="remark-label-wrap"><text class="remark-label-icon iconfont icon-edit"></text><text class="remark-label">{{ confirmationText.orderRemark }}</text></view>
            <view v-if="orderRemarkChips.length" class="remark-chips">
              <view
                v-for="chip in orderRemarkChips"
                :key="chip"
                class="remark-chip"
                :class="{ 'remark-chip--on': remark.includes(chip) }"
                @click="toggleRemarkChip(chip)"
              ><text>{{ chip }}</text></view>
            </view>
            <view class="remark-row order-remark-row">
              <text v-if="!showOrderRemarkExtra" class="item-remark-extra-toggle" @click="showOrderRemarkExtra = true">+ 其他要求</text>
              <input v-else class="remark-input" v-model="remark" :placeholder="confirmationText.orderRemarkPlaceholder" placeholder-class="remark-placeholder" maxlength="60" />
            </view>
          </view>

          <view class="confirm-card price-summary-card">
            <view class="price-row"><view class="price-label-wrap"><text class="price-label-icon iconfont icon-list"></text><text>{{ confirmationText.goodsAmount }}</text></view><text>{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text></view>
            <view class="price-row price-row--clickable" @click="openCouponPicker">
              <view class="price-label-wrap"><text class="price-label-icon iconfont icon-ticket"></text><text>{{ confirmationText.coupon }}</text></view>
              <text v-if="discountAmount > 0" class="price-discount">-{{ confirmationText.currency }}{{ discountAmount.toFixed(2) }} {{ confirmationText.arrow }}</text>
              <text v-else-if="availableCoupons.length > 0" class="price-muted">{{ availableCoupons.length }}{{ confirmationText.couponAvailable }} {{ confirmationText.arrow }}</text>
              <text v-else class="price-muted">{{ confirmationText.couponNone }} {{ confirmationText.arrow }}</text>
            </view>
            <view class="price-row price-row--payable">
              <view class="price-label-wrap"><text class="price-label-icon iconfont icon-pay"></text><text>{{ confirmPaymentLabel }}</text></view>
              <text>{{ confirmationText.currency }}{{ wechatPayAmount.toFixed(2) }}</text>
            </view>
          </view>
        </scroll-view>

        <view class="order-confirm-bottom">
          <view class="checkout-btn-full" :class="{ 'checkout-btn-full--disabled': !canSubmitOrder || ordering || paying }" @click="goCheckout">
            <text class="checkout-btn-icon iconfont icon-pay"></text><text>{{ payButtonText }}</text>
          </view>
        </view>
      </view>
    </view>

    <view v-if="showCouponPicker" class="mask" @click="closeCouponPicker">
      <view class="coupon-picker-sheet" @click.stop>
        <view class="cp-head">
          <text class="cp-title">选择优惠券</text>
          <text class="cp-close iconfont icon-close" @click="closeCouponPicker"></text>
        </view>
        <scroll-view class="cp-list" scroll-y>
          <view class="cp-option" :class="{ 'cp-option--on': !selectedCouponId }" @click="pickCoupon(null)">
            <view class="cp-option-main">
              <text class="cp-option-name">不使用优惠券</text>
            </view>
            <text :class="['cp-radio-icon', 'iconfont', !selectedCouponId ? 'icon-roundcheckfill' : 'icon-roundcheck']"></text>
          </view>
          <view
            v-for="c in couponPickerList"
            :key="c.id"
            class="cp-option"
            :class="{ 'cp-option--on': selectedCouponId === c.id, 'cp-option--disabled': !c.eligible }"
            @click="pickCoupon(c)"
          >
            <view class="cp-option-amount"><text>¥{{ couponPickerAmount(c) }}</text></view>
            <view class="cp-option-main">
              <text class="cp-option-name">{{ c.name || '\u4f18\u60e0\u5238' }}</text>
              <text class="cp-option-cond">{{ c.eligible ? couponPickerCondText(c) : '\u8fd8\u5dee' + formatPrice(Math.max(0, Number(c.min_amount || c.threshold_amount || 0) - totalPrice)) + '\u5143\u53ef\u7528' }}</text>
            </view>
            <text :class="['cp-radio-icon', 'iconfont', selectedCouponId === c.id ? 'icon-roundcheckfill' : 'icon-roundcheck']"></text>
          </view>
          <view v-if="!couponPickerList.length" class="cp-empty"><text>暂无可用优惠券</text></view>
        </scroll-view>
      </view>
    </view>

    <view v-if="showCheckoutAuth" class="mask checkout-auth-mask" @click="cancelCheckoutAuth">
      <view class="checkout-auth-sheet" @click.stop>
        <view class="checkout-auth-handle"></view>
        <text class="checkout-auth-title">{{ authSheetText.title }}</text>
        <text class="checkout-auth-desc">{{ authSheetText.desc }}</text>
        <view class="checkout-auth-order">
          <view class="checkout-auth-row"><text>{{ authSheetText.store }}</text><text>{{ shopName }}</text></view>
          <view class="checkout-auth-row"><text>{{ authSheetText.table }}</text><text>{{ tableNo || authSheetText.unknownTable }}</text></view>
          <view class="checkout-auth-row checkout-auth-row--amount"><text>{{ authAmountLabel }}</text><text>{{ confirmationText.currency }}{{ wechatPayAmount.toFixed(2) }}</text></view>
        </view>
        <view class="checkout-auth-auto">
          <text>{{ authSheetText.auto }}</text>
        </view>
        <button
          class="checkout-auth-primary"
          open-type="getPhoneNumber"
          :disabled="authorizing || ordering || paying"
          @getphonenumber="handleCheckoutAuth"
        >{{ authPrimaryText }}</button>
        <view class="checkout-auth-cancel" @click="cancelCheckoutAuth">
          <text>{{ authSheetText.cancel }}</text>
        </view>
        <text class="checkout-auth-member">{{ authSheetText.member }}</text>
        <text class="checkout-auth-privacy">{{ authSheetText.privacy }}</text>
      </view>
    </view>

    <view v-if="showSuccess" class="mask success-mask">
      <view class="success-sheet" @click.stop>
        <view class="success-handle"></view>
        <view class="success-card">
          <view class="success-check">
            <view class="success-check-inner"></view>
          </view>
          <text class="success-title">{{ successText.title }}</text>
          <view class="success-paid-amount-row">
            <text class="success-paid-currency">{{ confirmationText.currency }}</text>
            <text class="success-paid-amount">{{ successTotal.toFixed(2) }}</text>
          </view>
          <text class="success-paid-label">{{ successText.paidLabel }}</text>

          <view class="order-status-bar" :class="successStatusTone">
            <text class="order-status-text">{{ successStatusText }}</text>
          </view>

          <view v-if="earnedCoupon" class="earned-coupon-card">
            <text class="ec-ribbon">{{ earnedCoupon.isSecondOrder ? '欢迎回来 · 专属奖励' : '支付成功 · 专属奖励' }}</text>
            <view class="ec-amount-row">
              <text class="ec-currency">¥</text>
              <text class="ec-amount">{{ formatPrice(earnedCoupon.amount) }}</text>
            </view>
            <text class="ec-cond">{{ earnedCoupon.threshold > 0 ? '满' + formatPrice(earnedCoupon.threshold) + '元可用' : '无门槛立减' }}</text>
            <view class="ec-divider"></view>
            <text class="ec-title">{{ (earnedCoupon.isSecondOrder ? '欢迎回来，这是你的第二次光临！再送你一张券：' : '又送你一张券：') + (earnedCoupon.name || '') }}</text>
            <text v-if="earnedCoupon.expire_time" class="ec-deadline">{{ couponValidityText(earnedCoupon) }}</text>
            <text
              v-if="couponReminderTemplateId && earnedCoupon.couponId"
              class="ec-remind-btn"
              :class="{ 'ec-remind-btn--done': reminderRequested }"
              @click="requestCouponReminder"
            >{{ reminderRequested ? '已设置提醒 ✓' : (requestingReminder ? '设置中...' : '提醒我别忘了用') }}</text>
          </view>

          <view class="success-summary">
            <view class="success-summary-row">
              <text class="success-summary-label">{{ successText.table }}</text>
              <text class="success-summary-value">{{ tableNo || orderModeText.unknownTable }}</text>
            </view>
            <view class="success-summary-row">
              <text class="success-summary-label">{{ successText.orderNo }}</text>
              <text class="success-summary-value">#{{ successOrderNo }}</text>
            </view>
            <view class="success-summary-row">
              <text class="success-summary-label">{{ successText.items }}</text>
              <text class="success-summary-value">{{ successOrderItemCount }}{{ successText.itemUnit }}</text>
            </view>
          </view>

          <view class="success-actions">
            <view class="success-btn-primary" @click="closeSuccessAndWait">
              <text>{{ successText.closeAndWait }}</text>
            </view>
            <view class="success-btn-secondary" @click="continueOrdering">
              <text>{{ successText.continueOrdering }}</text>
            </view>
            <view class="success-btn-ghost" @click="viewOrderDetail">
              <text>{{ successText.viewDetail }}</text>
            </view>
          </view>

          <text class="success-safe-tip">{{ successText.safeTip }}</text>
        </view>
      </view>
    </view>

    <view v-if="showWelcomeCoupon" class="mask welcome-mask" @click="closeWelcomeCoupon">
      <view class="welcome-coupon-sheet" @click.stop>
        <text class="wc-ribbon">送你一张新人券</text>
        <view class="wc-amount-row">
          <text class="wc-currency">¥</text>
          <text class="wc-amount">{{ formatPrice(welcomeCouponData?.amount ?? welcomeCouponData?.value ?? 0) }}</text>
        </view>
        <text class="wc-cond">{{ welcomeCouponCondText }}</text>
        <view class="wc-divider"></view>
        <text class="wc-name">{{ welcomeCouponData?.name || '优惠券' }}</text>
        <view class="wc-btn" @click="goOrderFromWelcomeCoupon"><text>去点餐使用</text></view>
        <text class="wc-skip" @click="closeWelcomeCoupon">稍后再说</text>
      </view>
    </view>

    <view v-if="showOrders" class="mask" @click="showOrders = false">
      <view v-if="isSharedBillMode" class="orders-sheet table-account-sheet" @click.stop>
        <view class="orders-sheet-head table-account-head">
          <view class="table-account-back" @click="showOrders = false">
            <text class="iconfont icon-back"></text>
          </view>
          <text class="orders-sheet-title">已点菜品</text>
          <text class="orders-sheet-close iconfont icon-close" @click="showOrders = false"></text>
        </view>

        <scroll-view v-if="!loadError" class="table-account-list" scroll-y :scroll-into-view="tableAccountScrollInto" scroll-with-animation>
          <view id="table-account-status-anchor" class="table-account-status">
            <view class="table-account-status-icon" :class="'table-account-status-icon--' + tableStatusView.tone">
              <text class="iconfont" :class="tableStatusView.icon"></text>
            </view>
            <text class="table-account-status-title">{{ tableStatusView.title }}</text>
            <text class="table-account-status-desc">{{ tableStatusView.desc }}</text>
            <text v-if="tableStatusView.note" class="table-account-status-note">{{ tableStatusView.note }}</text>
          </view>

          <view class="table-account-summary">
            <view class="table-account-summary-left">
              <text class="table-account-table">{{ tableNo || orderModeText.unknownTable }}桌</text>
              <text class="table-account-sub">{{ sharedBillSubLabel }}</text>
            </view>
            <view class="table-account-summary-right">
              <text class="table-account-total">¥{{ formatPrice(tableTotal) }}</text>
              <text class="table-account-count">共 {{ tableItemCount }} 份</text>
            </view>
          </view>

          <view class="table-account-section">
            <view class="table-account-section-head">
              <text class="table-account-section-title">本桌已点菜品</text>
            </view>

            <view v-if="tableOrderGroups.length" class="table-account-groups">
              <view v-for="group in tableOrderGroups" :key="group.id" class="table-account-group">
                <view class="table-account-group-head">
                  <view class="table-account-group-left">
                    <view v-if="group.participantNo" class="participant-badge" :style="{ background: group.participantColor }">{{ group.participantNo }}</view>
                    <text v-if="group.isStaff" class="table-account-staff-badge">服务员代点{{ group.staffNote ? ' · ' + group.staffNote : '' }}</text>
                    <text class="table-account-group-time">{{ group.title }}</text>
                    <text v-if="group.discountAmount > 0" class="table-account-group-discount">优惠 -¥{{ formatPrice(group.discountAmount) }}</text>
                  </view>
                  <text class="table-account-group-status" :class="'table-account-group-status--' + group.tone">{{ group.statusText }}</text>
                </view>
                <view v-for="(item, idx) in group.items" :key="item.specKey || item.dish_id || item.id || item.name || idx" class="table-account-item" :class="{ 'table-account-item--muted': item.isInvalid }">
                  <view class="table-account-item-img-wrap">
                    <image
                      v-if="orderItemImage(item) && !orderItemImageFailed[group.id + '_' + idx]"
                      class="table-account-item-img"
                      :src="orderItemImage(item)"
                      mode="aspectFill"
                      @error="markOrderItemImageFailed(group.id + '_' + idx)"
                    />
                    <view v-else class="table-account-item-placeholder">
                      <text>{{ orderItemName(item).slice(0, 1) }}</text>
                    </view>
                  </view>
                  <view class="table-account-item-main">
                    <text class="table-account-item-name">{{ orderItemName(item) }}</text>
                    <text v-if="orderItemSpecText(item)" class="table-account-item-spec">{{ orderItemSpecText(item) }}</text>
                    <text v-if="item.isInvalid" class="table-account-item-mark">{{ item.invalidText }}</text>
                  </view>
                  <text class="table-account-item-qty">×{{ orderItemQty(item) }}</text>
                  <text class="table-account-item-amount">¥{{ formatPrice(orderItemAmount(item)) }}</text>
                </view>
              </view>
            </view>

            <view v-else class="table-account-empty">
              <text class="table-account-empty-title">本桌还没有已点菜品</text>
              <text class="table-account-empty-desc">可以先去点菜，后续加菜会自动合并到本桌账单</text>
            </view>
          </view>

          <view class="table-account-tip">
            <text>同桌后续加菜会自动合并，不需要每次付款。</text>
          </view>
        </scroll-view>

        <view v-else class="table-status-empty">
          <text class="table-status-empty-icon iconfont icon-warnfill"></text>
          <text class="table-status-empty-title">本桌订单加载失败</text>
          <text class="table-status-empty-desc">请重新加载后再查看本桌账单</text>
          <view class="table-account-retry" @click="loadMenu"><text>重新加载</text></view>
        </view>

        <view class="table-account-actions">
          <view
            class="table-account-action table-account-action--secondary"
            :class="{ 'table-account-action--disabled': !canContinueOrder }"
            @click="handleTableContinueOrder"
          >
            <text>{{ tableOrderGroups.length ? '继续加菜' : '去点菜' }}</text>
          </view>
          <view
            v-if="canCheckout"
            class="table-account-action table-account-action--primary"
            :class="{ 'table-account-action--disabled': tableCheckouting || checkoutRequested }"
            @click="handleTableCheckout"
          >
            <text>{{ tableCheckouting ? '呼叫中...' : (checkoutRequested ? '已呼叫服务员，等待确认' : '吃好了，去结账') }}</text>
          </view>
          <view
            v-else-if="isTableSettled"
            class="table-account-action table-account-action--primary table-account-action--ghost"
            @click="scrollTableAccountToTop"
          >
            <text>查看结账详情</text>
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
      </view>

      <view v-else class="orders-sheet" @click.stop>
        <view class="orders-sheet-head">
          <text class="orders-sheet-title">本桌订单</text>
          <text class="orders-sheet-close iconfont icon-close" @click="showOrders = false"></text>
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
              <text class="order-core-value order-core-value--amount">{{ '\u00a5' + formatPrice(currentTableOrder.total || 0) }}</text>
            </view>
            <view class="order-core-item">
              <text class="order-core-icon iconfont icon-timefill"></text>
              <text class="order-core-value">{{ currentTableOrder.createdAt || '-' }}</text>
            </view>
            <view class="order-core-item">
              <text class="order-core-icon iconfont icon-form"></text>
              <text class="order-core-value">{{ currentOrderItemCount + '\u4efd' }}</text>
            </view>
          </view>

          <view class="order-progress-card">
            <view class="order-progress-head">
              <text class="order-progress-card-title">{{ '\u8ba2\u5355\u8fdb\u5ea6' }}</text>
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
                  <text class="current-order-title">{{ '\u83dc\u54c1\u660e\u7ec6' }}</text>
                </view>
                <text class="current-order-no">#{{ currentTableOrder.orderNo }}</text>
              </view>
              <text class="current-order-total">{{ '\u00a5' + formatPrice(currentTableOrder.total || 0) }}</text>
            </view>
            <view class="current-order-summary">
              <text>{{ '\u4e0b\u5355\u65f6\u95f4 ' + (currentTableOrder.createdAt || '-') }}</text>
              <text>{{ '\u5171' + currentOrderItemCount + '\u4efd' }}</text>
            </view>
            <view v-if="currentTableOrder.items && currentTableOrder.items.length" class="current-order-items current-order-items--visible">
              <view v-for="(item, idx) in currentTableOrder.items" :key="item.specKey || item.id || item.name || idx" class="order-detail-row">
                <view class="order-detail-main">
                  <text class="order-detail-name">{{ orderItemName(item) }}</text>
                  <text v-if="orderItemSpecText(item)" class="order-detail-spec">{{ orderItemSpecText(item) }}</text>
                </view>
                <text class="order-detail-qty">{{ '\u00d7' + orderItemQty(item) }}</text>
                <text class="order-detail-amount">{{ '\u00a5' + formatPrice(orderItemAmount(item)) }}</text>
              </view>
            </view>
            <view v-else class="current-order-empty-detail">
              <text>{{ currentOrderMainItemText }}</text>
            </view>
          </view>

          <view v-if="historyTableOrders.length" class="history-orders-card">
            <view class="history-orders-head" @click="showAllOrders = !showAllOrders">
              <text>历史订单</text>
              <text>{{ showAllOrders ? '\u6536\u8d77' : '\u67e5\u770b\u5168\u90e8 ' + historyTableOrders.length }}</text>
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
          <view class="orders-secondary-btn" :class="'orders-secondary-btn--' + tableOrderStatusTone" @click="showOrders = false">
            <text>{{ tableOrderPrimaryButtonText }}</text>
          </view>
        </view>
      </view>
    </view>

    <view v-if="showSpecSheet" class="mask" @click="cancelSpec">
      <view class="spec-sheet option-sheet" @click.stop>
        <view class="spec-detail-hero">
          <image
            v-if="dishImage(specDish) && !detailImageFailed"
            class="spec-detail-img"
            :src="dishImage(specDish, 750)"
            mode="aspectFill"
            @error="detailImageFailed = true"
          />
          <view v-else class="spec-detail-placeholder" :style="dishPlaceholderStyle(specDish)">
            <text>{{ specDish.name ? specDish.name[0] : '\u83dc' }}</text>
          </view>
        </view>
        <view class="spec-sheet-head">
          <text class="spec-sheet-title">{{ specDish.name }}</text>
          <text v-if="specDishDesc" class="spec-sheet-desc">{{ specDishDesc }}</text>
          <view class="spec-sheet-price">
            <text class="spec-price-symbol">{{ confirmationText.currency }}</text>
            <text class="spec-price-num">{{ formatPrice(specBasePrice) }}</text>
          </view>
          <view class="spec-sheet-close" @click="cancelSpec"><text class="iconfont icon-close"></text></view>
        </view>
        <scroll-view class="spec-sheet-body" scroll-y>
          <view v-for="group in specRadioGroups" :key="group.name" class="spec-group-block">
            <view class="spec-group-label">
              <text class="spec-group-name">{{ group.name }}</text>
              <text v-if="group.required" class="spec-required">{{ specText.required }}</text>
              <text v-else class="spec-optional">{{ specText.optional }}</text>
            </view>
            <view class="spec-option-list spec-option-list--single">
              <view v-for="opt in group.options" :key="opt.name" class="spec-option" :class="{ 'spec-option--on': isSpecSelected(group, opt) }" @click="toggleSpec(group, opt)">
                <text>{{ opt.name }}</text>
                <text v-if="opt.price_delta > 0" class="spec-price">+{{ confirmationText.currency }}{{ formatPrice(opt.price_delta) }}</text>
              </view>
            </view>
          </view>
          <view v-if="specExtraOptions.length" class="spec-group-block">
            <view class="spec-group-label"><text class="spec-group-name">{{ specText.extras }}</text><text class="spec-optional">{{ specText.multi }}</text></view>
            <view class="spec-option-list">
              <view v-for="extra in specExtraOptions" :key="extra.name" class="spec-option" :class="{ 'spec-option--on': selectedExtras.includes(extra.name) }" @click="toggleExtra(extra.name)">
                <text>{{ extra.name }}</text>
                <text v-if="extra.price_delta > 0" class="spec-price">+{{ confirmationText.currency }}{{ formatPrice(extra.price_delta) }}</text>
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
                @click="toggleItemRemarkChip(chip)"
              >{{ chip }}</view>
            </view>
            <text v-if="!showItemRemarkExtra" class="item-remark-extra-toggle" @click="showItemRemarkExtra = true">+ 其他要求</text>
            <template v-else>
              <textarea class="item-remark-input" v-model="itemRemark" maxlength="50" :placeholder="specText.itemRemarkPlaceholder" />
              <text class="item-remark-count">{{ itemRemark.length }}/50</text>
            </template>
          </view>
          <view class="spec-qty-row"><text class="spec-group-name">{{ specText.qty }}</text><view class="spec-counter-row"><view class="counter-btn minus" @click="specQty > 1 && specQty--"><text class="iconfont icon-move"></text></view><text class="counter-num">{{ specQty }}</text><view class="counter-btn plus" @click="specQty++"><text class="iconfont icon-add"></text></view></view></view>
        </scroll-view>
        <view class="spec-footer">
          <view class="spec-confirm-btn" :class="{ 'spec-confirm-btn--disabled': !canGoNextSpec }" @click="handleSpecPrimary"><text>{{ specPrimaryText }}</text></view>
        </view>
      </view>
    </view>

    <view v-if="storeClosed || tableSessionClosed" class="closed-mask">
      <view class="closed-card">
        <view class="closed-icon-wrap"><text class="closed-icon iconfont" :class="tableSessionClosed ? 'icon-roundcheckfill' : 'icon-shopfill'"></text></view>
        <text class="closed-title">{{ tableSessionClosed ? '\u672c\u684c\u7528\u9910\u5df2\u7ed3\u675f' : shopName + ' \u5f53\u524d\u4f11\u606f\u4e2d' }}</text>
        <text class="closed-desc">{{ tableSessionClosed ? tableSessionClosedNotice : (closedNotice || '\u8425\u4e1a\u65f6\u95f4\u8bf7\u53c2\u8003\u95e8\u5e97\u516c\u544a') }}</text>
        <view v-if="tableSessionClosed" class="closed-btn" @click="goMine"><text>{{ '\u597d\u7684\uff0c\u6211\u77e5\u9053\u4e86' }}</text></view>
        <view v-else class="closed-btn" @click="storeClosed = false"><text>{{ '\u4ecd\u8981\u6d4f\u89c8\u83dc\u5355' }}</text></view>
      </view>
    </view>


    <view v-if="loadError && !loading" class="loading-mask">
      <text class="loading-text">菜单加载中...</text>
      <view class="retry-btn" @click="loadMenu"><text>重新加载</text></view>
    </view>


    <view v-if="loading" class="loading-mask skeleton-mask">
      <view class="skeleton-nav">
        <view v-for="n in 6" :key="n" class="skeleton-nav-item"></view>
      </view>
      <view class="skeleton-list">
        <view v-for="n in 4" :key="n" class="skeleton-dish">
          <view class="skeleton-thumb"></view>
          <view class="skeleton-lines">
            <view class="skeleton-line skeleton-line--title"></view>
            <view class="skeleton-line skeleton-line--desc"></view>
            <view class="skeleton-line skeleton-line--price"></view>
          </view>
        </view>
      </view>
    </view>


  </view>
</template>

<script>
import { ref, computed, watch, nextTick } from 'vue'
import { getMenuItems, getShopInfo, createOrder, cancelOrder, createWxPayOrder, getCurrentDiningOrders, getOrderStatus, requestTableCheckout } from '@/api/order'
import { getCustomerCoupons, remindMeForCoupon } from '@/api/coupon'
import { buildCouponNudgeState } from '../utils/couponNudge.mjs'
import { getMemberProfile, getMembershipGrowth, joinByEntranceCode, bindDiningParticipant } from '@/api/auth'
import { saveCustomerSession, clearCustomerSession } from '@/utils/auth'
import { resolveDiningIdentity, persistDiningContext as persistDiningStorage, isDiningIdentityError } from '@/utils/dining'
import OrderBubble from '@/components/order-bubble/order-bubble.vue'
const wxLogin = () => new Promise((resolve, reject) => {
  uni.login({
    provider: 'weixin',
    success: (res) => res.code ? resolve(res.code) : reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5')),
    fail: () => reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u5c0f\u7a0b\u5e8f\u73af\u5883'))
  })
})

export default {
  components: { OrderBubble },
  setup() {
    const tableNo = ref('')
    const shopId = ref('')
    const shopName = ref(uni.getStorageSync('tenant_name') || '\u672a\u6765\u9910\u5385')
    const shopLogo = ref('')
    const shopCreatedAt = ref('')
    const memberSinceText = computed(() => {
      const year = new Date(shopCreatedAt.value).getFullYear()
      return Number.isNaN(year) ? '' : '\u4f1a\u5458\u81ea ' + year + ' \u5e74'
    })
    const diningSessionId = ref(uni.getStorageSync('dining_session_id') || '')
    const diningParticipantToken = ref(uni.getStorageSync('dining_participant_token') || '')
    const diningClientId = ref(uni.getStorageSync('dining_client_id') || '')
    const paymentMode = ref('prepay')
    const normalizePaymentMode = (mode) => {
      const value = String(mode || 'prepay').trim()
      return ['prepay', 'postpay', 'table_account'].includes(value) ? value : 'prepay'
    }
    const orderModeText = {
      dineIn: '\u5802\u98df',
      delivery: '\u5916\u5356',
      tableLabel: '\u684c\u53f7',
      unknownTable: '\u672a\u8bc6\u522b'
    }
    // 只更新本组件的响应式状态；实际的"怎么建立/校验本桌身份、往 storage 写哪些字段"
    // 全部收敛到 utils/dining.js 的 resolveDiningIdentity/persistDiningContext，跟扫码
    // 入口页（entry/index.vue）共用同一份实现，不再各自维护一份。
    const persistDiningContext = (data = {}) => {
      diningSessionId.value = data.dining_session_id || diningSessionId.value || ''
      diningParticipantToken.value = data.participant_token || diningParticipantToken.value || ''
      diningClientId.value = data.client_id || diningClientId.value || ''
      persistDiningStorage(data)
    }

    const ensureDiningSession = async (force = false) => {
      const tenantId = shopId.value || uni.getStorageSync('tenant_id') || ''
      const table = tableNo.value || uni.getStorageSync('table_no') || ''
      if (tableSessionClosed.value && !force) return false
      const identity = await resolveDiningIdentity({ tenantId, table, force })
      if (!identity.ok) return false
      persistDiningContext(identity.data)
      tableSessionClosed.value = false
      return true
    }

    const bindCurrentDiningParticipant = async () => {
      if (!diningParticipantToken.value) return
      const tenantId = shopId.value || uni.getStorageSync('tenant_id') || ''
      if (!tenantId) return
      try {
        await bindDiningParticipant({ tenant_id: tenantId, participant_token: diningParticipantToken.value }, { authRedirect: false })
      } catch (e) {}
    }

    const diningOrderQuery = () => ({
      tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
      dining_session_id: diningSessionId.value || uni.getStorageSync('dining_session_id') || '',
      participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') || '',
    })

    const mapServerOrder = (order) => {
      const created = order.created_at ? new Date(order.created_at) : new Date()
      const timeStr = Number.isNaN(created.getTime()) ? '' : created.getHours().toString().padStart(2,'0') + ':' + created.getMinutes().toString().padStart(2,'0')
      return {
        id: String(order.id || ''),
        orderNo: String(order.order_no || order.id || '').slice(-4),
        status: order.status || 'pending',
        paymentStatus: order.payment_status || '',
        paymentMode: normalizePaymentMode(order.payment_mode),
        diningSessionId: order.dining_session_id ? String(order.dining_session_id) : '',
        tableSessionId: order.dining_session_id ? String(order.dining_session_id) : '',
        items: Array.isArray(order.items) ? order.items.map(i => ({ ...i, qty: Number(i.qty || 0), price: Number(i.price || 0) })) : [],
        total: Number(order.total || 0),
        discountAmount: Number(order.discount_amount || 0),
        tableTotal: Number(order.table_total || order.session_total || 0),
        participantNo: order.participant_no ?? null,
        isStaff: order.source === 'staff',
        staffNote: order.staff_note || '',
        createdAt: timeStr,
        createdTs: Number.isNaN(created.getTime()) ? Date.now() : created.getTime(),
        table: order.table_no || tableNo.value,
      }
    }

    // \u672c\u684c\u4eba\u6570\u53d8\u5316\u63d0\u793a\uff08\u53c2\u7167\u5ba2\u5982\u4e91\u540c\u6b3e\u4f53\u9a8c\uff09\uff1a\u53ea\u5728\u4eba\u6570\u6bd4\u4e0a\u4e00\u6b21\u540c\u6b65"\u53d8\u591a"\u65f6\u63d0\u9192\u4e00\u6b21\uff0c
    // \u7b2c\u4e00\u6b21\u540c\u6b65\u4e0d\u63d0\u9192\uff08\u4e0d\u7136\u521a\u8fdb\u684c\u5c31\u5f39\u4e00\u4e2a"\u6709\u4eba\u52a0\u5165"\u5f88\u5947\u602a\uff0c\u90a3\u662f\u81ea\u5df1\uff09\u3002\u4eba\u6570\u4e0d\u843d\u5230
    // \u5177\u4f53\u662f\u8c01\uff0c\u8ddf"\u53c2\u4e0e\u8005\u7f16\u53f7"\u6807\u7b7e\u662f\u540c\u4e00\u4e2a"\u4e0d\u66b4\u9732\u771f\u5b9e\u8eab\u4efd"\u7684\u539f\u5219\u3002
    const knownParticipantCount = ref(0)
    const hasSyncedParticipantCount = ref(false)

    // 身份没就绪（守卫拦下）或后端明确回了 identity_mismatch，都不能悄悄返回"查不到订单"了
    // 事——那跟"这一桌真的还没人点单"在界面上长得一模一样，顾客不会知道是身份出了问题。
    // 这两种情况都先强制重建一次身份再重试，isRetry 保证最多重试一次，不会死循环。
    const syncDiningOrders = async (isRetry = false) => {
      const query = diningOrderQuery()
      if (!query.tenant_id || !query.dining_session_id || !query.participant_token) {
        if (isRetry) return false
        return (await ensureDiningSession(true)) ? syncDiningOrders(true) : false
      }
      try {
        const res = await getCurrentDiningOrders(query)
        if (res?.code !== 200) return false
        if (res.data?.identity_mismatch) {
          if (isRetry) return false
          return (await ensureDiningSession(true)) ? syncDiningOrders(true) : false
        }
        const sessionStatus = String(res.data?.session_status || '').toUpperCase()
        tableSessionStatus.value = sessionStatus
        tableSessionTotal.value = Number(res.data?.table_total || res.data?.session_total || 0)
        tableSessionClosed.value = res.data?.closed === true || ['CLOSED', 'EXPIRED'].includes(sessionStatus)
        if (tableSessionClosed.value) {
          tableSessionClosedNotice.value = '\u672c\u684c\u7528\u9910\u5df2\u7ed3\u675f\uff0c\u5982\u9700\u7ee7\u7eed\u70b9\u9910\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u8fdb\u5165\u65b0\u4e00\u684c'
          // Session closed: clear the local "which table" markers so the
          // mine page won't keep showing this settled table as still dining.
          uni.removeStorageSync('table_no')
          uni.removeStorageSync('table_no_at')
          uni.removeStorageSync('dining_session_id')
          uni.removeStorageSync('dining_participant_id')
          uni.removeStorageSync('dining_participant_token')
          uni.removeStorageSync('dining_table_no')
        }
        checkoutRequestedAt.value = res.data?.checkout_requested_at || ''
        tableSessionClosedAt.value = res.data?.closed_at || ''
        myOrders.value = (res.data?.orders || []).map(mapServerOrder)
        saveMyOrders()

        const newParticipantCount = Number(res.data?.participant_count || 0)
        if (newParticipantCount > 0) {
          if (hasSyncedParticipantCount.value && newParticipantCount > knownParticipantCount.value) {
            uni.showToast({ title: '\u6709\u65b0\u4f19\u4f34\u626b\u7801\u52a0\u5165\u4e86\u672c\u684c', icon: 'none', duration: 2500 })
          }
          knownParticipantCount.value = newParticipantCount
          hasSyncedParticipantCount.value = true
        }
        return true
      } catch (e) {
        if (!isRetry && isDiningIdentityError(e)) {
          return (await ensureDiningSession(true)) ? syncDiningOrders(true) : false
        }
        return false
      }
    }
    const showTableHint = () => {
      uni.showModal({
        title: '\u684c\u53f7\u63d0\u793a',
        content: '\u5f53\u524d\u684c\u53f7\uff1a' + (tableNo.value || orderModeText.unknownTable) + '\\n\u8bf7\u786e\u8ba4\u684c\u53f7\u540e\u7ee7\u7eed\u70b9\u9910',
        showCancel: false,
        confirmText: '\u77e5\u9053\u4e86'
      })
    }
    const confirmationText = {
      title: '\u786e\u8ba4\u8ba2\u5355', tableMissing: '\u672a\u8bc6\u522b\u684c\u53f7\uff0c\u8bf7\u91cd\u65b0\u626b\u7801',
      selectedItems: '\u5df2\u9009\u5546\u54c1', clear: '\u6e05\u7a7a\u5df2\u9009\u5546\u54c1',
      remark: '\u5907\u6ce8', remarkPlaceholder: '\u5176\u4ed6\u8981\u6c42\u2026', goodsAmount: '\u5546\u54c1\u91d1\u989d', coupon: '\u4f18\u60e0\u5238', couponAvailable: '\u5f20\u53ef\u7528', couponNone: '\u6682\u65e0\u53ef\u7528', noThreshold: '\u65e0\u95e8\u69db', thresholdPrefix: '\u6ee1',
      payable: '\u5e94\u4ed8\u91d1\u989d', wechatPay: '\u5fae\u4fe1\u652f\u4ed8', tableAccount: '\u684c\u53f0\u8d26\u5355', postpay: '\u9910\u540e\u4ed8\u6b3e', payNow: '\u7acb\u5373\u652f\u4ed8', submitTableAccount: '\u63d0\u4ea4\u5230\u684c\u53f0\u8d26\u5355', submitOrder: '\u63d0\u4ea4\u8ba2\u5355',
      orderRemark: '\u6574\u5355\u5907\u6ce8', orderRemarkPlaceholder: '\u4f8b\u5982\uff1a\u4e00\u8d77\u4e0a\u83dc\u3001\u5168\u90e8\u6253\u5305\u3001\u9700\u8981\u513f\u7ae5\u9910\u5177', unavailable: '\u5f53\u524d\u4e0d\u53ef\u4e0b\u5355', confirming: '\u6b63\u5728\u786e\u8ba4\u8ba2\u5355\u2026', paying: '\u6b63\u5728\u53d1\u8d77\u652f\u4ed8\u2026', currency: '\u00a5', close: 'x', arrow: '>'
    }
    const successText = {
      title: '\u4e0b\u5355\u6210\u529f',
      paidLabel: '\u5b9e\u4ed8\u91d1\u989d',
      table: '\u684c\u53f7',
      orderNo: '\u8ba2\u5355\u53f7',
      items: '\u5546\u54c1',
      itemUnit: '\u4ef6',
      closeAndWait: '\u5173\u95ed\u5e76\u7b49\u5f85',
      continueOrdering: '\u7ee7\u7eed\u52a0\u83dc',
      viewDetail: '\u67e5\u770b\u8ba2\u5355\u8be6\u60c5',
      safeTip: '\u8ba2\u5355\u72b6\u6001\u4f1a\u81ea\u52a8\u66f4\u65b0\uff0c\u65e0\u9700\u91cd\u590d\u63d0\u4ea4\u6216\u518d\u6b21\u652f\u4ed8\u3002',
      statusPending: '\u5546\u5bb6\u5df2\u6536\u5230\u8ba2\u5355\uff0c\u6b63\u5728\u7b49\u5f85\u63a5\u5355',
      statusPreparing: '\u5546\u5bb6\u5df2\u63a5\u5355\uff0c\u6b63\u5728\u5236\u4f5c',
      statusDone: '\u9910\u54c1\u5df2\u5b8c\u6210\uff0c\u8bf7\u7559\u610f\u53d6\u9910\u6216\u670d\u52a1\u5458\u901a\u77e5',
      statusRejected: '\u8ba2\u5355\u72b6\u6001\u5f02\u5e38\uff0c\u8bf7\u8054\u7cfb\u5546\u5bb6\u5904\u7406',
      statusFallback: '\u8ba2\u5355\u5df2\u63d0\u4ea4\uff0c\u53ef\u5728\u8ba2\u5355\u8be6\u60c5\u4e2d\u67e5\u770b\u72b6\u6001',
      detailOpened: '\u5df2\u6253\u5f00\u8ba2\u5355\u8be6\u60c5',
      closed: '\u5df2\u5173\u95ed\uff0c\u8bf7\u5b89\u5fc3\u7b49\u5f85',
      backToMenu: '\u5df2\u8fd4\u56de\u70b9\u9910\u9875',
    }
    const specText = {
      defaultDesc: '\u9009\u597d\u53e3\u5473\u540e\u52a0\u5165\u8d2d\u7269\u8f66', required: '\u5fc5\u9009', optional: '\u53ef\u9009', multi: '\u53ef\u591a\u9009', extras: '\u9644\u52a0\u8981\u6c42', itemRemark: '\u5355\u54c1\u5907\u6ce8', itemRemarkPlaceholder: '\u4f8b\u5982\uff1a\u5c11\u76d0\u3001\u4e0d\u8981\u9999\u83dc\u3001\u5bf9\u82b1\u751f\u8fc7\u654f',
      dish: '\u83dc\u54c1', spec: '\u89c4\u683c', qty: '\u6570\u91cf', none: '\u65e0', prev: '\u8fd4\u56de\u4e0a\u4e00\u6b65', next: '\u4e0b\u4e00\u6b65', add: '\u52a0\u5165\u8d2d\u7269\u8f66', chooseTaste: '\u9009\u53e3\u5473', chooseSpec: '\u9009\u89c4\u683c', selectedKinds: '\u5df2\u9009', kindUnit: '\u79cd', separator: '\u3001', dotSeparator: '\u00b7'
    }
    const todayActivity = ref('')
    const loading = ref(false)
    const loadError = ref(false)
    const ordering = ref(false)
    // 提交订单的幂等键：开开购物车时生成一次，
    // 同一次结算内的重试（弱网超时后重新提交）都带同一个值，
    // 后端用它返回同一张订单而不是建出第二张。
    const pendingSubmitRequestId = ref('')
    const ensureSubmitRequestId = () => {
      if (!pendingSubmitRequestId.value) {
        pendingSubmitRequestId.value = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      }
      return pendingSubmitRequestId.value
    }
    const showCart = ref(false)
    const itemsExpanded = ref(false)
    const showSuccess = ref(false)
    const earnedCoupon = ref(null)
    const reminderRequested = ref(false)
    const requestingReminder = ref(false)
    const requestCouponReminder = async () => {
      if (requestingReminder.value || reminderRequested.value) return
      if (!earnedCoupon.value?.couponId || !couponReminderTemplateId.value) return
      requestingReminder.value = true
      try {
        // 微信这个订阅额度是一次性的，用户点了"允许"才算真正拿到推送权限；
        // 不管用户在弹窗里选了允许还是拒绝，我们都记一次"顾客想要提醒"——
        // 真发不发得出去，交给后台按有没有拿到授权去处理，这里不做二次拦截。
        await new Promise((resolve) => {
          uni.requestSubscribeMessage({
            tmplIds: [couponReminderTemplateId.value],
            complete: resolve,
          })
        })
        const res = await remindMeForCoupon(earnedCoupon.value.couponId)
        if (res?.code === 200) {
          reminderRequested.value = true
          uni.showToast({ title: '好的，到期前会提醒你', icon: 'none' })
        } else {
          uni.showToast({ title: res?.msg || '设置失败，请重试', icon: 'none' })
        }
      } catch (e) {
        uni.showToast({ title: '设置失败，请重试', icon: 'none' })
      } finally {
        requestingReminder.value = false
      }
    }
    const showWelcomeCoupon = ref(false)
    const welcomeCouponData = ref(null)
    const welcomeCouponCondText = computed(() => {
      const min = Number(welcomeCouponData.value?.min_amount || 0)
      return min > 0 ? '\u6ee1' + min.toFixed(0) + '\u5143\u53ef\u7528' : '\u65e0\u95e8\u69db\u53ef\u7528'
    })
    const consumeWelcomeCoupon = () => {
      if (uni.getStorageSync('coupon_modal_shown') !== 'false') return null
      uni.setStorageSync('coupon_modal_shown', 'true')
      const raw = uni.getStorageSync('welcome_coupon')
      if (!raw) return null
      try { return JSON.parse(raw) } catch { return null }
    }
    const checkWelcomeCoupon = () => {
      const data = consumeWelcomeCoupon()
      if (!data) return
      welcomeCouponData.value = data
      showWelcomeCoupon.value = true
    }
    const closeWelcomeCoupon = () => {
      showWelcomeCoupon.value = false
    }
    const goOrderFromWelcomeCoupon = () => {
      showWelcomeCoupon.value = false
      activeTab.value = 'order'
    }
    const orderNo = ref('')
    const orderId = ref('')
    const orderStatus = ref('pending') // pending | preparing | done
    const successItems = ref([])
    const successTotal = ref(0)
    const successDiscount = ref(0)
    const showCheckoutAuth = ref(false)
    const authorizing = ref(false)
    const authSheetText = {
      title: '\u7ee7\u7eed\u652f\u4ed8',
      desc: '\u5fae\u4fe1\u6388\u6743\u540e\uff0c\u5c06\u81ea\u52a8\u7ee7\u7eed\u63d0\u4ea4\u672c\u6b21\u8ba2\u5355\uff0c\u65e0\u9700\u91cd\u590d\u64cd\u4f5c\u3002',
      auto: '\u6388\u6743\u6210\u529f\u540e\uff0c\u7cfb\u7edf\u5c06\u81ea\u52a8\u521b\u5efa\u8ba2\u5355\u5e76\u62c9\u8d77\u5fae\u4fe1\u652f\u4ed8\u3002',
      store: '\u95e8\u5e97',
      table: '\u684c\u53f7',
      amount: '\u5e94\u4ed8\u91d1\u989d',
      unknownTable: '\u672a\u8bc6\u522b',
      confirm: '\u6388\u6743\u5e76\u652f\u4ed8',
      confirmSubmit: '\u6388\u6743\u5e76\u63d0\u4ea4\u8ba2\u5355',
      confirmFree: '\u6388\u6743\u5e76\u5b8c\u6210\u8ba2\u5355',
      authorizing: '\u6b63\u5728\u6388\u6743\u2026',
      submitting: '\u6b63\u5728\u63d0\u4ea4\u8ba2\u5355\u2026',
      paying: '\u6b63\u5728\u53d1\u8d77\u652f\u4ed8\u2026',
      cancel: '\u6682\u4e0d\u652f\u4ed8',
      member: '\u652f\u4ed8\u6210\u529f\u540e\u81ea\u52a8\u6210\u4e3a\u672c\u5e97\u4f1a\u5458\uff0c\u53ef\u5728\u201c\u6211\u7684\u201d\u4e2d\u67e5\u770b\u8ba2\u5355\u4e0e\u6743\u76ca\u3002',
      privacy: '\u6388\u6743\u4ec5\u7528\u4e8e\u8bc6\u522b\u672c\u6b21\u8ba2\u5355\u4e0e\u4f1a\u5458\u8eab\u4efd\uff0c\u4e0d\u4f1a\u53d1\u5e03\u5185\u5bb9\u3002',
    }
    const authActionStatus = ref('idle')
    const pendingPaymentIntent = ref(null)
    const paying = ref(false)
    const paymentFailed = ref(false)  // 上一次点"去支付"真的失败了（不是用户取消）——按钮要明确提示这是在重试，不能让用户猜要不要再点一次
    const payAmount = ref(0)
    const pendingOrderId = ref('')
    let statusPollTimer = null
    let tablePresencePollTimer = null

    const myOrders = ref([])
    const showOrders = ref(false)
    const showAllOrders = ref(false)
    const tableSessionStatus = ref('')
    const tableSessionTotal = ref(0)
    const tableCheckouting = ref(false)
    const checkoutRequestedAt = ref('')
    const tableSessionClosedAt = ref('')   // 真正的结账时间（区别于下单时间），给"查看结账详情"用
    const tableAccountScrollInto = ref('')
    const orderItemImageFailed = ref({})
    const storeClosed = ref(false)
    const tableSessionClosed = ref(false)
    const tableSessionClosedNotice = ref('\u672c\u684c\u7528\u9910\u5df2\u7ed3\u675f\uff0c\u5982\u9700\u7ee7\u7eed\u70b9\u9910\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u8fdb\u5165\u65b0\u4e00\u684c')
    const isMember = ref(false)
    const bannerInfo = ref(null)
    const memberAuthorizing = ref(false)
    const memberLoading = ref(false)
    const isCustomerLoggedIn = ref(Boolean(uni.getStorageSync('customer_token')))
    const authStateVersion = ref(0)
    const activeTab = ref('order')
    const shopDistance = ref('')

    const refreshCustomerAuthState = () => {
      authStateVersion.value += 1
      isCustomerLoggedIn.value = Boolean(uni.getStorageSync('customer_token') || uni.getStorageSync('customer_phone'))
      checkWelcomeCoupon()
    }
    const hasCustomerIdentity = computed(() => {
      authStateVersion.value
      return Boolean(uni.getStorageSync('customer_token') || uni.getStorageSync('customer_phone'))
    })

    const isCheckoutAuthError = (err) => {
      const code = String(err?.code || '')
      const statusCode = Number(err?.statusCode || 0)
      const message = String(err?.message || '')
      return [401, 403].includes(statusCode) || ['401', '403', 'NEED_LOGIN', 'member auth required'].includes(code) || message.includes('NEED_LOGIN')
    }

    const requireCheckoutAuth = () => {
      clearCustomerSession()
      refreshCustomerAuthState()
      if (!pendingPaymentIntent.value && !pendingOrderId.value) pendingPaymentIntent.value = createPaymentIntent()
      authActionStatus.value = 'idle'
      showCheckoutAuth.value = true
    }

    const switchToCard = () => {
      activeTab.value = 'card'
      refreshCustomerAuthState()
      if (hasCustomerIdentity.value && !bannerInfo.value) loadMemberStatus({ authRedirect: false })
    }
    const goMine = () => uni.navigateTo({ url: '/pages/mine/mine' })
    const memberLevelLabel = computed(() => bannerInfo.value?.levelLabel || '\u666e\u901a\u4f1a\u5458')
    const MEMBER_LEVEL_BADGES = { LV1: '/static/member-levels/level-lv1.png', LV2: '/static/member-levels/level-lv2.png', LV3: '/static/member-levels/level-lv3.png' }
    const memberLevelBadgeSrc = computed(() => MEMBER_LEVEL_BADGES[bannerInfo.value?.levelCode] || MEMBER_LEVEL_BADGES.LV1)
    const memberProgressPercent = computed(() => {
      const current = Number(bannerInfo.value?.growth || bannerInfo.value?.growthValue || 0)
      const target = Number(bannerInfo.value?.nextGrowth || 0)
      if (!target || target <= 0) return 0
      return Math.max(0, Math.min(100, Math.round((current / target) * 100)))
    })
    const memberUpgradeText = computed(() => {
      const amount = Number(bannerInfo.value?.nextUpgradeAmount || 0)
      return amount > 0 ? '\u518d\u6d88\u8d39 \u00a5' + formatPrice(amount) + ' \u5347\u7ea7' : ''
    })
    const usableMemberCoupons = computed(() => (bannerInfo.value?.coupons || []).slice(0, 3))
    const couponAmountText = (coupon) => formatPrice(coupon?.value ?? coupon?.amount ?? coupon?.discount_amount ?? 0)
    const couponConditionText = (coupon) => {
      const min = Number(coupon?.min_amount ?? coupon?.threshold_amount ?? coupon?.threshold ?? 0)
      return min > 0 ? '\u6ee1' + formatPrice(min) + '\u5143\u53ef\u7528' : '\u65e0\u95e8\u69db\u53ef\u7528'
    }
    const couponValidityText = (coupon) => {
      const raw = coupon?.expire_time || coupon?.valid_end_time || coupon?.end_time || ''
      if (!raw) return '\u5f53\u524d\u53ef\u7528'
      const end = new Date(raw)
      if (Number.isNaN(end.getTime())) return '\u5f53\u524d\u53ef\u7528'
      const now = new Date()
      if (end.toDateString() === now.toDateString()) return '\u4eca\u65e5\u6709\u6548'
      return '\u6709\u6548\u671f\u81f3' + String(end.getMonth() + 1).padStart(2, '0') + '.' + String(end.getDate()).padStart(2, '0')
    }
    const goOrderFromMember = () => { activeTab.value = 'order' }
    const handleMemberCardAuth = async (event) => {
      if (memberAuthorizing.value) return
      const phoneCode = event?.detail?.code || event?.detail?.phoneCode || ''
      if (!phoneCode) return uni.showToast({ title: '\u672a\u5b8c\u6210\u6388\u6743\uff0c\u8bf7\u91cd\u8bd5', icon: 'none' })
      memberAuthorizing.value = true
      try {
        const code = await wxLogin()
        const res = await joinByEntranceCode({
          scene: uni.getStorageSync('entrance_scene') || '',
          tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
          table_no: tableNo.value || uni.getStorageSync('table_no') || '',
          code,
          phone_code: phoneCode,
          agreement_accepted: true,
          invite_code: uni.getStorageSync('invite_code') || '',
        }, { authRedirect: false })
        if (res?.code !== 200) {
          uni.showToast({ title: res?.msg || '\u52a0\u5165\u4f1a\u5458\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5', icon: 'none' })
          return
        }
        // \u9080\u8bf7\u7801\u7528\u8fc7\u5c31\u6e05\u6389\uff0c\u907f\u514d\u4ee5\u540e\u5728\u522b\u7684\u5e97\u8bef\u7528
        uni.removeStorageSync('invite_code')
        saveCustomerSession(res.data || {})
        await bindCurrentDiningParticipant()
        await loadMemberStatus({ authRedirect: false })
        activeTab.value = 'card'
        uni.showToast({ title: '\u5df2\u767b\u5f55', icon: 'none' })
        checkWelcomeCoupon()
      } catch (err) {
        uni.showToast({ title: err?.message || '\u6388\u6743\u672a\u5b8c\u6210\uff0c\u8bf7\u91cd\u8bd5', icon: 'none' })
      } finally {
        memberAuthorizing.value = false
      }
    }
    const useMemberCoupon = (coupon) => {
      selectedCouponId.value = coupon?.id || coupon?.coupon_id || null
      activeTab.value = 'order'
    }
    const loadDistance = (shopLat, shopLng) => {
      if (!shopLat || !shopLng) return
      uni.getLocation({
        type: 'gcj02',
        success: (res) => {
          const R = 6371000
          const dLat = (shopLat - res.latitude) * Math.PI / 180
          const dLng = (shopLng - res.longitude) * Math.PI / 180
          const a = Math.sin(dLat / 2) ** 2 + Math.cos(res.latitude * Math.PI / 180) * Math.cos(shopLat * Math.PI / 180) * Math.sin(dLng / 2) ** 2
          const d = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
            shopDistance.value = d < 1000 ? Math.round(d) + 'm' : (d / 1000).toFixed(1) + 'km'
        },
        fail: () => {},
      })
    }
    const closedNotice = ref('')

    const showSpecSheet = ref(false)
    const specDish = ref({})
    const specQty = ref(1)
    const specStep = ref(1)
    const selectedSpecs = ref({})
    const selectedExtras = ref([])
    const itemRemark = ref('') // { groupName: [optName] }
    const showItemRemarkExtra = ref(false)
    const itemRemarkExtra = computed(() => {
      let text = itemRemark.value
      remarkChips.value.forEach((chip) => { text = text.split(chip).join('') })
      return text.replace(/\s+/g, ' ').trim()
    })
    const toggleItemRemarkChip = (chip) => {
      if (itemRemark.value.includes(chip)) {
        itemRemark.value = itemRemark.value.replace(chip, '').replace(/^\s+|\s+$/g, '').trim()
      } else {
        itemRemark.value = itemRemark.value ? itemRemark.value + ' ' + chip : chip
      }
    }
    const imageLoadFailed = ref({})
    const detailImageFailed = ref(false)

    const specSteps = [
      { no: 1, label: '\u9009\u89c4\u683c' },
      { no: 2, label: '\u9644\u52a0' },
      { no: 3, label: '\u5907\u6ce8' },
      { no: 4, label: '\u786e\u8ba4' },
    ]
    const normalizeSpecGroups = (dish) => {
      const raw = dish?.spec_groups || dish?.specs || dish?.spec_options || []
      if (Array.isArray(raw) && raw.length) {
        return raw.map((g) => {
          const rawType = g.type || (g.multiple ? 'checkbox' : 'single')
          const normalizedType = ['multi', 'multiple', 'checkbox'].includes(rawType) ? 'multiple' : 'single'
          return {
            name: g.name || g.group || g.title || specText.spec,
            type: normalizedType,
            required: g.required !== false,
            options: (g.options || g.values || []).map((o) => typeof o === 'string' ? { name: o, price_delta: 0 } : { name: o.name || o.value || o.label, price_delta: Number(o.price_delta || o.extra_price || 0) }),
          }
        }).filter(g => g.options.length)
      }
      if (dish?.has_options || dish?.hasOptions) {
        return [{ name: '\u8fa3\u5ea6', type: 'single', required: true, options: ['\u4e0d\u8fa3', '\u5fae\u8fa3', '\u4e2d\u8fa3', '\u91cd\u8fa3'].map(name => ({ name, price_delta: 0 })) }]
      }
      return []
    }
    const specAllGroups = computed(() => normalizeSpecGroups(specDish.value))
    const specRadioGroups = computed(() => specAllGroups.value.filter(g => g.type !== 'checkbox' && g.type !== 'multiple' && g.type !== 'multi'))
    const specExtraOptions = computed(() => {
      const groups = specAllGroups.value.filter(g => g.type === 'checkbox' || g.type === 'multiple' || g.type === 'multi')
      return groups.flatMap(g => g.options).filter(o => o.name)
    })
    // 备注快捷词跟这道菜自己的规格选项字面重复时不再展示——比如这道菜的"辣度"
    // 规格已经问过"不辣/微辣/中辣/重辣"，备注里就不该再问一遍"不要辣/微辣"，不然
    // 顾客两边都能点、选出自相矛盾的组合（规格选中辣、备注又点不要辣），厨房不
    // 知道听哪个。去掉"不要/不/少/多/加/免"这类常见修饰前缀取核心词再比较，纯
    // 字符串规则、不做语义理解，能覆盖"不要辣"对应规格选项"不辣"这类同义表达，
    // 又不会误伤"少盐""打包"这些跟规格无关的词。
    const SPEC_REMARK_MODIFIER_PREFIXES = ['不要', '不', '少', '多', '加', '免']
    const specRemarkCoreWord = (text) => {
      const raw = String(text || '').trim()
      for (const prefix of SPEC_REMARK_MODIFIER_PREFIXES) {
        if (raw.startsWith(prefix) && raw.length > prefix.length) return raw.slice(prefix.length)
      }
      return raw
    }
    const specGroupOptionCoreWords = computed(() => {
      const words = new Set()
      specAllGroups.value.forEach((group) => {
        group.options.forEach((opt) => {
          const core = specRemarkCoreWord(opt.name)
          if (core) words.add(core)
        })
      })
      return words
    })
    const filteredRemarkChips = computed(() => {
      const coreWords = specGroupOptionCoreWords.value
      if (!coreWords.size) return remarkChips.value
      return remarkChips.value.filter((chip) => !coreWords.has(specRemarkCoreWord(chip)))
    })
    const specBasePrice = computed(() => Number(specDish.value.price) || 0)
    const specExtraPrice = computed(() => {
      let extra = 0
      for (const group of specRadioGroups.value) {
        const sel = selectedSpecs.value[group.name] || []
        for (const opt of group.options) if (sel.includes(opt.name)) extra += Number(opt.price_delta || 0)
      }
      for (const opt of specExtraOptions.value) if (selectedExtras.value.includes(opt.name)) extra += Number(opt.price_delta || 0)
      return extra
    })
    const specUnitPrice = computed(() => specBasePrice.value + specExtraPrice.value)
    const specTotalPrice = computed(() => specUnitPrice.value * specQty.value)
    const selectedSpecRows = computed(() => specRadioGroups.value.map(group => ({ group: group.name, value: (selectedSpecs.value[group.name] || [])[0] || '' })).filter(i => i.value))
    const selectedSpecSummary = computed(() => selectedSpecRows.value.map(i => i.value).join(specText.separator))
    const specDishDesc = computed(() => String(specDish.value.desc || specDish.value.description || '').trim())
    const missingRequiredSpecGroup = computed(() => specRadioGroups.value.find(group => group.required && !(selectedSpecs.value[group.name] || []).length))
    const requiredGroupPrompt = (group) => new RegExp('\\u8fa3|\\u53e3\\u5473|\\u751c\\u5ea6|\\u6e29\\u5ea6').test(group?.name || '') ? specText.chooseTaste : specText.chooseSpec
    const canGoNextSpec = computed(() => !isSoldOut(specDish.value) && !missingRequiredSpecGroup.value)
    const specPrimaryText = computed(() => {
      if (isSoldOut(specDish.value)) return '\u5df2\u552e\u7f44'
      if (missingRequiredSpecGroup.value) return requiredGroupPrompt(missingRequiredSpecGroup.value)
      return specText.add + ' ' + confirmationText.currency + formatPrice(specTotalPrice.value)
    })
    function isSpecSelected(group, opt) {
      return (selectedSpecs.value[group.name] || []).includes(opt.name)
    }
    function toggleSpec(group, opt) {
      selectedSpecs.value = { ...selectedSpecs.value, [group.name]: [opt.name] }
    }
    const toggleExtra = (extra) => {
      selectedExtras.value = selectedExtras.value.includes(extra) ? selectedExtras.value.filter(x => x !== extra) : [...selectedExtras.value, extra]
    }
    const buildSpecKey = () => JSON.stringify({ id: specDish.value.id, specifications: selectedSpecRows.value, extras: selectedExtras.value, itemRemark: itemRemark.value.trim() })
    function cancelSpec() { showSpecSheet.value = false }
    function handleSpecPrimary() {
      if (!canGoNextSpec.value) return
      confirmSpec()
    }
    function confirmSpec() {
      if (isSoldOut(specDish.value)) return
      const specKey = buildSpecKey()
      const specifications = selectedSpecRows.value.map(i => ({ group: i.group, value: i.value }))
      const extras = [...selectedExtras.value]
      const remarkText = itemRemark.value.trim()
      const labels = [...specifications.map(i => i.value), ...extras]
      if (remarkText) labels.push(remarkText)
      const existing = specCartItems.value.find(i => i.specKey === specKey)
      if (existing) {
        existing.qty += specQty.value
      } else {
        specCartItems.value.push({
          specKey,
          id: specDish.value.id,
          name: specDish.value.name,
          orderName: labels.length ? specDish.value.name + '(' + labels.join(specText.separator) + ')' : specDish.value.name,
          price: specUnitPrice.value,
          qty: specQty.value,
          emoji: specDish.value.emoji,
          specLabel: labels.join(specText.dotSeparator),
          specifications,
          extras,
          itemRemark: remarkText,
          selectedSpecs: JSON.parse(JSON.stringify(selectedSpecs.value)),
        })
      }
      showSpecSheet.value = false
      triggerCartSuccessFeedback(specKey)
      uni.vibrateShort({ type: 'light' })
    }

    const specCartItems = ref([])

    const normalizeOrderStatus = (status) => {
      if (['paid', 'pending'].includes(status)) return 'pending'
      if (['accepted', 'preparing', 'cooking'].includes(status)) return 'preparing'
      if (['done', 'completed'].includes(status)) return 'done'
      if (status === 'settled') return 'settled'
      if (['cancelled', 'rejected'].includes(status)) return status
      return 'pending'
    }

    const orderItemCount = (order) =>
      (order?.items || []).reduce((sum, item) => sum + Number(item.qty || 0), 0)

    const activeOrderRank = (order) => {
      const status = normalizeOrderStatus(order?.status)
      if (['pending', 'preparing'].includes(status)) return 0
      if (status === 'done') return 1
      return 2
    }

    const currentTableOrder = computed(() => {
      if (!myOrders.value.length) return null
      const active = [...myOrders.value]
        .filter(order => !['cancelled', 'rejected'].includes(normalizeOrderStatus(order.status)))
        .sort((a, b) => activeOrderRank(a) - activeOrderRank(b))[0]
      if (active) return active
      // 全部订单都已取消/拒单时，只有当前设备正在跟踪的那单才继续展示"异常状态"，
      // 避免把本桌历史上别人取消的旧单当成当前顾客的订单弹出来。
      return myOrders.value.find(order => order.id === orderId.value) || null
    })

    const historyTableOrders = computed(() =>
      myOrders.value.filter(order => !currentTableOrder.value || order.id !== currentTableOrder.value.id)
    )

    const isTableAccountMode = computed(() => paymentMode.value === "table_account")
    const isPostpayMode = computed(() => paymentMode.value === "postpay")
    // 餐后付款和桌台账单，后端其实是同一套机制：同一桌多次下单共用同一个 dining_session，
    // 商家在后台也是按整桌一次性结账（settle-table），不是按单笔结账。小程序这边如果还是把
    // 餐后付款当成"每笔订单各自一个独立进度条"来展示，就跟后端的真实行为对不上——这里统一
    // 用"共享账单模式"复用桌台账单那套汇总视图，只是底部动作不同（见下面 canCheckout 附近）。
    const isSharedBillMode = computed(() => isTableAccountMode.value || isPostpayMode.value)
    const sharedBillSubLabel = computed(() => isPostpayMode.value ? '堂食 · 餐后统一结账' : '堂食 · 本桌统一结账')
    const tableSessionId = computed(() => String(diningSessionId.value || uni.getStorageSync('dining_session_id') || ''))
    const isSameDiningSessionOrder = (order) => {
      const orderSessionId = String(order?.diningSessionId || order?.tableSessionId || '')
      if (!tableSessionId.value || !orderSessionId) return false
      return orderSessionId === tableSessionId.value
    }
    const tableSessionOrders = computed(() =>
      myOrders.value
        .filter(order => ['table_account', 'postpay'].includes(normalizePaymentMode(order?.paymentMode || paymentMode.value)))
        .filter(isSameDiningSessionOrder)
        .sort((a, b) => Number(a.createdTs || 0) - Number(b.createdTs || 0))
    )
    const isOrderInvalid = (order) => ['cancelled', 'rejected'].includes(normalizeOrderStatus(order?.status))
    const isItemInvalid = (item) => ['refunded', 'refund', 'cancelled', 'canceled'].includes(String(item?.status || item?.refund_status || '').toLowerCase())
    const validTableOrders = computed(() => tableSessionOrders.value.filter(order => !isOrderInvalid(order)))
    const tableTotal = computed(() => {
      if (Number(tableSessionTotal.value) > 0) return Number(tableSessionTotal.value)
      const backendTotal = validTableOrders.value.map(order => Number(order.tableTotal || 0)).find(total => total > 0)
      if (backendTotal) return backendTotal
      return validTableOrders.value.reduce((sum, order) => sum + Number(order.total || 0), 0)
    })
    const tableItemCount = computed(() =>
      validTableOrders.value.reduce((sum, order) => sum + (order.items || []).reduce((itemSum, item) => itemSum + (isItemInvalid(item) ? 0 : orderItemQty(item)), 0), 0)
    )
    const tableGroupStatusText = (status) => ({
      pending: '待确认',
      preparing: '制作中',
      done: '已上桌',
      settled: '已结账',
      cancelled: '已取消',
      rejected: '已取消',
    })[normalizeOrderStatus(status)] || '待确认'
    const tableGroupStatusTone = (status) => {
      const normalized = normalizeOrderStatus(status)
      if (['cancelled', 'rejected'].includes(normalized)) return 'muted'
      if (normalized === 'settled') return 'settled'
      if (normalized === 'done') return 'served'
      return 'active'
    }
    // 拼桌时同一桌可能好几个人各自的手机都在下单，用固定的一组颜色循环分配，
    // 不够用就从头再来一轮——纯展示用的编号，跟真实身份无关，参考大厂拼单点餐的做法。
    const PARTICIPANT_COLORS = ['#07C160', '#FF7D45', '#5B8FF9', '#F5A623', '#B37FEB', '#3ABBB0']
    const participantColor = (no) => {
      if (!no || no < 1) return PARTICIPANT_COLORS[0]
      return PARTICIPANT_COLORS[(no - 1) % PARTICIPANT_COLORS.length]
    }
    const tableOrderGroups = computed(() =>
      tableSessionOrders.value.map((order, index) => ({
        id: order.id || String(index),
        title: (order.createdAt || '--:--') + (index === 0 ? ' 下单' : ' 加菜'),
        statusText: tableGroupStatusText(order.status),
        tone: tableGroupStatusTone(order.status),
        discountAmount: Number(order.discountAmount || 0),
        participantNo: order.participantNo || null,
        participantColor: participantColor(order.participantNo),
        isStaff: Boolean(order.isStaff),
        staffNote: order.staffNote || '',
        items: (order.items || []).map(item => ({
          ...item,
          isInvalid: isOrderInvalid(order) || isItemInvalid(item),
          invalidText: isOrderInvalid(order) ? '已取消' : '已退菜',
        })),
      }))
    )
    const isTableSettled = computed(() => {
      if (tableSessionClosed.value) return true
      if (tableSessionStatus.value === 'CLOSED') return true
      return tableSessionOrders.value.length > 0 && tableSessionOrders.value.every(order => normalizeOrderStatus(order.status) === 'settled')
    })
    const canContinueOrder = computed(() => isSharedBillMode.value && !tableSessionClosed.value && tableSessionStatus.value !== 'CLOSED')
    // 桌台账单/餐后付款都必须等本桌所有有效订单都做完（done）才算"可以结账"，否则会出现
    // 桌台账单顾客点了"去结账"、商家在后台点结账时却被后端 settle-table 以"本桌还有未完成
    // 的订单"拒绝的落差；餐后付款虽然没有"去结账"按钮，但同样的判断决定要不要提示去收银台。
    const allOrdersDone = computed(() =>
      validTableOrders.value.length > 0 && validTableOrders.value.every(order => normalizeOrderStatus(order.status) === 'done')
    )
    const stillPreparing = computed(() => tableOrderGroups.value.length > 0 && !isTableSettled.value && !allOrdersDone.value)
    const checkoutRequested = computed(() => Boolean(checkoutRequestedAt.value))
    // 只有桌台账单才有"去结账"这个可点击的自助操作——餐后付款结账动作在商家手里
    // （收银台/服务员操作后台"结账"按钮），小程序这边只负责提示，不提供可点的按钮。
    const canCheckout = computed(() =>
      isTableAccountMode.value && tableItemCount.value > 0 && !isTableSettled.value && !tableCheckouting.value && allOrdersDone.value
    )
    const postpayReadyToSettle = computed(() =>
      isPostpayMode.value && tableItemCount.value > 0 && !isTableSettled.value && allOrdersDone.value
    )
    // "查看结账详情"点击后要做的事：账单信息（结账时间/优惠/明细）本来就在这个 sheet
    // 里，不需要再跳一个页面或弹一次窗——只是把视图滚回顶部，让这些信息进入视野。
    // 之前这里错误地复用了"发起结账"的 handleTableCheckout，点了只会弹"请联系服务员"。
    const scrollTableAccountToTop = async () => {
      tableAccountScrollInto.value = ''
      await nextTick()
      tableAccountScrollInto.value = 'table-account-status-anchor'
    }
    const formatClosedAtTime = (raw) => {
      if (!raw) return ''
      const d = new Date(raw)
      if (Number.isNaN(d.getTime())) return ''
      return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
    }
    const tableStatusView = computed(() => {
      if (isTableSettled.value) {
        const closedTimeText = formatClosedAtTime(tableSessionClosedAt.value)
        const payNote = isTableAccountMode.value
          ? '由商家柜台现结，无需再次付款'
          : (isPostpayMode.value ? '已在收银台完成支付' : '')
        return {
          icon: 'icon-roundcheckfill',
          title: '本桌已结账',
          desc: closedTimeText ? `结账时间 ${closedTimeText}` : '本次用餐账单已经结清',
          note: payNote,
          tone: 'settled',
        }
      }
      if (!tableOrderGroups.value.length) return { icon: 'icon-list', title: '本桌还没有已点菜品', desc: '先点菜，后续加菜会自动合并', tone: 'settled' }
      const statuses = validTableOrders.value.map(order => normalizeOrderStatus(order.status))
      if (statuses.includes('pending')) return { icon: 'icon-timefill', title: '订单已收到', desc: '商家正在确认订单，请稍候', tone: 'active' }
      if (statuses.includes('preparing')) return { icon: 'icon-beican', title: '菜品正在制作', desc: '厨房正在制作，可以继续加菜', tone: 'active' }
      if (statuses.includes('done')) {
        if (isPostpayMode.value) {
          return { icon: 'icon-roundcheckfill', title: '菜品已上齐', desc: '用餐结束请到收银台或联系服务员结账', tone: 'served' }
        }
        return checkoutRequested.value
          ? { icon: 'icon-roundcheckfill', title: '已呼叫服务员', desc: '请稍候，服务员马上为您结账', tone: 'served' }
          : { icon: 'icon-roundcheckfill', title: '菜品已上齐', desc: '吃好后可统一结账', tone: 'served' }
      }
      return { icon: 'icon-beican', title: '商家已接单', desc: '厨房正在为您制作，可以继续加菜', tone: 'active' }
    })
    const orderItemImage = (item) => item?.image || item?.image_url || item?.cover || item?.cover_url || ''
    const markOrderItemImageFailed = (key) => { orderItemImageFailed.value = { ...orderItemImageFailed.value, [key]: true } }

    const currentTableOrderStatus = computed(() => normalizeOrderStatus(currentTableOrder.value?.status || orderStatus.value))


    const tableOrderStatusTone = computed(() => {
      if (!currentTableOrder.value) return 'empty'
      const status = currentTableOrderStatus.value
      if (['cancelled', 'rejected'].includes(status)) return 'canceled'
      if (status === 'pending') return 'paid'
      if (status === 'preparing') return 'preparing'
      if (status === 'done') return 'served'
      if (status === 'settled') return 'settled'
      return 'paid'
    })

    const tableOrderStatusBadge = computed(() => ({
      canceled: '\u5f02\u5e38\u72b6\u6001',
      paid: '\u6b63\u5e38\u8fdb\u884c',
      preparing: '\u6b63\u5728\u5907\u9910',
      served: '\u5df2\u9001\u8fbe',
      settled: '\u8ba2\u5355\u5b8c\u6210',
    })[tableOrderStatusTone.value] || '\u6b63\u5e38\u8fdb\u884c')

    const tableOrderStatusIcon = computed(() => ({
      canceled: 'icon-warnfill',
      paid: 'icon-pay',
      preparing: 'icon-beican',
      served: 'icon-deliver',
      settled: 'icon-roundcheckfill',
    })[tableOrderStatusTone.value] || 'icon-pay')

    const tableOrderNextAction = computed(() => ({
      canceled: '\u91cd\u65b0\u70b9\u9910',
      paid: '\u65e0\u9700\u64cd\u4f5c\uff0c\u8bf7\u7a0d\u5019',
      preparing: '\u7b49\u5f85\u4e0a\u9910\u5373\u53ef',
      served: '\u8bf7\u786e\u8ba4\u83dc\u54c1',
      settled: '\u53ef\u5173\u95ed\u67e5\u770b',
    })[tableOrderStatusTone.value] || '\u65e0\u9700\u64cd\u4f5c\uff0c\u8bf7\u7a0d\u5019')

    const tableOrderProgressSub = computed(() => ({
      canceled: '\u65e0\u9700\u7b49\u5f85',
      paid: '\u9884\u8ba1\u5f88\u5feb\u63a5\u5355',
      preparing: '\u5546\u5bb6\u5904\u7406\u4e2d',
      served: '\u53ef\u5b89\u5fc3\u7528\u9910',
      settled: '\u8ba2\u5355\u5b8c\u6210',
    })[tableOrderStatusTone.value] || '\u8ba2\u5355\u8fdb\u884c\u4e2d')

    const tableOrderPrimaryButtonText = computed(() => ({
      empty: '\u53bb\u70b9\u9910',
      canceled: '\u91cd\u65b0\u70b9\u9910',
      paid: '\u6211\u77e5\u9053\u4e86',
      preparing: '\u6211\u77e5\u9053\u4e86',
      served: '\u786e\u8ba4\u5df2\u6536\u5230',
      settled: '\u5173\u95ed',
    })[tableOrderStatusTone.value] || '\u6211\u77e5\u9053\u4e86')

    const tableOrderStatusTitle = computed(() => ({
      pending: '\u5546\u5bb6\u6b63\u5728\u786e\u8ba4\u8ba2\u5355',
      preparing: '\u5546\u5bb6\u5df2\u63a5\u5355\uff0c\u6b63\u5728\u5236\u4f5c',
      done: '\u9910\u54c1\u5df2\u4e0a\u9910\uff0c\u8bf7\u7559\u610f',
      settled: '\u672c\u684c\u8ba2\u5355\u5df2\u5b8c\u6210',
      rejected: '\u8ba2\u5355\u5f02\u5e38\uff0c\u8bf7\u8054\u7cfb\u5546\u5bb6',
      cancelled: '\u8ba2\u5355\u5df2\u53d6\u6d88',
    })[currentTableOrderStatus.value] || '\u5546\u5bb6\u6b63\u5728\u786e\u8ba4\u8ba2\u5355')

    const tableOrderStatusHint = computed(() => {
      if (!currentTableOrder.value) return '\u6682\u65e0\u672c\u684c\u8ba2\u5355'
      return ['done', 'settled'].includes(currentTableOrderStatus.value) ? '\u8bf7\u7559\u610f\u53d6\u9910\u6216\u670d\u52a1\u5458\u901a\u77e5' : '\u65e0\u9700\u64cd\u4f5c\uff0c\u8bf7\u5b89\u5fc3\u7b49\u5f85'
    })

    const tableOrderTimeline = computed(() => {
      const order = ['pending', 'preparing', 'done', 'settled']
      const currentIndex = Math.max(0, order.indexOf(currentTableOrderStatus.value))
      return [
        { key: 'paid', status: 'pending', label: '\u5df2\u652f\u4ed8', icon: 'icon-pay', desc: currentTableOrder.value?.createdAt || '' },
        { key: 'preparing', status: 'preparing', label: '\u5546\u5bb6\u5df2\u63a5\u5355', icon: 'icon-beican', desc: currentIndex >= 1 ? '\u53a8\u623f\u5f00\u59cb\u5904\u7406' : '' },
        { key: 'done', status: 'done', label: '\u5df2\u4e0a\u9910', icon: 'icon-deliver', desc: currentIndex >= 2 ? '\u9910\u54c1\u5df2\u5b8c\u6210' : '' },
        { key: 'settled', status: 'settled', label: '\u5df2\u5b8c\u6210', icon: 'icon-roundcheckfill', desc: currentIndex >= 3 ? '\u672c\u684c\u5df2\u7ed3\u675f' : '' },
      ].map((step, index) => ({ ...step, done: index < currentIndex, active: index === currentIndex }))
    })

    const currentOrderItemCount = computed(() => orderItemCount(currentTableOrder.value))
    const currentOrderItems = computed(() => currentTableOrder.value?.items || [])

    const orderItemName = (item) => item?.orderName || item?.name || item?.goods_name || item?.dish_name || '\u5546\u54c1'
    const orderItemQty = (item) => Number(item?.qty || item?.quantity || item?.count || 1)
    const orderItemAmount = (item) => Number(item?.amount ?? item?.total ?? (Number(item?.price || 0) * orderItemQty(item)))
    const orderItemSpecText = (item) => {
      if (item?.specLabel) return item.specLabel
      if (item?.spec_text) return item.spec_text
      if (Array.isArray(item?.specifications) && item.specifications.length) {
        return item.specifications.map(spec => spec.value || spec.name).filter(Boolean).join(' \u00b7 ')
      }
      return ''
    }

    const currentOrderMainItemText = computed(() => {
      const items = currentTableOrder.value?.items || []
      if (!items.length) return '\u6682\u65e0\u5546\u54c1'
      const first = items[0]
      const suffix = items.length > 1 ? ' \u7b49' + items.length + '\u79cd' : ''
      return first.name + ' x' + first.qty + suffix
    })
    const pendingOrderCount = computed(() =>
      myOrders.value.filter(o => !['settled', 'cancelled', 'rejected'].includes(normalizeOrderStatus(o.status))).length
    )

    const statusLabel = (s) => ({ pending: '\u7b49\u5f85\u63a5\u5355', preparing: '\u5907\u9910\u4e2d', done: '\u5df2\u5b8c\u6210', rejected: '\u5df2\u62d2\u5355', cancelled: '\u5df2\u53d6\u6d88', settled: '\u5df2\u7ed3\u8d26' })[s] || s

    const doCancelOrder = (order) => {
      uni.showModal({
        title: '\u53d6\u6d88\u8ba2\u5355',
        content: '\u786e\u8ba4\u53d6\u6d88\u6b64\u8ba2\u5355\u5417\uff1f\u5546\u5bb6\u63a5\u5355\u540e\u65e0\u6cd5\u53d6\u6d88\u3002',
        success: async ({ confirm }) => {
          if (!confirm) return
          try {
            await cancelOrder(order.id, diningParticipantToken.value || uni.getStorageSync('dining_participant_token'))
            order.status = 'cancelled'
            saveMyOrders()
            if (orderId.value === order.id) {
              stopStatusPoll()
              orderStatus.value = 'cancelled'
              showSuccess.value = false
            }
            uni.showToast({ title: '\u8ba2\u5355\u5df2\u53d6\u6d88', icon: 'success', duration: 1200 })
          } catch {
            uni.showToast({ title: '\u53d6\u6d88\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5', icon: 'none', duration: 1200 })
          }
        }
      })
    }

    function saveMyOrders() {
      const key = 'my_orders_' + shopId.value + '_' + tableNo.value
      try { uni.setStorageSync(key, JSON.stringify(myOrders.value)) } catch (e) {}
    }

    function loadMyOrders() {
      const key = 'my_orders_' + shopId.value + '_' + tableNo.value
      try {
        const raw = uni.getStorageSync(key)
        if (raw) myOrders.value = JSON.parse(raw)
      } catch (e) {}
    }

    const pendingPaymentStorageKey = () => 'pending_payment_order_' + shopId.value + '_' + tableNo.value

    const savePendingPaymentOrder = () => {
      if (!pendingOrderId.value) return
      try {
        uni.setStorageSync(pendingPaymentStorageKey(), JSON.stringify({
          orderId: pendingOrderId.value,
          orderNo: orderNo.value,
          payAmount: payAmount.value,
          total: payAmount.value,
          items: successItems.value,
          createdTs: Date.now(),
        }))
      } catch (e) {}
    }

    const restorePendingPaymentOrder = () => {
      if (pendingOrderId.value) return true
      try {
        const raw = uni.getStorageSync(pendingPaymentStorageKey())
        if (!raw) return false
        const record = JSON.parse(raw)
        if (!record?.orderId) return false
        pendingOrderId.value = String(record.orderId)
        orderNo.value = String(record.orderNo || record.orderId || '').slice(-4)
        payAmount.value = Number(record.payAmount || record.total || 0)
        successItems.value = Array.isArray(record.items) ? record.items : []
        successTotal.value = Number(record.total || record.payAmount || 0)
        return true
      } catch (e) {
        return false
      }
    }

    const clearPendingPaymentOrder = () => {
      try { uni.removeStorageSync(pendingPaymentStorageKey()) } catch (e) {}
      pendingOrderId.value = ''
      paymentFailed.value = false
    }

    const clearStalePrepayOrderForPayLater = () => {
      if (isPrepayMode.value || !pendingOrderId.value) return
      clearPendingPaymentOrder()
      pendingPaymentIntent.value = null
    }

    const isPaidOrSubmittedOrder = (order) => {
      const status = order?.status || ''
      const paymentStatus = order?.payment_status || ''
      return paymentStatus === 'paid' || ['pending', 'paid', 'accepted', 'preparing', 'done', 'completed', 'settled'].includes(status)
    }

    let recoveringPayment = false
    const recoverPendingPaymentResult = async ({ showDetail = false } = {}) => {
      if (recoveringPayment) return false
      restorePendingPaymentOrder()
      const id = pendingOrderId.value
      if (!id) return false
      recoveringPayment = true
      try {
        const res = await getOrderStatus(id, diningParticipantToken.value)
        const data = res?.data || {}
        if (isPaidOrSubmittedOrder(data)) {
          orderId.value = id
          orderStatus.value = data.status || 'pending'
          merchantNote.value = data.merchant_note || ''
          showCart.value = false
          showCheckoutAuth.value = false
          pendingPaymentIntent.value = null
          clearPendingPaymentOrder()

          const now = new Date()
          const existed = myOrders.value.find(o => String(o.id) === String(id))
          if (existed) {
            existed.status = orderStatus.value
          } else {
            myOrders.value.unshift({
              id,
              orderNo: orderNo.value || String(id).slice(-4),
              status: orderStatus.value,
              items: successItems.value,
              total: successTotal.value || payAmount.value,
              createdAt: now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0'),
              createdTs: now.getTime(),
              table: tableNo.value,
            })
          }
          saveMyOrders()
          startStatusPoll(id)
          await syncDiningOrders()
          showOrders.value = showDetail || showOrders.value
          return true
        }
        if (['cancelled', 'rejected'].includes(data.status)) {
          clearPendingPaymentOrder()
        }
        return false
      } catch (e) {
        return false
      } finally {
        recoveringPayment = false
      }
    }

    const merchantNote = ref('')

    const successOrderItemCount = computed(() =>
      successItems.value.reduce((sum, item) => sum + Number(item.qty || 0), 0)
    )
    const successOrderNo = computed(() => orderNo.value || (orderId.value ? String(orderId.value).slice(-4) : '--'))
    const successStatusText = computed(() => ({
      pending: successText.statusPending,
      paid: successText.statusPending,
      accepted: successText.statusPreparing,
      preparing: successText.statusPreparing,
      done: successText.statusDone,
      completed: successText.statusDone,
      settled: successText.statusDone,
      rejected: successText.statusRejected,
      cancelled: successText.statusRejected,
    })[orderStatus.value] || successText.statusFallback)
    const successStatusTone = computed(() => {
      if (['preparing', 'accepted'].includes(orderStatus.value)) return 'preparing'
      if (['done', 'completed', 'settled'].includes(orderStatus.value)) return 'done'
      if (['rejected', 'cancelled'].includes(orderStatus.value)) return 'warning'
      return 'pending'
    })
    const orderStatusText = successStatusText

    const orderStatusClass = computed(() => orderStatus.value)

    watch(orderStatus, (newVal, oldVal) => {
      if (newVal === 'preparing' && oldVal === 'pending') {
        uni.vibrateShort({ type: 'heavy' })
        uni.showToast({ title: '\u5546\u5bb6\u5df2\u63a5\u5355\uff0c\u6b63\u5728\u5907\u9910', icon: 'none', duration: 2500 })
      } else if (newVal === 'done') {
        uni.vibrateShort({ type: 'heavy' })
      } else if (newVal === 'rejected') {
        stopStatusPoll()
        uni.vibrateShort({ type: 'heavy' })
        uni.showModal({ title: '\u8ba2\u5355\u5df2\u88ab\u62d2\u7edd', content: '\u5546\u5bb6\u6682\u65f6\u65e0\u6cd5\u5904\u7406\u6b64\u8ba2\u5355\uff0c\u8bf7\u8054\u7cfb\u670d\u52a1\u5458', showCancel: false })
      }
    })


    const finishOrdering = () => {
      showSuccess.value = false
      cart.value = {}
      specCartItems.value = []
      remark.value = ''
      selectedCouponId.value = null
      uni.showToast({ title: successText.closed, icon: 'none', duration: 900 })
      // Keep polling the paid order status in the background.
    }

    const closeSuccessAndWait = () => {
      finishOrdering()
    }

    const continueOrdering = () => {
      showSuccess.value = false
      cart.value = {}
      specCartItems.value = []
      remark.value = ''
      selectedCouponId.value = null
      activeTab.value = 'order'
      uni.showToast({ title: successText.backToMenu, icon: 'none', duration: 900 })
    }

    const viewOrderDetail = () => {
      showSuccess.value = false
      refreshAllOrderStatuses()
      showOrders.value = true
    }

    function startStatusPoll(id) {
      stopStatusPoll()
      statusPollTimer = setInterval(() => {
        getOrderStatus(id, diningParticipantToken.value).then((body) => {
          if (body.code === 200) {
            const newStatus = body.data?.status || 'pending'
            merchantNote.value = body.data?.merchant_note || ''
            orderStatus.value = newStatus
            const rec = myOrders.value.find(o => o.id === id)
            if (rec && rec.status !== newStatus) {
              rec.status = newStatus
              saveMyOrders()
            }
            if (['settled', 'cancelled', 'rejected'].includes(newStatus)) stopStatusPoll()
          }
        }).catch(() => { })
      }, 15000)
    }

    function stopStatusPoll() {
      if (statusPollTimer) { clearInterval(statusPollTimer); statusPollTimer = null }
    }

    // 本桌人数轮询：只在顾客真的停留在点餐页时跑，间隔比订单状态轮询（15秒）更松——
    // "有人加入"不是紧急信息，稍微有延迟没关系，没必要跟催单一样频繁。onHide/onUnload
    // 会停掉，不在后台空耗电量和流量。
    function startTablePresencePoll() {
      stopTablePresencePoll()
      tablePresencePollTimer = setInterval(() => {
        syncDiningOrders().catch(() => {})
      }, 25000)
    }

    function stopTablePresencePoll() {
      if (tablePresencePollTimer) { clearInterval(tablePresencePollTimer); tablePresencePollTimer = null }
    }

    async function refreshAllOrderStatuses() {
      if (await syncDiningOrders()) return
      const orders = myOrders.value.filter(o => !['settled', 'cancelled', 'rejected'].includes(normalizeOrderStatus(o.status)))
      orders.forEach(order => {
        getOrderStatus(order.id, diningParticipantToken.value).then((body) => {
          if (body.code === 200) {
            const newStatus = body.data?.status || order.status
            const rec = myOrders.value.find(o => o.id === order.id)
            if (rec && rec.status !== newStatus) {
              rec.status = newStatus
              saveMyOrders()
            }
          }
        }).catch(() => {})
      })
    }
    const remark = ref('')
    const remarkChips = ref(['\u4e0d\u8981\u8fa3', '\u5fae\u8fa3', '\u4e0d\u8981\u9999\u83dc', '\u4e0d\u8981\u8471', '\u5c11\u76d0', '\u6253\u5305'])
    const orderRemarkChips = ref(['\u4e00\u8d77\u4e0a\u83dc', '\u5168\u90e8\u6253\u5305', '\u52a0\u53cc\u7b77\u5b50', '\u4e0d\u7528\u9910\u5177', '\u6709\u513f\u7ae5\u7528\u9910'])
    const showOrderRemarkExtra = ref(false)
    const orderRemarkExtra = computed(() => {
      let text = remark.value
      orderRemarkChips.value.forEach((chip) => { text = text.split(chip).join('') })
      return text.replace(/\s+/g, ' ').trim()
    })
    const deliveryEnabled = ref(false)
    const availableCoupons = ref([])
    const selectedCouponId = ref(null)
    const selectedCoupon = computed(() =>
      availableCoupons.value.find(c => c.id === selectedCouponId.value) || null
    )
    const couponBarVisible = computed(() => isCustomerLoggedIn.value && availableCoupons.value.length > 0)
    const bestCouponValue = computed(() => {
      if (!availableCoupons.value.length) return 0
      return Math.max(...availableCoupons.value.map(c => Number(c.value || c.amount || 0)))
    })
    const couponBarText = computed(() => `\u60a8\u6709${availableCoupons.value.length}\u5f20\u4f18\u60e0\u5238\uff0c\u6700\u9ad8\u51cf\u00a5${formatPrice(bestCouponValue.value)}`)
    const couponBarPrefix = computed(() => `\u60a8\u6709${availableCoupons.value.length}\u5f20\u4f18\u60e0\u5238\uff0c\u6700\u9ad8\u51cf`)
    const couponBarAmount = computed(() => `\u00a5${formatPrice(bestCouponValue.value)}`)
    const MAX_DISCOUNT_RATIO = 0.20
    const discountAmount = computed(() => {
      if (!selectedCoupon.value) return 0
      const min = Number(selectedCoupon.value.min_amount || selectedCoupon.value.threshold_amount || 0)
      if (totalPrice.value < min) return 0
      const rawDiscount = Number(selectedCoupon.value.value || selectedCoupon.value.amount || 0)
      return Math.min(rawDiscount, Math.round(totalPrice.value * MAX_DISCOUNT_RATIO * 100) / 100)
    })
    const finalPrice = computed(() => Math.max(totalPrice.value - discountAmount.value, 0))
    const showCouponPicker = ref(false)
    // 面额一样大的时候，谁排前面不能看后端接口凑巧返回的顺序——快过期的那张要是没被
    // 选中用掉，白白过期作废，就是纯浪费掉的营销成本。所以打平时改成比谁先过期。
    const compareCouponPriority = (a, b) => {
      const valueDiff = Number(b.value || b.amount || 0) - Number(a.value || a.amount || 0)
      if (valueDiff !== 0) return valueDiff
      const aExpire = new Date(a.expire_time || a.valid_end_time || '2099-01-01').getTime()
      const bExpire = new Date(b.expire_time || b.valid_end_time || '2099-01-01').getTime()
      return aExpire - bExpire
    }
    const couponPickerList = computed(() =>
      [...availableCoupons.value]
        .map(c => ({ ...c, eligible: totalPrice.value >= Number(c.min_amount || c.threshold_amount || 0) }))
        .sort((a, b) => (b.eligible - a.eligible) || compareCouponPriority(a, b))
    )
    const couponPickerAmount = (c) => formatPrice(c.value || c.amount || 0)
    const couponPickerCondText = (c) => {
      const min = Number(c.min_amount || c.threshold_amount || 0)
      return min > 0 ? '\u6ee1' + formatPrice(min) + '\u5143\u53ef\u7528' : '\u65e0\u95e8\u69db\u53ef\u7528'
    }
    const openCouponPicker = () => { showCouponPicker.value = true }
    const closeCouponPicker = () => { showCouponPicker.value = false }
    const pickCoupon = (coupon) => {
      if (coupon && !coupon.eligible) return
      selectedCouponId.value = coupon ? coupon.id : null
      showCouponPicker.value = false
    }
    const wechatPayAmount = computed(() => finalPrice.value)
    const isPrepayMode = computed(() => paymentMode.value === 'prepay')
    const confirmPaymentLabel = computed(() => {
      if (paymentMode.value === 'table_account') return confirmationText.tableAccount
      if (paymentMode.value === 'postpay') return confirmationText.postpay
      return wechatPayAmount.value > 0 ? confirmationText.wechatPay : confirmationText.payable
    })
    const authAmountLabel = computed(() => isPrepayMode.value ? authSheetText.amount : confirmationText.goodsAmount)
    const canSubmitOrder = computed(() => totalCount.value > 0 && !!tableNo.value && !storeClosed.value && !tableSessionClosed.value)
    const payButtonText = computed(() => {
      if (ordering.value) return confirmationText.confirming
      if (paying.value) return confirmationText.paying
      if (tableSessionClosed.value) return '\u672c\u684c\u5df2\u7ed3\u675f'
      if (!canSubmitOrder.value) return confirmationText.unavailable
      if (paymentFailed.value && pendingOrderId.value) return '\u91cd\u65b0\u652f\u4ed8'
      if (paymentMode.value === 'table_account') return confirmationText.submitTableAccount
      if (paymentMode.value === 'postpay') return confirmationText.submitOrder
      return confirmationText.payNow + ' ' + confirmationText.currency + wechatPayAmount.value.toFixed(2)
    })
    const authPrimaryText = computed(() => {
      if (authActionStatus.value === 'authorizing') return authSheetText.authorizing
      if (authActionStatus.value === 'submitting') return authSheetText.submitting
      if (authActionStatus.value === 'paying') return authSheetText.paying
      if (!isPrepayMode.value) return authSheetText.confirmSubmit
      if (wechatPayAmount.value <= 0) return authSheetText.confirmFree
      return authSheetText.confirm + ' ' + confirmationText.currency + wechatPayAmount.value.toFixed(2)
    })
    const createPaymentIntent = () => ({
      merchantId: shopId.value,
      tableId: tableNo.value,
      cartSnapshot: cartItems.value.map(item => ({ id: item.id, name: item.orderName || item.name, price: item.price, qty: item.qty, specKey: item.specKey || '' })),
      couponId: selectedCouponId.value || null,
      orderRemark: remark.value.trim(),
      payableAmount: wechatPayAmount.value,
      requestId: 'pay_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
      createdAt: Date.now(),
    })
    const toggleItemsExpanded = () => { itemsExpanded.value = !itemsExpanded.value }
    const closeOrderConfirm = () => { if (!ordering.value && !paying.value) showCart.value = false }
    const resetPendingPayment = () => {
      if (ordering.value || paying.value) return
      pendingOrderId.value = ''
      pendingPaymentIntent.value = null
      paymentFailed.value = false
    }
    const toggleRemarkChip = (chip) => {
      if (remark.value.includes(chip)) {
        remark.value = remark.value.replace(chip, '').replace(/^\s+|\s+$/g, '').trim()
      } else {
        remark.value = remark.value ? remark.value + ' ' + chip : chip
      }
    }
    const activeCategory = ref('')
    const orderMode = ref('dineIn')
    const tableDisplayText = computed(() => (tableNo.value || orderModeText.unknownTable) + '\u684c')
    const orderModeDisplayText = computed(() => orderMode.value === 'delivery' ? orderModeText.delivery : orderModeText.dineIn)
    const scrollTarget = ref('')
    const allDishes = ref([])
    const cart = ref({}) // { dishId: qty }
    const addPressKey = ref('')
    const qtyPulseKey = ref('')
    const cartIconPulse = ref(false)
    const cartBadgePulse = ref(false)
    const amountPulse = ref(false)
    const microTimers = {}
    const restartMicroTimer = (key, done, duration = 180) => {
      if (microTimers[key]) clearTimeout(microTimers[key])
      microTimers[key] = setTimeout(() => {
        done()
        microTimers[key] = null
      }, duration)
    }
    const pulseKey = (target, key, timerKey, duration = 160) => {
      target.value = ''
      nextTick(() => {
        target.value = key
        restartMicroTimer(timerKey, () => { target.value = '' }, duration)
      })
    }
    const pulseFlag = (target, timerKey, duration = 180) => {
      target.value = false
      nextTick(() => {
        target.value = true
        restartMicroTimer(timerKey, () => { target.value = false }, duration)
      })
    }
    const triggerAddPress = (key) => pulseKey(addPressKey, key, 'add-' + key, 160)
    const triggerCartSuccessFeedback = (key) => {
      pulseKey(qtyPulseKey, key, 'qty-' + key, 160)
      pulseFlag(cartIconPulse, 'cart-icon', 180)
      pulseFlag(cartBadgePulse, 'cart-badge', 180)
      pulseFlag(amountPulse, 'cart-amount', 220)
    }
    const triggerCartValueFeedback = (key) => {
      pulseKey(qtyPulseKey, key, 'qty-' + key, 150)
      pulseFlag(amountPulse, 'cart-amount', 200)
    }
    const categoryOrder = ref([])

    const RECOMMEND_CAT = '\u63a8\u8350'

    const categories = computed(() => {
      const raw = []
      for (const d of allDishes.value) {
        if (d.category && !raw.includes(d.category)) raw.push(d.category)
      }
      const order = categoryOrder.value
      let sorted
      if (order.length) {
        // 分类锚点 id（cat-nav-N / cat-sec-N）都是按数组下标生成的，如果 order 里同一个分类
        // 出现了两次（商家后台保存过脏数据，或旧版本排序抽屉没做去重），这里再用 filter 不去重
        // 的话，categories 数组会带着重复项：indexOf(cat) 永远只会命中第一次出现的下标，
        // 点击排在后面的那个重名分类会跳到前面那个的位置——这正是点分类跳错、滚动时中间
        // 分类被跳过的根因，跟去重后 sidebar/正文两个 v-for 是否还共用同一份数组无关。
        const seen = new Set()
        sorted = order.filter(c => raw.includes(c) && !seen.has(c) && seen.add(c))
      } else {
        // 商家没配置分类顺序时，按点餐习惯给个默认顺序，而不是菜品在数据库里出现的原始
        // 顺序（等于商家后台录入顺序直接透传给顾客）；商家一旦自己配置过就完全尊重商家。
        sorted = [...raw].sort((a, b) => categoryOrderWeight(a) - categoryOrderWeight(b))
      }
      raw.forEach(c => { if (!sorted.includes(c)) sorted.push(c) })
      const hasRecommended = allDishes.value.some(d => {
        const tags = Array.isArray(d.tags) ? d.tags : String(d.tags || '').split(new RegExp('[,\\s\\uFF0C\\u3001]+')).map(t => t.trim()).filter(Boolean)
        return tags.includes('\u63a8\u8350') || tags.includes('\u62db\u724c') || tags.includes('\u70ed\u9500')
      })
      if (hasRecommended) sorted = [RECOMMEND_CAT, ...sorted.filter(c => c !== RECOMMEND_CAT)]
      return sorted
    })

    const normalizeCategoryText = (cat) => String(cat || '').trim()

    const categoryDisplayName = (cat) => {
      const text = normalizeCategoryText(cat)
      if (text === RECOMMEND_CAT) return RECOMMEND_CAT
      if (/\u62db\u724c|\u70ed\u9500|\u7279\u8272/.test(text)) return '\u62db\u724c'
      if (/\u6c64|\u7ca5|\u4f8b\u6c64/.test(text)) return '\u6c64\u54c1'
      if (/\u4e3b\u98df|\u7c73\u996d|\u7c73\u7ebf|\u9762|\u7c89|\u996d/.test(text)) return '\u4e3b\u98df'
      if (/\u996e|\u5976\u8336|\u5496\u5561|\u679c\u6c41|\u8336|\u9152/.test(text)) return '\u996e\u54c1'
      if (/\u70b9\u5fc3|\u8336\u70b9|\u751c\u54c1|\u5305\u5b50|\u997a\u5b50/.test(text)) return text.length > 3 ? '\u70b9\u5fc3' : text
      return text.length > 4 ? text.slice(0, 4) : text
    }

    const categoryIconClass = (cat) => {
      const text = normalizeCategoryText(cat)
      if (text === RECOMMEND_CAT) return 'icon-likefill'
      if (/\u62db\u724c|\u70ed\u9500|\u7279\u8272/.test(text)) return 'icon-xiaochao'
      if (/\u6c64|\u7ca5|\u4f8b\u6c64/.test(text)) return 'icon-zhou'
      if (/\u9762|\u7c89/.test(text)) return 'icon-mianshi'
      if (/\u4e3b\u98df|\u7c73\u996d|\u996d/.test(text)) return 'icon-mifan'
      if (/\u51b7\u996e|\u996e\u54c1|\u996e\u6599|\u679c\u6c41/.test(text)) return 'icon-lengyin'
      if (/\u70ed\u996e|\u5496\u5561|\u8336/.test(text)) return 'icon-reyin'
      if (/\u70b9\u5fc3|\u8336\u70b9/.test(text)) return 'icon-chadian'
      if (/\u5305\u5b50/.test(text)) return 'icon-baozi'
      if (/\u997a\u5b50/.test(text)) return 'icon-jiaozi'
      if (/\u751c\u54c1/.test(text)) return 'icon-tianpin'
      return 'icon-chadian'
    }

    // \u5546\u5bb6\u6ca1\u6709\u5728\u540e\u53f0\u624b\u52a8\u914d\u597d\u5206\u7c7b\u987a\u5e8f\u65f6\uff0c\u4e4b\u524d\u662f\u6309\u83dc\u54c1\u5728\u6570\u636e\u5e93\u91cc\u51fa\u73b0\u7684\u539f\u59cb\u987a\u5e8f\u6392\u5206\u7c7b
    // sidebar\u2014\u2014\u672c\u8d28\u4e0a\u662f\u5546\u5bb6\u540e\u53f0\u7684\u5f55\u5165\u987a\u5e8f\u76f4\u63a5\u900f\u4f20\u5230\u987e\u5ba2\u70b9\u9910\u754c\u9762\uff0c\u4e0d\u662f\u70b9\u9910\u4e60\u60ef\u7684\u987a\u5e8f\u3002
    // \u8fd9\u91cc\u7ed9\u51e0\u4e2a\u5e38\u89c1\u5f52\u4e00\u5316\u540e\u7684\u5206\u7c7b\u4e00\u4e2a\u9ed8\u8ba4\u6743\u91cd\uff0c\u547d\u4e2d\u4e0d\u4e86\u7684\u5206\u7c7b\uff08\u6743\u91cd99\uff09\u6392\u5728\u6700\u540e\uff0c
    // \u4e00\u65e6\u5546\u5bb6\u81ea\u5df1\u914d\u7f6e\u8fc7 category_order\uff0c\u8fd9\u4e2a\u9ed8\u8ba4\u6743\u91cd\u5b8c\u5168\u4e0d\u751f\u6548\uff0c\u4e0d\u8986\u76d6\u5546\u5bb6\u7684\u9009\u62e9\u3002
    const CATEGORY_DEFAULT_WEIGHT = { '\u62db\u724c': 1, '\u6c64\u54c1': 2, '\u4e3b\u98df': 3, '\u996e\u54c1': 4, '\u70b9\u5fc3': 5 }
    const categoryOrderWeight = (cat) => {
      if (normalizeCategoryText(cat) === RECOMMEND_CAT) return 0
      return CATEGORY_DEFAULT_WEIGHT[categoryDisplayName(cat)] ?? 99
    }

    const dishesByCategory = (cat) => {
      if (cat === RECOMMEND_CAT) {
        return allDishes.value.filter(d => {
          const tags = Array.isArray(d.tags) ? d.tags : String(d.tags || '').split(new RegExp('[,\\s\\uFF0C\\u3001]+')).map(t => t.trim()).filter(Boolean)
          return tags.includes('\u63a8\u8350') || tags.includes('\u62db\u724c') || tags.includes('\u70ed\u9500')
        })
      }
      return allDishes.value.filter((d) => d.category === cat)
    }

    // 存量菜品图片是商家直接传的原图（可能几MB），在服务端加处理管线之前上传的图都是这样，
    // 重新上传前没法改变已经存在 COS 上的文件本身。用 COS 万象缩略图参数在"读"的时候按需
    // 裁一份小图，不用等商家重新上传就能立刻覆盖全部存量图片；只对 http(s) 的 COS 图片链接
    // 生效，本地占位图/相对路径原样返回。size 是缩略图目标宽度（像素），列表小图和详情大图
    // 用不同的值，没必要都按详情图的尺寸下载。
    const withCosThumbnail = (url, size) => {
      if (!url || typeof url !== 'string' || !/^https?:\/\//i.test(url)) return url
      const sep = url.includes('?') ? '&' : '?'
      return `${url}${sep}imageMogr2/thumbnail/${size}x/format/webp`
    }

    const dishImage = (dish, size = 240) => withCosThumbnail(dish.image_url || dish.image || dish.cover_image || '', size)

    const dishTags = (dish) => {
      if (Array.isArray(dish.tags) && dish.tags.length) return dish.tags.slice(0, 3)
      if (typeof dish.tags === 'string' && dish.tags.trim()) {
        return dish.tags.split(new RegExp('[,\\s\\uFF0C\\u3001]+')).map(t => t.trim()).filter(Boolean).slice(0, 3)
      }
      return []
    }


    const strongDishTags = ['\u62db\u724c', '\u70ed\u9500', '\u5e97\u957f\u63a8\u8350', '\u65b0\u54c1']
    const normalizeDishTag = (tag) => {
      const text = String(tag || '').trim()
      if (['\u63a8\u8350', '\u5fc5\u70b9', '\u5fc5\u5403'].includes(text)) return '\u62db\u724c'
      if (text === '\u706b\u7206') return '\u70ed\u9500'
      return text
    }
    const isStrongDishTag = (tag) => tag === '\u5df2\u552e\u7f44' || strongDishTags.includes(tag)
    const dishCardTags = (dish) => {
      if (isSoldOut(dish)) return ['\u5df2\u552e\u7f44']
      const normalized = dishTags(dish).map(normalizeDishTag).filter(Boolean)
      for (const tag of strongDishTags) {
        if (normalized.includes(tag)) return [tag]
      }
      return []
    }
    const dishCardDesc = (dish) => {
      const desc = String(dish.desc || dish.description || '').trim()
      if (desc) return desc
      if (hasSpecs(dish)) return '\u591a\u89c4\u683c\u53ef\u9009'
      return ''
    }
    const showDishSales = (dish) => Number(dish.sales_count || 0) >= 10
    const isSoldOut = (dish) => dish.available === false || dish.sold_out === true || dish.is_sold_out === true || ['sold_out', 'soldout', 'unavailable'].includes(String(dish.status || '').toLowerCase()) || (dish.stock !== undefined && dish.stock !== null && dish.stock !== '' && Number(dish.stock) <= 0)
    const dishPriceBase = (dish) => Number(dish.min_price ?? dish.price_min ?? dish.price ?? 0)
    const dishPriceText = (dish) => formatPrice(dishPriceBase(dish))
    const dishPriceSuffix = (dish) => hasSpecs(dish) || Number(dish.max_price || dish.price_max || 0) > dishPriceBase(dish) ? '\u8d77' : ''

    const dishOriginalPrice = (dish) => dish.original_price || dish.market_price || ''

    const formatPrice = (val) => {
      const n = Number(val)
      if (isNaN(n)) return val
      return n % 1 === 0 ? String(n) : n.toFixed(2)
    }
    const hasSpecs = (dish) => {
      const tags = Array.isArray(dish.tags) ? dish.tags : String(dish.tags || '').split(new RegExp('[,\\s\\uFF0C\\u3001]+')).map(t => t.trim()).filter(Boolean)
      return !!dish.has_options || !!dish.hasOptions || tags.includes('\u591a\u89c4\u683c') || tags.includes('\u89c4\u683c') || (Array.isArray(dish.spec_groups) && dish.spec_groups.length > 0) || (Array.isArray(dish.specs) && dish.specs.length > 0) || (Array.isArray(dish.spec_options) && dish.spec_options.length > 0)
    }
    const specButtonText = (dish) => dish.option_button_text || dish.spec_button_text || (hasSpecs(dish) ? specText.chooseTaste : specText.chooseSpec)
    const dishOptionKindCount = (id) => specCartItems.value.filter(i => i.id === id).length
    const optionCountText = (id) => specText.selectedKinds + dishOptionKindCount(id) + specText.kindUnit

    const placeholderGradients = [
      'linear-gradient(135deg,#a8edea,#fed6e3)',
      'linear-gradient(135deg,#d4fc79,#96e6a1)',
      'linear-gradient(135deg,#ffecd2,#fcb69f)',
      'linear-gradient(135deg,#a1c4fd,#c2e9fb)',
      'linear-gradient(135deg,#fbc2eb,#a6c1ee)',
      'linear-gradient(135deg,#fddb92,#d1fdff)',
      'linear-gradient(135deg,#e0c3fc,#8ec5fc)',
      'linear-gradient(135deg,#f6d365,#fda085)',
    ]
    const homeRecommendedTags = ['\u62db\u724c', '\u70ed\u9500', '\u5e97\u957f\u63a8\u8350', '\u65b0\u54c1']
    const isMenuEmpty = computed(() => allDishes.value.length <= 0)
    const canStartOrdering = computed(() => !storeClosed.value && !isMenuEmpty.value)
    const homeStatusDesc = computed(() => {
      if (isMenuEmpty.value) return '\u6682\u65e0\u53ef\u70b9\u83dc\u54c1'
      return '\u5171' + allDishes.value.length + '\u9053\u83dc\u53ef\u70b9'
    })
    const homeOrderButtonText = computed(() => {
      if (storeClosed.value) return '\u95e8\u5e97\u4f11\u606f\u4e2d'
      if (isMenuEmpty.value) return '\u6682\u65e0\u83dc\u54c1'
      return '\u5f00\u59cb\u70b9\u9910'
    })
    const homeCouponHint = computed(() => {
      const count = Number(bannerInfo.value?.couponCount || 0)
      if (count <= 0) return ''
      return count + '\u5f20\u4f18\u60e0\u5238\u53ef\u7528'
    })
    const canHomeAdd = computed(() => !!featuredDish.value && !storeClosed.value && !isSoldOut(featuredDish.value))
    const featuredDish = computed(() => {
      if (isMenuEmpty.value) return null
      return allDishes.value.find(d => {
        if (isSoldOut(d)) return false
        const tags = dishTags(d).map(normalizeDishTag)
        return homeRecommendedTags.some(tag => tags.includes(normalizeDishTag(tag)))
      }) || null
    })
    const featuredDishTag = computed(() => {
      if (!featuredDish.value) return ''
      const tags = dishTags(featuredDish.value).map(normalizeDishTag)
      if (tags.includes('\u62db\u724c')) return '\u62db\u724c'
      if (tags.includes('\u70ed\u9500')) return '\u70ed\u9500'
      if (tags.includes('\u65b0\u54c1')) return '\u65b0\u54c1'
      return ''
    })
    const dishMatchesHistoryItem = (dish, item) => String(dish.id) === String(item.id || item.dish_id || item.menu_item_id || '') || dish.name === item.name
    const findHistoryDish = (item) => allDishes.value.find(d => dishMatchesHistoryItem(d, item))
    const historyItemHasSpecSnapshot = (item) => !!(item?.specKey || item?.specLabel || item?.specifications?.length || /[闂?]/.test(String(item?.name || "")))
    const validateHistoryReorderItem = (item) => {
      const dish = findHistoryDish(item)
      if (!dish || isSoldOut(dish)) return { dish, reason: 'unavailable' }
      if (hasSpecs(dish) || historyItemHasSpecSnapshot(item)) return { dish, reason: 'spec_changed' }
      return { dish, reason: '' }
    }
    const showHistoryReorderToast = ({ added = 0, skippedUnavailable = 0, skippedSpec = 0 }) => {
      if (added > 0) {
        let title = '已加入' + added + '件'
        if (skippedUnavailable > 0) title += '，部分菜品已下架或售罄'
        else if (skippedSpec > 0) title += '，部分规格已变更，请重新选择'
        uni.showToast({ title, icon: 'none', duration: 1400 })
        return
      }
      if (skippedUnavailable > 0) {
        uni.showToast({ title: '菜品已下架或售罄', icon: 'none', duration: 1400 })
        return
      }
      if (skippedSpec > 0) {
        uni.showToast({ title: '规格已变更，请重新选择', icon: 'none', duration: 1400 })
        return
      }
      uni.showToast({ title: '没有可重新加入的菜品', icon: 'none', duration: 1200 })
    }

    const lastOrderItems = computed(() => {
      const last = myOrders.value.find(o => !['cancelled', 'rejected'].includes(o.status))
      if (!last || !last.items) return []
      return last.items.slice(0, 6)
    })
    const homeLastOrderItems = computed(() => {
      if (isMenuEmpty.value) return []
      return lastOrderItems.value
        .map((item, index) => ({ ...item, dish: findHistoryDish(item), key: String(item.id || item.name || index) + '-' + index }))
        .filter(item => item.dish && !isSoldOut(item.dish))
        .slice(0, 4)
    })

    const handleHomeStartOrder = () => {
      if (!canStartOrdering.value) return
      activeTab.value = 'order'
    }
    const handleFeaturedAdd = () => {
      if (!canHomeAdd.value) return
      if (hasSpecs(featuredDish.value)) openSpecSheet(featuredDish.value)
      else addToCart(featuredDish.value)
    }
    const handleHomeReorderItem = (item) => {
      if (storeClosed.value) return
      const check = validateHistoryReorderItem(item)
      if (!check.dish || check.reason === 'unavailable') {
        uni.showToast({ title: '菜品已下架或售罄', icon: 'none', duration: 1200 })
        return
      }
      if (check.reason === 'spec_changed') {
        openSpecSheet(check.dish)
        uni.showToast({ title: '规格已变更，请重新选择', icon: 'none', duration: 1200 })
        return
      }
      addToCart(check.dish)
    }
    const handleHomeReorderAll = () => {
      if (storeClosed.value || !homeLastOrderItems.value.length) return
      let added = 0
      let skippedUnavailable = 0
      let skippedSpec = 0
      homeLastOrderItems.value.forEach(item => {
        const check = validateHistoryReorderItem(item)
        if (!check.dish || check.reason === 'unavailable') {
          skippedUnavailable += 1
          return
        }
        if (check.reason === 'spec_changed') {
          skippedSpec += 1
          return
        }
        addToCart(check.dish)
        added += 1
      })
      if (added > 0) uni.vibrateShort({ type: 'medium' })
      showHistoryReorderToast({ added, skippedUnavailable, skippedSpec })
    }

    const reorderItem = (item) => {
      const check = validateHistoryReorderItem(item)
      if (!check.dish || check.reason === 'unavailable') {
        uni.showToast({ title: '菜品已下架或售罄', icon: 'none', duration: 1200 })
        return
      }
      if (check.reason === 'spec_changed') {
        openSpecSheet(check.dish)
        uni.showToast({ title: '规格已变更，请重新选择', icon: 'none', duration: 1200 })
        return
      }
      addToCart(check.dish)
    }

    const reorderAll = () => {
      let added = 0
      let skippedUnavailable = 0
      let skippedSpec = 0
      lastOrderItems.value.forEach(item => {
        const check = validateHistoryReorderItem(item)
        if (!check.dish || check.reason === 'unavailable') {
          skippedUnavailable += 1
          return
        }
        if (check.reason === 'spec_changed') {
          skippedSpec += 1
          return
        }
        addToCart(check.dish)
        added++
      })
      if (added > 0) uni.vibrateShort({ type: 'medium' })
      showHistoryReorderToast({ added, skippedUnavailable, skippedSpec })
    }

    const isFeatured = (dish) => {
      const tags = dishTags(dish).map(normalizeDishTag)
      return tags.includes('\u62db\u724c') || tags.includes('\u70ed\u9500') || tags.includes('\u65b0\u54c1')
    }
    const dishPlaceholderStyle = (dish) => {
      const idx = (dish.name || '').charCodeAt(0) % placeholderGradients.length
      return { background: placeholderGradients[idx] }
    }

    const markDishImageFailed = (id) => {
      imageLoadFailed.value = { ...imageLoadFailed.value, [id]: true }
    }

    const cartCount = (id) => cart.value[id] || 0

    const openSpecSheet = (dish, existingItem = null) => {
      specDish.value = dish
      detailImageFailed.value = false
      specQty.value = existingItem?.qty || 1
      specStep.value = 4
      selectedSpecs.value = {}
      for (const g of normalizeSpecGroups(dish).filter(g => g.type !== 'checkbox' && g.type !== 'multiple' && g.type !== 'multi')) {
        const existingValue = existingItem?.specifications?.find(i => i.group === g.name)?.value
        if (existingValue) selectedSpecs.value[g.name] = [existingValue]
      }
      selectedExtras.value = existingItem?.extras ? [...existingItem.extras] : []
      itemRemark.value = existingItem?.itemRemark || ''
      showItemRemarkExtra.value = Boolean(itemRemarkExtra.value)
      showSpecSheet.value = true
    }

    const openProductDetail = (dish) => openSpecSheet(dish)

    const addToCart = (dish) => {
      if (isSoldOut(dish)) return
      if (hasSpecs(dish)) {
        openSpecSheet(dish)
        return
      }
      triggerAddPress(dish.id)
      cart.value = { ...cart.value, [dish.id]: (cart.value[dish.id] || 0) + 1 }
      triggerCartSuccessFeedback(dish.id)
      uni.vibrateShort({ type: 'light' })
    }

    const removeFromCart = (dish) => {
      if (dish.specKey) {
        const item = specCartItems.value.find(i => i.specKey === dish.specKey)
        if (!item) return
        if (item.qty <= 1) specCartItems.value = specCartItems.value.filter(i => i.specKey !== dish.specKey)
        else item.qty -= 1
        triggerCartValueFeedback(dish.specKey)
        return
      }
      const cur = cart.value[dish.id] || 0
      if (cur <= 1) {
        const next = { ...cart.value }
        delete next[dish.id]
        cart.value = next
      } else {
        cart.value = { ...cart.value, [dish.id]: cur - 1 }
      }
    triggerCartValueFeedback(dish.id)
    }

    const increaseCartItem = (item) => {
      if (item.specKey) {
        const target = specCartItems.value.find(i => i.specKey === item.specKey)
        if (target) {
          target.qty += 1
          triggerCartSuccessFeedback(item.specKey)
        }
        return
      }
      addToCart(item)
    }

    const clearCart = () => {
      cart.value = {}
      specCartItems.value = []
      showCart.value = false
    }

    const simpleCartItems = computed(() =>
      allDishes.value
        .filter((d) => cart.value[d.id] > 0)
        .map((d) => ({ ...d, qty: cart.value[d.id], specLabel: '' }))
    )

    const cartItems = computed(() => [...simpleCartItems.value, ...specCartItems.value])

    const totalCount = computed(() =>
      Object.values(cart.value).reduce((s, n) => s + n, 0) +
      specCartItems.value.reduce((s, i) => s + i.qty, 0)
    )

    const totalPrice = computed(() =>
      cartItems.value.reduce((s, item) => s + item.price * item.qty, 0)
    )
    const cartBadgeText = computed(() => totalCount.value > 99 ? '99+' : String(totalCount.value))

    const couponNudgeState = computed(() => buildCouponNudgeState({
      totalPrice: totalPrice.value,
      totalCount: totalCount.value,
      coupons: availableCoupons.value,
    }))

    const goCouponAddOn = () => {
      const preferred = categories.value.find(cat => /主食|米饭|饮|小菜|凉菜|点心|甜品/.test(String(cat)))
      const fallbackDish = allDishes.value
        .filter(dish => !isSoldOut(dish))
        .sort((a, b) => dishPriceBase(a) - dishPriceBase(b))[0]
      const target = preferred || fallbackDish?.category || categories.value[0]
      if (target) switchCategory(target)
    }
    const memberSavings = computed(() => {
      return cartItems.value.reduce((s, item) => {
        const dish = allDishes.value.find(d => d.id === item.id)
        if (dish && dish.member_price && dish.member_price < dish.price) {
          return s + (dish.price - dish.member_price) * item.qty
        }
        return s
      }, 0)
    })

    const dishScrollTopVal = ref(0)
    const categoryScrollTarget = ref('')
    const categoryScrollTop = ref(0)
    const categoryItemHeight = 108
    const categoryVisibleRows = 6
    let categoryVisibleStart = 0
    const syncCategoryVisible = (cat) => {
      const idx = categories.value.indexOf(cat)
      if (idx < 0) return
      const visibleEnd = categoryVisibleStart + categoryVisibleRows - 1
      if (idx >= categoryVisibleStart && idx <= visibleEnd) return
      categoryVisibleStart = Math.max(0, idx - 2)
      categoryScrollTop.value = categoryVisibleStart * categoryItemHeight
    }
    let ignoreScroll = false

    const switchCategory = (cat) => {
      activeCategory.value = cat
      ignoreScroll = true
      setTimeout(() => { ignoreScroll = false }, 600)
      const idx = categories.value.indexOf(cat)
      syncCategoryVisible(cat)
      scrollTarget.value = ''
      nextTick(() => { scrollTarget.value = 'cat-sec-' + idx })
    }


    // 之前的做法是缓存每个分类锚点的位置，滚动时拿当前 scrollTop 去跟缓存比对——问题是
    // 分类顺序会在页面加载过程中动态变化（商家配置的分类顺序是另一个跟菜单并行加载的
    // 请求，可能比菜单晚到），缓存跟真实布局之间必然存在时间差，这几轮修复下来一直在
    // 堵不同的时机漏洞，本身就说明"缓存一份随时可能过期的快照"这个思路跟"分类顺序会
    // 动态变化"这个前提是矛盾的。改成不缓存任何东西：每次滚动（节流后）都直接现场查一次
    // 真实的 DOM 布局，问到的永远是当下的真相，不存在"缓存没跟上"这类问题。
    let scrollThrottleTimer = null
    const onDishScroll = () => {
      if (ignoreScroll) return
      if (scrollThrottleTimer) return
      scrollThrottleTimer = setTimeout(() => {
        scrollThrottleTimer = null
        const cats = categories.value
        if (!cats.length) return
        const query = uni.createSelectorQuery()
        query.select('.dish-scroll').boundingClientRect()
        cats.forEach((_, i) => query.select('#cat-sec-' + i).boundingClientRect())
        query.exec((res) => {
          const svRect = res[0]
          if (!svRect || svRect.height <= 0) return
          let current = cats[0]
          for (let i = 0; i < cats.length; i++) {
            const r = res[i + 1]
            if (r && typeof r.top === 'number' && (r.top - svRect.top) <= 30) current = cats[i]
          }
          if (current !== activeCategory.value) {
            activeCategory.value = current
            syncCategoryVisible(current)
          }
        })
      }, 150)
    }

    const setupCategoryObserver = () => {}

    const switchOrderMode = (mode) => {
      if (mode === 'delivery') {
        uni.showToast({ title: '\u5916\u5356\u914d\u9001\u6b63\u5728\u5b8c\u5584\uff0c\u5f53\u524d\u5148\u652f\u6301\u5802\u98df\u70b9\u9910', icon: 'none' })
        return
      }
      orderMode.value = mode
    }

    const openCart = async () => {
      pendingSubmitRequestId.value = ''
      await loadShopSettings()
      showCart.value = true
      itemsExpanded.value = totalCount.value <= 1
      if (uni.getStorageSync('customer_token')) {
        try {
          const res = await getCustomerCoupons('UNUSED')
          const now = Date.now()
          const list = (res?.data || []).filter(c => new Date(c.expire_time || c.valid_end_time || '2099-01-01').getTime() > now)
          availableCoupons.value = list
          const eligible = list.filter(c => totalPrice.value >= Number(c.min_amount || c.threshold_amount || 0))
          const keepExistingChoice = selectedCouponId.value && eligible.some(c => c.id === selectedCouponId.value)
          if (!keepExistingChoice) {
            if (eligible.length) {
              eligible.sort(compareCouponPriority)
              selectedCouponId.value = eligible[0].id
            } else {
              selectedCouponId.value = null
            }
          }
        } catch {}
      }
    }

    const goCheckout = () => {
      if (ordering.value || paying.value || authorizing.value) return
      if (!canSubmitOrder.value) {
        uni.showToast({ title: tableSessionClosed.value ? '\u672c\u684c\u5df2\u7ed3\u675f\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u70b9\u9910' : (tableNo.value ? '\u5f53\u524d\u4e0d\u53ef\u4e0b\u5355' : '\u672a\u8bc6\u522b\u684c\u53f7\uff0c\u8bf7\u91cd\u65b0\u626b\u7801'), icon: 'none' })
        return
      }
      clearStalePrepayOrderForPayLater()
      if (pendingOrderId.value) return confirmPay()
      submitOrder()
    }

    const cancelCheckoutAuth = () => {
      if (authorizing.value) return
      showCheckoutAuth.value = false
    }

    const continuePendingPaymentIntent = async () => {
      clearStalePrepayOrderForPayLater()
      if (!pendingPaymentIntent.value && !pendingOrderId.value) pendingPaymentIntent.value = createPaymentIntent()
      if (pendingOrderId.value) return confirmPay()
      return submitOrder()
    }

    const handleCheckoutAuth = async (event) => {
      if (authorizing.value || ordering.value || paying.value) return
      const phoneCode = event?.detail?.code || event?.detail?.phoneCode || ''
      if (!phoneCode) return uni.showToast({ title: '\u672a\u5b8c\u6210\u6388\u6743\uff0c\u6682\u65f6\u65e0\u6cd5\u7ee7\u7eed\u652f\u4ed8', icon: 'none' })
      authorizing.value = true
      authActionStatus.value = 'authorizing'
      try {
        const code = await wxLogin()
        const res = await joinByEntranceCode({
          scene: uni.getStorageSync('entrance_scene') || '',
          tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
          table_no: tableNo.value || uni.getStorageSync('table_no') || '',
          code,
          phone_code: phoneCode,
          agreement_accepted: true,
          invite_code: uni.getStorageSync('invite_code') || '',
        }, { authRedirect: false })
        if (res.code !== 200) {
          authActionStatus.value = 'idle'
          uni.showToast({ title: res?.msg || '\u52a0\u5165\u4f1a\u5458\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5', icon: 'none', duration: 1200 })
          return
        }
        uni.removeStorageSync('invite_code')
        saveCustomerSession(res.data || {})
        await bindCurrentDiningParticipant()
        authActionStatus.value = 'submitting'
        const ok = await continuePendingPaymentIntent()
        if (ok) {
          pendingPaymentIntent.value = null
          showCheckoutAuth.value = false
        } else {
          authActionStatus.value = 'idle'
        }
      } catch (err) {
        authActionStatus.value = 'idle'
        uni.showToast({ title: err.message || '\u6388\u6743\u672a\u5b8c\u6210\uff0c\u8bf7\u91cd\u8bd5', icon: 'none' })
      } finally {
        authorizing.value = false
        if (!ordering.value && !paying.value && authActionStatus.value !== 'idle') authActionStatus.value = 'idle'
      }
    }

    // performSubmitOrder \u62c6\u51fa\u6765\u662f\u4e3a\u4e86\u8ba9"\u672c\u684c\u8eab\u4efd\u5931\u6548\uff0c\u91cd\u5efa\u540e\u81ea\u52a8\u91cd\u8bd5\u4e00\u6b21"\u8fd9\u6761\u8def\u5f84\u80fd
    // \u9012\u5f52\u8c03\u7528\u81ea\u5df1\u800c\u4e0d\u649e\u4e0a submitOrder \u81ea\u5df1\u7684 ordering.value \u91cd\u5165\u9501\uff08\u9501\u5728\u6574\u4e2a\u4e0b\u5355+\u652f\u4ed8
    // \u671f\u95f4\u4e00\u76f4\u662f true\uff0c\u9012\u5f52\u8c03\u7528\u5916\u5c42 submitOrder \u4f1a\u88ab\u8fd9\u628a\u9501\u76f4\u63a5\u6321\u56de\u6765\uff09\u3002
    const performSubmitOrder = async (isRetry = false) => {
      try {
        const sessionReady = await ensureDiningSession()
        if (!sessionReady || tableSessionClosed.value) throw new Error(tableSessionClosed.value ? '\u672c\u684c\u5df2\u7ed3\u675f\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u70b9\u9910' : '\u672c\u684c\u70b9\u9910\u4f1a\u8bdd\u4e0d\u53ef\u7528\uff0c\u8bf7\u91cd\u65b0\u626b\u7801')
        const payload = {
          table: tableNo.value,
          shop: shopId.value,
          total: totalPrice.value,
          remark: remark.value.trim() || undefined,
          coupon_id: selectedCouponId.value || undefined,
          dining_session_id: diningSessionId.value || undefined,
          participant_token: diningParticipantToken.value || undefined,
          client_id: diningClientId.value || undefined,
          request_id: ensureSubmitRequestId(),
          items: cartItems.value.map((item) => ({ dish_id: item.id, name: item.orderName || item.name, price: item.price, qty: item.qty, specifications: item.specifications && item.specifications.length ? item.specifications : undefined, extras: item.extras && item.extras.length ? item.extras : undefined })),
        }
        const res = await createOrder(payload, { authRedirect: false })
        const data = res?.data || {}
        pendingOrderId.value = String(data.id || data.order_id || '')
        paymentFailed.value = false
        orderNo.value = String(data.order_no || data.id || '').slice(-4)
        successItems.value = cartItems.value.map(i => ({ ...i }))
        successDiscount.value = Number(data.discount_amount ?? 0)
        payAmount.value = Number(data.pay_amount ?? data.total ?? finalPrice.value)
        paymentMode.value = normalizePaymentMode(data.payment_mode)
        if (!pendingOrderId.value) throw new Error('\u8ba2\u5355\u521b\u5efa\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5')
        if (data.need_payment !== false) {
          savePendingPaymentOrder()
          return await confirmPay()
        }
        _handlePaySuccess({ ...data, total: payAmount.value, status: data.status || 'pending' })
        pendingPaymentIntent.value = null
        return true
      } catch (err) {
        // \u672c\u684c\u533f\u540d\u8eab\u4efd\u5931\u6548\uff08\u540e\u7aef\u7edf\u4e00\u8fd4\u56de 409\uff09\u4e0d\u662f\u4f1a\u5458\u767b\u5f55\u95ee\u9898\uff0c\u9759\u9ed8\u91cd\u5efa\u8eab\u4efd\u540e\u81ea\u52a8\u91cd\u8bd5
        // \u4e00\u6b21\uff1b\u4ecd\u5931\u8d25\u624d\u8d70\u4e0b\u9762\u7684\u515c\u5e95\u63d0\u793a\uff0c\u4e0d\u4f1a\u5f39"\u7ee7\u7eed\u652f\u4ed8/\u6388\u6743"\u8fd9\u79cd\u4f1a\u5458\u4e13\u5c5e\u7684\u63aa\u8f9e\u3002
        if (!isRetry && isDiningIdentityError(err)) {
          const rebuilt = await ensureDiningSession(true)
          if (rebuilt) return performSubmitOrder(true)
        }
        if (isCheckoutAuthError(err)) {
          requireCheckoutAuth()
          return false
        }
        const rawMsg = err?.message || ''
        if (rawMsg.includes('\u4f1a\u8bdd') || rawMsg.includes('\u91cd\u65b0\u626b\u7801') || rawMsg.includes('\u672c\u684c')) tableSessionClosed.value = true
        const msg = rawMsg || '\u4e0b\u5355\u5931\u8d25\uff0c\u8bf7\u544a\u77e5\u670d\u52a1\u5458'
        uni.showToast({ title: String(msg).slice(0, 30), icon: 'none' })
        return false
      }
    }

    const submitOrder = async () => {
      if (ordering.value || paying.value) return false
      ordering.value = true
      if (showCheckoutAuth.value) authActionStatus.value = 'submitting'
      try {
        return await performSubmitOrder()
      } finally {
        ordering.value = false
      }
    }

    const _handlePaySuccess = (data) => {
      showCart.value = false
      orderId.value = pendingOrderId.value
      orderStatus.value = data.status || 'pending'
      successTotal.value = Number(data.total ?? payAmount.value)
      startStatusPoll(orderId.value)
      const now = new Date()
      const timeStr = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0')
      myOrders.value.unshift({
        id: orderId.value, orderNo: orderNo.value, status: orderStatus.value,
        paymentStatus: data.payment_status || '', paymentMode: normalizePaymentMode(data.payment_mode || paymentMode.value),
        diningSessionId: diningSessionId.value || '', tableSessionId: diningSessionId.value || '',
        items: successItems.value, total: successTotal.value, createdAt: timeStr,
        createdTs: now.getTime(), table: tableNo.value,
      })
      saveMyOrders()
      syncDiningOrders().catch(() => {})
      reminderRequested.value = false
      applyRewardCoupon(data.coupon || null)
      cart.value = {}
      specCartItems.value = []
      selectedCouponId.value = null
      remark.value = ''
      pendingSubmitRequestId.value = ''
      showSuccess.value = true
      clearPendingPaymentOrder()
    }

    // \u628a"\u540e\u7aef\u8fd4\u56de\u7684\u5956\u52b1\u5238"\u62d3\u6210 earnedCoupon \u7684\u5c55\u793a\u5f62\u72b6\uff1a\u6709\u771f\u5b9e\u5956\u52b1\u5238\u5c31\u7528\u5b83\uff0c
    // \u6ca1\u6709\uff08c \u4e3a null\uff09\u5219\u56de\u9000\u5230\u672c\u5730\u7f13\u5b58\u7684\u5165\u4f1a\u6b22\u8fce\u5238\uff0c\u514d\u5f97\u652f\u4ed8\u5b8c\u6210\u90a3\u4e00\u523b\u4ec0\u4e48\u90fd\u4e0d\u5c55\u793a\u3002
    const applyRewardCoupon = (c) => {
      if (c) {
        earnedCoupon.value = {
          couponId: c.id || '',
          amount: Number(c.value ?? c.amount ?? 0),
          threshold: Number(c.min_amount ?? c.threshold ?? 0),
          // \u540e\u7aef\u7ed9\u7684\u662f\u7edd\u5bf9\u8fc7\u671f\u65f6\u95f4 expired_at\uff0c\u4e0d\u662f\u76f8\u5bf9\u5929\u6570\uff0c
          // \u76f4\u63a5\u5b58\u6210 expire_time \u65b9\u4fbf\u590d\u7528\u4e0b\u9762\u7684 couponValidityText\u3002
          expire_time: c.expired_at || '',
          name: c.name || '\u4f18\u60e0\u5238',
          isSecondOrder: Boolean(c.is_second_order),
        }
        return true
      }
      const welcome = consumeWelcomeCoupon()
      earnedCoupon.value = welcome ? {
        couponId: welcome.id || '',
        amount: Number(welcome.amount ?? welcome.value ?? 0),
        threshold: Number(welcome.min_amount ?? welcome.threshold ?? 0),
        expire_time: welcome.expired_at || '',
        name: welcome.name || '\u65b0\u4eba\u4f18\u60e0\u5238',
      } : null
      return false
    }

    // \u771f\u5b9e\u5fae\u4fe1\u652f\u4ed8\u7684\u5956\u52b1\u5238\u662f\u5f02\u6b65\u53d1\u7684\uff08wxpay_notify \u56de\u8c03\u843d\u5e93\uff09\uff0c\u5ba2\u6237\u7aef requestPayment
    // \u521a\u6210\u529f\u90a3\u4e00\u523b\u540e\u7aef\u672a\u5fc5\u5df2\u7ecf\u5904\u7406\u5b8c\uff0c\u6240\u4ee5\u5148\u7528\u56de\u9000\u6587\u6848\u5c55\u793a\uff0c\u518d\u5728\u540e\u53f0\u77ed\u8f6e\u8be2 /orders/my
    // \u62ff\u5230\u771f\u5b9e\u53d1\u653e\u7684\u5956\u52b1\u5238\u540e\u8865\u4e0a\u53bb\u2014\u2014\u82e5\u7528\u6237\u5df2\u5173\u95ed\u6210\u529f\u9762\u677f\u6216\u5df2\u53bb\u770b\u5176\u4ed6\u8ba2\u5355\u5c31\u4e0d\u518d\u6539\u3002
    const attachPaymentReward = async (id) => {
      for (let attempt = 0; attempt < 6; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 900))
        try {
          const res = await getOrderStatus(id, diningParticipantToken.value)
          const d = res?.data || {}
          if (d.payment_status === 'paid') {
            if (showSuccess.value && orderId.value === id && d.reward_coupon) {
              applyRewardCoupon(d.reward_coupon)
            }
            return
          }
        } catch (e) { /* keep retrying */ }
      }
    }

    const confirmPay = async () => {
      if (paying.value || !pendingOrderId.value) return false
      paying.value = true
      paymentFailed.value = false
      try {
        if (await recoverPendingPaymentResult()) return true
        if (showCheckoutAuth.value) authActionStatus.value = 'paying'
        let jsCode = ''
        if (!uni.getStorageSync('customer_token')) {
          jsCode = await wxLogin()
        }
        const res = await createWxPayOrder(pendingOrderId.value, false, { authRedirect: false, js_code: jsCode, participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') })
        const data = res?.data || {}

        if (data.free) {
          _handlePaySuccess(data)
          pendingPaymentIntent.value = null
          return true
        }

        const p = data.pay_params
        if (!p) {
          throw new Error('\u652f\u4ed8\u53c2\u6570\u7f3a\u5931\uff0c\u8bf7\u91cd\u65b0\u4e0b\u5355')
        }

        await uni.requestPayment({
          provider: 'wxpay',
          timeStamp: p.timeStamp,
          nonceStr: p.nonceStr,
          package: p.package,
          signType: p.signType || 'RSA',
          paySign: p.paySign,
        })

        const paidOrderId = pendingOrderId.value
        _handlePaySuccess({ ...data, total: payAmount.value })
        pendingPaymentIntent.value = null
        // _handlePaySuccess 内部会清空 pendingOrderId，这里用支付前存下的 id 去轮询。
        attachPaymentReward(paidOrderId)
        return true

      } catch (err) {
        if (isCheckoutAuthError(err)) {
          requireCheckoutAuth()
          return false
        }
        if (await recoverPendingPaymentResult({ showDetail: true })) return true
        const msg = err?.errMsg || err?.message || '\u652f\u4ed8\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5'
        paymentFailed.value = true
        if (String(msg).includes('cancel')) {
          uni.showToast({ title: '\u5df2\u53d6\u6d88\u652f\u4ed8', icon: 'none' })
        } else {
          uni.showToast({ title: String(msg).slice(0, 30), icon: 'none' })
        }
        return false
      } finally {
        paying.value = false
      }
    }
    const resetOrder = () => {
      stopStatusPoll()
      cart.value = {}
      specCartItems.value = []
      remark.value = ''
      selectedCouponId.value = null
      earnedCoupon.value = null
      orderNo.value = ''
      orderId.value = ''
      orderStatus.value = data.status || 'pending'
      successItems.value = []
      successTotal.value = 0
      successDiscount.value = 0
      showSuccess.value = false
    }

    const clearCheckoutRequest = () => {
      if (!checkoutRequestedAt.value) return
      checkoutRequestedAt.value = ''
      requestTableCheckout({
        tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
        dining_session_id: tableSessionId.value,
        participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') || '',
        requested: false,
      }).catch(() => {})
    }

    const handleTableContinueOrder = async () => {
      if (!canContinueOrder.value) {
        uni.showToast({ title: '本桌账单已结束，不能继续加菜', icon: 'none' })
        return
      }
      if (!tableSessionId.value) {
        const ok = await ensureDiningSession(true)
        if (!ok) {
          uni.showToast({ title: '本桌点餐会话不可用，请重新扫码', icon: 'none' })
          return
        }
      }
      // 顾客决定继续加菜，说明这一桌暂时不结账了，之前呼叫服务员的请求就该撤销，
      // 不然等新点的菜也做完了，界面会立刻显示"已呼叫服务员"这种其实早就过期的状态。
      clearCheckoutRequest()
      persistDiningContext({
        dining_session_id: tableSessionId.value,
        participant_token: diningParticipantToken.value,
        client_id: diningClientId.value,
      })
      showOrders.value = false
      showSuccess.value = false
      activeTab.value = 'order'
    }

    const performTableCheckout = async (isRetry = false) => {
      try {
        // participant_token 有时会跟 session 状态不同步（比如缓存只留下了 session_id），
        // 后端校验不到身份会直接 409，先补一次 ensureDiningSession 把它修复回来，
        // 避免明明这一桌点单正常、结账却因为身份缺失而失败。
        if (!diningParticipantToken.value && !uni.getStorageSync('dining_participant_token')) {
          await ensureDiningSession()
        }
        const res = await requestTableCheckout({
          tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
          dining_session_id: tableSessionId.value,
          participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') || '',
          requested: true,
        }, { authRedirect: false })
        if (res?.code === 200) {
          checkoutRequestedAt.value = res.data?.checkout_requested_at || new Date().toISOString()
          uni.vibrateShort({ type: 'heavy' })
          uni.showToast({ title: '已通知服务员，请稍候为您结账', icon: 'none', duration: 2000 })
        } else {
          uni.showToast({ title: res?.msg || '呼叫失败，请重试', icon: 'none' })
        }
      } catch (e) {
        if (!isRetry && isDiningIdentityError(e)) {
          const rebuilt = await ensureDiningSession(true)
          if (rebuilt) return performTableCheckout(true)
        }
        uni.showToast({ title: '呼叫失败，请重试', icon: 'none' })
      }
    }

    const handleTableCheckout = async () => {
      if (tableCheckouting.value || checkoutRequested.value) return
      if (isTableSettled.value) {
        uni.showModal({
          title: '本桌已结账',
          content: '本次用餐账单已经结清，如需明细请联系服务员。',
          showCancel: false,
          confirmText: '知道了',
        })
        return
      }
      if (!tableSessionId.value) {
        uni.showToast({ title: '缺少桌台账单信息，请重新加载', icon: 'none' })
        return
      }
      tableCheckouting.value = true
      try {
        await performTableCheckout()
      } finally {
        tableCheckouting.value = false
      }
    }

    const goCoupons = () => {
      showSuccess.value = false
      uni.navigateTo({ url: '/subpkg-coupon/pages/list' })
    }

    const pickAvatarChar = (name) => {
      const chars = Array.from(String(name || '').trim())
      const ch = chars.find(c => /[一-龥a-zA-Z0-9]/.test(c))
      if (!ch) return '会'
      return /[a-z]/.test(ch) ? ch.toUpperCase() : ch
    }

    const loadMemberStatus = async (opts = {}) => {
      refreshCustomerAuthState()
      const token = uni.getStorageSync('customer_token')
      isCustomerLoggedIn.value = Boolean(token || uni.getStorageSync('customer_phone'))
      if (!token) {
        bannerInfo.value = null
        isMember.value = false
        return
      }
      if (memberLoading.value) return
      memberLoading.value = true
      try {
        const [profileRes, couponRes, growthRes] = await Promise.all([
          getMemberProfile({ authRedirect: opts.authRedirect !== false }),
          getCustomerCoupons('UNUSED', { authRedirect: opts.authRedirect !== false }).catch(() => null),
          getMembershipGrowth().catch(() => null),
        ])
        if (profileRes?.code === 200 && profileRes?.data) {
          const p = profileRes.data
          const g = growthRes?.code === 200 ? (growthRes.data || {}) : {}
          isMember.value = !!(p.membership_level || p.is_member || p.member_card || p.membership_expire_at || p.level)
          const coupons = Array.isArray(couponRes?.data) ? couponRes.data : []
          availableCoupons.value = coupons
          bannerInfo.value = {
            nameChar: pickAvatarChar(p.name),
            avatar: p.avatar || p.avatar_url || p.headimgurl || '',
            memberNo: p.store_member_no ? String(p.store_member_no).padStart(6, '0') : '',
            levelLabel: p.level || p.membership_level || '\u666e\u901a\u4f1a\u5458',
            levelCode: p.level_code || g.level_code || 'LV1',
            couponCount: coupons.length,
            coupons,
            points: Number(p.points || 0),
            // \u8fd9\u4e09\u4e2a\u5b57\u6bb5\u4e4b\u524d\u4ece\u672a\u88ab /v1/member/profile \u586b\u8fc7\uff0c
            // \u8fdb\u5ea6\u6761\u6c38\u8fdc\u4e0d\u6e32\u67d3\uff0c\u73b0\u5728\u6539\u4ece\u4e0e growth.vue \u540c\u4e00\u4e2a
            // /v1/member/membership \u53d6\u6570\uff0c\u907f\u514d\u4e24\u5904\u5404\u7b97\u4e00\u5957\u5bf9\u4e0d\u4e0a\u53f7\u3002
            growth: Number(g.yearly_consumption || 0),
            nextGrowth: Number(g.next_level?.threshold || 0),
            nextUpgradeAmount: Math.max(0, Number(g.next_level?.threshold || 0) - Number(g.yearly_consumption || 0)),
          }
        }
      } catch { }
      finally { memberLoading.value = false }
    }

    const entryCoupon = ref(null)   // { coupon_id, amount, threshold, expire_time }
    const couponReminderTemplateId = ref('')   // 空字符串表示还没配置订阅消息模板，"提醒我"按钮不显示
    const newCustomerCouponPreview = ref(null)   // { name, amount, min_amount, valid_days }，未登录也能看到的首单钩子数字
    // 首单钩子文案：登录按钮、会员Tab、点餐页顶部三处统一读这一个 computed，
    // 保证顾客登录前看到的数字和登录后弹出的"新人券"数字对得上，不会各写各的。
    const newCustomerHookText = computed(() => {
      const p = newCustomerCouponPreview.value
      if (!p || !(p.amount > 0)) return '登录解锁会员专属优惠'
      const amount = formatPrice(p.amount)
      const min = Number(p.min_amount || 0)
      return min > 0 ? `新客立减¥${amount}，满${min.toFixed(0)}元可用` : `新客立减¥${amount}，授权手机号立得`
    })

    const loadShopSettings = async () => {
      if (!shopId.value) return
      try {
        const res = await getShopInfo(shopId.value)
        if (res?.code === 200 && res?.data) {
          const d = res.data
          deliveryEnabled.value = !!d.delivery_enabled
          paymentMode.value = normalizePaymentMode(d.payment_mode)
          shopCreatedAt.value = d.created_at || d.create_time || d.createdAt || d.register_time || ''
          const realShopName = d.name || d.shop_name || d.tenant_name || ''
          if (realShopName) {
            shopName.value = realShopName
            uni.setStorageSync('tenant_name', realShopName)
            uni.setNavigationBarTitle({ title: realShopName + ' \u70b9\u9910' })
          }
          shopLogo.value = d.logo || d.logo_url || ''
          if (Array.isArray(d.remark_chips) && d.remark_chips.length) {
            remarkChips.value = d.remark_chips
          }
          if (Array.isArray(d.order_remark_chips) && d.order_remark_chips.length) {
            orderRemarkChips.value = d.order_remark_chips
          }
          if (Array.isArray(d.category_order) && d.category_order.length) {
            categoryOrder.value = d.category_order
          }
          if (d.entry_coupon?.coupon_id) {
            entryCoupon.value = d.entry_coupon
            // is_new 是后端算好的"这张是不是这次调用才发的"——同一天重复进店只会拿到
            // 同一张已发过的进店券（is_new:false），不重复提示，只在真正新发时提醒一次，
            // 不然这张后端已经在默默发放的券，顾客永远不知道自己刚刚薅到了。
            if (d.entry_coupon.is_new) {
              uni.showToast({
                title: `已发放进店券 ¥${formatPrice(d.entry_coupon.amount)}，满${Number(d.entry_coupon.threshold || 0).toFixed(0)}元可用`,
                icon: 'none',
                duration: 3000,
              })
            }
          }
          newCustomerCouponPreview.value = d.new_customer_coupon_preview || null
          couponReminderTemplateId.value = d.coupon_reminder_template_id || ''
          if (d.is_open === false) {
            storeClosed.value = true
            closedNotice.value = d.closed_notice || d.business_hours || ''
          } else {
            storeClosed.value = false
          }
          if (d.lat && d.lng) loadDistance(d.lat, d.lng)
        }
      } catch (e) {
        console.warn('[loadShopSettings] failed', e)
      }
    }

    const loadMenu = async () => {
      loading.value = true
      loadError.value = false
      try {
        const res = await getMenuItems(shopId.value)
        if (res?.code !== 200) {
          loadError.value = true
          allDishes.value = []
          return
        }
        const items = res?.data?.items || res?.data || []
        allDishes.value = Array.isArray(items) ? items.map(d => ({ ...d, desc: d.desc || d.description || '' })) : []
      } catch {
        loadError.value = true
        allDishes.value = []
      } finally {
        loading.value = false
        if (categories.value.length) activeCategory.value = categories.value[0]
      }
    }


    watch(cartItems, () => {
      if (showCart.value && totalCount.value <= 0) showCart.value = false
      resetPendingPayment()
    }, { deep: true })
    watch([selectedCouponId, remark], resetPendingPayment)

    return {
      tableNo, shopId, shopName, shopLogo, memberSinceText, tableDisplayText, orderModeDisplayText, showTableHint, todayActivity, orderMode, orderModeText, confirmationText, confirmPaymentLabel, authAmountLabel, successText, specText,
      loading, loadError, ordering, showCart, showSuccess, earnedCoupon, itemsExpanded, toggleItemsExpanded, closeOrderConfirm,
      couponReminderTemplateId, reminderRequested, requestingReminder, requestCouponReminder,
      showWelcomeCoupon, welcomeCouponData, welcomeCouponCondText, checkWelcomeCoupon, closeWelcomeCoupon, goOrderFromWelcomeCoupon,
      showCheckoutAuth, authorizing, authSheetText, authPrimaryText, handleCheckoutAuth, cancelCheckoutAuth,
      paying, payAmount, confirmPay,
      orderId, orderNo, orderStatus, orderStatusText, successStatusText, successStatusTone, successOrderItemCount, successOrderNo, orderStatusClass, merchantNote,
      startStatusPoll, stopStatusPoll, startTablePresencePoll, stopTablePresencePoll,
      remark, remarkChips, toggleRemarkChip, orderRemarkChips, showOrderRemarkExtra, orderRemarkExtra,
      availableCoupons, selectedCouponId, selectedCoupon, discountAmount, finalPrice,
      showCouponPicker, couponPickerList, couponPickerAmount, couponPickerCondText, openCouponPicker, closeCouponPicker, pickCoupon,
      couponBarVisible, bestCouponValue, couponBarText, couponBarPrefix, couponBarAmount, couponNudgeState, goCouponAddOn,
      openCart,
      activeCategory, scrollTarget, categoryScrollTarget, categoryScrollTop, dishScrollTopVal, allDishes, cart, addPressKey, qtyPulseKey, cartIconPulse, cartBadgePulse, amountPulse,
      successItems, successTotal,
      categories, categoryDisplayName, categoryIconClass, dishesByCategory, dishImage, dishTags, dishCardTags, isStrongDishTag, dishCardDesc, showDishSales, isSoldOut, dishPriceText, dishPriceSuffix, dishOriginalPrice, hasSpecs, formatPrice,
      imageLoadFailed, detailImageFailed, markDishImageFailed, openProductDetail,
      cartCount, addToCart, removeFromCart, increaseCartItem, clearCart, specButtonText, dishOptionKindCount, optionCountText, openSpecSheet,
      cartItems, totalCount, totalPrice, cartBadgeText,
      switchCategory, switchOrderMode,
      goCheckout, resetOrder, finishOrdering, closeSuccessAndWait, continueOrdering, viewOrderDetail, goCoupons, loadMenu,
      myOrders, showOrders, showAllOrders, pendingOrderCount, statusLabel, doCancelOrder,
      isTableAccountMode, isPostpayMode, isSharedBillMode, sharedBillSubLabel, tableSessionId, tableOrderGroups, tableTotal, tableItemCount, tableStatusView, isTableSettled, canContinueOrder, canCheckout, postpayReadyToSettle, stillPreparing, checkoutRequested, tableCheckouting, handleTableContinueOrder, handleTableCheckout,
      tableAccountScrollInto, scrollTableAccountToTop,
      currentTableOrder, historyTableOrders, currentTableOrderStatus, tableOrderStatusTone, tableOrderStatusIcon, tableOrderStatusBadge, tableOrderNextAction, tableOrderProgressSub, tableOrderPrimaryButtonText, tableOrderStatusTitle, tableOrderStatusHint, tableOrderTimeline, orderItemCount, currentOrderItemCount, currentOrderItems, currentOrderMainItemText,
      orderItemName, orderItemQty, orderItemAmount, orderItemSpecText, orderItemImage, orderItemImageFailed, markOrderItemImageFailed,
      saveMyOrders, loadMyOrders, refreshAllOrderStatuses, ensureDiningSession, syncDiningOrders,
      savePendingPaymentOrder, restorePendingPaymentOrder, clearPendingPaymentOrder, recoverPendingPaymentResult,
      availableCoupons, selectedCouponId, selectedCoupon, discountAmount, finalPrice,
      successDiscount, wechatPayAmount, canSubmitOrder, payButtonText,
      storeClosed, closedNotice, tableSessionClosed, tableSessionClosedNotice, isMember, memberSavings, bannerInfo, memberAuthorizing, memberLoading, isCustomerLoggedIn, hasCustomerIdentity,
      activeTab, shopDistance, switchToCard, goMine,
      memberLevelLabel, memberLevelBadgeSrc, memberProgressPercent, memberUpgradeText, usableMemberCoupons, couponAmountText, couponConditionText, couponValidityText, goOrderFromMember, handleMemberCardAuth, useMemberCoupon,
      homeStatusDesc, homeOrderButtonText, homeCouponHint, canStartOrdering, featuredDish, featuredDishTag, canHomeAdd, homeLastOrderItems,
      handleHomeStartOrder, handleFeaturedAdd, handleHomeReorderItem, handleHomeReorderAll,
      loadMemberStatus, refreshCustomerAuthState, loadShopSettings,
      deliveryEnabled, entryCoupon, newCustomerCouponPreview, newCustomerHookText,
      showSpecSheet, specDish, specQty, selectedSpecs, specTotalPrice,
      isSpecSelected, toggleSpec, toggleExtra, cancelSpec, handleSpecPrimary, confirmSpec, specCartItems, specStep, specSteps, specRadioGroups, specExtraOptions, filteredRemarkChips, selectedExtras, itemRemark, showItemRemarkExtra, toggleItemRemarkChip, selectedSpecSummary, specBasePrice, specDishDesc, canGoNextSpec, specPrimaryText,
      isFeatured, dishPlaceholderStyle,
      lastOrderItems, reorderItem, reorderAll,
      setupCategoryObserver, onDishScroll,
    }
  },

  onLoad: function (options) {
    return (async () => {
      this.tableNo = options.table || 'A01'
      this.shopId = options.shop || uni.getStorageSync('tenant_id') || ''
      if (options.activity) this.todayActivity = decodeURIComponent(options.activity)
      uni.setNavigationBarTitle({ title: this.shopName + ' \u70b9\u9910' })
      this.loadMyOrders()
      this.restorePendingPaymentOrder()
      this.refreshCustomerAuthState()
      this.loadMemberStatus({ authRedirect: false })

      // \u83dc\u5355\u80fd\u4e0d\u80fd\u663e\u793a\u53ea\u53d6\u51b3\u4e8e shopId\uff08\u4e0a\u9762\u5df2\u7ecf\u540c\u6b65\u8bbe\u597d\uff09\uff0c\u8ddf\u672c\u684c\u8eab\u4efd/\u684c\u53f0\u8ba2\u5355/
      // \u5f85\u652f\u4ed8\u6062\u590d\u5b8c\u5168\u65e0\u5173\u2014\u2014\u8fd9\u6761\u94fe\u548c\u4e0b\u9762\u90a3\u6761"\u8eab\u4efd\u2192\u684c\u53f0\u540c\u6b65\u2192\u5f85\u652f\u4ed8\u6062\u590d"\u7684\u94fe\u8def
      // \u5e76\u884c\u8dd1\uff0c\u4e0d\u518d\u8ba9\u83dc\u5355\u7b49\u4e00\u4e2a\u8ddf\u5b83\u65e0\u5173\u7684\u94fe\u8def\u3002
      // loadShopSettings（门店信息/分类顺序）和 loadMenu（菜品列表）互不依赖对方的返回
      // 数据，之前写成先后 await 纯粹是顺序问题——两者互相独立就应该并行发起，少等一次
      // 网络往返。
      const menuReady = Promise.all([this.loadShopSettings(), this.loadMenu()])

      const sessionReady = (async () => {
        // entry \u9875\u626b\u7801\u8fdb\u6765\u65f6\u5df2\u7ecf\u5f3a\u5236\u5237\u65b0\u8fc7\u4e00\u6b21\u8eab\u4efd\u5e76\u5199\u8fdb\u672c\u5730\u7f13\u5b58\uff08resolveTableSession
        // \u91cc\u7684 force:true\uff09\uff0c\u8fd9\u91cc\u4e0d\u518d\u4f20 force\u2014\u2014ensureDiningSession \u5185\u90e8\u7684
        // resolveDiningIdentity \u4f1a\u81ea\u5df1\u5224\u65ad\u7f13\u5b58\u662f\u5426\u53ef\u4fe1\uff08\u684c\u53f7\u5bf9\u4e0d\u5bf9\u5f97\u4e0a\u3001\u6709\u6ca1\u6709
        // session/token\uff09\uff0c\u7f13\u5b58\u4e0d\u53ef\u4fe1\u65f6\u4f9d\u7136\u4f1a\u81ea\u52a8\u53d1\u771f\u5b9e\u8bf7\u6c42\uff0c\u4e0d\u4f1a\u5e26\u7740\u8fc7\u671f\u8eab\u4efd"\u88f8\u5954"\uff0c
        // \u4f46\u53ef\u4fe1\u65f6\u5c31\u7701\u6389\u4e00\u6b21\u53c2\u6570\u5b8c\u5168\u76f8\u540c\u7684\u91cd\u590d\u7f51\u7edc\u5f80\u8fd4\u3002
        await this.ensureDiningSession(false)
        await this.syncDiningOrders()
        this.startTablePresencePoll()
        await this.recoverPendingPaymentResult({ showDetail: options.openOrders === '1' })
        if (options.openOrders === '1') this.showOrders = true
      })()

      await Promise.all([menuReady, sessionReady])
    })()
  },
  onShow() {
    const focusTab = uni.getStorageSync('menu_focus_tab')
    if (focusTab) {
      this.activeTab = focusTab
      uni.removeStorageSync('menu_focus_tab')
    }
    if (this.refreshCustomerAuthState) this.refreshCustomerAuthState()
    if (this.recoverPendingPaymentResult) this.recoverPendingPaymentResult()
    if (this.activeTab === 'card' || uni.getStorageSync('customer_token') || uni.getStorageSync('customer_phone')) {
      this.loadMemberStatus({ authRedirect: false })
    }
    if (this.orderId && !['settled', 'cancelled', 'rejected'].includes(this.orderStatus)) {
      this.startStatusPoll(this.orderId)
    }
    this.startTablePresencePoll()
  },
  onHide: function () {
    this.stopStatusPoll()
    this.stopTablePresencePoll()
  },
  onUnload: function () {
    this.stopStatusPoll()
    this.stopTablePresencePoll()
    if (this.setupCategoryObserver) {

    }
  },
}
</script>

<style lang="scss">
.order-page {
  height: 100vh;
  overflow: hidden;
  background: #f5f6fa;
  display: flex;
  flex-direction: column;
}


.shop-header {
  position: relative;
  height: calc(220rpx + env(safe-area-inset-top));
  min-height: calc(220rpx + env(safe-area-inset-top));
  max-height: calc(220rpx + env(safe-area-inset-top));
  background: var(--brand) url('/static/order/shop-cover-default.jpg') right bottom / cover no-repeat;
  padding: calc(28rpx + env(safe-area-inset-top)) 32rpx 24rpx;
  box-sizing: border-box;
  overflow: hidden;
}

/* 门店封面图目前是通用素材，不分商户；等 admin-h5 有了真正的封面上传入口，
   这层叠加渐变可以继续用，只需要把 url() 换成商户自己的封面图。
   background-position 用 right bottom：这张图的餐桌/菜品在右下方，居中裁剪
   会把菜品裁掉一截、只剩空景。
   这张图本身左侧就是渐变到浅色的留白（跟首页"立即点餐"卡片同一张风格的图），
   之前又在上面叠了一层深绿色遮罩、文字还留白色——两层"提亮对比度"的手段叠加，
   把照片本身糊成一片。首页卡片那次是对的做法：不加遮罩，直接把文字换成深色，
   这里改成同一个做法，照片才能透出来，不然然会一直"雾蒙蒙"。 */

.shop-header-row {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 18rpx;
  height: 100%;
  max-width: calc(100vw - 220rpx);
  box-sizing: border-box;
}

.shop-logo {
  width: 80rpx;
  height: 80rpx;
  border-radius: 50%;
  flex-shrink: 0;
  border: 2rpx solid rgba(255,255,255,0.65);
  background: rgba(255,255,255,0.15);
}

.shop-title-main {
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
}

.shop-name {
  display: block;
  width: 100%;
  box-sizing: border-box;
  color: #2b1c0f;
  font-size: 36rpx;
  font-weight: 600;
  line-height: 50rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shop-meta-row {
  min-height: 72rpx;
  margin-top: 4rpx;
  display: flex;
  align-items: center;
  width: fit-content;
  max-width: 100%;
  box-sizing: border-box;
}

.shop-table-text {
  color: #2b1c0f;
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 600;
  white-space: nowrap;
}

.shop-meta-dot {
  margin: 0 10rpx;
  color: rgba(58,38,18,0.6);
  font-size: 28rpx;
  line-height: 40rpx;
}

.shop-mode-text {
  color: rgba(58,38,18,0.78);
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 500;
  white-space: nowrap;
}

.shop-meta-arrow {
  margin-left: 10rpx;
  color: rgba(58,38,18,0.55);
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 500;
}

.shop-name-row,
.mode-pill,
.mode-pill--muted,
.activity-bar,
.activity-text,
.shop-meta { display: none; }

.coupon-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10rpx;
  height: 68rpx;
  padding: 0 32rpx;
  background: linear-gradient(90deg, #fdf0dc, #fbe4bf);
  box-sizing: border-box;
}

.coupon-bar-icon {
  font-size: 26rpx;
  line-height: 1;
  color: #b5691f;
}

.coupon-bar-text {
  flex: 1;
  min-width: 0;
  font-size: 24rpx;
  font-weight: 700;
  color: #5a3c1e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coupon-bar-amount {
  color: #e0432a;
  font-weight: 800;
}

.coupon-bar-arrow {
  flex-shrink: 0;
  color: rgba(90, 60, 30, 0.55);
  font-size: 24rpx;
  line-height: 1;
}

.new-customer-bar {
  width: 100%;
  margin: 0;
  border: 0;
  border-radius: 0;
  line-height: normal;
}
.new-customer-bar::after { border: none; }
.new-customer-bar[disabled] { opacity: .7; }


.menu-body {
  display: flex;
  flex: 1;
  width: 100%;
  min-width: 0;
  /* 不能设 overflow:hidden——小程序的渲染引擎会把 overflow:hidden 祖先当成"裁剪边界"，
     连它里面 position:fixed 的弹层（确认订单、优惠券选择等）也一起裁掉，跟标准浏览器里
     position:fixed 应该完全无视祖先 overflow 裁剪的行为不一样。这些弹层要铺满到屏幕最
     底部，一旦被 menu-body 自己的高度边界裁掉，最下面的按钮就会看不见（这次反馈的问题）。
     侧栏分类和菜品列表各自已经自己声明了 overflow-y:auto，靠的是 min-height:0 这个
     flex 属性让它们在受限布局里能正常滚动，不依赖 menu-body 自己的 overflow，去掉它
     不影响任何滚动区域。 */
  overflow: visible;
  min-height: 0;
}

.category-nav {
  width: 168rpx;
  flex: 0 0 168rpx;
  background: #F6F7F8;
  overflow-x: hidden;
  overflow-y: auto;
  box-sizing: border-box;
}

.cat-item {
  position: relative;
  height: 108rpx;
  min-height: 108rpx;
  padding: 12rpx 10rpx 10rpx 14rpx;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6rpx;
  text-align: center;
  color: #6F7680;
  background: transparent;
}

.cat-icon-wrap {
  width: 42rpx;
  height: 42rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  flex-shrink: 0;
}

.cat-icon {
  color: #9CA3AF;
  font-size: 32rpx;
  line-height: 36rpx;
}

.cat-name {
  max-width: 124rpx;
  font-size: 24rpx;
  line-height: 30rpx;
  font-weight: 600;
  color: #6F7680;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cat-item.active {
  background: #fff;
}

.cat-item.active .cat-icon-wrap {
  background: var(--brand-light);
}

.cat-item.active .cat-icon,
.cat-item.active .cat-name {
  color: var(--brand);
}

.cat-item.active .cat-name {
  font-weight: 800;
}

.cat-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 6rpx;
  height: 52rpx;
  border-radius: 0 4rpx 4rpx 0;
  background: var(--brand);
}

.dish-scroll {
  flex: 1;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--bg-page);
  padding: 0;
  box-sizing: border-box;
}

.cat-divider {
  height: 64rpx;
  padding: 0 24rpx;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}
.cat-divider-line {
  flex: 1;
  max-width: 160rpx;
  height: 1rpx;
  background: #E7E9EC;
}
.cat-divider-main {
  margin: 0 18rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  min-width: 0;
}

.cat-divider-icon {
  flex-shrink: 0;
  font-size: 28rpx;
  line-height: 32rpx;
  color: var(--brand);
}

.cat-divider-text {
  max-width: 168rpx;
  font-size: 26rpx;
  color: var(--text-3);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0;
}

.cat-title {
  display: block;
  padding: 24rpx 0 16rpx;
  font-size: 24rpx;
  font-weight: 700;
  color: var(--text-3);
}

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
.dish-emoji-wrap, .dish-emoji, .dish-initial, .dish-badge-top { display: none; }


.reorder-bar {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin: 16rpx 20rpx 12rpx;
  padding: 16rpx 20rpx;
  border-radius: 20rpx;
  background: #fff;
  box-shadow: var(--card-shadow);
  box-sizing: border-box;
}

.reorder-label {
  font-size: 22rpx;
  color: var(--text-3);
  white-space: nowrap;
  flex-shrink: 0;
}

.reorder-scroll {
  flex: 1;
  white-space: nowrap;
}

.reorder-chips {
  display: flex;
  gap: 10rpx;
}

.reorder-chip {
  display: inline-flex;
  align-items: center;
  gap: 6rpx;
  padding: 8rpx 16rpx;
  border-radius: 32rpx;
  border: 1rpx solid var(--brand);
  background: #f0fdf4;
  flex-shrink: 0;
}

.reorder-chip-name {
  font-size: 22rpx;
  color: #065f46;
  max-width: 120rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reorder-chip-add {
  font-size: 24rpx;
  color: var(--brand);
  font-weight: 800;
  line-height: 1;
}

.reorder-all-btn {
  flex-shrink: 0;
  background: var(--brand);
  border-radius: 28rpx;
  padding: 6rpx 18rpx;
}

.reorder-all-text {
  font-size: 22rpx;
  color: #fff;
  font-weight: 700;
  white-space: nowrap;
}


.dish-save-badge {
  font-size: 18rpx;
  color: #fff;
  background: #f97316;
  border-radius: 6rpx;
  padding: 2rpx 8rpx;
  font-weight: 700;
  margin-left: 4rpx;
}


.member-hint-bar {
  margin: 8rpx 0 0;
  background: linear-gradient(90deg, #fff7ed, #fef3c7);
  border-radius: 12rpx;
  padding: 14rpx 20rpx;
  border-left: 4rpx solid var(--warning);
}

.member-hint-text {
  font-size: 24rpx;
  color: #92400e;
  font-weight: 600;
}


.order-saved-bar {
  background: linear-gradient(90deg, #ecfdf5, #d1fae5);
  border-radius: 12rpx;
  padding: 14rpx 20rpx;
  margin: 0 0 12rpx;
  text-align: center;
}

.order-saved-text {
  font-size: 26rpx;
  color: #065f46;
  font-weight: 700;
}


.dish-info { flex: 1; min-width: 0; display: flex; flex-direction: column; margin-left: 18rpx; box-sizing: border-box; overflow: hidden; }
.dish-title-row { display: flex; align-items: flex-start; gap: 8rpx; min-width: 0; }
.dish-name { flex: 1; min-width: 0; font-size: 32rpx; font-weight: 600; line-height: 44rpx; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-tags { display: flex; flex-shrink: 0; flex-wrap: nowrap; max-width: 88rpx; overflow: hidden; }
.dish-tag { max-width: 88rpx; height: 34rpx; padding: 0 8rpx; border-radius: 8rpx; box-sizing: border-box; font-size: 20rpx; font-weight: 500; line-height: 34rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-tag--strong { color: #078546; background: #e9f9f0; }
.dish-tag--plain { display: none; }
.dish-meta { flex: 1; min-width: 0; min-height: 0; padding-top: 6rpx; }
.dish-desc { display: block; min-width: 0; font-size: 26rpx; color: var(--text-3); line-height: 36rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-sales { display: block; min-width: 0; margin-top: 2rpx; margin-left: 0; font-size: 24rpx; line-height: 34rpx; color: #A8ADB4; font-weight: 400; }
.dish-bottom-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 0; margin-top: auto; min-width: 0; }
.dish-price-wrap { flex: 1; min-width: 104rpx; overflow: hidden; display: flex; align-items: baseline; color: var(--brand); }
.dish-price-currency { flex-shrink: 0; font-size: 24rpx; font-weight: 700; line-height: 1; }
.dish-price-amount { min-width: 0; font-size: 40rpx; font-weight: 700; line-height: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-price-suffix { flex-shrink: 0; margin-left: 2rpx; font-size: 22rpx; font-weight: 500; line-height: 1; color: var(--brand); }
.dish-origin-price, .dish-save-badge, .member-price { display: none; }
.dish-counter { flex: none; display: flex; align-items: center; justify-content: flex-end; flex-shrink: 0; margin-left: 6rpx; min-width: 60rpx; max-width: 176rpx; padding-right: 0; box-sizing: border-box; }
.dish-qty-control { width: 164rpx; max-width: 164rpx; height: 58rpx; padding: 4rpx; display: flex; align-items: center; justify-content: space-between; gap: 0; overflow: hidden; flex-shrink: 0; box-sizing: border-box; border-radius: 29rpx; background: #F3F4F6; }
.counter-touch { width: 72rpx; height: 72rpx; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; }
.dish-qty-control .counter-touch { width: 50rpx; height: 50rpx; }
.dish-counter > .counter-touch { width: 76rpx; height: 76rpx; }
.dish-counter .counter-btn { width: 60rpx; height: 60rpx; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-sizing: border-box; flex-shrink: 0; }
.dish-qty-control .counter-btn { width: 50rpx; height: 50rpx; }
.dish-qty-control .counter-btn--pressing { animation: none; transform: none; }
.dish-counter .counter-btn text { font-size: 30rpx; font-weight: 800; line-height: 1; }
.dish-counter .counter-btn .iconfont { font-size: 27rpx; font-weight: 400; line-height: 1; }
.dish-counter .counter-btn.plus { background: var(--brand); }
.dish-counter .counter-btn.plus text { color: #fff; }
.dish-counter .counter-btn.minus { border: none; background: #E5E7EB; }
.dish-qty-control .counter-btn.minus { background: #EAEDF1; }
.dish-counter .counter-btn.minus text { color: #4B5563; }
.dish-counter .counter-num { width: 36rpx; min-width: 36rpx; text-align: center; font-size: 30rpx; line-height: 32rpx; font-weight: 600; color: var(--text-1); }
.dish-qty-control .counter-num { width: 32rpx; min-width: 32rpx; font-size: 30rpx; line-height: 32rpx; }
.soldout-action { height: 60rpx; min-width: 104rpx; padding: 0 20rpx; border-radius: 30rpx; display: flex; align-items: center; justify-content: center; background: #eef1f4; box-sizing: border-box; flex-shrink: 0; }
.soldout-action text { font-size: 24rpx; font-weight: 600; color: #9aa1aa; white-space: nowrap; }


.counter-btn {
  width: 72rpx;
  height: 72rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 36rpx;
    font-weight: 700;
    line-height: 1;
  }

  &.plus {
    background: var(--brand);
    text { color: #fff; }
  }

  &.minus {
    background: #f3f4f6;
    text { color: var(--text-2); }
  }

  &.sm {
    width: 52rpx;
    height: 52rpx;
    text { font-size: 30rpx; }
  }
}

.counter-num {
  font-size: 28rpx;
  font-weight: 800;
  color: var(--text-1);
  min-width: 32rpx;
  text-align: center;
}


.list-pad { height: calc(348rpx + env(safe-area-inset-bottom)); }

.empty-menu {
  min-height: 520rpx;
  padding: 80rpx 32rpx 32rpx;
  text-align: center;
  box-sizing: border-box;
}

.empty-menu-img {
  width: 280rpx;
  height: 280rpx;
  margin: 0 auto 8rpx;
}

.empty-title {
  display: block;
  color: var(--text-1);
  font-size: 34rpx;
  font-weight: 800;
}

.empty-desc {
  display: block;
  margin-top: 14rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 1.6;
}

.empty-retry {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 28rpx;
  padding: 0 36rpx;
  height: 72rpx;
  border-radius: 36rpx;
  background: var(--brand);
  text { color: #fff; font-size: 28rpx; font-weight: 700; }
}


.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(100rpx + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  background: #fff;
  border-top: 1rpx solid var(--border);
  display: flex;
  align-items: stretch;
  z-index: 300;
}

.bn-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;

  &:active { opacity: 0.72; }
}

.bn-icon {
  display: block;
  width: 60rpx;
  height: 60rpx;
  color: var(--text-3);
  font-size: 56rpx;
  line-height: 60rpx;
  text-align: center;
  transition: color 180ms ease-out, transform 180ms ease-out;
}


.bn-item.active .bn-icon {
  color: var(--brand);
  transform: translateY(-1rpx);
  animation: tabLabelBounce 280ms var(--bounce-ease);
}

@keyframes tabLabelBounce {
  0% { transform: scale(1); }
  40% { transform: scale(1.18); }
  100% { transform: scale(1); }
}

.bn-dot {
  position: absolute;
  top: 12rpx;
  right: calc(50% - 36rpx);
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background: var(--danger);
}


.shop-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12rpx;
}

.dist-pill {
  flex-shrink: 0;
  background: rgba(255,255,255,0.2);
  border-radius: 20rpx;
  padding: 4rpx 12rpx;
  margin-top: 4rpx;
}

.dist-text {
  color: rgba(255,255,255,0.9);
  font-size: 20rpx;
}


.tab-scroll {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: calc(100rpx + env(safe-area-inset-bottom));
  padding-top: calc(176rpx + env(safe-area-inset-top));
}


.card-tab.member-center {
  padding: 28rpx 32rpx calc(132rpx + env(safe-area-inset-bottom));
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  box-sizing: border-box;
}
@keyframes micBorderGlow { 0%, 100% { box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), 0 10rpx 24rpx rgba(0,0,0,.22), 0 0 0 1px rgba(212,175,110,.28); } 50% { box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), 0 10rpx 26rpx rgba(0,0,0,.26), 0 0 0 1px rgba(232,202,160,.6); } }
.member-identity-card { position: relative; padding: 30rpx 32rpx 26rpx; border-radius: 32rpx; background: linear-gradient(120deg,#15392a 0%,#0a2216 42%,#1c4530 100%); box-sizing: border-box; overflow: hidden; animation: micBorderGlow 3.2s ease-in-out infinite; }
.member-identity-card::before { content:''; position: absolute; inset: 0; opacity: .5; background-image: repeating-linear-gradient(135deg, rgba(255,255,255,.035) 0px, rgba(255,255,255,.035) 1px, transparent 1px, transparent 7px); pointer-events: none; }
.mic-glow { position: absolute; right: -68rpx; top: -68rpx; width: 260rpx; height: 260rpx; border-radius: 50%; background: radial-gradient(circle, rgba(212,175,110,.2), transparent 70%); pointer-events: none; }
.mic-issuer { position: relative; z-index: 1; font-size: 21rpx; font-weight: 800; letter-spacing: 2rpx; color: rgba(232,202,160,.5); text-transform: uppercase; }
.mic-body { position: relative; z-index: 1; margin-top: 20rpx; display: flex; align-items: center; gap: 22rpx; }
.member-avatar { width: 100rpx; height: 100rpx; border-radius: 50%; background: #16311f; display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; }
.member-avatar text { color: #f3e6cf; font-size: 34rpx; line-height: 48rpx; font-weight: 900; }
.member-avatar-img { width: 100%; height: 100%; }
.member-avatar-badge { width: 96%; height: 96%; animation: micBadgePulse 3.2s ease-in-out infinite; }
.member-identity-main { flex: 1; min-width: 0; }
.mic-crest-row { display: flex; align-items: center; gap: 10rpx; min-width: 0; }
.member-level { display: block; font-size: 38rpx; line-height: 50rpx; font-weight: 900; color: #f3e6cf; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mic-sub { display: block; margin-top: 6rpx; font-size: 21rpx; color: rgba(232,202,160,.55); font-weight: 700; letter-spacing: 3rpx; text-transform: uppercase; }
@keyframes micBadgePulse { 0%, 100% { opacity: .85; } 50% { opacity: 1; text-shadow: 0 0 12rpx rgba(232,202,160,.9); } }
.mic-chevron { position: relative; z-index: 1; color: rgba(232,202,160,.55); font-size: 28rpx; flex-shrink: 0; }
.member-progress-wrap { position: relative; z-index: 1; margin-top: 22rpx; }
.member-progress-track { height: 8rpx; border-radius: 999rpx; background: rgba(232,202,160,.16); overflow: hidden; }
.member-progress-fill { height: 100%; border-radius: 999rpx; background: linear-gradient(90deg,#c9a668,#f3e6cf); }
.member-upgrade-text { display: block; margin-top: 10rpx; color: rgba(232,202,160,.7); font-size: 22rpx; line-height: 32rpx; font-weight: 700; }
.mic-footer { position: relative; z-index: 1; margin-top: 22rpx; padding-top: 18rpx; border-top: 1rpx solid rgba(232,202,160,.16); display: flex; align-items: center; justify-content: space-between; }
.mic-number { font-size: 22rpx; font-weight: 700; letter-spacing: 3rpx; color: rgba(232,202,160,.65); }
.mic-since { font-size: 20rpx; color: rgba(232,202,160,.4); font-weight: 700; }
.member-assets-card { min-height: 168rpx; background: #fff; border-radius: 32rpx; display: flex; align-items: stretch; padding: 28rpx 0; box-sizing: border-box; }
.member-asset-item { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8rpx; }
.member-asset-item:active { opacity: .72; }
.member-asset-divider { width: 1rpx; margin: 12rpx 0; background: var(--border); }
.member-asset-value { color: var(--text-1); font-size: 38rpx; line-height: 46rpx; font-weight: 900; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-asset-label { color: var(--text-1); font-size: 26rpx; line-height: 36rpx; font-weight: 700; }
.member-main-action-card { padding: 34rpx; border-radius: var(--radius-hero); background: var(--brand-gradient); box-sizing: border-box; }
.member-action-title { display: block; color: #fff; font-size: 36rpx; line-height: 48rpx; font-weight: 900; }
.member-action-btn { margin-top: 24rpx; height: 96rpx; border-radius: 48rpx; background: #fff; display: flex; align-items: center; justify-content: center; }
.member-action-btn:active { transform: scale(.98); }
.member-action-btn text { color: var(--brand); font-size: 32rpx; line-height: 44rpx; font-weight: 900; }
.member-section { display: flex; flex-direction: column; gap: 16rpx; }
.member-section-title { color: var(--text-1); font-size: 32rpx; line-height: 44rpx; font-weight: 900; }
.member-coupon-list { display: flex; flex-direction: column; gap: 16rpx; }
.member-coupon-card { min-height: 132rpx; padding: 24rpx; border-radius: 28rpx; background: #fff; display: flex; align-items: center; gap: 20rpx; box-sizing: border-box; }
.member-coupon-card:active { opacity: .74; }
.member-coupon-value { width: 118rpx; flex-shrink: 0; color: var(--brand); display: flex; align-items: baseline; justify-content: center; }
.member-coupon-yen { font-size: 26rpx; line-height: 34rpx; font-weight: 900; }
.member-coupon-amount { font-size: 48rpx; line-height: 56rpx; font-weight: 900; }
.member-coupon-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8rpx; }
.member-coupon-condition { color: var(--text-1); font-size: 28rpx; line-height: 38rpx; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-coupon-time { color: var(--text-3); font-size: 24rpx; line-height: 34rpx; }
.member-coupon-use { height: 64rpx; padding: 0 24rpx; border-radius: 32rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.member-coupon-use text { color: #fff; font-size: 24rpx; line-height: 34rpx; font-weight: 800; }
.member-service-card { background: #fff; border-radius: 32rpx; overflow: hidden; }
.member-service-row { min-height: 96rpx; padding: 0 30rpx; display: flex; align-items: center; gap: 20rpx; color: var(--text-1); font-size: 30rpx; line-height: 42rpx; font-weight: 800; box-sizing: border-box; }
.member-service-row + .member-service-row { border-top: 1rpx solid var(--border); }
.member-service-row:active { background: #F7F9FA; }
.member-service-icon { width: 56rpx; height: 56rpx; border-radius: 16rpx; background: #E8F8EF; color: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.member-service-icon .iconfont { font-size: 28rpx; }
.member-service-label { flex: 1; min-width: 0; }
.member-service-arrow { color: #B0B7C0; font-size: 26rpx; line-height: 42rpx; flex-shrink: 0; }
.card-tab-empty { padding: 120rpx 40rpx; text-align: center; }
.cte-title { display: block; font-size: 32rpx; font-weight: 800; color: var(--text-1); margin-bottom: 12rpx; }
.cte-desc { display: block; font-size: 26rpx; color: var(--text-3); line-height: 1.6; }
.cte-btn { margin-top: 32rpx; width: 100%; height: 96rpx; line-height: 96rpx; border-radius: 48rpx; background: var(--brand); color: #fff; font-size: 30rpx; font-weight: 800; display: flex; align-items: center; justify-content: center; padding: 0; border: 0; }
.cte-btn::after { border: 0; }
.cte-btn[disabled] { opacity: .7; }
.cte-btn-plain { background: #EEF2F5; color: #3F4650; }
.cte-secondary { display: block; margin-top: 24rpx; color: #6B7280; font-size: 26rpx; line-height: 38rpx; }
@media screen and (max-width: 340px) {
  .card-tab.member-center { padding-left: 24rpx; padding-right: 24rpx; }
  .member-identity-card { padding: 26rpx 26rpx 22rpx; }
  .mic-body { gap: 18rpx; }
  .member-level { font-size: 34rpx; }
  .member-asset-value { font-size: 34rpx; }
  .member-coupon-card { gap: 14rpx; padding: 22rpx; }
  .member-coupon-use { padding: 0 18rpx; }
}


.coupon-nudge-bar {
  position: fixed;
  left: 20rpx;
  right: 20rpx;
  bottom: calc(248rpx + env(safe-area-inset-bottom) + env(safe-area-inset-bottom));
  z-index: 319;
  min-height: 76rpx;
  padding: 12rpx 14rpx 12rpx 18rpx;
  border-radius: 18rpx 18rpx 0 0;
  background: #fff7e6;
  border: 1rpx solid #ffe2ad;
  box-shadow: 0 -6rpx 18rpx rgba(120, 75, 20, .08);
  display: flex;
  align-items: center;
  gap: 14rpx;
  box-sizing: border-box;
}

.coupon-nudge-bar--done {
  background: #ecfbf3;
  border-color: #bdebd2;
}

.coupon-nudge-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.coupon-nudge-icon {
  flex-shrink: 0;
  width: 42rpx;
  height: 42rpx;
  border-radius: 50%;
  background: #ffe9c7;
  color: #d85a22;
  font-size: 24rpx;
  line-height: 42rpx;
  text-align: center;
}

.coupon-nudge-bar--done .coupon-nudge-icon {
  background: #dff7e9;
  color: var(--brand);
}

.coupon-nudge-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.coupon-nudge-title {
  color: #5a3c1e;
  font-size: 25rpx;
  line-height: 34rpx;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coupon-nudge-bar--done .coupon-nudge-title {
  color: #0f8f50;
}

.coupon-nudge-strong {
  color: #ef3f24;
  font-weight: 900;
}

.coupon-nudge-sub {
  margin-top: 2rpx;
  color: #9a6a21;
  font-size: 20rpx;
  line-height: 28rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coupon-nudge-bar--done .coupon-nudge-sub {
  color: #43a36b;
}

.coupon-nudge-action {
  flex-shrink: 0;
  height: 52rpx;
  min-width: 112rpx;
  padding: 0 20rpx;
  border-radius: 26rpx;
  background: #ff5a3c;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}

.coupon-nudge-action text {
  color: #fff;
  font-size: 23rpx;
  line-height: 32rpx;
  font-weight: 900;
  white-space: nowrap;
}

.coupon-nudge-action--plain {
  background: var(--brand);
}
.cart-bar {
  position: fixed;
  z-index: 320;
  bottom: calc(100rpx + env(safe-area-inset-bottom));
  left: 0;
  right: 0;
  height: calc(148rpx + env(safe-area-inset-bottom));
  min-height: calc(148rpx + env(safe-area-inset-bottom));
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 12rpx 24rpx;
  padding-bottom: calc(12rpx + env(safe-area-inset-bottom));
  background: #1f2937;
  box-shadow: 0 -6rpx 20rpx rgba(0,0,0,0.18);
  box-sizing: border-box;

  &.has-items { background: var(--text-1); }
}

.cart-main {
  flex: 1;
  min-width: 0;
  min-height: 112rpx;
  display: flex;
  align-items: center;
}

.cart-icon-wrap {
  position: relative;
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: #4B5362;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  .has-items & { background: var(--brand); }
}

.cart-iconfont {
  width: 48rpx;
  height: 48rpx;
  color: #fff;
  font-size: 46rpx;
  line-height: 48rpx;
  text-align: center;
}

.cart-badge {
  position: absolute;
  top: -4rpx;
  right: -4rpx;
  min-width: 36rpx;
  height: 36rpx;
  border-radius: 18rpx;
  background: #F04444;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8rpx;
  box-sizing: border-box;

  text { color: #fff; font-size: 22rpx; line-height: 36rpx; font-weight: 600; }
}

.cart-info { flex: 1; min-width: 0; margin-left: 20rpx; display: flex; flex-direction: column; justify-content: center; }
.cart-right { display: flex; align-items: center; flex-shrink: 0; }

.cart-price {
  display: block;
  color: #fff;
  font-size: 48rpx;
  line-height: 56rpx;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cart-tip {
  display: block;
  color: rgba(255,255,255,0.62);
  font-size: 24rpx;
  line-height: 34rpx;
  margin-top: 4rpx;
}

.cart-empty {
  display: block;
  color: rgba(255,255,255,0.72);
  font-size: 30rpx;
  line-height: 40rpx;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.checkout-btn {
  min-width: 236rpx;
  height: 92rpx;
  padding: 0 48rpx;
  border-radius: 46rpx;
  background: var(--brand);
  box-shadow: 0 8rpx 24rpx rgba(7,193,96,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-sizing: border-box;

  text { color: #fff; font-size: 32rpx; font-weight: 600; white-space: nowrap; }

  &.disabled {
    background: #4B5362;
    box-shadow: none;
    text { color: rgba(255,255,255,0.45); }
  }
}

.choose-option-btn { height: 60rpx; padding: 0 20rpx; border-radius: 30rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; transition: transform 180ms var(--bounce-ease); text { color: #fff; font-size: 24rpx; font-weight: 600; white-space: nowrap; } }
.choose-option-btn:active { transform: scale(.97); }
.option-count-pill { position: static; min-width: 34rpx; height: 34rpx; padding: 0 10rpx; border-radius: 999rpx; background: #fff; border: 2rpx solid var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; text { color: var(--brand); font-size: 20rpx; font-weight: 800; white-space: nowrap; } }



.mask {
  position: fixed;
  inset: 0;
  z-index: 3100;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: flex-end;
}


.cart-sheet {
  width: 100%;
  background: #f5f7f8;
  border-radius: 32rpx 32rpx 0 0;
  box-sizing: border-box;
  max-height: 88vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.order-confirm-head { flex-shrink: 0; display: grid; grid-template-columns: 1fr 64rpx; align-items: center; padding: 30rpx 28rpx 22rpx; background: #fff; border-bottom: 1rpx solid #edf0f2; }
.order-confirm-title { font-size: 36rpx; font-weight: 900; color: var(--text-1); }
.order-confirm-close { width: 64rpx; height: 64rpx; display: flex; align-items: center; justify-content: center; color: var(--text-3); font-size: 34rpx; line-height: 64rpx; text-align: center; }
.order-confirm-content { flex: 1; min-height: 0; padding: 20rpx 24rpx 18rpx; box-sizing: border-box; }
.order-confirm-bottom { flex-shrink: 0; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: rgba(255,255,255,0.96); border-top: 1rpx solid #edf0f2; }
.order-summary-card { padding: 18rpx 24rpx; border-radius: var(--radius-card); background: #ecfbf3; border: 1rpx solid #cbeedb; margin-bottom: 18rpx; display: flex; align-items: center; gap: 14rpx; }
.order-summary-card--missing { background: #fff7ed; border-color: #fed7aa; }
.summary-mode-pill { height: 46rpx; padding: 0 18rpx; border-radius: 999rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; text { color: #fff; font-size: 24rpx; font-weight: 900; } }
.summary-table-no { font-size: 32rpx; color: var(--text-1); font-weight: 900; line-height: 1; }
.summary-table-tip { color: #9a6f22; font-size: 24rpx; font-weight: 800; flex-shrink: 0; margin-left: auto; }
.confirm-card { background: #fff; border: 1rpx solid #eef1f3; border-radius: var(--radius-card); margin-bottom: 18rpx; overflow: hidden; }
.selected-items-summary { min-height: 118rpx; padding: 0 28rpx; display: flex; justify-content: space-between; align-items: center; gap: 18rpx; }
.selected-items-title-wrap { display: flex; flex-direction: column; gap: 8rpx; min-width: 0; }
.confirm-title-line { display: flex; align-items: center; gap: 10rpx; min-width: 0; }
.confirm-title-icon { flex-shrink: 0; color: var(--brand); font-size: 30rpx; line-height: 34rpx; }
.selected-items-title { color: var(--text-1); font-size: 34rpx; font-weight: 900; }
.selected-items-action { display: flex; align-items: center; gap: 18rpx; flex-shrink: 0; color: var(--text-2); }
.selected-items-amount { color: var(--brand); font-size: 34rpx; font-weight: 900; }
.selected-items-toggle { color: var(--text-2); font-size: 26rpx; }
.selected-items-toggle-icon { color: var(--text-3); font-size: 28rpx; line-height: 32rpx; }
.cart-items-panel { border-top: 1rpx solid #edf0f2; padding: 0 0 8rpx; }
.cart-items { max-height: 34vh; padding: 0 28rpx; box-sizing: border-box; }
.cart-row { display: flex; align-items: center; gap: 16rpx; padding: 24rpx 0; border-bottom: 1rpx solid #edf0f2; }
.cart-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.cart-row-name { font-size: 31rpx; font-weight: 800; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cart-row-spec { font-size: 22rpx; color: var(--text-3); }
.cart-row-right { display: flex; align-items: center; gap: 14rpx; flex-shrink: 0; }
.cart-row-price { min-width: 82rpx; text-align: right; font-size: 30rpx; font-weight: 900; color: var(--brand); }
.cart-clear-line { height: 58rpx; display: flex; align-items: center; justify-content: flex-end; gap: 6rpx; text { color: #c8ccd1; font-size: 23rpx; font-weight: 700; } .iconfont { color: #c8ccd1; font-size: 24rpx; line-height: 26rpx; } }
.order-preference-section { padding: 26rpx 28rpx; }
.order-preference-section .remark-chips { margin-bottom: 22rpx; }
.order-preference-section .remark-chip { margin-right: 14rpx; margin-bottom: 14rpx; padding: 14rpx 24rpx; border-radius: 999rpx; border: 1rpx solid #dfe5e8; background: #fff; }
.order-preference-section .remark-chip--on { border-color: var(--brand); background: #ecfbf3; }
.order-preference-section .remark-row { border-top: 1rpx solid #edf0f2; padding-top: 22rpx; }
.remark-label-wrap { display: flex; align-items: center; gap: 8rpx; flex-shrink: 0; }
.remark-label-icon { color: var(--brand); font-size: 28rpx; line-height: 32rpx; }
.price-summary-card { padding: 12rpx 28rpx 10rpx; }
.price-row { min-height: 88rpx; display: flex; align-items: center; justify-content: space-between; gap: 18rpx; color: #475467; font-size: 29rpx; border-bottom: 1rpx solid #edf0f2; }
.price-label-wrap { display: flex; align-items: center; gap: 10rpx; min-width: 0; }
.price-label-icon { flex-shrink: 0; color: var(--brand); font-size: 30rpx; line-height: 34rpx; }
.price-row:last-child { border-bottom: 0; }
.price-row--clickable { color: var(--text-1); }
.price-discount { color: var(--brand); font-weight: 800; }
.price-muted { color: var(--text-3); }
.price-row--payable { min-height: 110rpx; color: var(--text-1); font-size: 34rpx; font-weight: 900; }
.price-row--payable text:last-child { color: var(--brand); font-size: 52rpx; font-weight: 900; }
.checkout-btn-full { height: 104rpx; border-radius: 28rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; gap: 10rpx; box-shadow: 0 16rpx 32rpx rgba(16,196,105,0.22); text { color: #fff; font-size: 34rpx; font-weight: 900; } .checkout-btn-icon { font-size: 34rpx; line-height: 38rpx; font-weight: 400; } }
.checkout-btn-full--disabled { background: #cbd5e1; box-shadow: none; }

.ht-shop-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12rpx;
}
.ht-status-badge {
  padding: 6rpx 20rpx; border-radius: 999rpx; font-size: 22rpx; font-weight: 600;
}
.ht-status-badge--open { background: #d1fae5; color: #065f46; }
.ht-status-badge--closed { background: #fee2e2; color: #991b1b; }
.ht-notice { display: block; font-size: 26rpx; color: rgba(255,255,255,0.85); line-height: 1.5; }


.cte-btn {
  margin-top: 32rpx; padding: 24rpx 80rpx;
  background: var(--brand); border-radius: 16rpx;
  color: #fff; font-size: 30rpx; font-weight: 700;
}


.home-tab {
  padding: 32rpx 32rpx calc(132rpx + env(safe-area-inset-bottom));
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  gap: 28rpx;
  box-sizing: border-box;
}

.ht-status-card {
  margin: 0;
  padding: 36rpx;
  background: #fff;
  border-radius: 32rpx;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24rpx;
  box-shadow: 0 8rpx 24rpx rgba(17, 24, 39, 0.04);
  box-sizing: border-box;
}

.ht-status-main { flex: 1; min-width: 0; }
.ht-store-name {
  display: block;
  font-size: 40rpx;
  line-height: 50rpx;
  font-weight: 700;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ht-status-desc {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  line-height: 36rpx;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ht-status-badge {
  flex-shrink: 0;
  min-height: 48rpx;
  padding: 0 20rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  line-height: 34rpx;
  font-weight: 700;
}
.ht-status-badge--open { background: #E8F8EF; color: #087A3D; }
.ht-status-badge--closed { background: #F1F3F5; color: var(--text-3); }

.ht-order-card {
  margin: 0;
  padding: 36rpx;
  border-radius: 36rpx;
  background: var(--brand) url('/static/order/home-hero-bg.jpg') left center / cover no-repeat;
  color: #fff;
  box-sizing: border-box;
  transition: transform 120ms ease-out, opacity 120ms ease-out;
}
.ht-order-card:active { transform: scale(0.992); }
.ht-order-card--disabled { opacity: 0.72; }
.ht-order-card--disabled:active { transform: none; }
.ht-order-kicker {
  display: block;
  font-size: 24rpx;
  line-height: 34rpx;
  color: rgba(58,38,18,0.75);
  font-weight: 600;
}
.ht-order-title {
  display: block;
  margin-top: 8rpx;
  font-size: 48rpx;
  line-height: 64rpx;
  color: #2b1c0f;
  font-weight: 800;
}
.ht-order-desc {
  display: block;
  margin-top: 12rpx;
  font-size: 28rpx;
  line-height: 40rpx;
  color: rgba(58,38,18,0.78);
}
.ht-order-coupon {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  line-height: 34rpx;
  color: rgba(58,38,18,0.75);
}
.ht-order-btn {
  margin-top: 32rpx;
  width: 100%;
  height: 100rpx;
  border-radius: 50rpx;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}
.ht-order-btn text { color: var(--brand); font-size: 34rpx; line-height: 48rpx; font-weight: 800; }
.ht-order-btn--disabled { background: rgba(255,255,255,0.82); }
.ht-order-btn--disabled text { color: var(--text-3); }

.ht-section { display: flex; flex-direction: column; gap: 16rpx; }
.ht-section-head { display: flex; flex-direction: column; gap: 4rpx; }
.ht-section-head--row { flex-direction: row; align-items: center; justify-content: space-between; gap: 20rpx; }
.ht-section-title {
  display: block;
  margin: 0;
  font-size: 34rpx;
  line-height: 46rpx;
  font-weight: 800;
  color: var(--text-1);
}
.ht-section-sub {
  display: block;
  font-size: 24rpx;
  line-height: 34rpx;
  color: var(--text-3);
}
.ht-section-action {
  flex-shrink: 0;
  font-size: 26rpx;
  line-height: 38rpx;
  color: var(--brand);
  font-weight: 700;
}

.ht-feature-card {
  padding: 24rpx;
  background: #fff;
  border-radius: 32rpx;
  display: flex;
  gap: 24rpx;
  box-sizing: border-box;
}
.ht-feature-img-wrap {
  width: 192rpx;
  height: 192rpx;
  border-radius: 28rpx;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--border);
}
.ht-feature-img { width: 100%; height: 100%; display: block; }
.ht-feature-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--border);
}
.ht-feature-placeholder-img {
  width: 55%;
  height: 55%;
}
.ht-feature-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.ht-feature-title-row { display: flex; align-items: center; gap: 12rpx; min-width: 0; }
.ht-feature-name {
  flex: 1;
  min-width: 0;
  font-size: 36rpx;
  line-height: 48rpx;
  font-weight: 800;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ht-feature-tag {
  flex-shrink: 0;
  height: 36rpx;
  padding: 0 14rpx;
  border-radius: 18rpx;
  background: #E8F8EF;
  color: #087A3D;
  font-size: 22rpx;
  line-height: 36rpx;
  font-weight: 700;
}
.ht-feature-desc {
  margin-top: 10rpx;
  font-size: 26rpx;
  line-height: 38rpx;
  color: var(--text-3);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ht-feature-bottom { margin-top: auto; display: flex; align-items: flex-end; justify-content: space-between; gap: 16rpx; }
.ht-feature-price { display: flex; align-items: baseline; min-width: 0; color: var(--brand); }
.ht-feature-yen { font-size: 28rpx; line-height: 36rpx; font-weight: 800; }
.ht-feature-amount { font-size: 40rpx; line-height: 48rpx; font-weight: 900; }
.ht-feature-suffix { margin-left: 4rpx; font-size: 24rpx; line-height: 34rpx; font-weight: 700; }
.ht-feature-add {
  flex-shrink: 0;
  height: 72rpx;
  padding: 0 30rpx;
  border-radius: 36rpx;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease-out;
}
.ht-feature-add:active { transform: scale(0.96); }
.ht-feature-add text { color: #fff; font-size: 26rpx; line-height: 36rpx; font-weight: 800; }
.ht-feature-add--disabled { background: #D0D5DD; }
.ht-feature-add--disabled:active { transform: none; }

.ht-last-list { display: flex; flex-wrap: wrap; gap: 16rpx; }
.ht-last-chip {
  max-width: 100%;
  min-height: 68rpx;
  padding: 0 22rpx 0 26rpx;
  border-radius: 34rpx;
  background: #fff;
  border: 1rpx solid #E5E8EB;
  display: flex;
  align-items: center;
  gap: 10rpx;
  box-sizing: border-box;
}
.ht-last-chip--disabled { opacity: 0.55; }
.ht-last-name {
  max-width: 220rpx;
  font-size: 26rpx;
  line-height: 36rpx;
  color: var(--text-1);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ht-last-add { color: var(--brand); font-size: 30rpx; line-height: 36rpx; font-weight: 900; }

@media screen and (max-width: 340px) {
  .home-tab { padding-left: 24rpx; padding-right: 24rpx; }
  .ht-status-card, .ht-order-card { padding: 30rpx; }
  .ht-feature-card { gap: 18rpx; padding: 20rpx; }
  .ht-feature-img-wrap { width: 176rpx; height: 176rpx; }
  .ht-feature-add { padding: 0 22rpx; }
  .ht-feature-add text { font-size: 24rpx; }
  .ht-last-name { max-width: 184rpx; }
}
.success-mask {
  align-items: center;
  justify-content: center;
  padding: 40rpx;
  background: rgba(10,16,30,0.75);
}

.success-card {
  width: 100%;
  max-height: 88vh;
  background: #fff;
  border-radius: 40rpx;
  padding: 0 0 40rpx;
  box-sizing: border-box;
  overflow-y: auto;
}


.success-header {
  padding: 48rpx 40rpx 32rpx;
  text-align: center;
  border-bottom: 2rpx solid #f1f5f9;
}

.success-check {
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: var(--brand);
  margin: 0 auto 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.success-check-inner {
  width: 44rpx;
  height: 28rpx;
  border-left: 6rpx solid #fff;
  border-bottom: 6rpx solid #fff;
  transform: rotate(-45deg) translateY(-6rpx);
}

.success-title {
  display: block;
  font-size: 40rpx;
  font-weight: 900;
  color: var(--text-1);
  margin-bottom: 8rpx;
}
.success-subtitle {
  display: block;
  font-size: 26rpx;
  color: var(--text-3);
  margin-bottom: 4rpx;
}
.success-paid-amount-row {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  margin: 4rpx 0 8rpx;
}
.success-paid-currency {
  font-size: 32rpx;
  font-weight: 700;
  color: #111;
  margin-bottom: 10rpx;
  margin-right: 2rpx;
}
.success-paid-amount {
  font-size: 88rpx;
  font-weight: 900;
  color: #111;
  line-height: 1;
}
.success-saved-tip {
  display: block;
  font-size: 24rpx;
  color: var(--brand);
  margin-bottom: 4rpx;
}

.success-meta-row {
  display: flex;
  justify-content: center;
  gap: 24rpx;
}

.success-meta {
  font-size: 24rpx;
  color: var(--text-3);
}


.order-status-bar {
  margin: 0 40rpx 0;
  padding: 22rpx 24rpx;
  border-radius: 20rpx;
  text-align: center;
  transition: background 0.3s;
}
.order-status-bar.pending {
  background: #fef9c3;
}
.order-status-bar.preparing {
  background: var(--brand);
  animation: status-pulse 1.5s ease-in-out infinite;
}
.order-status-bar.done {
  background: #fbbf24;
}
.order-status-bar.pending .order-status-text { color: #92400e; }
.order-status-bar.preparing .order-status-text { color: #fff; font-size: 30rpx; }
.order-status-bar.done .order-status-text { color: #78350f; font-size: 30rpx; }
.order-status-text { font-size: 26rpx; font-weight: 700; color: var(--text-2); }

@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.82; }
}

.merchant-note-bar {
  margin: 12rpx 40rpx 0;
  padding: 16rpx 20rpx;
  border-radius: 16rpx;
  background: #fffbeb;
  display: flex;
  align-items: flex-start;
  gap: 10rpx;
}
.merchant-note-icon { font-size: 24rpx; flex-shrink: 0; }
.merchant-note-text { font-size: 24rpx; color: #92400e; line-height: 1.5; flex: 1; }


.success-items {
  padding: 24rpx 40rpx;
  border-bottom: 2rpx solid #f1f5f9;
}

.success-item-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f8fafc;
}

.success-item-row:last-of-type { border-bottom: none; }

.success-item-name {
  flex: 1;
  font-size: 28rpx;
  color: var(--text-2);
  font-weight: 600;
}

.success-item-qty {
  font-size: 24rpx;
  color: var(--text-3);
  font-weight: 400;
}

.success-item-price {
  font-size: 28rpx;
  color: var(--text-1);
  font-weight: 700;
}

.success-discount-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 12rpx;
}
.success-discount-label {
  font-size: 24rpx;
  color: var(--text-3);
}
.success-discount-val {
  font-size: 26rpx;
  color: var(--danger);
  font-weight: 600;
}

.success-total-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 16rpx;
  padding-top: 16rpx;
  border-top: 2rpx solid #e5e7eb;
}

.success-total-label {
  font-size: 26rpx;
  color: var(--text-2);
  font-weight: 700;
}

.success-total-price {
  font-size: 36rpx;
  font-weight: 900;
  color: var(--brand);
}


.success-actions {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
  padding: 0 40rpx;
}

.success-btn-primary {
  height: 96rpx;
  border-radius: var(--radius-card);
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #fff; font-size: 34rpx; font-weight: 900; }
}
.success-btn-secondary {
  height: 96rpx;
  border-radius: var(--radius-card);
  background: #f1f5f9;
  border: 2rpx solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: var(--text-3); font-size: 30rpx; font-weight: 600; }
}

.success-btn-primary.success-btn-secondary {
  background: #f1f5f9;
  border: 2rpx solid #e2e8f0;
  text { color: var(--text-3); font-size: 30rpx; font-weight: 600; }
}

.success-btn-settle {
  background: linear-gradient(135deg, var(--brand), var(--brand-dark));
  box-shadow: 0 8rpx 24rpx rgba(7,193,96,0.35);
  text { font-size: 36rpx; }
}
.success-btn-ghost {
  height: 80rpx;
  border-radius: 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: var(--text-3); font-size: 28rpx; }
}
.success-btn-call {
  height: 72rpx;
  border-radius: 20rpx;
  border: 1rpx solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 4rpx;
  text { color: var(--text-3); font-size: 26rpx; }
}

.success-check--done {
  background: linear-gradient(135deg, #f97316, var(--danger)) !important;
  animation: pulse-done 1s ease-in-out infinite;
}

@keyframes pulse-done {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(249,115,22,0.4); }
  50% { transform: scale(1.05); box-shadow: 0 0 0 16rpx rgba(249,115,22,0); }
}

.success-btn-row {
  display: flex;
  gap: 16rpx;
}

.success-btn-half {
  flex: 1;
  height: 80rpx;
  border-radius: var(--radius-card);
  border: 2rpx solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: var(--text-3); font-size: 28rpx; }
}


.my-orders-pill {
  position: relative;
  display: flex;
  align-items: center;
  padding: 10rpx 18rpx;
  border-radius: 32rpx;
  border: 2rpx solid rgba(255,255,255,0.2);
  text { font-size: 24rpx; color: rgba(255,255,255,0.75); white-space: nowrap; }
}


.my-orders-btn {
  position: relative;
  display: flex;
  align-items: center;
  padding: 0 20rpx;
  height: 64rpx;
  border-radius: 32rpx;
  border: 2rpx solid rgba(255,255,255,0.25);
  flex-shrink: 0;
}

.my-orders-label {
  font-size: 22rpx;
  color: rgba(255,255,255,0.75);
  white-space: nowrap;
}

.my-orders-spent {
  font-size: 26rpx;
  font-weight: 800;
  color: #fff;
  white-space: nowrap;
}

.my-orders-dot {
  position: absolute;
  top: -8rpx;
  right: -8rpx;
  min-width: 32rpx;
  height: 32rpx;
  border-radius: 16rpx;
  background: var(--danger);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 6rpx;
  box-sizing: border-box;
  text { color: #fff; font-size: 20rpx; font-weight: 800; }
}


.orders-sheet {
  width: 100%;
  background: #fff;
  border-radius: 32rpx 32rpx 0 0;
  padding: 0 0 calc(24rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
}

.orders-sheet-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 28rpx 36rpx 18rpx;
  border-bottom: 0;
  flex-shrink: 0;
}

.orders-sheet-title {
  font-size: 36rpx;
  font-weight: 800;
  color: var(--text-1);
  line-height: 1.2;
}

.orders-sheet-spent {
  display: block;
  font-size: 24rpx;
  color: var(--brand);
  font-weight: 700;
  margin-top: 4rpx;
}

.orders-sheet-close {
  width: 56rpx;
  height: 56rpx;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f3f4f6;
  color: var(--text-3);
  font-size: 28rpx;
}

.active-order-bar {
  margin: 0 32rpx 16rpx;
  padding: 18rpx 24rpx;
  border-radius: 16rpx;
  text-align: center;
  &.preparing { background: var(--brand); }
  &.done { background: #fbbf24; }
}
.active-order-text {
  font-size: 26rpx;
  font-weight: 700;
  color: #fff;
}

.orders-list {
  flex: 1;
  width: 100%;
  padding: 8rpx 32rpx 20rpx;
  box-sizing: border-box;
}

.order-card {
  background: #f8fafc;
  border-radius: var(--radius-card);
  padding: 24rpx;
  margin-bottom: 20rpx;
}

.order-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16rpx;
}

.order-card-no {
  font-size: 26rpx;
  font-weight: 700;
  color: var(--text-2);
}

.order-status-tag {
  padding: 6rpx 16rpx;
  border-radius: 20rpx;
  font-size: 22rpx;
  font-weight: 700;
  &.pending { background: #fef9c3; text { color: #854d0e; } }
  &.preparing { background: #dbeafe; text { color: #1d4ed8; } }
  &.done { background: #dcfce7; text { color: #16a34a; } }
}

.order-card-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 8rpx 0;
}

.order-card-item-name {
  flex: 1;
  font-size: 26rpx;
  color: var(--text-3);
}

.order-card-item-price {
  font-size: 26rpx;
  color: var(--text-2);
  font-weight: 600;
}

.order-card-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16rpx;
  padding-top: 16rpx;
  border-top: 2rpx solid #e5e7eb;
}

.order-card-total {
  font-size: 28rpx;
  font-weight: 800;
  color: var(--brand);
}

.order-card-time {
  font-size: 22rpx;
  color: var(--text-3);
}

.order-card-cancel-row {
  margin-top: 16rpx;
  padding-top: 16rpx;
  border-top: 1rpx solid #f1f5f9;
  display: flex;
  justify-content: flex-end;
}

.order-cancel-btn {
  padding: 10rpx 28rpx;
  border-radius: 20rpx;
  border: 1rpx solid #e5e7eb;
  text { font-size: 24rpx; color: var(--text-3); }
}


.table-status-card {
  padding: 30rpx;
  border-radius: var(--radius-card);
  border: 2rpx solid var(--order-status-border, #bae6fd);
  background: var(--order-status-bg, #eff8ff);
  box-sizing: border-box;
}

.table-status-card--canceled {
  --order-status-main: #ef4444;
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
  --order-status-main: #f59e0b;
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

.table-status-empty {
  padding: 90rpx 40rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.table-status-empty-icon {
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: #f3f5f7;
  color: #b8bfc7;
  font-size: 44rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20rpx;
}

.table-status-empty-title {
  font-size: 30rpx;
  font-weight: 900;
  color: var(--text-1);
}

.table-status-empty-desc {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: var(--text-3);
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

.order-progress-step.done .order-progress-line {
  background: var(--brand);
}

.order-progress-step.done .order-progress-dot,
.order-progress-step.active .order-progress-dot {
  background: var(--brand);
  color: #fff;
}

.order-progress-step.active .order-progress-dot {
  box-shadow: 0 0 0 8rpx #dcfce7;
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

.orders-secondary-btn--canceled {
  background: var(--text-1);
}

.orders-secondary-btn--completed {
  background: #f3f5f7;
  text { color: var(--text-2); }
}

.loading-mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(255,255,255,0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24rpx;
}

.loading-text { font-size: 28rpx; color: var(--text-3); }

.skeleton-mask {
  position: fixed;
  top: calc(176rpx + env(safe-area-inset-top));
  left: 0;
  right: 0;
  bottom: 0;
  background: #fff;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  justify-content: flex-start;
  gap: 0;
}

.skeleton-nav {
  width: 156rpx;
  flex: 0 0 156rpx;
  background: #F6F7F8;
  padding-top: 20rpx;
  box-sizing: border-box;
}

.skeleton-nav-item {
  height: 36rpx;
  margin: 0 28rpx 32rpx;
  border-radius: 8rpx;
}

.skeleton-list {
  flex: 1;
  min-width: 0;
  padding: 20rpx 20rpx 0;
  box-sizing: border-box;
  overflow: hidden;
}

.skeleton-dish {
  display: flex;
  align-items: flex-start;
  height: 192rpx;
  margin-bottom: 24rpx;
}

.skeleton-thumb {
  width: 192rpx;
  height: 192rpx;
  border-radius: 20rpx;
  flex-shrink: 0;
}

.skeleton-lines {
  flex: 1;
  min-width: 0;
  margin-left: 20rpx;
  padding-top: 10rpx;
  display: flex;
  flex-direction: column;
  gap: 18rpx;
}

.skeleton-line {
  height: 26rpx;
  border-radius: 8rpx;
}

.skeleton-line--title { width: 55%; height: 32rpx; }
.skeleton-line--desc { width: 85%; }
.skeleton-line--price { width: 28%; height: 34rpx; margin-top: 36rpx; }

.skeleton-nav-item,
.skeleton-thumb,
.skeleton-line {
  background: linear-gradient(90deg, #edeff1 25%, #f7f8f9 37%, #edeff1 63%);
  background-size: 400% 100%;
  animation: skeletonShimmer 1.4s ease infinite;
}

@keyframes skeletonShimmer {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}

.retry-btn {
  margin-top: 24rpx;
  padding: 16rpx 48rpx;
  border-radius: var(--radius-card);
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #fff; font-size: 30rpx; font-weight: 700; }
}


.coupon-select-section {
  border-top: 1rpx solid #f3f4f6;
  padding: 20rpx 0 8rpx;
}
.coupon-select-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16rpx;
}
.coupon-select-label {
  font-size: 26rpx;
  color: var(--text-2);
  font-weight: 600;
}
.coupon-select-tip {
  font-size: 24rpx;
  color: var(--danger);
  font-weight: 600;
}
.coupon-select-list {
  white-space: nowrap;
}
.coupon-chip-item {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  padding: 14rpx 24rpx;
  margin-right: 16rpx;
  border-radius: 16rpx;
  border: 2rpx solid #e5e7eb;
  background: #fff;
}
.coupon-chip-item--on {
  border-color: var(--brand);
  background: #f0fdf4;
  .coupon-chip-amount { color: var(--brand); }
  .coupon-chip-min { color: #16a34a; }
}
.coupon-chip-amount {
  font-size: 30rpx;
  font-weight: 700;
  color: var(--danger);
}
.coupon-chip-min {
  font-size: 20rpx;
  color: var(--text-3);
  margin-top: 4rpx;
}


.remark-section {
  border-top: 1rpx solid #f3f4f6;
  margin-top: 8rpx;
  padding-top: 16rpx;
}

.remark-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  padding-bottom: 16rpx;
}

.remark-chip {
  padding: 8rpx 22rpx;
  border-radius: 32rpx;
  border: 1rpx solid #e5e7eb;
  background: #f8fafc;
  text { font-size: 24rpx; color: var(--text-3); }
}
.remark-chip--on {
  border-color: var(--brand);
  background: #f0fdf4;
  text { color: var(--brand); font-weight: 600; }
}

.remark-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 12rpx 0 16rpx;
  border-top: 1rpx solid #f3f4f6;
}

.remark-label {
  flex-shrink: 0;
  font-size: 26rpx;
  color: var(--text-3);
}

.remark-input {
  flex: 1;
  font-size: 26rpx;
  color: var(--text-1);
  background: transparent;
}

.remark-placeholder { color: #c8c9cc; }


.member-price {
  font-size: 24rpx;
  color: var(--brand);
  font-weight: 600;
  margin-left: 8rpx;
}


.cart-row-spec {
  display: block;
  font-size: 22rpx;
  color: var(--text-3);
  margin-top: 4rpx;
}

.spec-detail-hero {
  width: 100%;
  height: 460rpx;
  min-height: 460rpx;
  max-height: 460rpx;
  background: #f6f7f8;
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
}

.spec-detail-placeholder text {
  width: 96rpx;
  height: 96rpx;
  border-radius: 48rpx;
  background: rgba(255, 255, 255, 0.72);
  color: var(--text-2);
  font-size: 44rpx;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Detail / SKU bottom sheet */
.spec-sheet {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100%;
  max-height: 90vh;
  background: #fff;
  border-radius: 40rpx 40rpx 0 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  animation: slide-up 0.25s ease;
}

@keyframes slide-up {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}

.spec-sheet-head {
  position: relative;
  padding: 32rpx;
  background: #fff;
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
  display: flex;
  align-items: flex-end;
  margin-top: 16rpx;
  color: var(--brand);
  line-height: 1;
}

.spec-price-symbol {
  font-size: 28rpx;
  font-weight: 700;
  line-height: 1;
}

.spec-price-num {
  font-size: 44rpx;
  font-weight: 700;
  line-height: 1;
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
    background: #e8f9f0;
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
  background: #e8f9f0;
  color: var(--brand);
  font-weight: 600;
}

.item-remark-extra-toggle {
  display: inline-block;
  margin-top: 20rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 36rpx;
}

.item-remark-input {
  width: 100%;
  min-height: 152rpx;
  margin-top: 20rpx;
  max-height: 176rpx;
  padding: 24rpx;
  border: 1rpx solid #e5e7ea;
  border-radius: 20rpx;
  background: #fff;
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

.spec-counter-row .counter-btn {
  width: 72rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  box-sizing: border-box;
}

.spec-counter-row .counter-btn.minus {
  width: 64rpx;
  height: 64rpx;
  background: #f5f6f7;
  color: var(--text-2);
}

.spec-counter-row .counter-btn.plus {
  background: var(--brand);
  color: #fff;
}

.spec-counter-row .counter-btn text {
  font-size: 36rpx;
  font-weight: 600;
  line-height: 1;
}

.spec-counter-row .counter-btn .iconfont {
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
  background: #fff;
  box-sizing: border-box;
}

.spec-confirm-btn {
  width: 100%;
  height: 100rpx;
  border-radius: 50rpx;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;

  text {
    color: #fff;
    font-size: 32rpx;
    font-weight: 600;
    line-height: 44rpx;
  }
}

.spec-confirm-btn--disabled {
  background: #cfd6dc;
  opacity: .95;
}

.closed-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48rpx;
}

.closed-card {
  background: #fff;
  border-radius: 32rpx;
  padding: 56rpx 40rpx 40rpx;
  text-align: center;
  width: 100%;
}

.closed-icon-wrap {
  width: 112rpx;
  height: 112rpx;
  margin: 0 auto 24rpx;
  border-radius: 50%;
  background: #F3F4F6;
  color: #9aa1aa;
  display: flex;
  align-items: center;
  justify-content: center;
}

.closed-icon {
  font-size: 56rpx;
}

.closed-title {
  display: block;
  font-size: 36rpx;
  font-weight: 700;
  color: #111;
  margin-bottom: 12rpx;
}

.closed-desc {
  display: block;
  font-size: 28rpx;
  color: var(--text-3);
  line-height: 1.6;
  margin-bottom: 40rpx;
}

.closed-btn {
  padding: 24rpx 0;
  background: var(--brand);
  border-radius: 20rpx;
  text {
    font-size: 30rpx;
    color: #fff;
    font-weight: 700;
  }
}

.closed-btn-plain {
  margin-top: 16rpx;
  background: #f3f4f6;
  text { color: var(--text-3); font-weight: 600; }
}

.checkout-auth-mask { align-items: flex-end; }
.checkout-auth-sheet { width: 100%; max-height: 55vh; background: #fff; border-radius: 32rpx 32rpx 0 0; padding: 18rpx 36rpx calc(22rpx + env(safe-area-inset-bottom)); box-sizing: border-box; display: flex; flex-direction: column; align-items: stretch; animation: authSheetIn .2s ease-out; }
.checkout-auth-handle { width: 72rpx; height: 8rpx; border-radius: 999rpx; background: #e5e7eb; align-self: center; margin-bottom: 20rpx; }
.checkout-auth-title { color: var(--text-1); font-size: 38rpx; font-weight: 900; text-align: center; line-height: 1.25; }
.checkout-auth-desc { margin-top: 12rpx; color: var(--text-2); font-size: 27rpx; line-height: 1.55; text-align: center; }
.checkout-auth-order { margin-top: 22rpx; padding: 22rpx 24rpx; border-radius: 22rpx; background: #f8fafb; border: 1rpx solid #edf0f2; }
.checkout-auth-row { display: flex; align-items: center; justify-content: space-between; gap: 24rpx; color: var(--text-3); font-size: 26rpx; line-height: 1.5; }
.checkout-auth-row + .checkout-auth-row { margin-top: 12rpx; }
.checkout-auth-row text:last-child { color: var(--text-1); font-weight: 800; text-align: right; max-width: 440rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.checkout-auth-row--amount text:last-child { color: var(--brand); font-size: 32rpx; font-weight: 900; }
.checkout-auth-auto { margin-top: 18rpx; padding: 18rpx 20rpx; border-radius: 18rpx; background: #ecfbf3; color: #0f8f50; font-size: 24rpx; line-height: 1.55; }
.checkout-auth-primary { margin-top: 24rpx; height: 96rpx; border-radius: var(--radius-card); background: #16c76f; color: #fff; font-size: 31rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; box-shadow: 0 14rpx 34rpx rgba(16, 196, 105, .22); }
.checkout-auth-primary[disabled] { opacity: .72; box-shadow: none; }
.checkout-auth-cancel { height: 72rpx; display: flex; align-items: center; justify-content: center; color: var(--text-3); font-size: 28rpx; }
.checkout-auth-member { display: block; color: var(--text-3); font-size: 22rpx; line-height: 1.45; text-align: center; margin-top: 2rpx; }
.checkout-auth-privacy { display: block; color: #a8b1bd; font-size: 21rpx; line-height: 1.45; text-align: center; margin-top: 10rpx; }
@keyframes authSheetIn { from { transform: translateY(24rpx); opacity: .92; } to { transform: translateY(0); opacity: 1; } }

.order-remark-row { border-top: 0 !important; padding-top: 0 !important; }

/* Cart micro interactions */
.counter-btn {
  transform-origin: center;
  transition: transform 160ms ease-out;
}

.counter-btn .iconfont {
  font-size: 30rpx;
  font-weight: 400;
  line-height: 1;
}

.counter-btn--pressing {
  animation: addButtonPress 220ms var(--bounce-ease);
}

.counter-num--pulse {
  animation: cartQtyPulse 150ms ease-out;
}

.cart-icon-wrap {
  transform-origin: center;
  transition: background 150ms ease-out, transform 180ms ease-out;
}

.cart-icon-wrap--pulse {
  animation: cartIconPulse 180ms ease-out;
}

.cart-badge {
  transform-origin: center;
}

.cart-badge--pulse {
  animation: cartBadgePulse 180ms ease-out;
}

.cart-price {
  transform-origin: left center;
  transition: color 150ms ease-out, transform 180ms ease-out;
}

.cart-price--highlight {
  color: #34f38a;
  animation: cartAmountHighlight 200ms ease-out;
}

.checkout-btn {
  transition: background 180ms ease-out, opacity 180ms ease-out;
}

@keyframes addButtonPress {
  0% { transform: scale(1); }
  40% { transform: scale(.9); }
  75% { transform: scale(1.08); }
  100% { transform: scale(1); }
}

@keyframes cartQtyPulse {
  0% { opacity: .75; transform: scale(.9); }
  100% { opacity: 1; transform: scale(1); }
}

@keyframes cartIconPulse {
  0% { transform: scale(1); }
  45% { transform: scale(1.07); }
  100% { transform: scale(1); }
}

@keyframes cartBadgePulse {
  0% { opacity: .85; transform: scale(.86); }
  55% { opacity: 1; transform: scale(1.1); }
  100% { opacity: 1; transform: scale(1); }
}

@keyframes cartAmountHighlight {
  0% { transform: translateY(0); }
  45% { transform: translateY(-4rpx); }
  100% { transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .counter-btn,
  .cart-icon-wrap,
  .cart-badge,
  .cart-price,
  .checkout-btn,
  .choose-option-btn {
    transition-duration: 0ms;
    animation: none;
  }
}

.table-account-sheet {
  background: #f6f7f8;
  padding-bottom: 0;
}

.table-account-head {
  position: relative;
  justify-content: center;
  min-height: 88rpx;
}

.table-account-back {
  position: absolute;
  left: 18rpx;
  top: 12rpx;
  width: 64rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-2);
}

.table-account-back text {
  font-size: 34rpx;
}

.table-account-list {
  max-height: calc(82vh - 176rpx - env(safe-area-inset-bottom));
  padding: 0 24rpx 188rpx;
  box-sizing: border-box;
}

.table-account-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18rpx 24rpx 20rpx;
  text-align: center;
}

.table-account-status-icon {
  width: 56rpx;
  height: 56rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 顶部大状态图标和下面每笔子订单的状态标签用同一套语义色：
   active=还在等（下单/制作中），served=菜已上齐可以结账，settled=已结账/归档。 */
.table-account-status-icon--active {
  background: #fff7e6;
  color: var(--warning);
}

.table-account-status-icon--served {
  background: #ecfbf3;
  color: var(--brand);
}

.table-account-status-icon--settled {
  background: #f3f4f6;
  color: var(--text-3);
}

.table-account-status-icon text {
  font-size: 30rpx;
}

.table-account-status-title {
  margin-top: 12rpx;
  color: var(--text-1);
  font-size: 44rpx;
  font-weight: 900;
  line-height: 1.25;
}

.table-account-status-desc {
  margin-top: 8rpx;
  color: var(--text-3);
  font-size: 28rpx;
  line-height: 1.45;
}

.table-account-status-note {
  display: block;
  margin-top: 4rpx;
  color: var(--text-3);
  font-size: 24rpx;
  line-height: 1.4;
}

.table-account-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  margin-top: 8rpx;
  padding: 26rpx 28rpx;
  border-radius: 24rpx;
  background: #fff;
  box-sizing: border-box;
}

.table-account-summary-left,
.table-account-summary-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.table-account-table,
.table-account-total {
  color: var(--text-1);
  font-size: 40rpx;
  font-weight: 900;
  line-height: 1.25;
}

.table-account-sub,
.table-account-count {
  margin-top: 8rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 1.4;
}

.table-account-summary-right {
  flex-shrink: 0;
  align-items: flex-end;
  text-align: right;
}

.table-account-total {
  color: var(--brand);
}

.table-account-section {
  margin-top: 18rpx;
  padding: 24rpx;
  border-radius: 24rpx;
  background: #fff;
  box-sizing: border-box;
}

.table-account-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18rpx;
}

.table-account-section-title {
  color: var(--text-1);
  font-size: 34rpx;
  font-weight: 900;
  line-height: 1.35;
}

.table-account-group + .table-account-group {
  margin-top: 26rpx;
  padding-top: 22rpx;
  border-top: 1rpx solid #eef1f3;
}

.table-account-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18rpx;
  margin-bottom: 16rpx;
}

.table-account-group-left {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12rpx;
}

/* 拼桌时标出"这一单是第几位点的"，纯展示编号，不关联真实身份 */
.participant-badge {
  flex-shrink: 0;
  width: 34rpx;
  height: 34rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20rpx;
  font-weight: 800;
}

.table-account-group-time {
  color: var(--text-2);
  font-size: 28rpx;
  font-weight: 800;
}

/* 服务员代客加的单也标出来，让顾客知道这道菜是谁帮加的，结账时不会觉得莫名其妙 */
.table-account-staff-badge {
  flex-shrink: 0;
  color: #a21caf;
  background: #fdf4ff;
  border-radius: 8rpx;
  padding: 2rpx 10rpx;
  font-size: 20rpx;
  font-weight: 700;
}

.table-account-group-discount {
  flex-shrink: 0;
  color: #ef4444;
  font-size: 24rpx;
  font-weight: 700;
}

.table-account-group-status {
  flex-shrink: 0;
  color: var(--warning);
  font-size: 24rpx;
  line-height: 34rpx;
}

.table-account-group-status--served {
  color: var(--brand);
}

.table-account-group-status--settled {
  color: var(--text-3);
}

.table-account-group-status--muted {
  color: #9aa1aa;
}

.table-account-item {
  min-height: 128rpx;
  display: flex;
  align-items: center;
  gap: 18rpx;
  padding: 12rpx 0;
  box-sizing: border-box;
}

.table-account-item--muted {
  opacity: .58;
}

.table-account-item-img-wrap,
.table-account-item-img,
.table-account-item-placeholder {
  width: 112rpx;
  height: 112rpx;
  border-radius: 20rpx;
  flex-shrink: 0;
  overflow: hidden;
}

.table-account-item-placeholder {
  background: #f2f4f5;
  display: flex;
  align-items: center;
  justify-content: center;
}

.table-account-item-placeholder text {
  color: var(--text-3);
  font-size: 34rpx;
  font-weight: 800;
}

.table-account-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.table-account-item-name {
  color: var(--text-1);
  font-size: 32rpx;
  font-weight: 800;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-account-item-spec,
.table-account-item-mark {
  margin-top: 6rpx;
  color: var(--text-3);
  font-size: 25rpx;
  line-height: 1.35;
}

.table-account-item-mark {
  color: #9a6a21;
}

.table-account-item-qty {
  flex-shrink: 0;
  min-width: 52rpx;
  color: var(--text-2);
  font-size: 28rpx;
  font-weight: 800;
  text-align: right;
}

.table-account-item-amount {
  flex-shrink: 0;
  min-width: 118rpx;
  color: var(--text-1);
  font-size: 29rpx;
  font-weight: 900;
  text-align: right;
}

.table-account-empty {
  padding: 56rpx 20rpx;
  text-align: center;
}

.table-account-empty-title {
  display: block;
  color: var(--text-1);
  font-size: 32rpx;
  font-weight: 900;
}

.table-account-empty-desc {
  display: block;
  margin-top: 10rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 1.5;
}

.table-account-tip {
  margin: 18rpx 0 0;
  padding: 18rpx 22rpx;
  border-radius: 18rpx;
  background: #eef2f0;
  color: var(--text-3);
  font-size: 25rpx;
  line-height: 1.45;
}

.table-account-retry {
  width: 220rpx;
  height: 76rpx;
  margin: 24rpx auto 0;
  border-radius: 38rpx;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
}

.table-account-retry text {
  color: #fff;
  font-size: 28rpx;
  font-weight: 900;
}

.table-account-actions {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  display: flex;
  gap: 18rpx;
  padding: 18rpx 24rpx calc(18rpx + env(safe-area-inset-bottom));
  background: #fff;
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
}

.table-account-action text {
  font-size: 29rpx;
  font-weight: 900;
  white-space: nowrap;
}

.table-account-action--secondary {
  flex: 0 0 236rpx;
  border: 2rpx solid var(--brand);
  background: #fff;
  color: var(--brand);
}

.table-account-action--secondary text {
  color: var(--brand);
}

.table-account-action--primary {
  flex: 1;
  min-width: 0;
  background: var(--brand);
  color: #fff;
}

.table-account-action--primary text {
  color: #fff;
}

.table-account-action--ghost {
  background: #f1f4f3;
}

.table-account-action--ghost text {
  color: var(--text-2);
}

.table-account-action--disabled {
  opacity: .5;
}

/* 餐后付款没有可点击的"去结账"——结账动作在商家手里，这里只是一句提示，
   不能长得跟旁边的按钮一样可点，字号、字重都调低，允许换行。 */
.table-account-action--info {
  height: auto;
  min-height: 92rpx;
  background: #f6f7f8;
  padding: 12rpx 20rpx;
}

.table-account-action--info text {
  color: var(--text-2);
  font-size: 24rpx;
  font-weight: 600;
  white-space: normal;
  line-height: 1.4;
  text-align: center;
}

/* Order success sheet */
.success-mask {
  align-items: flex-end;
  justify-content: flex-end;
  padding: 0;
  background: rgba(15, 23, 42, .52);
}

.success-sheet {
  width: 100%;
  max-height: 88vh;
  background: #f6f7f8;
  border-radius: 32rpx 32rpx 0 0;
  padding: 18rpx 24rpx calc(20rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
  animation: successSheetIn 200ms ease-out;
}

.success-handle {
  width: 72rpx;
  height: 8rpx;
  border-radius: 999rpx;
  background: #d7dce2;
  margin: 0 auto 18rpx;
}

.success-sheet .success-card {
  max-height: none;
  overflow: visible;
  border-radius: 28rpx;
  padding: 44rpx 34rpx 28rpx;
  border: 1rpx solid #edf0f2;
  text-align: center;
}

.success-sheet .success-check {
  width: 112rpx;
  height: 112rpx;
  margin: 0 auto 22rpx;
  box-shadow: 0 12rpx 28rpx rgba(16,196,105,.22);
  animation: successCheckIn 280ms ease-out;
}

.success-sheet .success-check-inner {
  width: 46rpx;
  height: 28rpx;
  border-left: 7rpx solid #fff;
  border-bottom: 7rpx solid #fff;
  transform: rotate(-45deg) translateY(-6rpx);
}

.success-sheet .success-title {
  margin: 0;
  font-size: 46rpx;
  line-height: 1.2;
  font-weight: 900;
  color: var(--text-1);
}

.success-sheet .success-paid-amount-row {
  margin: 12rpx 0 0;
}

.success-sheet .success-paid-currency {
  font-size: 34rpx;
  margin-bottom: 10rpx;
}

.success-sheet .success-paid-amount {
  font-size: 68rpx;
  letter-spacing: 0;
}

.success-paid-label {
  display: block;
  margin-top: 4rpx;
  color: var(--text-3);
  font-size: 23rpx;
}

.success-sheet .order-status-bar {
  margin: 28rpx 0 0;
  padding: 22rpx 24rpx;
  border-radius: 20rpx;
  background: #ecfbf3;
  text-align: center;
  animation: none;
}

.success-sheet .order-status-bar.pending,
.success-sheet .order-status-bar.preparing {
  background: #ecfbf3;
}

.success-sheet .order-status-bar.done {
  background: #f0fdf4;
}

.success-sheet .order-status-bar.warning {
  background: #fff7ed;
}

.success-sheet .order-status-text {
  color: var(--brand);
  font-size: 27rpx;
  font-weight: 800;
  line-height: 1.55;
}

.success-sheet .order-status-bar.warning .order-status-text {
  color: #9a6a21;
}

.earned-coupon-card {
  position: relative;
  margin-top: 20rpx;
  padding: 34rpx 28rpx 28rpx;
  border-radius: 24rpx;
  text-align: center;
  background: linear-gradient(160deg, #ff5a3c 0%, #ff2f1f 55%, #d81717 100%);
  border: 2rpx solid rgba(255, 222, 150, 0.9);
  box-shadow: 0 16rpx 40rpx -14rpx rgba(180, 20, 10, 0.45);
  overflow: hidden;
  animation: ec-card-in 0.5s cubic-bezier(0.22, 1.3, 0.4, 1) both;
}

.earned-coupon-card::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(115deg, transparent 42%, rgba(255, 255, 255, 0.5) 50%, transparent 58%);
  transform: translateX(-140%);
  animation: ec-shine 1s ease 0.45s 1;
  pointer-events: none;
}

@keyframes ec-card-in {
  0% { transform: scale(0.85); opacity: 0; }
  60% { transform: scale(1.03); opacity: 1; }
  100% { transform: scale(1); }
}

@keyframes ec-shine {
  to { transform: translateX(140%); }
}

.ec-ribbon {
  display: inline-block;
  padding: 4rpx 20rpx;
  border-radius: 999rpx;
  background: rgba(255, 255, 255, 0.18);
  color: #ffe9c2;
  font-size: 21rpx;
  font-weight: 700;
  margin-bottom: 14rpx;
}

.ec-amount-row {
  display: flex;
  align-items: baseline;
  justify-content: center;
}

.ec-currency {
  font-size: 30rpx;
  font-weight: 800;
  color: #ffffff;
  margin-right: 2rpx;
}

.ec-amount {
  font-size: 68rpx;
  font-weight: 900;
  color: #ffffff;
  line-height: 1;
  text-shadow: 0 3rpx 0 rgba(120, 10, 0, 0.4);
}

.ec-cond {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #ffe4d2;
}

.ec-divider {
  width: 100%;
  height: 1rpx;
  background: rgba(255, 255, 255, 0.25);
  margin: 20rpx 0 18rpx;
}

.ec-title {
  display: block;
  font-size: 25rpx;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.5;
}

.ec-deadline {
  display: block;
  margin-top: 8rpx;
  font-size: 21rpx;
  font-weight: 700;
  color: #ffe9c2;
}

.ec-remind-btn {
  display: inline-block;
  margin-top: 18rpx;
  padding: 8rpx 22rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.6);
  border-radius: 999rpx;
  font-size: 21rpx;
  font-weight: 700;
  color: #ffffff;
  background: rgba(255, 255, 255, 0.12);
}

.ec-remind-btn--done {
  border-color: rgba(255, 255, 255, 0.3);
  color: rgba(255, 255, 255, 0.55);
  background: transparent;
}

.success-summary {
  margin-top: 26rpx;
  padding-top: 4rpx;
}

.success-summary-row {
  min-height: 76rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1rpx solid #edf0f2;
  gap: 24rpx;
}

.success-summary-row:last-child {
  border-bottom: 0;
}

.success-summary-label {
  color: var(--text-3);
  font-size: 27rpx;
}

.success-summary-value {
  color: var(--text-1);
  font-size: 29rpx;
  font-weight: 800;
  text-align: right;
  max-width: 440rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.success-sheet .success-actions {
  margin-top: 24rpx;
  padding: 0;
  gap: 14rpx;
}

.success-sheet .success-btn-primary {
  height: 98rpx;
  border-radius: var(--radius-card);
  background: var(--brand);
  box-shadow: 0 12rpx 24rpx rgba(16,196,105,.18);
}

.success-sheet .success-btn-primary text {
  color: #fff;
  font-size: 32rpx;
  font-weight: 900;
}

.success-sheet .success-btn-secondary {
  height: 94rpx;
  border-radius: var(--radius-card);
  background: #fff;
  border: 1rpx solid #dfe5e8;
}

.success-sheet .success-btn-secondary text {
  color: #344054;
  font-size: 30rpx;
  font-weight: 800;
}

.success-sheet .success-btn-ghost {
  height: 68rpx;
}

.success-sheet .success-btn-ghost text {
  color: var(--text-2);
  font-size: 26rpx;
  font-weight: 700;
}

.success-safe-tip {
  display: block;
  margin: 16rpx 10rpx 0;
  color: var(--text-3);
  font-size: 22rpx;
  line-height: 1.55;
}

@keyframes successSheetIn {
  from { transform: translateY(28rpx); opacity: .92; }
  to { transform: translateY(0); opacity: 1; }
}

@keyframes successCheckIn {
  0% { transform: scale(.82); opacity: 0; }
  70% { transform: scale(1.04); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .success-sheet,
  .success-sheet .success-check {
    animation: none;
  }
}

.welcome-mask {
  align-items: center;
  justify-content: center;
  padding: 0 48rpx;
  background: rgba(15, 23, 42, .58);
}

.welcome-coupon-sheet {
  width: 100%;
  max-width: 560rpx;
  background: linear-gradient(160deg, #ff5a3c 0%, #ff2f1f 55%, #d81717 100%);
  border: 2rpx solid rgba(255, 222, 150, 0.9);
  border-radius: 32rpx;
  padding: 48rpx 40rpx 36rpx;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
  overflow: hidden;
  box-shadow: 0 16rpx 40rpx -14rpx rgba(180, 20, 10, 0.45);
  animation: ec-card-in 0.5s cubic-bezier(0.22, 1.3, 0.4, 1) both;
}

.welcome-coupon-sheet::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(115deg, transparent 42%, rgba(255, 255, 255, 0.5) 50%, transparent 58%);
  transform: translateX(-140%);
  animation: ec-shine 1s ease 0.45s 1;
  pointer-events: none;
}

.wc-ribbon {
  display: inline-block;
  padding: 4rpx 20rpx;
  border-radius: 999rpx;
  background: rgba(255, 255, 255, 0.18);
  color: #ffe9c2;
  font-size: 22rpx;
  font-weight: 700;
}

.wc-amount-row {
  display: flex;
  align-items: baseline;
  margin-top: 22rpx;
}

.wc-currency {
  font-size: 34rpx;
  font-weight: 800;
  color: #ffffff;
  margin-right: 4rpx;
}

.wc-amount {
  font-size: 88rpx;
  font-weight: 900;
  color: #ffffff;
  line-height: 1;
  text-shadow: 0 3rpx 0 rgba(120, 10, 0, 0.4);
}

.wc-cond {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #ffe4d2;
}

.wc-divider {
  width: 100%;
  height: 1rpx;
  background: rgba(255, 255, 255, 0.25);
  margin: 24rpx 0 18rpx;
}

.wc-name {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  color: #ffffff;
}

.wc-btn {
  width: 100%;
  height: 88rpx;
  margin-top: 32rpx;
  border-radius: 999rpx;
  background: linear-gradient(180deg, #ffe9a8, #ffcf5c);
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  box-shadow: 0 10rpx 22rpx -10rpx rgba(255, 180, 40, 0.75);
  text { color: #7a1f00; font-size: 30rpx; font-weight: 900; }
}

.wc-skip {
  margin-top: 20rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.7);
}

.coupon-picker-sheet {
  width: 100%;
  max-height: 76vh;
  background: #fff;
  border-radius: 32rpx 32rpx 0 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  animation: slide-up 0.25s ease;
}

.cp-head {
  position: relative;
  flex-shrink: 0;
  padding: 28rpx 32rpx 18rpx;
  text-align: center;
}

.cp-title {
  font-size: 32rpx;
  font-weight: 900;
  color: var(--text-1);
}

.cp-close {
  position: absolute;
  right: 20rpx;
  top: 16rpx;
  width: 64rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: 34rpx;
  line-height: 64rpx;
  text-align: center;
}

.cp-list {
  flex: 1;
  min-height: 0;
  padding: 0 24rpx calc(24rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.cp-option {
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 22rpx 20rpx;
  margin-bottom: 16rpx;
  border-radius: 20rpx;
  border: 2rpx solid #edf0f2;
  background: #fafbfc;
  box-sizing: border-box;
}

.cp-option--on {
  border-color: var(--brand);
  background: #ecfbf3;
}

.cp-option--disabled {
  opacity: .5;
}

.cp-option-amount {
  flex-shrink: 0;
  min-width: 108rpx;
  text-align: center;
  /* 券面额用红金色而不是品牌绿，跟"选中态"用色分开：绿色始终代表"这个选项被选中"，
     红金色代表"这是一张券"，两套含义混用同一个颜色会互相干扰。 */
  text { color: #ff3018; font-size: 40rpx; font-weight: 900; }
}

.cp-option-main {
  flex: 1;
  min-width: 0;
}

.cp-option-name {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  color: var(--text-1);
}

.cp-option-cond {
  display: block;
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--text-3);
}

.cp-radio-icon {
  flex-shrink: 0;
  width: 44rpx;
  height: 44rpx;
  color: #d7dce2;
  font-size: 42rpx;
  line-height: 44rpx;
  text-align: center;
}

.cp-option--on .cp-radio-icon {
  color: var(--brand);
}

.cp-empty {
  padding: 64rpx 0;
  text-align: center;
  text { color: var(--text-3); font-size: 26rpx; }
}
</style>



















































































