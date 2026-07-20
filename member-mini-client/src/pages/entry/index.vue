﻿﻿﻿<template>
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
import { resolveEntranceCode, resolveDiningSession } from '@/api/auth'

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
  }
}


const getDiningClientId = () => {
  let clientId = uni.getStorageSync('dining_client_id') || ''
  if (!clientId) {
    clientId = `dc_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`
    uni.setStorageSync('dining_client_id', clientId)
  }
  return clientId
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
      if (ctx.scene) uni.setStorageSync('entrance_scene', ctx.scene)
      if (ctx.tenant_id) uni.setStorageSync('tenant_id', ctx.tenant_id)
      if (ctx.shop_name) uni.setStorageSync('tenant_name', ctx.shop_name)
      if (ctx.table) {
        uni.setStorageSync('table_no', ctx.table)
        uni.setStorageSync('table_no_at', Date.now())
      }
      if (ctx.table_id) uni.setStorageSync('table_id', ctx.table_id)
      uni.setStorageSync('entry_type', ctx.entry_type || 'table')
      uni.setStorageSync('channel', ctx.channel || 'TABLE')
      uni.setStorageSync('order_mode', ctx.order_mode || 'dine_in')
      uni.setStorageSync('entry_return_context', JSON.stringify(ctx))
    }


    const resolveTableSession = async (ctx) => {
      if (!ctx.tenant_id || !ctx.table) return
      const clientId = getDiningClientId()
      const res = await resolveDiningSession({
        tenant_id: ctx.tenant_id,
        table_no: ctx.table,
        client_id: clientId,
        participant_token: uni.getStorageSync('dining_participant_token') || undefined,
      })
      if (res.code !== 200 || !res.data) throw new Error(res.msg || '本桌订单初始化失败')
      uni.setStorageSync('dining_session_id', res.data.dining_session_id || '')
      uni.setStorageSync('dining_participant_id', res.data.participant_id || '')
      uni.setStorageSync('dining_participant_token', res.data.participant_token || '')
      uni.setStorageSync('dining_client_id', res.data.client_id || clientId)
    }
    const routeToMenu = async (ctx) => {
      if (isRouting.value) return
      isRouting.value = true
      const url = buildMenuUrl(ctx)
      console.log('[ENTRY_MENU_ROUTE_START]', { scene: ctx.scene, tenant_id: ctx.tenant_id, table_no: ctx.table, url })
      await new Promise((resolve) => {
        uni.redirectTo({
          url,
          success: () => {
            console.log('[ENTRY_MENU_ROUTE_SUCCESS]', { url })
            resolve(true)
          },
          fail: (err) => {
            console.log('[ENTRY_MENU_ROUTE_FAIL]', { url, error: err })
            uni.reLaunch({
              url,
              success: () => {
                console.log('[ENTRY_MENU_ROUTE_SUCCESS]', { url })
                resolve(true)
              },
              fail: (finalErr) => {
                console.log('[ENTRY_MENU_ROUTE_FINAL_FAIL]', { url, error: finalErr })
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

    const loadEntrance = async (options = {}) => {
      lastOptions.value = options
      error.value = ''
      errorDesc.value = ''
      const parsed = parseOptions(options)
      try {
        if (parsed.scene) {
          console.log('[ENTRY_RESOLVE_START]', { scene: parsed.scene })
          const res = await resolveEntranceCode(parsed.scene)
          if (res.code !== 200) {
            console.log('[ENTRY_RESOLVE_FAIL]', { scene: parsed.scene, status: res.code, message: res.msg })
            error.value = res.msg || '桌码识别失败'
            errorDesc.value = '请联系门店工作人员处理'
            return
          }
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
          saveContext(ctx)
          await resolveTableSession(ctx)
          console.log('[ENTRY_RESOLVE_SUCCESS]', { scene: ctx.scene, tenant_id: ctx.tenant_id, table_no: ctx.table, target_page: ctx.target_page })
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
        console.log('[ENTRY_RESOLVE_FAIL]', { scene: parsed.scene, status: 0, message: err.message })
        error.value = '网络连接失败'
        errorDesc.value = '请检查网络后重试'
      }
    }

    const reloadEntrance = () => loadEntrance(lastOptions.value)

    return { text, error, errorDesc, loadEntrance, reloadEntrance }
  },
  onLoad(options) {
    uni.setNavigationBarTitle({ title: '开心点单' })
    this.loadEntrance(options)
  }
}
</script>

<style lang="scss">
.entry-page { min-height: 100vh; background: #f5f7fa; display: flex; align-items: center; justify-content: center; padding: 48rpx; box-sizing: border-box; }
.entry-card { width: 100%; min-height: 360rpx; border-radius: 28rpx; background: #fff; box-shadow: 0 18rpx 48rpx rgba(15, 23, 42, .08); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 48rpx 36rpx; text-align: center; box-sizing: border-box; }
.entry-card--loading { color: #111827; }
.loading-ring { width: 72rpx; height: 72rpx; border: 6rpx solid #e5e7eb; border-top-color: #16c76f; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.entry-error { width: 76rpx; height: 76rpx; border-radius: 50%; background: #fff1f2; color: #e11d48; display: flex; align-items: center; justify-content: center; font-size: 42rpx; font-weight: 900; }
.entry-title { margin-top: 28rpx; color: #111827; font-size: 34rpx; font-weight: 900; }
.entry-desc { margin-top: 14rpx; color: #64748b; font-size: 26rpx; line-height: 1.5; }
.entry-btn { margin-top: 36rpx; width: 100%; height: 88rpx; border-radius: 22rpx; background: #16c76f; color: #fff; font-size: 30rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; }
</style>

