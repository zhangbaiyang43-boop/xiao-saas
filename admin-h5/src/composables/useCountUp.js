import { isRef, ref, watch } from 'vue'

/**
 * 数字平滑滚动到目标值，用于首页营收这类"核心大数字"。
 * source 可以是 ref/computed，也可以是普通数字。
 * 首次挂载会从 0 滚到目标值；之后 source 变化（比如轮询刷新）也会平滑过渡，
 * 不会出现"数字瞬间跳变"的生硬感。
 *
 * 用法：
 *   const revenueDisplay = useCountUp(computed(() => orderStats.value.revenue))
 *   <a-statistic :value="revenueDisplay" :precision="2" />
 */
export function useCountUp(source, options = {}) {
  const { duration = 600 } = options
  const display = ref(0)
  let raf = null

  function animateTo(target) {
    target = Number(target) || 0
    const start = display.value
    if (start === target) return
    const startTime = performance.now()
    if (raf) cancelAnimationFrame(raf)

    function tick(now) {
      const progress = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
      display.value = start + (target - start) * eased
      if (progress < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        display.value = target
        raf = null
      }
    }
    raf = requestAnimationFrame(tick)
  }

  if (isRef(source)) {
    watch(source, (val) => animateTo(val), { immediate: true })
  } else {
    animateTo(source)
  }

  return display
}
