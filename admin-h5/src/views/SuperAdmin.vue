<template>
  <div class="super-wrap">
    <div v-if="!authed" class="login-box">
      <div class="login-card animate-in">
        <div class="login-hero">
          <div class="login-logo">中控</div>
          <div class="login-title">平台中控台</div>
          <div class="login-sub">OPERATOR CONSOLE</div>
        </div>
        <div class="login-form">
          <input v-if="!needTotp" v-model="pwd" type="password" class="login-input" placeholder="输入管理密码" @keyup.enter="doLogin" />
          <template v-else>
            <div class="totp-hint">请输入认证器 App 里的 6 位动态口令</div>
            <input v-model="totpCode" type="text" inputmode="numeric" maxlength="6" class="login-input" placeholder="6位动态口令" @keyup.enter="doLogin" />
          </template>
          <button class="login-btn tap-shrink" :disabled="logging || (!needTotp && !pwd.trim()) || (needTotp && !totpCode.trim())" @click="doLogin">{{ logging ? '登录中...' : (needTotp ? '验证' : '登录') }}</button>
          <div v-if="loginErr" class="login-err">{{ loginErr }}</div>
        </div>
      </div>
    </div>

    <SuperAdminShell v-else :pending-count="pendingPaymentCount" @logout="logout">
      <template v-if="isDetail">
        <div class="merchant-context">
          <button class="back-link tap-shrink" @click="backToMerchants">返回商户列表</button>

          <div v-if="detailLoading && !detail" class="section">
            <div class="context-kicker">正在打开商户</div>
            <div class="context-name">{{ route.params.tenantId }}</div>
            <div class="loading">加载中...</div>
          </div>
          <div v-else-if="!detail" class="section">
            <div class="context-kicker">商户</div>
            <div class="context-name">{{ route.params.tenantId }}</div>
            <div class="empty error-state">
              <div>{{ detailError || '商户信息加载失败' }}</div>
              <button class="refresh-btn tap-shrink" @click="loadMerchantDetail(false)">重试</button>
            </div>
          </div>
          <template v-else>
            <div class="merchant-context-head section">
              <div class="context-kicker">当前商户</div>
              <div class="context-name">{{ detail.tenant.name || '未命名商户' }}</div>
              <div class="context-pills">
                <span class="mc-badge" :class="detail.tenant.status ? 'on' : 'off'">账号：{{ detail.tenant.status ? '启用' : '已停用' }}</span>
                <span class="mc-pay-badge" :class="statusClass(paymentStatusOf(detail))">收款：{{ statusText(paymentStatusOf(detail)) }}</span>
                <span class="mc-badge" :class="displaySubscription?.load_error ? 'off' : 'on'">套餐：{{ subscriptionLabel(displaySubscription) }}</span>
              </div>
              <div class="context-meta">Tenant ID <span class="tenant-id">{{ detail.tenant.tenant_id }}</span></div>
              <div class="context-meta">
                手机号
                <span class="phone-reveal tap-shrink" @click="togglePhone(detail.tenant.tenant_id)">{{ revealedPhones.has(detail.tenant.tenant_id) ? (detail.tenant.phone || '-') : (detail.tenant.phone_masked || maskPhone(detail.tenant.phone)) }}</span>
              </div>
              <div class="context-meta">注册时间 {{ detail.tenant.created_at || '未记录' }}</div>
              <div v-if="detailError" class="create-result err">{{ detailError }}</div>
            </div>

            <div class="detail-tabs">
              <button class="filter-chip tap-shrink" :class="{ active: detailSection === 'overview' }" @click="setDetailSection('overview')">概览</button>
              <button class="filter-chip tap-shrink" :class="{ active: detailSection === 'payment' }" @click="setDetailSection('payment')">收款</button>
              <button class="filter-chip tap-shrink" :class="{ active: detailSection === 'subscription' }" @click="setDetailSection('subscription')">订阅与付款</button>
              <button class="filter-chip tap-shrink" :class="{ active: detailSection === 'channel' }" @click="setDetailSection('channel')">渠道归属</button>
            </div>

            <div v-if="detailSection === 'overview'" class="section">
              <div class="section-title">平台状态</div>
              <div class="fact-list">
                <div class="fact-row"><span>账号状态</span><strong>{{ detail.tenant.status ? '账号启用' : '账号已停用' }}</strong></div>
                <div class="fact-row"><span>收款状态</span><strong>{{ statusText(paymentStatusOf(detail)) }}</strong></div>
                <div class="fact-row">
                  <span>套餐状态</span>
                  <strong v-if="!displaySubscription?.load_error">{{ subscriptionLabel(displaySubscription) }}</strong>
                  <strong v-else>套餐信息加载失败 <button class="text-link tap-shrink" @click="loadMerchantDetail(true)">重试</button></strong>
                </div>
                <div class="fact-row"><span>到期时间</span><strong>{{ expiryLabel(displaySubscription) }}</strong></div>
                <div class="fact-row"><span>渠道来源</span><strong>{{ channelLabel(detail.channel) }}</strong></div>
                <div class="fact-row">
                  <span>今日订单</span>
                  <strong v-if="!detail.operations?.load_error">{{ detail.operations?.today_order_count ?? 0 }} 单</strong>
                  <strong v-else>今日订单加载失败 <button class="text-link tap-shrink" @click="loadMerchantDetail(true)">重试</button></strong>
                </div>
                <div class="fact-row"><span>注册时间</span><strong>{{ detail.tenant.created_at || '未记录' }}</strong></div>
              </div>

              <div class="danger-zone">
                <div class="danger-zone-label">危险操作 · {{ detail.tenant.name || '该商户' }}</div>
                <div class="danger-ops-actions">
                  <button
                    class="toggle-btn tap-shrink"
                    :class="detail.tenant.status ? 'stop' : 'resume'"
                    :disabled="rowBusy(detail.tenant.tenant_id)"
                    @click="confirmToggleStatus(detail.tenant)"
                  >{{ statusButtonText(detail.tenant) }}</button>
                  <button class="more-btn tap-shrink" @click="detailSeedOpen = !detailSeedOpen">{{ detailSeedOpen ? '收起' : '更多' }}</button>
                </div>
                <div v-if="detailSeedOpen" class="seed-block">
                  <div class="seed-hint">测试 / 开发辅助。没有订单的商户会先被清掉菜单、会员、入口码和优惠券模板，再写入演示数据。</div>
                  <button class="seed-btn tap-shrink" :disabled="rowBusy(detail.tenant.tenant_id)" @click="seedTestData(detail.tenant)">{{ seedingId === detail.tenant.tenant_id ? '填充中...' : '填充测试数据' }}</button>
                </div>
                <div v-if="statusResult && statusResult.tenant_id === detail.tenant.tenant_id" class="create-result" :class="statusResult.ok ? 'ok' : 'err'">{{ statusResult.msg }}</div>
                <div v-if="seedResult && seedResult.tenant_id === detail.tenant.tenant_id" class="create-result" :class="seedResult.ok ? 'ok' : 'err'">{{ seedResult.msg }}</div>
              </div>
            </div>

            <div v-else-if="detailSection === 'payment'" class="section">
              <div class="section-title">微信支付收款 — {{ detail.tenant.name }}</div>
              <div v-if="paymentStatusOf(detail) === 'unconfigured'" class="empty">尚未配置微信支付收款</div>
              <div v-else class="fact-list">
                <div class="fact-row"><span>收款状态</span><strong>{{ statusText(paymentStatusOf(detail)) }}</strong></div>
                <div class="fact-row"><span>微信商户号</span><strong>{{ detail.payment?.merchant_no_masked || detail.payment?.wx_mchid_masked || '-' }}</strong></div>
                <div class="fact-row"><span>收款账户</span><strong>{{ detail.payment?.locked || detail.payment?.payment_locked ? '已锁定' : '未锁定' }}</strong></div>
                <div class="fact-row"><span>最后验证时间</span><strong>{{ detail.payment?.verified_time || '未验证' }}</strong></div>
              </div>
              <button class="create-btn tap-shrink pay-open-btn" @click="openPayConfig(payMerchantFromDetail())">打开收款配置</button>
            </div>

            <div v-else-if="detailSection === 'subscription'" class="section">
              <div class="section-title">当前套餐</div>
              <div v-if="detail.subscription?.load_error" class="empty error-state">
                <div>套餐信息加载失败</div>
                <button class="refresh-btn tap-shrink" @click="loadMerchantDetail(true)">重试</button>
              </div>
              <div v-else class="fact-list">
                <div class="fact-row"><span>当前套餐</span><strong>{{ displaySubscription?.plan_name || '免费版' }}</strong></div>
                <div class="fact-row"><span>状态</span><strong>{{ subscriptionDomainStatus(displaySubscription) }}</strong></div>
                <div class="fact-row"><span>开始时间</span><strong>{{ displayDate(displaySubscription?.started_at) }}</strong></div>
                <div class="fact-row"><span>到期时间</span><strong>{{ displayDateTime(displaySubscription?.expires_at) }}</strong></div>
                <div class="fact-row"><span>剩余时间</span><strong>{{ subscriptionRemainingText(displaySubscription) }}</strong></div>
                <div class="fact-row"><span>试用</span><strong>{{ displaySubscription?.is_trial ? '试用中' : '不是试用' }}</strong></div>
              </div>

              <SubscriptionAdjustmentModal
                :super-token="superToken"
                :tenant-id="detail.tenant.tenant_id"
                :merchant-name="detail.tenant.name"
                :context="detail.subscription_adjustment"
                @committed="refreshDetailAfterAdjustment"
                @auth-expired="logout"
              />

              <div class="section-title bill-title">付款记录</div>
              <div v-if="invoicesLoading" class="loading">加载中...</div>
              <div v-else-if="invoicesError" class="empty error-state">
                <div>付款记录加载失败</div>
                <button class="refresh-btn tap-shrink" @click="loadInvoices(true)">重试</button>
              </div>
              <div v-else-if="!invoices.length" class="empty">尚无付款记录</div>
              <div v-else class="bill-list">
                <div v-for="invoice in invoices" :key="invoice.id" class="bill-row">
                  <div class="bill-main">
                    <div class="bill-name">{{ invoiceTitle(invoice) }}</div>
                    <div class="bill-meta">{{ invoice.invoice_no }} · {{ invoiceStatusText(invoice.status) }}</div>
                    <div class="bill-meta">创建 {{ displayDateTime(invoice.created_at) }}<template v-if="invoice.paid_at"> · 支付 {{ displayDateTime(invoice.paid_at) }}</template></div>
                  </div>
                  <div class="bill-amount">{{ formatYuan(invoice.amount_cents) }}</div>
                </div>
              </div>
            </div>

            <div v-else class="section">
              <div class="section-title">渠道归属</div>
              <div v-if="detail.channel?.load_error" class="empty error-state">
                <div>渠道信息加载失败</div>
                <button class="refresh-btn tap-shrink" @click="loadMerchantDetail(true)">重试</button>
              </div>
              <div v-else-if="!detail.channel?.bound" class="empty">尚未绑定渠道伙伴</div>
              <div v-else class="fact-list">
                <div class="fact-row">
                  <span>渠道伙伴</span>
                  <strong>
                    <button class="text-link tap-shrink" @click="openChannelPartner(detail.channel.partner_id)">{{ detail.channel.partner_name || '渠道伙伴资料缺失' }}</button>
                  </strong>
                </div>
                <div class="fact-row"><span>绑定状态</span><strong>{{ bindingStatusText(detail.channel.binding_status) }}</strong></div>
                <div class="fact-row"><span>佣金比例</span><strong>{{ commissionText(detail.channel.commission_rate_bps) }}</strong></div>
                <div class="fact-row"><span>归属开始</span><strong>{{ displayDate(detail.channel.started_at) }}</strong></div>
                <div class="fact-row"><span>归属结束</span><strong>{{ displayDate(detail.channel.ends_at) }}</strong></div>
                <div v-if="detail.channel.commission_term_months != null" class="fact-row"><span>佣金期限</span><strong>{{ detail.channel.commission_term_months }} 个月</strong></div>
              </div>
            </div>
          </template>
        </div>
      </template>

      <template v-else-if="currentPage === 'overview'">
        <div class="super-page-header animate-in">
          <div>
            <h1>平台总览</h1>
            <p>先处理影响商户开通、收款和平台使用的问题。</p>
          </div>
        </div>

        <div v-if="overviewError" class="section overview-alert">
          <span>{{ overviewError }}</span>
          <button class="refresh-btn tap-shrink" @click="loadOverview(true)">重新加载</button>
        </div>

        <section class="section animate-in" aria-labelledby="action-title">
          <div id="action-title" class="section-title title-row">
            <span>需要处理</span>
            <button class="refresh-btn tap-shrink" :disabled="overviewLoading" @click="loadOverview(true)">{{ overviewLoading ? '刷新中...' : '刷新' }}</button>
          </div>
          <div class="action-grid">
            <button class="action-card" @click="router.push('/super/billing/pending')">
              <span>待确认付款</span><strong>{{ pendingCountLoaded ? pendingPaymentCount : '—' }}</strong><small>进入付款核对</small>
            </button>
            <button class="action-card" @click="openMerchantFilter('pending')">
              <span>支付待验证</span><strong>{{ merchantsLoaded ? paymentPendingVerifyCount : '—' }}</strong><small>查看商户</small>
            </button>
            <button class="action-card" @click="openMerchantFilter('unconfigured')">
              <span>支付未配置</span><strong>{{ merchantsLoaded ? paymentUnconfiguredCount : '—' }}</strong><small>查看商户</small>
            </button>
            <button class="action-card" @click="openMerchantFilter('', 'disabled')">
              <span>已停用商户</span><strong>{{ merchantsLoaded ? disabledMerchantCount : '—' }}</strong><small>查看商户</small>
            </button>
          </div>
        </section>

        <section class="section animate-in" aria-labelledby="metrics-title">
          <div id="metrics-title" class="section-title">经营辅助数据</div>
          <div class="stat-row overview-stats">
            <div class="stat-card"><div class="stat-num">{{ statsLoaded ? stats.total_merchants : '—' }}</div><div class="stat-label">商户总数</div></div>
            <div class="stat-card"><div class="stat-num blue">{{ statsLoaded ? stats.today_orders : '—' }}</div><div class="stat-label">今日商户订单</div></div>
            <div class="stat-card"><div class="stat-num">{{ statsLoaded ? `¥${Number(stats.today_revenue || 0).toFixed(0)}` : '—' }}</div><div class="stat-label">今日商户餐饮交易额</div></div>
          </div>
          <div class="metric-note">餐饮交易额来自商户经营流水，不代表开心点单 SaaS 收入。</div>
        </section>
      </template>

      <template v-else-if="currentPage === 'merchant-create'">
        <div class="super-page-header animate-in">
          <div>
            <button class="back-link header-back" @click="router.push('/super/merchants')">返回商户列表</button>
            <h1>开通商户</h1>
            <p>创建一家新的商户账号。开通后，商家使用手机号和短信验证码登录。</p>
          </div>
        </div>
        <div class="section form-section animate-in">
          <div class="create-form">
            <input v-model="newMerchant.name" class="form-input" placeholder="* 商户名称" />
            <input v-model="newMerchant.phone" class="form-input" placeholder="* 手机号（登录账号）" maxlength="11" />
            <button class="create-btn tap-shrink" :disabled="creating" @click="createMerchant">{{ creating ? '创建中...' : '确认开通' }}</button>
          </div>
          <div v-if="createResult" class="create-result" :class="createResult.ok ? 'ok' : 'err'">{{ createResult.msg }}</div>
        </div>
      </template>

      <template v-else-if="currentPage === 'performance'">
        <div class="super-page-header animate-in">
          <div>
            <h1>性能</h1>
            <p>查看开心点单平台运行指标，不是商户经营数据。</p>
          </div>
        </div>
        <div class="section animate-in">
          <div class="section-title title-row">
            <span>性能采样（P50 / P95）</span>
            <button class="refresh-btn tap-shrink" :disabled="perfStatsLoading" @click="loadPerfStats(true)">{{ perfStatsLoading ? '刷新中...' : '刷新' }}</button>
          </div>
        <div v-if="perfStatsLoading" class="loading">加载中...</div>
        <div v-else-if="perfStatsError" class="empty error-state">
          <div>性能采样加载失败</div>
          <button class="refresh-btn tap-shrink" @click="loadPerfStats(true)">重新加载</button>
        </div>
        <div v-else-if="!perfStats.length" class="empty">暂无采样数据</div>
        <div v-else class="perf-table-scroll">
          <table class="perf-table">
            <thead>
              <tr>
                <th>指标</th>
                <th class="num">样本数</th>
                <th class="num">均值</th>
                <th class="num">P50</th>
                <th class="num">P95</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in perfStats" :key="row.metric">
                <td>{{ row.metric }}</td>
                <td class="num">{{ row.count }}</td>
                <td class="num">{{ row.avg }} ms</td>
                <td class="num">{{ row.p50 }} ms</td>
                <td class="num">{{ row.p95 }} ms</td>
              </tr>
            </tbody>
          </table>
        </div>
        </div>
      </template>

      <template v-else-if="currentPage === 'merchant-list'">
        <div class="super-page-header animate-in">
          <div>
            <h1>商户</h1>
            <p>管理开心点单平台中的商户账号、收款和订阅状态。</p>
          </div>
          <button class="primary-action tap-shrink" @click="router.push('/super/merchants/new')">开通商户</button>
        </div>

        <MerchantList
          :merchants="merchants"
          :loading="loadingList"
          :error="merchantListError"
          :danger-open-id="dangerOpenId"
          :status-busy-id="statusBusyId"
          :seeding-id="seedingId"
          :status-result="statusResult"
          :seed-result="seedResult"
          @refresh="loadMerchants(true)"
          @create="router.push('/super/merchants/new')"
          @open="openMerchant"
          @pay-config="openPayConfig"
          @toggle-danger="toggleDanger"
          @toggle-status="confirmToggleStatus"
          @seed="seedTestData"
        />
      </template>

      <template v-else-if="currentPage === 'billing'">
        <div class="super-page-header animate-in">
          <div>
            <h1>待确认付款</h1>
            <p>核对商户提交的 SaaS 套餐付款，只按真实到账结果确认。</p>
          </div>
        </div>
        <ManualPaymentPanel :super-token="superToken" @update:count="handlePendingCount" />
      </template>

      <template v-else-if="currentPage === 'channels'">
        <div class="super-page-header animate-in">
          <div>
            <h1>渠道伙伴</h1>
            <p>维护平台真实渠道伙伴；商户归属、佣金与结算工作流本阶段不扩张。</p>
          </div>
        </div>
        <ChannelPartnerPanel :super-token="superToken" :highlight-partner-id="channelPartnerFocus" />
      </template>
    </SuperAdminShell>

    <div v-if="payConfigTarget" class="modal-mask" @click.self="closePayConfig">
      <div class="modal-box animate-in">
        <div class="modal-title">微信支付收款 — {{ payConfigTarget.name }}</div>

        <div class="receiver-card">
          <div class="receiver-head">
            <div>
              <div class="receiver-kicker">收款安全</div>
              <div class="receiver-title">钱进入商家自己的微信商户号</div>
            </div>
            <span class="status-pill" :class="statusClass(payConfigForm.payment_status)">{{ statusText(payConfigForm.payment_status) }}</span>
          </div>
          <div class="receiver-grid">
            <div><span>收款主体</span><strong>{{ payConfigForm.receiver_name || payConfigTarget.name || '-' }}</strong></div>
            <div><span>微信支付商户号</span><strong>{{ payConfigForm.wx_mchid_masked || maskMchid(payConfigForm.wx_mchid) }}</strong></div>
            <div><span>开户类型</span><strong>{{ receiverTypeText(payConfigForm.receiver_type) }}</strong></div>
            <div><span>最后验证时间</span><strong>{{ payConfigForm.verified_time || '未验证' }}</strong></div>
            <div><span>收款账户锁定状态</span><strong class="lock-text">{{ payConfigForm.payment_locked ? '已锁定' : '未锁定' }}</strong></div>
          </div>
          <div class="safe-tip">平台不能在锁定后把收款商户号改成其他账户；商家后台仅展示收款信息，不展示密钥和私钥。</div>
        </div>

        <button class="fold-btn tap-shrink" @click="techOpen = !techOpen">{{ techOpen ? '收起技术配置' : '展开技术配置（平台管理员）' }}</button>
        <div v-if="techOpen" class="tech-box animate-in">
          <div v-if="copySources.length" class="copy-box">
            <div class="modal-label">从其它商户复制配置</div>
            <div class="field-hint">已验证过的商户可以直接复制过来，不用逐字段重新抄一遍</div>
            <div class="copy-row">
              <select v-model="copySourceId" class="form-input copy-select">
                <option value="">选择源商户...</option>
                <option v-for="s in copySources" :key="s.tenant_id" :value="s.tenant_id">{{ s.name }}（{{ statusText(s.payment_status) }}）</option>
              </select>
              <button class="copy-btn tap-shrink" :disabled="!copySourceId || copyingPay" @click="confirmCopyPayConfig">{{ copyingPay ? '复制中...' : '复制' }}</button>
            </div>
          </div>
          <div class="modal-label">收款主体</div>
          <input v-model="payConfigForm.receiver_name" class="form-input" placeholder="自动读取失败时可填商户主体名称" />
          <div class="modal-label">开户类型</div>
          <div class="pay-radio-row">
            <button class="pay-radio-btn tap-shrink" :class="payConfigForm.receiver_type === 'enterprise' ? 'selected' : ''" @click="payConfigForm.receiver_type = 'enterprise'">企业</button>
            <button class="pay-radio-btn tap-shrink" :class="payConfigForm.receiver_type === 'individual' ? 'selected' : ''" @click="payConfigForm.receiver_type = 'individual'">个体</button>
          </div>
          <div class="modal-label">商户号</div>
          <div class="field-hint">商户平台首页右上角，或「账户中心 → 商户信息」可查看</div>
          <input v-model="payConfigForm.wx_mchid" class="form-input" placeholder="商家微信支付商户号" :disabled="payConfigForm.payment_locked && !!payConfigTarget.wx_mchid" />
          <div class="modal-label">APIv3 密钥</div>
          <div class="field-hint">「账户中心 → API安全 → 设置/重置 APIv3 密钥」；这是自己设定的 32 位密钥，忘记了要在那里重置</div>
          <input v-model="payConfigForm.wx_api_key_v3" class="form-input" placeholder="32位 APIv3 密钥" />
          <div class="modal-label">证书序列号</div>
          <div class="field-hint">「账户中心 → API安全 → API证书」，证书详情页可见</div>
          <input v-model="payConfigForm.wx_cert_serial" class="form-input" placeholder="证书序列号" />
          <div class="modal-label">私钥</div>
          <div class="field-hint">申请 API 证书后下载的压缩包里，apiclient_key.pem 文件的全部内容</div>
          <textarea v-model="payConfigForm.wx_private_key" class="form-input private-input" rows="6" placeholder="粘贴 apiclient_key.pem 内容（商户私钥，用于请求签名）" />
          <div class="modal-label">微信支付公钥ID</div>
          <div class="field-hint">「账户中心 → API安全 → 微信支付公钥」，下载后可见</div>
          <input v-model="payConfigForm.wx_public_key_id" class="form-input" placeholder="微信支付公钥ID（从商户平台获取）" />
          <div class="modal-label">微信支付公钥</div>
          <div class="field-hint">同样在「账户中心 → API安全 → 微信支付公钥」下载获取</div>
          <textarea v-model="payConfigForm.wx_public_key" class="form-input private-input" rows="6" placeholder="粘贴微信支付公钥内容（用于验证回调签名）" />
        </div>

        <div v-if="payConfigResult" class="create-result" :class="payConfigResult.ok ? 'ok' : 'err'">{{ payConfigResult.msg }}</div>
        <div class="modal-actions">
          <button class="create-btn tap-shrink" :disabled="savingPay" @click="savePayConfig">{{ savingPay ? '保存中...' : '保存' }}</button>
          <button class="verify-btn tap-shrink" :class="{ 'verify-btn--pending': payConfigTarget.wx_mchid && !payConfigForm.receiver_verified }" :disabled="verifyingPay || !payConfigTarget.wx_mchid" @click="verifyPayConfig">{{ verifyingPay ? '验证中...' : '验证配置' }}</button>
        </div>
        <button class="cancel-btn tap-shrink" @click="closePayConfig">关闭</button>

        <div class="danger-zone">
          <div class="danger-zone-label">危险操作</div>
          <button class="pause-btn tap-shrink" :disabled="pausingPay || !payConfigTarget.wx_mchid" @click="confirmPausePay">{{ pausingPay ? '暂停中...' : '暂停支付' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listBillingInvoices, listManualPayments } from '../api/superBilling'
import superRequest from '../api/superRequest'
import { getSuperSessionToken, setSuperSessionToken } from '../api/superSession'
import { formatBeijingDate, formatBeijingDateTime } from '../utils/beijingTime'
import { formatYuan, planDisplayName } from '../utils/subscriptionUi'
import ChannelPartnerPanel from './super/ChannelPartnerPanel.vue'
import ManualPaymentPanel from './super/ManualPaymentPanel.vue'
import MerchantList from './super/MerchantList.vue'
import SuperAdminShell from './super/SuperAdminShell.vue'
import SubscriptionAdjustmentModal from './super/SubscriptionAdjustmentModal.vue'
import {
  channelLabel,
  expiryLabel,
  maskPhone,
  statusClass,
  statusText,
  subscriptionLabel,
} from './super/merchantListModel'

const BASE = '/super'

const authed = ref(false)
const pwd = ref('')
const logging = ref(false)
const loginErr = ref('')
const needTotp = ref(false)
const totpCode = ref('')
const totpEnabled = ref(false)
let superToken = ''
superToken = getSuperSessionToken()
if (superToken) authed.value = true
const pendingPaymentCount = ref(0)
const pendingCountLoaded = ref(false)
const pendingCountError = ref('')
const route = useRoute()
const router = useRouter()
const isDetail = computed(() => route.name === 'SuperMerchantDetail' && !!route.params.tenantId)
const currentPage = computed(() => ({
  SuperOverview: 'overview',
  SuperMerchantList: 'merchant-list',
  SuperMerchantCreate: 'merchant-create',
  SuperBillingPending: 'billing',
  SuperChannels: 'channels',
  SuperSystemPerformance: 'performance',
}[route.name] || 'overview'))
const channelPartnerFocus = computed(() => String(route.query.partner || ''))
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const detailSection = ref('overview')
const detailSeedOpen = ref(false)
const invoices = ref([])
const invoicesLoading = ref(false)
const invoicesError = ref('')
const invoicesTenantId = ref('')
const invoicesLoaded = ref(false)

const stats = reactive({ total_merchants: 0, active_merchants: 0, today_orders: 0, today_revenue: 0 })
const merchants = ref([])
const loadingList = ref(false)
const merchantsLoaded = ref(false)
const merchantListError = ref('')
const newMerchant = reactive({ name: '', phone: '', initial_code: '123456' })
const creating = ref(false)
const createResult = ref(null)
const payConfigTarget = ref(null)
const techOpen = ref(false)
const payConfigForm = reactive({
  wx_mchid: '', wx_mchid_masked: '', wx_api_key_v3: '', wx_cert_serial: '', wx_private_key: '', wx_public_key_id: '', wx_public_key: '', wx_pay_enabled: true,
  receiver_name: '', receiver_type: 'enterprise', receiver_verified: false, payment_locked: true, payment_status: 'unconfigured', verified_time: '',
})
const savingPay = ref(false)
const verifyingPay = ref(false)
const pausingPay = ref(false)
const payConfigResult = ref(null)
const seedingId = ref('')
const seedResult = ref(null)
const statusBusyId = ref('')
const statusResult = ref(null)
const dangerOpenId = ref('')
const perfStats = ref([])
const perfStatsLoading = ref(false)
const perfStatsError = ref(false)
const perfStatsLoaded = ref(false)
const statsLoading = ref(false)
const statsLoaded = ref(false)
const statsError = ref('')
const revealedPhones = reactive(new Set())
const copySourceId = ref('')
const copyingPay = ref(false)

const copySources = computed(() => merchants.value.filter(m =>
  m.tenant_id !== payConfigTarget.value?.tenant_id && m.wx_mchid_masked && m.wx_mchid_masked !== '-'
))
const paymentUnconfiguredCount = computed(() => merchants.value.filter(item => (item.payment_status || 'unconfigured') === 'unconfigured').length)
const paymentPendingVerifyCount = computed(() => merchants.value.filter(item => item.payment_status === 'pending').length)
const disabledMerchantCount = computed(() => merchants.value.filter(item => !item.status).length)
const overviewLoading = computed(() => statsLoading.value || loadingList.value)
const overviewError = computed(() => statsError.value || merchantListError.value || pendingCountError.value)
const displaySubscription = computed(() => {
  const current = detail.value?.subscription
  const context = detail.value?.subscription_adjustment
  if (!context?.adjustable || !context.natural_expiry_recovery) return current
  return {
    ...current,
    plan_code: context.plan_code,
    plan_name: context.plan_name,
    status: 'EXPIRED',
    is_trial: context.stored_status === 'TRIAL',
    started_at: context.started_at,
    expires_at: context.expires_at,
    days_remaining: context.days_remaining,
    load_error: false,
  }
})

function superHeaders() { return { 'X-Super-Token': superToken } }
function rememberToken(value) {
  superToken = value || ''
  setSuperSessionToken(superToken)
}
function normalizeSection(section) {
  return ['overview', 'payment', 'subscription', 'channel'].includes(section) ? section : 'overview'
}
function applyRoute() {
  if (isDetail.value) {
    detailSection.value = normalizeSection(route.query.section)
    return
  }
  if (route.name === 'SuperOverview' && route.query.tab === 'billing') router.replace('/super/billing/pending')
  else if (route.name === 'SuperOverview' && route.query.tab === 'channel') router.replace({ path: '/super/channels', query: route.query.partner ? { partner: route.query.partner } : {} })
  else if (route.name === 'SuperOverview' && route.query.tab === 'merchants') router.replace('/super/merchants')
}
function paymentStatusOf(payload) {
  return payload?.payment?.status || payload?.payment?.payment_status || 'unconfigured'
}
function displayDate(value) {
  if (!value) return '未记录'
  return formatBeijingDate(value) || '未记录'
}
function displayDateTime(value) {
  if (!value) return '未记录'
  return formatBeijingDateTime(value) || '未记录'
}
function subscriptionDomainStatus(subscription) {
  if (!subscription || subscription.load_error) return '加载失败'
  if (subscription.status === 'TRIAL' || subscription.is_trial) return '试用中'
  if (subscription.status === 'ACTIVE') return '生效中'
  if (subscription.status === 'EXPIRED') return '已到期'
  if (subscription.status === 'CANCELLED') return '已取消'
  if (subscription.status === 'FREE') return '免费版'
  return '状态待确认'
}
function subscriptionRemainingText(subscription) {
  if (!subscription?.expires_at || typeof subscription.days_remaining !== 'number') return '—'
  return subscription.days_remaining > 0 ? `${subscription.days_remaining} 天` : '已到期'
}
function bindingStatusText(status) {
  if (status === 'ACTIVE') return '生效中'
  if (!status) return '未记录'
  return '未生效'
}
function commissionText(bps) {
  if (bps === null || bps === undefined || bps === '') return '未记录'
  const rate = Number(bps)
  if (!Number.isFinite(rate)) return '未记录'
  const percent = rate / 100
  return Number.isInteger(percent) ? `${percent}%` : `${percent.toFixed(2)}%`
}
function invoiceStatusText(status) {
  return {
    PENDING: '待支付',
    PAID: '已支付',
    CANCELLED: '已取消',
    EXPIRED: '已过期',
    REFUNDED: '已退款',
    PARTIALLY_REFUNDED: '部分退款',
  }[status] || '状态待确认'
}
function invoiceTitle(invoice) {
  const plan = planDisplayName(invoice?.plan_code)
  const period = invoice?.billing_period === 'YEAR' ? '年付' : invoice?.billing_period === 'MONTH' ? '月付' : ''
  if (plan) return period ? `${plan} · ${period}` : plan
  return invoice?.description || '套餐账单'
}
function receiverTypeText(type) { return type === 'individual' ? '个体' : '企业' }
function maskMchid(value) {
  const v = (value || '').trim()
  if (!v) return '-'
  if (v.length <= 6) return v
  return `${v.slice(0, 3)}****${v.slice(-3)}`
}
function togglePhone(tenantId) {
  if (revealedPhones.has(tenantId)) revealedPhones.delete(tenantId)
  else revealedPhones.add(tenantId)
}
function applyPaymentData(target, data) {
  if (!data) return
  Object.assign(target, {
    wx_mchid: data.wx_mchid ?? target.wx_mchid,
    wx_mchid_masked: data.wx_mchid_masked ?? maskMchid(data.wx_mchid ?? target.wx_mchid),
    wx_pay_enabled: data.wx_pay_enabled ?? target.wx_pay_enabled,
    receiver_name: data.receiver_name ?? target.receiver_name,
    receiver_type: data.receiver_type ?? target.receiver_type,
    receiver_verified: data.receiver_verified ?? target.receiver_verified,
    payment_locked: data.payment_locked ?? target.payment_locked,
    payment_status: data.payment_status ?? target.payment_status,
    verified_time: data.verified_time ?? target.verified_time,
  })
}
function closePayConfig() { payConfigTarget.value = null }

async function doLogin() {
  if (!needTotp.value && !pwd.value.trim()) return
  if (needTotp.value && !totpCode.value.trim()) return
  logging.value = true
  loginErr.value = ''
  try {
    const res = await superRequest.post(`${BASE}/login`, { password: pwd.value, totp_code: totpCode.value.trim() || undefined })
    if (res.data?.code === 200) {
      rememberToken(res.data.data.token)
      totpEnabled.value = !!res.data.data.totp_enabled
      authed.value = true
      if (isDetail.value) {
        loadMerchantDetail(false)
        loadPendingPaymentCount(false)
      } else loadCurrentPage(false)
    } else if (res.data?.data?.require_totp) {
      needTotp.value = true
      totpCode.value = ''
      loginErr.value = res.data?.msg || '请输入动态口令'
    } else {
      needTotp.value = false
      totpCode.value = ''
      loginErr.value = res.data?.msg || '登录失败'
    }
  } catch { loginErr.value = '网络错误，请重试' }
  finally { logging.value = false }
}

async function loadPerfStats(force = false) {
  if (!force && perfStatsLoaded.value && !perfStatsError.value) return
  perfStatsLoading.value = true
  perfStatsError.value = false
  try {
    const res = await superRequest.get(`${BASE}/perf-stats`, { params: { days: 7 }, headers: superHeaders() })
    if (res.data?.code === 200) {
      perfStats.value = res.data.data?.stats || []
      perfStatsLoaded.value = true
    } else {
      perfStats.value = []
      perfStatsError.value = true
      perfStatsLoaded.value = false
    }
  } catch (e) {
    if (e?.response?.status === 401) authed.value = false
    else {
      perfStats.value = []
      perfStatsError.value = true
      perfStatsLoaded.value = false
    }
  } finally {
    perfStatsLoading.value = false
  }
}

async function loadStats(force = false) {
  if (!force && statsLoaded.value && !statsError.value) return
  statsLoading.value = true
  statsError.value = ''
  try {
    const res = await superRequest.get(`${BASE}/stats`, { headers: superHeaders() })
    if (res.data?.code === 200) {
      Object.assign(stats, res.data.data)
      statsLoaded.value = true
    } else {
      statsError.value = res.data?.msg || '经营辅助数据加载失败'
      statsLoaded.value = false
    }
  } catch (e) {
    if (e?.response?.status === 401) authed.value = false
    else statsError.value = backendMessage(e) || '经营辅助数据加载失败'
    statsLoaded.value = false
  } finally {
    statsLoading.value = false
  }
}

async function loadMerchants(force = false) {
  if (!force && merchantsLoaded.value && !merchantListError.value) return
  loadingList.value = true
  merchantListError.value = ''
  try {
    const res = await superRequest.get(`${BASE}/merchants`, { headers: superHeaders() })
    if (res.data?.code === 200) {
      merchants.value = res.data.data || []
      merchantsLoaded.value = true
    } else {
      merchantListError.value = res.data?.msg || '商户列表加载失败'
      merchantsLoaded.value = false
    }
  } catch (e) {
    if (e?.response?.status === 401) authed.value = false
    else {
      merchantListError.value = backendMessage(e) || '商户列表加载失败'
      merchantsLoaded.value = false
    }
  }
  finally { loadingList.value = false }
}

async function loadPendingPaymentCount(force = false) {
  if (!force && pendingCountLoaded.value && !pendingCountError.value) return
  pendingCountError.value = ''
  try {
    const res = await listManualPayments(superToken)
    if (res.data?.code === 200) {
      pendingPaymentCount.value = (res.data.data || []).length
      pendingCountLoaded.value = true
    } else {
      pendingCountError.value = res.data?.msg || '待确认付款数量加载失败'
      pendingCountLoaded.value = false
    }
  } catch (e) {
    if (e?.response?.status === 401) authed.value = false
    else pendingCountError.value = backendMessage(e) || '待确认付款数量加载失败'
    pendingCountLoaded.value = false
  }
}

function handlePendingCount(value) {
  pendingPaymentCount.value = Number(value || 0)
  pendingCountLoaded.value = true
  pendingCountError.value = ''
}

async function loadOverview(force = false) {
  await Promise.all([
    loadStats(force),
    loadMerchants(force),
    loadPendingPaymentCount(force),
  ])
}

function loadCurrentPage(force = false) {
  if (!superToken || !authed.value) return
  if (currentPage.value === 'overview') return loadOverview(force)
  if (currentPage.value === 'merchant-list') loadMerchants(force)
  else if (currentPage.value === 'performance') loadPerfStats(force)
  if (currentPage.value !== 'billing') loadPendingPaymentCount(force)
}

async function createMerchant() {
  if (!newMerchant.name || !newMerchant.phone) { createResult.value = { ok: false, msg: '店铺名称和手机号必填' }; return }
  creating.value = true
  createResult.value = null
  try {
    const res = await superRequest.post(`${BASE}/merchants`, { ...newMerchant }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      const d = res.data.data
      createResult.value = { ok: true, msg: `已开通「${d.name}」。商家可使用手机号 ${d.phone} 通过短信验证码登录商家后台。` }
      newMerchant.name = ''; newMerchant.phone = ''; newMerchant.initial_code = '123456'
      merchantsLoaded.value = false
      statsLoaded.value = false
    } else createResult.value = { ok: false, msg: res.data?.msg || '创建失败' }
  } catch { createResult.value = { ok: false, msg: '网络错误，请重试' } }
  finally { creating.value = false }
}

function openPayConfig(m) {
  payConfigTarget.value = m
  techOpen.value = false
  payConfigResult.value = null
  copySourceId.value = ''
  Object.assign(payConfigForm, {
    wx_mchid: m.wx_mchid || '', wx_mchid_masked: m.wx_mchid_masked || maskMchid(m.wx_mchid), wx_api_key_v3: '', wx_cert_serial: '', wx_private_key: '', wx_pay_enabled: m.wx_pay_enabled ?? true,
    receiver_name: m.receiver_name || m.name || '', receiver_type: m.receiver_type || 'enterprise', receiver_verified: !!m.receiver_verified,
    payment_locked: m.payment_locked ?? true, payment_status: m.payment_status || 'unconfigured', verified_time: m.verified_time || '',
  })
}

async function savePayConfig() {
  if (!payConfigForm.wx_mchid.trim() || !payConfigForm.wx_api_key_v3.trim() || !payConfigForm.wx_cert_serial.trim() || !payConfigForm.wx_private_key.trim()) {
    payConfigResult.value = { ok: false, msg: '请完整填写技术配置后保存' }
    techOpen.value = true
    return
  }
  savingPay.value = true
  payConfigResult.value = null
  try {
    const res = await superRequest.patch(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay`, {
      wx_mchid: payConfigForm.wx_mchid.trim(),
      wx_api_key_v3: payConfigForm.wx_api_key_v3.trim(),
      wx_cert_serial: payConfigForm.wx_cert_serial.trim(),
      wx_private_key: payConfigForm.wx_private_key.trim(),
      wx_public_key_id: payConfigForm.wx_public_key_id.trim() || null,
      wx_public_key: payConfigForm.wx_public_key.trim() || null,
      wx_pay_enabled: true,
      receiver_name: payConfigForm.receiver_name.trim(),
      receiver_type: payConfigForm.receiver_type,
    }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: '保存成功，请继续验证配置' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      refreshDetailAfterPayment()
      applyPaymentData(payConfigForm, res.data.data)
      payConfigForm.wx_api_key_v3 = ''; payConfigForm.wx_cert_serial = ''; payConfigForm.wx_private_key = ''; payConfigForm.wx_public_key = ''
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '保存失败' }
  } catch (e) { payConfigResult.value = { ok: false, msg: e?.response?.data?.msg || e?.response?.data?.detail?.message || '网络错误，请重试' } }
  finally { savingPay.value = false }
}

async function verifyPayConfig() {
  verifyingPay.value = true
  payConfigResult.value = null
  try {
    const res = await superRequest.post(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay/verify`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: res.data?.msg || '验证通过' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      refreshDetailAfterPayment()
      applyPaymentData(payConfigForm, res.data.data)
      payConfigForm.wx_api_key_v3 = ''; payConfigForm.wx_cert_serial = ''; payConfigForm.wx_private_key = ''; payConfigForm.wx_public_key = ''
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '验证失败' }
  } catch (e) {
    const detail = e?.response?.data?.detail
    const msg = detail?.message || e?.response?.data?.msg || '验证失败'
    payConfigResult.value = { ok: false, msg }
  }
  finally { verifyingPay.value = false }
}

function _promptTotpCode() {
  if (!totpEnabled.value) return ''
  const code = window.prompt('请输入认证器 App 里的 6 位动态口令完成二次验证') || ''
  return code.trim()
}

function confirmCopyPayConfig() {
  if (!copySourceId.value) return
  const source = merchants.value.find(m => m.tenant_id === copySourceId.value)
  const sourceName = source?.name || copySourceId.value
  const targetName = payConfigTarget.value.name
  if (!window.confirm(`确定要把「${sourceName}」的支付配置复制到「${targetName}」吗？\n复制后需要重新点击"验证配置"。`)) return
  const totp = _promptTotpCode()
  if (totpEnabled.value && !totp) return
  copyPayConfig(totp)
}

async function copyPayConfig(totpCodeInput = '') {
  copyingPay.value = true
  payConfigResult.value = null
  try {
    const res = await superRequest.post(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay/copy-from`, {
      source_tenant_id: copySourceId.value,
      totp_code: totpCodeInput || undefined,
    }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: res.data?.msg || '复制成功，请继续验证配置' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      refreshDetailAfterPayment()
      applyPaymentData(payConfigForm, res.data.data)
      copySourceId.value = ''
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '复制失败' }
  } catch (e) {
    payConfigResult.value = { ok: false, msg: e?.response?.data?.msg || '网络错误，请重试' }
  }
  finally { copyingPay.value = false }
}

function confirmPausePay() {
  if (!window.confirm(`确定要暂停「${payConfigTarget.value.name}」的收款吗？暂停后顾客将无法在线支付。`)) return
  const totp = _promptTotpCode()
  if (totpEnabled.value && !totp) return
  pausePay(totp)
}

async function pausePay(totpCodeInput = '') {
  pausingPay.value = true
  payConfigResult.value = null
  try {
    const res = await superRequest.patch(`${BASE}/merchants/${payConfigTarget.value.tenant_id}/wxpay/pause`, { totp_code: totpCodeInput || undefined }, { headers: superHeaders() })
    if (res.data?.code === 200) {
      payConfigResult.value = { ok: true, msg: '已暂停支付' }
      applyPaymentData(payConfigTarget.value, res.data.data)
      refreshDetailAfterPayment()
      applyPaymentData(payConfigForm, res.data.data)
    } else payConfigResult.value = { ok: false, msg: res.data?.msg || '暂停失败' }
  } catch (e) { payConfigResult.value = { ok: false, msg: e?.response?.data?.msg || '暂停失败' } }
  finally { pausingPay.value = false }
}

function rowBusy(tenantId) {
  return statusBusyId.value === tenantId || seedingId.value === tenantId
}

function toggleDanger(tenantId) {
  dangerOpenId.value = dangerOpenId.value === tenantId ? '' : tenantId
}

function statusButtonText(merchant) {
  if (statusBusyId.value === merchant.tenant_id) return merchant.status ? '停用中...' : '恢复中...'
  return merchant.status ? '停用商户' : '恢复商户'
}

function backendMessage(error) {
  const data = error?.response?.data
  if (typeof data?.msg === 'string' && data.msg.trim()) return data.msg.trim()
  const detail = data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message.trim()
  return ''
}

function confirmToggleStatus(merchant) {
  if (rowBusy(merchant.tenant_id)) return
  const name = merchant.name || '该商户'
  const message = merchant.status
    ? `确认停用「${name}」？\n\n这是平台停用该商户账号，不是餐厅今天休息。\n停用后，该商户不能继续登录使用开心点单，顾客也不能再通过该商户下单。\n\n如果只是今天不营业，请让商家在经营后台自己切换营业状态。`
    : `确认恢复「${name}」？\n\n恢复后，该商户账号将重新启用。\n商家当天是否营业，仍由商家在经营后台设置。`
  if (!window.confirm(message)) return
  toggleStatus(merchant)
}

async function seedTestData(merchant) {
  if (rowBusy(merchant.tenant_id)) return
  const name = merchant.name || '该商户'
  const ok = window.confirm(
    `为「${name}」填充测试数据？\n\n这是测试/开发辅助操作，不是开店步骤。\n\n该商户如果还没有订单，此操作会先删除已有的：\n· 全部菜品\n· 会员\n· 入口码（含桌码、海报码等）\n· 优惠券模板\n\n然后写入演示菜品、演示会员、演示优惠券模板、演示桌码，以及近 30 天和今日的演示订单。\n\n已经有订单的商户会被拒绝，不会删除真实订单。\n如果这是已经开始配置的真实商户，请取消。`,
  )
  if (!ok) return
  seedingId.value = merchant.tenant_id
  seedResult.value = null
  try {
    const res = await superRequest.post(`${BASE}/merchants/${merchant.tenant_id}/seed-test-data`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) {
      const d = res.data.data
      seedResult.value = { tenant_id: merchant.tenant_id, ok: true, msg: `填充成功：${d.menu_items} 道菜 · ${d.customers} 位会员 · 历史 ${d.history_orders} 单 · 今日 ${d.today_orders} 单` }
      if (isDetail.value) loadMerchantDetail(true)
    } else {
      seedResult.value = { tenant_id: merchant.tenant_id, ok: false, msg: res.data?.msg || '测试数据写入失败，未确认操作完成，请重新检查该商户的菜单、会员和入口码。' }
    }
  } catch (e) {
    seedResult.value = { tenant_id: merchant.tenant_id, ok: false, msg: backendMessage(e) || '测试数据写入失败，未确认操作完成，请重新检查该商户的菜单、会员和入口码。' }
  }
  finally { seedingId.value = '' }
}

async function toggleStatus(merchant) {
  const disabling = !!merchant.status
  const name = merchant.name || '该商户'
  statusBusyId.value = merchant.tenant_id
  statusResult.value = null
  try {
    const res = await superRequest.patch(`${BASE}/merchants/${merchant.tenant_id}/status`, {}, { headers: superHeaders() })
    if (res.data?.code === 200) {
      merchant.status = res.data.data.status
      const listed = merchants.value.find(item => item.tenant_id === merchant.tenant_id)
      if (listed && listed !== merchant) listed.status = merchant.status
      if (detail.value?.tenant && detail.value.tenant.tenant_id === merchant.tenant_id && detail.value.tenant !== merchant) {
        detail.value.tenant.status = merchant.status
      }
      statusResult.value = {
        tenant_id: merchant.tenant_id,
        ok: true,
        msg: merchant.status ? `已恢复「${name}」的商户账号` : `已停用「${name}」的商户账号`,
      }
    } else {
      statusResult.value = {
        tenant_id: merchant.tenant_id,
        ok: false,
        msg: res.data?.msg || (disabling ? '停用失败，请重试。' : '恢复失败，请重试。'),
      }
    }
  } catch (e) {
    if (e?.response?.status === 401) authed.value = false
    statusResult.value = {
      tenant_id: merchant.tenant_id,
      ok: false,
      msg: backendMessage(e) || (disabling ? '停用失败，请重试。' : '恢复失败，请重试。'),
    }
  } finally {
    statusBusyId.value = ''
  }
}

function logout() {
  rememberToken('')
  authed.value = false
  pwd.value = ''
  needTotp.value = false
  totpCode.value = ''
  pendingCountLoaded.value = false
  merchantsLoaded.value = false
  statsLoaded.value = false
  perfStatsLoaded.value = false
}

function backToMerchants() {
  router.push('/super/merchants')
}

function openMerchant(merchant, section = 'overview') {
  if (!merchant?.tenant_id) return
  const query = section && section !== 'overview' ? { section } : {}
  router.push({ name: 'SuperMerchantDetail', params: { tenantId: merchant.tenant_id }, query })
}

function setDetailSection(section) {
  detailSection.value = normalizeSection(section)
  const query = { ...route.query }
  if (detailSection.value === 'overview') delete query.section
  else query.section = detailSection.value
  router.replace({ name: 'SuperMerchantDetail', params: { tenantId: route.params.tenantId }, query })
}

function openChannelPartner(partnerId) {
  router.push({ path: '/super/channels', query: { partner: partnerId || undefined } })
}

function openMerchantFilter(paymentStatus = '', accountStatus = '') {
  router.push({
    path: '/super/merchants',
    query: {
      payment: paymentStatus || undefined,
      account: accountStatus || undefined,
    },
  })
}

function payMerchantFromDetail() {
  const current = detail.value
  if (!current?.tenant) return null
  const payment = current.payment || {}
  return {
    tenant_id: current.tenant.tenant_id,
    name: current.tenant.name,
    status: current.tenant.status,
    wx_mchid: '',
    wx_mchid_masked: payment.merchant_no_masked || payment.wx_mchid_masked || '',
    wx_pay_enabled: payment.wx_pay_enabled,
    receiver_name: payment.receiver_name || current.tenant.name || '',
    receiver_type: payment.receiver_type || 'enterprise',
    receiver_verified: !!payment.receiver_verified,
    payment_locked: payment.locked ?? payment.payment_locked ?? true,
    payment_status: payment.status || payment.payment_status || 'unconfigured',
    verified_time: payment.verified_time || '',
  }
}

let detailRequestSeq = 0
let invoiceRequestSeq = 0

async function loadMerchantDetail(silent = false) {
  const tenantId = String(route.params.tenantId || '')
  if (!tenantId || !superToken) return
  const requestSeq = ++detailRequestSeq
  if (!silent) detailLoading.value = true
  try {
    const res = await superRequest.get(`${BASE}/merchants/${tenantId}`, { headers: superHeaders() })
    if (requestSeq !== detailRequestSeq || String(route.params.tenantId || '') !== tenantId) return
    if (res.data?.code === 200) {
      detail.value = res.data.data
      detailError.value = ''
      syncListedMerchant(tenantId, res.data.data)
      if (detailSection.value === 'subscription') loadInvoices(false)
    } else if (!detail.value) {
      detailError.value = res.data?.msg || '商户信息加载失败'
    } else {
      detailError.value = res.data?.msg || '商户信息刷新失败'
    }
  } catch (e) {
    if (requestSeq !== detailRequestSeq) return
    if (e?.response?.status === 401) authed.value = false
    else if (!detail.value) detailError.value = backendMessage(e) || '商户信息加载失败'
    else detailError.value = backendMessage(e) || '商户信息刷新失败'
  } finally {
    if (requestSeq === detailRequestSeq) detailLoading.value = false
  }
}

async function loadInvoices(force = false) {
  const tenantId = String(route.params.tenantId || '')
  if (!tenantId || !superToken) return
  if (!force && invoicesLoaded.value && invoicesTenantId.value === tenantId && !invoicesError.value) return
  const requestSeq = ++invoiceRequestSeq
  invoicesLoading.value = true
  invoicesError.value = ''
  try {
    const res = await listBillingInvoices(superToken, tenantId)
    if (requestSeq !== invoiceRequestSeq || String(route.params.tenantId || '') !== tenantId) return
    if (res.data?.code === 200) {
      invoices.value = (res.data.data || []).filter(row => row.tenant_id === tenantId)
      invoicesTenantId.value = tenantId
      invoicesLoaded.value = true
    } else {
      invoicesError.value = res.data?.msg || '付款记录加载失败'
      invoicesLoaded.value = false
    }
  } catch (e) {
    if (requestSeq !== invoiceRequestSeq) return
    if (e?.response?.status === 401) authed.value = false
    invoicesError.value = backendMessage(e) || '付款记录加载失败'
    invoicesLoaded.value = false
  } finally {
    if (requestSeq === invoiceRequestSeq) invoicesLoading.value = false
  }
}

function refreshDetailAfterPayment() {
  if (isDetail.value) loadMerchantDetail(true)
}

function refreshDetailAfterAdjustment() {
  if (isDetail.value) loadMerchantDetail(true)
}

function syncListedMerchant(tenantId, payload) {
  const row = merchants.value.find(item => item.tenant_id === tenantId)
  if (!row || !payload) return
  const payment = payload.payment || {}
  row.status = payload.tenant?.status
  row.payment_status = payment.status || payment.payment_status || row.payment_status
  row.wx_mchid_masked = payment.merchant_no_masked || payment.wx_mchid_masked || row.wx_mchid_masked
  row.payment_locked = payment.locked ?? payment.payment_locked
  row.receiver_verified = payment.receiver_verified
  row.receiver_name = payment.receiver_name || row.receiver_name
  row.receiver_type = payment.receiver_type || row.receiver_type
  row.verified_time = payment.verified_time || row.verified_time
  row.wx_pay_enabled = payment.wx_pay_enabled ?? row.wx_pay_enabled
  row.subscription = payload.subscription
  if (payload.channel) {
    row.channel = {
      bound: payload.channel.bound,
      partner_id: payload.channel.partner_id,
      partner_name: payload.channel.partner_name,
      load_error: payload.channel.load_error,
    }
  }
  if (payload.operations && !payload.operations.load_error) row.today_orders = payload.operations.today_order_count
}

watch(() => route.params.tenantId, (tenantId) => {
  invoices.value = []
  invoicesTenantId.value = ''
  invoicesLoaded.value = false
  invoicesError.value = ''
  detailSeedOpen.value = false
  applyRoute()
  if (!authed.value || !tenantId) return
  detail.value = null
  loadMerchantDetail(false)
})

watch(() => route.query.section, () => {
  if (!isDetail.value) return
  applyRoute()
  if (detailSection.value === 'subscription') loadInvoices(false)
})

watch(() => route.fullPath, () => {
  applyRoute()
  if (isDetail.value) return
  loadCurrentPage(false)
})

onMounted(() => {
  applyRoute()
  if (!superToken) return
  authed.value = true
  if (isDetail.value) {
    loadMerchantDetail(false)
    loadPendingPaymentCount(false)
  } else loadCurrentPage(false)
})
</script>

<style scoped>
* { box-sizing: border-box; }

.super-wrap { min-height: 100vh; background: var(--bg-page); font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; color: var(--text-1); }

/* ─── Login ─────────────────────────────────────────────────── */
.login-box { max-width: 380px; margin: 0 auto; padding: 64px 20px 0; }
.login-card { border-radius: var(--radius-card); background: var(--bg-card); box-shadow: 0 12px 40px rgba(0,0,0,.16); overflow: hidden; }
.login-hero {
  position: relative;
  overflow: hidden;
  padding: 36px 24px 26px;
  text-align: center;
  background: linear-gradient(135deg, var(--hero-dark) 0%, #33335c 100%);
  color: #fff;
}
.login-hero::before {
  content: '';
  position: absolute;
  top: -70px; right: -50px;
  width: 200px; height: 200px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.14), transparent 70%);
}
.login-logo {
  position: relative;
  display: inline-flex; align-items: center; justify-content: center;
  width: 52px; height: 52px; border-radius: 14px;
  background: rgba(255,255,255,.14); color: #fff; font-weight: 900;
  margin-bottom: 12px;
}
.login-title { position: relative; font-size: 20px; font-weight: 900; margin-bottom: 4px; }
.login-sub { position: relative; font-size: 11px; letter-spacing: .12em; color: rgba(255,255,255,.55); font-weight: 700; }
.login-form { padding: 22px 22px 24px; }
.login-input, .form-input { width: 100%; height: 44px; border: 1px solid var(--border); border-radius: 8px; padding: 0 12px; font-size: 14px; outline: none; background: var(--bg-card); color: var(--text-1); }
.login-input { height: 48px; margin-bottom: 12px; }
.totp-hint { font-size: 13px; color: var(--text-2); margin-bottom: 10px; text-align: center; }
.login-input:focus, .form-input:focus { border-color: var(--hero-dark); box-shadow: 0 0 0 2px rgba(26,26,46,.12); }
.login-btn { width: 100%; height: 48px; background: var(--hero-dark); color: #fff; border: 0; border-radius: 8px; font-size: 15px; font-weight: 800; cursor: pointer; }
.create-btn { height: 44px; background: var(--brand); color: #fff; border: 0; border-radius: 8px; font-size: 15px; font-weight: 800; cursor: pointer; }
.login-btn:disabled, .create-btn:disabled, .verify-btn:disabled, .pause-btn:disabled, .toggle-btn:disabled { opacity: .55; cursor: not-allowed; }
.login-err { color: var(--danger); font-size: 13px; margin-top: 8px; }

/* ─── Control plane pages ───────────────────────────────────── */
.super-page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin: 0 16px 20px; }
.super-page-header h1 { margin: 0; color: var(--text-1); font-size: 26px; font-weight: 900; line-height: 1.25; }
.super-page-header p { max-width: 680px; margin: 7px 0 0; color: var(--text-2); font-size: 14px; line-height: 1.6; }
.primary-action { flex: none; min-height: 40px; padding: 0 18px; border: 0; border-radius: 8px; background: var(--brand); color: #fff; cursor: pointer; font-size: 14px; font-weight: 800; }
.overview-alert { display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid #fecaca; color: var(--danger); }
.action-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.action-card { display: grid; min-height: 118px; align-content: center; gap: 4px; padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-page); color: var(--text-1); cursor: pointer; text-align: left; }
.action-card:hover { border-color: var(--brand-mid); background: var(--brand-light); }
.action-card span { color: var(--text-2); font-size: 13px; font-weight: 700; }
.action-card strong { font-size: 26px; font-variant-numeric: tabular-nums; }
.action-card small { color: var(--text-3); font-size: 11px; }
.overview-stats { grid-template-columns: repeat(3, 1fr); padding: 0; }
.overview-stats .stat-card { border: 1px solid var(--border); box-shadow: none; }
.metric-note { margin-top: 12px; color: var(--text-3); font-size: 12px; }
.form-section { max-width: 560px; }
.header-back { margin: 0 0 10px; }
.refresh-btn, .pay-cfg-btn, .cancel-btn, .fold-btn { border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-2); cursor: pointer; }
.refresh-btn { padding: 5px 12px; font-size: 13px; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); padding: 12px 16px; gap: 8px; }
.stat-card, .section { background: var(--bg-card); border-radius: var(--radius-card); }
.stat-card { padding: 12px 8px; text-align: center; }
.stat-num { font-size: 20px; font-weight: 900; color: var(--text-1); }
.stat-num.green { color: var(--brand); } .stat-num.blue { color: #1677ff; }
.stat-label { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.section { margin: 0 16px 16px; padding: 16px; }
.section-title { font-size: 15px; font-weight: 800; margin-bottom: 12px; color: var(--text-1); }
.title-row { display: flex; align-items: center; justify-content: space-between; }
.create-form { display: grid; gap: 8px; }
.create-result { margin-top: 10px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.create-result.ok { background: var(--brand-light); color: var(--success); } .create-result.err { background: #fef2f2; color: var(--danger); }
.filter-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.filter-chip { height: 30px; padding: 0 12px; border: 1px solid var(--border); border-radius: 999px; background: var(--bg-card); color: var(--text-2); font-size: 12px; font-weight: 700; cursor: pointer; }
.filter-chip.active { border-color: var(--brand); background: var(--brand-light); color: var(--success); }
.loading, .empty { text-align: center; color: var(--text-3); padding: 24px 0; font-size: 14px; }
.perf-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.perf-table-scroll { overflow-x: auto; }
.perf-table th, .perf-table td { padding: 8px 6px; border-bottom: 1px solid var(--border); text-align: left; }
.perf-table th.num, .perf-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.perf-table th { color: var(--text-3); font-weight: 700; font-size: 12px; }
.phone-reveal { border-bottom: 1px dashed var(--text-3); cursor: pointer; }
.mc-badge, .mc-pay-badge, .status-pill { font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 20px; white-space: nowrap; }
.mc-badge.on, .pay-on { background: var(--brand-light); color: var(--success); }
.mc-badge.off { background: #f3f4f6; color: var(--text-2); }
.pay-off { background: #fef9c3; color: #92400e; } .pay-pending { background: #eff6ff; color: #2563eb; } .pay-paused { background: #f3f4f6; color: var(--text-2); }
.toggle-btn { font-size: 12px; padding: 4px 12px; border-radius: 6px; border: 0; cursor: pointer; font-weight: 700; }
.toggle-btn.stop { background: #fef2f2; color: var(--danger); } .toggle-btn.resume { background: var(--brand-light); color: var(--success); }
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 999; padding: 18px; }
.modal-box { width: min(520px, 100%); max-height: calc(100vh - 36px); overflow-y: auto; background: var(--bg-card); border-radius: 16px; padding: 18px; }
.modal-title { font-size: 17px; font-weight: 900; margin-bottom: 12px; color: var(--text-1); }
.receiver-card { border: 1px solid var(--brand-mid); background: var(--brand-light); border-radius: var(--radius-card); padding: 14px; }
.receiver-head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; margin-bottom: 12px; }
.receiver-kicker { font-size: 12px; color: var(--success); font-weight: 900; }
.receiver-title { font-size: 16px; font-weight: 900; margin-top: 2px; color: var(--text-1); }
.receiver-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.receiver-grid span, .modal-label { display: block; font-size: 12px; color: var(--text-2); margin-bottom: 5px; }
.field-hint { font-size: 11.5px; color: var(--text-3); margin-bottom: 6px; line-height: 1.5; }
.receiver-grid strong { display: block; font-size: 14px; color: var(--text-1); word-break: break-all; }
.lock-text { color: var(--success) !important; }
.safe-tip { margin-top: 12px; padding: 10px; border-radius: 8px; background: var(--bg-card); color: var(--text-2); font-size: 12px; line-height: 1.6; }
.fold-btn { width: 100%; height: 40px; margin-top: 12px; font-weight: 800; }
.tech-box { display: grid; gap: 8px; margin-top: 12px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-card); background: var(--bg-page); }
.copy-box { padding: 10px; margin-bottom: 4px; border: 1px dashed var(--brand-mid); border-radius: 10px; background: var(--brand-light); }
.copy-row { display: flex; gap: 8px; }
.copy-select { flex: 1; height: 40px; }
.copy-btn { flex: none; height: 40px; padding: 0 16px; border: 0; border-radius: 8px; background: var(--brand); color: #fff; font-weight: 800; font-size: 13px; cursor: pointer; }
.copy-btn:disabled { opacity: .55; cursor: not-allowed; }
.pay-radio-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.pay-radio-btn { height: 36px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-2); font-size: 14px; cursor: pointer; }
.pay-radio-btn.selected { border-color: var(--brand); background: var(--brand-light); color: var(--success); font-weight: 800; }
.private-input { height: 148px; padding-top: 10px; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.6; }
.modal-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
.verify-btn, .pause-btn { height: 44px; border: 0; border-radius: 8px; font-weight: 800; cursor: pointer; }
.verify-btn { background: #1677ff; color: #fff; }
.verify-btn--pending { box-shadow: 0 0 0 3px rgba(22,119,255,.28); }
.pause-btn { width: 100%; background: #fef2f2; color: #dc2626; }
.cancel-btn { width: 100%; height: 40px; margin-top: 8px; }
.danger-zone { margin-top: 20px; padding: 12px; border: 1px solid #fecaca; border-radius: var(--radius-card); background: #fff5f5; }
.danger-zone.card-danger { margin-top: 8px; }
.danger-zone-label { font-size: 11px; font-weight: 800; letter-spacing: .04em; color: #dc2626; margin-bottom: 8px; }
.more-btn { border: 0; background: transparent; color: var(--text-3); font-size: 12px; font-weight: 700; padding: 3px 4px; cursor: pointer; }
.danger-ops-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.seed-btn { font-size: 12px; padding: 4px 12px; border-radius: 6px; border: 1px solid #fcd34d; background: #fffbeb; color: #92400e; cursor: pointer; font-weight: 700; }
.seed-btn:disabled, .more-btn:disabled { opacity: .55; cursor: not-allowed; }
.seed-hint { margin-top: 8px; font-size: 11px; line-height: 1.5; color: #92400e; }
.tenant-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; color: var(--text-3); }
.merchant-context { padding-top: 12px; }
.back-link { margin: 0 16px 8px; border: 0; background: transparent; color: var(--text-2); font-size: 13px; font-weight: 700; cursor: pointer; padding: 0; }
.merchant-context-head { position: sticky; top: 0; z-index: 4; }
.context-kicker { font-size: 12px; font-weight: 800; color: var(--text-3); }
.context-name { margin-top: 2px; font-size: 22px; font-weight: 900; line-height: 1.3; }
.context-pills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.context-meta { margin-top: 6px; font-size: 12px; color: var(--text-2); }
.detail-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 16px 12px; }
.fact-list { display: grid; gap: 8px; }
.fact-row { display: flex; justify-content: space-between; gap: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); font-size: 13px; }
.fact-row span { color: var(--text-3); }
.fact-row strong { color: var(--text-1); text-align: right; font-weight: 800; }
.text-link { border: 0; background: transparent; padding: 0; color: #1677ff; font: inherit; font-weight: 800; cursor: pointer; }
.pay-open-btn { width: 100%; margin-top: 14px; }
.bill-title { margin-top: 18px; }
.bill-list { display: grid; gap: 8px; }
.bill-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px; border-radius: 10px; background: var(--bg-page); }
.bill-name { font-size: 14px; font-weight: 800; }
.bill-meta { margin-top: 3px; font-size: 12px; color: var(--text-2); }
.bill-amount { flex: none; font-size: 16px; font-weight: 900; }
.seed-block { margin-top: 8px; }
.error-state { display: grid; justify-items: center; gap: 10px; }
@media (max-width: 820px) {
  .action-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .overview-stats { grid-template-columns: 1fr; }
  .perf-table { min-width: 560px; }
}
@media (max-width: 420px) {
  .super-page-header { flex-direction: column; margin-right: 0; margin-left: 0; }
  .super-page-header h1 { font-size: 22px; }
  .primary-action { width: 100%; }
  .overview-alert { align-items: flex-start; flex-direction: column; }
  .section { margin-right: 0; margin-left: 0; }
  .stat-row { grid-template-columns: repeat(2, 1fr); }
  .receiver-grid { grid-template-columns: 1fr; }
}
</style>
