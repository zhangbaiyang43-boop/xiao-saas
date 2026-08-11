// The customer can order only after menu data and the shop's authoritative
// payment/open-state context are both available. Identity, history, coupons,
// member state and payment recovery are detached follow-up work.
export function createMenuInitialization({
  loadMenu,
  loadCriticalContext,
  onCriticalReady,
  onCriticalFailure = () => {},
  onDeferredError = () => {},
}) {
  let disposed = false

  const startDeferred = (task) => {
    try {
      Promise.resolve(task()).catch(onDeferredError)
    } catch (error) {
      onDeferredError(error)
    }
  }

  const run = async ({ secondaryTasks = [] } = {}) => {
    let menuReady
    let contextReady
    try {
      [menuReady, contextReady] = await Promise.all([
        loadMenu(),
        loadCriticalContext(),
      ])
    } catch (error) {
      if (!disposed) onCriticalFailure(error)
      return false
    }

    if (disposed) return false
    if (menuReady !== true || contextReady !== true) {
      onCriticalFailure(new Error('menu critical context unavailable'))
      return false
    }

    await onCriticalReady()
    if (disposed) return false
    secondaryTasks.forEach(startDeferred)
    return true
  }

  return {
    run,
    dispose: () => { disposed = true },
  }
}
