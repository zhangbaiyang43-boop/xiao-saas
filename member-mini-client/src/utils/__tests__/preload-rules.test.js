import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

const sourcePath = (path) => fileURLToPath(new URL(path, import.meta.url))
const pagesConfig = JSON.parse(readFileSync(sourcePath('../../pages.json'), 'utf8'))
const growthSource = readFileSync(sourcePath('../../subpkg-member/pages/growth.vue'), 'utf8')
const memberCardSource = readFileSync(sourcePath('../../subpkg-order/composables/useMemberCard.js'), 'utf8')

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
    }
    expect(growthSource).not.toMatch(/level-lv[123]\.png/)
    expect(memberCardSource).not.toMatch(/level-lv[123]\.png/)
  })
})
