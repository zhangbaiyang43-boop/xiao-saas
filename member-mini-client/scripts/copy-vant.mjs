import { cpSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const src  = join(root, 'node_modules/@vant/weapp/lib')
const dst  = join(root, 'dist/build/mp-weixin/miniprogram_npm/@vant/weapp')

const components = [
  'button','cell','cell-group','grid','grid-item',
  'tag','icon','empty','loading','popup',
  'overlay','transition','info','common','wxs','mixins'
]

for (const c of components) {
  mkdirSync(join(dst, c), { recursive: true })
  cpSync(join(src, c), join(dst, c), { recursive: true, force: true })
}

console.log('miniprogram_npm/@vant/weapp copied to dist')
