#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

// Frontend Constitution V1 / F1C overlay + layer contract.
// Do not expand into hex / button / typography scans.
const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../src')

export const BASE_OVERLAY_AUTHORITY = 'components/base-overlay/base-overlay.vue'

export const LEGACY_MASK_ALLOWLIST = [
  'subpkg-order/components/CheckoutSheet.vue',
  'subpkg-order/components/CouponPicker.vue',
  'subpkg-order/components/PaymentSuccessSheet.vue',
  'subpkg-order/components/SpecSheet.vue',
  'subpkg-order/components/WelcomeCouponSheet.vue',
]

export const LEGACY_RAW_BLOCKING_ALLOWLIST = [
  'subpkg-order/styles/_shared.scss',
  'subpkg-order/components/LoadingStates.vue',
  'subpkg-order/components/WelcomeCouponSheet.vue',
  'subpkg-common/pages/verify-qr.vue',
  'subpkg-member/pages/profile-edit.vue',
]

export const SEMANTIC_Z_ALLOWLIST = [
  BASE_OVERLAY_AUTHORITY,
  'subpkg-order/styles/_shared.scss',
]

export function stripCssComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:\\\n])\/\/.*$/gm, '$1')
}

function cssRules(source) {
  return stripCssComments(source).split('}')
}

function hasFourEdgeZero(block) {
  return /top\s*:\s*0/.test(block)
    && /right\s*:\s*0/.test(block)
    && /bottom\s*:\s*0/.test(block)
    && /left\s*:\s*0/.test(block)
}

export function isRawBlockingOverlaySource(source) {
  return cssRules(source).some((block) => {
    const hasFixed = /position\s*:\s*fixed/.test(block)
    const hasZ = /z-index\s*:/.test(block)
    const fullscreen = /inset\s*:\s*0/.test(block) || hasFourEdgeZero(block)
    return hasFixed && hasZ && fullscreen
  })
}

export function extractClassTokens(source) {
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

export function hasExactClassToken(source, token) {
  return extractClassTokens(source).includes(token)
}

export function importsShared(source) {
  return /@import\s+['"][^'"]*_shared\.scss['"]/.test(source)
}

export function readBlockingFloor(scssSource) {
  const match = scssSource.match(/--z-blocking\s*:\s*(\d+)\s*;/)
  if (!match) {
    throw new Error('blocking floor token --z-blocking missing from global.scss')
  }
  return Number(match[1])
}

function workflowLines(workflowSource) {
  return String(workflowSource).replace(/\r\n/g, '\n').split('\n')
}

export function extractTopLevelOnEventBlock(workflowSource, eventName) {
  const lines = workflowLines(workflowSource)
  let onStart = -1
  for (let i = 0; i < lines.length; i++) {
    if (/^on:\s*(#.*)?$/.test(lines[i])) {
      onStart = i
      break
    }
  }
  if (onStart < 0) return ''

  let onEnd = lines.length
  for (let i = onStart + 1; i < lines.length; i++) {
    const trimmed = lines[i].trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    if (/^\S/.test(lines[i])) {
      onEnd = i
      break
    }
  }

  const onBlock = lines.slice(onStart + 1, onEnd)
  const eventRe = new RegExp(`^  ${eventName}:\\s*(#.*)?$`)
  let eventStart = -1
  for (let i = 0; i < onBlock.length; i++) {
    if (eventRe.test(onBlock[i])) {
      eventStart = i
      break
    }
  }
  if (eventStart < 0) return ''

  let eventEnd = onBlock.length
  for (let i = eventStart + 1; i < onBlock.length; i++) {
    const trimmed = onBlock[i].trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    if (/^  [A-Za-z_][\w-]*:/.test(onBlock[i])) {
      eventEnd = i
      break
    }
  }
  return onBlock.slice(eventStart, eventEnd).join('\n')
}

function stripInlineComment(value) {
  const hash = value.indexOf('#')
  return (hash === -1 ? value : value.slice(0, hash)).trim()
}

export function extractWorkflowRunCommands(workflowSource) {
  const lines = workflowLines(workflowSource)
  const commands = []
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().startsWith('#')) continue
    const match = lines[i].match(/^(\s*)(?:-\s+)?run:\s*(.*)$/)
    if (!match) continue
    const indent = match[1].length
    const rest = stripInlineComment(match[2])
    if (!rest) continue
    if (rest === '|' || rest === '>') {
      const collected = []
      for (let j = i + 1; j < lines.length; j++) {
        if (lines[j].trim().startsWith('#')) continue
        const nextIndent = lines[j].match(/^(\s*)/)[1].length
        if (lines[j].trim() && nextIndent <= indent) break
        const piece = stripInlineComment(lines[j])
        if (piece) collected.push(piece)
      }
      if (collected.length) commands.push(collected.join(' '))
      continue
    }
    commands.push(rest)
  }
  return commands
}

function eventActiveLines(block) {
  return String(block).split('\n').flatMap((line) => {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) return []
    const content = stripInlineComment(line)
    return content ? [content] : []
  })
}

function eventBranchTokens(block) {
  const tokens = []
  for (const line of eventActiveLines(block)) {
    const match = line.match(/branches:\s*\[([^\]]*)\]/)
    if (!match) continue
    for (const raw of match[1].split(',')) {
      const token = raw.trim().replace(/^['"]|['"]$/g, '')
      if (token) tokens.push(token)
    }
  }
  return tokens
}

function eventPathEntries(block) {
  const lines = String(block).split('\n')
  const entries = []
  let inPaths = false
  let pathsIndent = 0
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const content = stripInlineComment(line).trim()
    if (!content) continue
    const indent = line.match(/^(\s*)/)[1].length
    if (/^paths:\s*$/.test(content)) {
      inPaths = true
      pathsIndent = indent
      continue
    }
    if (inPaths) {
      if (/^[A-Za-z_][\w-]*:/.test(content) && indent <= pathsIndent) {
        inPaths = false
      } else {
        const item = content.match(/^-\s+(.+)$/)
        if (item) entries.push(item[1].trim().replace(/^['"]|['"]$/g, ''))
      }
    }
  }
  return entries
}

function eventHasMainBranch(block) {
  return eventBranchTokens(block).includes('main')
}

function eventHasPath(block, pathNeedle) {
  return eventPathEntries(block).includes(pathNeedle)
}

function hasRunCommand(commands, script) {
  return commands.some((cmd) => cmd === script)
}

function isRawUniMpCommand(command) {
  if (command === 'npm run build:mp-weixin') return false
  return /(?:^|\s)(?:npx\s+|npm\s+exec\s+)?uni\b/.test(command)
    || /(?:^|\s)npm\s+exec\s+uni\b/.test(command)
    || /node_modules[/\\]\.bin[/\\]uni\b/.test(command)
}

export function workflowHasRequiredGates(workflowSource) {
  const commands = extractWorkflowRunCommands(workflowSource)
  const push = extractTopLevelOnEventBlock(workflowSource, 'push')
  const pullRequest = extractTopLevelOnEventBlock(workflowSource, 'pull_request')
  return {
    lint: hasRunCommand(commands, 'npm run lint'),
    uiContracts: hasRunCommand(commands, 'npm run check:ui-contracts'),
    unit: hasRunCommand(commands, 'npm run test:unit'),
    h5: hasRunCommand(commands, 'npm run build:h5'),
    mpWeixin: hasRunCommand(commands, 'npm run build:mp-weixin'),
    rawUniMp: commands.some(isRawUniMpCommand),
    pushMain: eventHasMainBranch(push),
    pullRequestMain: eventHasMainBranch(pullRequest),
    pushPathMini: eventHasPath(push, 'member-mini-client/**'),
    pushPathWorkflow: eventHasPath(push, '.github/workflows/member-mini-client-ci.yml'),
    prPathMini: eventHasPath(pullRequest, 'member-mini-client/**'),
    prPathWorkflow: eventHasPath(pullRequest, '.github/workflows/member-mini-client-ci.yml'),
    workingDirectory: /working-directory:\s*member-mini-client/.test(workflowSource),
    node20: /node-version:\s*20/.test(workflowSource),
    npmCi: hasRunCommand(commands, 'npm ci') || /(?:^|\n)\s+run:\s*npm ci\s*$/m.test(workflowSource),
  }
}

const walk = (dir, acc = []) => {
  if (!fs.existsSync(dir)) return acc
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'miniprogram_npm' || entry.name === 'uni_modules' || entry.name === 'node_modules' || entry.name === 'dist') continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, acc)
    else acc.push(full)
  }
  return acc
}

export function checkUiContracts(root = srcRoot, options = {}) {
  const FAIL = []
  const maskAllowlist = new Set(options.maskAllowlist ?? LEGACY_MASK_ALLOWLIST)
  const rawAllowlist = new Set(options.rawBlockingAllowlist ?? LEGACY_RAW_BLOCKING_ALLOWLIST)
  const overlayAuthority = options.overlayAuthority ?? BASE_OVERLAY_AUTHORITY
  const semanticAllowlist = new Set(options.semanticZAllowlist ?? SEMANTIC_Z_ALLOWLIST)
  const floorSource = options.blockingFloorSource
    ?? (fs.existsSync(path.join(root, 'styles/global.scss'))
      ? fs.readFileSync(path.join(root, 'styles/global.scss'), 'utf8')
      : null)
  const blockingFloor = options.blockingFloor
    ?? (floorSource ? readBlockingFloor(floorSource) : null)

  const requiredPaths = new Set([
    overlayAuthority,
    ...maskAllowlist,
    ...rawAllowlist,
    ...semanticAllowlist,
  ])
  for (const relPath of requiredPaths) {
    if (!relPath) continue
    if (!fs.existsSync(path.join(root, relPath))) {
      FAIL.push(`dead allowlist path does not exist: ${relPath}`)
    }
  }

  const vueFiles = walk(root).filter((file) => file.endsWith('.vue'))
  const scssFiles = walk(root).filter((file) => file.endsWith('.scss'))

  for (const file of vueFiles) {
    const source = fs.readFileSync(file, 'utf8')
    const name = path.relative(root, file).split(path.sep).join('/')
    if (!hasExactClassToken(source, 'mask')) continue
    if (!maskAllowlist.has(name)) {
      FAIL.push(`${name}: exact class token "mask" is not on LEGACY_MASK_ALLOWLIST; new overlays must use BaseOverlay`)
      continue
    }
    if (!importsShared(source)) {
      FAIL.push(`${name}: legacy exact class token "mask" requires @import of _shared.scss`)
    }
  }

  for (const file of [...vueFiles, ...scssFiles]) {
    const source = fs.readFileSync(file, 'utf8')
    const name = path.relative(root, file).split(path.sep).join('/')
    if (name === overlayAuthority || rawAllowlist.has(name)) continue
    if (isRawBlockingOverlaySource(source)) {
      FAIL.push(`${name}: raw blocking overlay (fixed + fullscreen + z-index) is outside BaseOverlay / LEGACY_RAW_BLOCKING_ALLOWLIST`)
    }
  }

  if (blockingFloor != null) {
    for (const file of [...vueFiles, ...scssFiles]) {
      const source = fs.readFileSync(file, 'utf8')
      const name = path.relative(root, file).split(path.sep).join('/')
      if (name === overlayAuthority || rawAllowlist.has(name)) continue
      const stripped = stripCssComments(source)
      for (const match of stripped.matchAll(/z-index\s*:\s*(\d+)/g)) {
        if (Number(match[1]) >= blockingFloor) {
          FAIL.push(`${name}: numeric z-index ${match[1]} >= blocking floor ${blockingFloor} is outside BaseOverlay / legacy exception`)
        }
      }
    }
  }

  for (const file of [...vueFiles, ...scssFiles]) {
    const source = fs.readFileSync(file, 'utf8')
    const name = path.relative(root, file).split(path.sep).join('/')
    if (semanticAllowlist.has(name)) continue
    if (/z-index\s*:\s*var\(\s*--z-(?:blocking-top|blocking|critical)\s*\)/.test(stripCssComments(source))) {
      FAIL.push(`${name}: blocking layer token z-index is outside BaseOverlay / _shared.scss`)
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
