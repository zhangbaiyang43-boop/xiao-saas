<template>
  <a-modal
    :open="open"
    title="生成印刷版桌贴"
    :confirm-loading="loading"
    :ok-button-props="{ disabled: exportable.length === 0 }"
    ok-text="生成并下载"
    cancel-text="取消"
    :mask-closable="!loading"
    :closable="!loading"
    @ok="$emit('confirm')"
    @cancel="$emit('update:open', false)"
  >
    <p v-if="exportable.length" style="font-size:14px;margin-bottom:10px">
      已选 <b style="color:var(--brand)">{{ exportable.length }}</b> 张可导出的桌贴码。
    </p>
    <a-alert
      v-else
      type="warning"
      show-icon
      message="选中的桌码里没有可导出的桌贴码"
      description="桌贴码需为：正式码、状态正常、有桌号、二维码已生成成功。"
      style="margin-bottom:10px"
    />

    <div class="spec">
      <div class="spec-t">导出内容</div>
      <ul>
        <li>成品 100 × 120 mm，300 DPI</li>
        <li>每桌一张 PNG</li>
        <li>单贴单页 PDF（送印厂）</li>
        <li>A4 四联 PDF（自己打印，带裁切线）</li>
        <li>导出说明文件，全部打包为一个 ZIP</li>
      </ul>
    </div>

    <div v-if="excluded.length" class="excluded">
      <div class="spec-t">{{ excluded.length }} 张已排除，不会进导出包</div>
      <ul>
        <li v-for="(item, i) in excluded" :key="i">
          <span class="ex-name">{{ item.name }}</span>
          <span class="ex-reason">{{ item.reason }}</span>
        </li>
      </ul>
    </div>

    <p class="hint">正式印刷前，务必先打印一张用两台手机各扫一次，核对进入本店、桌号对得上。</p>
  </a-modal>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  exportable: { type: Array, default: () => [] },
  excluded: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
defineEmits(['update:open', 'confirm'])
</script>

<style scoped lang="scss">
.spec, .excluded {
  background: var(--bg-page);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
  font-size: 13px;
}
.spec-t { font-weight: 700; color: var(--text-1); margin-bottom: 6px; }
.spec ul, .excluded ul { margin: 0; padding-left: 18px; color: var(--text-2); }
.spec li, .excluded li { margin: 2px 0; }
.excluded { max-height: 168px; overflow-y: auto; }
.ex-name { font-weight: 600; color: var(--text-1); margin-right: 8px; }
.ex-reason { color: var(--danger); }
.hint { font-size: 12px; color: var(--text-3); margin: 0; }
</style>
