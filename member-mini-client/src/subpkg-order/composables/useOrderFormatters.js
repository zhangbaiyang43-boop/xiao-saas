import { formatOrderStatusText } from '@/utils/orderStatus'
import { parseServerTime, formatBeijingDate } from '@/utils/beijingTime'

// 从 menu.vue 拆出来的纯格式化/展示函数——菜品图片、价格、规格判断、订单明细
// 文案、优惠券文案。全部是纯函数（输入什么就算什么，不读、不改任何页面状态），
// 逻辑跟原来在 menu.vue 里一字未改，只是搬了个位置。
const placeholderGradients = [
  'linear-gradient(135deg,#a8edea,#fed6e3)',
  'linear-gradient(135deg,#d4fc79,#96e6a1)',
  'linear-gradient(135deg,#ffecd2,#fcb69f)',
  'linear-gradient(135deg,#a1c4fd,#c2e9fb)',
  'linear-gradient(135deg,#fbc2eb,#a6c1ee)',
  'linear-gradient(135deg,#fddb92,#d1fdff)',
  'linear-gradient(135deg,#e0c3fc,#8ec5fc)',
  'linear-gradient(135deg,#f6d365,#fda085)',
]

export function useOrderFormatters() {
  const formatPrice = (val) => {
    const n = Number(val)
    if (isNaN(n)) return val
    return n % 1 === 0 ? String(n) : n.toFixed(2)
  }

  // 商品浏览价格展示（FORMATTER_1 / PRODUCT_PRICE_DISPLAY）：最多两位小数，
  // 去掉无意义的末尾 0 和小数点，让整桌菜价格式一致（不会 ¥128 和 ¥34.80 并排）。
  // 只用于菜单浏览场景的商品售价；支付 / 退款 / 应付 / 实付 / 结算等财务金额
  // 一律固定两位小数（见各自的 toFixed(2)），不走这个 formatter。
  //   128 → 128        128.00 → 128        128.5 → 128.5
  //   34.80 → 34.8     49.888 → 49.89      0.01 → 0.01
  // 先 toFixed(2) 再裁零：既限死两位精度，也不会把 34.7999999 这类浮点误差暴露出来。
  const formatProductPrice = (val) => {
    const n = Number(val)
    if (isNaN(n)) return val
    return n.toFixed(2).replace(/\.?0+$/, '')
  }

  // 存量菜品图片是商家直接传的原图（可能几MB），在服务端加处理管线之前上传的图都是这样，
  // 重新上传前没法改变已经存在 COS 上的文件本身。用 COS 万象缩略图参数在“读”的时候按需
  // 裁一份小图，不用等商家重新上传就能立刻覆盖全部存量图片；只对 http(s) 的 COS 图片链接
  // 生效，本地占位图/相对路径原样返回。size 是缩略图目标宽度（像素），列表小图和详情大图
  // 用不同的值，没必要都按详情图的尺寸下载。
  const withCosThumbnail = (url, size) => {
    if (!url || typeof url !== 'string' || !/^https?:\/\//i.test(url)) return url
    const sep = url.includes('?') ? '&' : '?'
    return `${url}${sep}imageMogr2/thumbnail/${size}x/format/webp`
  }

  const dishImage = (dish, size = 240) => withCosThumbnail(dish.image_url || dish.image || dish.cover_image || '', size)

  const dishPlaceholderStyle = (dish) => {
    const idx = (dish.name || '').charCodeAt(0) % placeholderGradients.length
    return { background: placeholderGradients[idx] }
  }

  const hasSpecs = (dish) => {
    const tags = Array.isArray(dish.tags) ? dish.tags : String(dish.tags || '').split(new RegExp('[,\\s\\uFF0C\\u3001]+')).map(t => t.trim()).filter(Boolean)
    return !!dish.has_options || !!dish.hasOptions || tags.includes('多规格') || tags.includes('规格') || (Array.isArray(dish.spec_groups) && dish.spec_groups.length > 0) || (Array.isArray(dish.specs) && dish.specs.length > 0) || (Array.isArray(dish.spec_options) && dish.spec_options.length > 0)
  }

  const isSoldOut = (dish) => dish.available === false || dish.sold_out === true || dish.is_sold_out === true || ['sold_out', 'soldout', 'unavailable'].includes(String(dish.status || '').toLowerCase()) || (dish.stock !== undefined && dish.stock !== null && dish.stock !== '' && Number(dish.stock) <= 0)

  const dishCardDesc = (dish) => {
    const desc = String(dish.desc || dish.description || '').trim()
    if (desc) return desc
    if (hasSpecs(dish)) return '多规格可选'
    return ''
  }

  const dishPriceBase = (dish) => Number(dish.min_price ?? dish.price_min ?? dish.price ?? 0)
  const dishPriceText = (dish) => formatProductPrice(dishPriceBase(dish))
  const dishPriceSuffix = (dish) => hasSpecs(dish) || Number(dish.max_price || dish.price_max || 0) > dishPriceBase(dish) ? '起' : ''
  const dishOriginalPrice = (dish) => dish.original_price || dish.market_price || ''
  const showDishSales = (dish) => Number(dish.sales_count || 0) >= 10

  const couponAmountText = (coupon) => formatPrice(coupon?.value ?? coupon?.amount ?? coupon?.discount_amount ?? 0)
  const couponConditionText = (coupon) => {
    const min = Number(coupon?.min_amount ?? coupon?.threshold_amount ?? coupon?.threshold ?? 0)
    return min > 0 ? '满' + formatPrice(min) + '元可用' : '无门槛可用'
  }
  const couponValidityText = (coupon) => {
    const raw = coupon?.expire_time || coupon?.valid_end_time || coupon?.end_time || ''
    if (!raw) return '当前可用'
    // 后端 expire_time 是裸 UTC，必须走 parseServerTime，否则差 8 小时，
    // 会把明天到期的显示成"今日有效"、把今天到期的显示成明天。日期比较也按北京口径。
    const end = parseServerTime(raw)
    if (!end) return '当前可用'
    const endDate = formatBeijingDate(end)       // YYYY-MM-DD
    if (endDate === formatBeijingDate(new Date())) return '今日有效'
    return '有效期至' + endDate.slice(5, 7) + '.' + endDate.slice(8, 10)
  }
  const couponPickerAmount = (c) => formatPrice(c.value || c.amount || 0)
  const couponPickerCondText = (c) => {
    const min = Number(c.min_amount || c.threshold_amount || 0)
    return min > 0 ? '满' + formatPrice(min) + '元可用' : '无门槛可用'
  }

  const orderItemName = (item) => item?.orderName || item?.name || item?.goods_name || item?.dish_name || '商品'
  const orderItemQty = (item) => Number(item?.qty || item?.quantity || item?.count || 1)
  const orderItemAmount = (item) => Number(item?.amount ?? item?.total ?? (Number(item?.price || 0) * orderItemQty(item)))
  const orderItemSpecText = (item) => {
    if (item?.specLabel) return item.specLabel
    if (item?.spec_text) return item.spec_text
    if (Array.isArray(item?.specifications) && item.specifications.length) {
      return item.specifications.map(spec => spec.value || spec.name).filter(Boolean).join(' · ')
    }
    return ''
  }
  const orderItemImage = (item) => item?.image || item?.image_url || item?.cover || item?.cover_url || ''
  const orderItemCount = (order) => (order?.items || []).reduce((sum, item) => sum + Number(item.qty || 0), 0)

  const statusLabel = (s, statusText) => formatOrderStatusText(s, statusText)

  const dishTags = (dish) => {
    if (Array.isArray(dish.tags) && dish.tags.length) return dish.tags.slice(0, 3)
    if (typeof dish.tags === 'string' && dish.tags.trim()) {
      return dish.tags.split(new RegExp('[,\\s\\uFF0C\\u3001]+')).map(t => t.trim()).filter(Boolean).slice(0, 3)
    }
    return []
  }

  const strongDishTags = ['招牌', '热销', '店长推荐', '新品']
  const normalizeDishTag = (tag) => {
    const text = String(tag || '').trim()
    if (['推荐', '必点', '必吃'].includes(text)) return '招牌'
    if (text === '火爆') return '热销'
    return text
  }
  const isStrongDishTag = (tag) => tag === '已售罄' || strongDishTags.includes(tag)
  const dishCardTags = (dish) => {
    if (isSoldOut(dish)) return ['已售罄']
    const normalized = dishTags(dish).map(normalizeDishTag).filter(Boolean)
    for (const tag of strongDishTags) {
      if (normalized.includes(tag)) return [tag]
    }
    return []
  }
  const isFeatured = (dish) => {
    const tags = dishTags(dish).map(normalizeDishTag)
    return tags.includes('招牌') || tags.includes('热销') || tags.includes('新品')
  }

  const pickAvatarChar = (name) => {
    const chars = Array.from(String(name || '').trim())
    const ch = chars.find(c => /[一-龥a-zA-Z0-9]/.test(c))
    if (!ch) return '会'
    return /[a-z]/.test(ch) ? ch.toUpperCase() : ch
  }

  return {
    formatPrice,
    formatProductPrice,
    dishImage,
    dishPlaceholderStyle,
    hasSpecs,
    isSoldOut,
    dishCardDesc,
    dishPriceBase,
    dishPriceText,
    dishPriceSuffix,
    dishOriginalPrice,
    showDishSales,
    couponAmountText,
    couponConditionText,
    couponValidityText,
    couponPickerAmount,
    couponPickerCondText,
    orderItemName,
    orderItemQty,
    orderItemAmount,
    orderItemSpecText,
    orderItemImage,
    orderItemCount,
    statusLabel,
    dishTags,
    strongDishTags,
    normalizeDishTag,
    isStrongDishTag,
    dishCardTags,
    isFeatured,
    pickAvatarChar,
  }
}
