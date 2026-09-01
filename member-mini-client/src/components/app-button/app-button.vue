<template>
  <button
    class="app-button"
    :class="[
      `app-button--${normalizedVariant}`,
      `app-button--${normalizedSize}`,
      { 'app-button--block': block, 'app-button--loading': loading },
    ]"
    :disabled="isDisabled"
    :loading="false"
    @click="handleClick"
  >
    <view v-if="loading" class="app-button-spinner"></view>
    <text class="app-button-content"><slot /></text>
  </button>
</template>

<script>
const VARIANTS = ['primary', 'secondary', 'ghost', 'danger']
const SIZES = ['sm', 'md', 'lg']

export default {
  name: 'AppButton',
  options: {
    virtualHost: true,
  },
  props: {
    variant: {
      type: String,
      default: 'primary',
      validator(value) {
        return VARIANTS.includes(value)
      },
    },
    size: {
      type: String,
      default: 'md',
      validator(value) {
        return SIZES.includes(value)
      },
    },
    block: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
  },
  emits: ['click'],
  computed: {
    normalizedVariant() {
      return VARIANTS.includes(this.variant) ? this.variant : 'primary'
    },
    normalizedSize() {
      return SIZES.includes(this.size) ? this.size : 'md'
    },
    isDisabled() {
      return this.disabled || this.loading
    },
  },
  methods: {
    handleClick(event) {
      if (this.isDisabled) return
      this.$emit('click', event)
    },
  },
}
</script>

<style lang="scss" scoped>
.app-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  margin: 0;
  padding: 0 var(--space-24);
  border: none;
  border-radius: var(--radius-pill);
  box-sizing: border-box;
  font-size: var(--font-body);
  font-weight: var(--btn-primary-font-weight);
  line-height: 1;
  transition: transform var(--motion-fast) ease, opacity var(--motion-fast) ease;

  &::after {
    border: none;
  }

  &:active {
    transform: scale(0.96);
  }
}

.app-button--block {
  display: flex;
  width: 100%;
}

.app-button--sm {
  height: var(--control-sm);
  min-height: 72rpx;
  padding: 0 var(--space-20);
  font-size: var(--font-meta);
}

.app-button--md {
  height: var(--control-md);
  min-height: 88rpx;
  padding: 0 var(--space-24);
  font-size: var(--font-body);
}

.app-button--lg {
  height: var(--control-lg);
  min-height: 100rpx;
  padding: 0 var(--space-32);
  font-size: var(--btn-primary-font-size);
}

.app-button--primary {
  background: var(--brand);
  color: var(--text-inverse);
}

.app-button--secondary {
  background: var(--brand-light);
  color: var(--brand-dark);
}

.app-button--ghost {
  background: transparent;
  color: var(--text-2);
}

.app-button--danger {
  background: var(--danger);
  color: var(--text-inverse);
}

.app-button[disabled],
.app-button--loading {
  opacity: 0.56;
  transform: none;
}

.app-button-content {
  display: block;
  max-width: 100%;
  overflow: hidden;
  color: inherit;
  font-size: inherit;
  font-weight: inherit;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-button-spinner {
  position: absolute;
  left: var(--space-24);
  width: 28rpx;
  height: 28rpx;
  border: 4rpx solid rgba(255, 255, 255, 0.45);
  border-top-color: currentColor;
  border-radius: 50%;
  box-sizing: border-box;
  animation: appButtonSpin 780ms linear infinite;
}

.app-button--secondary .app-button-spinner,
.app-button--ghost .app-button-spinner {
  border-color: rgba(5, 153, 82, 0.22);
  border-top-color: currentColor;
}

@keyframes appButtonSpin {
  to { transform: rotate(360deg); }
}
</style>
