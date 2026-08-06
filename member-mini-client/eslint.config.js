import vuePlugin from 'eslint-plugin-vue'

// 第一次给这个仓库接 ESLint，刻意从一套很小的规则集开始——目标是"接住这次
// 清理暴露出来的那几类问题不再复发"（空 catch、真正没用的变量），不是一次性
// 把整个历史代码库按最严格的规范推倒重来。规则加太猛，首次接入就会在一堆
// 跟这次改动无关的老代码上报错，CI 直接红，逼着大家要么忽略要么全量返工，
// 两个结果都不是目标。规则可以以后再一条条收紧。
//
// 只认 src/** 和这次新加的测试代码——项目根目录下还平行放着一份
// subpkg-coupon/subpkg-member/subpkg-plugins/subpkg-common/pages/store
// （连 App.vue、manifest.json、pages.json 都在根目录有一份），跟 src/ 底下
// 那份是什么关系（是编译产物、旧结构迁移剩下的，还是另一个真的在用的入口）
// 现在没有把握确认，不该在"接一个基础 lint"的时候顺手对着不了解的目录报错。
// 用 files 白名单只圈 src/** 和 test(s)/**，比对整个仓库用 ignores 去一个个
// 排除要安全——排除清单漏一个，没弄明白的目录就混进来报一堆无关的错。
//
// vue/* 那组规则直接展开 eslint-plugin-vue 官方提供的 flat config 数组，而
// 不是自己手动摘出 rules 再拼一份——之前摘 rules 的写法漏带了 processor 之类
// 让插件识别 <template>/<script>/<style> 分块边界所需要的配置，导致每个 .vue
// 文件的三个闭合标签处都被 vue/comment-directive 规则误报一遍，是配置错误
// 不是代码问题，用官方推荐的展开方式就没有这个问题。
export default [
  {
    ignores: ['**/dist/**', '**/node_modules/**', '**/wxcomponents/**', 'src/miniprogram_npm/**', 'src/uni_modules/**'],
  },
  ...vuePlugin.configs['flat/essential'].map((cfg) => ({
    ...cfg,
    files: ['src/**/*.vue'],
  })),
  {
    files: ['src/**/*.js', 'src/**/*.mjs', 'test/**/*.js', 'tests/**/*.mjs', '*.config.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: uniAppGlobals(),
    },
    rules: baseRules(),
  },
  {
    files: ['src/**/*.vue'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: uniAppGlobals(),
    },
    rules: {
      ...baseRules(),
      // 这份仓库里单词组件名本来就存在（比如页面级的 list.vue/detail.vue），
      // 不是这次要收紧的东西，关掉避免制造一堆跟这次目标无关的噪音。
      'vue/multi-word-component-names': 'off',
    },
  },
]

// uni-app / 微信小程序运行时注入的全局对象——项目里到处直接用 `uni.xxx`、
// `wx.xxx`，不是 import 进来的，不声明成 global 的话每一处都会被 no-undef
// 误报。
function uniAppGlobals() {
  return {
    uni: 'readonly',
    wx: 'readonly',
    getApp: 'readonly',
    getCurrentPages: 'readonly',
    Page: 'readonly',
    App: 'readonly',
    Component: 'readonly',
    Behavior: 'readonly',
    requirePlugin: 'readonly',
    console: 'readonly',
    setTimeout: 'readonly',
    clearTimeout: 'readonly',
    setInterval: 'readonly',
    clearInterval: 'readonly',
    Promise: 'readonly',
    Date: 'readonly',
    Math: 'readonly',
    JSON: 'readonly',
    Array: 'readonly',
    Object: 'readonly',
    Number: 'readonly',
    String: 'readonly',
    Boolean: 'readonly',
    process: 'readonly',
  }
}

function baseRules() {
  return {
    // 这次清理的起因之一——catch(e){} 把错误彻底吞掉，出了问题没人知道。
    // allowEmptyCatch 关掉，强制要么处理、要么至少写清楚"为什么故意留空"。
    'no-empty': ['error', { allowEmptyCatch: false }],
    // 真正没用到的变量/参数——排除以 _ 开头的（约定俗成的"故意不用"标记，
    // 比如解构时占位）。catch 绑定的错误变量哪怕暂时不用也不报，很多地方
    // 就是想留个 e 方便以后调试时加日志，不算真的"没用"。
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' }],
    // 明显的逻辑错误，不是风格问题，随手就能抓到复制粘贴漏改的 bug。
    'no-dupe-keys': 'error',
    'no-unreachable': 'error',
    'no-constant-condition': ['error', { checkLoops: false }],
  }
}
