import { describe, it, expect } from 'vitest'
import { incrementSimpleCart, decrementSimpleCart } from '../simpleCartMath.js'

// P0-03 T01/T02: real executed cart mutation, not source pattern matching.
// This is the exact math menu.vue's addToCart/removeFromCart delegate to.

describe('simpleCartMath (P0-03 T01/T02)', () => {
  it('T01: 连续调用 incrementSimpleCart 10 次，qty=10', () => {
    let cart = {}
    for (let i = 0; i < 10; i += 1) {
      cart = incrementSimpleCart(cart, 'dish_1')
    }
    expect(cart).toEqual({ dish_1: 10 })
  })

  it('T02: + - + - + 序列，逐步验证每一步，最终 qty=1', () => {
    let cart = {}
    const steps = []

    cart = incrementSimpleCart(cart, 'dish_1'); steps.push(cart.dish_1 ?? 0) // +
    cart = decrementSimpleCart(cart, 'dish_1'); steps.push(cart.dish_1 ?? 0) // -
    cart = incrementSimpleCart(cart, 'dish_1'); steps.push(cart.dish_1 ?? 0) // +
    cart = decrementSimpleCart(cart, 'dish_1'); steps.push(cart.dish_1 ?? 0) // -
    cart = incrementSimpleCart(cart, 'dish_1'); steps.push(cart.dish_1 ?? 0) // +

    expect(steps).toEqual([1, 0, 1, 0, 1])
    expect(cart).toEqual({ dish_1: 1 })
  })

  it('T02b: qty=1 时连续 decrement 两次，不能出现负数，第二次仍是移除状态（qty 0 / key 不存在）', () => {
    let cart = { dish_1: 1 }

    cart = decrementSimpleCart(cart, 'dish_1')
    expect(cart).toEqual({})

    cart = decrementSimpleCart(cart, 'dish_1') // decrementing an already-absent item
    expect(cart).toEqual({})
    expect(cart.dish_1).toBeUndefined()
  })

  it('increment 与 decrement 互不影响其他 dish 的 qty', () => {
    let cart = { dish_1: 2, dish_2: 5 }
    cart = incrementSimpleCart(cart, 'dish_1')
    cart = decrementSimpleCart(cart, 'dish_2')
    expect(cart).toEqual({ dish_1: 3, dish_2: 4 })
  })
})
