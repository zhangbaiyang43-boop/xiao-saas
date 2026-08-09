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
assert.match(superAdmin, /axios\.post\(`\$\{BASE\}\/merchants`/)
assert.match(superAdmin, /openPayConfig/)

assert.match(api, /\/api\/super\/channel/)
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
