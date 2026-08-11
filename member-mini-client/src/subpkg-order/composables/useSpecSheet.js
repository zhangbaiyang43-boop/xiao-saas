import { ref, computed } from 'vue'
import { specText, confirmationText } from '../utils/orderText.js'

// 从 menu.vue 拆出来的规格选择弹层（SpecSheet）全部状态——选规格/附加、备注
// 提示词过滤、价格计算、"下一步"按钮文案，以及最终把选好的这一份加进购物车。
// 之所以是 MEDIUM 而不是 LOW：confirmSpec 会真的往 specCartItems（购物车）
// 里 push 一条记录、触发购物车反馈动画，是有真实副作用的操作，不是纯展示
// 计算。
//
// 特意没有拆进来的东西，作为外部依赖传入：
// - itemRemark/showItemRemarkExtra/itemRemarkExtra/remarkChips：备注这块在
//   LOW 那轮已经拆成 useRemarkChips 了，这里只是复用同一份状态，不重新实现。
// - specCartItems：本质是"购物车"的一部分（removeFromCart/increaseCartItem/
//   cartItems 计算都要读它），不是规格弹层独有的，规格弹层只是它的一个写入方。
// - triggerCartSuccessFeedback：来自 useCartFeedback，在 menu.vue 里跟这个
//   组合式函数是分开调用的两个composable，这里只是复用其中一个触发函数。
export function useSpecSheet({
  itemRemark, showItemRemarkExtra, itemRemarkExtra, remarkChips,
  specCartItems, isSoldOut, formatPrice, triggerCartSuccessFeedback,
}) {
  const showSpecSheet = ref(false)
  const specDish = ref({})
  const specQty = ref(1)
  const specStep = ref(1)
  const selectedSpecs = ref({})
  const selectedExtras = ref([])
  const detailImageFailed = ref(false)

  const specSteps = [
    { no: 1, label: '选规格' },
    { no: 2, label: '附加' },
    { no: 3, label: '备注' },
    { no: 4, label: '确认' },
  ]
  const normalizeSpecGroups = (dish) => {
    const raw = dish?.spec_groups || dish?.specs || dish?.spec_options || []
    if (Array.isArray(raw) && raw.length) {
      return raw.map((g) => {
        const rawType = g.type || (g.multiple ? 'checkbox' : 'single')
        const normalizedType = ['multi', 'multiple', 'checkbox'].includes(rawType) ? 'multiple' : 'single'
        return {
          name: g.name || g.group || g.title || specText.spec,
          type: normalizedType,
          required: g.required !== false,
          options: (g.options || g.values || []).map((o) => typeof o === 'string' ? { name: o, price_delta: 0 } : { name: o.name || o.value || o.label, price_delta: Number(o.price_delta || o.extra_price || 0) }),
        }
      }).filter(g => g.options.length)
    }
    if (dish?.has_options || dish?.hasOptions) {
      return [{ name: '辣度', type: 'single', required: true, options: ['不辣', '微辣', '中辣', '重辣'].map(name => ({ name, price_delta: 0 })) }]
    }
    return []
  }
  const specAllGroups = computed(() => normalizeSpecGroups(specDish.value))
  const specRadioGroups = computed(() => specAllGroups.value.filter(g => g.type !== 'checkbox' && g.type !== 'multiple' && g.type !== 'multi'))
  const specExtraOptions = computed(() => {
    const groups = specAllGroups.value.filter(g => g.type === 'checkbox' || g.type === 'multiple' || g.type === 'multi')
    return groups.flatMap(g => g.options).filter(o => o.name)
  })
  // 备注快捷词跟这道菜自己的规格选项字面重复时不再展示——比如这道菜的"辣度"
  // 规格已经问过"不辣/微辣/中辣/重辣"，备注里就不该再问一遍"不要辣/微辣"，不然
  // 顾客两边都能点、选出自相矛盾的组合（规格选中辣、备注又点不要辣），厨房不
  // 知道听哪个。去掉"不要/不/少/多/加/免"这类常见修饰前缀取核心词再比较，纯
  // 字符串规则、不做语义理解，能覆盖"不要辣"对应规格选项"不辣"这类同义表达，
  // 又不会误伤"少盐""打包"这些跟规格无关的词。
  const SPEC_REMARK_MODIFIER_PREFIXES = ['不要', '不', '少', '多', '加', '免']
  const specRemarkCoreWord = (text) => {
    const raw = String(text || '').trim()
    for (const prefix of SPEC_REMARK_MODIFIER_PREFIXES) {
      if (raw.startsWith(prefix) && raw.length > prefix.length) return raw.slice(prefix.length)
    }
    return raw
  }
  const specGroupOptionCoreWords = computed(() => {
    const words = new Set()
    specAllGroups.value.forEach((group) => {
      group.options.forEach((opt) => {
        const core = specRemarkCoreWord(opt.name)
        if (core) words.add(core)
      })
    })
    return words
  })
  const filteredRemarkChips = computed(() => {
    const coreWords = specGroupOptionCoreWords.value
    if (!coreWords.size) return remarkChips.value
    return remarkChips.value.filter((chip) => !coreWords.has(specRemarkCoreWord(chip)))
  })
  const specBasePrice = computed(() => Number(specDish.value.price) || 0)
  const specExtraPrice = computed(() => {
    let extra = 0
    for (const group of specRadioGroups.value) {
      const sel = selectedSpecs.value[group.name] || []
      for (const opt of group.options) if (sel.includes(opt.name)) extra += Number(opt.price_delta || 0)
    }
    for (const opt of specExtraOptions.value) if (selectedExtras.value.includes(opt.name)) extra += Number(opt.price_delta || 0)
    return extra
  })
  const specUnitPrice = computed(() => specBasePrice.value + specExtraPrice.value)
  const specTotalPrice = computed(() => specUnitPrice.value * specQty.value)
  const selectedSpecRows = computed(() => specRadioGroups.value.map(group => ({ group: group.name, value: (selectedSpecs.value[group.name] || [])[0] || '' })).filter(i => i.value))
  const selectedSpecSummary = computed(() => selectedSpecRows.value.map(i => i.value).join(specText.separator))
  // 给弹层底部的"已选：..."实时小结用——跟 confirmSpec() 里拼 orderName/specLabel
  // 用的是同一套"规格+附加+备注"拼接逻辑，不能只显示 selectedSpecSummary（只有
  // 辣度/做法这类必选项），不然顾客勾了"附加要求"却在小结里看不到，以为没选上。
  const selectedSpecFullSummary = computed(() => {
    const parts = [...selectedSpecRows.value.map(i => i.value), ...selectedExtras.value]
    const remarkText = itemRemark.value.trim()
    if (remarkText) parts.push(remarkText)
    return parts.join(specText.separator)
  })
  const specDishDesc = computed(() => String(specDish.value.desc || specDish.value.description || '').trim())
  const missingRequiredSpecGroup = computed(() => specRadioGroups.value.find(group => group.required && !(selectedSpecs.value[group.name] || []).length))
  const requiredGroupPrompt = (group) => /辣|口味|甜度|温度/.test(group?.name || '') ? specText.chooseTaste : specText.chooseSpec
  const canGoNextSpec = computed(() => !isSoldOut(specDish.value) && !missingRequiredSpecGroup.value)
  const specPrimaryText = computed(() => {
    if (isSoldOut(specDish.value)) return '已售罄'
    if (missingRequiredSpecGroup.value) return requiredGroupPrompt(missingRequiredSpecGroup.value)
    return specText.add + ' ' + confirmationText.currency + formatPrice(specTotalPrice.value)
  })
  function isSpecSelected(group, opt) {
    return (selectedSpecs.value[group.name] || []).includes(opt.name)
  }
  function toggleSpec(group, opt) {
    selectedSpecs.value = { ...selectedSpecs.value, [group.name]: [opt.name] }
  }
  const toggleExtra = (extra) => {
    selectedExtras.value = selectedExtras.value.includes(extra) ? selectedExtras.value.filter(x => x !== extra) : [...selectedExtras.value, extra]
  }
  const buildSpecKey = () => JSON.stringify({ id: specDish.value.id, specifications: selectedSpecRows.value, extras: selectedExtras.value, itemRemark: itemRemark.value.trim() })
  function cancelSpec() { showSpecSheet.value = false }
  function handleSpecPrimary() {
    if (!canGoNextSpec.value) return
    confirmSpec()
  }
  function confirmSpec() {
    if (isSoldOut(specDish.value)) return
    const specKey = buildSpecKey()
    const specifications = selectedSpecRows.value.map(i => ({ group: i.group, value: i.value }))
    const extras = [...selectedExtras.value]
    const remarkText = itemRemark.value.trim()
    const labels = [...specifications.map(i => i.value), ...extras]
    if (remarkText) labels.push(remarkText)
    const existing = specCartItems.value.find(i => i.specKey === specKey)
    if (existing) {
      existing.qty += specQty.value
    } else {
      specCartItems.value.push({
        specKey,
        id: specDish.value.id,
        name: specDish.value.name,
        orderName: labels.length ? specDish.value.name + '(' + labels.join(specText.separator) + ')' : specDish.value.name,
        price: specUnitPrice.value,
        qty: specQty.value,
        emoji: specDish.value.emoji,
        specLabel: labels.join(specText.dotSeparator),
        specifications,
        extras,
        itemRemark: remarkText,
        selectedSpecs: JSON.parse(JSON.stringify(selectedSpecs.value)),
      })
    }
    showSpecSheet.value = false
    triggerCartSuccessFeedback(specKey)
    uni.vibrateShort({ type: 'light' })
  }

  const openSpecSheet = (dish, existingItem = null) => {
    specDish.value = dish
    detailImageFailed.value = false
    specQty.value = existingItem?.qty || 1
    specStep.value = 4
    selectedSpecs.value = {}
    for (const g of normalizeSpecGroups(dish).filter(g => g.type !== 'checkbox' && g.type !== 'multiple' && g.type !== 'multi')) {
      const existingValue = existingItem?.specifications?.find(i => i.group === g.name)?.value
      if (existingValue) selectedSpecs.value[g.name] = [existingValue]
    }
    selectedExtras.value = existingItem?.extras ? [...existingItem.extras] : []
    itemRemark.value = existingItem?.itemRemark || ''
    showItemRemarkExtra.value = Boolean(itemRemarkExtra.value)
    showSpecSheet.value = true
  }

  const openProductDetail = (dish) => openSpecSheet(dish)

  return {
    showSpecSheet,
    specDish,
    specQty,
    specStep,
    selectedSpecs,
    selectedExtras,
    detailImageFailed,
    specSteps,
    specRadioGroups,
    specExtraOptions,
    filteredRemarkChips,
    specBasePrice,
    specTotalPrice,
    selectedSpecSummary,
    selectedSpecFullSummary,
    specDishDesc,
    canGoNextSpec,
    specPrimaryText,
    isSpecSelected,
    toggleSpec,
    toggleExtra,
    cancelSpec,
    handleSpecPrimary,
    confirmSpec,
    openSpecSheet,
    openProductDetail,
  }
}
