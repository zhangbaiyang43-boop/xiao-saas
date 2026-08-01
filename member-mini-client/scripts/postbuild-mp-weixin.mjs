import { existsSync, rmSync, readdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { transformSync } from '@babel/core'

const root = process.cwd()
const distRoot = join(root, 'dist/build/mp-weixin')
const legacyVantWxcomponents = join(distRoot, 'wxcomponents/vant')
const projectConfigPath = join(distRoot, 'project.config.json')
const plugins = [
  '@babel/plugin-transform-optional-chaining',
  '@babel/plugin-transform-nullish-coalescing-operator',
  '@babel/plugin-transform-object-rest-spread',
]

function patchProjectConfig() {
  if (!existsSync(projectConfigPath)) return
  const projectConfig = JSON.parse(readFileSync(projectConfigPath, 'utf-8'))
  projectConfig.setting = { ...(projectConfig.setting || {}), es6: false, newFeature: false }
  writeFileSync(projectConfigPath, `${JSON.stringify(projectConfig, null, 2)}\n`)
}

function walk(dir) {
  const entries = readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const fullPath = join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(fullPath)
      continue
    }
    if (!entry.isFile() || !entry.name.endsWith('.js')) continue

    const code = readFileSync(fullPath, 'utf-8')
    const normalizedCode = code.replace(/\?\.(\d)/g, '?0.$1')
    const result = transformSync(normalizedCode, {
      babelrc: false,
      configFile: false,
      comments: false,
      compact: true,
      plugins,
    })
    if (result?.code && result.code !== code) {
      writeFileSync(fullPath, `${result.code}\n`)
    }
  }
}

walk(distRoot)
if (existsSync(legacyVantWxcomponents)) {
  rmSync(legacyVantWxcomponents, { recursive: true, force: true })
}
patchProjectConfig()
console.log('mp-weixin JS compatibility postbuild complete')