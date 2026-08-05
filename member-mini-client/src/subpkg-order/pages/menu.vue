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


    <CouponBar
      v-if="activeTab === 'order'"
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

    <DishList
      v-show="activeTab === 'order'"
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
      :can-submit-order="canSubmitOrder"
      :ordering="ordering"
      :paying="paying"
      :pay-button-text="payButtonText"
      :format-price="formatPrice"
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
import { consumeStart, recordSample } from '@/utils/perf'
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
import { orderModeText, confirmationText, successText, specText, authSheetText } from '../utils/orderText.js'
const wxLogin = () => new Promise((resolve, reject) => {
  uni.login({
    provider: 'weixin',
    success: (res) => res.code ? resolve(res.code) : reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5')),
    fail: () => reject(new Error('\u5fae\u4fe1\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u5c0f\u7a0b\u5e8f\u73af\u5883'))
  })
})

export default {
  components: { OrderBubble, MemberCard, SpecSheet, CouponPicker, HomeTab, TableBillSheet, OrderHistorySheet, PaymentSuccessSheet, CheckoutSheet, CheckoutAuthSheet, DishList, CartBar, CouponBar, WelcomeCouponSheet },
  setup() {
    const {
      formatPrice, dishImage, dishPlaceholderStyle, hasSpecs, isSoldOut, dishCardDesc,
      dishPriceBase, dishPriceText, dishPriceSuffix, dishOriginalPrice, showDishSales,
      couponAmountText, couponConditionText, couponValidityText, couponPickerAmount, couponPickerCondText,
      orderItemName, orderItemQty, orderItemAmount, orderItemSpecText, orderItemImage, orderItemCount,
      statusLabel, dishTags, strongDishTags, normalizeDishTag, isStrongDishTag, dishCardTags, isFeatured,
    } = useOrderFormatters()
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
    // 整单备注默认折叠成一行，跟"已选商品"用同一个模式（menu.vue 里 toggleItemsExpanded
    // 那一行），避免5个chip换行铺开撑高确认单、跟价格支付这些核心信息抢视觉权重。
    // 折叠态靠这句摘要保留可见性，不会出现"以为选了、其实没点开"的问题。
    const orderRemarkExpanded = ref(false)
    const toggleOrderRemarkExpanded = () => { orderRemarkExpanded.value = !orderRemarkExpanded.value }
    const orderRemarkSummary = computed(() => remark.value.trim() || confirmationText.orderRemarkEmpty)
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

    const specButtonText = (dish) => dish.option_button_text || dish.spec_button_text || (hasSpecs(dish) ? specText.chooseTaste : specText.chooseSpec)
    const dishOptionKindCount = (id) => specCartItems.value.filter(i => i.id === id).length
    const optionCountText = (id) => specText.selectedKinds + dishOptionKindCount(id) + specText.kindUnit

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
    const ignoreScroll = ref(false)

    const switchCategory = (cat) => {
      activeCategory.value = cat
      ignoreScroll.value = true
      setTimeout(() => { ignoreScroll.value = false }, 600)
      const idx = categories.value.indexOf(cat)
      syncCategoryVisible(cat)
      scrollTarget.value = ''
      nextTick(() => { scrollTarget.value = 'cat-sec-' + idx })
    }

    // 滚动时"实时查 DOM 现在滚到哪个分类锚点"这段查询逻辑现在在 DishList.vue 组件内部
    // 自己做（因为要查的 .dish-scroll/#cat-sec-N 节点现在是它自己的模板节点，必须用
    // .in(this) 绑定到组件实例才能可靠查到，不能从页面这一层隔着组件边界去查）。这里
    // 只负责接收子组件查完之后报上来的"当前应该高亮哪个分类"结论，然后跟 switchCategory
    // 点击分类时做的事一样：赋值 + 同步左侧分类栏可见区域。
    const handleActiveCategoryChange = (cat) => {
      activeCategory.value = cat
      syncCategoryVisible(cat)
    }

    const setupCategoryObserver = () => {}

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
      try { uni.setStorageSync(menuCacheKey(), { items, version, cachedAt: Date.now() }) } catch {}
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
      activeCategory, scrollTarget, categoryScrollTarget, categoryScrollTop, dishScrollTopVal, allDishes, cart, addPressKey, qtyPulseKey, cartIconPulse, cartBadgePulse, amountPulse,
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
      setupCategoryObserver, handleActiveCategoryChange, ignoreScroll,
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
      // 第0批性能埋点："扫码到首屏可交互"到这里就算数——菜单数据齐了、顾客能开始点菜了，
      // 不用等 sessionReady（本桌身份/历史订单同步）一起完成，那些不影响首屏能不能点餐。
      // 非扫码进来的场景（比如从"我的"页正常打开）consumeStart 拿不到起点，直接跳过。
      menuReady.then(() => {
        const startedAt = consumeStart('scan_to_interactive')
        if (startedAt) recordSample('scan_to_interactive', Date.now() - startedAt)
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

.cat-title {
  display: block;
  padding: 24rpx 0 16rpx;
  font-size: 24rpx;
  font-weight: 700;
  color: var(--text-3);
}
.dish-emoji-wrap, .dish-emoji, .dish-initial, .dish-badge-top { display: none; }


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
.dish-tag--strong { color: #078546; background: #e9f9f0; }
.dish-tag--plain { display: none; }
.dish-origin-price, .dish-save-badge, .member-price { display: none; }
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
@keyframes micBorderGlow { 0%, 100% { box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), 0 10rpx 24rpx rgba(0,0,0,.22), 0 0 0 1px rgba(212,175,110,.28); } 50% { box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), 0 10rpx 26rpx rgba(0,0,0,.26), 0 0 0 1px rgba(232,202,160,.6); } }
@keyframes micBadgePulse { 0%, 100% { opacity: .85; } 50% { opacity: 1; text-shadow: 0 0 12rpx rgba(232,202,160,.9); } }
.member-service-icon .iconfont { font-size: 28rpx; }
@media screen and (max-width: 340px) {
  .card-tab.member-center { padding-left: 24rpx; padding-right: 24rpx; }
  .member-identity-card { padding: 26rpx 26rpx 22rpx; }
  .mic-body { gap: 18rpx; }
  .member-level { font-size: 34rpx; }
  .member-asset-value { font-size: 34rpx; }
  .member-coupon-card { gap: 14rpx; padding: 22rpx; }
  .member-coupon-use { padding: 0 18rpx; }
}


.mask {
  position: fixed;
  inset: 0;
  z-index: 3100;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: flex-end;
}
.selected-items-toggle { color: var(--text-2); font-size: 26rpx; }

.ht-shop-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12rpx;
}
.ht-notice { display: block; font-size: 26rpx; color: rgba(255,255,255,0.85); line-height: 1.5; }

@media screen and (max-width: 340px) {
  .home-tab { padding-left: 24rpx; padding-right: 24rpx; }
  .ht-status-card, .ht-order-card { padding: 30rpx; }
  .ht-feature-card { gap: 18rpx; padding: 20rpx; }
  .ht-feature-img-wrap { width: 176rpx; height: 176rpx; }
  .ht-feature-add { padding: 0 22rpx; }
  .ht-feature-add text { font-size: 24rpx; }
  .ht-last-name { max-width: 184rpx; }
}


.success-header {
  padding: 48rpx 40rpx 32rpx;
  text-align: center;
  border-bottom: 2rpx solid #f1f5f9;
}
.success-subtitle {
  display: block;
  font-size: 26rpx;
  color: var(--text-3);
  margin-bottom: 4rpx;
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

.success-btn-settle {
  background: linear-gradient(135deg, var(--brand), var(--brand-dark));
  box-shadow: 0 8rpx 24rpx rgba(7,193,96,0.35);
  text { font-size: 36rpx; }
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

.order-progress-step.done .order-progress-title,
.order-progress-step.active .order-progress-title {
  color: var(--text-1);
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


.member-price {
  font-size: 24rpx;
  color: var(--brand);
  font-weight: 600;
  margin-left: 8rpx;
}

@keyframes slide-up {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}

.item-remark-extra-toggle {
  display: inline-block;
  margin-top: 20rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 36rpx;
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

.closed-btn-plain {
  margin-top: 16rpx;
  background: #f3f4f6;
  text { color: var(--text-3); font-weight: 600; }
}
@keyframes authSheetIn { from { transform: translateY(24rpx); opacity: .92; } to { transform: translateY(0); opacity: 1; } }

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

.counter-num--pulse {
  animation: cartQtyPulse 150ms ease-out;
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

.table-account-group-status--served {
  color: var(--brand);
}

.table-account-group-status--settled {
  color: var(--text-3);
}

.table-account-group-status--muted {
  color: #9aa1aa;
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

.success-sheet .order-status-bar.warning .order-status-text {
  color: #9a6a21;
}

@keyframes ec-card-in {
  0% { transform: scale(0.85); opacity: 0; }
  60% { transform: scale(1.03); opacity: 1; }
  100% { transform: scale(1); }
}

@keyframes ec-shine {
  to { transform: translateX(140%); }
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



















































































