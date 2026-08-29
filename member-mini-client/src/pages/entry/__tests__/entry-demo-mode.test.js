import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(path.resolve(here, '../index.vue'), 'utf8')

describe('entry Demo mode contract', () => {
  it('Demo 入口清除旧会员身份并持久化标准化的 DEMO 渠道', () => {
    expect(source).toContain("String(ctx.channel || 'TABLE').trim().toUpperCase()")
    expect(source).toMatch(/if \(channel === 'DEMO'\) \{\s*clearCustomerSession\(\)/)
    expect(source).toContain("uni.setStorageSync('channel', channel)")
  })

  it('正式门店仍只在跨租户时清理旧会员身份', () => {
    expect(source).toMatch(/else if \(ctx\.tenant_id && previousTenantId && previousTenantId !== ctx\.tenant_id\)/)
  })
})
