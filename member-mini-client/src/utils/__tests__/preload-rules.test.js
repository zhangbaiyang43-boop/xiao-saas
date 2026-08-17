import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

const sourcePath = (path) => fileURLToPath(new URL(path, import.meta.url))
const pagesConfig = JSON.parse(readFileSync(sourcePath('../../pages.json'), 'utf8'))
const growthSource = readFileSync(sourcePath('../../subpkg-member/pages/growth.vue'), 'utf8')
const memberCardSource = readFileSync(sourcePath('../../subpkg-order/composables/useMemberCard.js'), 'utf8')
const memberCardComponentSource = readFileSync(sourcePath('../../subpkg-order/components/MemberCard.vue'), 'utf8')
const menuSource = readFileSync(sourcePath('../../subpkg-order/pages/menu.vue'), 'utf8')

describe('ordering startup package contracts', () => {
  it('preloads only the ordering package from entry and home', () => {
    expect(pagesConfig.preloadRule['pages/entry/index'].packages).toEqual(['subpkg-order'])
    expect(pagesConfig.preloadRule['pages/index/index'].packages).toEqual(['subpkg-order'])
  })

  it('keeps deferred feature packages registered', () => {
    const roots = pagesConfig.subPackages.map((item) => item.root)
    expect(roots).toEqual(expect.arrayContaining([
      'subpkg-order',
      'subpkg-member',
      'subpkg-coupon',
      'subpkg-common',
    ]))
  })

  it('uses optimized level badges without changing production card backgrounds', () => {
    for (const level of ['lv1', 'lv2', 'lv3']) {
      const webp = `level-${level}.webp`
      expect(existsSync(sourcePath(`../../static/member-levels/${webp}`))).toBe(true)
      expect(growthSource).toContain(webp)
      expect(memberCardSource).toContain(webp)
      expect(growthSource).toContain(`card-bg-${level}.jpg`)
      expect(memberCardSource).toContain(`card-bg-${level}.jpg`)
    }
    expect(growthSource).not.toMatch(/level-lv[123]\.png/)
    expect(memberCardSource).not.toMatch(/level-lv[123]\.png/)
  })

  it('会员身份卡背景 style 从 menu.vue 经 composable 完整传到 MemberCard.vue', () => {
    // 防止再次出现：父组件传了 prop、composable 没产生值、子组件也没消费的断链。
    expect(memberCardSource).toContain('memberIdentityCardStyle')
    expect(memberCardComponentSource).toContain('memberIdentityCardStyle: { type: String')
    expect(memberCardComponentSource).toContain(':style="memberIdentityCardStyle"')
    expect(menuSource).toContain(':member-identity-card-style="memberIdentityCardStyle"')
  })

  it('member-avatar-badge 用固定 rpx 尺寸，不用百分比（微信运行时曾在 flex 交叉轴上把百分比高度塌成 0）', () => {
    expect(memberCardComponentSource).toContain('width: 96rpx; height: 96rpx; display: block;')
    expect(memberCardComponentSource).not.toMatch(/\.member-avatar-badge\s*\{\s*width:\s*96%;\s*height:\s*96%;/)
  })

  it('member-avatar-badge 的数据合同（prop + WXML 绑定）保持不变', () => {
    expect(memberCardComponentSource).toContain("memberLevelBadgeSrc: { type: String, default: '' }")
    expect(memberCardComponentSource).toContain('class="member-avatar-badge"')
    expect(memberCardComponentSource).toContain(':src="memberLevelBadgeSrc"')
  })
})
