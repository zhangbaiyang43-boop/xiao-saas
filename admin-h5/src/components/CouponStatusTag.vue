<template>
  <a-tag :color="COLOR_MAP[status] || 'default'" :size="size">{{ TEXT_MAP[status] || status || '-' }}</a-tag>
</template>

<script setup>
// 优惠券四态标签：UNUSED/USED/EXPIRED/REVOKED 是同一个业务状态，之前分别在
// CouponRecords.vue（Vant van-tag，四态区分）和 CustomerDetail.vue（Ant a-tag，
// 只判断 UNUSED 其余全拍成 default）各画一遍，同一张券在两个页面颜色不一致。
// 这里只表达语义，不做任何请求或业务判断（状态本身仍由调用方传入）。
defineProps({
  status: { type: String, default: '' },
  size: { type: String, default: 'small' },
})

const TEXT_MAP = {
  UNUSED: '未使用',
  USED: '已使用',
  EXPIRED: '已过期',
  REVOKED: '已收回',
}

// 颜色语义沿用 CouponRecords.vue 原有的四态区分（更完整）：未使用=待处理提醒，
// 已使用=好结果，已过期=中性已结束，已收回=商家主动作废，跟"已过期"含义不同不能合并。
const COLOR_MAP = {
  UNUSED: 'warning',
  USED: 'success',
  EXPIRED: 'default',
  REVOKED: 'error',
}
</script>
