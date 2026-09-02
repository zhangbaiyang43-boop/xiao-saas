import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 「本桌订单」每道菜进度点竖排里「当前那个点」的进行中指示合同。
//
// 早期试过一条横排「待接单 / 制作中 / 已上齐」三阶段文字条（.to-progress /
// tableProgress / progressStepClass / @keyframes toBreathe），真机看不出、也不是
// 产品想要的，已整条移除。改为：每道菜自己那一竖排 .to-stage-dot 里，「当前那一步」
// （= 最后一个亮点，row.stage === n 且这道菜还没上齐）——
//   静止态就明显做大 + 一圈品牌绿描边（不依赖动画，减弱动效下也可辨），
//   再叠一个伪元素 ::after 的 ripple 绿环，只靠 transform + opacity 外扩淡出。
//
// mp-weixin 合规点：会动的东西只动 transform / opacity（仓库既有 keyframe 全是如此），
// 不在 @keyframes 里动 box-shadow、也不在 @keyframes 里用 var()。
//
// SOURCE CONTRACT（node 环境不挂载 SFC）：锁结构，不锁逐帧数值 / 时长 / 颜色。

const here = path.dirname(fileURLToPath(import.meta.url))
const SRC = fs.readFileSync(path.resolve(here, '../TableBillSheet.vue'), 'utf8')

const TEMPLATE = SRC.slice(SRC.indexOf('<template'), SRC.indexOf('<script'))
const SCRIPT = SRC.slice(SRC.indexOf('<script'), SRC.indexOf('<style'))
const STYLE = SRC.slice(SRC.indexOf('<style'))

// 语义 marker-to-marker 提取，绝不按固定字符数 / 行号截取。
function sliceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker)
  const end = source.indexOf(endMarker, start + startMarker.length)
  expect(start, `未找到起始标记 ${startMarker}`).toBeGreaterThanOrEqual(0)
  expect(end, `未找到结束标记 ${endMarker}`).toBeGreaterThan(start)
  return source.slice(start, end)
}

describe('废弃的横排三阶段文字条已彻底移除', () => {
  it('模板 / 脚本 / 样式里都没有 .to-progress 那套残留', () => {
    for (const [name, src] of [['TEMPLATE', TEMPLATE], ['SCRIPT', SCRIPT], ['STYLE', STYLE]]) {
      expect(src, `${name} 不应再出现 to-progress`).not.toContain('to-progress')
      expect(src, `${name} 不应再出现 toBreathe`).not.toContain('toBreathe')
    }
    expect(SCRIPT).not.toContain('tableProgressSteps')
    expect(SCRIPT).not.toContain('progressStepClass')
    expect(SCRIPT).not.toContain('tableProgress')
  })
})

describe('当前进行中的那道菜：进度点竖排里「当前点」的指示', () => {
  it('只有 row.stage === n 且这道菜还没上齐(< stageCount) 的那个点带 --cur', () => {
    const dot = sliceBetween(TEMPLATE, 'class="to-stage-dot"', '></view>')
    expect(dot).toMatch(/on:\s*row\.stage >= n/)
    // 当前点用「恰好等于」，不是「>=」—— 同一竖排至多一个点。
    expect(dot).toMatch(/to-stage-dot--cur['"]?\s*:\s*row\.stage === n/)
    // 且排除已上齐的菜（那走汇聚成对号的收尾动效）。
    expect(dot).toMatch(/to-stage-dot--cur[\s\S]{0,60}row\.stage < stageCount/)
  })

  it('静止态就明显可辨：当前点放大 + 一圈品牌绿描边，不依赖动画', () => {
    const rule = sliceBetween(STYLE, '.to-stage-dot--cur {', '}')
    // 放大（transform: scale(...) 大于 1）
    const scale = rule.match(/transform:\s*scale\(([\d.]+)\)/)
    expect(scale, `.to-stage-dot--cur 静止态应放大: ${rule}`).not.toBeNull()
    expect(Number(scale[1])).toBeGreaterThan(1)
    // 品牌绿描边（box-shadow 里带 var(--brand)）
    expect(rule).toMatch(/box-shadow:[^;]*var\(--brand\)/)
    // 静止规则本身不挂 animation（呼吸交给 ::after）
    expect(rule).not.toMatch(/\banimation:/)
  })

  it('ripple 由伪元素 ::after 承担，只动 transform + opacity（mp-weixin 可靠插值的属性）', () => {
    const after = sliceBetween(STYLE, '.to-stage-dot--cur::after {', '}')
    expect(after).toContain("content: ''")
    expect(after).toMatch(/position:\s*absolute/)
    expect(after).toMatch(/animation:\s*toStagePing\b/)

    const kf = sliceBetween(STYLE, '@keyframes toStagePing', '\n}')
    expect(kf).toContain('transform')
    expect(kf).toContain('opacity')
    // 关键合规：@keyframes 里不动 box-shadow、不出现 var()。
    expect(kf, 'ripple keyframe 不应动 box-shadow（mp-weixin 动画不可靠插值）').not.toContain('box-shadow')
    expect(kf, '@keyframes 里不应用 var()（自定义属性在 keyframe 内解析不稳）').not.toContain('var(')
    // 也不动会触发重排的属性。
    for (const layoutProp of ['width', 'height', 'margin', 'padding', 'top:', 'left:', 'right:', 'bottom:']) {
      expect(kf, `keyframe 不应动 ${layoutProp}`).not.toContain(layoutProp)
    }
  })

  it('ripple 确实向外扩散并淡出（首帧不透明、末帧透明且更大）', () => {
    const kf = sliceBetween(STYLE, '@keyframes toStagePing', '\n}')
    const scales = [...kf.matchAll(/transform:\s*scale\(([\d.]+)\)/g)].map(m => Number(m[1]))
    const opacities = [...kf.matchAll(/opacity:\s*([\d.]+)/g)].map(m => Number(m[1]))
    expect(Math.max(...scales)).toBeGreaterThan(Math.min(...scales)) // 有外扩
    expect(Math.min(...opacities)).toBe(0) // 末态完全淡出
    expect(Math.max(...opacities)).toBeGreaterThan(0) // 起始可见
  })
})

describe('无障碍 + CSS-only', () => {
  it('尊重 prefers-reduced-motion: reduce —— 停掉 ripple（静止的放大点+描边仍在）', () => {
    expect(STYLE).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
    const mq = sliceBetween(STYLE, '@media (prefers-reduced-motion: reduce)', '\n}')
    expect(mq).toMatch(/\.to-stage-dot--cur::after[\s\S]{0,60}animation:\s*none/)
  })

  it('不靠任何 JS 定时器 / rAF 驱动', () => {
    expect(SCRIPT).not.toContain('setInterval')
    expect(SCRIPT).not.toContain('setTimeout')
    expect(SCRIPT).not.toContain('requestAnimationFrame')
  })
})
