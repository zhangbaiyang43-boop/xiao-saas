import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

const sourcePath = (path) => fileURLToPath(new URL(path, import.meta.url))
const source = readFileSync(sourcePath('../order-bubble.vue'), 'utf8')

// 首次引导提示（"点这里随时看订单进度"）和状态变化提示条（actionText，比如
// "请确认菜品"）曾经各自独立触发，冷启动时如果订单状态恰好同时刷新成新状态
// （比如"已送达"），两条提示会同时挤在左下角互相打架。这里锁定两个方向的
// 互斥判断都还在：状态提示条优先，首次引导让位。
describe('order-bubble hint/callout mutual exclusion', () => {
  it('visible watcher 在 showChangeCallout 已经为 true 时不再显示首次引导，但仍标记已提示', () => {
    const visibleWatcherMatch = source.match(/watch\(\(\) => props\.visible,[\s\S]*?\n {4}\}\)/)
    expect(visibleWatcherMatch, 'visible watcher not found').toBeTruthy()
    const body = visibleWatcherMatch[0]
    expect(body).toMatch(/if \(showChangeCallout\.value\) \{[\s\S]*?uni\.setStorageSync\(HINT_STORAGE_KEY, '1'\)[\s\S]*?return/)
  })

  it('triggerChangeFeedback 在显示状态提示条之前，如果首次引导还挂着就先收起', () => {
    const triggerFnMatch = source.match(/function triggerChangeFeedback\(\) \{[\s\S]*?\n {4}\}/)
    expect(triggerFnMatch, 'triggerChangeFeedback not found').toBeTruthy()
    const body = triggerFnMatch[0]
    expect(body).toMatch(/if \(showHint\.value\) dismissHint\(\)/)
    // dismissHint 调用必须在 showChangeCallout.value = true 之前，不能先弹出再收起。
    const dismissIndex = body.indexOf('dismissHint()')
    const showCalloutIndex = body.indexOf('showChangeCallout.value = true')
    expect(dismissIndex).toBeGreaterThan(-1)
    expect(showCalloutIndex).toBeGreaterThan(-1)
    expect(dismissIndex).toBeLessThan(showCalloutIndex)
  })
})
