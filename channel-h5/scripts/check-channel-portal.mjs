import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const src = join(root, 'src')
const files = []

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full)
    else if (/\.(js|vue)$/.test(name)) files.push(full)
  }
}

walk(src)

const source = files.map((file) => [`\n/* ${relative(root, file)} */\n`, readFileSync(file, 'utf8')]).flat().join('')
const forbidden = [
  ['merchant localStorage token key', /localStorage\.(getItem|setItem|removeItem)\(['"]token['"]/],
  ['hardcoded production OTP', /123456|固定验证码|production.*debug_code/i],
  ['tenant_id as channel auth context', /tenant_id.*channel_access_token|channel_access_token.*tenant_id/],
  ['settlement mutation API', /\.(post|patch|put|delete)\(['"][^'"]*settlements/],
  ['commission mutation API', /\.(post|patch|put|delete)\(['"][^'"]*commissions/],
]

const selfApiFiles = files.filter((file) => file.includes(`${join('src', 'api')}`))
for (const file of selfApiFiles) {
  const text = readFileSync(file, 'utf8')
  if (/partner_id\s*:|partner_id=|params:\s*{[^}]*partner_id/s.test(text)) {
    throw new Error(`self-scoped API must not send partner_id: ${relative(root, file)}`)
  }
}

for (const [label, pattern] of forbidden) {
  if (pattern.test(source)) throw new Error(`forbidden pattern found: ${label}`)
}

console.log('CHANNEL_PORTAL_SECURITY_CHECK_OK')
