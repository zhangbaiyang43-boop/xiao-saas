import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { isRawBlockingOverlaySource } from '../../../../scripts/check-ui-contracts.mjs'

// STATIC overlay-authority contract. This file proves source structure and
// token inequality. It does not mount components or read computed CSS, and
// must not be treated as runtime visual proof on mp-weixin.

const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../../../')

const read = (rel) => readFileSync(path.join(srcRoot, rel), 'utf8')

const extractClassTokens = (source) => {
  const tokens = []
  const classAttr = /(?:^|\s)(?:class|:class)=["']([^"']+)["']/g
  let match
  while ((match = classAttr.exec(source))) {
    for (const raw of match[1].split(/\s+/)) {
      const token = raw.replace(/^[^A-Za-z0-9_-]+|[^A-Za-z0-9_-]+$/g, '')
      if (token) tokens.push(token)
    }
  }
  return tokens
}

const hasExactClassToken = (source, token) => extractClassTokens(source).includes(token)

const readCssVarPx = (source, name) => {
  const match = source.match(new RegExp(`${name}\\s*:\\s*(\\d+)\\s*;`))
  expect(match, `${name} numeric token missing`).toBeTruthy()
  return Number(match[1])
}

describe('overlay authority contract (static)', () => {
  const choice = read('subpkg-order/components/MemberCheckoutChoice.vue')
  const auth = read('subpkg-order/components/CheckoutAuthSheet.vue')
  const overlay = read('components/base-overlay/base-overlay.vue')
  const shared = read('subpkg-order/styles/_shared.scss')
  const global = read('styles/global.scss')

  it('TEST A: MemberCheckoutChoice imports BaseOverlay', () => {
    expect(choice).toMatch(/import\s+BaseOverlay\s+from\s+['"]@\/components\/base-overlay\/base-overlay\.vue['"]/)
    expect(choice).toMatch(/components\s*:\s*\{[\s\S]*BaseOverlay/)
  })

  it('TEST B: MemberCheckoutChoice uses layer="blocking-top"', () => {
    expect(choice).toMatch(/layer=["']blocking-top["']/)
  })

  it('TEST C: MemberCheckoutChoice has no exact mask class token', () => {
    expect(hasExactClassToken(choice, 'mask')).toBe(false)
  })

  it('TEST D: CheckoutAuthSheet uses BaseOverlay blocking-top and has no exact mask class token', () => {
    expect(auth).toMatch(/import\s+BaseOverlay\s+from\s+['"]@\/components\/base-overlay\/base-overlay\.vue['"]/)
    expect(auth).toMatch(/components\s*:\s*\{[\s\S]*BaseOverlay/)
    expect(auth).toMatch(/layer=["']blocking-top["']/)
    expect(hasExactClassToken(auth, 'mask')).toBe(false)
  })

  it('TEST E: legacy _shared .mask uses var(--z-blocking)', () => {
    expect(shared).toMatch(/\.mask\s*\{[\s\S]*?z-index:\s*var\(--z-blocking\)/)
    expect(shared).toMatch(/\.mask\s*\{[\s\S]*?background:\s*var\(--overlay-dim\)/)
    expect(shared).not.toMatch(/\.mask\s*\{[\s\S]*?z-index:\s*3100/)
  })

  it('TEST F: BaseOverlay blocking-top maps var(--z-blocking-top)', () => {
    expect(overlay).toMatch(/base-overlay--blocking-top[\s\S]*z-index:\s*var\(--z-blocking-top\)/)
    expect(overlay).toMatch(/base-overlay--blocking[^{\n]*\{[\s\S]*z-index:\s*var\(--z-blocking\)/)
    expect(overlay).toMatch(/base-overlay--critical[\s\S]*z-index:\s*var\(--z-critical\)/)
    expect(overlay).not.toMatch(/align-items:\s*flex-end/)
    expect(overlay).not.toMatch(/styleIsolation/)
    expect(overlay).toMatch(/virtualHost:\s*true/)
  })

  it('TEST G: token numeric relation blocking-top > blocking and critical > blocking-top', () => {
    const blocking = readCssVarPx(global, '--z-blocking')
    const blockingTop = readCssVarPx(global, '--z-blocking-top')
    const critical = readCssVarPx(global, '--z-critical')
    const chrome = readCssVarPx(global, '--z-chrome')
    const floating = readCssVarPx(global, '--z-floating')
    expect(chrome).toBe(300)
    expect(floating).toBe(850)
    expect(blocking).toBe(3100)
    expect(blockingTop).toBe(3200)
    expect(critical).toBe(4000)
    expect(chrome).toBeLessThan(floating)
    expect(floating).toBeLessThan(blocking)
    expect(blockingTop).toBeGreaterThan(blocking)
    expect(critical).toBeGreaterThan(blockingTop)
    expect(global).toMatch(/--overlay-dim:\s*rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\.5\s*\)/)
  })

  it('TEST H: MemberCheckoutChoice keeps getPhoneNumber and emit contracts', () => {
    expect(choice).toContain('open-type="getPhoneNumber"')
    expect(choice).toContain("'getphonenumber'")
    expect(choice).toContain("'guest-pay'")
    expect(choice).toContain("'cancel'")
    expect(choice).toContain("'open-agreement'")
    expect(choice).toContain('@getphonenumber="$emit(\'getphonenumber\', $event)"')
    expect(choice).toContain('background: var(--brand)')
    expect(choice).not.toContain('#16c76f')
  })

  it('TEST I: CheckoutAuthSheet keeps getPhoneNumber and emit contracts', () => {
    expect(auth).toContain('open-type="getPhoneNumber"')
    expect(auth).toContain("'getphonenumber'")
    expect(auth).toContain("'cancel'")
    expect(auth).toContain('@getphonenumber="$emit(\'getphonenumber\', $event)"')
  })

  it('TEST J: BaseOverlay owns backdrop mask-click without slot @click.stop', () => {
    expect(overlay).toMatch(/class="base-overlay-backdrop"\s+@click="\$emit\('mask-click'\)"/)
    const rootOpen = overlay.match(/<view[\s\S]*?class="base-overlay"[\s\S]*?>/)
    expect(rootOpen, 'BaseOverlay root opening tag missing').toBeTruthy()
    expect(rootOpen[0]).not.toContain('@click')
    expect(choice).not.toMatch(/<view class="member-choice-sheet"[^>]*@click/)
    expect(auth).not.toMatch(/<view class="checkout-auth-sheet"[^>]*@click/)
    expect(choice).not.toContain('member-choice-layout')
    expect(auth).not.toContain('checkout-auth-layout')
  })

  it('TEST K: business sheets keep local bottom placement without overlay geometry', () => {
    expect(choice).toMatch(/\.member-choice-sheet\s*\{[^}]*position:\s*absolute/)
    expect(choice).toMatch(/\.member-choice-sheet\s*\{[^}]*bottom:\s*0/)
    expect(choice).not.toMatch(/\.member-choice-sheet\s*\{[^}]*position:\s*fixed/)
    expect(choice).not.toMatch(/\.member-choice-sheet\s*\{[^}]*inset:\s*0/)
    expect(auth).toMatch(/\.checkout-auth-sheet\s*\{[^}]*position:\s*absolute/)
    expect(auth).toMatch(/\.checkout-auth-sheet\s*\{[^}]*bottom:\s*0/)
    expect(auth).not.toMatch(/\.checkout-auth-sheet\s*\{[^}]*position:\s*fixed/)
  })

  it('TEST L: raw overlay detector rejects numeric and token z-index alike', () => {
    expect(isRawBlockingOverlaySource(`
      .evil { position: fixed; inset: 0; z-index: 3200; }
    `)).toBe(true)
    expect(isRawBlockingOverlaySource(`
      .evil { position: fixed; inset: 0; z-index: var(--z-blocking-top); }
    `)).toBe(true)
    expect(isRawBlockingOverlaySource(`
      @import '../styles/_shared.scss';
      .evil { position: fixed; inset: 0; z-index: var(--z-blocking-top); }
    `)).toBe(true)
    expect(isRawBlockingOverlaySource(`
      .chrome { position: fixed; bottom: 0; z-index: 300; }
    `)).toBe(false)
  })
})
