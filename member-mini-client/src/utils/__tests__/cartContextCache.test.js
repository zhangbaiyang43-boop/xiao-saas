import { describe, it, expect, beforeEach } from 'vitest'
import { saveCartSnapshot, restoreCartSnapshot, clearCartSnapshot } from '../cartContextCache.js'

// P0-03: process-lifetime (module-scoped, in-memory only -- never uni storage)
// cart snapshot cache. Restore must require an EXACT match on tenant_id +
// table_no + dining_session_id; any mismatch discards silently rather than
// ever handing back a cart for a different context.

const CTX_A_S1 = { tenant_id: 'tenant-a', table_no: 'A12', dining_session_id: 'sess-1' }

describe('cartContextCache', () => {
  beforeEach(() => {
    clearCartSnapshot()
  })

  it('T11: same context (tenant+table+session) 全部一致 -- 恢复成功', () => {
    saveCartSnapshot(CTX_A_S1, { dish_1: 2 }, [{ specKey: 'k1', qty: 1 }])

    const restored = restoreCartSnapshot({ ...CTX_A_S1 })

    expect(restored).not.toBeNull()
    expect(restored.cart).toEqual({ dish_1: 2 })
    expect(restored.specCartItems).toEqual([{ specKey: 'k1', qty: 1 }])
  })

  it('T12: table 变化（同 tenant，同 session 字段不再有效）-- 必须为空', () => {
    saveCartSnapshot(CTX_A_S1, { dish_1: 1 }, [])

    const restored = restoreCartSnapshot({ ...CTX_A_S1, table_no: 'A08' })

    expect(restored).toBeNull()
  })

  it('T13: tenant 变化 -- 必须为空', () => {
    saveCartSnapshot(CTX_A_S1, { dish_1: 1 }, [])

    const restored = restoreCartSnapshot({ ...CTX_A_S1, tenant_id: 'tenant-b', table_no: 'B01', dining_session_id: 'sess-x' })

    expect(restored).toBeNull()
  })

  it('T14: 同 tenant/table，session 变化（下一批客人）-- 必须为空', () => {
    saveCartSnapshot(CTX_A_S1, { dish_1: 1 }, [])

    const restored = restoreCartSnapshot({ ...CTX_A_S1, dining_session_id: 'sess-2' })

    expect(restored).toBeNull()
  })

  it('缺少 tenant_id/table_no/dining_session_id 中任一字段时，save 是 no-op（拒绝建立不完整 context）', () => {
    saveCartSnapshot({ tenant_id: 'tenant-a', table_no: '', dining_session_id: 'sess-1' }, { dish_1: 5 }, [])

    const restored = restoreCartSnapshot(CTX_A_S1)

    expect(restored).toBeNull()
  })

  it('restore 请求方缺少字段时直接返回 null，即使曾经保存过完整快照', () => {
    saveCartSnapshot(CTX_A_S1, { dish_1: 1 }, [])

    const restored = restoreCartSnapshot({ tenant_id: 'tenant-a', table_no: 'A12', dining_session_id: '' })

    expect(restored).toBeNull()
  })

  it('clearCartSnapshot 后任何 context 都恢复不到旧数据', () => {
    saveCartSnapshot(CTX_A_S1, { dish_1: 9 }, [])
    clearCartSnapshot()

    const restored = restoreCartSnapshot({ ...CTX_A_S1 })

    expect(restored).toBeNull()
  })

  it('restore 返回的是快照的拷贝，调用方修改不会污染缓存', () => {
    saveCartSnapshot(CTX_A_S1, { dish_1: 1 }, [{ specKey: 'k1', qty: 1 }])

    const first = restoreCartSnapshot({ ...CTX_A_S1 })
    first.cart.dish_1 = 999
    first.specCartItems[0].qty = 999

    const second = restoreCartSnapshot({ ...CTX_A_S1 })

    expect(second.cart.dish_1).toBe(1)
    expect(second.specCartItems[0].qty).toBe(1)
  })
})
