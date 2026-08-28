import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  classifyTableStickerCode,
  parseBlobErrorMessage,
  selectedExportableCodes,
  triggerBlobDownload,
} from '../src/utils/tableStickerExport.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const validCode = {
  id: '1',
  channel: 'TABLE',
  entry_type: 'table',
  status: 1,
  env_version: 'release',
  generation_status: 'SUCCESS',
  image_url: '/static/entrance-codes/a.jpg',
  table_no: 'A01',
}

test('only formal successful table codes are exportable', () => {
  assert.deepEqual(classifyTableStickerCode(validCode), { valid: true, reason: '' })

  for (const invalid of [
    { ...validCode, channel: 'STORE' },
    { ...validCode, entry_type: 'store' },
    { ...validCode, status: 0 },
    { ...validCode, env_version: 'trial' },
    { ...validCode, generation_status: 'FAILED' },
    { ...validCode, image_url: ' ' },
    { ...validCode, table_no: ' ' },
  ]) {
    assert.equal(classifyTableStickerCode(invalid).valid, false)
  }
})

test('selected exportable codes compare ids as strings and preserve list order', () => {
  const numericId = { ...validCode, id: 1 }
  const second = { ...validCode, id: '2', table_no: 'A02' }
  const disabled = { ...validCode, id: '3', status: 0 }

  assert.deepEqual(selectedExportableCodes([numericId, second, disabled], new Set(['1', 2, '3'])), [numericId, second])
})

test('blob JSON error prefers the existing backend envelope message', async () => {
  const blob = new Blob([
    JSON.stringify({ code: 422, msg: '桌码状态已变化，请刷新后重新选择', message: '兼容文案', data: null }),
  ], { type: 'application/json' })

  assert.equal(await parseBlobErrorMessage(blob), '桌码状态已变化，请刷新后重新选择')
})

test('blob JSON error accepts message fallback and malformed payload fallback', async () => {
  const compatible = new Blob([JSON.stringify({ message: '兼容错误文案' })], { type: 'application/json' })
  const malformed = new Blob(['not json'], { type: 'application/json' })

  assert.equal(await parseBlobErrorMessage(compatible), '兼容错误文案')
  assert.equal(await parseBlobErrorMessage(malformed), '桌贴生成失败，请稍后重试')
})

test('download helper removes its anchor and revokes the object URL', async () => {
  const originalUrl = globalThis.URL
  const originalDocument = globalThis.document
  const events = []
  const anchor = {
    click: () => events.push('click'),
    remove: () => events.push('remove'),
  }
  globalThis.URL = {
    createObjectURL: () => {
      events.push('create')
      return 'blob:table-stickers'
    },
    revokeObjectURL: value => events.push(`revoke:${value}`),
  }
  globalThis.document = {
    createElement: () => anchor,
    body: { appendChild: value => events.push(value === anchor ? 'append' : 'wrong-anchor') },
  }

  try {
    triggerBlobDownload(new Blob(['zip']), '桌贴.zip')
    await new Promise(resolve => setTimeout(resolve, 0))
    assert.equal(anchor.href, 'blob:table-stickers')
    assert.equal(anchor.download, '桌贴.zip')
    assert.deepEqual(events, ['create', 'append', 'click', 'remove', 'revoke:blob:table-stickers'])
  } finally {
    globalThis.URL = originalUrl
    globalThis.document = originalDocument
  }
})

test('download helper still revokes the object URL when clicking fails', async () => {
  const originalUrl = globalThis.URL
  const originalDocument = globalThis.document
  const events = []
  const anchor = {
    click: () => { throw new Error('click blocked') },
    remove: () => events.push('remove'),
  }
  globalThis.URL = {
    createObjectURL: () => 'blob:failed-download',
    revokeObjectURL: value => events.push(`revoke:${value}`),
  }
  globalThis.document = {
    createElement: () => anchor,
    body: { appendChild: () => events.push('append') },
  }

  try {
    assert.throws(() => triggerBlobDownload(new Blob(['zip']), '桌贴.zip'), /click blocked/)
    await new Promise(resolve => setTimeout(resolve, 0))
    assert.deepEqual(events, ['append', 'remove', 'revoke:blob:failed-download'])
  } finally {
    globalThis.URL = originalUrl
    globalThis.document = originalDocument
  }
})

test('download helper still revokes the object URL when anchor cleanup fails', async () => {
  const originalUrl = globalThis.URL
  const originalDocument = globalThis.document
  const events = []
  const anchor = {
    click: () => events.push('click'),
    remove: () => { throw new Error('remove blocked') },
  }
  globalThis.URL = {
    createObjectURL: () => 'blob:cleanup-failed',
    revokeObjectURL: value => events.push(`revoke:${value}`),
  }
  globalThis.document = {
    createElement: () => anchor,
    body: { appendChild: () => events.push('append') },
  }

  try {
    assert.throws(() => triggerBlobDownload(new Blob(['zip']), '桌贴.zip'), /remove blocked/)
    await new Promise(resolve => setTimeout(resolve, 0))
    assert.deepEqual(events, ['append', 'click', 'revoke:blob:cleanup-failed'])
  } finally {
    globalThis.URL = originalUrl
    globalThis.document = originalDocument
  }
})

test('API request sends only entranceCodeIds and uses an isolated Blob timeout', () => {
  const api = fs.readFileSync(path.join(root, 'src/api/index.js'), 'utf8')
  assert.match(
    api,
    /exportTableStickers\s*=\s*\(entranceCodeIds\)\s*=>\s*request\.post\(\s*['"]\/v1\/entrance-codes\/table-stickers\/export['"]\s*,\s*\{\s*entranceCodeIds\s*\}\s*,/,
  )
  assert.match(api, /exportTableStickers[\s\S]*responseType:\s*['"]blob['"][\s\S]*timeout:\s*120000/)
  assert.match(api, /meta:\s*\{\s*rawResponse:\s*true\s*\}/)
})
