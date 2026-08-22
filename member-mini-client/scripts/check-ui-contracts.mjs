#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

// F1B overlay contract only. Do not expand into hex / button / typography scans.
const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../src')

export function stripCssComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:\\\n])\/\/.*$/gm, '$1')
}

export function isRawBlockingOverlaySource(source) {
  const stripped = stripCssComments(source)
  return /position\s*:\s*fixed/.test(stripped)
    && /inset\s*:\s*0/.test(stripped)
    && /z-index\s*:/.test(stripped)
}

export const RAW_BLOCKING_ALLOWLIST = new Set([
  'components/base-overlay/base-overlay.vue',
  'subpkg-order/styles/_shared.scss',
  'subpkg-order/components/LoadingStates.vue',
  'subpkg-order/components/WelcomeCouponSheet.vue',
  'subpkg-common/pages/verify-qr.vue',
])

const MIGRATED_OFF_MASK = [
  'subpkg-order/components/MemberCheckoutChoice.vue',
  'subpkg-order/components/CheckoutAuthSheet.vue',
]

const walk = (dir, acc = []) => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'miniprogram_npm' || entry.name === 'uni_modules' || entry.name === 'node_modules') continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, acc)
    else acc.push(full)
  }
  return acc
}

const rel = (file) => path.relative(srcRoot, file).split(path.sep).join('/')

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
const importsShared = (source) => /@import\s+['"][^'"]*_shared\.scss['"]/.test(source)

export function checkUiContracts(root = srcRoot) {
  const FAIL = []
  const vueFiles = walk(root).filter((file) => file.endsWith('.vue'))
  const scssFiles = walk(root).filter((file) => file.endsWith('.scss'))

  for (const file of vueFiles) {
    const source = fs.readFileSync(file, 'utf8')
    const name = path.relative(root, file).split(path.sep).join('/')

    if (MIGRATED_OFF_MASK.includes(name) && hasExactClassToken(source, 'mask')) {
      FAIL.push(`${name}: migrated overlay must not keep exact class token "mask"`)
    }

    if (hasExactClassToken(source, 'mask') && !importsShared(source) && name !== 'components/base-overlay/base-overlay.vue') {
      FAIL.push(`${name}: exact class token "mask" requires @import of _shared.scss`)
    }
  }

  for (const file of [...vueFiles, ...scssFiles]) {
    const source = fs.readFileSync(file, 'utf8')
    const name = path.relative(root, file).split(path.sep).join('/')
    if (RAW_BLOCKING_ALLOWLIST.has(name)) continue
    if (isRawBlockingOverlaySource(source)) {
      FAIL.push(`${name}: raw blocking overlay (position:fixed + inset:0 + z-index) is outside BaseOverlay / explicit legacy allowlist`)
    }
  }

  return FAIL
}

function isDirectRun() {
  if (!process.argv[1]) return false
  try {
    return import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
  } catch {
    return false
  }
}

if (isDirectRun()) {
  const FAIL = checkUiContracts()
  if (FAIL.length) {
    console.error('UI contract check failed:')
    for (const line of FAIL) console.error(' - ' + line)
    process.exit(1)
  }
  console.log('UI contract check passed.')
}
