import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 右侧菜品区「分类区块头」的展示合同。
//
// 定向修复：右侧每个分类区块原本是 图标 + 名称 + 两段横线，信息与左侧 rail 重复。
// 现在右侧只留一条 hairline 分隔，图标和名称都移除；左侧 rail 仍是纯文字分类，
// 区块 anchor（左点跳转 / 右侧 scroll-spy 的目标）保持不变。
//
// 这个文件只保护「右侧呈现」+「anchor 还在」。左点滚动、scroll-spy 的深层行为
// 由 useCategoryScroll.test.js 负责，这里不重复锁。
// 像素值（线宽 / 间距 / 颜色）故意不锁。

const here = path.dirname(fileURLToPath(import.meta.url))
const SRC = fs.readFileSync(path.resolve(here, '../DishList.vue'), 'utf8')

// §31 分区：左 rail 里「分类名称」是合法存在的，所以不能对整份源码做
// notContains(分类名称) 这类断言——必须把左右两块分开看。
const navStart = SRC.indexOf('class="category-nav"')
const scrollStart = SRC.indexOf('class="dish-scroll"')
const rightForStart = SRC.indexOf('v-for="cat in categories"', scrollStart)
const rightEnd = SRC.indexOf('</scroll-view>', rightForStart)

const LEFT_RAIL = SRC.slice(navStart, scrollStart)
const RIGHT_LIST = SRC.slice(rightForStart, rightEnd)

describe('分区提取自身是稳定的', () => {
  it('左 rail 区块与右侧列表区块都能定位，且不相交', () => {
    expect(navStart).toBeGreaterThan(-1)
    expect(scrollStart).toBeGreaterThan(navStart)
    expect(rightForStart).toBeGreaterThan(scrollStart)
    expect(rightEnd).toBeGreaterThan(rightForStart)
  })
})

describe('右侧分类区块头：只剩一条分隔线', () => {
  it('DIVIDER_PRESENT —— 右侧仍有 cat-divider 分隔', () => {
    expect(RIGHT_LIST).toContain('class="cat-divider"')
  })

  it('RIGHT_ICON_ABSENT —— 右侧分类头不再渲染图标', () => {
    expect(RIGHT_LIST).not.toContain('cat-divider-icon')
    expect(RIGHT_LIST).not.toContain('categoryIconClass')
  })

  it('RIGHT_NAME_ABSENT —— 右侧分类头不再渲染名称', () => {
    expect(RIGHT_LIST).not.toContain('cat-divider-text')
  })
})

describe('anchor 保留（轻 guard）', () => {
  it('ANCHOR_LIGHT_GUARD —— 右侧分类 section wrapper 仍带 :id="categoryAnchorId(cat)"', () => {
    expect(RIGHT_LIST).toContain(':id="categoryAnchorId(cat)"')
  })
})

describe('左侧 rail 未被误删', () => {
  it('LEFT_RAIL_PRESENCE —— 左侧仍是纯文字分类（cat-name + categoryDisplayName）', () => {
    expect(LEFT_RAIL).toContain('cat-name')
    expect(LEFT_RAIL).toContain('categoryDisplayName')
  })
})
