import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 「本桌订单」三阶段状态呼吸指示器的结构合同。
//
// 测试环境是 node（没有 jsdom / @vue/test-utils），SFC 无法真实挂载，
// 所以这里是 SOURCE CONTRACT：不实际跑 S1–S16 分支，而是锁住决定这些分支
// 结果的关键结构——阶段数、排除顺序、frontier 优先级、settled 短路、
// 单点呼吸、CSS-only 动画。
//
// S1_S16_RUNTIME_EXECUTION = NO
// STRUCTURAL_CONTRACT_PROTECTION = YES
//
// 逐帧的视觉参数（时长 / 颜色 / 尺寸 / 间距）故意不锁——留出安全微调空间。

const here = path.dirname(fileURLToPath(import.meta.url))
const SRC = fs.readFileSync(path.resolve(here, '../TableBillSheet.vue'), 'utf8')

// §21 稳定分区：不用 /<template>([\s\S]*?)<\/template>/（会被内嵌 <template v-if> 提前截断）。
const TEMPLATE = SRC.slice(SRC.indexOf('<template'), SRC.indexOf('<script'))
const SCRIPT = SRC.slice(SRC.indexOf('<script'), SRC.indexOf('<style'))
const STYLE = SRC.slice(SRC.indexOf('<style'))

// 语义 marker-to-marker 提取：绝不按固定字符数 / 行号截取。
// startMarker 到「startMarker 之后的第一个 endMarker」之间的原文。
function sliceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker)
  const end = source.indexOf(endMarker, start + startMarker.length)
  expect(start, `未找到起始标记 ${startMarker}`).toBeGreaterThanOrEqual(0)
  expect(end, `未找到结束标记 ${endMarker}`).toBeGreaterThan(start)
  return source.slice(start, end)
}

// tableProgress computed 的正文，精确 bound 到下一个 computed（mergedItems）之前。
const tpStart = SCRIPT.indexOf('tableProgress()')
const TP = SCRIPT.slice(tpStart, SCRIPT.indexOf('mergedItems()', tpStart))

describe('三阶段：恰好 待接单 / 制作中 / 已上齐', () => {
  it('progress steps 恰好三个正常经营阶段，没有旧的四步文案', () => {
    // tableProgressSteps 的返回数组本体：从方法名到数组闭合 `]`。
    const block = sliceBetween(SCRIPT, 'tableProgressSteps()', ']')
    expect(block).toContain('待接单')
    expect(block).toContain('制作中')
    expect(block).toContain('已上齐')
    // 恰好三档：不存在第 4 档。
    expect(block).not.toMatch(/index:\s*4/)
    // 不是旧的「已下单 / 接单 / 上齐 / 结账」四步 timeline 文案。
    expect(block).not.toContain('已结账')
    expect(block).not.toContain('已下单')
  })
})

describe('frontier：先排除未支付单，再读 stage，再选档', () => {
  it('AWAITING_FILTER_ORDER_GUARD —— isAwaitingPayment 的排除发生在 map(stage) 和选档之前', () => {
    const iSettled = TP.indexOf('isTableSettled')
    const iExclude = TP.indexOf('isAwaitingPayment')
    const iMap = TP.indexOf('.map(')
    const iStage1 = TP.indexOf('=== 1')
    for (const [name, v] of [['isTableSettled', iSettled], ['isAwaitingPayment', iExclude], ['.map(', iMap], ['=== 1', iStage1]]) {
      expect(v, `${name} 应出现在 tableProgress 里`).toBeGreaterThan(-1)
    }
    // settled 短路在最前；未支付排除在读 stage 之前；选档在最后。
    expect(iSettled).toBeLessThan(iExclude)
    expect(iExclude).toBeLessThan(iMap)
    expect(iMap).toBeLessThan(iStage1)
    // 排除是「取反的 filter」，不是先选 frontier 再补救。
    expect(TP).toMatch(/filter\([^)]*!\s*[A-Za-z_$][\w$]*\.isAwaitingPayment/)
  })

  it('FRONTIER_POLICY_GUARD —— 最早的经营阶段优先（先判 stage 1，再判 stage 2，stage 3 兜底）', () => {
    const i1 = TP.indexOf('=== 1')
    const i2 = TP.indexOf('=== 2')
    expect(i1).toBeGreaterThan(-1)
    expect(i2).toBeGreaterThan(-1)
    expect(i1).toBeLessThan(i2)
    // stage 3 是最后的兜底档，仍可呼吸。
    expect(TP).toMatch(/stage:\s*3,\s*breathing:\s*true/)
  })

  it('SETTLED_PRIORITY_GUARD —— isTableSettled 短路到 no-breathing，且在正常 frontier 计算之前', () => {
    const iExclude = TP.indexOf('isAwaitingPayment')
    const head = TP.slice(0, iExclude)
    expect(head).toContain('isTableSettled')
    // 短路分支返回不呼吸。
    expect(head).toMatch(/isTableSettled[\s\S]{0,80}breathing:\s*false/)
  })

  it('NO_ELIGIBLE_STAGE —— 没有合格阶段时 stage 0 / 不呼吸，模板不渲染 active strip', () => {
    expect(TP).toMatch(/!stages\.length[\s\S]{0,60}stage:\s*0[\s\S]{0,40}breathing:\s*false/)
    // 模板对进度条整体有「至少要有一档」的渲染门槛。
    expect(TEMPLATE).toMatch(/v-if="tableProgress\.stage\s*>=\s*1"/)
    expect(TEMPLATE).toContain('class="to-progress"')
  })
})

describe('单点呼吸 + 三态可区分', () => {
  it('ONE_ACTIVE_BREATHING_GUARD —— 只有「当前档」能拿到 is-breathing，已过的档不呼吸', () => {
    // progressStepClass 是 methods 里最后一个方法，用 SFC 段落硬边界 </script> 收口。
    const block = sliceBetween(SCRIPT, 'progressStepClass(', '</script>')
    // is-breathing 的判据里带「当前档」条件。
    expect(block).toMatch(/is-breathing[^,}]*stage === index/)
    // is-breathing 绝不是「已过的档」(stage > index)。
    expect(block).not.toMatch(/is-breathing[^,}]*stage > index/)
  })

  it('三态（已过 / 当前 / 未到）由 class 区分，模板按 step 逐个套用', () => {
    expect(TEMPLATE).toContain('progressStepClass(step.index)')
    expect(TEMPLATE).toContain('v-for="step in tableProgressSteps"')
    expect(STYLE).toContain('.to-progress-step.is-done')
    expect(STYLE).toContain('.to-progress-step.is-cur')
    expect(STYLE).toContain('.to-progress-step.is-breathing')
  })
})

describe('动画：CSS-only + 尊重减弱动效', () => {
  it('REDUCED_MOTION_GUARD —— 有 @keyframes 且尊重 prefers-reduced-motion: reduce', () => {
    expect(STYLE).toContain('@keyframes toBreathe')
    expect(STYLE).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
  })

  it('NO_JS_TIMER_GUARD —— 呼吸不靠任何 JS 定时器 / rAF 驱动', () => {
    expect(SCRIPT).not.toContain('setInterval')
    expect(SCRIPT).not.toContain('setTimeout')
    expect(SCRIPT).not.toContain('requestAnimationFrame')
  })
})
