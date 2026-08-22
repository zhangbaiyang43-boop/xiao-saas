import { describe, expect, it } from 'vitest'
import { mkdtempSync, writeFileSync, mkdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  checkUiContracts,
  isRawBlockingOverlaySource,
  hasExactClassToken,
  workflowHasRequiredGates,
} from '../check-ui-contracts.mjs'

const repoRoot = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '../../..')
const workflowPath = path.join(repoRoot, '.github/workflows/member-mini-client-ci.yml')
const overlayContractPath = path.resolve(
  fileURLToPath(new URL('.', import.meta.url)),
  '../../src/subpkg-order/components/__tests__/overlay-authority.contract.test.js',
)

function writeRel(root, rel, contents) {
  const full = path.join(root, rel)
  mkdirSync(path.dirname(full), { recursive: true })
  writeFileSync(full, contents)
}

function fixtureRoot() {
  const root = mkdtempSync(path.join(tmpdir(), 'f1c-contracts-'))
  writeRel(root, 'components/base-overlay/base-overlay.vue', '<template></template>\n')
  writeRel(root, 'subpkg-order/styles/_shared.scss', '.mask { position: fixed; inset: 0; z-index: var(--z-blocking); }\n')
  writeRel(root, 'styles/global.scss', 'page { --z-blocking: 3100; }\n')
  return root
}

function optionsFor(root, extra = {}) {
  return {
    overlayAuthority: 'components/base-overlay/base-overlay.vue',
    semanticZAllowlist: ['components/base-overlay/base-overlay.vue', 'subpkg-order/styles/_shared.scss'],
    rawBlockingAllowlist: extra.rawBlockingAllowlist ?? ['subpkg-order/styles/_shared.scss'],
    maskAllowlist: extra.maskAllowlist ?? [],
    blockingFloor: extra.blockingFloor ?? 3100,
    ...extra,
  }
}

describe('F1C frontend CI / UI contracts', () => {
  it('TEST 01: new class="mask" + shared import not on allowlist fails', () => {
    const root = fixtureRoot()
    writeRel(root, 'subpkg-order/components/NewBadSheet.vue', `
<template>
  <view class="mask"></view>
</template>
<style lang="scss">
@import '../styles/_shared.scss';
</style>
`)
    const fail = checkUiContracts(root, optionsFor(root))
    expect(fail.some((line) => line.includes('NewBadSheet.vue') && line.includes('LEGACY_MASK_ALLOWLIST'))).toBe(true)
  })

  it('TEST 02: allowlisted exact mask + shared import passes mask rule', () => {
    const root = fixtureRoot()
    writeRel(root, 'subpkg-order/components/CheckoutSheet.vue', `
<template>
  <view class="mask"></view>
</template>
<style lang="scss">
@import '../styles/_shared.scss';
</style>
`)
    const fail = checkUiContracts(root, optionsFor(root, {
      maskAllowlist: ['subpkg-order/components/CheckoutSheet.vue'],
    }))
    expect(fail.filter((line) => line.includes('CheckoutSheet.vue'))).toEqual([])
  })

  it('TEST 03: allowlisted exact mask without shared import fails', () => {
    const root = fixtureRoot()
    writeRel(root, 'subpkg-order/components/CheckoutSheet.vue', `
<template>
  <view class="mask"></view>
</template>
`)
    const fail = checkUiContracts(root, optionsFor(root, {
      maskAllowlist: ['subpkg-order/components/CheckoutSheet.vue'],
    }))
    expect(fail.some((line) => line.includes('CheckoutSheet.vue') && line.includes('_shared.scss'))).toBe(true)
  })

  it('TEST 04: inset fullscreen + numeric z-index fails', () => {
    expect(isRawBlockingOverlaySource('.evil { position: fixed; inset: 0; z-index: 3200; }')).toBe(true)
  })

  it('TEST 05: inset fullscreen + token z-index fails', () => {
    expect(isRawBlockingOverlaySource('.evil { position: fixed; inset: 0; z-index: var(--z-blocking-top); }')).toBe(true)
  })

  it('TEST 06: four-edge fullscreen + token z-index fails', () => {
    expect(isRawBlockingOverlaySource(`
      .evil {
        position: fixed;
        top: 0;
        right: 0;
        bottom: 0;
        left: 0;
        z-index: var(--z-blocking-top);
      }
    `)).toBe(true)
    const root = fixtureRoot()
    writeRel(root, 'pages/BadFourEdge.vue', `
<style>
.evil { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: var(--z-blocking-top); }
</style>
`)
    const fail = checkUiContracts(root, optionsFor(root))
    expect(fail.some((line) => line.includes('BadFourEdge.vue'))).toBe(true)
  })

  it('TEST 07: bottom chrome z-index 300 is not a blocking overlay', () => {
    expect(isRawBlockingOverlaySource(`
      .bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; z-index: 300; }
    `)).toBe(false)
    const root = fixtureRoot()
    writeRel(root, 'subpkg-order/components/BottomNav.vue', `
<style>
.bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; z-index: 300; }
</style>
`)
    const fail = checkUiContracts(root, optionsFor(root))
    expect(fail.filter((line) => line.includes('BottomNav.vue'))).toEqual([])
  })

  it('TEST 08: loading-mask is not exact token mask', () => {
    expect(hasExactClassToken('<view class="loading-mask"></view>', 'mask')).toBe(false)
    const root = fixtureRoot()
    writeRel(root, 'subpkg-order/components/LoadingStates.vue', `<template><view class="loading-mask"></view></template>`)
    const fail = checkUiContracts(root, optionsFor(root, {
      rawBlockingAllowlist: ['subpkg-order/styles/_shared.scss', 'subpkg-order/components/LoadingStates.vue'],
    }))
    expect(fail.filter((line) => line.includes('exact class token "mask"'))).toEqual([])
  })

  it('TEST 09: commented fullscreen overlay is not a hit', () => {
    expect(isRawBlockingOverlaySource(`
      /* .evil { position: fixed; inset: 0; z-index: 3200; } */
      .ok { color: red; }
    `)).toBe(false)
  })

  it('TEST 10: dead allowlist path fails the gate', () => {
    const root = fixtureRoot()
    const fail = checkUiContracts(root, optionsFor(root, {
      maskAllowlist: ['subpkg-order/components/DoesNotExist.vue'],
    }))
    expect(fail.some((line) => line.includes('dead allowlist') && line.includes('DoesNotExist.vue'))).toBe(true)
  })

  it('numeric z-index at blocking floor is rejected outside exceptions', () => {
    const root = fixtureRoot()
    writeRel(root, 'pages/HighZ.vue', `.chip { z-index: 9999; }`)
    const fail = checkUiContracts(root, optionsFor(root))
    expect(fail.some((line) => line.includes('HighZ.vue') && line.includes('9999'))).toBe(true)
  })

  it('workflow source currently contains required F1C gates', () => {
    const workflow = readFileSync(workflowPath, 'utf8')
    const gates = workflowHasRequiredGates(workflow)
    expect(gates.lint).toBe(true)
    expect(gates.uiContracts).toBe(true)
    expect(gates.unit).toBe(true)
    expect(gates.h5).toBe(true)
    expect(gates.mpWeixin).toBe(true)
    expect(gates.rawUniMp).toBe(false)
    expect(gates.pushMain).toBe(true)
    expect(gates.pullRequestMain).toBe(true)
    expect(gates.pushPathMini).toBe(true)
    expect(gates.pushPathWorkflow).toBe(true)
    expect(gates.prPathMini).toBe(true)
    expect(gates.prPathWorkflow).toBe(true)
    expect(gates.workingDirectory).toBe(true)
    expect(gates.node20).toBe(true)
    expect(gates.npmCi).toBe(true)
  })

  it('deleting Build (mp-weixin) from a workflow fixture fails the contract helper', () => {
    const workflow = readFileSync(workflowPath, 'utf8')
    const stripped = workflow.replace(/npm run build:mp-weixin/g, '')
    expect(workflowHasRequiredGates(stripped).mpWeixin).toBe(false)
    expect(workflowHasRequiredGates(workflow).mpWeixin).toBe(true)
  })

  it('CASE A: push branches cannot borrow pull_request main', () => {
    const yaml = `
on:
  push:
    branches: [develop]
    paths:
      - 'member-mini-client/**'
      - '.github/workflows/member-mini-client-ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'member-mini-client/**'
      - '.github/workflows/member-mini-client-ci.yml'
`
    const gates = workflowHasRequiredGates(yaml)
    expect(gates.pushMain).toBe(false)
    expect(gates.pullRequestMain).toBe(true)
  })

  it('CASE B: push path loss is independent of pull_request paths', () => {
    const yaml = `
on:
  push:
    branches: [main]
    paths:
      - '.github/workflows/member-mini-client-ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'member-mini-client/**'
      - '.github/workflows/member-mini-client-ci.yml'
`
    const gates = workflowHasRequiredGates(yaml)
    expect(gates.pushPathMini).toBe(false)
    expect(gates.prPathMini).toBe(true)
    expect(gates.pushPathWorkflow).toBe(true)
  })

  it('CASE C: pull_request workflow path loss is independent of push', () => {
    const yaml = `
on:
  push:
    branches: [main]
    paths:
      - 'member-mini-client/**'
      - '.github/workflows/member-mini-client-ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'member-mini-client/**'
`
    const gates = workflowHasRequiredGates(yaml)
    expect(gates.pushPathWorkflow).toBe(true)
    expect(gates.prPathWorkflow).toBe(false)
  })

  it('rejects direct uni mp-weixin commands and allows the package script', () => {
    const wrap = (run) => `
jobs:
  x:
    steps:
      - run: ${run}
`
    expect(workflowHasRequiredGates(wrap('uni build -p mp-weixin')).rawUniMp).toBe(true)
    expect(workflowHasRequiredGates(wrap('npx uni build -p mp-weixin')).rawUniMp).toBe(true)
    expect(workflowHasRequiredGates(wrap('npm exec uni -- build -p mp-weixin')).rawUniMp).toBe(true)
    expect(workflowHasRequiredGates(wrap('npm run build:mp-weixin')).rawUniMp).toBe(false)
    expect(workflowHasRequiredGates(wrap('npm run build:mp-weixin')).mpWeixin).toBe(true)
  })

  it('comment-only npm run build:mp-weixin is not a CI gate', () => {
    const yaml = `
jobs:
  x:
    steps:
      - name: Build
        # npm run build:mp-weixin
        run: npm run lint
`
    const gates = workflowHasRequiredGates(yaml)
    expect(gates.mpWeixin).toBe(false)
    expect(gates.lint).toBe(true)
  })

  it('TEST A: commented branches:[main] does not prove pushMain', () => {
    const yaml = `
on:
  push:
    branches: [develop]
    # branches: [main]
  pull_request:
    branches: [main]
`
    const gates = workflowHasRequiredGates(yaml)
    expect(gates.pushMain).toBe(false)
    expect(gates.pullRequestMain).toBe(true)
  })

  it('TEST B: commented member-mini-client path does not prove pushPathMini', () => {
    const yaml = `
on:
  push:
    branches: [main]
    paths:
      # - 'member-mini-client/**'
      - '.github/workflows/member-mini-client-ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'member-mini-client/**'
      - '.github/workflows/member-mini-client-ci.yml'
`
    const gates = workflowHasRequiredGates(yaml)
    expect(gates.pushPathMini).toBe(false)
    expect(gates.pushPathWorkflow).toBe(true)
  })

  it('TEST C: main-old is not the main branch token', () => {
    const yaml = `
on:
  push:
    branches: [main-old]
    paths:
      - 'member-mini-client/**'
  pull_request:
    branches: [main]
`
    const gates = workflowHasRequiredGates(yaml)
    expect(gates.pushMain).toBe(false)
    expect(gates.pullRequestMain).toBe(true)
  })
})

describe('F1B overlay authority regression still present', () => {
  it('keeps overlay-authority.contract.test.js in the tree', () => {
    expect(readFileSync(overlayContractPath, 'utf8')).toContain('TEST L: raw overlay detector rejects numeric and token z-index alike')
  })
})
