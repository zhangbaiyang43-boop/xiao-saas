import { computed } from 'vue'
import { specText } from '../utils/orderText.js'

// 从 menu.vue 拆出来的分类展示逻辑——分类排序/去重、分类名和图标归一化、
// 按分类取菜品——都是只读的纯派生计算，不改任何页面状态。
//
// hasSpecs 是回调而不是直接 import：它来自 useOrderFormatters()，在 menu.vue
// 里跟这个组合式函数是同一层的两个独立调用，这里只是复用其中一个函数，不需要
// 也不应该重新实现一遍"有没有规格"的判断逻辑。
export function useDishCategories({ allDishes, categoryOrder, specCartItems, hasSpecs }) {
  const RECOMMEND_CAT = '推荐'

  const categories = computed(() => {
    const raw = []
    for (const d of allDishes.value) {
      if (d.category && !raw.includes(d.category)) raw.push(d.category)
    }
    const order = categoryOrder.value
    let sorted
    if (order.length) {
      // 分类锚点 id（cat-nav-N / cat-sec-N）都是按数组下标生成的，如果 order 里同一个分类
      // 出现了两次（商家后台保存过脏数据，或旧版本排序抽屉没做去重），这里再用 filter 不去重
      // 的话，categories 数组会带着重复项：indexOf(cat) 永远只会命中第一次出现的下标，
      // 点击排在后面的那个重名分类会跳到前面那个的位置——这正是点分类跳错、滚动时中间
      // 分类被跳过的根因，跟去重后 sidebar/正文两个 v-for 是否还共用同一份数组无关。
      const seen = new Set()
      sorted = order.filter(c => raw.includes(c) && !seen.has(c) && seen.add(c))
    } else {
      // 商家没配置分类顺序时，按点餐习惯给个默认顺序，而不是菜品在数据库里出现的原始
      // 顺序（等于商家后台录入顺序直接透传给顾客）；商家一旦自己配置过就完全尊重商家。
      sorted = [...raw].sort((a, b) => categoryOrderWeight(a) - categoryOrderWeight(b))
    }
    raw.forEach(c => { if (!sorted.includes(c)) sorted.push(c) })
    const hasRecommended = allDishes.value.some(d => {
      const tags = Array.isArray(d.tags) ? d.tags : String(d.tags || '').split(/[,\s，、]+/).map(t => t.trim()).filter(Boolean)
      return tags.includes('推荐') || tags.includes('招牌') || tags.includes('热销')
    })
    if (hasRecommended) sorted = [RECOMMEND_CAT, ...sorted.filter(c => c !== RECOMMEND_CAT)]
    return sorted
  })

  const normalizeCategoryText = (cat) => String(cat || '').trim()

  const categoryDisplayName = (cat) => {
    const text = normalizeCategoryText(cat)
    if (text === RECOMMEND_CAT) return RECOMMEND_CAT
    if (/招牌|热销|特色/.test(text)) return '招牌'
    if (/汤|粥|例汤/.test(text)) return '汤品'
    if (/主食|米饭|米线|面|粉|饭/.test(text)) return '主食'
    if (/饮|奶茶|咖啡|果汁|茶|酒/.test(text)) return '饮品'
    if (/点心|茶点|甜品|包子|饺子/.test(text)) return text.length > 3 ? '点心' : text
    return text.length > 4 ? text.slice(0, 4) : text
  }

  const categoryIconClass = (cat) => {
    const text = normalizeCategoryText(cat)
    if (text === RECOMMEND_CAT) return 'icon-likefill'
    if (/招牌|热销|特色/.test(text)) return 'icon-xiaochao'
    if (/汤|粥|例汤/.test(text)) return 'icon-zhou'
    if (/面|粉/.test(text)) return 'icon-mianshi'
    if (/主食|米饭|饭/.test(text)) return 'icon-mifan'
    if (/冷饮|饮品|饮料|果汁/.test(text)) return 'icon-lengyin'
    if (/热饮|咖啡|茶/.test(text)) return 'icon-reyin'
    if (/点心|茶点/.test(text)) return 'icon-chadian'
    if (/包子/.test(text)) return 'icon-baozi'
    if (/饺子/.test(text)) return 'icon-jiaozi'
    if (/甜品/.test(text)) return 'icon-tianpin'
    return 'icon-chadian'
  }

  // 商家没有在后台手动配好分类顺序时，之前是按菜品在数据库里出现的原始顺序排分类
  // sidebar——本质上是商家后台的录入顺序直接透传到顾客点餐界面，不是点餐习惯的顺序。
  // 这里给几个常见归一化后的分类一个默认权重，命中不了的分类（权重99）排在最后，
  // 一旦商家自己配置过 category_order，这个默认权重完全不生效，不覆盖商家的选择。
  const CATEGORY_DEFAULT_WEIGHT = { '招牌': 1, '汤品': 2, '主食': 3, '饮品': 4, '点心': 5 }
  const categoryOrderWeight = (cat) => {
    if (normalizeCategoryText(cat) === RECOMMEND_CAT) return 0
    return CATEGORY_DEFAULT_WEIGHT[categoryDisplayName(cat)] ?? 99
  }

  const dishesByCategory = (cat) => {
    if (cat === RECOMMEND_CAT) {
      return allDishes.value.filter(d => {
        const tags = Array.isArray(d.tags) ? d.tags : String(d.tags || '').split(/[,\s，、]+/).map(t => t.trim()).filter(Boolean)
        return tags.includes('推荐') || tags.includes('招牌') || tags.includes('热销')
      })
    }
    return allDishes.value.filter((d) => d.category === cat)
  }

  const specButtonText = (dish) => dish.option_button_text || dish.spec_button_text || (hasSpecs(dish) ? specText.chooseTaste : specText.chooseSpec)
  const dishOptionKindCount = (id) => specCartItems.value.filter(i => i.id === id).length
  const optionCountText = (id) => specText.selectedKinds + dishOptionKindCount(id) + specText.kindUnit

  return {
    categories,
    categoryDisplayName,
    categoryIconClass,
    dishesByCategory,
    specButtonText,
    dishOptionKindCount,
    optionCountText,
  }
}
