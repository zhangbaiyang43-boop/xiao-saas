/**
 * Phase F1G-CM-RF — SuperAdmin API-origin authority contract checks.
 *
 * CM-R found that SuperAdmin.vue / superChannel.js / superBilling.js used
 * raw axios with browser-relative paths ("/api/super/..."), while the
 * merchant/staff client (request.js) resolves an explicit configured origin
 * via VITE_API_BASE_URL. In local dev those two resolve to different hosts
 * -- that's exactly why CM-C/CM-D needed a temporary Vite dev-proxy to make
 * SuperAdmin's E2E work at all. This file proves the fix: one shared origin
 * -resolution function, used by every SuperAdmin API client, with no second
 * copy of the logic to drift out of sync -- and that no raw-axios call site
 * survives anywhere in admin-h5/src.
 */
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const srcRoot = path.join(root, 'src')

const apiBaseUrl = readFileSync(path.join(srcRoot, 'api', 'apiBaseUrl.js'), 'utf8')
const request = readFileSync(path.join(srcRoot, 'api', 'request.js'), 'utf8')
const superRequest = readFileSync(path.join(srcRoot, 'api', 'superRequest.js'), 'utf8')

// ---- ONE shared origin-resolution authority, not two independently-typed
// copies of the same VITE_API_BASE_URL/hostname logic. ----------------------
assert.match(apiBaseUrl, /export function resolveApiBaseURL/)
assert.match(apiBaseUrl, /VITE_API_BASE_URL/)
assert.match(apiBaseUrl, /saas\.zhangbaiyang\.com/)

assert.match(request, /import \{ resolveApiBaseURL \} from '\.\/apiBaseUrl'/)
assert.match(request, /const baseURL = resolveApiBaseURL\(\)/)
assert.doesNotMatch(request, /VITE_API_BASE_URL/, 'request.js must not re-implement env resolution itself -- that would be exactly the second drifting copy this fix removes')
assert.doesNotMatch(request, /window\.location\.hostname/, 'request.js must not re-implement hostname branching itself')

assert.match(superRequest, /import \{ resolveApiBaseURL \} from '\.\/apiBaseUrl'/)
assert.match(superRequest, /baseURL:\s*resolveApiBaseURL\(\)/)

// ---- SuperAdmin auth model preserved: X-Super-Token, no merchant JWT ------
// superRequest must NOT inject a merchant Authorization header, must NOT do
// the merchant client's on-401 redirect-to-/login (that would hijack the
// SuperAdmin session), and must NOT unwrap response.data (every existing
// SuperAdmin call site still reads res.data.code off the raw AxiosResponse).
assert.doesNotMatch(superRequest, /localStorage/, 'superRequest must never read the merchant token from localStorage')
assert.doesNotMatch(superRequest, /headers\.Authorization|['"]Authorization['"]\s*:/, 'superRequest must not inject a merchant Authorization header')
assert.doesNotMatch(superRequest, /\.interceptors\./, 'superRequest must stay a bare client -- no interceptor that could redirect/unwrap and diverge from every existing X-Super-Token call site')

// ---- No raw axios / browser-relative "/api/super" calls survive anywhere
// in admin-h5/src (Phase 18 audit, codified as a real test, not a one-off
// grep). ----------------------------------------------------------------
function listJsVueFiles(dir) {
  const out = []
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) out.push(...listJsVueFiles(full))
    else if (/\.(js|vue)$/.test(entry)) out.push(full)
  }
  return out
}

const offenders = []
for (const file of listJsVueFiles(srcRoot)) {
  if (file.endsWith(path.join('api', 'superRequest.js'))) continue // the client itself legitimately has no auth header baked in
  const text = readFileSync(file, 'utf8')
  if (/axios\.(get|post|put|patch|delete)\(\s*['"`]\/api\/super/.test(text)) {
    offenders.push(path.relative(root, file))
  }
  if (/\baxios\b/.test(text) && /\/api\/super/.test(text) && !/superRequest/.test(text) && !file.endsWith(path.join('api', 'request.js'))) {
    // Heuristic second pass: raw axios import co-occurring with a literal
    // /api/super path string, anywhere outside the fixed request clients.
    if (/import\s+axios\s+from\s+['"]axios['"]/.test(text)) offenders.push(path.relative(root, file))
  }
}
assert.deepEqual([...new Set(offenders)], [], `found raw-axios /api/super call sites: ${offenders.join(', ')}`)

// ---- .env.example completeness (Phase 14/17): 4 fields, safe disabled
// default, no real payee/QR/credential ---------------------------------
const envExamplePath = path.join(root, '..', 'saas-base', '.env.example')
const envExample = readFileSync(envExamplePath, 'utf8')
assert.match(envExample, /^SAAS_MANUAL_PAYMENT_ENABLED=false$/m, 'must default to disabled in the tracked example')
assert.match(envExample, /^SAAS_MANUAL_PAYMENT_PAYEE_NAME=$/m, 'must be an empty placeholder, not a real payee name')
assert.match(envExample, /^SAAS_MANUAL_PAYMENT_QR_URL=$/m, 'must be an empty placeholder, not a real QR URL')
assert.match(envExample, /^SAAS_MANUAL_PAYMENT_CONFIRM_MINUTES=10$/m)
assert.doesNotMatch(envExample, /data:image/, '.env.example must never contain a QR data URI')
assert.doesNotMatch(envExample, /灵宝市金白杨百货店/, '.env.example must never contain the real payee name')

console.log('TEST-FE superApiOriginAuthority: passed')
