<template>
  <div class="row-actions" @focusout="onFocusOut">
    <button type="button" class="view-btn tap-shrink" @click="$emit('view')">查看商户</button>
    <div class="menu-wrap">
      <button
        ref="trigger"
        type="button"
        class="more-trigger tap-shrink"
        aria-haspopup="menu"
        :aria-expanded="open ? 'true' : 'false'"
        :aria-label="`${merchant.name} 的更多操作`"
        title="更多操作"
        @click="toggle"
      >···</button>
      <div v-if="open" ref="menu" class="menu" role="menu" @keydown.esc.stop.prevent="close(true)">
        <button type="button" role="menuitem" class="menu-item" @click="pick('pay-config')">收款配置</button>
        <button type="button" role="menuitem" class="menu-item" @click="pick('toggle-danger')">{{ dangerOpen ? '收起危险操作' : '危险操作' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

defineProps({
  merchant: { type: Object, required: true },
  dangerOpen: { type: Boolean, default: false },
})
const emit = defineEmits(['view', 'pay-config', 'toggle-danger'])

const open = ref(false)
const trigger = ref(null)
const menu = ref(null)

function close(returnFocus = false) {
  open.value = false
  if (returnFocus) nextTick(() => trigger.value?.focus())
}

function toggle() {
  open.value = !open.value
}

function pick(name) {
  close(false)
  emit(name)
}

// Close when keyboard focus leaves this control group (Tab away).
function onFocusOut(event) {
  if (!open.value) return
  const next = event.relatedTarget
  if (next && event.currentTarget.contains(next)) return
  open.value = false
}

function onDocumentPointerDown(event) {
  if (!open.value) return
  const root = trigger.value?.closest('.row-actions')
  if (root && !root.contains(event.target)) open.value = false
}

watch(open, async (isOpen) => {
  if (isOpen) {
    document.addEventListener('mousedown', onDocumentPointerDown)
    await nextTick()
    menu.value?.querySelector('[role="menuitem"]')?.focus()
  } else {
    document.removeEventListener('mousedown', onDocumentPointerDown)
  }
})

onBeforeUnmount(() => document.removeEventListener('mousedown', onDocumentPointerDown))
</script>

<style scoped>
.row-actions { display: inline-flex; align-items: center; gap: 6px; }
.view-btn {
  min-height: 32px; padding: 0 12px; border: 0; border-radius: 8px;
  background: var(--brand); color: #fff; font-size: 13px; font-weight: 800; white-space: nowrap; cursor: pointer;
}
.view-btn:focus-visible, .more-trigger:focus-visible, .menu-item:focus-visible { outline: 2px solid var(--hero-dark); outline-offset: 2px; }
.menu-wrap { position: relative; }
.more-trigger {
  min-width: 32px; min-height: 32px; padding: 0 8px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-card); color: var(--text-2); font-size: 16px; font-weight: 900; line-height: 1; cursor: pointer;
}
.menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 20; min-width: 132px; padding: 4px;
  border: 1px solid var(--border); border-radius: 10px; background: var(--bg-card); box-shadow: 0 8px 24px rgba(0,0,0,.14);
}
.menu-item {
  display: block; width: 100%; padding: 8px 10px; border: 0; border-radius: 6px; background: transparent;
  color: var(--text-1); font-size: 13px; font-weight: 700; text-align: left; white-space: nowrap; cursor: pointer;
}
.menu-item:hover { background: var(--bg-page); }
</style>
