import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 「本桌订单」每道菜进度点竖排里「当前那个点」的呼吸指示合同。
//
// 早期版本试过一条横排「待接单 / 制作中 / 已上齐」三阶段文字条（.to-progress /
// tableProgress / progressStepClass / @keyframes toBreathe），真机上看不出效果、
// 也不是产品想要的。已整条移除，改为：每道菜自己那一竖排 .to-stage-dot 里，
// 「当前那一步」（= 最后一个亮点，row.stage === n 且这道菜还没上齐）做一次
// 极慢的 opacity + scale 呼吸，类似任务状态指示灯。
//
// 测试环境是 node（无 jsdom / @vue/test-utils），SFC 不挂载 —— SOURCE CONTRACT：
// 锁结构（哪个点带 --cur、有 keyframe、尊重减弱动效、不动布局、无 JS 计时器），
// 逐帧视觉参数（时长 / 具体 opacity / scale / 颜色）不锁，留安全微调空间。

const here = path.dirname(fileURLToPath(import.meta.url))
const SRC = fs.readFileSync(path.resolve(here, '../TableBillSheet.vue'), 'utf8')

// 稳定分区：不用会被内嵌 <template v-if> 截断的贪婪正则。
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
    expect(TEMPLATE).not.toContain('待接单')
    expect(TEMPLATE).not.toContain('制作中')
  })
})

describe('当前进行中的那道菜：进度点竖排里「当前点」呼吸', () => {
  it('只有 row.stage === n 且这道菜还没上齐(< stageCount) 的那个点带 --cur', () => {
    // 提取 .to-stage-dot 的 v-for class 绑定那一段。
    const dot = sliceBetween(TEMPLATE, 'class="to-stage-dot"', '></view>')
    // 亮点仍是 row.stage >= n。
    expect(dot).toMatch(/on:\s*row\.stage >= n/)
    // 当前点用「恰好等于」，不是「>=」—— 同一竖排至多一个点在呼吸。
    expect(dot).toMatch(/to-stage-dot--cur['"]?\s*:\s*row\.stage === n/)
    // 且排除已上齐的菜（那走汇聚成对号的收尾动效）。
    expect(dot).toMatch(/to-stage-dot--cur[\s\S]{0,60}row\.stage < stageCount/)
  })

  it('.to-stage-dot--cur 有一条 animation 规则，引用 toStagePulse', () => {
    const rule = sliceBetween(STYLE, '.to-stage-dot--cur {', '}')
    expect(rule).toMatch(/animation:\s*toStagePulse\b/)
  })

  it('@keyframes toStagePulse 存在，且只动 opacity + transform（不触发重排）', () => {
    const kf = sliceBetween(STYLE, '@keyframes toStagePulse', '\n}')
    expect(kf).toContain('opacity')
    expect(kf).toContain('transform')
    for (const layoutProp of ['width', 'height', 'margin', 'padding', 'top:', 'left:', 'right:', 'bottom:']) {
      expect(kf, `keyframe 不应动 ${layoutProp}`).not.toContain(layoutProp)
    }
  })
})

describe('无障碍 + CSS-only', () => {
  it('尊重 prefers-reduced-motion: reduce —— 停掉 --cur 的动画', () => {
    expect(STYLE).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
    const mq = sliceBetween(STYLE, '@media (prefers-reduced-motion: reduce)', '\n}')
    expect(mq).toMatch(/\.to-stage-dot--cur[\s\S]{0,40}animation:\s*none/)
  })

  it('呼吸不靠任何 JS 定时器 / rAF 驱动', () => {
    expect(SCRIPT).not.toContain('setInterval')
    expect(SCRIPT).not.toContain('setTimeout')
    expect(SCRIPT).not.toContain('requestAnimationFrame')
  })
})
