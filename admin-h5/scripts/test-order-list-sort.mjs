/**
 * 商家工作台订单列表排序契约（履约 FIFO + 终态最新优先）
 */
import assert from 'node:assert/strict'
import { sortMerchantOrders, compareMerchantOrders } from '../src/utils/orderListSort.js'

const t = (hhmm, day = '2026-08-08') => `${day}T${hhmm}:00+08:00`

function order(partial) {
  return {
    id: partial.id,
    status: partial.status,
    createdAt: partial.createdAt,
  }
}

function times(list) {
  return list.map((o) => o.createdAt.slice(11, 16))
}

function ids(list) {
  return list.map((o) => String(o.id))
}

// 24 待接单 FIFO（API 顺序故意打乱）
{
  const sorted = sortMerchantOrders([
    order({ id: '3', status: 'pending', createdAt: t('14:07') }),
    order({ id: '1', status: 'pending', createdAt: t('14:00') }),
    order({ id: '2', status: 'pending', createdAt: t('14:03') }),
  ])
  assert.deepEqual(times(sorted), ['14:00', '14:03', '14:07'])
}

// 25 备餐 FIFO
{
  const sorted = sortMerchantOrders([
    order({ id: '2', status: 'preparing', createdAt: t('14:06') }),
    order({ id: '1', status: 'preparing', createdAt: t('14:01') }),
  ])
  assert.deepEqual(times(sorted), ['14:01', '14:06'])
}

// 26 待结账/done FIFO
{
  const sorted = sortMerchantOrders([
    order({ id: '3', status: 'done', createdAt: t('14:18') }),
    order({ id: '1', status: 'done', createdAt: t('13:42') }),
    order({ id: '2', status: 'done', createdAt: t('13:54') }),
  ])
  assert.deepEqual(times(sorted), ['13:42', '13:54', '14:18'])
}

// 27 已结账最新优先
{
  const sorted = sortMerchantOrders([
    order({ id: '1', status: 'settled', createdAt: t('13:42') }),
    order({ id: '3', status: 'settled', createdAt: t('14:18') }),
    order({ id: '2', status: 'settled', createdAt: t('13:54') }),
  ])
  assert.deepEqual(times(sorted), ['14:18', '13:54', '13:42'])
}

// 28 拒绝/取消最新优先
{
  const rejected = sortMerchantOrders([
    order({ id: '1', status: 'rejected', createdAt: t('13:00') }),
    order({ id: '2', status: 'rejected', createdAt: t('14:00') }),
  ])
  assert.deepEqual(times(rejected), ['14:00', '13:00'])

  const cancelled = sortMerchantOrders([
    order({ id: '1', status: 'cancelled', createdAt: t('12:00') }),
    order({ id: '2', status: 'cancelled', createdAt: t('15:00') }),
  ])
  assert.deepEqual(times(cancelled), ['15:00', '12:00'])
}

// 29 待支付 DESC
{
  const sorted = sortMerchantOrders([
    order({ id: '1', status: 'pending_payment', createdAt: t('14:00') }),
    order({ id: '3', status: 'pending_payment', createdAt: t('14:07') }),
    order({ id: '2', status: 'pending_payment', createdAt: t('14:03') }),
  ])
  assert.deepEqual(times(sorted), ['14:07', '14:03', '14:00'])
}

// 30 全部 Tab：状态优先级 + 各状态时间方向
{
  const input = [
    order({ id: 'A', status: 'pending', createdAt: t('14:00') }),
    order({ id: 'B', status: 'preparing', createdAt: t('14:01') }),
    order({ id: 'C', status: 'done', createdAt: t('14:02') }),
    order({ id: 'D', status: 'pending', createdAt: t('14:03') }),
    order({ id: 'E', status: 'done', createdAt: t('14:04') }),
    order({ id: 'F', status: 'settled', createdAt: t('14:05') }),
    order({ id: 'G', status: 'preparing', createdAt: t('14:06') }),
    order({ id: 'H', status: 'pending', createdAt: t('14:07') }),
    order({ id: 'I', status: 'settled', createdAt: t('13:30') }),
  ]
  const sorted = sortMerchantOrders([...input].reverse())
  assert.deepEqual(ids(sorted), ['A', 'D', 'H', 'B', 'G', 'C', 'E', 'F', 'I'])
}

// 31 相同 createdAt：id 次键稳定（履约 ASC）
{
  const same = t('14:00')
  const sorted = sortMerchantOrders([
    order({ id: '9007199254740993', status: 'pending', createdAt: same }),
    order({ id: '9007199254740991', status: 'pending', createdAt: same }),
    order({ id: '9007199254740992', status: 'pending', createdAt: same }),
  ])
  assert.deepEqual(ids(sorted), [
    '9007199254740991',
    '9007199254740992',
    '9007199254740993',
  ])
  for (let i = 0; i < 10; i++) {
    assert.deepEqual(
      ids(sortMerchantOrders([...sorted].reverse())),
      ['9007199254740991', '9007199254740992', '9007199254740993'],
    )
  }
}

// 终态相同时间：id DESC
{
  const same = t('14:00')
  const sorted = sortMerchantOrders([
    order({ id: '1', status: 'settled', createdAt: same }),
    order({ id: '3', status: 'settled', createdAt: same }),
    order({ id: '2', status: 'settled', createdAt: same }),
  ])
  assert.deepEqual(ids(sorted), ['3', '2', '1'])
}

// 32 非法/缺失时间不产生 NaN
{
  const sorted = sortMerchantOrders([
    order({ id: '2', status: 'pending', createdAt: 'not-a-date' }),
    order({ id: '1', status: 'pending', createdAt: '' }),
    order({ id: '3', status: 'pending', createdAt: t('14:00') }),
  ])
  assert.equal(sorted.length, 3)
  const cmp = compareMerchantOrders(sorted[0], sorted[1])
  assert.ok(Number.isFinite(cmp))
  // 非法/空时间按 0 处理；有效时间更大 → FIFO 时排在后面
  assert.deepEqual(ids(sorted), ['1', '2', '3'])
}

console.log('TEST-FE orderListSort: passed')
