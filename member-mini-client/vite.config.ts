import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import { cpSync, mkdirSync } from 'fs'
import { join } from 'path'

function copyVantPlugin() {
  return {
    name: 'copy-vant-weapp',
    closeBundle() {
      const root = process.cwd()
      const src = join(root, 'node_modules/@vant/weapp/dist')
      const dst = join(root, 'dist/build/mp-weixin/miniprogram_npm/@vant/weapp')
      const components = [
        'button', 'cell', 'cell-group', 'grid', 'grid-item',
        'tag', 'icon', 'empty', 'loading', 'popup',
        'overlay', 'transition', 'info', 'common', 'wxs', 'mixins',
      ]
      for (const c of components) {
        try {
          mkdirSync(join(dst, c), { recursive: true })
          cpSync(join(src, c), join(dst, c), { recursive: true, force: true })
        } catch (e) {}
      }
      console.log('✓ @vant/weapp copied to dist')
    },
  }
}

export default defineConfig({
  plugins: [uni(), copyVantPlugin()],
})
