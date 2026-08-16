import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

// menu.vue is an SFC and can't be imported/executed by vitest here (no Vue-SFC
// compiler plugin wired into vitest.config.js -- see its own comment on why).
// Same pattern as ../../../utils/__tests__/preload-rules.test.js: pin the exact
// source text instead of executing it.
const menuSource = readFileSync(
  fileURLToPath(new URL('../menu.vue', import.meta.url)),
  'utf8',
)

describe('menu.vue table context (P0-01C, Finding B)', () => {
  it('case C06/C12: never fabricates a fake table number when one is missing', () => {
    // Must not silently substitute a plausible-looking real table number for a
    // genuinely missing one -- that's the exact bug this fix removes.
    expect(menuSource).not.toMatch(/options\.table\s*\|\|\s*['"]A01['"]/)
  })

  it('case C05/C12: still reads a real table number when one is provided', () => {
    // Deleting the fake fallback must not also break the real, valid case --
    // a genuinely scanned "A01" (or any other table) must still work.
    expect(menuSource).toMatch(/this\.tableNo\s*=\s*options\.table\s*\|\|\s*['"]['"]/)
  })
})
