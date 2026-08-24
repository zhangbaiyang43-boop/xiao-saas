import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { execFileSync } from 'node:child_process'

function normalizeBuildVersion(value) {
  const version = String(value || '').trim()
  return /^[0-9a-f]{40}$/i.test(version) ? version : null
}

function resolveBuildVersion() {
  const explicitVersion = normalizeBuildVersion(process.env.ADMIN_RELEASE_SHA)
  if (explicitVersion) return explicitVersion
  try {
    const checkoutVersion = execFileSync('git', ['rev-parse', 'HEAD'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    const normalizedCheckoutVersion = normalizeBuildVersion(checkoutVersion)
    if (normalizedCheckoutVersion) return normalizedCheckoutVersion
  } catch {
    // The CI checkout is authoritative; GITHUB_SHA is only a last-resort fallback.
  }
  return normalizeBuildVersion(process.env.GITHUB_SHA) || 'unknown'
}

export default defineConfig({
  plugins: [vue()],
  define: {
    __ADMIN_BUILD_VERSION__: JSON.stringify(resolveBuildVersion()),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: '@use "@/styles/variables.scss" as *;'
      }
    }
  },
  server: {
    port: 8989
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('ant-design-vue') || id.includes('@ant-design/icons-vue')) return 'vendor-antd'
          if (id.includes('/vant/') || id.includes('@vant')) return 'vendor-vant'
          if (id.includes('/vue/') || id.includes('vue-router') || id.includes('pinia') || id.includes('@vue/')) return 'vendor-vue'
          return 'vendor'
        }
      }
    }
  }
})
