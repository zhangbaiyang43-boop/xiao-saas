<template>
  <view class="entry-page">
    <view v-if="error" class="entry-card">
      <view class="entry-error">!</view>
      <text class="entry-title">{{ error }}</text>
      <text class="entry-desc">{{ errorDesc }}</text>
      <button class="entry-btn" @click="reloadEntrance">{{ text.retry }}</button>
    </view>
    <view v-else class="entry-card entry-card--loading">
      <view class="loading-ring"></view>
      <text class="entry-title">{{ text.loadingTitle }}</text>
      <text class="entry-desc">{{ text.loadingDesc }}</text>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { resolveEntranceCode } from '@/api/auth'
import { clearCustomerSession } from '@/utils/auth'
import { resolveDiningIdentity, getOrCreateDiningClientId, persistDiningContext } from '@/utils/dining'
import {
  consumeStart,
  markEvent,
  markEventOnce,
  markStart,
  recordDurationFromStart,
} from '@/utils/perf'

const text = {
  retry: '重新识别',
  loadingTitle: '正在进入菜单',
  loadingDesc: '请稍等，马上开始点餐',
}

const normalizePagePath = (page) => String(page || '').trim().replace(/^\//, '').split('?')[0]
const PAGE_ALIASES = { 'pages/order/index': 'subpkg-order/pages/menu' }
const resolveRegisteredPage = (page) => PAGE_ALIASES[normalizePagePath(page)] || normalizePagePath(page) || 'subpkg-order/pages/menu'

const getQueryValue = (source, key) => {
  const match = String(source || '').match(new RegExp('[?&]' + key + '=([^&]+)'))
  return match ? decodeURIComponent(match[1]).trim() : ''
}

const parseOptions = (options = {}) => {
  const decodedQ = options.q ? decodeURIComponent(options.q) : ''
  const read = (key, aliases = []) => {
    const keys = [key, ...aliases]
    for (const k of keys) {
      const direct = options[k] ? decodeURIComponent(options[k]).trim() : ''
      if (direct) return direct
      const fromQ = getQueryValue(decodedQ, k)
      if (fromQ) return fromQ
    }
    return ''
  }
  return {
    scene: read('scene'),
    tenant_id: read('tenant_id', ['merchant_id', 'shop', 'store_id']),
    table: read('table', ['table_no', 'desk', 'desk_no']),
    table_id: read('table_id', ['desk_id']),
    entry_type: read('entry_type') || 'table',
    channel: read('channel') || 'TABLE',
    order_mode: read('order_mode') || 'dine_in',
    // 分销分享链接（invite.vue 的 onShareAppMessage）带的就是这个参数——之前这里
    // 完全没读它，导致邀请关系从源头就没法绑定，整条老带新双边奖励链路空转。
    invite_code: read('invite_code', ['inviter_code']),
  }
}


const buildMenuUrl = ({ target_page, tenant_id, table, table_id, entry_type, channel, order_mode }) => {
  const page = resolveRegisteredPage(target_page || 'subpkg-order/pages/menu')
  const params = []
  if (table) params.push('table=' + encodeURIComponent(table))
  if (tenant_id) params.push('shop=' + encodeURIComponent(tenant_id))
  if (order_mode) params.push('order_mode=' + encodeURIComponent(order_mode))
  if (entry_type) params.push('entry_type=' + encodeURIComponent(entry_type))
  if (channel) params.push('channel=' + encodeURIComponent(channel))
  if (table_id) params.push('table_id=' + encodeURIComponent(table_id))
  return '/' + page + (params.length ? '?' + params.join('&') : '')
}

export default {
  setup() {
    const error = ref('')
    const errorDesc = ref('')
    const lastOptions = ref({})
    const isRouting = ref(false)

    const saveContext = (ctx) => {
      // 换了一家店（tenant_id 变了）就必须清掉上一家的登录态，否则"会员"tab 会
      // 用旧店的 token 悄悄查出旧店的积分/优惠券，新店这一单也会因为查不到匹配
      // 租户的客户身份而静默不发积分/优惠券，用户不会有任何提示。
      const previousTenantId = uni.getStorageSync('tenant_id') || ''
      if (ctx.tenant_id && previousTenantId && previousTenantId !== ctx.tenant_id) {
        clearCustomerSession()
      }
      if (ctx.scene) uni.setStorageSync('entrance_scene', ctx.scene)
      if (ctx.tenant_id) uni.setStorageSync('tenant_id', ctx.tenant_id)
      if (ctx.shop_name) uni.setStorageSync('tenant_name', ctx.shop_name)
      if (ctx.table) {
        uni.setStorageSync('table_no', ctx.table)
        uni.setStorageSync('table_no_at', Date.now())
      }
      if (ctx.table_id) uni.setStorageSync('table_id', ctx.table_id)
      // 只在这次扫描/点击真的带了邀请码时才写入——不能清空之前存的邀请码，
      // 万一顾客先点了邀请链接、又换成扫桌上的普通桌码，邀请关系不该因此丢失。
      if (ctx.invite_code) uni.setStorageSync('invite_code', ctx.invite_code)
      uni.setStorageSync('entry_type', ctx.entry_type || 'table')
      uni.setStorageSync('channel', ctx.channel || 'TABLE')
      uni.setStorageSync('order_mode', ctx.order_mode || 'dine_in')
      uni.setStorageSync('entry_return_context', JSON.stringify(ctx))
    }


    // 本桌身份的建立/校验统一走 utils/dining.js 的 resolveDiningIdentity——它同时也是
    // menu.vue onLoad 时用的那一份，两处不再各自维护，避免再出现"一处改了、另一处忘了"
    // 的偏差（比如历史上这里曾经漏写 dining_table_no 的持久化）。这里强制刷新（force:
    // true），确保刚扫完码进来的这一次一定拿到跟当前桌号匹配、服务端确认过的身份，
    // 失败就直接在入口页报错拦下来，不会带着一个不完整的身份"裸奔"进点餐页。
    const resolveTableSession = async (ctx) => {
      if (!ctx.tenant_id || !ctx.table) throw new Error('缺少门店或桌号信息')
      markEvent('entry_dining_resolve_start', { fallback: true })
      try {
        const identity = await resolveDiningIdentity({ tenantId: ctx.tenant_id, table: ctx.table, force: true })
        if (!identity.ok) throw new Error(identity.reason === 'missing_context' ? '缺少门店或桌号信息' : (identity.reason || '本桌身份初始化失败'))
        markEvent('entry_dining_resolve_success', { fallback: true })
      } catch (err) {
        markEvent('entry_dining_resolve_failure', { fallback: true })
        throw err
      }
    }
    const routeToMenu = async (ctx) => {
      if (isRouting.value) return
      isRouting.value = true
      const url = buildMenuUrl(ctx)
      markStart('entry_to_menu')
      await new Promise((resolve) => {
        uni.redirectTo({
          url,
          success: () => {
            resolve(true)
          },
          fail: () => {
            uni.reLaunch({
              url,
              success: () => {
                resolve(true)
              },
              fail: (finalErr) => {
                consumeStart('entry_to_menu')
                error.value = '进入菜单失败'
                errorDesc.value = finalErr?.errMsg || '页面跳转失败'
                isRouting.value = false
                resolve(false)
              }
            })
          }
        })
      })
    }

    const routeToStaffShare = async (ctx) => {
      if (isRouting.value) return
      isRouting.value = true
      const params = []
      if (ctx.tenant_id) params.push('tenant_id=' + encodeURIComponent(ctx.tenant_id))
      if (ctx.invite_code) params.push('invite_code=' + encodeURIComponent(ctx.invite_code))
      if (ctx.staff_name) params.push('staff_name=' + encodeURIComponent(ctx.staff_name))
      if (ctx.shop_name) params.push('shop_name=' + encodeURIComponent(ctx.shop_name))
      const url = '/subpkg-member/pages/staff-share' + (params.length ? '?' + params.join('&') : '')
      await new Promise((resolve) => {
        uni.redirectTo({
          url,
          success: () => resolve(true),
          fail: () => {
            uni.reLaunch({
              url,
              success: () => resolve(true),
              fail: (finalErr) => {
                error.value = '进入推荐页失败'
                errorDesc.value = finalErr?.errMsg || '页面跳转失败'
                isRouting.value = false
                resolve(false)
              }
            })
          }
        })
      })
    }

    const loadEntrance = async (options = {}) => {
      lastOptions.value = options
      error.value = ''
      errorDesc.value = ''
      const parsed = parseOptions(options)
      try {
        if (parsed.scene) {
          // 带上 client_id：后端识别到是桌码场景时会顺带把这一桌的会话建好一起返回，
          // 省掉下面单独再调一次 resolveTableSession 的网络往返。老后端/非桌码场景不会
          // 返回 dining_session_id，走后面的 fallback，行为不变。
          markEvent('entry_resolve_start')
          markStart('entry_resolve')
          let res
          try {
            res = await resolveEntranceCode(parsed.scene, { clientId: getOrCreateDiningClientId() })
          } catch (err) {
            markEvent('entry_resolve_failure', { status: 'failure' })
            recordDurationFromStart('entry_resolve', 'entry_resolve', { status: 'failure' })
            throw err
          }
          if (res.code !== 200) {
            markEvent('entry_resolve_failure', { status: 'failure', response_code: res.code })
            recordDurationFromStart('entry_resolve', 'entry_resolve', { status: 'failure', response_code: res.code })
            error.value = res.msg || '桌码识别失败'
            errorDesc.value = '请联系门店工作人员处理'
            return
          }
          markEvent('entry_resolve_success', { status: 'success' })
          recordDurationFromStart('entry_resolve', 'entry_resolve', { status: 'success' })
          const data = res.data || {}
          const entrance = data.entrance || data
          const ctx = {
            scene: parsed.scene,
            tenant_id: data.tenant_id || data.tenant?.tenant_id || entrance.tenant_id || parsed.tenant_id,
            shop_name: data.shop_name || data.tenant?.name || '',
            table: entrance.table_no || data.table_no || parsed.table,
            table_id: entrance.table_id || data.table_id || parsed.table_id,
            entry_type: entrance.entry_type || data.entry_type || parsed.entry_type,
            channel: entrance.channel || data.channel || parsed.channel,
            order_mode: entrance.order_mode || data.order_mode || parsed.order_mode,
            target_page: entrance.target_page || data.target_page || 'subpkg-order/pages/menu',
          }
          // 员工分享码：不建桌台身份，直接进员工的专属分享页，让他点右上角转发。
          if (ctx.entry_type === 'staff_share') {
            await routeToStaffShare({
              tenant_id: ctx.tenant_id,
              invite_code: data.invite_code || '',
              staff_name: data.staff_name || '',
              shop_name: ctx.shop_name,
            })
            return
          }
          saveContext(ctx)
          if (data.dining_session_id && data.participant_token) {
            // 会话已经在入口码解析这一次请求里建好了，直接落存储，不用再单独跑一次
            // resolveTableSession（那里面还会额外判断缓存新鲜度，这里是刚拿到的最新结果，
            // 不存在"缓存过期"这个问题）。
            persistDiningContext({
              dining_session_id: data.dining_session_id,
              participant_id: data.participant_id,
              participant_token: data.participant_token,
              client_id: data.client_id,
              table_no: ctx.table,
            })
          } else {
            await resolveTableSession(ctx)
          }
          await routeToMenu(ctx)
          return
        }

        const fallbackTenantId = parsed.tenant_id || uni.getStorageSync('tenant_id') || ''
        const fallbackTable = parsed.table || uni.getStorageSync('table_no') || ''
        if (!fallbackTenantId && !fallbackTable) {
          error.value = '桌码缺少门店信息'
          errorDesc.value = '请重新扫描桌贴码'
          return
        }
        const ctx = { ...parsed, tenant_id: fallbackTenantId, table: fallbackTable, target_page: 'subpkg-order/pages/menu' }
        saveContext(ctx)
        await resolveTableSession(ctx)
        await routeToMenu(ctx)
      } catch (err) {
        // resolveTableSession 失败时会带着具体原因抛出来，直接展示，不要笼统地说"网络连接
        // 失败"——不然本桌身份建立失败这类问题会被当成网络问题，误导用户去重试网络。
        error.value = '本桌身份初始化失败'
        errorDesc.value = err?.message || '请检查网络后重试'
      }
    }

    const reloadEntrance = () => loadEntrance(lastOptions.value)

    return { text, error, errorDesc, loadEntrance, reloadEntrance }
  },
  onLoad(options) {
    if (markEventOnce('entry_onload', 'entry_onload')) {
      recordDurationFromStart('launch_to_entry', 'launch_to_entry')
    }
    uni.setNavigationBarTitle({ title: '开心点单' })
    this.loadEntrance(options)
  }
}
</script>

<style lang="scss">
.entry-page { min-height: 100vh; background: #f5f7fa; display: flex; align-items: center; justify-content: center; padding: 48rpx; box-sizing: border-box; }
.entry-card { width: 100%; min-height: 360rpx; border-radius: 28rpx; background: #fff; box-shadow: 0 18rpx 48rpx rgba(15, 23, 42, .08); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 48rpx 36rpx; text-align: center; box-sizing: border-box; }
.entry-card--loading { color: #111827; }
.loading-ring { width: 72rpx; height: 72rpx; border: 6rpx solid #e5e7eb; border-top-color: var(--brand); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.entry-error { width: 76rpx; height: 76rpx; border-radius: 50%; background: #fff1f2; color: #e11d48; display: flex; align-items: center; justify-content: center; font-size: 42rpx; font-weight: 900; }
.entry-title { margin-top: 28rpx; color: #111827; font-size: 34rpx; font-weight: 900; }
.entry-desc { margin-top: 14rpx; color: #64748b; font-size: 26rpx; line-height: 1.5; }
.entry-btn { margin-top: 36rpx; width: 100%; height: 88rpx; border-radius: 22rpx; background: var(--brand); color: #fff; font-size: 30rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; }
</style>

