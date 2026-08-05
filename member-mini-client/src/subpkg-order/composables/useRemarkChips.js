import { computed } from 'vue'

// 从 menu.vue 拆出来的"备注 + 快捷标签"通用逻辑——菜品备注（itemRemark）和整单
// 备注（remark）用的是完全一样的一套规则：点一下标签就把对应文字加进/移出备注，
// 输入框里展示的文字要把这些标签摘掉（避免用户自己手打的内容和标签重复展示）。
// menu.vue 里实例化了两次，一次给菜品备注，一次给整单备注。逻辑跟原来在
// menu.vue 里的一字未改，只是搬了个位置、变成可复用的函数。
export function useRemarkChips(remarkRef, chipsRef) {
  const cleanedText = computed(() => {
    let text = remarkRef.value
    chipsRef.value.forEach((chip) => { text = text.split(chip).join('') })
    return text.replace(/\s+/g, ' ').trim()
  })
  const toggleChip = (chip) => {
    if (remarkRef.value.includes(chip)) {
      remarkRef.value = remarkRef.value.replace(chip, '').replace(/^\s+|\s+$/g, '').trim()
    } else {
      remarkRef.value = remarkRef.value ? remarkRef.value + ' ' + chip : chip
    }
  }
  return { cleanedText, toggleChip }
}
