<template>
  <div class="page-wrap">
    <!-- 页面顶部 -->
    <div class="page-header">
      <div>
        <span class="page-title">接单管理</span>
        <div v-if="lastRefreshed" style="font-size:11px;color:var(--text-3);margin-top:1px">{{ lastRefreshed }} 更新</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <a-button v-if="canStaffOrder" size="small" type="primary" @click="openStaffOrder()" style="font-size:12px;height:28px;padding:0 10px">
          代客加单
        </a-button>
        <div v-if="alertEnabled" class="alert-on-badge tap-shrink" @click="disableAlert">
          <span class="live-dot" />提醒开
        </div>
        <a-button v-else size="small" type="primary" ghost @click="enableAlert" style="font-size:12px;height:28px;padding:0 10px">
          开启提醒
        </a-button>
        <a-button type="text" aria-label="刷新" @click="manualRefresh" :loading="loading">
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>

    <!-- 提醒已开启但浏览器把声音挂起了——不点这里，新订单来了也听不到 -->
    <div v-if="audioNeedsUnlock" class="unlock-audio-banner tap-shrink" @click="unlockAudio">
      <span class="live-dot" />提醒还没生效，点这里立即解锁
    </div>

    <div
      v-if="isLiveToday && pendingPickupCount > 0"
      class="pickup-todo-banner tap-shrink"
      @click="focusFirstPendingPickup"
    >
      <span class="pickup-todo-dot" />
      <div>
        <div class="pickup-todo-title">{{ pendingPickupCount }}笔订单待发桌牌</div>
        <div class="pickup-todo-sub">顾客已付款</div>
      </div>
    </div>

    <!-- 统计数字 -->
    <div class="section-block animate-in">
      <a-card :bordered="false" :body-style="{ padding: '12px 0' }">
        <a-row>
          <a-col :span="6" v-for="s in statItems" :key="s.label" style="text-align:center;padding:4px 0">
            <div :style="{ fontSize: '22px', fontWeight: 900, color: s.color }">{{ s.value }}</div>
            <div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ s.label }}</div>
          </a-col>
        </a-row>
      </a-card>
    </div>

    <a-tabs v-model:activeKey="orderCenterMode" class="animate-in" style="padding:0 16px;margin-top:8px;animation-delay:.04s" :tab-bar-style="{ marginBottom: 0 }">
      <a-tab-pane key="live" tab="当前订单" />
      <a-tab-pane key="history" tab="历史订单" />
    </a-tabs>

    <!-- 视图切换 -->
    <a-tabs v-if="isLiveToday" v-model:activeKey="view" class="animate-in" style="padding:0 16px;margin-top:0" :tab-bar-style="{ marginBottom: 0 }">
      <a-tab-pane key="table" tab="桌台视图" />
      <a-tab-pane key="list" tab="订单列表" />
    </a-tabs>

    <!-- 没有会话的历史订单不再出现在桌台视图，给一个极轻的入口去订单列表看，不做成大 banner -->
    <div v-if="view === 'table' && hasSessionlessActiveOrders" style="padding:6px 16px 0;font-size:12px;color:var(--text-3)">
      有历史订单未关联桌台会话，<a @click="view = 'list'">请在订单列表查看</a>
    </div>

    <!-- 网络警告 -->
    <div v-if="pollFailCount >= 3" class="section-block" style="padding-top:8px">
      <a-alert type="warning" show-icon message="网络连接异常，数据可能不是最新的" style="border-radius:10px">
        <template #action>
          <a-button size="small" @click="manualRefresh">重试</a-button>
        </template>
      </a-alert>
    </div>

    <!-- 骨架屏 -->
    <div v-if="loading && orders.length === 0" class="section-block">
      <a-skeleton active :paragraph="{ rows: 4 }" style="background:var(--bg-card);border-radius:12px;padding:16px;margin-bottom:12px" />
      <a-skeleton active :paragraph="{ rows: 3 }" style="background:var(--bg-card);border-radius:12px;padding:16px" />
    </div>

    <!-- 空状态 -->
    <div v-else-if="!loading && orders.length === 0" style="padding:48px 0">
      <a-empty description="今天还没有订单，去桌码页面打印桌贴码，贴到桌上后顾客即可扫码点餐">
        <template #image><OrderedListOutlined style="font-size:60px;color:#d1d5db" /></template>
      </a-empty>
    </div>

    <!-- 桌台视图：宫格，一眼看清有几桌、分别什么状态 -->
    <template v-if="view === 'table'">
      <div v-if="!loading && visibleTableGroups.length === 0 && orders.length > 0" style="padding:48px 0">
        <a-empty description="今天的桌子都已结账，坐等下一波客人吧">
          <template #image><CheckCircleOutlined style="font-size:60px;color:#bbf7d0" /></template>
        </a-empty>
      </div>
      <div v-else class="table-grid section-block">
        <div
          v-for="table in visibleTableGroups"
          :key="table.groupKey"
          class="table-tile"
          :class="[`table-tile--${tableTagClass(table)}`, { 'table-tile--urgent': table.canSettle && table.checkoutRequestedAt }]"
          @click="openTableDetail(table)"
        >
          <div class="table-tile-top">
            <span class="table-tile-no">桌{{ table.tableNo }}</span>
            <span v-if="table.pendingPaymentOrders.length" class="table-tile-warn" title="有订单待支付">!</span>
          </div>
          <div class="table-tile-state">{{ tableStatusText(table) || '已结账' }}</div>
          <div class="table-tile-total">¥{{ table.total.toFixed(2) }}</div>
          <div class="table-tile-count">{{ table.orders.length }} 单<template v-if="table.pickupNo"> · {{ table.pickupNo }}号桌牌</template></div>
        </div>
      </div>

      <!-- 桌台详情：点宫格进来看这一桌具体点了什么、能做什么操作 -->
      <a-drawer
        v-model:open="showTableDetail"
        :title="selectedTable ? `桌${selectedTable.tableNo}` : ''"
        placement="bottom"
        height="88%"
        :body-style="{ padding: 0 }"
      >
        <div v-if="selectedTable">
          <div class="table-head">
            <div style="display:flex;align-items:center;gap:8px">
              <a-tag :class="`tag-${tableTagClass(selectedTable)}`" style="font-size:13px;padding:2px 8px">桌{{ selectedTable.tableNo }}</a-tag>
              <span class="table-state" :class="{ 'table-state--urgent': selectedTable.canSettle && selectedTable.checkoutRequestedAt }">{{ tableStatusText(selectedTable) }}</span>
            </div>
            <span class="table-total">¥{{ selectedTable.total.toFixed(2) }}</span>
          </div>

          <!-- 桌牌：一桌一次，加单共享；拿实体牌后再点号 -->
          <div
            v-if="selectedTable.pickupNo || selectedTablePickupOrder"
            style="padding:10px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:10px"
          >
            <div v-if="selectedTable.pickupNo" class="pickup-bound-row">
              <span class="pickup-bound-tag">{{ selectedTable.pickupNo }}号桌牌</span>
              <button
                v-if="selectedTablePickupOrder && orderCanReplacePickup(selectedTablePickupOrder)"
                type="button"
                class="pickup-replace-link"
                @click="openPickupSheet(selectedTablePickupOrder)"
              >更换</button>
            </div>
            <div v-else-if="selectedTablePickupOrder && orderNeedsPickup(selectedTablePickupOrder)" class="pickup-pending-row">
              <span class="pickup-pending-hint"><span class="pickup-todo-dot" />待发桌牌</span>
              <a-button type="primary" size="small" @click="openPickupSheet(selectedTablePickupOrder)">发桌牌</a-button>
            </div>
          </div>

          <!-- 订单列表 -->
          <div v-for="order in selectedTable.orders" :key="order.id" class="order-row">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
              <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <span v-if="order.participantNo" class="participant-badge" :style="{ background: participantColor(order.participantNo) }">{{ order.participantNo }}</span>
                <a-tag :class="`tag-${order.status}`" size="small">{{ statusLabel(order.status, order.status_text) }}</a-tag>
                <a-tag v-if="order.source === 'h5'" size="small" style="background:#eff6ff;color:#2563eb;border-color:#bfdbfe;font-size:10px">H5</a-tag>
                <a-tag v-if="order.source === 'staff'" size="small" style="background:#fdf4ff;color:#a21caf;border-color:#f5d0fe;font-size:10px">{{ staffSourceLabel(order) }}</a-tag>
                <a-tag v-if="order.pickup_no" size="small" style="background:#fff7ed;color:#c2410c;border-color:#fed7aa;font-size:10px">{{ order.pickup_no }}号桌牌</a-tag>
                <span v-else-if="orderNeedsPickup(order)" class="pickup-pending-hint"><span class="pickup-todo-dot" />待发桌牌</span>
                <a-tag v-if="order.printStatus === 'failed'" size="small" style="background:#fef2f2;color:#dc2626;border-color:#fecaca;font-size:10px">打印失败</a-tag>
                <a-tag v-else-if="order.printStatus === 'unknown'" size="small" style="background:#fffbeb;color:#b45309;border-color:#fde68a;font-size:10px">打印结果未知</a-tag>
                <a-tag v-if="order.refundRequired" color="error">需要退款处理</a-tag>
                <span style="font-size:12px;color:var(--text-3)">{{ order.time }}</span>
              </div>
              <div style="text-align:right">
                <div style="font-size:18px;font-weight:800;color:var(--text-1)">¥{{ Number(order.total).toFixed(2) }}</div>
                <div v-if="order.discount_amount" style="font-size:11px;color:#ef4444;margin-top:2px">优惠 -¥{{ Number(order.discount_amount).toFixed(2) }}</div>
              </div>
            </div>
            <div v-if="order.paymentMethodText" style="font-size:11px;color:var(--text-3);margin-bottom:6px">{{ order.paymentMethodText }}</div>
            <div v-if="order.refundRequired" class="refund-attention">该订单已付款但已终止，需要处理退款。请点击下方退款，由系统向支付渠道发起退款。</div>
            <div v-if="['failed','unknown'].includes(order.printStatus)" class="print-diagnostic">
              {{ printDiagnostic(order) }}
            </div>
            <div class="order-items">
              <div v-for="(item, idx) in order.items" :key="idx" class="order-item-row">
                <span class="order-item-name">{{ item.name }}</span>
                <span class="order-item-qty">×{{ item.qty }}</span>
              </div>
            </div>
            <div v-if="order.remark" class="order-remark">
              <EditOutlined style="font-size:16px;margin-top:1px;flex-shrink:0" />
              <span>{{ order.remark }}</span>
            </div>
            <div v-if="order.staffNote" class="order-remark" style="color:#a21caf;background:#fdf4ff">
              <EditOutlined style="font-size:16px;margin-top:1px;flex-shrink:0" />
              <span>代点备注：{{ order.staffNote }}</span>
            </div>
            <div class="order-action-row">
              <a-button v-if="order.status === 'pending'" type="primary" :loading="order.updating" @click="acceptOrder(order)" class="order-action-btn">接单</a-button>
              <a-button v-if="order.canReject" danger :loading="order.updating" @click="rejectOrder(order)" class="order-action-btn order-action-btn--reject">拒单</a-button>
              <span v-else-if="order.status === 'pending' && order.paymentStatus === 'paid'" class="paid-cancel-sop">已付款订单不可直接取消</span>
              <a-button v-if="order.status === 'preparing'" :loading="order.updating" @click="finishOrder(order)" class="order-action-btn order-action-btn--finish">出餐完成</a-button>
              <a-tag v-if="orderNeedsServe(order)" size="small" style="background:#ecfdf5;color:#047857;border-color:#a7f3d0;font-size:10px">待上菜</a-tag>
              <a-button v-if="orderNeedsServe(order)" type="primary" :loading="order.updating" @click="confirmServed(order)" class="order-action-btn">确认已上菜</a-button>
              <a-button v-if="['failed','unknown'].includes(order.printStatus)" danger :loading="order.reprinting" @click="reprintOrderTicket(order)" class="order-action-btn order-action-btn--reject">补打小票</a-button>
              <a-button v-if="order.refundRequired" danger :loading="order.refunding" @click="refundPaidOrderClick(order)" class="order-action-btn order-action-btn--reject">退款</a-button>
            </div>
            <div v-if="reviewsMap[order.id]" class="review-row">
              <span class="review-stars-display">{{ '★'.repeat(reviewsMap[order.id].rating) }}{{ '☆'.repeat(5 - reviewsMap[order.id].rating) }}</span>
              <span class="review-content-text">{{ reviewsMap[order.id].content || '顾客未评价' }}</span>
            </div>
          </div>

          <!-- 待支付订单：还没收到钱，但会挡住这桌结账，商家可以在这里直接取消 -->
          <div v-for="order in selectedTable.pendingPaymentOrders" :key="order.id" class="order-row order-row--pending-payment">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
              <div style="display:flex;align-items:center;gap:6px">
                <a-tag class="tag-pending_payment" size="small">待支付</a-tag>
                <span style="font-size:12px;color:var(--text-3)">{{ order.time }}</span>
              </div>
              <div style="font-size:18px;font-weight:800;color:var(--text-1)">¥{{ Number(order.total).toFixed(2) }}</div>
            </div>
            <div class="order-items">
              <div v-for="(item, idx) in order.items" :key="idx" class="order-item-row">
                <span class="order-item-name">{{ item.name }}</span>
                <span class="order-item-qty">×{{ item.qty }}</span>
              </div>
            </div>
            <div style="font-size:13px;color:#92400e;background:#fffbeb;padding:8px 10px;border-radius:8px;margin-bottom:8px;line-height:1.5">
              顾客还没完成支付，这单会挡住本桌结账。确认顾客不会再付款的话，可以取消这单。
            </div>
            <div class="order-action-row">
              <a-button v-if="order.canCancel" danger :loading="order.updating" @click="cancelPendingPaymentOrder(order)" class="order-action-btn order-action-btn--reject">取消订单</a-button>
            </div>
          </div>

          <!-- 桌台操作 -->
          <div v-if="canStaffOrder && !selectedTable.isSettled" class="table-actions">
            <a-button :loading="selectedTable.updating" @click="openStaffOrder(selectedTable.tableNo, selectedTable.groupKey)" class="order-action-btn">
              + 代客加单
            </a-button>
          </div>
          <div v-if="selectedTable.pendingOrders.length || selectedTable.preparingOrders.length || selectedTable.canSettle" class="table-actions">
            <a-button v-if="selectedTable.pendingOrders.length" type="primary" :loading="selectedTable.updating" @click="acceptTableOrders(selectedTable)" class="order-action-btn">
              全部接单 · {{ selectedTable.pendingOrders.length }} 单
            </a-button>
            <a-button v-if="selectedTable.preparingOrders.length" :loading="selectedTable.updating" @click="finishTableOrders(selectedTable)" class="order-action-btn order-action-btn--finish">
              全部出餐
            </a-button>
            <a-button v-if="selectedTable.canSettle" type="primary" :loading="selectedTable.updating" @click="settleTableClick(selectedTable)" class="order-action-btn order-action-btn--settle">
              {{ selectedTable.checkoutRequestedAt ? '顾客催结账 · ' : '' }}结账 ¥{{ selectedTable.total.toFixed(2) }}
            </a-button>
          </div>
          <div v-if="selectedTable.isSettled" style="display:flex;align-items:center;gap:4px;padding:8px 16px;color:#16a34a;font-size:13px;font-weight:600">
            <CheckCircleOutlined />已结账
          </div>
        </div>
      </a-drawer>
    </template>

    <!-- 列表视图 -->
    <template v-else>
      <!-- 待支付订单不计入桌台账，"全部"筛选下不显示，但钱还没收到是商家最需要关注的
           信息（桌台视图有角标提醒），这里补一条同等力度的提示，避免只用列表视图的
           店员完全看不到这类订单。 -->
      <div v-if="isLiveToday && statusFilter !== 'pending_payment' && pendingPaymentCount > 0" style="padding:8px 16px 0">
        <div class="pending-payment-banner tap-shrink" @click="statusFilter = 'pending_payment'">
          <span>{{ pendingPaymentCount }} 笔订单待支付，点击查看</span>
        </div>
      </div>
      <div v-if="isLiveToday" style="padding:8px 16px 0">
        <a-input
          v-model:value="searchQuery"
          placeholder="按桌号 / 订单尾号 / 菜品名搜索（顾客反馈问题时用这个快速定位）"
          allow-clear
          size="large"
        />
      </div>
      <div v-else style="padding:8px 16px 0">
        <a-input
          v-model:value="historyQuery"
          placeholder="按桌号或订单尾号查询（回车请求服务器）"
          allow-clear
          size="large"
          @pressEnter="loadHistoricalOrders({ append: false })"
        />
      </div>
      <div v-if="!isLiveToday" style="padding:8px 16px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span
          class="filter-chip"
          :class="historyDateKey === todayDateInput ? 'filter-chip--active' : ''"
          @click="setHistoryDate(todayDateInput)"
        >今天</span>
        <span
          class="filter-chip"
          :class="historyDateKey === 'yesterday' ? 'filter-chip--active' : ''"
          @click="setHistoryDate('yesterday')"
        >昨天</span>
        <input
          v-model="customDate"
          type="date"
          class="order-date-input"
          :max="todayDateInput"
          @change="onCustomDate"
        />
      </div>
      <div v-if="isLiveToday" style="padding:8px 16px 0;display:flex;gap:8px;flex-wrap:wrap">
        <span
          v-for="f in statusFilters"
          :key="f.val"
          class="filter-chip"
          :class="statusFilter === f.val ? 'filter-chip--active' : ''"
          @click="statusFilter = f.val"
        >{{ f.label }}</span>
      </div>
      <div v-if="sourceOrders.length > 0 && sortedOrders.length === 0" style="padding:32px 16px;text-align:center;color:var(--text-3);font-size:13px">
        <template v-if="searchQuery.trim()">没找到匹配"{{ searchQuery.trim() }}"的订单，换个桌号/尾号/菜名试试</template>
        <template v-else-if="statusFilter">{{ isLiveToday ? '今天' : '这一天' }}没有{{ statusFilters.find(f => f.val === statusFilter)?.label }}的订单</template>
        <template v-else-if="isLiveToday">今天的订单都还没到账，去"待支付"筛选看看</template>
        <template v-else>这一天没有订单</template>
      </div>
      <div v-else-if="!loading && !historicalLoading && sourceOrders.length === 0 && isLiveToday === false" style="padding:32px 16px;text-align:center;color:var(--text-3);font-size:13px">
        这一天没有订单
      </div>
      <div
        v-for="order in visibleOrders"
        :key="order.id"
        :data-order-card="order.id"
        :data-needs-pickup="orderNeedsPickup(order) ? '1' : '0'"
        style="padding:8px 16px 0"
      >
        <a-card :bordered="false" :body-style="{ padding: '12px 16px' }">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <a-tag style="color:#374151;background:#f3f4f6;border-color:#e5e7eb">桌{{ order.table }}</a-tag>
              <span v-if="order.participantNo" class="participant-badge" :style="{ background: participantColor(order.participantNo) }">{{ order.participantNo }}</span>
              <a-tag :class="`tag-${order.status}`">{{ statusLabel(order.status, order.status_text) }}</a-tag>
              <a-tag v-if="order.source === 'staff'" size="small" style="background:#fdf4ff;color:#a21caf;border-color:#f5d0fe;font-size:10px">{{ staffSourceLabel(order) }}</a-tag>
              <a-tag v-if="order.pickup_no" size="small" style="background:#fff7ed;color:#c2410c;border-color:#fed7aa;font-size:10px">{{ order.pickup_no }}号桌牌</a-tag>
              <span v-else-if="orderNeedsPickup(order)" class="pickup-pending-hint"><span class="pickup-todo-dot" />待发桌牌</span>
              <a-tag v-if="order.printStatus === 'failed'" size="small" style="background:#fef2f2;color:#dc2626;border-color:#fecaca;font-size:10px">打印失败</a-tag>
              <a-tag v-else-if="order.printStatus === 'unknown'" size="small" style="background:#fffbeb;color:#b45309;border-color:#fde68a;font-size:10px">打印结果未知</a-tag>
              <a-tag v-if="order.refundRequired" color="error">需要退款处理</a-tag>
              <span style="font-size:12px;color:var(--text-3)">{{ order.time }}</span>
            </div>
            <div style="text-align:right">
              <div style="font-size:18px;font-weight:800;color:var(--text-1)">¥{{ Number(order.total).toFixed(2) }}</div>
              <div v-if="order.discount_amount" style="font-size:11px;color:#ef4444;margin-top:2px">优惠 -¥{{ Number(order.discount_amount).toFixed(2) }}</div>
            </div>
          </div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:6px">单号尾号 {{ orderTail(order) }}<template v-if="order.paymentMethodText"> · {{ order.paymentMethodText }}</template></div>
          <div v-if="order.refundRequired" class="refund-attention">该订单已付款但已终止，需要处理退款。请点击下方退款，由系统向支付渠道发起退款。</div>
          <div v-if="['failed','unknown'].includes(order.printStatus)" class="print-diagnostic">
            {{ printDiagnostic(order) }}
          </div>
          <div class="order-items">
            <div v-for="(item, idx) in order.items" :key="idx" class="order-item-row">
              <span class="order-item-name">{{ item.name }}</span>
              <span class="order-item-qty">×{{ item.qty }}</span>
            </div>
          </div>
          <div v-if="order.remark" class="order-remark">
            <EditOutlined style="font-size:16px;margin-top:1px;flex-shrink:0" /><span>{{ order.remark }}</span>
          </div>
          <div v-if="order.staffNote" class="order-remark" style="color:#a21caf;background:#fdf4ff">
            <EditOutlined style="font-size:16px;margin-top:1px;flex-shrink:0" /><span>代点备注：{{ order.staffNote }}</span>
          </div>
          <div class="order-action-row">
            <a-button
              v-if="orderNeedsPickup(order)"
              type="primary"
              class="order-action-btn"
              @click="openPickupSheet(order)"
            >发桌牌</a-button>
            <a-button v-if="order.status === 'pending'" type="primary" :loading="order.updating" @click="acceptOrder(order)" class="order-action-btn">接单</a-button>
            <a-button v-if="order.canReject" danger :loading="order.updating" @click="rejectOrder(order)" class="order-action-btn order-action-btn--reject">拒单</a-button>
            <span v-else-if="order.status === 'pending' && order.paymentStatus === 'paid'" class="paid-cancel-sop">已付款订单不可直接取消</span>
            <a-button v-if="order.status === 'preparing'" :loading="order.updating" @click="finishOrder(order)" class="order-action-btn order-action-btn--finish">出餐完成</a-button>
            <a-tag v-if="orderNeedsServe(order)" size="small" style="background:#ecfdf5;color:#047857;border-color:#a7f3d0;font-size:10px">待上菜</a-tag>
            <a-button v-if="orderNeedsServe(order)" type="primary" :loading="order.updating" @click="confirmServed(order)" class="order-action-btn">确认已上菜</a-button>
            <a-button v-if="order.canCancel" danger :loading="order.updating" @click="cancelPendingPaymentOrder(order)" class="order-action-btn order-action-btn--reject">取消订单</a-button>
            <a-button v-if="['failed','unknown'].includes(order.printStatus)" danger :loading="order.reprinting" @click="reprintOrderTicket(order)" class="order-action-btn order-action-btn--reject">补打小票</a-button>
            <a-button v-if="order.refundRequired" danger :loading="order.refunding" @click="refundPaidOrderClick(order)" class="order-action-btn order-action-btn--reject">退款</a-button>
            <button
              v-if="orderCanReplacePickup(order)"
              type="button"
              class="pickup-replace-link"
              @click="openPickupSheet(order)"
            >更换</button>
          </div>
          <div v-if="reviewsMap[order.id]" class="review-row">
            <span class="review-stars-display">{{ '★'.repeat(reviewsMap[order.id].rating) }}{{ '☆'.repeat(5 - reviewsMap[order.id].rating) }}</span>
            <span class="review-content-text">{{ reviewsMap[order.id].content || '顾客未评价' }}</span>
          </div>
        </a-card>
      </div>
      <div v-if="isLiveToday && sortedOrders.length > visibleOrders.length" style="padding:8px 16px 0;text-align:center">
        <a-button block @click="listVisibleCount += LIST_PAGE_SIZE">
          加载更多（还有 {{ sortedOrders.length - visibleOrders.length }} 单）
        </a-button>
      </div>
      <div v-else-if="!isLiveToday && historicalOrders.length < historicalTotal" style="padding:8px 16px 0;text-align:center">
        <a-button block :loading="historicalLoading" @click="loadHistoricalOrders({ append: true })">
          加载更多（还有 {{ historicalTotal - historicalOrders.length }} 单）
        </a-button>
      </div>
      <div style="height:16px" />
    </template>

    <!-- 结账确认 Modal -->
    <a-modal
      v-model:open="showSettleDialog"
      title="确认结账"
      :footer="null"
      centered
    >
      <div v-if="settlingTable" style="text-align:center;padding:8px 0 16px">
        <div style="font-size:32px;font-weight:900;color:var(--text-1);margin:8px 0">
          ¥{{ settlingTable.total.toFixed(2) }}
        </div>
        <div style="color:#6b7280;font-size:13px;margin-bottom:16px">桌号 {{ settlingTable.tableNo }} · {{ settlingTable.orders.length }} 单合计</div>
        <a-list :data-source="settlingTable.orders" size="small" :split="true" style="text-align:left;margin-bottom:16px">
          <template #renderItem="{ item }">
            <a-list-item>
              <span style="font-size:13px">{{ item.items.map(i => i.name + '×' + i.qty).join(' ') }}</span>
              <template #actions>
                <span style="color:#07C160;font-weight:600">¥{{ Number(item.total).toFixed(2) }}</span>
              </template>
            </a-list-item>
          </template>
        </a-list>
        <a-button type="primary" block size="large" :loading="settling" @click="confirmSettle" style="background:#16a34a;border-color:#16a34a">
          确认收款
        </a-button>
        <a-button block style="margin-top:8px" @click="showSettleDialog = false">取消</a-button>
      </div>
    </a-modal>

    <!-- 账单 Modal（结账成功后显示）-->
    <a-modal
      v-model:open="showReceiptDialog"
      title="结账账单"
      :footer="null"
      centered
    >
      <div v-if="receiptData" style="padding:4px 0 16px">
        <div style="text-align:center;margin-bottom:16px">
          <div style="font-size:13px;color:#6b7280">桌号 {{ receiptData.tableNo }} · {{ receiptData.settledAt }}</div>
          <div style="font-size:36px;font-weight:900;color:#16a34a;margin:8px 0">¥{{ receiptData.total }}</div>
          <div style="font-size:13px;color:#6b7280">实收金额</div>
        </div>
        <div style="border-top:1px dashed #e5e7eb;margin-bottom:12px" />
        <div v-for="order in receiptData.orders" :key="order.id" style="margin-bottom:10px">
          <div v-for="item in order.items" :key="item.name + item.qty" style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
            <span style="color:#374151">{{ item.name }} × {{ item.qty }}</span>
            <span style="color:#374151;font-weight:600">¥{{ (item.price * item.qty).toFixed(2) }}</span>
          </div>
          <div v-if="order.discount_amount" style="display:flex;justify-content:space-between;font-size:12px;color:#ef4444">
            <span>优惠券抵扣</span>
            <span>-¥{{ Number(order.discount_amount).toFixed(2) }}</span>
          </div>
        </div>
        <div style="border-top:1px dashed #e5e7eb;margin:12px 0 10px" />
        <div style="display:flex;justify-content:space-between;font-size:15px;font-weight:700">
          <span>合计</span>
          <span style="color:#16a34a">¥{{ receiptData.total }}</span>
        </div>
        <a-button block style="margin-top:16px" @click="showReceiptDialog = false">关闭</a-button>
      </div>
    </a-modal>

    <!-- 代客加单：顾客直接从前台拿了东西、或喊一嘴要加菜，服务员在这里帮忙下单，
         这一单会跟顾客自己点的单一起挂在同一桌台账下，一起结账。 -->
    <a-drawer
      v-model:open="staffOrderVisible"
      title="代客加单"
      placement="bottom"
      height="88%"
      :body-style="{ padding: 0 }"
    >
      <div style="padding:12px 16px;border-bottom:1px solid var(--border)">
        <div style="font-size:13px;color:var(--text-2);margin-bottom:6px">选择桌台</div>
        <div v-if="visibleTableGroups.length === 0" style="padding:16px 0;text-align:center;color:var(--text-3);font-size:13px">
          暂无正在进行中的桌台，等顾客扫码点第一单后再来加单
        </div>
        <div v-else class="staff-table-picker">
          <div
            v-for="table in visibleTableGroups"
            :key="table.groupKey"
            class="table-tile"
            :class="[`table-tile--${tableTagClass(table)}`, { 'table-tile--selected': staffOrderSelectedKey === table.groupKey }]"
            @click="staffOrderTable = table.tableNo; staffOrderSelectedKey = table.groupKey"
          >
            <div class="table-tile-top">
              <span class="table-tile-no">桌{{ table.tableNo }}</span>
            </div>
            <div class="table-tile-state">{{ tableStatusText(table) || '已结账' }}</div>
            <div class="table-tile-total">¥{{ table.total.toFixed(2) }}</div>
          </div>
        </div>

        <template v-if="staffAvailableNewTables.length">
          <div style="font-size:12px;color:var(--text-3);margin:14px 0 6px">新开一桌（还没人点单的桌）</div>
          <div class="staff-new-table-chips">
            <button
              v-for="item in staffAvailableNewTables"
              :key="item.id"
              type="button"
              class="staff-new-table-chip tap-shrink"
              :class="{ 'staff-new-table-chip--selected': staffOrderSelectedKey === 'new:' + item.table_no }"
              @click="staffOrderTable = item.table_no; staffOrderSelectedKey = 'new:' + item.table_no"
            >桌{{ item.table_no }}</button>
          </div>
        </template>
      </div>
      <div style="padding:8px 16px;max-height:calc(100% - 260px);overflow-y:auto">
        <div v-if="staffMenuLoading" style="padding:24px 0;text-align:center;color:var(--text-3)">菜单加载中…</div>
        <template v-else>
          <div v-for="cat in staffMenuCategories" :key="cat" style="margin-bottom:4px">
            <p style="font-size:13px;font-weight:700;color:var(--text-2);margin:10px 0 4px">{{ cat }}</p>
            <div v-for="dish in staffMenuByCategory(cat)" :key="dish.id" style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <div style="flex:1;min-width:0">
                <div style="font-size:14px;font-weight:600;color:var(--text-1)">{{ dish.name }}</div>
                <div style="font-size:13px;color:#07C160;font-weight:700;margin-top:2px">¥{{ dish.price }}</div>
              </div>
              <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
                <a-button v-if="staffCart[dish.id]" shape="circle" size="small" @click="staffCartRemove(dish)">-</a-button>
                <span v-if="staffCart[dish.id]" style="min-width:16px;text-align:center;font-weight:700">{{ staffCart[dish.id] }}</span>
                <a-button shape="circle" size="small" type="primary" @click="staffCartAdd(dish)">+</a-button>
              </div>
            </div>
          </div>
          <div v-if="staffMenuItems.length === 0" style="padding:24px 0;text-align:center;color:var(--text-3)">还没有上架菜品</div>
        </template>
      </div>
      <div style="position:absolute;left:0;right:0;bottom:0;background:var(--bg-card);border-top:1px solid var(--border);padding:10px 16px 16px">
        <div v-if="pickupNoEnabled" class="pickup-bound-row" style="margin-bottom:10px">
          <span v-if="staffPickupNo" class="pickup-bound-tag">{{ staffPickupNo }}号桌牌</span>
          <a-button size="small" @click="openStaffPickupSheet">{{ staffPickupNo ? '更换' : '发桌牌（可选）' }}</a-button>
        </div>
        <a-input v-model:value="staffNote" placeholder="可选：备注是谁加的（如：前台-老王）" maxlength="64" style="margin-bottom:10px" />
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <span style="font-size:13px;color:var(--text-2)">共 {{ staffCartCount }} 件</span>
          <span style="font-size:20px;font-weight:900;color:var(--text-1)">¥{{ staffCartTotal.toFixed(2) }}</span>
        </div>
        <a-button type="primary" block size="large" :loading="staffSubmitting" :disabled="!staffOrderTable.trim() || staffCartCount === 0" @click="submitStaffOrder">
          提交这一单
        </a-button>
      </div>
    </a-drawer>

    <PickupNoPicker
      v-model:open="pickupSheetOpen"
      :count="pickupCount"
      :occupied="pickupOccupied"
      :current="pickupSheetCurrent"
      :dining-session-id="pickupSheetSessionId"
      :loading="pickupSheetLoading"
      :submitting="pickupSheetSubmitting"
      @select="handlePickupSelect"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ReloadOutlined, OrderedListOutlined, EditOutlined, CheckCircleOutlined } from '@ant-design/icons-vue'
import { getOrders, getOrdersWithCursor, getOwnerOrderChanges, updateOrderStatus, serveOrder, updateOrderPickupNo, getPickupNoStatus, reprintOrder, refundPaidOrder, settleTable, getReviews, getTenantProfile, getMenuItems, createOrder, getEntranceCodes } from '../api'
import { useWorkbenchSync } from '../composables/useWorkbenchSync'
import { ownerActionableIdsFromOrders } from '../composables/workbenchSyncCore'
import PickupNoPicker from '../components/PickupNoPicker.vue'
import { canReplacePickup, needsPickup, pickupConflictToast } from '../utils/pickupNoUi'
import { sortMerchantOrders } from '../utils/orderListSort'
import { formatOrderStatusText } from '../utils/orderStatusText'

function decodeJwtPayload(token) {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    return JSON.parse(window.atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
  } catch {
    return null
  }
}
function getCurrentTenantId() {
  const tokenPayload = decodeJwtPayload(localStorage.getItem('token') || '')
  return String(tokenPayload?.tenant_id || localStorage.getItem('tenant_id') || '')
}

const route = useRoute()
const reviewsMap = ref({}) // order_id -> review
// 默认打开"订单列表"而不是"桌台视图"——按桌视图要点开桌子详情抽屉才能看到接单/出餐
// 按钮，多了一步；订单列表按钮直接在卡片上。桌台视图还在，需要看整桌汇总时手动切过去。
// 唯一例外：从首页"有 N 桌待结账"带 ?view=table 进来时，意图已经很明确是去结账，
// 直接打开桌台视图，不强迫商家进来再手动切一次 tab；其它任何 query（包括没有 query）
// 都保持这个默认订单列表不变，不要把普通订单入口整体改成桌台视图。
const view = ref(route.query.view === 'table' ? 'table' : 'list')
const selectedTableKey = ref(null)
const showTableDetail = ref(false)
const showSettleDialog = ref(false)
const settlingTable = ref(null)
const settling = ref(false)
const showReceiptDialog = ref(false)
const receiptData = ref(null)

// 代客加单：只在「记账后付/桌台账」模式下开放——预付模式每单都要在线支付，
// 服务员没法替顾客走支付流程，这个入口对预付商户没有意义。
const paymentMode = ref('')
const canStaffOrder = computed(() => ['postpay', 'table_account'].includes(paymentMode.value))
const staffOrderVisible = ref(false)
const staffOrderTable = ref('')
// 同一个桌号可能同时挂着好几张卡片（历史遗留的桌台会话），选中态不能只按桌号字符串
// 判断——不然点一张就会把所有同桌号的卡片一起点亮。这里单独记一个"具体点中了哪张卡"，
// 已有桌台用它的 groupKey，"新开一桌"用 'new:'+桌号 前缀，互不冲突。
const staffOrderSelectedKey = ref('')
const staffMenuItems = ref([])
const staffMenuLoading = ref(false)
const staffMenuLoaded = ref(false)
const staffCart = ref({}) // dish_id -> qty
const staffNote = ref('')
const staffPickupNo = ref('')
const staffSubmitting = ref(false)
const pickupNoEnabled = ref(false)
const pickupCount = ref(30)
const pickupOccupied = ref([])
const pickupSheetOpen = ref(false)
const pickupSheetLoading = ref(false)
const pickupSheetSubmitting = ref(false)
const pickupTargetOrder = ref(null)
const pickupStaffMode = ref(false)

function orderNeedsPickup(order) {
  return needsPickup(order)
}
function orderCanReplacePickup(order) {
  return canReplacePickup(order)
}

const pendingPickupOrders = computed(() => orders.value.filter((o) => orderNeedsPickup(o)))
const pendingPickupCount = computed(() => pendingPickupOrders.value.length)

const selectedTablePickupOrder = computed(() => {
  const table = selectedTable.value
  if (!table?.orders?.length) return null
  return (
    table.orders.find((o) => orderNeedsPickup(o))
    || table.orders.find((o) => orderCanReplacePickup(o))
    || null
  )
})

const pickupSheetCurrent = computed(() => {
  if (pickupStaffMode.value) return staffPickupNo.value || ''
  return pickupTargetOrder.value?.pickup_no || ''
})
const pickupSheetSessionId = computed(() => {
  if (pickupStaffMode.value) return ''
  return pickupTargetOrder.value?.diningSessionId || ''
})

async function refreshPickupStatus() {
  pickupSheetLoading.value = true
  try {
    const res = await getPickupNoStatus({
      meta: { fromPolling: true, dedupe: true, dedupeKey: 'pickup-nos:status' },
    })
    if (res?.code === 200 && res.data) {
      pickupNoEnabled.value = !!res.data.enabled
      pickupCount.value = Number(res.data.count || 30)
      pickupOccupied.value = Array.isArray(res.data.occupied) ? res.data.occupied : []
    }
  } catch {
    /* 弹层仍可按本地 count 展示；后端 UNIQUE 仍是最终边界 */
  } finally {
    pickupSheetLoading.value = false
  }
}

async function openPickupSheet(order) {
  if (!order) return
  if (!orderNeedsPickup(order) && !orderCanReplacePickup(order)) return
  pickupStaffMode.value = false
  pickupTargetOrder.value = order
  pickupSheetOpen.value = true
  await refreshPickupStatus()
}

async function openStaffPickupSheet() {
  pickupStaffMode.value = true
  pickupTargetOrder.value = null
  pickupSheetOpen.value = true
  await refreshPickupStatus()
}

async function focusFirstPendingPickup() {
  const first = pendingPickupOrders.value[0]
  if (!first) return
  view.value = 'list'
  await nextTick()
  const el = document.querySelector(`[data-order-card="${first.id}"]`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function handlePickupSelect(n) {
  if (pickupSheetSubmitting.value) return
  const value = String(n || '').trim()
  if (!value) return

  if (pickupStaffMode.value) {
    staffPickupNo.value = value
    pickupSheetOpen.value = false
    message.success(`已选择${value}号桌牌`)
    return
  }

  const order = pickupTargetOrder.value
  if (!order) return
  if (value === String(order.pickup_no || '')) {
    pickupSheetOpen.value = false
    return
  }

  pickupSheetSubmitting.value = true
  try {
    const res = await updateOrderPickupNo(order.id, value)
    if (res?.code === 200) {
      pickupSheetOpen.value = false
      message.success(`已绑定${value}号桌牌`)
      await reconcileAfterOrderAction()
    } else if (res?.code === 409) {
      message.warning(pickupConflictToast(value))
      await refreshPickupStatus()
      await reconcileAfterOrderAction()
    } else {
      message.error(res?.msg || '绑定失败，请重试')
      await reconcileAfterOrderAction()
    }
  } catch {
    message.error('网络异常，请重试')
    await reconcileAfterOrderAction()
  } finally {
    pickupSheetSubmitting.value = false
  }
}

// 新开一桌：不能让店员手打桌号（容易跟顾客自己扫码用的桌号对不上，同一张桌子
// 变成两个不同字符串、账就分裂了）。可选的桌号必须来自商家自己在"桌码管理"
// 里已经生成过桌贴码的那些桌号——这些字符串已经印在贴纸上贴在真实桌子上了，
// 是唯一可信的桌号来源。这里只列出"已经有桌贴码、但今天还没人扫码点过单"的桌，
// 点一下就用这个真实桌号开桌，全程不需要输入。
const staffAllTables = ref([])
const staffNewTablesLoaded = ref(false)
const staffNewTablesLoading = ref(false)

async function ensureStaffNewTablesLoaded() {
  if (staffNewTablesLoaded.value) return
  staffNewTablesLoading.value = true
  try {
    const res = await getEntranceCodes({ page: 1, page_size: 200 })
    const list = res?.data?.items || res?.data?.data?.items || []
    staffAllTables.value = (Array.isArray(list) ? list : [])
      .filter(item => item.channel === 'TABLE' && item.status === 1 && item.table_no)
    staffNewTablesLoaded.value = true
  } catch {
    // 静默失败：这只是「新开一桌」这个兜底入口用的数据，加载失败不该挡住主流程
    // （给已有桌台加单）的使用。
  } finally {
    staffNewTablesLoading.value = false
  }
}

const staffAvailableNewTables = computed(() => {
  const activeTableNos = new Set(visibleTableGroups.value.map(t => String(t.tableNo)))
  const seen = new Set()
  return staffAllTables.value.filter(item => {
    const no = String(item.table_no)
    if (activeTableNos.has(no) || seen.has(no)) return false
    seen.add(no)
    return true
  })
})

async function loadPaymentMode() {
  try {
    const res = await getTenantProfile()
    paymentMode.value = res?.data?.payment_mode || 'prepay'
    if (res?.data?.pickup_no_enabled != null) {
      pickupNoEnabled.value = !!res.data.pickup_no_enabled
    }
    if (res?.data?.pickup_no_count != null) {
      pickupCount.value = Number(res.data.pickup_no_count) || 30
    }
  } catch {}
  try {
    const status = await getPickupNoStatus()
    if (status?.code === 200 && status.data) {
      pickupNoEnabled.value = !!status.data.enabled
      pickupCount.value = Number(status.data.count || 30)
      pickupOccupied.value = Array.isArray(status.data.occupied) ? status.data.occupied : []
    }
  } catch {}
}

async function ensureStaffMenuLoaded() {
  if (staffMenuLoaded.value) return
  staffMenuLoading.value = true
  try {
    const res = await getMenuItems()
    const list = res?.data?.data || res?.data || []
    staffMenuItems.value = (Array.isArray(list) ? list : []).filter(d => d.available !== false)
    staffMenuLoaded.value = true
  } catch {
    message.error('菜单加载失败')
  } finally {
    staffMenuLoading.value = false
  }
}

const staffMenuCategories = computed(() => {
  const set = new Set()
  staffMenuItems.value.forEach(d => set.add(d.category || '默认'))
  return Array.from(set)
})
function staffMenuByCategory(cat) {
  return staffMenuItems.value.filter(d => (d.category || '默认') === cat)
}

const staffCartCount = computed(() => Object.values(staffCart.value).reduce((s, q) => s + q, 0))
const staffCartTotal = computed(() =>
  staffMenuItems.value.reduce((sum, d) => sum + (staffCart.value[d.id] || 0) * Number(d.price || 0), 0)
)

function staffCartAdd(dish) {
  staffCart.value = { ...staffCart.value, [dish.id]: (staffCart.value[dish.id] || 0) + 1 }
}
function staffCartRemove(dish) {
  const next = { ...staffCart.value }
  if (!next[dish.id]) return
  next[dish.id] -= 1
  if (next[dish.id] <= 0) delete next[dish.id]
  staffCart.value = next
}

async function openStaffOrder(tableNo, groupKey) {
  staffOrderTable.value = tableNo || ''
  staffOrderSelectedKey.value = groupKey || ''
  staffCart.value = {}
  staffNote.value = ''
  staffPickupNo.value = ''
  staffOrderVisible.value = true
  await Promise.all([ensureStaffMenuLoaded(), ensureStaffNewTablesLoaded()])
}

async function submitStaffOrder() {
  const tableNo = staffOrderTable.value.trim()
  if (!tableNo || staffCartCount.value === 0) return
  staffSubmitting.value = true
  try {
    const items = Object.entries(staffCart.value).map(([dishId, qty]) => {
      const dish = staffMenuItems.value.find(d => String(d.id) === String(dishId))
      return { dish_id: dishId, name: dish?.name || '', price: Number(dish?.price || 0), qty }
    })
    const requestId = `owner-ao-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    const res = await createOrder({
      shop: getCurrentTenantId(),
      table: tableNo,
      items,
      total: staffCartTotal.value,
      staff_note: staffNote.value.trim() || undefined,
      pickup_no: staffPickupNo.value.trim() || undefined,
      request_id: requestId,
    })
    if (res.code === 200) {
      message.success('加单成功，厨房已收到')
      staffOrderVisible.value = false
      staffPickupNo.value = ''
      await loadOrders()
    } else {
      message.error(res.msg || '提交失败')
    }
  } catch {
    message.error('提交失败，请重试')
  } finally {
    staffSubmitting.value = false
  }
}
function mapOwnerOrders(raw) {
  const uniqueOrders = Array.from(new Map((Array.isArray(raw) ? raw : []).map(o => [String(o.id), o])).values())
  return uniqueOrders.map(o => ({
      id: String(o.id),
      table: o.table_no || '-',
      diningSessionId: o.dining_session_id || null,
      checkoutRequestedAt: o.checkout_requested_at || null,
      participantNo: o.participant_no || null,
      status: o.status || 'pending',
      status_text: o.status_text || '',
      total: Number(o.total || 0),
      discount_amount: o.discount_amount ? Number(o.discount_amount) : null,
      remark: o.remark || '',
      source: o.source || 'miniprogram',
      createdByAccountId: o.created_by_account_id || null,
      createdByRole: o.created_by_role || null,
      staffNote: o.staff_note || '',
      pickup_no: o.pickup_no || '',
      canAssignPickupNo: !!o.can_assign_pickup_no,
      served_at: o.served_at || null,
      paymentStatus: o.payment_status || '',
      canCancel: o.can_cancel === true,
      canReject: o.can_reject === true,
      refundRequired: o.refund_required === true,
      printStatus: o.print_status || null,
      printErrorCode: o.print_error_code || '',
      printLastAttemptAt: o.print_last_attempt_at || '',
      printProvider: o.print_provider || '',
      printPrinterIdentifier: o.print_printer_identifier || '',
      printManualReprintCount: Number(o.print_manual_reprint_count || 0),
      printManualReprintLastStatus: o.print_manual_reprint_last_status || '',
      createdAt: o.created_at || '',
      time: o.created_at ? new Date(o.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '',
      items: Array.isArray(o.items) ? o.items : [],
      paymentMethodText: paymentMethodText(o.payment_method, o.payment_status),
      updating: false,
      reprinting: false,
      refunding: false,
    }))
}

function readOwnerCursor(headers) {
  return headers?.['x-workbench-cursor'] || headers?.['X-Workbench-Cursor'] ||
    headers?.get?.('x-workbench-cursor') || headers?.get?.('X-Workbench-Cursor') || null
}

async function fetchOwnerFull() {
  const res = await getOrdersWithCursor(
    { date_str: 'today' },
    { meta: { fromPolling: true, dedupe: true, dedupeKey: 'admin:orders:today:manage' } },
  )
  return { orders: res?.data?.data || [], cursor: readOwnerCursor(res?.headers) }
}

async function fetchOwnerChanges(cursor) {
  const res = await getOwnerOrderChanges(
    { cursor },
    { meta: { fromPolling: true, dedupe: true, dedupeKey: 'admin:orders:today:changes' } },
  )
  const data = res?.data || {}
  return {
    items: Array.isArray(data.items) ? data.items : [],
    removed_ids: Array.isArray(data.removed_ids) ? data.removed_ids : [],
    next_cursor: data.next_cursor || cursor,
    has_more: Boolean(data.has_more),
    bootstrap: Boolean(data.bootstrap),
  }
}

const {
  orders,
  initialLoading,
  backgroundSyncing,
  syncFailureCount,
  lastSuccessfulSyncAt,
  alertEnabled,
  audioNeedsUnlock,
  enableAlert,
  disableAlert,
  unlockAudio,
  syncNow,
  startSync,
} = useWorkbenchSync({
  dedupeKey: 'owner:orders',
  fetchFull: fetchOwnerFull,
  fetchChanges: fetchOwnerChanges,
  filterOrders: (raw) => raw,
  mapOrders: mapOwnerOrders,
  alertIdsFromOrders: ownerActionableIdsFromOrders,
  autoStart: false,
})

const loading = computed(() => initialLoading.value || backgroundSyncing.value)
const pollFailCount = syncFailureCount
const lastRefreshed = computed(() => {
  if (!lastSuccessfulSyncAt.value) return ''
  const now = new Date(lastSuccessfulSyncAt.value)
  return `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
})

async function loadOrders() {
  return syncNow()
}

async function loadReviews() {
  try {
    const res = await getReviews()
    const list = res?.data?.data || []
    const map = {}
    list.forEach(r => { map[r.order_id] = r })
    reviewsMap.value = map
  } catch {}
}

async function manualRefresh() {
  await loadPaymentMode()
  await loadOrders()
  message.success('已刷新', 1)
}

const pendingCount = computed(() => orders.value.filter(o => o.status === 'pending').length)
const preparingCount = computed(() => orders.value.filter(o => o.status === 'preparing').length)
// 待结账只统计属于明确桌台会话的 done 订单——没有 diningSessionId 的历史订单不构成
// 一张真实可结账的桌台（见 tableGroups 上面的说明），不该被算进这个数字，否则跟桌台
// 视图上"看不到任何可结账桌子"互相矛盾。
const doneCount = computed(() => orders.value.filter(o => o.status === 'done' && o.diningSessionId).length)
const pendingPaymentCount = computed(() => orders.value.filter(o => o.status === 'pending_payment').length)
// 记账/桌台账模式下，preparing/done 阶段顾客还没有实际付款，钱是结账（settled）那一刻
// 才真正收到的——用跟预付模式一样的口径把 preparing/done 也算进"今日营收"会让这个数字
// 虚高，误导商家对当天实际到手现金的判断，所以这两种模式下只统计已结账的订单。
const todayRevenue = computed(() => {
  const revenueStatuses = ['postpay', 'table_account'].includes(paymentMode.value)
    ? ['settled']
    : ['preparing', 'done', 'settled']
  return orders.value.filter(o => revenueStatuses.includes(o.status)).reduce((s, o) => s + o.total, 0).toFixed(2)
})

const statItems = computed(() => [
  { label: '待接单', value: pendingCount.value, color: pendingCount.value > 0 ? '#ef4444' : '#374151' },
  { label: '制作中', value: preparingCount.value, color: '#374151' },
  { label: '待结账', value: doneCount.value, color: '#16a34a' },
  { label: '今日营收', value: '¥' + todayRevenue.value, color: '#07C160' },
])

const orderCenterMode = ref('live')
const customDate = ref('')
const historyQuery = ref('')
const todayDateInput = computed(() => {
  const now = new Date()
  const utc8 = new Date(now.getTime() + 8 * 60 * 60 * 1000)
  return utc8.toISOString().slice(0, 10)
})
const isLiveToday = computed(() => orderCenterMode.value === 'live')
const historyDateKey = ref('yesterday')
const historicalOrders = ref([])
const historicalTotal = ref(0)
const historicalPage = ref(1)
const historicalLoading = ref(false)
const HISTORICAL_PAGE_SIZE = 20

function setHistoryDate(key) {
  historyDateKey.value = key
  view.value = 'list'
  if (key === 'yesterday') customDate.value = ''
  else customDate.value = key
}

function onCustomDate() {
  const value = String(customDate.value || '').trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return
  historyDateKey.value = value
  view.value = 'list'
}

const sourceOrders = computed(() => (isLiveToday.value ? orders.value : historicalOrders.value))

function historySearchParams() {
  const q = String(historyQuery.value || '').trim()
  if (!q) return {}
  if (/^\d+$/.test(q)) return { order_tail: q }
  return { table_no: q }
}

async function loadHistoricalOrders({ append = false } = {}) {
  if (isLiveToday.value) return
  if (historicalLoading.value) return
  historicalLoading.value = true
  try {
    const page = append ? historicalPage.value + 1 : 1
    const res = await getOrders({
      date_str: historyDateKey.value,
      page,
      page_size: HISTORICAL_PAGE_SIZE,
      ...historySearchParams(),
    })
    if (res?.code && res.code !== 200) {
      message.error(res.msg || '历史订单加载失败')
      if (!append) historicalOrders.value = []
      return
    }
    const payload = res?.data || {}
    const rows = mapOwnerOrders(Array.isArray(payload.items) ? payload.items : [])
    historicalTotal.value = Number(payload.total || 0)
    historicalPage.value = Number(payload.page || page)
    historicalOrders.value = append ? historicalOrders.value.concat(rows) : rows
  } catch {
    if (!append) historicalOrders.value = []
    message.error('历史订单加载失败')
  } finally {
    historicalLoading.value = false
  }
}

const statusFilter = ref('')
const statusFilters = [
  { label: '全部', val: '' },
  { label: formatOrderStatusText('pending'), val: 'pending' },
  { label: formatOrderStatusText('preparing'), val: 'preparing' },
  { label: formatOrderStatusText('done'), val: 'done' },
  { label: formatOrderStatusText('settled'), val: 'settled' },
  { label: formatOrderStatusText('pending_payment'), val: 'pending_payment' },
  { label: formatOrderStatusText('rejected'), val: 'rejected' },
  { label: formatOrderStatusText('cancelled'), val: 'cancelled' },
]

// 顾客来店里反馈"我这单有问题"时，能报出来的通常就是桌号、大概几点、点了什么菜——
// 顾客小程序端"本桌已点菜品"里本来就会显示订单尾号（id 后4位），这里用同一套算法，
// 保证两边报的号对得上。搜索关键词可以匹配桌号、尾号、菜品名，覆盖顾客最常能报出来
// 的几种线索，不需要精确记住完整订单号。
const searchQuery = ref('')
const orderTail = (order) => String(order.id).slice(-4)

// 顾客投诉里很常见的一类是"我明明付了钱"——这里直接把支付方式和是否到账摊开显示，
// 商家不用再去猜这单到底是不是真的收到钱了。
function paymentMethodText(method, paymentStatus) {
  if (paymentStatus && paymentStatus !== 'paid') return '未支付'
  const labels = { wxpay: '微信支付', offline: '线下/记账已收', free: '优惠券抵扣至0元', balance: '余额支付', mock: '测试支付' }
  return labels[method] || ''
}

const sortedOrders = computed(() => {
  if (!isLiveToday.value) return historicalOrders.value
  let list = statusFilter.value
    ? sourceOrders.value.filter(o => o.status === statusFilter.value)
    : sourceOrders.value.filter(o => o.status !== 'pending_payment')
  const q = searchQuery.value.trim()
  if (q) {
    list = list.filter(o =>
      String(o.table).includes(q) ||
      orderTail(o).includes(q) ||
      o.items.some(item => (item.name || '').includes(q))
    )
  }
  // 后端 list_orders 按 created_at DESC；工作台有意二次排序：履约态 FIFO、终态/查看态最新优先。
  return sortMerchantOrders(list)
})

const LIST_PAGE_SIZE = 20
const listVisibleCount = ref(LIST_PAGE_SIZE)
const visibleOrders = computed(() => (
  isLiveToday.value ? sortedOrders.value.slice(0, listVisibleCount.value) : sortedOrders.value
))
watch([statusFilter, searchQuery], () => { listVisibleCount.value = LIST_PAGE_SIZE })
watch(orderCenterMode, async (mode) => {
  if (mode !== 'history') return
  view.value = 'list'
  await loadHistoricalOrders({ append: false })
})
watch(historyDateKey, async () => {
  if (isLiveToday.value) return
  await loadHistoricalOrders({ append: false })
})

const tableGroups = computed(() => {
  // 按 dining_session_id 分组，而不是按桌号：同一桌当天翻台会产生多个会话，
  // 按桌号分组会把上一批已结账客人的订单和当前这批混在一起，导致结账金额和小票错乱。
  // 没有 dining_session_id 的订单（老版本 H5 直连下单、超管填充测试数据等历史遗留）
  // 一律不进桌台视图分组——这类订单从建单起就没有会话身份，按桌号硬凑成一张"桌台卡"
  // 曾经导致过 P0 事故：同一桌号当时另有一个正在使用中的真实会话，商家在这张假卡片
  // 上点"结账"，后端为了不误结错桌正确拒绝（要求明确会话），但前端此前完全没有拦这
  // 一步，商家只能在点了"确认收款"之后才看到"请指定要结账的会话"。这类订单不会从系统
  // 里消失——它们仍在 orders.value 里，订单列表 tab 照常能看到/搜到，只是不再冒充一张
  // 可结账的桌台卡。
  const map = {}
  for (const o of orders.value) {
    if (['cancelled', 'rejected'].includes(o.status)) continue
    if (!o.diningSessionId) continue
    const key = `session:${o.diningSessionId}`
    if (!map[key]) map[key] = { groupKey: key, tableNo: o.table, diningSessionId: o.diningSessionId, orders: [], pendingPaymentOrders: [], total: 0, updating: false, checkoutRequestedAt: null }
    if (o.status === 'pending_payment') {
      map[key].pendingPaymentOrders.push(o)
      continue
    }
    map[key].orders.push(o)
    map[key].total += o.total
    if (o.checkoutRequestedAt && !map[key].checkoutRequestedAt) map[key].checkoutRequestedAt = o.checkoutRequestedAt
  }
  return Object.values(map).map(t => ({
    ...t,
    pickupNo: t.orders.find(o => o.pickup_no)?.pickup_no || null,
    pendingOrders: t.orders.filter(o => o.status === 'pending'),
    preparingOrders: t.orders.filter(o => o.status === 'preparing'),
    // Boolean(t.diningSessionId) 是第二道保险：本函数上面已经把没有会话的订单整个跳过、
    // 从不建组，理论上这里的 t.diningSessionId 必然存在——但结账能力判断本身必须独立
    // fail closed，不能只依赖分组阶段"恰好没漏"。
    canSettle: Boolean(t.diningSessionId) && t.orders.length > 0 && t.orders.every(o => ['done', 'settled'].includes(o.status)) && t.orders.some(o => o.status === 'done') && t.pendingPaymentOrders.length === 0,
    isSettled: t.orders.length > 0 && t.orders.every(o => o.status === 'settled'),
  })).sort((a, b) => {
    const p = t => t.pendingOrders.length ? 0 : t.preparingOrders.length ? 1 : t.canSettle ? 2 : 3
    return p(a) - p(b)
  })
})

// 桌台视图不再展示的历史/无会话订单——不是从系统里消失，只是不再冒充可结账的桌台卡，
// 订单列表 tab 里始终看得到。这里只用来判断要不要在桌台视图给一个"去订单列表看"的
// 极轻提示，不建独立的历史订单管理入口。已经 settled 的排除在外——那些是已经处理完
// 的历史订单，没有任何东西需要商家去订单列表"看"，永久挂着这条提示只是噪音。
const hasSessionlessActiveOrders = computed(() =>
  orders.value.some(o => !o.diningSessionId && !['cancelled', 'rejected', 'settled'].includes(o.status))
)

// 已结账的桌子对商家来说已经"翻台完毕"，不该继续占宫格——这里只在网格里隐藏，
// tableGroups 本身仍保留全量数据，这样刚结完账那一刻抽屉（selectedTable）还能正常
// 显示"已结账"的最终状态，不会因为过滤掉而突然变空白。
const visibleTableGroups = computed(() => tableGroups.value.filter(t => !t.isSettled))

// 宫格点进去看的那一桌详情，用 computed 而不是存快照，这样轮询刷新订单状态时
// 抽屉里的内容能跟着一起更新，不用关了再点一次才看到最新状态。
const selectedTable = computed(() => tableGroups.value.find(t => t.groupKey === selectedTableKey.value) || null)
function openTableDetail(table) {
  selectedTableKey.value = table.groupKey
  showTableDetail.value = true
}

function tableTagClass(t) {
  if (t.pendingOrders?.length) return 'pending'
  if (t.preparingOrders?.length) return 'preparing'
  if (t.canSettle) return 'done'
  // 只有待支付订单挡着、还没有任何已完成订单的桌子，不该套用"已结账"的灰色低优先级样式——
  // 这单钱还没收到，需要商家关注，跟真正结完账的桌子视觉上必须区分开。
  if (t.pendingPaymentOrders?.length) return 'pending_payment'
  return 'settled'
}

function tableStatusText(t) {
  if (t.pendingOrders?.length) return String(t.pendingOrders.length) + ' 单待接'
  if (t.preparingOrders?.length) return formatOrderStatusText('preparing')
  if (t.canSettle) return t.checkoutRequestedAt ? '顾客催结账 ⏰' : '可结账'
  if (t.isSettled) return '已结账'
  if (t.pendingPaymentOrders?.length) return '有订单待支付'
  return ''
}

function staffSourceLabel(order) {
  const role = order?.createdByRole || order?.created_by_role
  if (role === 'frontdesk') return '前台代加'
  if (role === 'waiter') return '服务员代加'
  if (role === 'owner') return '老板代加'
  return '员工代加'
}

function statusLabel(s, statusText) {
  return formatOrderStatusText(s, statusText)
}

// 拼桌时标出"这一单是第几位点的"，跟顾客小程序端用同一套颜色循环，纯展示编号，
// 不关联真实身份——同桌不一定互相认识，不适合亮真实姓名。
const PARTICIPANT_COLORS = ['#07C160', '#FF7D45', '#5B8FF9', '#F5A623', '#B37FEB', '#3ABBB0']
function participantColor(no) {
  if (!no || no < 1) return PARTICIPANT_COLORS[0]
  return PARTICIPANT_COLORS[(no - 1) % PARTICIPANT_COLORS.length]
}

async function reconcileAfterOrderAction() {
  await syncNow()
}

function showPaidCancelSop() {
  Modal.warning({
    title: '已付款订单不可直接取消',
    content: '已付款订单请点击退款，由系统向支付渠道发起退款，不能直接取消。',
    okText: '我知道了',
  })
}

function cancelPendingPaymentOrder(order) {
  Modal.confirm({
    title: '取消这单待支付订单？',
    content: `¥${Number(order.total).toFixed(2)}，取消后顾客的这个订单会失效，需要重新下单。`,
    okText: '取消订单',
    okType: 'danger',
    cancelText: '再想想',
    onOk: async () => {
      order.updating = true
      try {
        const res = await updateOrderStatus(order.id, 'cancelled')
        if (res.code === 200) message.success('已取消')
        else if (res?.data?.code === 'PAID_ORDER_CANCEL_REQUIRES_REFUND') showPaidCancelSop()
        else message.error(res.msg || '取消失败，请刷新页面重试')
        await reconcileAfterOrderAction()
      } catch { message.error('取消失败'); await reconcileAfterOrderAction() }
      finally { order.updating = false }
    },
  })
}

async function acceptOrder(order) {
  order.updating = true
  try {
    const res = await updateOrderStatus(order.id, 'preparing')
    if (res.code === 200) await reconcileAfterOrderAction()
    else { message.error(res.msg || '操作失败，请刷新页面重试'); await reconcileAfterOrderAction() }
  }
  catch { message.error('操作失败'); await reconcileAfterOrderAction() } finally { order.updating = false }
}

// 牌子管的是这一桌这一次吃饭：接口会把号同步给同一桌台会话下所有订单，立刻回写本地列表。
function applyPickupNoToOrders(pickupNo, orderIds) {
  const idSet = new Set((orderIds || []).map(String))
  for (const o of orders.value) {
    if (idSet.has(String(o.id))) {
      o.pickup_no = pickupNo || ''
      // 已有号后后端 can_assign=false；本地立即关掉「待发」避免等下一轮轮询
      o.canAssignPickupNo = !pickupNo
    }
  }
}

async function rejectOrder(order) {
  order.updating = true
  try {
    const res = await updateOrderStatus(order.id, 'rejected')
    if (res.code === 200) {
      message.warning('已拒单，请联系顾客说明原因')
      await reconcileAfterOrderAction()
    } else if (res?.data?.code === 'PAID_ORDER_CANCEL_REQUIRES_REFUND') {
      showPaidCancelSop()
      await reconcileAfterOrderAction()
    } else { message.error(res.msg || '操作失败，请刷新页面重试'); await reconcileAfterOrderAction() }
  }
  catch { message.error('操作失败'); await reconcileAfterOrderAction() } finally { order.updating = false }
}

async function finishOrder(order) {
  order.updating = true
  try {
    const res = await updateOrderStatus(order.id, 'done')
    if (res.code === 200) {
      await reconcileAfterOrderAction()
    } else { message.error(res.msg || '操作失败，请刷新页面重试'); await reconcileAfterOrderAction() }
  }
  catch { message.error('操作失败'); await reconcileAfterOrderAction() } finally { order.updating = false }
}

function orderNeedsServe(order) {
  return order?.status === 'done' && !order?.served_at
}

async function confirmServed(order) {
  order.updating = true
  try {
    const res = await serveOrder(order.id)
    if (res?.code === 200) {
      message.success('已确认上菜')
      await reconcileAfterOrderAction()
    } else { message.error(res?.msg || '操作失败，请刷新页面重试'); await reconcileAfterOrderAction() }
  } catch {
    message.error('操作失败')
    await reconcileAfterOrderAction()
  } finally {
    order.updating = false
  }
}

function refundPaidOrderClick(order) {
  Modal.confirm({
    title: '确认退款？',
    content: `¥${Number(order.total).toFixed(2)}，将由系统向支付渠道发起退款。已付款订单不能直接取消。`,
    okText: '确认退款',
    okType: 'danger',
    cancelText: '再想想',
    onOk: async () => {
      order.refunding = true
      try {
        const res = await refundPaidOrder(order.id)
        if (res.code === 200) message.success(res.msg || '已提交退款')
        else message.error(res.msg || '退款失败，请稍后重试')
        await reconcileAfterOrderAction()
      } catch (err) {
        if (err?.response?.status !== 403) {
          message.error(err?.response?.data?.msg || '退款失败')
        }
        await reconcileAfterOrderAction()
      } finally {
        order.refunding = false
      }
    },
  })
}

async function reprintOrderTicket(order) {
  order.reprinting = true
  try {
    const res = await reprintOrder(order.id)
    if (res.code === 200) {
      const printStatus = res.data?.print_status || null
      if (printStatus === 'printed') message.success('已重新打印')
      else message.warning('打印结果仍未知，请核实小票机是否已出票')
      await reconcileAfterOrderAction()
    } else {
      message.error(res.msg || '补打失败')
      await reconcileAfterOrderAction()
    }
  } catch { message.error('补打失败'); await reconcileAfterOrderAction() } finally { order.reprinting = false }
}

function printDiagnostic(order) {
  const route = [order.printProvider, order.printPrinterIdentifier].filter(Boolean).join(' / ')
  const attempt = order.printLastAttemptAt
    ? new Date(order.printLastAttemptAt).toLocaleString('zh-CN', { hour12: false })
    : '暂无时间'
  const manual = order.printManualReprintCount
    ? ` · 补打${order.printManualReprintCount}次(${order.printManualReprintLastStatus || '处理中'})`
    : ''
  return `${order.printErrorCode || '未返回错误码'} · ${attempt}${route ? ` · ${route}` : ''}${manual}`
}

async function acceptTableOrders(table) {
  table.updating = true
  try {
    for (const o of table.pendingOrders) {
      const res = await updateOrderStatus(o.id, 'preparing')
      if (res.code !== 200) { message.error(res.msg || '操作失败，请刷新页面重试'); break }
    }
    await reconcileAfterOrderAction()
  } catch { message.error('操作失败'); await reconcileAfterOrderAction() } finally { table.updating = false }
}

async function finishTableOrders(table) {
  table.updating = true
  try {
    for (const o of table.preparingOrders) {
      const res = await updateOrderStatus(o.id, 'done')
      if (res.code !== 200) { message.error(res.msg || '操作失败，请刷新页面重试'); break }
    }
    await reconcileAfterOrderAction()
  } catch { message.error('操作失败'); await reconcileAfterOrderAction() } finally { table.updating = false }
}

function settleTableClick(table) {
  // Defensive last line, not the primary guard -- tableGroups() no longer builds a
  // group without a diningSessionId at all, and canSettle already requires one, so
  // this should be unreachable in normal operation. Kept anyway so a future regression
  // in either of those still fails closed BEFORE the confirm-payment dialog opens,
  // instead of only after the merchant clicks "确认收款" and hits the backend's reject.
  if (!table?.diningSessionId) {
    message.error('该桌订单缺少有效桌台会话，请刷新后重试')
    return
  }
  settlingTable.value = table
  showSettleDialog.value = true
}

async function confirmSettle() {
  if (!settlingTable.value) return
  settling.value = true
  try {
    const res = await settleTable(settlingTable.value.tableNo, settlingTable.value.diningSessionId)
    if (res.code !== 200) {
      const statuses = res.data?.blocking_statuses
      const detail = Array.isArray(statuses) && statuses.length ? `（${statuses.map(statusLabel).join('、')}）` : ''
      message.error(`${res.msg || '结账失败'}${detail}`)
      // 结账失败常常是因为这张桌台卡片本身已经过期——比如这一桌已经被结过账了
      // （另一台设备操作、或者上一次点击其实已经成功但本地没刷新），也可能是 P0-10：
      // 本地这张卡片对应的会话已经不是服务端当前那一桌了（res.data.code ===
      // 'SESSION_SETTLE_CONFLICT'）。两种情况本地缓存的 orders.value 都已经过期，
      // 不重新拉一次订单的话，商家会对着一张服务端早就不认的过期卡片反复点
      // "确认收款"，每次都收到同一个错误，界面上却什么都不会变。这里主动关掉
      // 弹窗、重新拉取，让桌台视图跟服务端状态对齐。
      showSettleDialog.value = false
      await reconcileAfterOrderAction()
      return
    }
    const table = settlingTable.value
    showSettleDialog.value = false
    const now = new Date()
    // P0-10-02: the receipt MUST be built from the settle-table response's own
    // authoritative settled_orders snapshot, never from `table` (captured when
    // the dialog opened) -- that local snapshot could describe a different,
    // earlier session at this same physical table if this admin page was stale.
    receiptData.value = {
      tableNo: res.data.table_no || table.tableNo,
      settledAt: `${now.getFullYear()}/${now.getMonth()+1}/${now.getDate()} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`,
      total: Number(res.data.total || 0).toFixed(2),
      orders: (res.data.settled_orders || []).map(o => ({ id: o.id, items: o.items, discount_amount: o.discount_amount })),
    }
    showReceiptDialog.value = true
    await reconcileAfterOrderAction()
  } catch { message.error('结账失败，请重试'); await reconcileAfterOrderAction() }
  finally { settling.value = false }
}


onMounted(async () => {
  // 先单独查一次付款模式，再并发拉订单/评价——这两类接口目前对"是否记账/桌台账模式"
  // 的租户身份解析方式不一样，混在同一批并发请求里偶发会互相打架导致查错商户，
  // 拆开顺序请求可以避开这个问题。
  await loadPaymentMode()
  startSync()
  loadReviews()
})
</script>

<style scoped>
.print-diagnostic { margin: -2px 0 6px; color: #b45309; font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 52px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.page-title { font-size: 18px; font-weight: 700; color: var(--text-1); }

.alert-on-badge {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: #16a34a;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 20px;
  padding: 3px 10px;
  cursor: pointer;
  user-select: none;
}

.unlock-audio-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 0 16px 8px;
  font-size: 13px;
  font-weight: 700;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
}

.table-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 10px;
  padding: 8px 16px 0;
}
.table-tile {
  position: relative;
  padding: 12px 10px;
  border-radius: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
  transition: transform .12s ease;
  &:active { transform: scale(.96); }
}
.table-tile-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.table-tile-no { font-size: 15px; font-weight: 800; color: var(--text-1); }
.table-tile-warn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}
.table-tile-state { font-size: 12px; margin-top: 4px; color: var(--text-2); }
.table-tile-total { font-size: 16px; font-weight: 900; margin-top: 6px; color: var(--text-1); }
.table-tile-count { font-size: 11px; color: var(--text-3); margin-top: 2px; }

.table-tile--pending { background: #fef2f2; border-color: #fecaca; }
.table-tile--pending .table-tile-no,
.table-tile--pending .table-tile-state { color: #ef4444; }
.table-tile--preparing { background: #eff6ff; border-color: #bfdbfe; }
.table-tile--preparing .table-tile-no,
.table-tile--preparing .table-tile-state { color: #2563eb; }
.table-tile--done { background: #f0fdf4; border-color: #bbf7d0; }
.table-tile--done .table-tile-no,
.table-tile--done .table-tile-state { color: #16a34a; }
.table-tile--pending_payment { background: #fffbeb; border-color: #fde68a; }
.table-tile--pending_payment .table-tile-no,
.table-tile--pending_payment .table-tile-state { color: #92400e; }
.table-tile--settled { background: var(--bg-page); border-color: var(--border); opacity: .7; }
.table-tile--urgent {
  border-color: #f59e0b;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, .25);
}
.table-tile--urgent .table-tile-state { color: #92400e; font-weight: 700; }
.table-tile--selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand);
}

.staff-table-picker {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 10px;
}

.staff-new-table-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.staff-new-table-chip {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px dashed var(--border);
  background: var(--bg-page);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.staff-new-table-chip--selected {
  border: 1px solid var(--brand);
  border-style: solid;
  background: var(--brand-light);
  color: var(--brand);
}

.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-page);
  border-radius: 12px 12px 0 0;
}
.table-state { font-size: 13px; color: var(--text-2); }
.table-state--urgent { color: #92400e; font-weight: 700; }
.table-total { font-size: 18px; font-weight: 900; color: #07C160; }

.order-row {
  padding: 16px;
  border-top: 1px solid var(--border);
}

/* 拼桌时标出"这一单是第几位点的"，纯展示编号，不关联真实身份 */
.participant-badge {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

/* 菜名是这个页面使用频率最高、后厨/前台最需要一眼看清的信息，字号要明显大于
   周围的状态标签、时间这些次要信息——原来跟时间戳一样挤在 13px 的小字里，
   高峰期在后厨那种环境下很难扫一眼就看清楚。一行一个菜，数量单独放大加粗。 */
.order-items {
  margin-bottom: 10px;
}
.order-item-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 3px 0;
}
.order-item-name {
  font-size: 22px;
  font-weight: 800;
  color: #111827;
  line-height: 1.35;
}
.order-item-qty {
  flex-shrink: 0;
  font-size: 20px;
  font-weight: 900;
  color: #07C160;
}

.order-remark {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #92400e;
  background: #fffbeb;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 8px;
  line-height: 1.5;
}

.order-action-row {
  display: flex;
  gap: 10px;
}

.table-actions {
  display: flex;
  gap: 10px;
  padding: 10px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-page);
  border-radius: 0 0 12px 12px;
}

:deep(.ant-tabs-nav) { padding: 0; }
:deep(.ant-tabs-tab) { padding: 8px 0; font-size: 14px; }

/* 高频操作按钮：后厨/前台在忙的时候用，手指要能不看着点也点得中，
   高度和字号都明显加大，且在所在行里占满可用宽度而不是挤在一起的小按钮。 */
.order-action-btn {
  flex: 1 !important;
  height: 56px !important;
  padding: 0 18px !important;
  font-size: 18px !important;
  font-weight: 800 !important;
  border-radius: 12px !important;
}
.order-action-btn--finish {
  color: #16a34a !important;
  border-color: #16a34a !important;
}
.order-action-btn--settle {
  background: #16a34a !important;
  border-color: #16a34a !important;
}
.order-action-btn--reject {
  font-weight: 700 !important;
}
.paid-cancel-sop {
  color: #b45309;
  font-size: 12px;
  font-weight: 700;
}
.refund-attention {
  margin-bottom: 8px;
  padding: 9px 10px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 12px;
  line-height: 1.5;
}
.tag-rejected {
  color: #fff !important;
  background: #9ca3af !important;
  border-color: #9ca3af !important;
}
.tag-pending_payment {
  color: #92400e !important;
  background: #fffbeb !important;
  border-color: #fde68a !important;
}
/* 待接单/备餐中/已完成/已结账/已取消这 5 个之前共用组件库默认灰色，只能靠读文字分辨——
   现在每个状态一个专属颜色：待接单最紧急用红，备餐中进行中用蓝，已完成可结账用绿，
   已结账/已取消是"事情结束了"用浅灰区分开，不跟前面几个抢注意力。 */
.tag-pending {
  color: #dc2626 !important;
  background: #fef2f2 !important;
  border-color: #fecaca !important;
}
.tag-preparing {
  color: #2563eb !important;
  background: #eff6ff !important;
  border-color: #bfdbfe !important;
}
.tag-done {
  color: #16a34a !important;
  background: #f0fdf4 !important;
  border-color: #bbf7d0 !important;
}
.tag-settled {
  color: #6b7280 !important;
  background: #f3f4f6 !important;
  border-color: #e5e7eb !important;
}
.tag-cancelled {
  color: #9ca3af !important;
  background: #f9fafb !important;
  border-color: #e5e7eb !important;
}
.order-row--pending-payment {
  background: #fffbeb;
}
.pending-payment-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 10px;
  padding: 9px 14px;
  cursor: pointer;
  user-select: none;
}
.pickup-todo-banner {
  margin: 8px 16px 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  cursor: pointer;
  user-select: none;
}
.pickup-todo-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f59e0b;
  flex-shrink: 0;
  display: inline-block;
}
.pickup-todo-title {
  font-size: 13px;
  font-weight: 700;
  color: #c2410c;
  line-height: 1.3;
}
.pickup-todo-sub {
  font-size: 11px;
  color: #b45309;
  margin-top: 2px;
}
.pickup-pending-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  color: #c2410c;
}
.pickup-pending-row,
.pickup-bound-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}
.pickup-bound-tag {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  color: #c2410c;
  font-size: 13px;
  font-weight: 700;
}
.pickup-replace-link {
  border: none;
  background: transparent;
  color: var(--text-3);
  font-size: 13px;
  font-weight: 600;
  padding: 4px 6px;
  cursor: pointer;
}
.filter-chip {
  display: inline-block;
  padding: 4px 14px;
  border-radius: 20px;
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-2);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  transition: transform .15s ease;
  &:active { transform: scale(.95); }
}
.filter-chip--active {
  border-color: #07C160;
  color: #07C160;
  background: #f0fdf4;
  font-weight: 600;
}
.order-date-input {
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 20px;
  color: var(--text-2);
  font-size: 13px;
  background: var(--bg-card);
}

.review-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 6px 10px;
  background: #fffbeb;
  border-radius: 8px;
}
.review-stars-display {
  font-size: 14px;
  color: #f59e0b;
  letter-spacing: 2px;
}
.review-content-text {
  font-size: 12px;
  color: #6b7280;
  flex: 1;
}
</style>







