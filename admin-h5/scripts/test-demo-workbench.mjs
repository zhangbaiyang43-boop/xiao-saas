import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  clearDemoSession,
  nextDemoAction,
  readDemoSession,
  saveDemoSession,
} from '../src/demo/session.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const data = new Map()
const storage = {
  getItem: (key) => data.get(key) || null,
  setItem: (key, value) => data.set(key, value),
  removeItem: (key) => data.delete(key),
}

saveDemoSession(storage, {
  demoToken: 'demo-token',
  expiresAt: '2099-01-01T00:00:00Z',
})
assert.equal(readDemoSession(storage).demoToken, 'demo-token')
assert.equal(data.has('token'), false)
assert.deepEqual(nextDemoAction({ status: 'pending' }), {
  status: 'preparing',
  label: '接单',
})
assert.deepEqual(nextDemoAction({ status: 'preparing' }), {
  status: 'done',
  label: '制作完成',
})
assert.deepEqual(nextDemoAction({ status: 'done', servedAt: null }), {
  serve: true,
  label: '确认上菜',
})
assert.equal(
  nextDemoAction({ status: 'done', servedAt: '2026-08-29T00:00:00Z' }),
  null,
)
clearDemoSession(storage)
assert.equal(readDemoSession(storage), null)

const router = readFileSync(path.join(root, 'src/router/index.js'), 'utf8')
assert.match(router, /path:\s*['"]\/demo['"]/)
assert.match(router, /const isDemo = to\.path === ['"]\/demo['"]/)
assert.match(router, /isDemo[^\n]*\)\s*\{\s*\n\s*next\(\)/)

const demoRequest = readFileSync(path.join(root, 'src/api/demoRequest.js'), 'utf8')
assert.match(demoRequest, /resolveApiBaseURL\(\)/)
assert.match(demoRequest, /sessionStorage/)
assert.match(demoRequest, /DEMO_SESSION_KEY/)
assert.doesNotMatch(demoRequest, /localStorage/)
assert.doesNotMatch(demoRequest, /window\.location|\/login/)
assert.doesNotMatch(demoRequest, /from ['"]\.\/request['"]/)

const demoApi = readFileSync(path.join(root, 'src/api/demo.js'), 'utf8')
assert.match(demoApi, /post\(['"]\/v1\/demo\/sessions\/start['"]/)
assert.match(demoApi, /get\(['"]\/v1\/demo\/session['"]/)
assert.match(demoApi, /patch\(`\/v1\/demo\/orders\/\$\{orderId\}\/status`/)
assert.match(demoApi, /post\(`\/v1\/demo\/orders\/\$\{orderId\}\/serve`/)

console.log('TEST-FE demo workbench foundation: passed')
