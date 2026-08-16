// P0-03 reconciliation: pure reducer functions for the simple (no-spec) cart
// map { dishId: qty }, extracted verbatim (no behavior change) from menu.vue's
// addToCart/removeFromCart so the increment/decrement math itself is directly
// executable by a test -- menu.vue keeps every bit of its own control flow
// (context/sold-out checks, feedback animations, spec-branch handling), this
// only carries the actual cart.value = {...} computation.

export function incrementSimpleCart(cart, dishId) {
  return { ...cart, [dishId]: (cart[dishId] || 0) + 1 }
}

export function decrementSimpleCart(cart, dishId) {
  const cur = cart[dishId] || 0
  if (cur <= 1) {
    const next = { ...cart }
    delete next[dishId]
    return next
  }
  return { ...cart, [dishId]: cur - 1 }
}
