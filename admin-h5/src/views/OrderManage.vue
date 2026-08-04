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

    <!-- 视图切换 -->
    <a-tabs v-model:activeKey="view" class="animate-in" style="padding:0 16px;margin-top:8px;animation-delay:.04s" :tab-bar-style="{ marginBottom: 0 }">
      <a-tab-pane key="table" tab="桌台视图" />
      <a-tab-pane key="list" tab="订单列表" />
    </a-tabs>

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
          <div class="table-tile-count">{{ table.orders.length }} 单<template v-if="table.pickupNo"> · {{ table.pickupNo }}号牌</template></div>
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

          <!-- 取餐牌号：管的是这一桌这一次吃饭，不是某一单菜，一桌登记一次，后面的加单自动共享 -->
          <div style="padding:8px 16px;border-bottom:1px solid var(--border)">
            <PickupNoPicker :model-value="selectedTable.pickupNo" @pick="(n) => sendTablePickupNo(selectedTable, n)" />
          </div>

          <!-- 订单列表 -->
          <div v-for="order in selectedTable.orders" :key="order.id" class="order-row">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
              <div style="display:flex;align-items:center;gap:6px">
                <span v-if="order.participantNo" class="participant-badge" :style="{ background: participantColor(order.participantNo) }">{{ order.participantNo }}</span>
                <a-tag :class="`tag-${order.status}`" size="small">{{ statusLabel(order.status) }}</a-tag>
                <a-tag v-if="order.source === 'h5'" size="small" style="background:#eff6ff;color:#2563eb;border-color:#bfdbfe;font-size:10px">H5</a-tag>
                <a-tag v-if="order.source === 'staff'" size="small" style="background:#fdf4ff;color:#a21caf;border-color:#f5d0fe;font-size:10px">服务员代点</a-tag>
                <a-tag v-if="order.pickup_no" size="small" style="background:#fff7ed;color:#c2410c;border-color:#fed7aa;font-size:10px">{{ order.pickup_no }}号牌</a-tag>
                <a-tag v-if="order.printStatus === 'failed'" size="small" style="background:#fef2f2;color:#dc2626;border-color:#fecaca;font-size:10px">打印失败</a-tag>
                <a-tag v-else-if="order.printStatus === 'unknown'" size="small" style="background:#fffbeb;color:#b45309;border-color:#fde68a;font-size:10px">打印结果未知</a-tag>
                <span style="font-size:12px;color:var(--text-3)">{{ order.time }}</span>
              </div>
              <div style="text-align:right">
                <div style="font-size:18px;font-weight:800;color:var(--text-1)">¥{{ Number(order.total).toFixed(2) }}</div>
                <div v-if="order.discount_amount" style="font-size:11px;color:#ef4444;margin-top:2px">优惠 -¥{{ Number(order.discount_amount).toFixed(2) }}</div>
              </div>
            </div>
            <div v-if="order.paymentMethodText" style="font-size:11px;color:var(--text-3);margin-bottom:6px">{{ order.paymentMethodText }}</div>
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
              <a-button v-if="order.status === 'pending'" danger :loading="order.updating" @click="rejectOrder(order)" class="order-action-btn order-action-btn--reject">拒单</a-button>
              <a-button v-if="order.status === 'preparing'" :loading="order.updating" @click="finishOrder(order)" class="order-action-btn order-action-btn--finish">出餐完成</a-button>
              <a-button v-if="['failed','unknown'].includes(order.printStatus)" danger :loading="order.reprinting" @click="reprintOrderTicket(order)" class="order-action-btn order-action-btn--reject">补打小票</a-button>
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
              <a-button danger :loading="order.updating" @click="cancelPendingPaymentOrder(order)" class="order-action-btn order-action-btn--reject">取消订单</a-button>
            </div>
          </div>

          <!-- 桌台操作 -->
          <div v-if="canStaffOrder && !selectedTable.isSettled" class="table-actions">
            <a-button :loading="selectedTable.updating" @click="openStaffOrder(selectedTable.tableNo)" class="order-action-btn">
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
      <div v-if="statusFilter !== 'pending_payment' && pendingPaymentCount > 0" style="padding:8px 16px 0">
        <div class="pending-payment-banner tap-shrink" @click="statusFilter = 'pending_payment'">
          <span>{{ pendingPaymentCount }} 笔订单待支付，点击查看</span>
        </div>
      </div>
      <div style="padding:8px 16px 0">
        <a-input
          v-model:value="searchQuery"
          placeholder="按桌号 / 订单尾号 / 菜品名搜索（顾客反馈问题时用这个快速定位）"
          allow-clear
          size="large"
        />
      </div>
      <div style="padding:8px 16px 0;display:flex;gap:8px;flex-wrap:wrap">
        <span
          v-for="f in statusFilters"
          :key="f.val"
          class="filter-chip"
          :class="statusFilter === f.val ? 'filter-chip--active' : ''"
          @click="statusFilter = f.val"
        >{{ f.label }}</span>
      </div>
      <div v-if="orders.length > 0 && sortedOrders.length === 0" style="padding:32px 16px;text-align:center;color:var(--text-3);font-size:13px">
        <template v-if="searchQuery.trim()">没找到匹配"{{ searchQuery.trim() }}"的订单，换个桌号/尾号/菜名试试</template>
        <template v-else-if="statusFilter">今天没有{{ statusFilters.find(f => f.val === statusFilter)?.label }}的订单</template>
        <template v-else>今天的订单都还没到账，去"待支付"筛选看看</template>
      </div>
      <div v-for="order in visibleOrders" :key="order.id" style="padding:8px 16px 0">
        <a-card :bordered="false" :body-style="{ padding: '12px 16px' }">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
            <div style="display:flex;align-items:center;gap:6px">
              <a-tag style="color:#374151;background:#f3f4f6;border-color:#e5e7eb">桌{{ order.table }}</a-tag>
              <span v-if="order.participantNo" class="participant-badge" :style="{ background: participantColor(order.participantNo) }">{{ order.participantNo }}</span>
              <a-tag :class="`tag-${order.status}`">{{ statusLabel(order.status) }}</a-tag>
              <a-tag v-if="order.source === 'staff'" size="small" style="background:#fdf4ff;color:#a21caf;border-color:#f5d0fe;font-size:10px">服务员代点</a-tag>
              <a-tag v-if="order.pickup_no" size="small" style="background:#fff7ed;color:#c2410c;border-color:#fed7aa;font-size:10px">{{ order.pickup_no }}号牌</a-tag>
              <a-tag v-if="order.printStatus === 'failed'" size="small" style="background:#fef2f2;color:#dc2626;border-color:#fecaca;font-size:10px">打印失败</a-tag>
              <a-tag v-else-if="order.printStatus === 'unknown'" size="small" style="background:#fffbeb;color:#b45309;border-color:#fde68a;font-size:10px">打印结果未知</a-tag>
              <span style="font-size:12px;color:var(--text-3)">{{ order.time }}</span>
            </div>
            <div style="text-align:right">
              <div style="font-size:18px;font-weight:800;color:var(--text-1)">¥{{ Number(order.total).toFixed(2) }}</div>
              <div v-if="order.discount_amount" style="font-size:11px;color:#ef4444;margin-top:2px">优惠 -¥{{ Number(order.discount_amount).toFixed(2) }}</div>
            </div>
          </div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:6px">单号尾号 {{ orderTail(order) }}<template v-if="order.paymentMethodText"> · {{ order.paymentMethodText }}</template></div>
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
            <a-button v-if="order.status === 'pending'" type="primary" :loading="order.updating" @click="acceptOrder(order)" class="order-action-btn">接单</a-button>
            <a-button v-if="order.status === 'pending'" danger :loading="order.updating" @click="rejectOrder(order)" class="order-action-btn order-action-btn--reject">拒单</a-button>
            <a-button v-if="order.status === 'preparing'" :loading="order.updating" @click="finishOrder(order)" class="order-action-btn order-action-btn--finish">出餐完成</a-button>
            <a-button v-if="order.status === 'pending_payment'" danger :loading="order.updating" @click="cancelPendingPaymentOrder(order)" class="order-action-btn order-action-btn--reject">取消订单</a-button>
            <a-button v-if="['failed','unknown'].includes(order.printStatus)" danger :loading="order.reprinting" @click="reprintOrderTicket(order)" class="order-action-btn order-action-btn--reject">补打小票</a-button>
          </div>
          <div v-if="!['cancelled','rejected'].includes(order.status)" style="margin-top:8px">
            <PickupNoPicker :model-value="order.pickup_no" @pick="(n) => sendPickupNo(order, n)" />
          </div>
          <div v-if="reviewsMap[order.id]" class="review-row">
            <span class="review-stars-display">{{ '★'.repeat(reviewsMap[order.id].rating) }}{{ '☆'.repeat(5 - reviewsMap[order.id].rating) }}</span>
            <span class="review-content-text">{{ reviewsMap[order.id].content || '顾客未评价' }}</span>
          </div>
        </a-card>
      </div>
      <div v-if="sortedOrders.length > visibleOrders.length" style="padding:8px 16px 0;text-align:center">
        <a-button block @click="listVisibleCount += LIST_PAGE_SIZE">
          加载更多（还有 {{ sortedOrders.length - visibleOrders.length }} 单）
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
            :class="[`table-tile--${tableTagClass(table)}`, { 'table-tile--selected': staffOrderTable === table.tableNo }]"
            @click="staffOrderTable = table.tableNo"
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
              :class="{ 'staff-new-table-chip--selected': staffOrderTable === item.table_no }"
              @click="staffOrderTable = item.table_no"
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
        <a-input v-model:value="staffPickupNo" placeholder="可选：发给顾客的取餐牌号（如：07）" maxlength="16" style="margin-bottom:10px" />
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
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { ReloadOutlined, OrderedListOutlined, EditOutlined, CheckCircleOutlined } from '@ant-design/icons-vue'
import { getOrders, updateOrderStatus, updateOrderPickupNo, reprintOrder, settleTable, getReviews, getTenantProfile, getMenuItems, createOrder, getEntranceCodes } from '../api'
import pollingManager from '../utils/pollingManager'
import { useOrderAlert } from '../composables/useOrderAlert'
import PickupNoPicker from '../components/PickupNoPicker.vue'

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

const loading = ref(false)
const orders = ref([])
const reviewsMap = ref({}) // order_id -> review
// 默认打开"订单列表"而不是"桌台视图"——按桌视图要点开桌子详情抽屉才能看到接单/出餐
// 按钮，多了一步；订单列表按钮直接在卡片上。桌台视图还在，需要看整桌汇总时手动切过去。
const view = ref('list')
const selectedTableKey = ref(null)
const showTableDetail = ref(false)
const showSettleDialog = ref(false)
const settlingTable = ref(null)
const settling = ref(false)
const showReceiptDialog = ref(false)
const receiptData = ref(null)
const lastRefreshed = ref('')
const pollFailCount = ref(0)

// 代客加单：只在「记账后付/桌台账」模式下开放——预付模式每单都要在线支付，
// 服务员没法替顾客走支付流程，这个入口对预付商户没有意义。
const paymentMode = ref('')
const canStaffOrder = computed(() => ['postpay', 'table_account'].includes(paymentMode.value))
const staffOrderVisible = ref(false)
const staffOrderTable = ref('')
const staffMenuItems = ref([])
const staffMenuLoading = ref(false)
const staffMenuLoaded = ref(false)
const staffCart = ref({}) // dish_id -> qty
const staffNote = ref('')
const staffPickupNo = ref('')
const staffSubmitting = ref(false)

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

async function openStaffOrder(tableNo) {
  staffOrderTable.value = tableNo || ''
  staffCart.value = {}
  staffNote.value = ''
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
    const res = await createOrder({
      shop: getCurrentTenantId(),
      table: tableNo,
      items,
      total: staffCartTotal.value,
      staff_note: staffNote.value.trim() || undefined,
      pickup_no: staffPickupNo.value.trim() || undefined,
    })
    if (res.code === 200) {
      message.success('已提交，同步到这一桌的账单里了')
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
// 提醒的开关/解锁状态是模块级单例（见 useOrderAlert.js），不是这个组件自己的 ref——
// 后台切 Tab 不带 keep-alive，OrderManage.vue 会被反复卸载重建，状态挂在组件实例上
// 的话，AudioContext 每次都要重新解锁一遍。
const { alertEnabled, audioNeedsUnlock, enableAlert, disableAlert, unlockAudio, ensureAlertProbed, noteNewPendingCount } = useOrderAlert()

async function loadOrders(pollMeta = {}) {
  loading.value = true
  try {
    const res = await getOrders({ date_str: 'today' }, { meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'admin:orders:today:manage' } })
    pollFailCount.value = 0
    const raw = res?.data?.data || res?.data || []
    const uniqueOrders = Array.from(new Map((Array.isArray(raw) ? raw : []).map(o => [String(o.id), o])).values())
    const newPending = uniqueOrders.filter(o => o.status === 'pending').length
    noteNewPendingCount(newPending)
    orders.value = uniqueOrders.map(o => ({
      id: String(o.id),
      table: o.table_no || '-',
      diningSessionId: o.dining_session_id || null,
      checkoutRequestedAt: o.checkout_requested_at || null,
      participantNo: o.participant_no || null,
      status: o.status || 'pending',
      total: Number(o.total || 0),
      discount_amount: o.discount_amount ? Number(o.discount_amount) : null,
      remark: o.remark || '',
      source: o.source || 'miniprogram',
      staffNote: o.staff_note || '',
      pickup_no: o.pickup_no || '',
      printStatus: o.print_status || null,
      createdAt: o.created_at || '',
      time: o.created_at ? new Date(o.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '',
      items: Array.isArray(o.items) ? o.items : [],
      paymentMethodText: paymentMethodText(o.payment_method, o.payment_status),
      updating: false,
      reprinting: false,
    }))
  } catch {
    pollFailCount.value++
  }
  finally {
    loading.value = false
    const now = new Date()
    lastRefreshed.value = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
  }
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
const doneCount = computed(() => orders.value.filter(o => o.status === 'done').length)
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
  { label: '备餐中', value: preparingCount.value, color: '#374151' },
  { label: '待结账', value: doneCount.value, color: '#16a34a' },
  { label: '今日营收', value: '¥' + todayRevenue.value, color: '#07C160' },
])

const statusFilter = ref('')
const statusFilters = [
  { label: '全部', val: '' },
  { label: '待接单', val: 'pending' },
  { label: '备餐中', val: 'preparing' },
  { label: '已完成', val: 'done' },
  { label: '已结账', val: 'settled' },
  { label: '待支付', val: 'pending_payment' },
  { label: '已拒单', val: 'rejected' },
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
  const p = { pending: 0, preparing: 1, done: 2, settled: 3, rejected: 4, cancelled: 5, pending_payment: 6 }
  let list = statusFilter.value
    ? orders.value.filter(o => o.status === statusFilter.value)
    : orders.value.filter(o => o.status !== 'pending_payment')
  const q = searchQuery.value.trim()
  if (q) {
    list = list.filter(o =>
      String(o.table).includes(q) ||
      orderTail(o).includes(q) ||
      o.items.some(item => (item.name || '').includes(q))
    )
  }
  // 状态优先级不变（待接单永远最先看到）；同一优先级内之前是接口原始顺序，现在按
  // 下单时间从早到晚排——不然高峰期同时来好几单待接单，老板看不出该先做哪个。
  return [...list].sort((a, b) => (p[a.status] ?? 9) - (p[b.status] ?? 9) || a.createdAt.localeCompare(b.createdAt))
})

const LIST_PAGE_SIZE = 20
const listVisibleCount = ref(LIST_PAGE_SIZE)
const visibleOrders = computed(() => sortedOrders.value.slice(0, listVisibleCount.value))
watch([statusFilter, searchQuery], () => { listVisibleCount.value = LIST_PAGE_SIZE })

const tableGroups = computed(() => {
  // 按 dining_session_id 分组，而不是按桌号：同一桌当天翻台会产生多个会话，
  // 按桌号分组会把上一批已结账客人的订单和当前这批混在一起，导致结账金额和小票错乱。
  // 没有 dining_session_id 的订单（例如 H5 下单）仍按桌号分组，保持原有展示方式。
  // 待支付订单单独放进 pendingPaymentOrders：它们不计入桌台金额（钱还没收到），
  // 但会挡住结账（后端 settle-table 会拒绝），过去这里直接把它们过滤掉，导致商家在
  // 桌台视图上完全看不到、也不知道该结账的桌子为什么结不了账。
  const map = {}
  for (const o of orders.value) {
    if (['cancelled', 'rejected'].includes(o.status)) continue
    const key = o.diningSessionId ? `session:${o.diningSessionId}` : `table:${o.table}`
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
    canSettle: t.orders.length > 0 && t.orders.every(o => ['done', 'settled'].includes(o.status)) && t.orders.some(o => o.status === 'done') && t.pendingPaymentOrders.length === 0,
    isSettled: t.orders.length > 0 && t.orders.every(o => o.status === 'settled'),
  })).sort((a, b) => {
    const p = t => t.pendingOrders.length ? 0 : t.preparingOrders.length ? 1 : t.canSettle ? 2 : 3
    return p(a) - p(b)
  })
})

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
  if (t.preparingOrders?.length) return '备餐中'
  if (t.canSettle) return t.checkoutRequestedAt ? '顾客催结账 ⏰' : '可结账'
  if (t.isSettled) return '已结账'
  if (t.pendingPaymentOrders?.length) return '有订单待支付'
  return ''
}

function statusLabel(s) {
  return { pending_payment: '待支付', pending: '待接单', preparing: '备餐中', done: '已完成', settled: '已结账', rejected: '已拒单', cancelled: '已取消' }[s] || s
}

// 拼桌时标出"这一单是第几位点的"，跟顾客小程序端用同一套颜色循环，纯展示编号，
// 不关联真实身份——同桌不一定互相认识，不适合亮真实姓名。
const PARTICIPANT_COLORS = ['#07C160', '#FF7D45', '#5B8FF9', '#F5A623', '#B37FEB', '#3ABBB0']
function participantColor(no) {
  if (!no || no < 1) return PARTICIPANT_COLORS[0]
  return PARTICIPANT_COLORS[(no - 1) % PARTICIPANT_COLORS.length]
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
        if (res.code === 200) { order.status = 'cancelled'; message.success('已取消') }
        else message.error(res.msg || '取消失败，请刷新页面重试')
      } catch { message.error('取消失败') }
      finally { order.updating = false }
    },
  })
}

async function acceptOrder(order) {
  order.updating = true
  try {
    const res = await updateOrderStatus(order.id, 'preparing')
    if (res.code === 200) order.status = 'preparing'
    else message.error(res.msg || '操作失败，请刷新页面重试')
  }
  catch { message.error('操作失败') } finally { order.updating = false }
}

// 牌子管的是这一桌这一次吃饭，不是某一单菜：登记接口会把这个号同步给同一个桌台会话下的
// 所有订单，这里把返回的 order_ids 应用回本地列表，同一桌其它订单（包括加单）立刻跟着更新，
// 不用等下一次轮询刷新才看到。
function applyPickupNoToOrders(pickupNo, orderIds) {
  const idSet = new Set((orderIds || []).map(String))
  for (const o of orders.value) {
    if (idSet.has(String(o.id))) {
      o.pickup_no = pickupNo || ''
    }
  }
}

async function sendPickupNo(order, value) {
  if (!value || value === order.pickup_no) return
  try {
    const res = await updateOrderPickupNo(order.id, value)
    if (res.code === 200) {
      applyPickupNoToOrders(res.data.pickup_no, res.data.order_ids)
      message.success('取餐牌号已登记')
    } else message.error(res.msg || '登记失败')
  } catch { message.error('登记失败') }
}

async function sendTablePickupNo(table, value) {
  const anyOrder = table?.orders?.[0]
  if (!value || !anyOrder) return
  try {
    const res = await updateOrderPickupNo(anyOrder.id, value)
    if (res.code === 200) {
      applyPickupNoToOrders(res.data.pickup_no, res.data.order_ids)
      message.success('取餐牌号已登记，这一桌后面加单会自动带上')
    } else message.error(res.msg || '登记失败')
  } catch { message.error('登记失败') }
}

async function rejectOrder(order) {
  order.updating = true
  try {
    const res = await updateOrderStatus(order.id, 'rejected')
    if (res.code === 200) {
      order.status = 'rejected'
      message.warning('已拒单，请联系顾客说明原因')
    } else message.error(res.msg || '操作失败，请刷新页面重试')
  }
  catch { message.error('操作失败') } finally { order.updating = false }
}

async function finishOrder(order) {
  order.updating = true
  try {
    const res = await updateOrderStatus(order.id, 'done')
    if (res.code === 200) order.status = 'done'
    else message.error(res.msg || '操作失败，请刷新页面重试')
  }
  catch { message.error('操作失败') } finally { order.updating = false }
}

async function reprintOrderTicket(order) {
  order.reprinting = true
  try {
    const res = await reprintOrder(order.id)
    if (res.code === 200) {
      order.printStatus = res.data?.print_status || null
      if (order.printStatus === 'printed') message.success('已重新打印')
      else message.warning('打印结果仍未知，请核实小票机是否已出票')
    } else {
      message.error(res.msg || '补打失败')
    }
  } catch { message.error('补打失败') } finally { order.reprinting = false }
}

async function acceptTableOrders(table) {
  table.updating = true
  try {
    for (const o of table.pendingOrders) {
      const res = await updateOrderStatus(o.id, 'preparing')
      if (res.code === 200) o.status = 'preparing'
      else { message.error(res.msg || '操作失败，请刷新页面重试'); break }
    }
  } catch { message.error('操作失败') } finally { table.updating = false }
}

async function finishTableOrders(table) {
  table.updating = true
  try {
    for (const o of table.preparingOrders) {
      const res = await updateOrderStatus(o.id, 'done')
      if (res.code === 200) o.status = 'done'
      else { message.error(res.msg || '操作失败，请刷新页面重试'); break }
    }
  } catch { message.error('操作失败') } finally { table.updating = false }
}

function settleTableClick(table) { settlingTable.value = table; showSettleDialog.value = true }

async function confirmSettle() {
  if (!settlingTable.value) return
  settling.value = true
  try {
    const res = await settleTable(settlingTable.value.tableNo)
    if (res.code !== 200) {
      const statuses = res.data?.blocking_statuses
      const detail = Array.isArray(statuses) && statuses.length ? `（${statuses.map(statusLabel).join('、')}）` : ''
      message.error(`${res.msg || '结账失败'}${detail}`)
      return
    }
    const table = settlingTable.value
    for (const o of table.orders) o.status = 'settled'
    showSettleDialog.value = false
    const now = new Date()
    receiptData.value = {
      tableNo: table.tableNo,
      settledAt: `${now.getFullYear()}/${now.getMonth()+1}/${now.getDate()} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`,
      total: table.total.toFixed(2),
      orders: table.orders.map(o => ({ id: o.id, items: o.items, discount_amount: o.discount_amount })),
    }
    showReceiptDialog.value = true
  } catch { message.error('结账失败，请重试') }
  finally { settling.value = false }
}


onMounted(async () => {
  // 先单独查一次付款模式，再并发拉订单/评价——这两类接口目前对"是否记账/桌台账模式"
  // 的租户身份解析方式不一样，混在同一批并发请求里偶发会互相打架导致查错商户，
  // 拆开顺序请求可以避开这个问题。
  await loadPaymentMode()
  loadOrders()
  loadReviews()
  pollingManager.start('orders:today', {
    task: loadOrders,
    interval: 5000,
    hiddenInterval: 30000,
    idleInterval: 30000,
    immediate: false,
  })
  // 探测一次 AudioContext 是不是被浏览器挂起了；具体的"只探测一次"逻辑在
  // useOrderAlert.js 里，这里每次挂载都调用没关系，真正解锁过之后它自己会跳过。
  ensureAlertProbed()
})
onBeforeUnmount(() => {
  pollingManager.stop('orders:today')
})
</script>

<style scoped>
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







