import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const panel = readFileSync(new URL('../src/views/super/ChannelPartnerPanel.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/superChannel.js', import.meta.url), 'utf8')

assert.match(superAdmin, /ChannelPartnerPanel/)
assert.match(superAdmin, /activeTab === 'merchants'/)
assert.match(superAdmin, /activeTab === 'channel'/)
assert.match(superAdmin, /商家管理/)
assert.match(superAdmin, /渠道管理/)
assert.match(superAdmin, /const activeTab = ref\('merchants'\)/)
assert.match(superAdmin, /let superToken = ''/)
assert.doesNotMatch(superAdmin, /localStorage\.setItem\(['"]superToken/)
assert.match(superAdmin, /superRequest\.post\(`\$\{BASE\}\/merchants`/)
assert.match(superAdmin, /openPayConfig/)

// ---- Phase F1G-CM-RF: unified API-origin authority, no raw axios ----------
assert.match(superAdmin, /import superRequest from '\.\.\/api\/superRequest'/)
assert.doesNotMatch(superAdmin, /^import axios from ['"]axios['"]/m, 'SuperAdmin.vue must not import raw axios directly')
assert.doesNotMatch(superAdmin, /axios\.(get|post|put|patch|delete)\(/, 'SuperAdmin.vue must call through superRequest, not raw axios')
assert.match(superAdmin, /const BASE = '\/super'/)

assert.match(api, /\/super\/channel/)
assert.match(api, /import superRequest from '\.\/superRequest'/)
assert.doesNotMatch(api, /^import axios from ['"]axios['"]/m, 'must not import raw axios directly')
assert.doesNotMatch(api, /axios\.(get|post|put|patch|delete)\(/, 'must call through superRequest, not raw axios')
assert.doesNotMatch(api, /['"`]\/api\/super/, 'BASE must not hardcode the /api prefix a second time')
assert.match(api, /'X-Super-Token': superToken/)
assert.doesNotMatch(api, /localStorage/)

assert.match(panel, /listChannelPartners/)
assert.match(panel, /createChannelPartner/)
assert.match(panel, /渠道伙伴总数/)
assert.match(panel, /合作中/)
assert.match(panel, /渠道伙伴已创建/)
assert.match(panel, /\^1\\d\{10\}\$/)
assert.match(panel, /maskPhone/)
assert.doesNotMatch(panel, /console\./)
assert.doesNotMatch(panel, /partner_code["']?\s*:/)
assert.doesNotMatch(panel, /v-model(?:\.trim)?="form\.partner_code"/)

for (const value of [
  'WINE_SALES',
  'PAYMENT_AGENT',
  'PRINTING',
  'FOOD_SUPPLIER',
  'ADVERTISING',
  'EQUIPMENT',
  'DECORATION',
  'FINANCE_TAX',
  'KITCHEN_SUPPLIER',
  'OTHER',
  'ACTIVE',
  'SUSPENDED',
  'DISABLED',
]) {
  assert.match(panel, new RegExp(value))
}

console.log('TEST-FE superChannelPartners: passed')
