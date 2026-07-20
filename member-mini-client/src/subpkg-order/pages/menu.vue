<template>
  <view class="order-page">

    
    <view class="shop-header">
      <view class="shop-title-main">
        <text class="shop-name">{{ shopName }}</text>
        <view class="shop-meta-row" @click="showTableHint">
          <text class="shop-table-text">{{ tableDisplayText }}</text>
          <text class="shop-meta-dot">路</text>
          <text class="shop-mode-text">{{ orderModeDisplayText }}</text>
          <text class="shop-meta-arrow">鈥</text>
        </view>
      </view>
    </view>

    
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
          <text>{{ cat }}</text>
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
          <text class="reorder-label">鍐嶆潵涓€鍗</text>
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
            <text class="reorder-all-text">鍏ㄩ儴鍐嶆潵涓€娆</text>
          </view>
        </view>

        <view v-if="!allDishes.length" class="empty-menu">
          <text class="empty-title">暂无菜品</text>
          <text class="empty-desc">菜单加载失败</text>
          <view class="empty-retry" @click="loadMenu"><text>重新加载</text></view>
        </view>
        <view v-for="(cat, catIdx) in categories" :key="cat" :id="`cat-sec-${catIdx}`">
          <view class="cat-divider"><view class="cat-divider-line"></view><text class="cat-divider-text">{{ cat }}</text><view class="cat-divider-line"></view></view>
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
                @error="markDishImageFailed(dish.id)"
              />
              <view v-else class="dish-placeholder">
                <view class="dish-placeholder-icon">
                  <view class="dish-placeholder-plate"></view>
                  <view class="dish-placeholder-stick dish-placeholder-stick--left"></view>
                  <view class="dish-placeholder-stick dish-placeholder-stick--right"></view>
                </view>
              </view>
              <view v-if="isSoldOut(dish)" class="dish-soldout-mask"><text>宸插敭缃</text></view>
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
                  <text class="dish-price-currency">楼</text>
                  <text class="dish-price-amount">{{ dishPriceText(dish) }}</text>
                  <text v-if="dishPriceSuffix(dish)" class="dish-price-suffix">{{ dishPriceSuffix(dish) }}</text>
                </view>
                <view class="dish-counter" @click.stop>
                  <view v-if="isSoldOut(dish)" class="soldout-action" @click.stop><text>宸插敭缃</text></view>
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
                      <view class="counter-touch" @click.stop="removeFromCart(dish)"><view class="counter-btn minus"><text>-</text></view></view>
                      <text class="counter-num" :class="{ 'counter-num--pulse': qtyPulseKey === dish.id }">{{ cartCount(dish.id) }}</text>
                      <view class="counter-touch" @click.stop="addToCart(dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': addPressKey === dish.id }"><text>+</text></view></view>
                    </view>
                    <view v-else class="counter-touch" @click.stop="addToCart(dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': addPressKey === dish.id }"><text>+</text></view></view>
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
            <text class="ht-section-sub">绮鹃€夋嫑鐗岃彍鍝</text>
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
                <view class="ht-feature-plate"></view>
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
                  <text class="ht-feature-yen">楼</text>
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
            <text class="ht-section-title">鍐嶆潵涓€鍗</text>
            <text class="ht-section-action" @click="handleHomeReorderAll">鍏ㄩ儴鍐嶆潵涓€娆</text>
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
        <view class="member-identity-card">
          <view class="member-avatar"><text>{{ bannerInfo.nameChar }}</text></view>
          <view class="member-identity-main">
            <text class="member-level">{{ memberLevelLabel }}</text>
            <text class="member-growth-text">{{ memberGrowthText }}</text>
            <view v-if="memberUpgradeText" class="member-progress-wrap">
              <view class="member-progress-track"><view class="member-progress-fill" :style="{ width: memberProgressPercent + '%' }"></view></view>
              <text class="member-upgrade-text">{{ memberUpgradeText }}</text>
            </view>
          </view>
          <view class="member-level-pill"><text>{{ memberLevelLabel }}</text></view>
        </view>

        <view class="member-assets-card">
          <view class="member-asset-item" @click="goBalanceDetail">
            <text class="member-asset-value">楼{{ bannerInfo.balance.toFixed(2) }}</text>
            <text class="member-asset-label">余额</text>
            <text class="member-asset-hint">可用于下单支付</text>
          </view>
          <view class="member-asset-divider"></view>
          <view class="member-asset-item" @click="uni.navigateTo({ url: '/subpkg-member/pages/points' })">
            <text class="member-asset-value">{{ bannerInfo.points || 0 }}</text>
            <text class="member-asset-label">积分</text>
            <text class="member-asset-hint">消费1元得1积分</text>
          </view>
          <view class="member-asset-divider"></view>
          <view class="member-asset-item" @click="uni.navigateTo({ url: '/subpkg-coupon/pages/list' })">
            <text class="member-asset-value">{{ bannerInfo.couponCount }}</text>
            <text class="member-asset-label">浼樻儬鍒</text>
            <text class="member-asset-hint">涓嬪崟鏃惰嚜鍔ㄦ姷鎵</text>
          </view>
        </view>

        <view class="member-main-action-card">
          <text class="member-action-title">您有{{ bannerInfo.couponCount }}张优惠券可用</text>
          <text class="member-action-desc">查看会员权益享受更多优惠</text>
          <view class="member-action-btn" @click="goOrderFromMember"><text>鍘荤偣椁</text></view>
        </view>

        <view v-if="usableMemberCoupons.length" class="member-section">
          <text class="member-section-title">可用优惠券</text>
          <view class="member-coupon-list">
            <view v-for="coupon in usableMemberCoupons" :key="coupon.id || coupon.coupon_id || coupon.name" class="member-coupon-card" @click="useMemberCoupon(coupon)">
              <view class="member-coupon-value">
                <text class="member-coupon-yen">楼</text>
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
          <view class="member-service-row" @click="goBalanceDetail">
            <text>余额明细</text><text class="member-service-arrow">鈥</text>
          </view>
          <view class="member-service-row" @click="uni.navigateTo({ url: '/subpkg-member/pages/points' })">
            <text>积分明细</text><text class="member-service-arrow">鈥</text>
          </view>
          <view class="member-service-row" @click="uni.navigateTo({ url: '/subpkg-coupon/pages/list' })">
            <text>浼樻儬鍒</text><text class="member-service-arrow">鈥</text>
          </view>
        </view>
      </view>
      <view v-else-if="hasCustomerIdentity" class="card-tab-empty">
        <text class="cte-title">会员中心</text>
        <text class="cte-desc">普通会员</text>
        <view class="cte-btn cte-btn-plain" @click="loadMemberStatus">
          <text>{{ memberLoading ? '\u52a0\u8f7d\u4e2d...' : '\u91cd\u65b0\u52a0\u8f7d' }}</text>
        </view>
        <text class="cte-secondary" @click="goOrderFromMember">鍘荤偣椁</text>
      </view>
      <view v-else class="card-tab-empty">
        <text class="cte-title">会员中心</text>
        <text class="cte-desc">鐧诲綍鍚庝韩鍙椾細鍛樹紭鎯</text>
        <button
          class="cte-btn"
          open-type="getPhoneNumber"
          :disabled="memberAuthorizing"
          @getphonenumber="handleMemberCardAuth"
        >
          <text>{{ memberAuthorizing ? '\u6388\u6743\u4e2d...' : '\u67e5\u770b\u4f1a\u5458\u6743\u76ca' }}</text>
        </button>
        <text class="cte-secondary" @click="goOrderFromMember">鍘荤偣椁</text>
      </view>
    </scroll-view>

    <!-- 闂傚倸鍊烽懗鍫曞箠閹剧粯鍋ら柕濞炬櫅閸ㄥ倿鏌ｉ悢绋款棎闁?Tab -->
    <view v-show="activeTab === 'mine'" class="tab-scroll tab-mine-redirect">
    </view>

    <view v-if="activeTab === 'order' && myOrders.length" class="order-status-entry" @click="viewOrderDetail">
      <view class="order-status-entry-dot"></view>
      <view class="order-status-entry-copy">
        <text class="order-status-entry-title">查看本桌订单</text>
        <text class="order-status-entry-desc">{{ tableOrderStatusTitle }}</text>
      </view>
      <text v-if="pendingOrderCount > 0" class="order-status-entry-count">{{ pendingOrderCount }}</text>
      <text class="order-status-entry-arrow">鈥</text>
    </view>

    
    <view v-show="activeTab === 'order'" class="cart-bar" :class="{ 'has-items': totalCount > 0 }">
      <view class="cart-main" @click="totalCount > 0 ? openCart() : null">
        
        <view class="cart-icon-wrap" :class="{ 'cart-icon-wrap--pulse': cartIconPulse }">
          <view class="cart-icon-svg"></view>
          <view v-if="totalCount > 0" class="cart-badge" :class="{ 'cart-badge--pulse': cartBadgePulse }">
            <text>{{ cartBadgeText }}</text>
          </view>
        </view>

        
        <view class="cart-info">
          <template v-if="totalCount > 0">
            <text class="cart-price" :class="{ 'cart-price--highlight': amountPulse }">楼{{ formatPrice(totalPrice) }}</text>
            <text class="cart-tip">鍏眥{ totalCount }}浠</text>
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
          <text>鍘荤粨绠</text>
        </view>
      </view>
    </view>

    
    <view class="bottom-nav">
      <view :class="['bn-item', { active: activeTab === 'home' }]" @click="activeTab = 'home'">
        <text class="bn-label">首页</text>
      </view>
      <view :class="['bn-item', { active: activeTab === 'order' }]" @click="activeTab = 'order'">
        <text class="bn-label">点餐</text>
        <view v-if="totalCount > 0 && activeTab !== 'order'" class="bn-dot"></view>
      </view>
      <view :class="['bn-item', { active: activeTab === 'card' }]" @click="switchToCard">
        <text class="bn-label">会员</text>
        <view v-if="bannerInfo && bannerInfo.couponCount > 0 && activeTab !== 'card'" class="bn-dot"></view>
      </view>
      <view :class="['bn-item', { active: activeTab === 'mine' }]" @click="goMine">
        <text class="bn-label">我的</text>
      </view>
    </view>

    
    <!-- Order confirmation sheet -->
    <view v-if="showCart" class="mask" @click="closeOrderConfirm">
      <view class="cart-sheet order-confirm-sheet" @click.stop>
        <view class="order-confirm-head">
          <text class="order-confirm-title">{{ confirmationText.title }}</text>
          <text class="order-confirm-close" @click="closeOrderConfirm">{{ confirmationText.close }}</text>
        </view>

        <scroll-view class="order-confirm-content" scroll-y>
          <view class="order-summary-card" :class="{ 'order-summary-card--missing': !tableNo }">
            <view class="order-summary-topline">
              <view class="summary-service">
                <view class="summary-mode-pill"><text>{{ orderModeText.dineIn }}</text></view>
                <view class="summary-table-line">
                  <text class="summary-table-label">{{ confirmationText.tableLabel }}</text>
                  <text class="summary-table-no">{{ tableNo || orderModeText.unknownTable }}</text>
                </view>
              </view>
              <text class="summary-table-tip">{{ tableNo ? confirmationText.tableTip : confirmationText.tableMissing }}</text>
            </view>
            <view class="order-summary-subline">
              <text>{{ confirmationText.itemCountPrefix }}{{ totalCount }}{{ confirmationText.itemCountSuffix }}</text>
              <text>{{ prepareHint }}</text>
            </view>
          </view>

          <view class="confirm-card selected-items-section">
            <view class="selected-items-summary" @click="toggleItemsExpanded">
              <view class="selected-items-title-wrap">
                <text class="selected-items-title">{{ confirmationText.selectedItems }}({{ totalCount }})</text>
                <text class="selected-items-sub">{{ itemsExpanded ? confirmationText.itemEditHint : confirmationText.itemFoldHint }}</text>
              </view>
              <view class="selected-items-action">
                <text class="selected-items-amount">{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text>
                <text class="selected-items-toggle">{{ itemsExpanded ? confirmationText.collapse : confirmationText.expand }}</text>
              </view>
            </view>
            <view v-if="itemsExpanded" class="cart-items-panel">
              <scroll-view class="cart-items" scroll-y>
                <view v-for="item in cartItems" :key="item.specKey || item.id" class="cart-row">
                  <text class="cart-row-emoji">{{ item.emoji || confirmationText.noIcon }}</text>
                  <view class="cart-row-main">
                    <text class="cart-row-name">{{ item.name }}</text>
                    <text v-if="item.specLabel" class="cart-row-spec">{{ item.specLabel }}</text>
                  </view>
                  <view class="cart-row-right">
                    <view class="counter-btn minus sm" @click="removeFromCart(item)"><text>-</text></view>
                    <text class="counter-num" :class="{ 'counter-num--pulse': qtyPulseKey === (item.specKey || item.id) }">{{ item.qty }}</text>
                    <view class="counter-btn plus sm" @click="increaseCartItem(item)"><text>+</text></view>
                    <text class="cart-row-price">{{ confirmationText.currency }}{{ formatPrice(item.price * item.qty) }}</text>
                  </view>
                </view>
              </scroll-view>
              <view class="cart-clear-line" @click="clearCart"><text>{{ confirmationText.clear }}</text></view>
            </view>
          </view>

          <view class="confirm-card order-preference-section">
            <view class="remark-row order-remark-row">
              <text class="remark-label">{{ confirmationText.orderRemark }}</text>
              <input class="remark-input" v-model="remark" :placeholder="confirmationText.orderRemarkPlaceholder" placeholder-class="remark-placeholder" maxlength="60" />
            </view>
          </view>

          <view class="confirm-card price-summary-card">
            <view class="price-row"><text>{{ confirmationText.goodsAmount }}</text><text>{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text></view>
            <view class="price-row price-row--clickable">
              <text>{{ confirmationText.coupon }}</text>
              <text v-if="discountAmount > 0" class="price-discount">-{{ confirmationText.currency }}{{ discountAmount.toFixed(2) }} {{ confirmationText.arrow }}</text>
              <text v-else-if="availableCoupons.length > 0" class="price-muted">{{ availableCoupons.length }}{{ confirmationText.couponAvailable }} {{ confirmationText.arrow }}</text>
              <text v-else class="price-muted">{{ confirmationText.couponNone }} {{ confirmationText.arrow }}</text>
            </view>
            <view v-if="estimatedBalanceAvailable > 0" class="price-row balance-row" @click="useBalance = !useBalance">
              <view class="balance-row-left"><text>{{ confirmationText.balanceDeduction }}</text><text class="balance-row-desc">{{ confirmationText.balanceAvailable }} {{ confirmationText.currency }}{{ estimatedBalanceAvailable.toFixed(2) }}</text></view>
              <view class="pbl-switch" :class="{ 'pbl-switch--on': useBalance }"><view class="pbl-switch-thumb"></view></view>
            </view>
            <view v-if="useBalance && estimatedBalanceDeduction > 0" class="price-row">
              <text>{{ confirmationText.balanceUsed }}</text>
              <text class="price-discount">-{{ confirmationText.currency }}{{ estimatedBalanceDeduction.toFixed(2) }}</text>
            </view>
            <view class="price-row price-row--payable">
              <text>{{ wechatPayAmount > 0 ? confirmationText.wechatPay : confirmationText.payable }}</text>
              <text>{{ confirmationText.currency }}{{ wechatPayAmount.toFixed(2) }}</text>
            </view>
          </view>
        </scroll-view>

        <view class="order-confirm-bottom">
          <view class="checkout-btn-full" :class="{ 'checkout-btn-full--disabled': !canSubmitOrder || ordering || paying }" @click="goCheckout">
            <text>{{ payButtonText }}</text>
          </view>
        </view>
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
          <view class="checkout-auth-row checkout-auth-row--amount"><text>{{ authSheetText.amount }}</text><text>{{ confirmationText.currency }}{{ wechatPayAmount.toFixed(2) }}</text></view>
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
    <view v-if="showOrders" class="mask" @click="showOrders = false">
      <view class="orders-sheet" @click.stop>
        <view class="orders-sheet-head">
          <text class="orders-sheet-title">本桌订单</text>
          <text class="orders-sheet-close" @click="showOrders = false">脳</text>
        </view>

        <scroll-view class="orders-list" scroll-y>
          <view class="table-status-card">
            <view>
              <view class="table-status-mode">
                <text>堂食</text>
              </view>
              <text class="table-status-no">桌号: {{ tableNo || orderModeText.unknownTable }}</text>
            </view>
            <view class="table-status-copy">
              <text class="table-status-main">{{ tableOrderStatusTitle }}</text>
              <text class="table-status-sub">{{ tableOrderStatusHint }}</text>
            </view>
          </view>

          <view class="order-progress-card">
            <view v-for="step in tableOrderTimeline" :key="step.key" class="order-progress-step" :class="{ active: step.active, done: step.done }">
              <view class="order-progress-dot"></view>
              <view class="order-progress-copy">
                <text class="order-progress-title">{{ step.label }}</text>
                <text v-if="step.desc" class="order-progress-desc">{{ step.desc }}</text>
              </view>
            </view>
          </view>

          <view v-if="currentTableOrder" class="current-order-card">
            <view class="current-order-head">
              <view>
                <text class="current-order-title">当前订单</text>
                <text class="current-order-no">#{{ currentTableOrder.orderNo }}</text>
              </view>
              <text class="current-order-total">楼{{ Number(currentTableOrder.total || 0).toFixed(2) }}</text>
            </view>
            <view class="current-order-summary">
              <text>{{ tableOrderStatusTitle }}</text>
              <text>鍏眥{ currentOrderItemCount }}浠</text>
            </view>
            <view v-if="currentTableOrder.items && currentTableOrder.items.length" class="current-order-items current-order-items--visible">
              <view v-for="(item, idx) in currentTableOrder.items" :key="item.specKey || item.id || item.name || idx" class="order-detail-row">
                <view class="order-detail-main">
                  <text class="order-detail-name">{{ orderItemName(item) }}</text>
                  <text v-if="orderItemSpecText(item)" class="order-detail-spec">{{ orderItemSpecText(item) }}</text>
                </view>
                <text class="order-detail-qty">脳{{ orderItemQty(item) }}</text>
                <text class="order-detail-amount">楼{{ formatPrice(orderItemAmount(item)) }}</text>
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
                  <text>#{{ order.orderNo }} 脳{{ orderItemCount(order) }}</text>
                  <text>楼{{ Number(order.total || 0).toFixed(2) }}</text>
                </view>
                <view v-if="(order.items || []).length" class="history-order-items">
                  <view v-for="(item, idx) in order.items" :key="item.specKey || item.id || item.name || idx" class="history-order-item-row">
                    <text>{{ orderItemName(item) }} 脳{{ orderItemQty(item) }}</text>
                    <text>楼{{ formatPrice(orderItemAmount(item)) }}</text>
                  </view>
                </view>
              </view>
            </view>
          </view>
        </scroll-view>

        <view class="orders-actions">
          <view class="orders-primary-btn" @click="showOrders = false">
            <text>关闭</text>
          </view>
          <view class="orders-secondary-btn" @click="showAllOrders = !showAllOrders">
            <text>{{ showAllOrders ? '\u6536\u8d77\u5386\u53f2\u8ba2\u5355' : '\u67e5\u770b\u5168\u90e8\u8ba2\u5355' }}</text>
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
            :src="dishImage(specDish)"
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
          <view class="spec-sheet-close" @click="cancelSpec"><text>{{ confirmationText.close }}</text></view>
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
            <view class="spec-group-label"><text class="spec-group-name">{{ specText.itemRemark }}</text><text class="spec-optional">{{ specText.optional }}</text></view>
            <textarea class="item-remark-input" v-model="itemRemark" maxlength="50" :placeholder="specText.itemRemarkPlaceholder" />
            <text class="item-remark-count">{{ itemRemark.length }}/50</text>
          </view>
          <view class="spec-qty-row"><text class="spec-group-name">{{ specText.qty }}</text><view class="spec-counter-row"><view class="counter-btn minus" @click="specQty > 1 && specQty--"><text>-</text></view><text class="counter-num">{{ specQty }}</text><view class="counter-btn plus" @click="specQty++"><text>+</text></view></view></view>
        </scroll-view>
        <view class="spec-footer">
          <view class="spec-confirm-btn" :class="{ 'spec-confirm-btn--disabled': !canGoNextSpec }" @click="handleSpecPrimary"><text>{{ specPrimaryText }}</text></view>
        </view>
      </view>
    </view>

    <view v-if="storeClosed || tableSessionClosed" class="closed-mask">
      <view class="closed-card">
        <text class="closed-icon">{{ '\u4f11' }}</text>
        <text class="closed-title">{{ tableSessionClosed ? '\u672c\u684c\u7528\u9910\u5df2\u7ed3\u675f' : shopName + ' \u5f53\u524d\u4f11\u606f\u4e2d' }}</text>
        <text class="closed-desc">{{ tableSessionClosed ? tableSessionClosedNotice : (closedNotice || '\u8425\u4e1a\u65f6\u95f4\u8bf7\u53c2\u8003\u95e8\u5e97\u516c\u544a') }}</text>
        <view class="closed-btn" @click="tableSessionClosed ? (showOrders = true) : (storeClosed = false)"><text>{{ tableSessionClosed ? '\u67e5\u770b\u672c\u684c\u8ba2\u5355' : '\u4ecd\u8981\u6d4f\u89c8\u83dc\u5355' }}</text></view>
      </view>
    </view>

    
    <view v-if="loadError && !loading" class="loading-mask">
      <text class="loading-text">菜单加载失败</text>
      <view class="retry-btn" @click="loadMenu"><text>重新加载</text></view>
    </view>

    
    <view v-if="loading" class="loading-mask">
      <view class="loading-ring" />
      <text class="loading-text">鑿滃崟鍔犺浇涓?..</text>
    </view>

    
    <view v-if="showReview" class="mask review-mask" @click.self="closeReview">
      <view class="review-card">
        <text class="review-title">用餐评价</text>
        <text class="review-sub">您的评价对我们很重要</text>
        <view class="review-stars">
          <text
            v-for="n in 5"
            :key="n"
            class="review-star"
            :class="reviewRating >= n ? 'review-star--on' : ''"
            @click="reviewRating = n"
          >鈽</text>
        </view>
        <view class="review-hint-row">
          <text class="review-hint">{{ reviewHintText }}</text>
        </view>
        <textarea
          v-model="reviewContent"
          class="review-textarea"
          placeholder="\u53ef\u9009\uff1a\u5199\u4e0b\u4f60\u7684\u7528\u9910\u611f\u53d7"
          maxlength="100"
          auto-height
        />
        <view class="review-actions">
          <view class="review-btn-skip" @click="closeReview"><text>跳过</text></view>
          <view class="review-btn-submit" :class="reviewRating === 0 ? 'review-btn-submit--disabled' : ''" @click="doSubmitReview"><text>提交评价</text></view>
        </view>
      </view>
    </view>

  </view>
</template>

<script>
import { ref, computed, watch, nextTick } from 'vue'
import { getMenuItems, getShopInfo, createOrder, cancelOrder, submitReview, createWxPayOrder, getCurrentDiningOrders, getOrderStatus } from '@/api/order'
import { getCustomerCoupons } from '@/api/coupon'
import { getMemberProfile, joinByEntranceCode, resolveDiningSession, bindDiningParticipant } from '@/api/auth'
import { saveCustomerSession, clearCustomerSession } from '@/utils/auth'
const wxLogin = () => new Promise((resolve, reject) => {
  uni.login({
    provider: 'weixin',
    success: (res) => res.code ? resolve(res.code) : reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5')),
    fail: () => reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u5c0f\u7a0b\u5e8f\u73af\u5883'))
  })
})

export default {
  setup() {
    const tableNo = ref('')
    const shopId = ref('')
    const shopName = ref(uni.getStorageSync('tenant_name') || '\u672a\u6765\u9910\u5385')
    const diningSessionId = ref(uni.getStorageSync('dining_session_id') || '')
    const diningParticipantToken = ref(uni.getStorageSync('dining_participant_token') || '')
    const diningClientId = ref(uni.getStorageSync('dining_client_id') || '')
    const orderModeText = {
      dineIn: '\u5802\u98df',
      delivery: '\u5916\u5356',
      tableLabel: '\u684c\u53f7',
      unknownTable: '\u672a\u8bc6\u522b'
    }
    const getOrCreateDiningClientId = () => {
      if (!diningClientId.value) {
        diningClientId.value = 'dc_' + Date.now() + '_' + Math.random().toString(36).slice(2, 12)
        uni.setStorageSync('dining_client_id', diningClientId.value)
      }
      return diningClientId.value
    }

    const persistDiningContext = (data = {}) => {
      diningSessionId.value = data.dining_session_id || diningSessionId.value || ''
      diningParticipantToken.value = data.participant_token || diningParticipantToken.value || ''
      diningClientId.value = data.client_id || diningClientId.value || ''
      if (diningSessionId.value) uni.setStorageSync('dining_session_id', diningSessionId.value)
      if (data.participant_id) uni.setStorageSync('dining_participant_id', data.participant_id)
      if (diningParticipantToken.value) uni.setStorageSync('dining_participant_token', diningParticipantToken.value)
      if (diningClientId.value) uni.setStorageSync('dining_client_id', diningClientId.value)
    }

    const ensureDiningSession = async (force = false) => {
      const tenantId = shopId.value || uni.getStorageSync('tenant_id') || ''
      const table = tableNo.value || uni.getStorageSync('table_no') || ''
      if (!tenantId || !table) return false
      if (tableSessionClosed.value && !force) return false
      if (!force && diningSessionId.value && diningParticipantToken.value) return true
      const res = await resolveDiningSession({
        tenant_id: tenantId,
        table_no: table,
        client_id: getOrCreateDiningClientId(),
        participant_token: diningParticipantToken.value || undefined,
      })
      if (res?.code !== 200 || !res.data) return false
      persistDiningContext(res.data)
      tableSessionClosed.value = false
      return true
    }

    const bindCurrentDiningParticipant = async () => {
      if (!diningParticipantToken.value) return
      const tenantId = shopId.value || uni.getStorageSync('tenant_id') || ''
      if (!tenantId) return
      try {
        await bindDiningParticipant({ tenant_id: tenantId, participant_token: diningParticipantToken.value })
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
        items: Array.isArray(order.items) ? order.items.map(i => ({ ...i, qty: Number(i.qty || 0), price: Number(i.price || 0) })) : [],
        total: Number(order.total || 0),
        createdAt: timeStr,
        createdTs: Number.isNaN(created.getTime()) ? Date.now() : created.getTime(),
        table: order.table_no || tableNo.value,
      }
    }

    const syncDiningOrders = async () => {
      const query = diningOrderQuery()
      if (!query.tenant_id || !query.dining_session_id || !query.participant_token) return false
      try {
        const res = await getCurrentDiningOrders(query)
        if (res?.code !== 200) return false
        const sessionStatus = String(res.data?.session_status || '').toUpperCase()
        tableSessionClosed.value = res.data?.closed === true || ['CLOSED', 'EXPIRED'].includes(sessionStatus)
        if (tableSessionClosed.value) {
          tableSessionClosedNotice.value = '\u672c\u684c\u7528\u9910\u5df2\u7ed3\u675f\uff0c\u5982\u9700\u7ee7\u7eed\u70b9\u9910\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u8fdb\u5165\u65b0\u4e00\u684c'
        }
        myOrders.value = (res.data?.orders || []).map(mapServerOrder)
        saveMyOrders()
        return true
      } catch (e) {
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
      title: '\u786e\u8ba4\u8ba2\u5355', tableLabel: '\u684c\u53f7', tableTip: '\u8bf7\u786e\u8ba4\u684c\u53f7\u6b63\u786e', tableMissing: '\u672a\u8bc6\u522b\u684c\u53f7\uff0c\u8bf7\u91cd\u65b0\u626b\u7801',
      itemCountPrefix: '\u5171', itemCountSuffix: '\u4ef6\u5546\u54c1', selectedItems: '\u5df2\u9009\u5546\u54c1', itemFoldHint: '\u9700\u8981\u4fee\u6539\u65f6\u518d\u5c55\u5f00', itemEditHint: '\u53ef\u4fee\u6539\u6570\u91cf', expand: '\u5c55\u5f00 >', collapse: '\u6536\u8d77', clear: '\u6e05\u7a7a\u5df2\u9009\u5546\u54c1',
      remark: '\u5907\u6ce8', remarkPlaceholder: '\u5176\u4ed6\u8981\u6c42\u2026', goodsAmount: '\u5546\u54c1\u91d1\u989d', coupon: '\u4f18\u60e0\u5238', couponAvailable: '\u5f20\u53ef\u7528', couponNone: '\u6682\u65e0\u53ef\u7528', noThreshold: '\u65e0\u95e8\u69db', thresholdPrefix: '\u6ee1',
      balanceDeduction: '\u4f59\u989d\u62b5\u6263', balanceAvailable: '\u53ef\u7528', balanceUsed: '\u5df2\u62b5\u6263', payable: '\u5e94\u4ed8\u91d1\u989d', wechatPay: '\u5fae\u4fe1\u652f\u4ed8', payNow: '\u7acb\u5373\u652f\u4ed8', balancePay: '\u4f59\u989d\u652f\u4ed8',
      orderRemark: '\u6574\u5355\u5907\u6ce8', orderRemarkPlaceholder: '\u4f8b\u5982\uff1a\u4e00\u8d77\u4e0a\u83dc\u3001\u5168\u90e8\u6253\u5305\u3001\u9700\u8981\u513f\u7ae5\u9910\u5177', unavailable: '\u5f53\u524d\u4e0d\u53ef\u4e0b\u5355', confirming: '\u6b63\u5728\u786e\u8ba4\u8ba2\u5355\u2026', paying: '\u6b63\u5728\u53d1\u8d77\u652f\u4ed8\u2026', prepareHint: '\u4e0b\u5355\u540e\u5546\u5bb6\u5f00\u59cb\u5236\u4f5c', currency: '\u00a5', close: 'x', arrow: '>', noIcon: ''
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
    const showCart = ref(false)
    const itemsExpanded = ref(false)
    const showSuccess = ref(false)
    const earnedCoupon = ref(null)
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
    const payAmount = ref(0)
    const pendingOrderId = ref('')   // 待支付订单ID
    const useBalance = ref(false)    // 是否使用余额
    const balanceAvailable = ref(0)  // 可用余额
    const balanceDeducted = ref(0)   // 已扣余额
    const actualPayAmount = computed(() =>
      useBalance.value ? Math.max(payAmount.value - balanceAvailable.value, 0) : payAmount.value
    )
    const showReview = ref(false)
    const reviewRating = ref(0)
    const reviewContent = ref('')
    const reviewOrderId = ref('')
    const reviewHintText = computed(() => {
      const hints = ['', '\u5f88\u4e0d\u6ee1\u610f', '\u8fd8\u9700\u6539\u8fdb', '\u4e00\u822c', '\u6ee1\u610f', '\u975e\u5e38\u6ee1\u610f']
      return hints[reviewRating.value] || ''
    })
    let statusPollTimer = null

    const myOrders = ref([]) // 我的订单
    const showOrders = ref(false)
    const showAllOrders = ref(false)
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
      if (hasCustomerIdentity.value && !bannerInfo.value) loadMemberStatus()
    }
    const goMine = () => uni.navigateTo({ url: '/pages/mine/mine' })
    const memberLevelLabel = computed(() => bannerInfo.value?.levelLabel || '\u666e\u901a\u4f1a\u5458')
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
        })
        if (res?.code !== 200) {
          uni.showToast({ title: '\u5df2\u52a0\u5165' + added + '\u4efd', icon: 'success', duration: 1200 })
          return
        }
        saveCustomerSession(res.data || {})
        await bindCurrentDiningParticipant()
        await loadMemberStatus()
        activeTab.value = 'card'
        uni.showToast({ title: '\u5df2\u767b\u5f55', icon: 'none' })
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
    const goBalanceDetail = () => uni.navigateTo({ url: '/subpkg-member/pages/consumptions' })

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

    // 瑙勬牸閫夋嫨鐩稿叧鐘舵€?
    const showSpecSheet = ref(false)
    const specDish = ref({})
    const specQty = ref(1)
    const specStep = ref(1)
    const selectedSpecs = ref({})
    const selectedExtras = ref([])
    const itemRemark = ref('') // { groupName: [optName] }
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
    const requiredGroupPrompt = (group) => /鍙ｅ懗|鍛抽亾|杈ｅ害/.test(group?.name || '') ? specText.chooseTaste : specText.chooseSpec
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
      return [...myOrders.value]
        .filter(order => !['cancelled', 'rejected'].includes(normalizeOrderStatus(order.status)))
        .sort((a, b) => activeOrderRank(a) - activeOrderRank(b))[0] || myOrders.value[0]
    })

    const historyTableOrders = computed(() =>
      myOrders.value.filter(order => !currentTableOrder.value || order.id !== currentTableOrder.value.id)
    )

    const currentTableOrderStatus = computed(() => normalizeOrderStatus(currentTableOrder.value?.status || orderStatus.value))

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
        { key: 'paid', status: 'pending', label: '\u5df2\u652f\u4ed8', desc: currentTableOrder.value?.createdAt || '' },
        { key: 'preparing', status: 'preparing', label: '\u5546\u5bb6\u5df2\u63a5\u5355', desc: currentIndex >= 1 ? '\u53a8\u623f\u5f00\u59cb\u5904\u7406' : '' },
        { key: 'done', status: 'done', label: '\u5df2\u4e0a\u9910', desc: currentIndex >= 2 ? '\u9910\u54c1\u5df2\u5b8c\u6210' : '' },
        { key: 'settled', status: 'settled', label: '\u5df2\u5b8c\u6210', desc: currentIndex >= 3 ? '\u672c\u684c\u5df2\u7ed3\u675f' : '' },
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
        return item.specifications.map(spec => spec.value || spec.name).filter(Boolean).join(' 路 ')
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

    const tableTotalSpent = computed(() =>
      myOrders.value
        .filter(o => !['cancelled', 'rejected'].includes(o.status))
        .reduce((s, o) => s + (Number(o.total) || 0), 0)
    )

    const statusLabel = (s) => ({ pending: '\u7b49\u5f85\u63a5\u5355', preparing: '\u5907\u9910\u4e2d', done: '\u5df2\u5b8c\u6210', rejected: '\u5df2\u62d2\u5355', cancelled: '\u5df2\u53d6\u6d88', settled: '\u5df2\u7ed3\u8d26' })[s] || s

    const doCancelOrder = (order) => {
      uni.showModal({
        title: '\u53d6\u6d88\u8ba2\u5355',
        content: '\u786e\u8ba4\u53d6\u6d88\u6b64\u8ba2\u5355\u5417\uff1f\u5546\u5bb6\u63a5\u5355\u540e\u65e0\u6cd5\u53d6\u6d88\u3002',
        success: async ({ confirm }) => {
          if (!confirm) return
          try {
            await cancelOrder(order.id)
            order.status = 'cancelled'
            saveMyOrders()
            if (orderId.value === order.id) {
              stopStatusPoll()
              orderStatus.value = 'cancelled'
              showSuccess.value = false
            }
            uni.showToast({ title: '\u5df2\u52a0\u5165' + added + '\u4efd', icon: 'success', duration: 1200 })
          } catch {
            uni.showToast({ title: '\u5df2\u52a0\u5165' + added + '\u4efd', icon: 'success', duration: 1200 })
          }
        }
      })
    }

    const closeReview = () => { showReview.value = false }

    const doSubmitReview = async () => {
      if (reviewRating.value === 0) return
      try {
        await submitReview(reviewOrderId.value, {
          rating: reviewRating.value,
          content: reviewContent.value.trim() || undefined,
        })
        showReview.value = false
        uni.showToast({ title: '\u611f\u8c22\u60a8\u7684\u8bc4\u4ef7', icon: 'none', duration: 2000 })
      } catch {
        uni.showToast({ title: '\u63d0\u4ea4\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5', icon: 'none' })
      }
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
        const res = await getOrderStatus(id)
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
      console.log('[click_close_and_wait]', { order_id: orderId.value })
    }

    const continueOrdering = () => {
      showSuccess.value = false
      cart.value = {}
      specCartItems.value = []
      remark.value = ''
      selectedCouponId.value = null
      activeTab.value = 'order'
      uni.showToast({ title: successText.backToMenu, icon: 'none', duration: 900 })
      console.log('[click_continue_ordering]', { order_id: orderId.value })
    }

    const viewOrderDetail = () => {
      showSuccess.value = false
      refreshAllOrderStatuses()
      showOrders.value = true
      console.log('[click_view_order_detail]', { order_id: orderId.value })
    }
    function startStatusPoll(id) {
      stopStatusPoll()
      const baseUrl = uni.getStorageSync('api_base_url') || 'https://api.zhangbaiyang.com/api'
      statusPollTimer = setInterval(() => {
刷新订单状态
        uni.request({
          url: baseUrl + '/v1/orders/my',
          method: 'GET',
          data: { order_id: id },
          header: { Authorization: 'Bearer ' + (uni.getStorageSync('customer_token') || '') },
          success: (res) => {
            const body = res.data || {}
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
          },
          fail: () => { /* 忽略轮询失败 */ }
        })
      }, 15000)
    }

    function stopStatusPoll() {
      if (statusPollTimer) { clearInterval(statusPollTimer); statusPollTimer = null }
    }

    async function refreshAllOrderStatuses() {
      if (await syncDiningOrders()) return
      const baseUrl = uni.getStorageSync('api_base_url') || 'https://api.zhangbaiyang.com/api'
      const token = uni.getStorageSync('customer_token') || ''
      const orders = myOrders.value.filter(o => !['settled', 'cancelled', 'rejected'].includes(normalizeOrderStatus(o.status)))
      orders.forEach(order => {
        uni.request({
          url: baseUrl + '/v1/orders/my',
          method: 'GET',
          data: { order_id: order.id },
          header: { Authorization: 'Bearer ' + token },
          success: (res) => {
            const body = res.data || {}
            if (body.code === 200) {
              const newStatus = body.data?.status || order.status
              const rec = myOrders.value.find(o => o.id === order.id)
              if (rec && rec.status !== newStatus) {
                rec.status = newStatus
                saveMyOrders()
              }
            }
          },
          fail: () => {}
        })
      })
    }
    const remark = ref('')
    const remarkChips = ref(['\u4e0d\u8981\u8fa3', '\u5fae\u8fa3', '\u4e0d\u8981\u9999\u83dc', '\u4e0d\u8981\u8471', '\u5c11\u76d0', '\u6253\u5305'])
    const deliveryEnabled = ref(false)
    const availableCoupons = ref([])
    const selectedCouponId = ref(null)
    const selectedCoupon = computed(() =>
      availableCoupons.value.find(c => c.id === selectedCouponId.value) || null
    )
    const discountAmount = computed(() => {
      if (!selectedCoupon.value) return 0
      const min = Number(selectedCoupon.value.min_amount || selectedCoupon.value.threshold_amount || 0)
      if (totalPrice.value < min) return 0
      return Number(selectedCoupon.value.value || selectedCoupon.value.amount || 0)
    })
    const finalPrice = computed(() => Math.max(totalPrice.value - discountAmount.value, 0))
    const estimatedBalanceAvailable = computed(() => {
      const balance = Number(bannerInfo.value?.balance || 0)
      return Math.max(0, Math.min(balance, finalPrice.value))
    })
    const estimatedBalanceDeduction = computed(() => (useBalance.value ? Math.min(estimatedBalanceAvailable.value, finalPrice.value) : 0))
    const wechatPayAmount = computed(() => Math.max(finalPrice.value - estimatedBalanceDeduction.value, 0))
    const prepareHint = computed(() => confirmationText.prepareHint)
    const canSubmitOrder = computed(() => totalCount.value > 0 && !!tableNo.value && !storeClosed.value && !tableSessionClosed.value)
    const payButtonText = computed(() => {
      if (ordering.value) return confirmationText.confirming
      if (paying.value) return confirmationText.paying
      if (tableSessionClosed.value) return '\u672c\u684c\u5df2\u7ed3\u675f'
      if (!canSubmitOrder.value) return confirmationText.unavailable
      if (useBalance.value && wechatPayAmount.value <= 0) return confirmationText.balancePay + ' ' + confirmationText.currency + finalPrice.value.toFixed(2)
      return confirmationText.payNow + ' ' + confirmationText.currency + wechatPayAmount.value.toFixed(2)
    })
    const authPrimaryText = computed(() => {
      if (authActionStatus.value === 'authorizing') return authSheetText.authorizing
      if (authActionStatus.value === 'submitting') return authSheetText.submitting
      if (authActionStatus.value === 'paying') return authSheetText.paying
      if (wechatPayAmount.value <= 0) return authSheetText.confirmFree
      return authSheetText.confirm + ' ' + confirmationText.currency + wechatPayAmount.value.toFixed(2)
    })
    const createPaymentIntent = () => ({
      merchantId: shopId.value,
      tableId: tableNo.value,
      cartSnapshot: cartItems.value.map(item => ({ id: item.id, name: item.orderName || item.name, price: item.price, qty: item.qty, specKey: item.specKey || '' })),
      couponId: selectedCouponId.value || null,
      balanceEnabled: useBalance.value && estimatedBalanceAvailable.value > 0,
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
      let sorted = order.length ? order.filter(c => raw.includes(c)) : [...raw]
      raw.forEach(c => { if (!sorted.includes(c)) sorted.push(c) })
      const hasRecommended = allDishes.value.some(d => {
        const tags = Array.isArray(d.tags) ? d.tags : String(d.tags || '').split(/[,锛孿s]+/).map(t => t.trim()).filter(Boolean)
        return tags.includes('\u63a8\u8350') || tags.includes('\u62db\u724c') || tags.includes('\u70ed\u9500')
      })
      if (hasRecommended) sorted = [RECOMMEND_CAT, ...sorted.filter(c => c !== RECOMMEND_CAT)]
      return sorted
    })

    const dishesByCategory = (cat) => {
      if (cat === RECOMMEND_CAT) {
        return allDishes.value.filter(d => {
          const tags = Array.isArray(d.tags) ? d.tags : String(d.tags || '').split(/[,锛孿s]+/).map(t => t.trim()).filter(Boolean)
          return tags.includes('\u63a8\u8350') || tags.includes('\u62db\u724c') || tags.includes('\u70ed\u9500')
        })
      }
      return allDishes.value.filter((d) => d.category === cat)
    }

    const dishImage = (dish) => dish.image_url || dish.image || dish.cover_image || ''

    const dishTags = (dish) => {
      // 获取菜品标签
      if (Array.isArray(dish.tags) && dish.tags.length) return dish.tags.slice(0, 3)
      if (typeof dish.tags === 'string' && dish.tags.trim()) {
        return dish.tags.split(/[,锛孿s]+/).map(t => t.trim()).filter(Boolean).slice(0, 3)
      }
默认返回空数组
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
      return n % 1 === 0 ? String(n) : String(n)
    }
    const hasSpecs = (dish) => {
      const tags = Array.isArray(dish.tags) ? dish.tags : String(dish.tags || '').split(/[,锛孿s]+/).map(t => t.trim()).filter(Boolean)
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
    const historyItemHasSpecSnapshot = (item) => !!(item?.specKey || item?.specLabel || item?.specifications?.length || /[（(]/.test(String(item?.name || "")))
    const validateHistoryReorderItem = (item) => {
      const dish = findHistoryDish(item)
      if (!dish || isSoldOut(dish)) return { dish, reason: 'unavailable' }
      if (hasSpecs(dish) || historyItemHasSpecSnapshot(item)) return { dish, reason: 'spec_changed' }
      return { dish, reason: '' }
    }
    const showHistoryReorderToast = ({ added = 0, skippedUnavailable = 0, skippedSpec = 0 }) => {
      if (added > 0) {
        let title = '已加入' + added + '份'
        if (skippedUnavailable > 0) title += '，部分菜品已下架或售罄'
        else if (skippedSpec > 0) title += '，部分规格已变更，请重新选择'
        uni.showToast({ title, icon: 'none', duration: 1400 })
        return
      }
      if (skippedUnavailable > 0) {
        uni.showToast({ title: '部分菜品已下架或售罄', icon: 'none', duration: 1400 })
        return
      }
      if (skippedSpec > 0) {
        uni.showToast({ title: '部分规格已变更，请重新选择', icon: 'none', duration: 1400 })
        return
      }
      uni.showToast({ title: '没有可重新加入的菜品', icon: 'none', duration: 1200 })
    }

获取最近订单商品
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
        uni.showToast({ title: '部分菜品已下架或售罄', icon: 'none', duration: 1200 })
        return
      }
      if (check.reason === 'spec_changed') {
        openSpecSheet(check.dish)
        uni.showToast({ title: '部分规格已变更，请重新选择', icon: 'none', duration: 1200 })
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
        uni.showToast({ title: '部分菜品已下架或售罄', icon: 'none', duration: 1200 })
        return
      }
      if (check.reason === 'spec_changed') {
        openSpecSheet(check.dish)
        uni.showToast({ title: '部分规格已变更，请重新选择', icon: 'none', duration: 1200 })
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

    // 会员节省金额
    const memberSavings = computed(() => {
      return cartItems.value.reduce((s, item) => {
        const dish = allDishes.value.find(d => d.id === item.id)
        if (dish && dish.member_price && dish.member_price < dish.price) {
          return s + (dish.price - dish.member_price) * item.qty
        }
        return s
      }, 0)
    })

    // 婊氬姩鐩稿叧鐘舵€?
    const dishScrollTopVal = ref(0)  // 菜品列表滚动位置
    const categoryScrollTarget = ref('')
    const categoryScrollTop = ref(0)
    const categoryItemHeight = 96
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
    let currentScrollTop = 0
    let ignoreScroll = false
    let sectionTops = []             // 分类区域顶部位置

    // 缓存分类区域位置
    const cacheSectionPositions = (retry = 0) => {
      const cats = categories.value
      if (!cats.length) return
      const query = uni.createSelectorQuery()
      query.select('.dish-scroll').boundingClientRect()
      cats.forEach((_, i) => query.select('#cat-sec-' + i).boundingClientRect())
      query.exec((res) => {
        if (!res[0]) {
          if (retry < 5) setTimeout(() => cacheSectionPositions(retry + 1), 300)
          return
        }
        const svTop = res[0].top
        sectionTops = cats.map((cat, i) => ({
          cat,
          top: Math.max(0, (res[i + 1]?.top ?? 0) - svTop + currentScrollTop),
        }))
滚动到顶部时激活第一个分类
        if (currentScrollTop < 10 && cats.length) {
          activeCategory.value = cats[0]
        }
      })
    }

    // 切换分类
    const switchCategory = (cat) => {
      activeCategory.value = cat
      ignoreScroll = true
      setTimeout(() => { ignoreScroll = false }, 600)
      const idx = categories.value.indexOf(cat)
      syncCategoryVisible(cat)
滚动到对应分类区域
      scrollTarget.value = ''
      nextTick(() => { scrollTarget.value = 'cat-sec-' + idx })
    }

    
    let scrollThrottleTimer = null
    const onDishScroll = (e) => {
      currentScrollTop = e.detail.scrollTop
      if (ignoreScroll || !sectionTops.length) return
      if (scrollThrottleTimer) return
      scrollThrottleTimer = setTimeout(() => {
        scrollThrottleTimer = null
        let current = sectionTops[0].cat
        for (const s of sectionTops) {
          if (s.top <= currentScrollTop + 30) current = s.cat
        }
        if (current !== activeCategory.value) {
          activeCategory.value = current
          syncCategoryVisible(current)
        }
      }, 100)
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
      showCart.value = true
      itemsExpanded.value = totalCount.value <= 1
      useBalance.value = estimatedBalanceAvailable.value > 0
      if (uni.getStorageSync('customer_token')) {
        try {
          const res = await getCustomerCoupons('UNUSED')
          const now = Date.now()
          const list = (res?.data || []).filter(c => new Date(c.expire_time || c.valid_end_time || '2099-01-01').getTime() > now)
          availableCoupons.value = list
          const eligible = list.filter(c => totalPrice.value >= Number(c.min_amount || c.threshold_amount || 0))
          if (eligible.length) {
            eligible.sort((a, b) => Number(b.value || b.amount || 0) - Number(a.value || a.amount || 0))
            selectedCouponId.value = eligible[0].id
          } else {
            selectedCouponId.value = null
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
      if (pendingOrderId.value) return confirmPay()
      submitOrder()
    }

    const cancelCheckoutAuth = () => {
      if (authorizing.value) return
      showCheckoutAuth.value = false
    }

    const continuePendingPaymentIntent = async () => {
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
        })
        if (res.code !== 200) {
          authActionStatus.value = 'idle'
          uni.showToast({ title: '\u5df2\u52a0\u5165' + added + '\u4efd', icon: 'success', duration: 1200 })
          return
        }
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

    const submitOrder = async () => {
      if (ordering.value || paying.value) return false
      ordering.value = true
      if (showCheckoutAuth.value) authActionStatus.value = 'submitting'
      try {
        const sessionReady = await ensureDiningSession()
        if (!sessionReady || tableSessionClosed.value) throw new Error(tableSessionClosed.value ? '\u672c\u684c\u5df2\u7ed3\u675f\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u70b9\u9910' : '\u672c\u684c\u70b9\u9910\u4f1a\u8bdd\u4e0d\u53ef\u7528\uff0c\u8bf7\u91cd\u65b0\u626b\u7801')
        const payload = {
          table: tableNo.value,
          shop: shopId.value,
          total: totalPrice.value,
          remark: remark.value.trim() || undefined,
          coupon_id: selectedCouponId.value || undefined,
          use_balance: useBalance.value && estimatedBalanceAvailable.value > 0,
          dining_session_id: diningSessionId.value || undefined,
          participant_token: diningParticipantToken.value || undefined,
          client_id: diningClientId.value || undefined,
          items: cartItems.value.map((item) => ({ dish_id: item.id, name: item.orderName || item.name, price: item.price, qty: item.qty, specifications: item.specifications && item.specifications.length ? item.specifications : undefined, extras: item.extras && item.extras.length ? item.extras : undefined })),
        }
        const res = await createOrder(payload, { authRedirect: false })
        const data = res?.data || {}
        pendingOrderId.value = String(data.id || '')
        orderNo.value = String(data.order_no || data.id || '').slice(-4)
        successItems.value = cartItems.value.map(i => ({ ...i }))
        successDiscount.value = Number(data.discount_amount ?? 0)
        payAmount.value = Number(data.pay_amount ?? data.total ?? finalPrice.value)
        balanceAvailable.value = Number(data.balance_available ?? estimatedBalanceAvailable.value)
        savePendingPaymentOrder()
        if (!pendingOrderId.value) throw new Error('\u8ba2\u5355\u521b\u5efa\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5')
        return await confirmPay()
      } catch (err) {
        if (isCheckoutAuthError(err)) {
          requireCheckoutAuth()
          return false
        }
        const rawMsg = err?.message || ''
        if (rawMsg.includes('\u4f1a\u8bdd') || rawMsg.includes('\u91cd\u65b0\u626b\u7801') || rawMsg.includes('\u672c\u684c')) tableSessionClosed.value = true
        const msg = rawMsg || '\u4e0b\u5355\u5931\u8d25\uff0c\u8bf7\u544a\u77e5\u670d\u52a1\u5458'
        uni.showToast({ title: String(msg).slice(0, 30), icon: 'none' })
        return false
      } finally {
        ordering.value = false
      }
    }

    const _handlePaySuccess = (data) => {
      showCart.value = false
      orderId.value = pendingOrderId.value
      orderStatus.value = data.status || 'pending'
      balanceDeducted.value = Number(data.balance_deducted ?? 0)
      successTotal.value = Number(data.total ?? payAmount.value)
      if (balanceDeducted.value > 0 && bannerInfo.value) {
        bannerInfo.value = { ...bannerInfo.value, balance: Math.max(0, bannerInfo.value.balance - balanceDeducted.value) }
      }
      startStatusPoll(orderId.value)
      const now = new Date()
      const timeStr = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0')
      myOrders.value.unshift({
        id: orderId.value, orderNo: orderNo.value, status: orderStatus.value,
        items: successItems.value, total: successTotal.value, createdAt: timeStr,
        createdTs: now.getTime(), table: tableNo.value,
      })
      saveMyOrders()
      syncDiningOrders().catch(() => {})
      const c = data.coupon || null
      earnedCoupon.value = c ? {
        amount: Number(c.value ?? c.amount ?? 0),
        threshold: Number(c.min_amount ?? c.threshold ?? 0),
        validDays: Number(c.valid_days ?? 0),
          name: c.name || '\u4f18\u60e0\u5238',
      } : null
      cart.value = {}
      specCartItems.value = []
      selectedCouponId.value = null
      remark.value = ''
      showSuccess.value = true
      clearPendingPaymentOrder()
      console.log('[show_order_success]', { order_id: orderId.value, status: orderStatus.value })
    }

    const confirmPay = async () => {
      if (paying.value || !pendingOrderId.value) return false
      if (await recoverPendingPaymentResult()) return true
      paying.value = true
      if (showCheckoutAuth.value) authActionStatus.value = 'paying'
      try {
        console.log('[ORDER_PAY_START]', {
          order_id: pendingOrderId.value,
          amount: actualPayAmount.value,
          use_balance: useBalance.value
        })
        let jsCode = ''
        if (!uni.getStorageSync('customer_token')) {
          jsCode = await wxLogin()
        }
        const res = await createWxPayOrder(pendingOrderId.value, useBalance.value, { authRedirect: false, js_code: jsCode })
        const data = res?.data || {}
        console.log('[ORDER_PAY_RESPONSE]', {
          order_id: pendingOrderId.value,
          free: !!data.free,
          has_pay_params: !!data.pay_params
        })

        if (data.free) {
          console.log('[ORDER_PAY_FREE_SUCCESS]', { order_id: pendingOrderId.value })
          _handlePaySuccess(data)
          pendingPaymentIntent.value = null
          return true
        }

        const p = data.pay_params
        if (!p) {
          console.log('[ORDER_PAY_PARAMS_MISSING]', { order_id: pendingOrderId.value, data })
          throw new Error('\u652f\u4ed8\u53c2\u6570\u7f3a\u5931\uff0c\u8bf7\u91cd\u65b0\u4e0b\u5355')
        }

        console.log('[ORDER_REQUEST_PAYMENT_START]', { order_id: pendingOrderId.value })
        await uni.requestPayment({
          provider: 'wxpay',
          timeStamp: p.timeStamp,
          nonceStr: p.nonceStr,
          package: p.package,
          signType: p.signType || 'RSA',
          paySign: p.paySign,
        })

        console.log('[ORDER_REQUEST_PAYMENT_SUCCESS]', { order_id: pendingOrderId.value })
        _handlePaySuccess({ ...data, total: payAmount.value })
        pendingPaymentIntent.value = null
        return true

      } catch (err) {
        console.log('[ORDER_PAY_FAIL]', { order_id: pendingOrderId.value, error: err })
        if (isCheckoutAuthError(err)) {
          requireCheckoutAuth()
          return false
        }
        if (await recoverPendingPaymentResult({ showDetail: true })) return true
        const msg = err?.errMsg || err?.message || '\u652f\u4ed8\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5'
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
      useBalance.value = false
      balanceAvailable.value = 0
      balanceDeducted.value = 0
      showSuccess.value = false
    }

    const callWaiter = () => {
      uni.vibrateShort({ type: 'heavy' })
      uni.showToast({ title: '\u5df2\u901a\u77e5\u670d\u52a1\u5458\u7ed3\u8d26', icon: 'none', duration: 2000 })
    }

    const callWaiterBill = () => {
      uni.vibrateShort({ type: 'heavy' })
      uni.showModal({
        title: '\u786e\u8ba4\u7ed3\u8d26',
        content: '\u672c\u684c\u5408\u8ba1 \u00a5' + tableTotalSpent.value.toFixed(2) + '\uff0c\u8bf7\u786e\u8ba4\u5546\u5bb6\u5df2\u5b8c\u6210\u7ed3\u8d26\u3002',
        confirmText: '\u786e\u8ba4\u7ed3\u8d26',
        cancelText: '\u518d\u7b49\u7b49',
        success: (res) => {
          if (res.confirm) {
            uni.showToast({ title: '\u5df2\u5b8c\u6210\u672c\u684c\u7528\u9910', icon: 'success', duration: 1200 })
            finishOrdering()
          }
        }
      })
    }

    const goCoupons = () => {
      showSuccess.value = false
      uni.navigateTo({ url: '/subpkg-coupon/pages/list' })
    }

    const loadMemberStatus = async () => {
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
        const [profileRes, couponRes] = await Promise.all([
          getMemberProfile(),
          getCustomerCoupons('UNUSED').catch(() => null),
        ])
        if (profileRes?.code === 200 && profileRes?.data) {
          const p = profileRes.data
          isMember.value = !!(p.membership_level || p.is_member || p.member_card || p.membership_expire_at || p.level)
          const coupons = Array.isArray(couponRes?.data) ? couponRes.data : []
          bannerInfo.value = {
            nameChar: (p.name || '\u4f1a')[0],
            levelLabel: p.level || p.membership_level || '\u666e\u901a\u4f1a\u5458',
            couponCount: coupons.length,
            coupons,
            balance: Number(p.balance || 0),
            points: Number(p.points || 0),
            growth: Number(p.growth || p.growth_value || p.growthValue || 0),
            nextGrowth: Number(p.next_growth || p.nextGrowth || 0),
            nextUpgradeAmount: Number(p.next_upgrade_amount || p.nextUpgradeAmount || 0),
          }
        }
      } catch { /* 蹇界暐鍔犺浇澶辫触 */ }
      finally { memberLoading.value = false }
    }

    const entryCoupon = ref(null)   // { coupon_id, amount, threshold, expire_time }

    const loadShopSettings = async () => {
      if (!shopId.value) return
      try {
        const res = await getShopInfo(shopId.value)
        if (res?.code === 200 && res?.data) {
          const d = res.data
          deliveryEnabled.value = !!d.delivery_enabled
          const realShopName = d.name || d.shop_name || d.tenant_name || ''
          if (realShopName) {
            shopName.value = realShopName
            uni.setStorageSync('tenant_name', realShopName)
            uni.setNavigationBarTitle({ title: realShopName + ' \u70b9\u9910' })
          }
          if (Array.isArray(d.remark_chips) && d.remark_chips.length) {
            remarkChips.value = d.remark_chips
          }
          if (Array.isArray(d.category_order) && d.category_order.length) {
            categoryOrder.value = d.category_order
          }
          // 澶勭悊杩涘簵浼樻儬鍒?
          if (d.entry_coupon?.coupon_id) {
            entryCoupon.value = d.entry_coupon
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
        const shopInfo = res?.data?.shop || res?.data?.tenant || null
        if (shopInfo && shopInfo.is_open === false) {
          storeClosed.value = true
          closedNotice.value = shopInfo.closed_notice || shopInfo.business_hours || ''
        }
      } catch {
        loadError.value = true
        allDishes.value = []
      } finally {
        loading.value = false
菜单加载完成后重置滚动状态
        currentScrollTop = 0
        if (categories.value.length) activeCategory.value = categories.value[0]
        // DOM 鏇存柊鍚庣紦瀛樺垎绫讳綅缃?
        setTimeout(cacheSectionPositions, 400)
      }
    }


    watch(cartItems, () => {
      if (showCart.value && totalCount.value <= 0) showCart.value = false
      resetPendingPayment()
    }, { deep: true })
    watch([selectedCouponId, remark, useBalance], resetPendingPayment)

    return {
      tableNo, shopId, shopName, tableDisplayText, orderModeDisplayText, showTableHint, todayActivity, orderMode, orderModeText, confirmationText, successText, specText,
      loading, loadError, ordering, showCart, showSuccess, earnedCoupon, itemsExpanded, toggleItemsExpanded, closeOrderConfirm,
      showCheckoutAuth, authorizing, authSheetText, authPrimaryText, handleCheckoutAuth, cancelCheckoutAuth,
      paying, payAmount, confirmPay,
      orderNo, orderStatus, orderStatusText, successStatusText, successStatusTone, successOrderItemCount, successOrderNo, orderStatusClass, merchantNote,
      remark, remarkChips, toggleRemarkChip,
      availableCoupons, selectedCouponId, selectedCoupon, discountAmount, finalPrice,
      openCart,
      activeCategory, scrollTarget, categoryScrollTarget, categoryScrollTop, dishScrollTopVal, allDishes, cart, addPressKey, qtyPulseKey, cartIconPulse, cartBadgePulse, amountPulse,
      successItems, successTotal,
      categories, dishesByCategory, dishImage, dishTags, dishCardTags, isStrongDishTag, dishCardDesc, showDishSales, isSoldOut, dishPriceText, dishPriceSuffix, dishOriginalPrice, hasSpecs, formatPrice,
      imageLoadFailed, detailImageFailed, markDishImageFailed, openProductDetail,
      cartCount, addToCart, removeFromCart, increaseCartItem, clearCart, specButtonText, dishOptionKindCount, optionCountText, openSpecSheet,
      cartItems, totalCount, totalPrice, cartBadgeText,
      switchCategory, switchOrderMode,
      goCheckout, resetOrder, finishOrdering, closeSuccessAndWait, continueOrdering, viewOrderDetail, goCoupons, callWaiter, callWaiterBill, loadMenu,
      myOrders, showOrders, showAllOrders, pendingOrderCount, tableTotalSpent, statusLabel, doCancelOrder,
      currentTableOrder, historyTableOrders, currentTableOrderStatus, tableOrderStatusTitle, tableOrderStatusHint, tableOrderTimeline, orderItemCount, currentOrderItemCount, currentOrderItems, currentOrderMainItemText,
      orderItemName, orderItemQty, orderItemAmount, orderItemSpecText,
      saveMyOrders, loadMyOrders, refreshAllOrderStatuses, ensureDiningSession, syncDiningOrders,
      savePendingPaymentOrder, restorePendingPaymentOrder, clearPendingPaymentOrder, recoverPendingPaymentResult,
      availableCoupons, selectedCouponId, selectedCoupon, discountAmount, finalPrice,
      successDiscount, useBalance, balanceAvailable, balanceDeducted, actualPayAmount, estimatedBalanceAvailable, estimatedBalanceDeduction, wechatPayAmount, prepareHint, canSubmitOrder, payButtonText,
      showReview, reviewRating, reviewContent, reviewHintText, closeReview, doSubmitReview,
      storeClosed, closedNotice, tableSessionClosed, tableSessionClosedNotice, isMember, memberSavings, bannerInfo, memberAuthorizing, memberLoading, isCustomerLoggedIn, hasCustomerIdentity,
      activeTab, shopDistance, switchToCard, goMine,
      memberLevelLabel, memberProgressPercent, memberUpgradeText, usableMemberCoupons, couponAmountText, couponConditionText, couponValidityText, goOrderFromMember, handleMemberCardAuth, useMemberCoupon, goBalanceDetail,
      homeStatusDesc, homeOrderButtonText, homeCouponHint, canStartOrdering, featuredDish, featuredDishTag, canHomeAdd, homeLastOrderItems,
      handleHomeStartOrder, handleFeaturedAdd, handleHomeReorderItem, handleHomeReorderAll,
      loadMemberStatus, refreshCustomerAuthState, loadShopSettings,
      deliveryEnabled, entryCoupon,
      showSpecSheet, specDish, specQty, selectedSpecs, specTotalPrice,
      isSpecSelected, toggleSpec, toggleExtra, cancelSpec, handleSpecPrimary, confirmSpec, specCartItems, specStep, specSteps, specRadioGroups, specExtraOptions, selectedExtras, itemRemark, selectedSpecSummary, specBasePrice, specDishDesc, canGoNextSpec, specPrimaryText,
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
      await this.ensureDiningSession(true)
      await this.syncDiningOrders()
      await this.recoverPendingPaymentResult({ showDetail: options.openOrders === '1' })
      if (options.openOrders === '1') this.showOrders = true
      this.refreshCustomerAuthState()
      this.loadMemberStatus()
      await this.loadShopSettings()
      await this.loadMenu()
    })()
  },
  onShow: function () {
    if (this.refreshCustomerAuthState) this.refreshCustomerAuthState()
    if (this.recoverPendingPaymentResult) this.recoverPendingPaymentResult()
    if (this.activeTab === 'card' || uni.getStorageSync('customer_token') || uni.getStorageSync('customer_phone')) {
      this.loadMemberStatus()
    }
  },
  onUnload: function () {
    this.stopStatusPoll()
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

/* 搴楅摵澶撮儴 */
.shop-header {
  height: calc(176rpx + env(safe-area-inset-top));
  min-height: calc(176rpx + env(safe-area-inset-top));
  max-height: calc(176rpx + env(safe-area-inset-top));
  background: #07C160;
  padding: calc(28rpx + env(safe-area-inset-top)) 32rpx 24rpx;
  box-sizing: border-box;
}

.shop-title-main {
  width: 100%;
  min-width: 0;
  max-width: calc(100vw - 220rpx);
  box-sizing: border-box;
}

.shop-name {
  display: block;
  width: 100%;
  box-sizing: border-box;
  color: #fff;
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
  color: #fff;
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 600;
  white-space: nowrap;
}

.shop-meta-dot {
  margin: 0 10rpx;
  color: rgba(255,255,255,0.65);
  font-size: 28rpx;
  line-height: 40rpx;
}

.shop-mode-text {
  color: rgba(255,255,255,0.78);
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 500;
  white-space: nowrap;
}

.shop-meta-arrow {
  margin-left: 10rpx;
  color: rgba(255,255,255,0.55);
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


.menu-body {
  display: flex;
  flex: 1;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  min-height: 0;
}

.category-nav {
  width: 156rpx;
  flex: 0 0 156rpx;
  background: #F6F7F8;
  overflow-x: hidden;
  overflow-y: auto;
  box-sizing: border-box;
}

.cat-item {
  position: relative;
  height: 96rpx;
  min-height: 96rpx;
  padding: 0 16rpx;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 28rpx;
  line-height: 38rpx;
  font-weight: 500;
  color: #6F7680;
  background: transparent;

  text {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    word-break: break-all;
  }

  &.active {
    background: #fff;
    color: #07C160;
    font-weight: 600;
  }

  &.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 6rpx;
    height: 48rpx;
    border-radius: 0 4rpx 4rpx 0;
    background: #07C160;
  }
}

.dish-scroll {
  flex: 1;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
  background: #fff;
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
  background: #fff;
}
.cat-divider-line {
  flex: 1;
  max-width: 160rpx;
  height: 1rpx;
  background: #E7E9EC;
}
.cat-divider-text {
  margin: 0 20rpx;
  font-size: 26rpx;
  color: #8A9099;
  font-weight: 500;
  white-space: nowrap;
  letter-spacing: 0;
}

.cat-title {
  display: block;
  padding: 24rpx 0 16rpx;
  font-size: 24rpx;
  font-weight: 700;
  color: #9ca3af;
}

.dish-item {
  display: flex;
  align-items: stretch;
  width: 100%;
  min-width: 0;
  height: 236rpx;
  min-height: 236rpx;
  max-height: 236rpx;
  padding: 20rpx 20rpx 20rpx 24rpx;
  box-sizing: border-box;
  background: #fff;
  border-bottom: 0;
  position: relative;
  overflow: hidden;
  transition: background 120ms ease, opacity 120ms ease;
}

.dish-item::after { content: ""; position: absolute; left: 236rpx; right: 0; bottom: 0; height: 1rpx; background: #F0F1F2; }
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
}

.dish-img { width: 100%; height: 100%; display: block; }
.dish-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: #F5F3EE; }
.dish-placeholder-icon { position: relative; width: 62rpx; height: 62rpx; }
.dish-placeholder-plate { position: absolute; left: 10rpx; top: 12rpx; width: 42rpx; height: 42rpx; border: 4rpx solid #C7C2B8; border-radius: 50%; box-sizing: border-box; background: rgba(255,255,255,.46); }
.dish-placeholder-stick { position: absolute; top: 8rpx; width: 4rpx; height: 48rpx; border-radius: 999rpx; background: #C7C2B8; }
.dish-placeholder-stick--left { left: 2rpx; }
.dish-placeholder-stick--right { right: 2rpx; }
.dish-soldout-mask { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(31,41,55,.42); }
.dish-soldout-mask text { min-width: 104rpx; height: 48rpx; padding: 0 18rpx; border-radius: 999rpx; display: flex; align-items: center; justify-content: center; background: rgba(17,24,39,.76); color: #fff; font-size: 24rpx; font-weight: 700; }
.dish-emoji-wrap, .dish-emoji, .dish-initial, .dish-badge-top { display: none; }


.reorder-bar {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 16rpx 0 12rpx;
  border-bottom: 1rpx solid #f0f0f0;
  margin-bottom: 4rpx;
}

.reorder-label {
  font-size: 22rpx;
  color: #9ca3af;
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
  border: 1rpx solid #07C160;
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
  color: #07C160;
  font-weight: 800;
  line-height: 1;
}

.reorder-all-btn {
  flex-shrink: 0;
  background: #07C160;
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
  border-left: 4rpx solid #f59e0b;
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


.dish-info { flex: 1; min-width: 0; display: flex; flex-direction: column; margin-left: 20rpx; box-sizing: border-box; overflow: hidden; }
.dish-title-row { display: flex; align-items: flex-start; gap: 12rpx; min-width: 0; }
.dish-name { flex: 1; min-width: 0; font-size: 32rpx; font-weight: 600; line-height: 44rpx; color: #171A1D; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-tags { display: flex; flex-shrink: 0; flex-wrap: nowrap; max-width: 112rpx; overflow: hidden; }
.dish-tag { max-width: 112rpx; height: 36rpx; padding: 0 10rpx; border-radius: 8rpx; box-sizing: border-box; font-size: 20rpx; font-weight: 500; line-height: 36rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-tag--strong { color: #078546; background: #e9f9f0; }
.dish-tag--plain { display: none; }
.dish-meta { flex: 1; min-width: 0; min-height: 0; padding-top: 6rpx; }
.dish-desc { display: block; min-width: 0; font-size: 26rpx; color: #8A9099; line-height: 36rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-sales { display: block; min-width: 0; margin-top: 2rpx; margin-left: 0; font-size: 24rpx; line-height: 34rpx; color: #A8ADB4; font-weight: 400; }
.dish-bottom-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 0; margin-top: auto; min-width: 0; }
.dish-price-wrap { flex: 1; min-width: 104rpx; overflow: hidden; display: flex; align-items: baseline; color: #07C160; }
.dish-price-currency { flex-shrink: 0; font-size: 24rpx; font-weight: 700; line-height: 1; }
.dish-price-amount { min-width: 0; font-size: 40rpx; font-weight: 700; line-height: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-price-suffix { flex-shrink: 0; margin-left: 2rpx; font-size: 22rpx; font-weight: 500; line-height: 1; color: #07C160; }
.dish-origin-price, .dish-save-badge, .member-price { display: none; }
.dish-counter { flex: none; display: flex; align-items: center; justify-content: flex-end; flex-shrink: 0; gap: 6rpx; margin-left: 12rpx; min-width: 64rpx; max-width: 200rpx; box-sizing: border-box; }
.dish-qty-control { width: 200rpx; max-width: 200rpx; height: 68rpx; display: flex; align-items: center; justify-content: flex-end; gap: 6rpx; overflow: hidden; flex-shrink: 0; box-sizing: border-box; }
.counter-touch { width: 72rpx; height: 72rpx; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; }
.dish-counter > .counter-touch { width: 88rpx; height: 88rpx; }
.dish-counter .counter-btn { width: 64rpx; height: 64rpx; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-sizing: border-box; flex-shrink: 0; }
.dish-counter .counter-btn text { font-size: 30rpx; font-weight: 800; line-height: 1; }
.dish-counter .counter-btn.plus { background: #07C160; }
.dish-counter .counter-btn.plus text { color: #fff; }
.dish-counter .counter-btn.minus { width: 60rpx; height: 60rpx; border: 2rpx solid #d7dde2; background: #fff; }
.dish-counter .counter-btn.minus text { color: #5d6670; }
.dish-counter .counter-num { width: 44rpx; min-width: 44rpx; text-align: center; font-size: 32rpx; line-height: 34rpx; font-weight: 600; color: #171A1D; }
.soldout-action { height: 60rpx; min-width: 104rpx; padding: 0 20rpx; border-radius: 30rpx; display: flex; align-items: center; justify-content: center; background: #eef1f4; box-sizing: border-box; flex-shrink: 0; }
.soldout-action text { font-size: 24rpx; font-weight: 600; color: #9aa1aa; white-space: nowrap; }

/* 鍔犲噺鎸夐挳 */
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
    background: #07C160;
    text { color: #fff; }
  }

  &.minus {
    background: #f3f4f6;
    text { color: #374151; }
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
  color: #111827;
  min-width: 32rpx;
  text-align: center;
}


.list-pad { height: calc(264rpx + env(safe-area-inset-bottom)); }

.empty-menu {
  min-height: 520rpx;
  padding: 120rpx 32rpx 32rpx;
  text-align: center;
  box-sizing: border-box;
}

.empty-title {
  display: block;
  color: #111827;
  font-size: 34rpx;
  font-weight: 800;
}

.empty-desc {
  display: block;
  margin-top: 14rpx;
  color: #9ca3af;
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
  background: #07C160;
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
  border-top: 1rpx solid #f0f0f0;
  display: flex;
  align-items: stretch;
  z-index: 300;
}

.bn-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;

  &:active { opacity: 0.6; }
}

.bn-label {
  font-size: 30rpx;
  color: #9ca3af;
  font-weight: 500;
  line-height: 1;
}

.bn-item.active .bn-label {
  color: #07C160;
  font-weight: 700;
}

.bn-dot {
  position: absolute;
  top: 12rpx;
  right: calc(50% - 36rpx);
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background: #ef4444;
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
  background: #F5F7F9;
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  box-sizing: border-box;
}
.member-identity-card { min-height: 172rpx; padding: 32rpx; border-radius: 36rpx; background: #fff; display: flex; align-items: flex-start; gap: 22rpx; box-sizing: border-box; }
.member-avatar { width: 96rpx; height: 96rpx; border-radius: 50%; background: #E8F8EF; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.member-avatar text { color: #07C160; font-size: 36rpx; line-height: 48rpx; font-weight: 900; }
.member-identity-main { flex: 1; min-width: 0; }
.member-level { display: block; font-size: 38rpx; line-height: 50rpx; font-weight: 900; color: #171A1D; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-growth-text { display: block; margin-top: 8rpx; font-size: 26rpx; line-height: 36rpx; color: #7D848E; }
.member-level-pill { flex-shrink: 0; min-height: 48rpx; padding: 0 18rpx; border-radius: 24rpx; background: #E8F8EF; display: flex; align-items: center; justify-content: center; }
.member-level-pill text { color: #087A3D; font-size: 23rpx; line-height: 32rpx; font-weight: 800; }
.member-progress-wrap { margin-top: 24rpx; }
.member-progress-track { height: 10rpx; border-radius: 999rpx; background: #EDF1F3; overflow: hidden; }
.member-progress-fill { height: 100%; border-radius: 999rpx; background: #07C160; }
.member-upgrade-text { display: block; margin-top: 10rpx; color: #07C160; font-size: 24rpx; line-height: 34rpx; font-weight: 700; }
.member-assets-card { min-height: 168rpx; background: #fff; border-radius: 32rpx; display: flex; align-items: stretch; padding: 28rpx 0; box-sizing: border-box; }
.member-asset-item { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8rpx; }
.member-asset-item:active { opacity: .72; }
.member-asset-divider { width: 1rpx; margin: 12rpx 0; background: #EDF1F3; }
.member-asset-value { color: #171A1D; font-size: 38rpx; line-height: 46rpx; font-weight: 900; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-asset-label { color: #171A1D; font-size: 26rpx; line-height: 36rpx; font-weight: 700; }
.member-asset-hint { color: #8A9099; font-size: 22rpx; line-height: 32rpx; }
.member-main-action-card { padding: 34rpx; border-radius: 36rpx; background: linear-gradient(135deg, #07C160 0%, #10A85A 100%); box-sizing: border-box; }
.member-action-title { display: block; color: #fff; font-size: 36rpx; line-height: 48rpx; font-weight: 900; }
.member-action-desc { display: block; margin-top: 10rpx; color: rgba(255,255,255,.82); font-size: 26rpx; line-height: 36rpx; }
.member-action-btn { margin-top: 28rpx; height: 96rpx; border-radius: 48rpx; background: #fff; display: flex; align-items: center; justify-content: center; }
.member-action-btn:active { transform: scale(.98); }
.member-action-btn text { color: #07C160; font-size: 32rpx; line-height: 44rpx; font-weight: 900; }
.member-section { display: flex; flex-direction: column; gap: 16rpx; }
.member-section-title { color: #171A1D; font-size: 32rpx; line-height: 44rpx; font-weight: 900; }
.member-coupon-list { display: flex; flex-direction: column; gap: 16rpx; }
.member-coupon-card { min-height: 132rpx; padding: 24rpx; border-radius: 28rpx; background: #fff; display: flex; align-items: center; gap: 20rpx; box-sizing: border-box; }
.member-coupon-card:active { opacity: .74; }
.member-coupon-value { width: 118rpx; flex-shrink: 0; color: #07C160; display: flex; align-items: baseline; justify-content: center; }
.member-coupon-yen { font-size: 26rpx; line-height: 34rpx; font-weight: 900; }
.member-coupon-amount { font-size: 48rpx; line-height: 56rpx; font-weight: 900; }
.member-coupon-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8rpx; }
.member-coupon-condition { color: #171A1D; font-size: 28rpx; line-height: 38rpx; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-coupon-time { color: #8A9099; font-size: 24rpx; line-height: 34rpx; }
.member-coupon-use { height: 64rpx; padding: 0 24rpx; border-radius: 32rpx; background: #07C160; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.member-coupon-use text { color: #fff; font-size: 24rpx; line-height: 34rpx; font-weight: 800; }
.member-service-card { background: #fff; border-radius: 32rpx; overflow: hidden; }
.member-service-row { min-height: 96rpx; padding: 0 30rpx; display: flex; align-items: center; justify-content: space-between; color: #171A1D; font-size: 30rpx; line-height: 42rpx; font-weight: 800; box-sizing: border-box; }
.member-service-row + .member-service-row { border-top: 1rpx solid #F0F2F4; }
.member-service-row:active { background: #F7F9FA; }
.member-service-arrow { color: #B0B7C0; font-size: 34rpx; line-height: 42rpx; }
.card-tab-empty { padding: 120rpx 40rpx; text-align: center; }
.cte-title { display: block; font-size: 32rpx; font-weight: 800; color: #111827; margin-bottom: 12rpx; }
.cte-desc { display: block; font-size: 26rpx; color: #9ca3af; line-height: 1.6; }
.cte-btn { margin-top: 32rpx; width: 100%; height: 96rpx; line-height: 96rpx; border-radius: 48rpx; background: #07C160; color: #fff; font-size: 30rpx; font-weight: 800; display: flex; align-items: center; justify-content: center; padding: 0; border: 0; }
.cte-btn::after { border: 0; }
.cte-btn[disabled] { opacity: .7; }
.cte-btn-plain { background: #EEF2F5; color: #3F4650; }
.cte-secondary { display: block; margin-top: 24rpx; color: #6B7280; font-size: 26rpx; line-height: 38rpx; }
@media screen and (max-width: 340px) {
  .card-tab.member-center { padding-left: 24rpx; padding-right: 24rpx; }
  .member-identity-card { padding: 28rpx; gap: 18rpx; }
  .member-level { font-size: 34rpx; }
  .member-asset-value { font-size: 34rpx; }
  .member-coupon-card { gap: 14rpx; padding: 22rpx; }
  .member-coupon-use { padding: 0 18rpx; }
}


.cart-bar {
  position: fixed;
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
  box-sizing: border-box;

  &.has-items { background: #111827; }
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

  .has-items & { background: #07C160; }
}

.cart-icon-svg {
  width: 42rpx;
  height: 40rpx;
  position: relative;
  &::before {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 32rpx;
    border: 4rpx solid #fff;
    border-radius: 6rpx;
  }
  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 10rpx;
    right: 10rpx;
    height: 18rpx;
    border: 4rpx solid #fff;
    border-bottom: none;
    border-radius: 10rpx 10rpx 0 0;
  }
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
  background: #07C160;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-sizing: border-box;

  text { color: #fff; font-size: 32rpx; font-weight: 600; white-space: nowrap; }

  &.disabled {
    background: #4B5362;
    text { color: rgba(255,255,255,0.45); }
  }
}

.choose-option-btn { height: 60rpx; padding: 0 20rpx; border-radius: 30rpx; background: #07C160; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; transition: transform 140ms ease-out; text { color: #fff; font-size: 24rpx; font-weight: 600; white-space: nowrap; } }
.choose-option-btn:active { transform: scale(.97); }
.option-count-pill { position: static; min-width: 34rpx; height: 34rpx; padding: 0 10rpx; border-radius: 999rpx; background: #fff; border: 2rpx solid #07C160; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; text { color: #07C160; font-size: 20rpx; font-weight: 800; white-space: nowrap; } }



.mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
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
.order-confirm-title { font-size: 36rpx; font-weight: 900; color: #111827; }
.order-confirm-close { width: 64rpx; height: 64rpx; display: flex; align-items: center; justify-content: center; color: #98a2b3; font-size: 34rpx; line-height: 1; }
.order-confirm-content { flex: 1; min-height: 0; padding: 20rpx 24rpx 18rpx; box-sizing: border-box; }
.order-confirm-bottom { flex-shrink: 0; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: rgba(255,255,255,0.96); border-top: 1rpx solid #edf0f2; }
.order-summary-card { padding: 28rpx 28rpx; border-radius: 24rpx; background: #ecfbf3; border: 1rpx solid #cbeedb; margin-bottom: 18rpx; }
.order-summary-card--missing { background: #fff7ed; border-color: #fed7aa; }
.order-summary-topline { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; }
.summary-service { display: flex; align-items: center; gap: 18rpx; min-width: 0; }
.summary-mode-pill { height: 50rpx; padding: 0 20rpx; border-radius: 999rpx; background: #10c469; display: flex; align-items: center; justify-content: center; flex-shrink: 0; text { color: #fff; font-size: 25rpx; font-weight: 900; } }
.summary-table-line { display: flex; align-items: baseline; gap: 8rpx; min-width: 0; }
.summary-table-label { font-size: 29rpx; color: #475569; font-weight: 800; }
.summary-table-no { font-size: 46rpx; color: #0baa5a; font-weight: 900; line-height: 1; }
.summary-table-tip { color: #9a6f22; font-size: 24rpx; font-weight: 800; flex-shrink: 0; }
.order-summary-subline { display: flex; justify-content: space-between; align-items: center; gap: 16rpx; margin-top: 22rpx; padding-top: 20rpx; border-top: 1rpx solid rgba(16,196,105,.13); text { color: #667085; font-size: 25rpx; font-weight: 700; } }
.confirm-card { background: #fff; border: 1rpx solid #eef1f3; border-radius: 24rpx; margin-bottom: 18rpx; overflow: hidden; }
.selected-items-summary { min-height: 118rpx; padding: 0 28rpx; display: flex; justify-content: space-between; align-items: center; gap: 18rpx; }
.selected-items-title-wrap { display: flex; flex-direction: column; gap: 8rpx; min-width: 0; }
.selected-items-title { color: #111827; font-size: 34rpx; font-weight: 900; }
.selected-items-sub { color: #98a2b3; font-size: 24rpx; }
.selected-items-action { display: flex; align-items: center; gap: 18rpx; flex-shrink: 0; color: #667085; }
.selected-items-amount { color: #0baa5a; font-size: 34rpx; font-weight: 900; }
.selected-items-toggle { color: #667085; font-size: 26rpx; }
.cart-items-panel { border-top: 1rpx solid #edf0f2; padding: 0 0 8rpx; }
.cart-items { max-height: 34vh; padding: 0 28rpx; box-sizing: border-box; }
.cart-row { display: flex; align-items: center; gap: 16rpx; padding: 24rpx 0; border-bottom: 1rpx solid #edf0f2; }
.cart-row-emoji { width: 38rpx; color: #cbd5e1; font-size: 32rpx; }
.cart-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.cart-row-name { font-size: 31rpx; font-weight: 800; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cart-row-spec { font-size: 22rpx; color: #98a2b3; }
.cart-row-right { display: flex; align-items: center; gap: 14rpx; flex-shrink: 0; }
.cart-row-price { min-width: 82rpx; text-align: right; font-size: 30rpx; font-weight: 900; color: #0baa5a; }
.cart-clear-line { height: 74rpx; display: flex; align-items: center; justify-content: center; border-top: 1rpx solid #f5f7f8; text { color: #98a2b3; font-size: 26rpx; } }
.order-preference-section { padding: 26rpx 28rpx; }
.order-preference-section .remark-chips { margin-bottom: 22rpx; }
.order-preference-section .remark-chip { margin-right: 14rpx; margin-bottom: 14rpx; padding: 14rpx 24rpx; border-radius: 999rpx; border: 1rpx solid #dfe5e8; background: #fff; }
.order-preference-section .remark-chip--on { border-color: #10c469; background: #ecfbf3; }
.order-preference-section .remark-row { border-top: 1rpx solid #edf0f2; padding-top: 22rpx; }
.price-summary-card { padding: 12rpx 28rpx 10rpx; }
.price-row { min-height: 88rpx; display: flex; align-items: center; justify-content: space-between; gap: 18rpx; color: #475467; font-size: 29rpx; border-bottom: 1rpx solid #edf0f2; }
.price-row:last-child { border-bottom: 0; }
.price-row--clickable { color: #111827; }
.price-discount { color: #0baa5a; font-weight: 800; }
.price-muted { color: #98a2b3; }
.balance-row-left { display: flex; flex-direction: column; gap: 4rpx; }
.balance-row-desc { color: #98a2b3; font-size: 22rpx; }
.price-row--payable { min-height: 110rpx; color: #111827; font-size: 34rpx; font-weight: 900; }
.price-row--payable text:last-child { color: #10c469; font-size: 52rpx; font-weight: 900; }
.checkout-btn-full { height: 104rpx; border-radius: 28rpx; background: #10c469; display: flex; align-items: center; justify-content: center; box-shadow: 0 16rpx 32rpx rgba(16,196,105,0.22); text { color: #fff; font-size: 34rpx; font-weight: 900; } }
.checkout-btn-full--disabled { background: #cbd5e1; box-shadow: none; }
.pbl-switch { width: 88rpx; height: 48rpx; border-radius: 24rpx; background: #d1d5db; position: relative; transition: background 0.2s; flex-shrink: 0; }
.pbl-switch--on { background: #10c469; }
.pbl-switch-thumb { position: absolute; top: 4rpx; left: 4rpx; width: 40rpx; height: 40rpx; border-radius: 50%; background: #fff; transition: left 0.2s; box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.15); }
.pbl-switch--on .pbl-switch-thumb { left: 44rpx; }

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
  background: #07C160; border-radius: 16rpx;
  color: #fff; font-size: 30rpx; font-weight: 700;
}


.home-tab {
  padding: 32rpx 32rpx calc(132rpx + env(safe-area-inset-bottom));
  background: #F5F7F9;
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
  color: #171A1D;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ht-status-desc {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  line-height: 36rpx;
  color: #7D848E;
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
.ht-status-badge--closed { background: #F1F3F5; color: #7D848E; }

.ht-order-card {
  margin: 0;
  padding: 36rpx;
  border-radius: 36rpx;
  background: #07C160;
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
  color: rgba(255,255,255,0.78);
  font-weight: 600;
}
.ht-order-title {
  display: block;
  margin-top: 8rpx;
  font-size: 48rpx;
  line-height: 64rpx;
  color: #fff;
  font-weight: 800;
}
.ht-order-desc {
  display: block;
  margin-top: 12rpx;
  font-size: 28rpx;
  line-height: 40rpx;
  color: rgba(255,255,255,0.82);
}
.ht-order-coupon {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  line-height: 34rpx;
  color: rgba(255,255,255,0.8);
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
.ht-order-btn text { color: #07C160; font-size: 34rpx; line-height: 48rpx; font-weight: 800; }
.ht-order-btn--disabled { background: rgba(255,255,255,0.82); }
.ht-order-btn--disabled text { color: #7D848E; }

.ht-section { display: flex; flex-direction: column; gap: 16rpx; }
.ht-section-head { display: flex; flex-direction: column; gap: 4rpx; }
.ht-section-head--row { flex-direction: row; align-items: center; justify-content: space-between; gap: 20rpx; }
.ht-section-title {
  display: block;
  margin: 0;
  font-size: 34rpx;
  line-height: 46rpx;
  font-weight: 800;
  color: #171A1D;
}
.ht-section-sub {
  display: block;
  font-size: 24rpx;
  line-height: 34rpx;
  color: #8A9099;
}
.ht-section-action {
  flex-shrink: 0;
  font-size: 26rpx;
  line-height: 38rpx;
  color: #07C160;
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
  background: #F0F2F4;
}
.ht-feature-img { width: 100%; height: 100%; display: block; }
.ht-feature-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F0F2F4;
}
.ht-feature-plate {
  width: 64rpx;
  height: 64rpx;
  border-radius: 50%;
  border: 6rpx solid #D0D5DD;
  box-sizing: border-box;
}
.ht-feature-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.ht-feature-title-row { display: flex; align-items: center; gap: 12rpx; min-width: 0; }
.ht-feature-name {
  flex: 1;
  min-width: 0;
  font-size: 36rpx;
  line-height: 48rpx;
  font-weight: 800;
  color: #171A1D;
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
  color: #7D848E;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ht-feature-bottom { margin-top: auto; display: flex; align-items: flex-end; justify-content: space-between; gap: 16rpx; }
.ht-feature-price { display: flex; align-items: baseline; min-width: 0; color: #07C160; }
.ht-feature-yen { font-size: 28rpx; line-height: 36rpx; font-weight: 800; }
.ht-feature-amount { font-size: 40rpx; line-height: 48rpx; font-weight: 900; }
.ht-feature-suffix { margin-left: 4rpx; font-size: 24rpx; line-height: 34rpx; font-weight: 700; }
.ht-feature-add {
  flex-shrink: 0;
  height: 72rpx;
  padding: 0 30rpx;
  border-radius: 36rpx;
  background: #07C160;
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
  color: #171A1D;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ht-last-add { color: #07C160; font-size: 30rpx; line-height: 36rpx; font-weight: 900; }

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
  background: #07C160;
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
  color: #111827;
  margin-bottom: 8rpx;
}
.success-subtitle {
  display: block;
  font-size: 26rpx;
  color: #6b7280;
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
  color: #07c160;
  margin-bottom: 4rpx;
}

.success-meta-row {
  display: flex;
  justify-content: center;
  gap: 24rpx;
}

.success-meta {
  font-size: 24rpx;
  color: #9ca3af;
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
  background: #07C160;
  animation: status-pulse 1.5s ease-in-out infinite;
}
.order-status-bar.done {
  background: #fbbf24;
}
.order-status-bar.pending .order-status-text { color: #92400e; }
.order-status-bar.preparing .order-status-text { color: #fff; font-size: 30rpx; }
.order-status-bar.done .order-status-text { color: #78350f; font-size: 30rpx; }
.order-status-text { font-size: 26rpx; font-weight: 700; color: #374151; }

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
  color: #374151;
  font-weight: 600;
}

.success-item-qty {
  font-size: 24rpx;
  color: #9ca3af;
  font-weight: 400;
}

.success-item-price {
  font-size: 28rpx;
  color: #111827;
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
  color: #6b7280;
}
.success-discount-val {
  font-size: 26rpx;
  color: #ef4444;
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
  color: #374151;
  font-weight: 700;
}

.success-total-price {
  font-size: 36rpx;
  font-weight: 900;
  color: #07C160;
}


.success-actions {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
  padding: 0 40rpx;
}

.success-btn-primary {
  height: 96rpx;
  border-radius: 24rpx;
  background: #07C160;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #fff; font-size: 34rpx; font-weight: 900; }
}
.success-btn-secondary {
  height: 96rpx;
  border-radius: 24rpx;
  background: #f1f5f9;
  border: 2rpx solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #64748b; font-size: 30rpx; font-weight: 600; }
}

.success-btn-primary.success-btn-secondary {
  background: #f1f5f9;
  border: 2rpx solid #e2e8f0;
  text { color: #64748b; font-size: 30rpx; font-weight: 600; }
}

.success-btn-settle {
  background: linear-gradient(135deg, #07C160, #059952);
  box-shadow: 0 8rpx 24rpx rgba(7,193,96,0.35);
  text { font-size: 36rpx; }
}
.success-btn-ghost {
  height: 80rpx;
  border-radius: 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #9ca3af; font-size: 28rpx; }
}
.success-btn-call {
  height: 72rpx;
  border-radius: 20rpx;
  border: 1rpx solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 4rpx;
  text { color: #6b7280; font-size: 26rpx; }
}

.success-check--done {
  background: linear-gradient(135deg, #f97316, #ef4444) !important;
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
  border-radius: 24rpx;
  border: 2rpx solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #64748b; font-size: 28rpx; }
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
  background: #ef4444;
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
  padding: 0 0 calc(32rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.orders-sheet-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 32rpx 40rpx 24rpx;
  border-bottom: 2rpx solid #f1f5f9;
  flex-shrink: 0;
}

.orders-sheet-title {
  font-size: 34rpx;
  font-weight: 800;
  color: #111827;
}

.orders-sheet-spent {
  display: block;
  font-size: 24rpx;
  color: #07C160;
  font-weight: 700;
  margin-top: 4rpx;
}

.orders-sheet-close {
  font-size: 28rpx;
  color: #9ca3af;
  padding: 8rpx 16rpx;
}

.active-order-bar {
  margin: 0 32rpx 16rpx;
  padding: 18rpx 24rpx;
  border-radius: 16rpx;
  text-align: center;
  &.preparing { background: #07C160; }
  &.done { background: #fbbf24; }
}
.active-order-text {
  font-size: 26rpx;
  font-weight: 700;
  color: #fff;
}

.orders-list {
  flex: 1;
  padding: 16rpx 32rpx;
}

.order-card {
  background: #f8fafc;
  border-radius: 24rpx;
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
  color: #374151;
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
  color: #64748b;
}

.order-card-item-price {
  font-size: 26rpx;
  color: #374151;
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
  color: #07C160;
}

.order-card-time {
  font-size: 22rpx;
  color: #9ca3af;
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
  text { font-size: 24rpx; color: #9ca3af; }
}

.order-status-entry {
  position: fixed;
  left: 32rpx;
  right: 32rpx;
  bottom: calc(216rpx + env(safe-area-inset-bottom));
  z-index: 850;
  min-height: 86rpx;
  padding: 14rpx 22rpx;
  border-radius: 24rpx;
  background: rgba(23, 26, 29, 0.92);
  display: flex;
  align-items: center;
  gap: 16rpx;
  box-sizing: border-box;
}

.order-status-entry-dot {
  width: 18rpx;
  height: 18rpx;
  border-radius: 50%;
  background: #07C160;
  flex-shrink: 0;
}

.order-status-entry-copy {
  flex: 1;
  min-width: 0;
}

.order-status-entry-title,
.order-status-entry-desc {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.order-status-entry-title {
  color: #fff;
  font-size: 28rpx;
  font-weight: 800;
}

.order-status-entry-desc {
  margin-top: 2rpx;
  color: rgba(255,255,255,0.68);
  font-size: 22rpx;
}

.order-status-entry-count {
  min-width: 34rpx;
  height: 34rpx;
  padding: 0 10rpx;
  border-radius: 17rpx;
  background: #07C160;
  color: #fff;
  font-size: 22rpx;
  line-height: 34rpx;
  text-align: center;
  font-weight: 800;
}

.order-status-entry-arrow {
  color: rgba(255,255,255,0.8);
  font-size: 36rpx;
  line-height: 1;
}

.orders-sheet {
  max-height: 86vh;
  padding: 0 0 calc(24rpx + env(safe-area-inset-bottom));
}

.orders-sheet-head {
  padding: 28rpx 36rpx 18rpx;
  border-bottom: 0;
}

.orders-sheet-title {
  font-size: 36rpx;
  line-height: 1.2;
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
  color: #6b7280;
}

.orders-list {
  padding: 8rpx 32rpx 20rpx;
}

.table-status-card {
  padding: 26rpx;
  border-radius: 24rpx;
  background: #ecfff5;
  border: 2rpx solid #b8f3d0;
  display: flex;
  justify-content: space-between;
  gap: 20rpx;
}

.table-status-mode {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8rpx 18rpx;
  border-radius: 999rpx;
  background: #07C160;
  text { color: #fff; font-size: 24rpx; font-weight: 800; }
}

.table-status-no {
  display: block;
  margin-top: 14rpx;
  font-size: 40rpx;
  font-weight: 900;
  color: #111827;
}

.table-status-copy {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  text-align: right;
  min-width: 0;
}

.table-status-main {
  font-size: 30rpx;
  font-weight: 900;
  color: #07C160;
}

.table-status-sub {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #64748b;
}

.order-progress-card,
.current-order-card,
.history-orders-card {
  margin-top: 20rpx;
  padding: 24rpx;
  border-radius: 24rpx;
  background: #fff;
  border: 2rpx solid #f1f5f9;
}

.order-progress-step {
  position: relative;
  display: flex;
  gap: 18rpx;
  padding-bottom: 24rpx;
}

.order-progress-step:last-child {
  padding-bottom: 0;
}

.order-progress-step::after {
  content: '';
  position: absolute;
  left: 11rpx;
  top: 28rpx;
  bottom: 2rpx;
  width: 2rpx;
  background: #e5e7eb;
}

.order-progress-step:last-child::after {
  display: none;
}

.order-progress-step.done::after {
  background: #07C160;
}

.order-progress-dot {
  position: relative;
  z-index: 1;
  width: 24rpx;
  height: 24rpx;
  margin-top: 4rpx;
  border-radius: 50%;
  background: #d1d5db;
}

.order-progress-step.done .order-progress-dot,
.order-progress-step.active .order-progress-dot {
  background: #07C160;
}

.order-progress-title {
  display: block;
  font-size: 28rpx;
  font-weight: 800;
  color: #9ca3af;
}

.order-progress-step.done .order-progress-title,
.order-progress-step.active .order-progress-title {
  color: #111827;
}

.order-progress-desc {
  display: block;
  margin-top: 4rpx;
  font-size: 22rpx;
  color: #94a3b8;
}

.current-order-head,
.current-order-summary,
.history-orders-head,
.history-order-row {
  display: flex;
  justify-content: space-between;
  gap: 20rpx;
  align-items: center;
}

.current-order-title {
  display: block;
  font-size: 30rpx;
  font-weight: 900;
  color: #111827;
}

.current-order-no {
  display: block;
  margin-top: 4rpx;
  font-size: 24rpx;
  color: #64748b;
}

.current-order-total {
  font-size: 36rpx;
  font-weight: 900;
  color: #07C160;
}

.current-order-summary {
  margin-top: 20rpx;
  padding-top: 18rpx;
  border-top: 2rpx solid #f1f5f9;
  text { font-size: 26rpx; color: #475569; }
  text:first-child { color: #171A1D; font-weight: 900; }
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
  text { font-size: 26rpx; color: #64748b; }
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
  color: #171A1D;
  font-weight: 700;
}

.order-detail-spec {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: #8A9099;
}

.order-detail-qty {
  width: 72rpx;
  text-align: right;
  font-size: 26rpx;
  color: #64748b;
}

.order-detail-amount {
  width: 110rpx;
  text-align: right;
  font-size: 26rpx;
  color: #171A1D;
  font-weight: 800;
}

.history-orders-head {
  text:first-child { font-size: 28rpx; font-weight: 800; color: #111827; }
  text:last-child { font-size: 24rpx; color: #07C160; font-weight: 700; }
}

.history-order-block {
  margin-top: 18rpx;
  padding-top: 18rpx;
  border-top: 2rpx solid #f1f5f9;
}

.history-order-row {
  text { font-size: 25rpx; color: #64748b; }
  text:last-child { color: #111827; font-weight: 800; }
}

.history-order-items {
  margin-top: 10rpx;
}

.history-order-item-row {
  display: flex;
  justify-content: space-between;
  gap: 16rpx;
  padding: 8rpx 0;
  text { font-size: 23rpx; color: #8A9099; }
  text:first-child { flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  text:last-child { color: #475569; font-weight: 700; }
}

.orders-actions {
  flex-shrink: 0;
  padding: 8rpx 32rpx 0;
  background: #fff;
}

.orders-primary-btn,
.orders-secondary-btn {
  height: 88rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  text { font-size: 30rpx; font-weight: 900; }
}

.orders-primary-btn {
  background: #07C160;
  box-shadow: 0 12rpx 28rpx rgba(7, 193, 96, 0.22);
  text { color: #fff; }
}

.orders-secondary-btn {
  margin-top: 16rpx;
  background: #f3f5f7;
  text { color: #374151; }
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

.loading-ring {
  width: 72rpx;
  height: 72rpx;
  border: 6rpx solid #e8e8e8;
  border-top-color: #07C160;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.loading-text { font-size: 28rpx; color: #9ca3af; }

.retry-btn {
  margin-top: 24rpx;
  padding: 16rpx 48rpx;
  border-radius: 24rpx;
  background: #07C160;
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
  color: #374151;
  font-weight: 600;
}
.coupon-select-tip {
  font-size: 24rpx;
  color: #ef4444;
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
  border-color: #07C160;
  background: #f0fdf4;
  .coupon-chip-amount { color: #07C160; }
  .coupon-chip-min { color: #16a34a; }
}
.coupon-chip-amount {
  font-size: 30rpx;
  font-weight: 700;
  color: #ef4444;
}
.coupon-chip-min {
  font-size: 20rpx;
  color: #9ca3af;
  margin-top: 4rpx;
}


.review-mask {
  align-items: center;
  justify-content: center;
}
.review-card {
  background: #fff;
  border-radius: 32rpx;
  padding: 56rpx 48rpx 40rpx;
  width: 620rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.review-title {
  font-size: 36rpx;
  font-weight: 700;
  color: #111827;
  margin-bottom: 8rpx;
}
.review-sub {
  font-size: 24rpx;
  color: #9ca3af;
  margin-bottom: 36rpx;
}
.review-stars {
  display: flex;
  gap: 16rpx;
  margin-bottom: 20rpx;
}
.review-star {
  font-size: 64rpx;
  color: #e5e7eb;
  transition: color .15s;
}
.review-star--on {
  color: #f59e0b;
}
.review-hint-row {
  height: 36rpx;
  margin-bottom: 24rpx;
}
.review-hint {
  font-size: 26rpx;
  color: #f59e0b;
  font-weight: 600;
}
.review-textarea {
  width: 100%;
  min-height: 120rpx;
  font-size: 26rpx;
  color: #374151;
  background: #f8fafc;
  border: none;
  border-radius: 16rpx;
  padding: 20rpx 24rpx;
  box-sizing: border-box;
  margin-bottom: 32rpx;
}
.review-actions {
  display: flex;
  gap: 20rpx;
  width: 100%;
}
.review-btn-skip {
  flex: 1;
  height: 88rpx;
  border-radius: 44rpx;
  border: 1rpx solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: center;
  text { font-size: 28rpx; color: #9ca3af; }
}
.review-btn-submit {
  flex: 2;
  height: 88rpx;
  border-radius: 44rpx;
  background: #07C160;
  display: flex;
  align-items: center;
  justify-content: center;
  text { font-size: 28rpx; color: #fff; font-weight: 700; }
}
.review-btn-submit--disabled {
  background: #d1d5db;
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
  text { font-size: 24rpx; color: #64748b; }
}
.remark-chip--on {
  border-color: #07C160;
  background: #f0fdf4;
  text { color: #07C160; font-weight: 600; }
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
  color: #64748b;
}

.remark-input {
  flex: 1;
  font-size: 26rpx;
  color: #111827;
  background: transparent;
}

.remark-placeholder { color: #c8c9cc; }


.member-price {
  font-size: 24rpx;
  color: #07C160;
  font-weight: 600;
  margin-left: 8rpx;
}


.cart-row-spec {
  display: block;
  font-size: 22rpx;
  color: #9ca3af;
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
  color: #535a63;
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
  color: #171a1d;
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
  color: #8a9099;
  font-size: 44rpx;
  line-height: 1;
}

.spec-sheet-desc {
  display: -webkit-box;
  margin-top: 8rpx;
  color: #8a9099;
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
  color: #07c160;
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

.spec-group-name {
  color: #171a1d;
  font-size: 32rpx;
  font-weight: 600;
  line-height: 44rpx;
}

.spec-required {
  color: #07c160;
  font-size: 22rpx;
  font-weight: 400;
  line-height: 32rpx;
}

.spec-optional {
  color: #a0a5ac;
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
  color: #535a63;
  font-size: 28rpx;
  line-height: 40rpx;
  box-sizing: border-box;
  transition: background 0.15s, color 0.15s, border-color 0.15s;

  &--on {
    border-color: #07c160;
    background: #e8f9f0;
    color: #07c160;
    font-weight: 600;
  }
}

.spec-option-list--single .spec-option {
  min-width: 148rpx;
}

.spec-price {
  color: #8a9099;
  font-size: 24rpx;
  line-height: 34rpx;
  .spec-option--on & { color: #07c160; }
}

.spec-remark-block {
  margin-top: 32rpx;
}

.item-remark-input {
  width: 100%;
  min-height: 152rpx;
  max-height: 176rpx;
  padding: 24rpx;
  border: 1rpx solid #e5e7ea;
  border-radius: 20rpx;
  background: #fff;
  box-sizing: border-box;
  color: #171a1d;
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
  color: #535a63;
}

.spec-counter-row .counter-btn.plus {
  background: #07c160;
  color: #fff;
}

.spec-counter-row .counter-btn text {
  font-size: 36rpx;
  font-weight: 600;
  line-height: 1;
}

.spec-counter-row .counter-num {
  width: 56rpx;
  color: #171a1d;
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
  background: #07c160;
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

.closed-icon {
  font-size: 80rpx;
  display: block;
  margin-bottom: 20rpx;
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
  color: #9ca3af;
  line-height: 1.6;
  margin-bottom: 40rpx;
}

.closed-btn {
  padding: 24rpx 0;
  background: #f3f4f6;
  border-radius: 20rpx;
  text {
    font-size: 30rpx;
    color: #6b7280;
    font-weight: 600;
  }
}

.checkout-auth-mask { align-items: flex-end; }
.checkout-auth-sheet { width: 100%; max-height: 55vh; background: #fff; border-radius: 32rpx 32rpx 0 0; padding: 18rpx 36rpx calc(22rpx + env(safe-area-inset-bottom)); box-sizing: border-box; display: flex; flex-direction: column; align-items: stretch; animation: authSheetIn .2s ease-out; }
.checkout-auth-handle { width: 72rpx; height: 8rpx; border-radius: 999rpx; background: #e5e7eb; align-self: center; margin-bottom: 20rpx; }
.checkout-auth-title { color: #111827; font-size: 38rpx; font-weight: 900; text-align: center; line-height: 1.25; }
.checkout-auth-desc { margin-top: 12rpx; color: #475569; font-size: 27rpx; line-height: 1.55; text-align: center; }
.checkout-auth-order { margin-top: 22rpx; padding: 22rpx 24rpx; border-radius: 22rpx; background: #f8fafb; border: 1rpx solid #edf0f2; }
.checkout-auth-row { display: flex; align-items: center; justify-content: space-between; gap: 24rpx; color: #94a3b8; font-size: 26rpx; line-height: 1.5; }
.checkout-auth-row + .checkout-auth-row { margin-top: 12rpx; }
.checkout-auth-row text:last-child { color: #111827; font-weight: 800; text-align: right; max-width: 440rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.checkout-auth-row--amount text:last-child { color: #0aa65a; font-size: 32rpx; font-weight: 900; }
.checkout-auth-auto { margin-top: 18rpx; padding: 18rpx 20rpx; border-radius: 18rpx; background: #ecfbf3; color: #0f8f50; font-size: 24rpx; line-height: 1.55; }
.checkout-auth-primary { margin-top: 24rpx; height: 96rpx; border-radius: 24rpx; background: #16c76f; color: #fff; font-size: 31rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; box-shadow: 0 14rpx 34rpx rgba(16, 196, 105, .22); }
.checkout-auth-primary[disabled] { opacity: .72; box-shadow: none; }
.checkout-auth-cancel { height: 72rpx; display: flex; align-items: center; justify-content: center; color: #64748b; font-size: 28rpx; }
.checkout-auth-member { display: block; color: #98a2b3; font-size: 22rpx; line-height: 1.45; text-align: center; margin-top: 2rpx; }
.checkout-auth-privacy { display: block; color: #a8b1bd; font-size: 21rpx; line-height: 1.45; text-align: center; margin-top: 10rpx; }
@keyframes authSheetIn { from { transform: translateY(24rpx); opacity: .92; } to { transform: translateY(0); opacity: 1; } }

.order-remark-row { border-top: 0 !important; padding-top: 0 !important; }

/* Cart micro interactions */
.counter-btn {
  transform-origin: center;
  transition: transform 160ms ease-out;
}

.counter-btn--pressing {
  animation: addButtonPress 160ms ease-out;
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
  45% { transform: scale(.95); }
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
  .checkout-btn {
    transition-duration: 0ms;
    animation: none;
  }
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
  color: #111827;
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
  color: #98a2b3;
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
  color: #0aa65a;
  font-size: 27rpx;
  font-weight: 800;
  line-height: 1.55;
}

.success-sheet .order-status-bar.warning .order-status-text {
  color: #9a6a21;
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
  color: #98a2b3;
  font-size: 27rpx;
}

.success-summary-value {
  color: #111827;
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
  border-radius: 24rpx;
  background: #10c469;
  box-shadow: 0 12rpx 24rpx rgba(16,196,105,.18);
}

.success-sheet .success-btn-primary text {
  color: #fff;
  font-size: 32rpx;
  font-weight: 900;
}

.success-sheet .success-btn-secondary {
  height: 94rpx;
  border-radius: 24rpx;
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
  color: #667085;
  font-size: 26rpx;
  font-weight: 700;
}

.success-safe-tip {
  display: block;
  margin: 16rpx 10rpx 0;
  color: #98a2b3;
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
</style>





















































































