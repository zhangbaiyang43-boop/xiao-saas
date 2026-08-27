import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 「模板用到的 .to-* 类，样式里必须真的存在」。
//
// 起因：一次清理废弃样式时按索引区间删除，`.to-ident` 和 `.to-divider` 之间
// 夹着 `.to-stage` 整块，被一起删掉了。模板照常渲染出 <view class="to-stage">，
// 但没有任何样式，width/height 未定义于是塌成 0 ——菜品左边的四点进度
// 在真机上整个消失，而 lint / 单测 / 构建全部通过，没有任何一环会报错。
//
// 这个测试就是补上那一环：静态比对模板里的类名和样式里的选择器。

const here = path.dirname(fileURLToPath(import.meta.url))
const read = (rel) => fs.readFileSync(path.resolve(here, rel), 'utf8')

const SHEETS = ['../TableBillSheet.vue', '../OrderHistorySheet.vue']
const SHARED_SCSS = '../table-order-card.scss'

// 只取 <template> 部分，避免把 <script>/注释里提到的类名也算进来。
function templateOf(source) {
  const match = source.match(/<template>([\s\S]*)<\/template>/)
  return match ? match[1] : ''
}

function styleOf(source) {
  const match = source.match(/<style[^>]*>([\s\S]*)<\/style>/)
  return match ? match[1] : ''
}

// 从 class="..." / :class="..." 的属性值里挖出 to-* 类名。
// 以 `-` 结尾的是拼接前缀（如 'to-card--' + tone），运行时才成型，跳过。
function usedToClasses(template) {
  const found = new Set()
  const attrRe = /(?::)?class="([^"]*)"/g
  let match
  while ((match = attrRe.exec(template))) {
    for (const token of match[1].match(/to-[a-z0-9-]+/g) || []) {
      if (!token.endsWith('-')) found.add(token)
    }
  }
  return [...found].sort()
}

function definedToClasses(css) {
  return new Set((css.match(/\.to-[a-z0-9-]+/g) || []).map(s => s.slice(1)))
}

describe('本桌订单卡片：模板用到的类都有对应样式', () => {
  const shared = definedToClasses(read(SHARED_SCSS))

  for (const rel of SHEETS) {
    const name = rel.replace('../', '')

    it(`${name} 里没有"有标签但没样式"的 .to-* 类`, () => {
      const source = read(rel)
      const defined = new Set([...shared, ...definedToClasses(styleOf(source))])
      const missing = usedToClasses(templateOf(source)).filter(c => !defined.has(c))
      expect(missing).toEqual([])
    })
  }

  it('四点进度的样式确实存在，并且真的有尺寸（不会塌成 0）', () => {
    const css = read(SHARED_SCSS)
    expect(css).toContain('.to-stage-dot')
    // 塌成 0 就等于不存在——尺寸必须显式写出来。
    const dotBlock = css.match(/\.to-stage-dot\s*\{[^}]*\}/)
    expect(dotBlock).not.toBeNull()
    expect(dotBlock[0]).toMatch(/width:\s*\d+rpx/)
    expect(dotBlock[0]).toMatch(/height:\s*\d+rpx/)

    const wrapBlock = css.match(/\.to-stage\s*\{[^}]*\}/)
    expect(wrapBlock).not.toBeNull()
    expect(wrapBlock[0]).toMatch(/height:\s*\d+rpx/)
  })

  it('进度点整条的高度必须小于菜品缩略图，不能喧宾夺主', () => {
    const css = read(SHARED_SCSS)
    const rpx = (block, prop) => {
      const m = block.match(new RegExp(prop + ':\\s*(\\d+)rpx'))
      return m ? Number(m[1]) : null
    }
    const stage = css.match(/\.to-stage\s*\{[^}]*\}/)[0]
    const img = css.match(/\.to-drow-img\s*\{[^}]*\}/)[0]
    const stageH = rpx(stage, 'height')
    const imgH = rpx(img, 'height')
    expect(stageH).not.toBeNull()
    expect(imgH).not.toBeNull()
    expect(stageH).toBeLessThan(imgH)
  })

  it('上餐后有汇聚成对号的收尾动效，并且尊重系统的"减弱动效"设置', () => {
    const css = read(SHARED_SCSS)
    expect(css).toContain('.to-stage--done')
    expect(css).toContain('.to-stage-check')
    // 汇聚：上下两端的点各自往中心位移
    expect(css).toContain('@keyframes toStageConvergeTop')
    expect(css).toContain('@keyframes toStageConvergeBottom')
    expect(css).toContain('@keyframes toStageCheckIn')
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
  })

  it('点亮态和未点亮态是两种颜色，否则进度看不出来', () => {
    const css = read(SHARED_SCSS)
    const base = css.match(/\.to-stage-dot\s*\{[^}]*background:\s*([^;]+);/)
    const on = css.match(/\.to-stage-dot\.on\s*\{[^}]*background:\s*([^;]+);/)
    expect(base).not.toBeNull()
    expect(on).not.toBeNull()
    expect(on[1].trim()).not.toBe(base[1].trim())
  })
})
