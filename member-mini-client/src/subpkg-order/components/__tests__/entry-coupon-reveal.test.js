import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const src = readFileSync(path.resolve(here, '../EntryCouponReveal.vue'), 'utf8')

describe('EntryCouponReveal — 开奖层加菜引导', () => {
  it('带门槛的券按钮是「去加菜」并 emit add-dish；无门槛是「收下」emit close', () => {
    expect(src).toContain('v-if="hasThreshold"')
    expect(src).toContain('>去加菜<')
    expect(src).toContain("$emit('add-dish')")
    expect(src).toContain('v-else class="ecr-btn tap-shrink" @click="$emit(\'close\')"><text>收下</text>')
    expect(src).toContain("emits: ['close', 'add-dish']")
  })

  it('文案不写解释句：只有 满X可用 / 无门槛 / 今日有效', () => {
    expect(src).toContain('满${Number(this.threshold).toFixed(0)}可用')
    expect(src).toContain("'无门槛'")
    expect(src).toContain('今日有效')
    expect(src).not.toMatch(/加一道.*的菜就能用|因为|由于|说明/)
  })

  it('入场有缩放动效', () => {
    expect(src).toContain('animation: ecr-in')
    expect(src).toContain('@keyframes ecr-in')
  })
})
