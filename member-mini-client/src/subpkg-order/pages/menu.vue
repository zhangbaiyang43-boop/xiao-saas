<template>
  <view class="order-page">


    <!-- 门店头条（方案 B）：全宽压在分类/菜品两列之上。
    点餐 tab 上滑过阈值后收起，改由迷你条承接；其它 tab 一直显示。 -->
    <ShopHeader
      v-show="activeTab !== 'order' || headerVisible"
      :shop-logo="shopLogo"
      :shop-name="shopName"
      :table-display-text="tableDisplayText"
      :order-mode-display-text="orderModeDisplayText"
      :store-closed="storeClosed"
      :dish-count="allDishes.length"
      :coupon-count="availableCoupons.length"
      @show-table-hint="showTableHint"
    />

    <!-- 点餐 tab 收起后的迷你条：店名 + 桌号芯片。 -->
    <view
      v-if="activeTab === 'order'"
      class="mini-shop-bar"
      :class="{ 'mini-shop-bar--visible': !headerVisible }"
      @click="showTableHint"
    >
      <text class="mini-shop-bar-name">{{ shopName }}</text>
      <text class="mini-shop-bar-chip">{{ tableDisplayText }}</text>
    </view>

    <!-- 优惠券条：全宽，在头部/迷你条之下、分类菜品之上（不进右侧滚动区）。 -->
    <view v-if="activeTab === 'order'" class="order-coupon-wrap">
      <CouponBar
        :coupon-bar-visible="couponBarVisible"
        :coupon-bar-prefix="couponBarPrefix"
        :coupon-bar-amount="couponBarAmount"
        :is-customer-logged-in="isCustomerLoggedIn"
        :new-customer-coupon-preview="newCustomerCouponPreview"
        :new-customer-hook-text="newCustomerHookText"
        :member-authorizing="memberAuthorizing"
        :coupon-nudge-state="couponNudgeState"
        :total-price="totalPrice"
        :format-price="formatPrice"
        @open-coupon-picker="openCouponPicker"
        @phone-auth="handleMemberCardAuth"
        @coupon-add-on="goCouponAddOn"
      />
    </view>

    <DishList
      v-show="activeTab === 'order'"
      @scroll-position="onDishScrollPosition"
      :categories="categories"
      :active-category="activeCategory"
      :category-scroll-top="categoryScrollTop"
      :scroll-target="scrollTarget"
      :last-order-items="lastOrderItems"
      :loading="loading"
      :load-error="loadError"
      :all-dishes="allDishes"
      :image-load-failed="imageLoadFailed"
      :qty-pulse-key="qtyPulseKey"
      :add-press-key="addPressKey"
      :ignore-scroll="ignoreScroll"
      :category-icon-class="categoryIconClass"
      :category-display-name="categoryDisplayName"
      :dishes-by-category="dishesByCategory"
      :is-featured="isFeatured"
      :is-sold-out="isSoldOut"
      :dish-image="dishImage"
      :dish-card-tags="dishCardTags"
      :is-strong-dish-tag="isStrongDishTag"
      :dish-card-desc="dishCardDesc"
      :show-dish-sales="showDishSales"
      :dish-price-text="dishPriceText"
      :dish-price-suffix="dishPriceSuffix"
      :dish-option-kind-count="dishOptionKindCount"
      :option-count-text="optionCountText"
      :cart-count="cartCount"
      :has-specs="hasSpecs"
      @switch-category="switchCategory"
      @active-category-change="handleActiveCategoryChange"
      @reorder-item="reorderItem"
      @reorder-all="reorderAll"
      @retry-load="loadMenu"
      @open-cart="openCart"
      @open-spec-sheet="openSpecSheet"
      @image-error="markDishImageFailed"
      @open-product-detail="openProductDetail"
      @remove-from-cart="removeFromCart"
      @add-to-cart="addToCart"
    />


    <scroll-view v-show="activeTab === 'home'" class="tab-scroll" scroll-y>
      <HomeTab
        :shop-name="shopName"
        :home-status-desc="homeStatusDesc"
        :store-closed="storeClosed"
        :can-start-ordering="canStartOrdering"
        :home-coupon-hint="homeCouponHint"
        :home-order-button-text="homeOrderButtonText"
        :featured-dish="featuredDish"
        :featured-dish-tag="featuredDishTag"
        :can-home-add="canHomeAdd"
        :home-last-order-items="homeLastOrderItems"
        :image-load-failed="imageLoadFailed"
        :dish-image="dishImage"
        :dish-card-desc="dishCardDesc"
        :dish-price-text="dishPriceText"
        :dish-price-suffix="dishPriceSuffix"
        :has-specs="hasSpecs"
        @start-order="handleHomeStartOrder"
        @open-product-detail="openProductDetail"
        @featured-add="handleFeaturedAdd"
        @image-error="markDishImageFailed"
        @reorder-item="handleHomeReorderItem"
        @reorder-all="handleHomeReorderAll"
      />
    </scroll-view>
    <scroll-view v-show="activeTab === 'card'" class="tab-scroll" scroll-y>
      <MemberCard
        :banner-info="bannerInfo"
        :shop-name="shopName"
        :member-level-badge-src="memberLevelBadgeSrc"
        :member-level-label="memberLevelLabel"
        :member-upgrade-text="memberUpgradeText"
        :member-progress-percent="memberProgressPercent"
        :member-since-text="memberSinceText"
        :usable-member-coupons="usableMemberCoupons"
        :has-customer-identity="hasCustomerIdentity"
        :member-loading="memberLoading"
        :new-customer-hook-text="newCustomerHookText"
        :member-authorizing="memberAuthorizing"
        :coupon-amount-text="couponAmountText"
        :coupon-condition-text="couponConditionText"
        :coupon-validity-text="couponValidityText"
        @go-order="goOrderFromMember"
        @reload="loadMemberStatus"
        @use-coupon="useMemberCoupon"
        @phone-auth="handleMemberCardAuth"
      />
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



    <CartBar
      v-show="activeTab === 'order'"
      :total-count="totalCount"
      :cart-icon-pulse="cartIconPulse"
      :cart-badge-text="cartBadgeText"
      :cart-badge-pulse="cartBadgePulse"
      :total-price="totalPrice"
      :amount-pulse="amountPulse"
      :format-price="formatPrice"
      @open-cart="openCart"
    />


    <BottomNav
      :active-tab="activeTab"
      :total-count="totalCount"
      :banner-info="bannerInfo"
      @switch-tab="tab => activeTab = tab"
      @switch-to-card="switchToCard"
      @go-mine="goMine"
    />


    <!-- Order confirmation sheet -->
    <CheckoutSheet
      v-if="showCart"
      :confirmation-text="confirmationText"
      :order-mode-text="orderModeText"
      :table-no="tableNo"
      :items-expanded="itemsExpanded"
      :cart-items="cartItems"
      :total-count="totalCount"
      :total-price="totalPrice"
      :qty-pulse-key="qtyPulseKey"
      :order-remark-expanded="orderRemarkExpanded"
      :order-remark-summary="orderRemarkSummary"
      :order-remark-chips="orderRemarkChips"
      :remark="remark"
      :show-order-remark-extra="showOrderRemarkExtra"
      :discount-amount="discountAmount"
      :available-coupons="availableCoupons"
      :confirm-payment-label="confirmPaymentLabel"
      :wechat-pay-amount="wechatPayAmount"
      :expected-points="expectedOrderPoints"
      :is-member="isMember"
      :is-logged-in="isCustomerLoggedIn"
      :member-level-label="memberLevelLabel"
      :member-summary-text="checkoutMemberSummaryText"
      :can-submit-order="canSubmitOrder"
      :ordering="ordering"
      :paying="paying"
      :pay-button-text="payButtonText"
      @close="closeOrderConfirm"
      @show-table-hint="showTableHint"
      @toggle-items-expanded="toggleItemsExpanded"
      @remove-from-cart="removeFromCart"
      @increase-cart-item="increaseCartItem"
      @clear-cart="clearCart"
      @toggle-order-remark-expanded="toggleOrderRemarkExpanded"
      @toggle-remark-chip="toggleRemarkChip"
      @show-order-remark-extra="showOrderRemarkExtra = true"
      @update:remark="remark = $event"
      @open-coupon-picker="openCouponPicker"
      @checkout="goCheckout"
    />

    <CouponPicker
      v-if="showCouponPicker"
      :selected-coupon-id="selectedCouponId"
      :coupon-picker-list="couponPickerList"
      :total-price="totalPrice"
      :coupon-picker-amount="couponPickerAmount"
      :coupon-picker-cond-text="couponPickerCondText"
      :format-price="formatPrice"
      @cancel="closeCouponPicker"
      @select-coupon="pickCoupon"
    />
    <CheckoutAuthSheet
      v-if="showCheckoutAuth"
      :auth-sheet-text="authSheetText"
      :shop-name="shopName"
      :table-no="tableNo"
      :auth-amount-label="authAmountLabel"
      :confirmation-text="confirmationText"
      :wechat-pay-amount="wechatPayAmount"
      :authorizing="authorizing"
      :ordering="ordering"
      :paying="paying"
      :auth-primary-text="authPrimaryText"
      @cancel="cancelCheckoutAuth"
      @getphonenumber="handleCheckoutAuth"
    />

    <PaymentSuccessSheet
      v-if="showSuccess"
      :success-text="successText"
      :currency="confirmationText.currency"
      :success-total="successTotal"
      :success-status-tone="successStatusTone"
      :success-status-text="successStatusText"
      :earned-coupon="earnedCoupon"
      :coupon-reminder-template-id="couponReminderTemplateId"
      :reminder-requested="reminderRequested"
      :requesting-reminder="requestingReminder"
      :table-no="tableNo"
      :order-mode-text="orderModeText"
      :success-order-no="successOrderNo"
      :success-order-item-count="successOrderItemCount"
      :format-price="formatPrice"
      :coupon-validity-text="couponValidityText"
      @request-coupon-reminder="requestCouponReminder"
      @close-and-wait="closeSuccessAndWait"
      @continue-ordering="continueOrdering"
      @view-order-detail="viewOrderDetail"
    />

    <WelcomeCouponSheet
      :show-welcome-coupon="showWelcomeCoupon"
      :welcome-coupon-data="welcomeCouponData"
      :welcome-coupon-cond-text="welcomeCouponCondText"
      :store-closed="storeClosed"
      :table-session-closed="tableSessionClosed"
      :shop-name="shopName"
      :table-session-closed-notice="tableSessionClosedNotice"
      :closed-notice="closedNotice"
      :format-price="formatPrice"
      @close="closeWelcomeCoupon"
      @go-order="goOrderFromWelcomeCoupon"
      @go-mine="goMine"
      @keep-browsing="storeClosed = false"
    />

    <TableBillSheet
      v-if="showOrders && isSharedBillMode"
      :load-error="loadError"
      :table-status-view="tableStatusView"
      :table-no="tableNo"
      :order-mode-text="orderModeText"
      :shared-bill-sub-label="sharedBillSubLabel"
      :table-total="tableTotal"
      :table-item-count="tableItemCount"
      :table-order-groups="tableOrderGroups"
      :order-item-image-failed="orderItemImageFailed"
      :can-continue-order="canContinueOrder"
      :can-checkout="canCheckout"
      :is-table-settled="isTableSettled"
      :still-preparing="stillPreparing"
      :postpay-ready-to-settle="postpayReadyToSettle"
      :table-checkouting="tableCheckouting"
      :checkout-requested="checkoutRequested"
      :table-account-scroll-into="tableAccountScrollInto"
      :format-price="formatPrice"
      :order-item-image="orderItemImage"
      :order-item-name="orderItemName"
      :order-item-spec-text="orderItemSpecText"
      :order-item-qty="orderItemQty"
      :order-item-amount="orderItemAmount"
      @close="showOrders = false"
      @retry-load="loadMenu"
      @continue-order="handleTableContinueOrder"
      @checkout="handleTableCheckout"
      @scroll-to-top="scrollTableAccountToTop"
      @mark-image-failed="markOrderItemImageFailed"
    />
    <OrderHistorySheet
      v-if="showOrders && !isSharedBillMode"
      :current-table-order="currentTableOrder"
      :history-table-orders="historyTableOrders"
      :show-all-orders="showAllOrders"
      :table-order-status-tone="tableOrderStatusTone"
      :table-order-status-icon="tableOrderStatusIcon"
      :table-order-status-badge="tableOrderStatusBadge"
      :table-order-next-action="tableOrderNextAction"
      :table-order-status-title="tableOrderStatusTitle"
      :table-order-status-hint="tableOrderStatusHint"
      :table-order-progress-sub="tableOrderProgressSub"
      :table-order-timeline="tableOrderTimeline"
      :current-order-item-count="currentOrderItemCount"
      :current-order-main-item-text="currentOrderMainItemText"
      :table-order-primary-button-text="tableOrderPrimaryButtonText"
      :table-no="tableNo"
      :order-mode-text="orderModeText"
      :format-price="formatPrice"
      :order-item-name="orderItemName"
      :order-item-spec-text="orderItemSpecText"
      :order-item-qty="orderItemQty"
      :order-item-amount="orderItemAmount"
      :order-item-count="orderItemCount"
      @close="showOrders = false"
      @toggle-history="showAllOrders = !showAllOrders"
    />

    <SpecSheet
      v-if="showSpecSheet"
      :spec-dish="specDish"
      :detail-image-failed="detailImageFailed"
      :currency="confirmationText.currency"
      :spec-dish-desc="specDishDesc"
      :spec-base-price="specBasePrice"
      :spec-radio-groups="specRadioGroups"
      :spec-extra-options="specExtraOptions"
      :spec-text="specText"
      :selected-extras="selectedExtras"
      :item-remark="itemRemark"
      :filtered-remark-chips="filteredRemarkChips"
      :show-item-remark-extra="showItemRemarkExtra"
      :spec-qty="specQty"
      :can-go-next-spec="canGoNextSpec"
      :spec-primary-text="specPrimaryText"
      :dish-image="dishImage"
      :dish-placeholder-style="dishPlaceholderStyle"
      :format-price="formatPrice"
      :is-spec-selected="isSpecSelected"
      @cancel="cancelSpec"
      @confirm="handleSpecPrimary"
      @image-error="detailImageFailed = true"
      @toggle-spec="toggleSpec"
      @toggle-extra="toggleExtra"
      @toggle-remark-chip="toggleItemRemarkChip"
      @show-remark-extra="showItemRemarkExtra = true"
      @update:item-remark="itemRemark = $event"
      @qty-increase="specQty++"
      @qty-decrease="specQty--"
    />


    <LoadingStates
      :load-error="loadError"
      :loading="loading"
      @retry-load="loadMenu"
    />


  </view>
</template>

<script>
import { ref, computed, watch, nextTick } from 'vue'
import { getMenuItems, getShopInfo } from '@/api/order'
import { getCustomerCoupons, remindMeForCoupon } from '@/api/coupon'
import { buildCouponNudgeState } from '../utils/couponNudge.mjs'
import { consumeStart, flushPending, recordSample } from '@/utils/perf'
import { reportError } from '@/utils/monitor'
import OrderBubble from '@/components/order-bubble/order-bubble.vue'
import MemberCard from '../components/MemberCard.vue'
import SpecSheet from '../components/SpecSheet.vue'
import CouponPicker from '../components/CouponPicker.vue'
import HomeTab from '../components/HomeTab.vue'
import TableBillSheet from '../components/TableBillSheet.vue'
import OrderHistorySheet from '../components/OrderHistorySheet.vue'
import PaymentSuccessSheet from '../components/PaymentSuccessSheet.vue'
import CheckoutSheet from '../components/CheckoutSheet.vue'
import CheckoutAuthSheet from '../components/CheckoutAuthSheet.vue'
import DishList from '../components/DishList.vue'
import CartBar from '../components/CartBar.vue'
import CouponBar from '../components/CouponBar.vue'
import WelcomeCouponSheet from '../components/WelcomeCouponSheet.vue'
import { useOrderFormatters } from '../composables/useOrderFormatters.js'
import { useWelcomeCoupon } from '../composables/useWelcomeCoupon.js'
import { useMemberCard } from '../composables/useMemberCard.js'
import { useCouponPicker } from '../composables/useCouponPicker.js'
import { useDishCategories } from '../composables/useDishCategories.js'
import { useHomeTabView } from '../composables/useHomeTabView.js'
import { useTableBillView } from '../composables/useTableBillView.js'
import { useSuccessSheetView } from '../composables/useSuccessSheetView.js'
import { useRemarkChips } from '../composables/useRemarkChips.js'
import { useCartFeedback } from '../composables/useCartFeedback.js'
import { useCategoryScroll } from '../composables/useCategoryScroll.js'
import { useFailedImageMap } from '../composables/useFailedImageMap.js'
import { useHistoryReorder } from '../composables/useHistoryReorder.js'
import { useMyOrdersStore } from '../composables/useMyOrdersStore.js'
import { useSpecSheet } from '../composables/useSpecSheet.js'
import { useMemberAuth } from '../composables/useMemberAuth.js'
import { useTableCheckout } from '../composables/useTableCheckout.js'
import { useOrderStatusPoll } from '../composables/useOrderStatusPoll.js'
import { useCheckout } from '../composables/useCheckout.js'
import { useDiningSession } from '../composables/useDiningSession.js'
import ShopHeader from '../components/ShopHeader.vue'
import BottomNav from '../components/BottomNav.vue'
import LoadingStates from '../components/LoadingStates.vue'
import { orderModeText, confirmationText, successText, specText, authSheetText } from '../utils/orderText.js'
const wxLogin = () => new Promise((resolve, reject) => {
  uni.login({
    provider: 'weixin',
    success: (res) => res.code ? resolve(res.code) : reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5')),
    fail: () => reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u5c0f\u7a0b\u5e8f\u73af\u5883'))
  })
})

export default {
  components: { OrderBubble, MemberCard, SpecSheet, CouponPicker, HomeTab, TableBillSheet, OrderHistorySheet, PaymentSuccessSheet, CheckoutSheet, CheckoutAuthSheet, DishList, CartBar, CouponBar, WelcomeCouponSheet, ShopHeader, BottomNav, LoadingStates },
  setup() {
    const {
      formatPrice, dishImage, dishPlaceholderStyle, hasSpecs, isSoldOut, dishCardDesc,
      dishPriceBase, dishPriceText, dishPriceSuffix, dishOriginalPrice, showDishSales,
      couponAmountText, couponConditionText, couponValidityText, couponPickerAmount, couponPickerCondText,
      orderItemName, orderItemQty, orderItemAmount, orderItemSpecText, orderItemImage, orderItemCount,
      statusLabel, dishTags, normalizeDishTag, isStrongDishTag, dishCardTags, isFeatured,
      pickAvatarChar,
    } = useOrderFormatters()
    const tableNo = ref('')
    const shopId = ref('')
    const shopName = ref(uni.getStorageSync('tenant_name') || '\u672a\u6765\u9910\u5385')
    const shopLogo = ref('')
    const shopCreatedAt = ref('')
    const diningSessionId = ref(uni.getStorageSync('dining_session_id') || '')
    const diningParticipantToken = ref(uni.getStorageSync('dining_participant_token') || '')
    const diningClientId = ref(uni.getStorageSync('dining_client_id') || '')
    const paymentMode = ref('prepay')
    const normalizePaymentMode = (mode) => {
      const value = String(mode || 'prepay').trim()
      return ['prepay', 'postpay', 'table_account'].includes(value) ? value : 'prepay'
    }
    const todayActivity = ref('')
    const loading = ref(false)
    const loadError = ref(false)
    const ordering = ref(false)
    // 提交订单的幂等键：开开购物车时生成一次，
    // 同一次结算内的重试（弱网超时后重新提交）都带同一个值，
    // 后端用它返回同一张订单而不是建出第二张。
    const pendingSubmitRequestId = ref('')
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
    const {
      showWelcomeCoupon, welcomeCouponData, welcomeCouponCondText,
      consumeWelcomeCoupon, checkWelcomeCoupon, closeWelcomeCoupon, goOrderFromWelcomeCoupon,
    } = useWelcomeCoupon(() => { activeTab.value = 'order' })
    const orderNo = ref('')
    const orderId = ref('')
    const orderStatus = ref('pending') // pending | preparing | done
    const successItems = ref([])
    const successTotal = ref(0)
    const successDiscount = ref(0)
    const showCheckoutAuth = ref(false)
    const authorizing = ref(false)
    const authActionStatus = ref('idle')
    const pendingPaymentIntent = ref(null)
    const paying = ref(false)
    const paymentFailed = ref(false)  // 上一次点"去支付"真的失败了（不是用户取消）——按钮要明确提示这是在重试，不能让用户猜要不要再点一次
    const payAmount = ref(0)
    const pendingOrderId = ref('')

    const myOrders = ref([])
    const showOrders = ref(false)
    const showAllOrders = ref(false)
    const tableSessionStatus = ref('')
    const tableSessionTotal = ref(0)
    const tableCheckouting = ref(false)
    const checkoutRequestedAt = ref('')
    const tableSessionClosedAt = ref('')   // 真正的结账时间（区别于下单时间），给"查看结账详情"用
    const tableAccountScrollInto = ref('')
    const { failed: orderItemImageFailed, markFailed: markOrderItemImageFailed } = useFailedImageMap()
    const storeClosed = ref(false)
    const tableSessionClosed = ref(false)
    const tableSessionClosedNotice = ref('\u672c\u684c\u7528\u9910\u5df2\u7ed3\u675f\uff0c\u5982\u9700\u7ee7\u7eed\u70b9\u9910\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u8fdb\u5165\u65b0\u4e00\u684c')
    const {
      bannerInfo, isMember, memberLoading, memberAuthorizing, memberSinceText,
      memberLevelLabel, memberLevelBadgeSrc, memberProgressPercent, memberUpgradeText,
      usableMemberCoupons, goOrderFromMember, useMemberCoupon,
    } = useMemberCard({
      shopCreatedAt,
      formatPrice,
      onGoOrder: () => { activeTab.value = 'order' },
      onUseCoupon: (id) => { selectedCouponId.value = id },
    })
    const isCustomerLoggedIn = ref(Boolean(uni.getStorageSync('customer_token')))
    const authStateVersion = ref(0)
    const activeTab = ref('order')

    // 方案1：全宽 ShopHeader 在两列之上；列表 scrollTop 过阈值后收起并露出迷你条。
    const HEADER_COLLAPSE_SCROLL = 48
    const headerVisible = ref(true)
    const onDishScrollPosition = (scrollTop) => {
      if (activeTab.value !== 'order') return
      headerVisible.value = scrollTop < HEADER_COLLAPSE_SCROLL
    }
    // 切回点餐 tab 时复位，避免停在收起态。
    watch(activeTab, (tab) => {
      if (tab === 'order') headerVisible.value = true
    })
    const shopDistance = ref('')

    const goMine = () => uni.navigateTo({ url: '/pages/mine/mine' })

    const availableCoupons = ref([])
    const {
      refreshCustomerAuthState, hasCustomerIdentity, loadMemberStatus, switchToCard, handleMemberCardAuth,
    } = useMemberAuth({
      shopId, tableNo, activeTab, isCustomerLoggedIn, authStateVersion, availableCoupons,
      bannerInfo, isMember, memberLoading, memberAuthorizing,
      wxLogin, bindCurrentDiningParticipant: () => bindCurrentDiningParticipant(), pickAvatarChar, checkWelcomeCoupon,
    })

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

    const itemRemark = ref('') // { groupName: [optName] }
    const showItemRemarkExtra = ref(false)
    const remarkChips = ref(['不要辣', '微辣', '不要香菜', '不要葱', '少盐', '打包'])
    const { cleanedText: itemRemarkExtra, toggleChip: toggleItemRemarkChip } = useRemarkChips(itemRemark, remarkChips)
    const { failed: imageLoadFailed, markFailed: markDishImageFailed } = useFailedImageMap()

    const specCartItems = ref([])
    const {
      showSpecSheet, specDish, specQty, specStep, selectedSpecs, selectedExtras, detailImageFailed,
      specSteps, specRadioGroups, specExtraOptions, filteredRemarkChips, specBasePrice, specTotalPrice,
      selectedSpecSummary, specDishDesc, canGoNextSpec, specPrimaryText, isSpecSelected, toggleSpec,
      toggleExtra, cancelSpec, handleSpecPrimary, confirmSpec, openSpecSheet, openProductDetail,
    } = useSpecSheet({
      itemRemark, showItemRemarkExtra, itemRemarkExtra, remarkChips,
      specCartItems, isSoldOut, hasSpecs, formatPrice,
      triggerCartSuccessFeedback: (key) => triggerCartSuccessFeedback(key),
    })

    const {
      normalizeOrderStatus, currentTableOrder, historyTableOrders,
      isTableAccountMode, isPostpayMode, isSharedBillMode, sharedBillSubLabel, tableSessionId,
      tableTotal, tableItemCount, tableOrderGroups,
      isTableSettled, canContinueOrder, stillPreparing, checkoutRequested,
      canCheckout, postpayReadyToSettle, scrollTableAccountToTop, tableStatusView,
      currentTableOrderStatus, tableOrderStatusTone, tableOrderStatusBadge, tableOrderStatusIcon,
      tableOrderNextAction, tableOrderProgressSub, tableOrderPrimaryButtonText, tableOrderStatusTitle,
      tableOrderStatusHint, tableOrderTimeline, currentOrderItemCount, currentOrderItems,
      currentOrderMainItemText, pendingOrderCount,
    } = useTableBillView({
      myOrders, orderId, orderStatus, paymentMode, diningSessionId,
      tableSessionTotal, tableSessionClosed, tableSessionStatus, checkoutRequestedAt,
      tableCheckouting, tableSessionClosedAt, tableAccountScrollInto,
      normalizePaymentMode, orderItemQty, orderItemCount,
    })

    const { saveMyOrders, loadMyOrders, doCancelOrder } = useMyOrdersStore({
      myOrders, shopId, tableNo, orderId, orderStatus, showSuccess, diningParticipantToken,
      stopStatusPoll: () => stopStatusPoll(),
    })

    const {
      persistDiningContext, ensureDiningSession, bindCurrentDiningParticipant, syncDiningOrders, showTableHint,
    } = useDiningSession({
      shopId, tableNo, diningSessionId, diningParticipantToken, diningClientId,
      tableSessionClosed, tableSessionStatus, tableSessionTotal, tableSessionClosedNotice,
      checkoutRequestedAt, tableSessionClosedAt, myOrders,
      normalizePaymentMode, saveMyOrders,
    })

    const {
      successOrderItemCount, successOrderNo, successStatusText, successStatusTone,
      orderStatusText, orderStatusClass,
    } = useSuccessSheetView({ successItems, orderNo, orderId, orderStatus })

    const {
      startStatusPoll, stopStatusPoll, startTablePresencePoll, stopTablePresencePoll, refreshAllOrderStatuses,
    } = useOrderStatusPoll({
      orderStatus, diningParticipantToken, myOrders, saveMyOrders, syncDiningOrders, normalizeOrderStatus,
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

    const remark = ref('')
    const orderRemarkChips = ref(['\u4e00\u8d77\u4e0a\u83dc', '\u5168\u90e8\u6253\u5305', '\u52a0\u53cc\u7b77\u5b50', '\u4e0d\u7528\u9910\u5177', '\u6709\u513f\u7ae5\u7528\u9910'])
    const showOrderRemarkExtra = ref(false)
    const { cleanedText: orderRemarkExtra, toggleChip: toggleRemarkChip } = useRemarkChips(remark, orderRemarkChips)
    // 整单备注默认折叠成一行，跟"已选商品"用同一个模式（menu.vue 里 toggleItemsExpanded
    // 那一行），避免5个chip换行铺开撑高确认单、跟价格支付这些核心信息抢视觉权重。
    // 折叠态靠这句摘要保留可见性，不会出现"以为选了、其实没点开"的问题。
    const orderRemarkExpanded = ref(false)
    const toggleOrderRemarkExpanded = () => { orderRemarkExpanded.value = !orderRemarkExpanded.value }
    const orderRemarkSummary = computed(() => remark.value.trim() || confirmationText.orderRemarkEmpty)
    const deliveryEnabled = ref(false)
    const {
      selectedCouponId, selectedCoupon, couponBarVisible, bestCouponValue,
      couponBarText, couponBarPrefix, couponBarAmount, discountAmount, finalPrice,
      showCouponPicker, couponPickerList, openCouponPicker, closeCouponPicker, pickCoupon,
    } = useCouponPicker({
      availableCoupons,
      getTotalPrice: () => totalPrice.value,
      isCustomerLoggedIn,
      formatPrice,
    })
    const wechatPayAmount = computed(() => finalPrice.value)
    const expectedOrderPoints = computed(() => {
      if (wechatPayAmount.value <= 0) return 0
      const multiplier = bannerInfo.value?.pointMultiplier || 1
      return Math.floor(wechatPayAmount.value * multiplier)
    })
    const checkoutMemberSummaryText = computed(() => {
      if (wechatPayAmount.value <= 0) return ''
      const points = String(expectedOrderPoints.value)
      if (isMember.value) {
        let text = confirmationText.memberSummaryMember
          .replace('{level}', memberLevelLabel.value || '普通会员')
          .replace('{points}', points)
        if (availableCoupons.value.length > 0) {
          text += confirmationText.memberSummaryMemberCoupons
            .replace('{count}', String(availableCoupons.value.length))
        }
        return text
      }
      return confirmationText.memberSummaryGuest.replace('{points}', points)
    })
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
    const toggleItemsExpanded = () => { itemsExpanded.value = !itemsExpanded.value }
    const closeOrderConfirm = () => { if (!ordering.value && !paying.value) showCart.value = false }
    const resetPendingPayment = () => {
      if (ordering.value || paying.value) return
      pendingOrderId.value = ''
      pendingPaymentIntent.value = null
      paymentFailed.value = false
    }
    const activeCategory = ref('')
    const orderMode = ref('dineIn')
    const tableDisplayText = computed(() => (tableNo.value || orderModeText.unknownTable) + '\u684c')
    const orderModeDisplayText = computed(() => orderMode.value === 'delivery' ? orderModeText.delivery : orderModeText.dineIn)
    const scrollTarget = ref('')
    const allDishes = ref([])
    const cart = ref({}) // { dishId: qty }
    const {
      addPressKey, qtyPulseKey, cartIconPulse, cartBadgePulse, amountPulse,
      triggerAddPress, triggerCartSuccessFeedback, triggerCartValueFeedback,
    } = useCartFeedback()
    const categoryOrder = ref([])

    const {
      categories, categoryDisplayName, categoryIconClass, dishesByCategory,
      specButtonText, dishOptionKindCount, optionCountText,
    } = useDishCategories({ allDishes, categoryOrder, specCartItems, hasSpecs })

    const {
      canStartOrdering, homeStatusDesc, homeOrderButtonText, homeCouponHint,
      featuredDish, canHomeAdd, featuredDishTag, validateHistoryReorderItem,
      lastOrderItems, homeLastOrderItems,
    } = useHomeTabView({ allDishes, storeClosed, bannerInfo, myOrders, isSoldOut, dishTags, normalizeDishTag, hasSpecs })
    const cartCount = (id) => cart.value[id] || 0

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

    const {
      handleHomeStartOrder, handleFeaturedAdd, handleHomeReorderItem, handleHomeReorderAll,
      reorderItem, reorderAll,
    } = useHistoryReorder({
      activeTab, storeClosed, canStartOrdering, canHomeAdd, featuredDish,
      validateHistoryReorderItem, homeLastOrderItems, lastOrderItems,
      hasSpecs, addToCart, openSpecSheet,
    })

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
      if (!totalCount.value) return
      uni.showModal({
        title: '清空购物车',
        content: `确定要清空已选的${totalCount.value}件商品吗？`,
        confirmText: '清空',
        confirmColor: '#ff3018',
        success: (res) => {
          if (res.confirm) {
            cart.value = {}
            specCartItems.value = []
          }
        },
      })
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
    const {
      categoryScrollTop, ignoreScroll, switchCategory, handleActiveCategoryChange,
    } = useCategoryScroll({ categories, activeCategory, scrollTarget })

    const switchOrderMode = (mode) => {
      if (mode === 'delivery') {
        uni.showToast({ title: '\u5916\u5356\u914d\u9001\u6b63\u5728\u5b8c\u5584\uff0c\u5f53\u524d\u5148\u652f\u6301\u5802\u98df\u70b9\u9910', icon: 'none' })
        return
      }
      orderMode.value = mode
    }

    // 第1批：优惠券列表原来只在 openCart 里现拉，拆成独立函数——进菜单页空闲时机先拉一次
    // 打底（见 onLoad 里的调用），openCart 不用等它了；同时还是 openCart 时机也顺手调用
    // 一次刷新（不 await），保证券状态不会因为顾客在菜单页停留太久而过期不准。
    const refreshAvailableCoupons = async () => {
      if (!uni.getStorageSync('customer_token')) return
      try {
        const res = await getCustomerCoupons('UNUSED')
        const now = Date.now()
        const list = (res?.data || []).filter(c => new Date(c.expire_time || c.valid_end_time || '2099-01-01').getTime() > now)
        availableCoupons.value = list
        const keepExistingChoice = selectedCouponId.value && couponPickerList.value.some(c => c.id === selectedCouponId.value && c.eligible)
        if (!keepExistingChoice) {
          const best = couponPickerList.value.find(c => c.eligible)
          selectedCouponId.value = best ? best.id : null
        }
      } catch (e) {
        reportError('menu.refresh_coupons', e)
      }
    }

    const openCart = () => {
      // 第1批：openCart 不再 await 任何网络请求——loadShopSettings 在 onLoad 已经拉过一次，
      // 这里只是顺手刷新，不该让购物车面板等它才显示；优惠券同理，正常情况下已经被
      // onLoad 里的预拉垫过底了，这里再刷新一次只是保证不过期，不等它。
      // 第0批性能埋点：量的是"点开购物车图标"到"购物车面板真的显示出来"这一段。
      const _openCartStartedAt = Date.now()
      pendingSubmitRequestId.value = ''
      loadShopSettings().catch(() => {})
      showCart.value = true
      recordSample('cart_open', Date.now() - _openCartStartedAt)
      itemsExpanded.value = totalCount.value <= 1
      refreshAvailableCoupons()
    }

    const {
      goCheckout, cancelCheckoutAuth, handleCheckoutAuth,
      confirmPay,
      savePendingPaymentOrder, restorePendingPaymentOrder, clearPendingPaymentOrder,
      recoverPendingPaymentResult,
    } = useCheckout({
      shopId, tableNo, diningSessionId, diningParticipantToken, diningClientId,
      orderNo, orderId, orderStatus, successItems, successTotal, successDiscount,
      showCheckoutAuth, authorizing, authActionStatus, pendingPaymentIntent, paying, paymentFailed,
      payAmount, pendingOrderId, pendingSubmitRequestId,
      myOrders, showOrders, showCart, showSuccess,
      ordering, tableSessionClosed, paymentMode,
      reminderRequested, earnedCoupon, cart, specCartItems, remark, selectedCouponId,
      totalPrice, cartItems, finalPrice, wechatPayAmount, isPrepayMode, canSubmitOrder,
      wxLogin, ensureDiningSession, bindCurrentDiningParticipant, syncDiningOrders,
      normalizePaymentMode, refreshCustomerAuthState, saveMyOrders, startStatusPoll, consumeWelcomeCoupon,
    })

    const { handleTableContinueOrder, handleTableCheckout } = useTableCheckout({
      shopId, diningParticipantToken, diningClientId, tableSessionId,
      canContinueOrder, checkoutRequestedAt, checkoutRequested, isTableSettled, tableCheckouting,
      showOrders, showSuccess, activeTab,
      ensureDiningSession, persistDiningContext,
    })

    const goCoupons = () => {
      showSuccess.value = false
      uni.navigateTo({ url: '/subpkg-coupon/pages/list' })
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

    const applyShopInfoState = (d) => {
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
      }
      newCustomerCouponPreview.value = d.new_customer_coupon_preview || null
      couponReminderTemplateId.value = d.coupon_reminder_template_id || ''
      if (d.is_open === false) {
        storeClosed.value = true
        closedNotice.value = d.closed_notice || d.business_hours || ''
      } else {
        storeClosed.value = false
      }
    }

    const shopInfoCacheKey = () => 'shop_info_cache_' + (shopId.value || '')
    const readShopInfoCache = () => {
      try {
        const cached = uni.getStorageSync(shopInfoCacheKey())
        return cached && cached.data ? cached.data : null
      } catch { return null }
    }
    const writeShopInfoCache = (data) => {
      try { uni.setStorageSync(shopInfoCacheKey(), { data, cachedAt: Date.now() }) } catch (e) {
        reportError('menu.write_shop_info_cache', e)
      }
    }

    const loadShopSettings = async () => {
      if (!shopId.value) return
      const cachedData = readShopInfoCache()
      if (cachedData) applyShopInfoState(cachedData)
      try {
        const res = await getShopInfo(shopId.value)
        if (res?.code === 200 && res?.data) {
          const d = res.data
          applyShopInfoState(d)
          writeShopInfoCache(d)
          // 进店券到账提示和距离计算必须只在这次真实网络响应里触发一次——如果
          // 挪进 applyShopInfoState，缓存命中那次调用也会触发，会出现重复弹
          // toast、重复请求距离接口的问题。
          if (d.entry_coupon?.is_new) {
            uni.showToast({
              title: `已发放进店券 ¥${formatPrice(d.entry_coupon.amount)}，满${Number(d.entry_coupon.threshold || 0).toFixed(0)}元可用`,
              icon: 'none',
              duration: 3000,
            })
          }
          if (d.lat && d.lng) loadDistance(d.lat, d.lng)
        }
      } catch (e) {
        console.warn('[loadShopSettings] failed', e)
      }
    }

    // 第2批：菜单按 tenant_id 存本地缓存，带一个 version（后端用这批菜品自己的 updated_at
    // 取最大值算出来，零额外查询开销）。有缓存就先用缓存秒出首屏，跳过骨架屏，网络请求
    // 照常在后台发；version 没变就什么都不用换（不折腾已经在渲染的列表），变了才替换成
    // 新数据并顺手更新缓存。第一次进店没有缓存，行为跟以前完全一样（骨架屏等到网络回来）。
    const menuCacheKey = () => 'menu_cache_' + (shopId.value || '')
    const readMenuCache = () => {
      try {
        const cached = uni.getStorageSync(menuCacheKey())
        return cached && Array.isArray(cached.items) ? cached : null
      } catch { return null }
    }
    const writeMenuCache = (items, version) => {
      // 写缓存失败不影响这一次能不能看到菜单（数据已经从接口拿到了），但会
      // 悄悄拖慢下一次进店——缓存一直写不进去，顾客每次都要等接口，值得报一下。
      try { uni.setStorageSync(menuCacheKey(), { items, version, cachedAt: Date.now() }) } catch (e) {
        reportError('menu.write_cache', e)
      }
    }

    const loadMenu = async () => {
      const cached = readMenuCache()
      const hadCacheHit = Boolean(cached && cached.items.length)
      if (hadCacheHit) {
        allDishes.value = cached.items
        if (categories.value.length) activeCategory.value = categories.value[0]
      }
      loading.value = !hadCacheHit
      loadError.value = false
      try {
        const res = await getMenuItems(shopId.value)
        if (res?.code !== 200) {
          if (!hadCacheHit) { loadError.value = true; allDishes.value = [] }
          return
        }
        const payload = res?.data || {}
        const rawItems = Array.isArray(payload) ? payload : (payload.items || [])
        const version = Array.isArray(payload) ? '' : (payload.version || '')
        const mapped = Array.isArray(rawItems) ? rawItems.map(d => ({ ...d, desc: d.desc || d.description || '' })) : []
        if (!hadCacheHit || version !== cached.version) {
          allDishes.value = mapped
          if (categories.value.length) activeCategory.value = categories.value[0]
        }
        if (version) writeMenuCache(mapped, version)
      } catch {
        if (!hadCacheHit) { loadError.value = true; allDishes.value = [] }
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
      orderId, orderNo, orderStatus, orderStatusText, successStatusText, successStatusTone, successOrderItemCount, successOrderNo, orderStatusClass,
      startStatusPoll, stopStatusPoll, startTablePresencePoll, stopTablePresencePoll,
      remark, remarkChips, toggleRemarkChip, orderRemarkChips, showOrderRemarkExtra, orderRemarkExtra,
      orderRemarkExpanded, toggleOrderRemarkExpanded, orderRemarkSummary,
      availableCoupons, selectedCouponId, selectedCoupon, discountAmount, finalPrice,
      showCouponPicker, couponPickerList, couponPickerAmount, couponPickerCondText, openCouponPicker, closeCouponPicker, pickCoupon,
      couponBarVisible, bestCouponValue, couponBarText, couponBarPrefix, couponBarAmount, couponNudgeState, goCouponAddOn,
      openCart, refreshAvailableCoupons,
      activeCategory, scrollTarget, categoryScrollTop, allDishes, cart, addPressKey, qtyPulseKey, cartIconPulse, cartBadgePulse, amountPulse,
      successItems, successTotal,
      categories, categoryDisplayName, categoryIconClass, dishesByCategory, dishImage, dishTags, dishCardTags, isStrongDishTag, dishCardDesc, showDishSales, isSoldOut, dishPriceText, dishPriceSuffix, dishOriginalPrice, hasSpecs, formatPrice,
      imageLoadFailed, detailImageFailed, markDishImageFailed, openProductDetail,
      cartCount, addToCart, removeFromCart, increaseCartItem, clearCart, specButtonText, dishOptionKindCount, optionCountText, openSpecSheet,
      cartItems, totalCount, totalPrice, cartBadgeText,
      switchCategory, switchOrderMode,
      goCheckout, finishOrdering, closeSuccessAndWait, continueOrdering, viewOrderDetail, goCoupons, loadMenu,
      myOrders, showOrders, showAllOrders, pendingOrderCount, statusLabel, doCancelOrder,
      isTableAccountMode, isPostpayMode, isSharedBillMode, sharedBillSubLabel, tableSessionId, tableOrderGroups, tableTotal, tableItemCount, tableStatusView, isTableSettled, canContinueOrder, canCheckout, postpayReadyToSettle, stillPreparing, checkoutRequested, tableCheckouting, handleTableContinueOrder, handleTableCheckout,
      tableAccountScrollInto, scrollTableAccountToTop,
      currentTableOrder, historyTableOrders, currentTableOrderStatus, tableOrderStatusTone, tableOrderStatusIcon, tableOrderStatusBadge, tableOrderNextAction, tableOrderProgressSub, tableOrderPrimaryButtonText, tableOrderStatusTitle, tableOrderStatusHint, tableOrderTimeline, orderItemCount, currentOrderItemCount, currentOrderItems, currentOrderMainItemText,
      orderItemName, orderItemQty, orderItemAmount, orderItemSpecText, orderItemImage, orderItemImageFailed, markOrderItemImageFailed,
      saveMyOrders, loadMyOrders, refreshAllOrderStatuses, ensureDiningSession, syncDiningOrders,
      savePendingPaymentOrder, restorePendingPaymentOrder, clearPendingPaymentOrder, recoverPendingPaymentResult,
      successDiscount, wechatPayAmount, expectedOrderPoints, checkoutMemberSummaryText, canSubmitOrder, payButtonText,
      storeClosed, closedNotice, tableSessionClosed, tableSessionClosedNotice, isMember, bannerInfo, memberAuthorizing, memberLoading, isCustomerLoggedIn, hasCustomerIdentity,
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
      handleActiveCategoryChange, ignoreScroll,
      headerVisible, onDishScrollPosition,
    }
  },

  onLoad: function (options) {
    return (async () => {
      // 第1批：把"扫码到首屏可交互"这一个总耗时拆成三段，才知道 6-7 秒具体花在
      // 冷启动、等接口、还是渲染上——只有一个总数没法对症下药。scanStartedAt 在这里
      // 就读走（consumeStart 读到即删），后面 menuReady.then 里不能再读一次，
      // 所以先存进局部变量传下去。
      const onLoadStartedAt = Date.now()
      const scanStartedAt = consumeStart('scan_to_interactive')
      if (scanStartedAt) recordSample('stage_cold_start_to_onload', onLoadStartedAt - scanStartedAt)

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
      // 第0批性能埋点："扫码到首屏可交互"到这里就算数——菜单数据齐了、顾客能开始点菜了，
      // 不用等 sessionReady（本桌身份/历史订单同步）一起完成，那些不影响首屏能不能点餐。
      // 非扫码进来的场景（比如从"我的"页正常打开）consumeStart 拿不到起点，直接跳过。
      menuReady.then(() => {
        const menuReadyAt = Date.now()
        recordSample('stage_onload_to_menu_ready', menuReadyAt - onLoadStartedAt)
        if (scanStartedAt) recordSample('scan_to_interactive', menuReadyAt - scanStartedAt)
        // nextTick 之后才是"数据已经写进真实 DOM"的时机，用它来近似"渲染完成"，
        // 比 menuReady resolve 那一刻（数据到手但可能还没画出来）更贴近顾客真实感知。
        nextTick(() => {
          recordSample('stage_menu_ready_to_render', Date.now() - menuReadyAt)
        })
        // 第1批：优惠券预拉，别等顾客点开购物车才现拉。故意错开一点延迟，把带宽/CPU
        // 优先让给刚刚渲染出来的菜单，不跟首屏抢；顾客通常也要选几件商品才会点开购物车，
        // 这点延迟基本感觉不到。
        setTimeout(() => { this.refreshAvailableCoupons() }, 800)
      })

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
    flushPending()
  },
  onUnload: function () {
    this.stopStatusPoll()
    this.stopTablePresencePoll()
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

.mini-shop-bar {
  overflow: hidden;
  flex-shrink: 0;
  height: 0;
  opacity: 0;
  display: flex;
  align-items: center;
  gap: 8rpx;
  padding: 0 32rpx;
  background: var(--bg-card);
  border-bottom: 1rpx solid transparent;
  box-sizing: border-box;
  pointer-events: none;
  transition: height 0.22s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.18s ease;
}

.mini-shop-bar--visible {
  height: 72rpx;
  opacity: 1;
  border-bottom-color: #edf0f2;
  pointer-events: auto;
}

.mini-shop-bar-name {
  font-size: 28rpx;
  font-weight: 700;
  color: var(--text-1);
  max-width: 50%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-shop-bar-chip {
  margin-left: auto;
  padding: 4rpx 16rpx;
  border-radius: 8rpx;
  background: #1a1a1a;
  color: #fff;
  font-size: 22rpx;
  font-weight: 600;
  line-height: 32rpx;
  white-space: nowrap;
}

.order-coupon-wrap {
  flex-shrink: 0;
  background: var(--bg-card);
}

/* DishList 拆成独立组件后，.menu-body 的 flex:1/min-height:0 是靠"父级是 flex
   容器"才生效的——原来 .menu-body 直接是 .order-page 的 flex 子元素，现在中间
   多了一层 <dish-list> 自定义组件的宿主节点，小程序自定义组件宿主节点默认
   display:block，不参与 flex 布局，.menu-body 的尺寸链就断在这一层，分类栏和
   菜品列表都会失去可滚动的高度边界（点击分类没反应、菜品列表滚不动，就是这个
   原因）。这里让 dish-list 标签本身也变成 flex:1 的 flex 容器，把 .order-page
   分配的高度正确传下去。 */
dish-list {
  display: flex;
  flex: 1;
  min-height: 0;
  width: 100%;
}

.tab-scroll {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: calc(100rpx + env(safe-area-inset-bottom));
  padding-top: calc(176rpx + env(safe-area-inset-top));
}
</style>
