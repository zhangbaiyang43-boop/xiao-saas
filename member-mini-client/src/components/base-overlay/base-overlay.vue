<template>
  <view
    v-if="isKnownLayer"
    class="base-overlay"
    :class="'base-overlay--' + layer"
  >
    <view class="base-overlay-backdrop" @click="$emit('mask-click')"></view>
    <slot />
  </view>
</template>

<script>
const KNOWN_LAYERS = ['blocking', 'blocking-top', 'critical']

export default {
  name: 'BaseOverlay',
  options: {
    virtualHost: true,
  },
  props: {
    layer: {
      type: String,
      required: true,
      validator(value) {
        return KNOWN_LAYERS.includes(value)
      },
    },
  },
  emits: ['mask-click'],
  computed: {
    isKnownLayer() {
      return KNOWN_LAYERS.includes(this.layer)
    },
  },
}
</script>

<style lang="scss">
.base-overlay {
  position: fixed;
  inset: 0;
}

.base-overlay-backdrop {
  position: absolute;
  inset: 0;
  background: var(--overlay-dim);
}

.base-overlay--blocking {
  z-index: var(--z-blocking);
}

.base-overlay--blocking-top {
  z-index: var(--z-blocking-top);
}

.base-overlay--critical {
  z-index: var(--z-critical);
}
</style>
