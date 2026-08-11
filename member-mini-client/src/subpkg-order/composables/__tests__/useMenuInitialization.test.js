import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { createMenuInitialization } from '../useMenuInitialization.js'

const menuSource = readFileSync(
  fileURLToPath(new URL('../../pages/menu.vue', import.meta.url)),
  'utf8',
)

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const flushPromises = () => new Promise(resolve => setTimeout(resolve, 0))

const setup = () => {
  const menu = deferred()
  const authority = deferred()
  const onReady = vi.fn(() => Promise.resolve())
  const onFailure = vi.fn()
  const onDeferredError = vi.fn()
  return {
    menu,
    authority,
    onReady,
    onFailure,
    onDeferredError,
    initialization: createMenuInitialization({
      loadMenu: () => menu.promise,
      loadCriticalContext: () => authority.promise,
      onCriticalReady: onReady,
      onCriticalFailure: onFailure,
      onDeferredError,
    }),
  }
}

describe('production menu initialization gate', () => {
  it('waits for both menu data and authoritative shop context', async () => {
    const state = setup()
    const result = state.initialization.run()
    state.menu.resolve(true)
    await flushPromises()
    expect(state.onReady).not.toHaveBeenCalled()
    state.authority.resolve(true)
    await expect(result).resolves.toBe(true)
    expect(state.onReady).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['closed or unavailable authority', (state) => state.authority.resolve(false)],
    ['failed authority request', (state) => state.authority.reject(new Error('shop failed'))],
  ])('does not expose ordering when %s', async (_, fail) => {
    const state = setup()
    const result = state.initialization.run()
    state.menu.resolve(true)
    fail(state)
    await expect(result).resolves.toBe(false)
    expect(state.onReady).not.toHaveBeenCalled()
    expect(state.onFailure).toHaveBeenCalledTimes(1)
  })

  it('starts member, coupon, session/history and payment recovery only after critical readiness', async () => {
    const state = setup()
    const tasks = [vi.fn(), vi.fn(), vi.fn(), vi.fn()]
    const result = state.initialization.run({ secondaryTasks: tasks })
    expect(tasks.every(task => task.mock.calls.length === 0)).toBe(true)
    state.menu.resolve(true)
    state.authority.resolve(true)
    await expect(result).resolves.toBe(true)
    expect(tasks.every(task => task.mock.calls.length === 1)).toBe(true)
  })

  it('contains deferred failure after the menu is ready', async () => {
    const state = setup()
    const error = new Error('member failed')
    const result = state.initialization.run({ secondaryTasks: [() => Promise.reject(error)] })
    state.menu.resolve(true)
    state.authority.resolve(true)
    await expect(result).resolves.toBe(true)
    await flushPromises()
    expect(state.onDeferredError).toHaveBeenCalledWith(error)
  })

  it('does not update readiness or start deferred work after navigation away', async () => {
    const state = setup()
    const deferredTask = vi.fn()
    const result = state.initialization.run({ secondaryTasks: [deferredTask] })
    state.initialization.dispose()
    state.menu.resolve(true)
    state.authority.resolve(true)
    await expect(result).resolves.toBe(false)
    expect(state.onReady).not.toHaveBeenCalled()
    expect(deferredTask).not.toHaveBeenCalled()
  })

  it('wires readiness to authoritative payment/open-state context and guards ordering', () => {
    expect(menuSource).toContain('loadCriticalContext: () => this.loadShopSettings()')
    expect(menuSource).toContain('paymentMode.value = normalizePaymentMode(d.payment_mode)')
    expect(menuSource).toContain('if (d.is_open === false)')
    expect(menuSource).toContain('orderingContextReady.value && totalCount.value > 0')
    expect(menuSource.match(/if \(!orderingContextReady\.value\)/g)).toHaveLength(2)
  })
})
