import { defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

// 独立的 vitest 配置，不复用 vite.config.ts 里的 uni() 插件——组合式函数
// 是纯 JS/Vue 响应式逻辑，测试不需要小程序编译链路，只需要 @ 别名和一个
// 全局 uni mock（见 test/setup.js）。
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    setupFiles: ['./test/setup.js'],
    // tests/*.test.mjs 是更早之前用 Node 原生 node:test 写的（不是 vitest 的
    // describe/it），vitest 收集不了里面的用例、只会报 "No test suite found"。
    // 那份测试本身没坏，只是跑法不一样——交给 package.json 里单独的
    // `test:legacy` 脚本用 `node --test` 去跑，这里明确排除掉，不要混进来
    // 制造一个假失败。
    exclude: ['**/node_modules/**', '**/dist/**', 'tests/**'],
  },
})
