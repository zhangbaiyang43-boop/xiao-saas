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

  it('growth.vue 和 useMemberCard.js 的等级背景图（jpg）保持一致，不受徽章格式影响', () => {
    for (const level of ['lv1', 'lv2', 'lv3']) {
      expect(existsSync(sourcePath(`../../static/member-levels/card-bg-${level}.jpg`))).toBe(true)
      expect(growthSource).toContain(`card-bg-${level}.jpg`)
      expect(memberCardSource).toContain(`card-bg-${level}.jpg`)
    }
  })

  it('MemberCard 的等级徽章用 PNG：同名 WebP 在真机微信运行时被证实 404（RGB 无 alpha、丢失透明通道），' +
    'PNG 是 WebP 性能优化之前最后一版已验证可用的版本，V1 稳定性优先于包体大小', () => {
    for (const level of ['lv1', 'lv2', 'lv3']) {
      expect(existsSync(sourcePath(`../../static/member-levels/level-${level}.png`))).toBe(true)
      expect(memberCardSource).toContain(`level-${level}.png`)
    }
    expect(memberCardSource).not.toMatch(/level-lv[123]\.webp/)
    // growth.vue 的等级徽章目前仍是 WebP——跟 MemberCard 曾经的问题同一个根因，
    // 本轮按范围限制未修复，是已知的后续工作，不是遗漏。
    expect(growthSource).toContain('level-lv1.webp')
  })

  it('会员徽章 PNG 文件本身能真实解码：PNG 签名 + IHDR 尺寸都合法（不引入图片解析依赖，直接读文件头）', () => {
    const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
    for (const level of ['lv1', 'lv2', 'lv3']) {
      const buf = readFileSync(sourcePath(`../../static/member-levels/level-${level}.png`))
      expect(buf.length).toBeGreaterThan(PNG_SIGNATURE.length)
      expect(buf.subarray(0, 8).equals(PNG_SIGNATURE)).toBe(true)
      // IHDR is always the first chunk: bytes 8-11 length, 12-15 "IHDR", 16-19 width, 20-23 height (big-endian)
      expect(buf.subarray(12, 16).toString('ascii')).toBe('IHDR')
      const width = buf.readUInt32BE(16)
      const height = buf.readUInt32BE(20)
      expect(width).toBeGreaterThan(0)
      expect(height).toBeGreaterThan(0)
      expect(width).toBe(height) // 已知这批徽章素材是方形画布
    }
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

  it('WebP 404 排查用的临时 A/B 诊断代码已经清理干净，不带进正式版本', () => {
    expect(memberCardComponentSource).not.toContain('DEBUG_USE_JPG_BADGE_FOR_LOAD_TEST')
    expect(memberCardComponentSource).not.toContain('debugMemberBadgeSrc')
    expect(memberCardComponentSource).not.toContain('MEMBER_BADGE_LOAD_OK')
    expect(memberCardComponentSource).not.toContain('MEMBER_BADGE_LOAD_ERROR')
    expect(memberCardComponentSource).not.toContain('@load')
    expect(memberCardComponentSource).not.toContain('@error')
  })
})
