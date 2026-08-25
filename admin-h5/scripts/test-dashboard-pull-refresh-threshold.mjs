// Dashboard 下拉刷新误触发 P0 修复：van-pull-refresh 默认 headHeight=50px，从"划到
// 底部再往回滑到顶"这种带惯性的正常上滑手势里，划过头 50px 太容易发生——触发后
// preventDefault 会冻结原生滚动，刷新期间页面区块又因为数据重拉而变高，最终卡在
// 旧布局的中间位置，回不到顶部。这里锁定：阈值被显式调大，且刷新进行中禁用手势。
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = fs.readFileSync(path.join(root, 'src/views/Dashboard.vue'), 'utf8').replace(/\r\n/g, '\n')

const failures = []
function test(name, fn) {
  try {
    fn()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, error })
    console.error(`FAIL ${name}: ${error.message}`)
  }
}

test('1. pull-distance is explicitly widened past the 50px default', () => {
  const tag = src.slice(src.indexOf('<van-pull-refresh'), src.indexOf('<van-pull-refresh') + 200)
  assert.ok(/:pull-distance="\d+"/.test(tag), 'must pass an explicit pull-distance prop')
  const distance = Number(tag.match(/:pull-distance="(\d+)"/)[1])
  assert.ok(distance > 50, `pull-distance (${distance}) must exceed Vant's 50px default headHeight -- the whole point is to make accidental overshoot harder`)
})

test('2. the gesture is explicitly disabled while a refresh is in flight', () => {
  const tag = src.slice(src.indexOf('<van-pull-refresh'), src.indexOf('<van-pull-refresh') + 200)
  assert.ok(tag.includes(':disabled="refreshing"'), 'must explicitly disable touch handling during refreshing, not rely only on the internal state machine')
})

console.log(`Dashboard pull-refresh threshold P0: ${failures.length === 0 ? 'passed' : 'FAILED'}`)
if (failures.length > 0) process.exit(1)
