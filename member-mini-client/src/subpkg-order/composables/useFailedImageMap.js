import { ref } from 'vue'

// 从 menu.vue 拆出来的"图片加载失败就换成占位图"状态——本质就是一个
// key -> 是否失败 的映射，菜品图和订单商品图各用一份（互不影响，一个菜品图
// 挂了不会连累订单历史里同一道菜的缩略图）。menu.vue 里实例化两次。逻辑跟
// 原来的一字未改，只是搬了个位置、变成可复用的函数。
export function useFailedImageMap() {
  const failed = ref({})
  const markFailed = (key) => {
    failed.value = { ...failed.value, [key]: true }
  }
  return { failed, markFailed }
}
