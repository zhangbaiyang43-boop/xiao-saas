<template>
  <view
    class="app-tag"
    :class="[
      `app-tag--${normalizedTone}`,
      `app-tag--${normalizedSize}`,
      { 'app-tag--subtle': subtle },
    ]"
  >
    <text class="app-tag-text"><slot /></text>
  </view>
</template>

<script>
const TONES = ['brand', 'warning', 'danger', 'neutral']
const SIZES = ['sm', 'md']

export default {
  name: 'AppTag',
  options: {
    virtualHost: true,
  },
  props: {
    tone: {
      type: String,
      default: 'neutral',
      validator(value) {
        return TONES.includes(value)
      },
    },
    size: {
      type: String,
      default: 'sm',
      validator(value) {
        return SIZES.includes(value)
      },
    },
    subtle: { type: Boolean, default: true },
  },
  computed: {
    normalizedTone() {
      return TONES.includes(this.tone) ? this.tone : 'neutral'
    },
    normalizedSize() {
      return SIZES.includes(this.size) ? this.size : 'sm'
    },
  },
}
</script>

<style lang="scss" scoped>
.app-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  max-width: 100%;
  border-radius: var(--radius-sm);
  box-sizing: border-box;
  line-height: 1;
}

.app-tag-text {
  display: block;
  max-width: 100%;
  overflow: hidden;
  color: inherit;
  font-size: inherit;
  font-weight: 600;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-tag--sm {
  height: 40rpx;
  padding: 0 var(--space-12);
  font-size: var(--font-caption);
}

.app-tag--md {
  height: 48rpx;
  padding: 0 var(--space-16);
  font-size: var(--font-meta);
}

.app-tag--brand {
  background: var(--brand);
  color: var(--text-inverse);
}

.app-tag--brand.app-tag--subtle {
  background: var(--brand-light);
  color: var(--brand-dark);
}

.app-tag--warning {
  background: var(--warning);
  color: var(--text-inverse);
}

.app-tag--warning.app-tag--subtle {
  background: #fff7e6;
  color: #b45309;
}

.app-tag--danger {
  background: var(--danger);
  color: var(--text-inverse);
}

.app-tag--danger.app-tag--subtle {
  background: #fee2e2;
  color: #b91c1c;
}

.app-tag--neutral {
  background: var(--bg-muted);
  color: var(--text-2);
}

.app-tag--neutral.app-tag--subtle {
  background: var(--bg-subtle);
  color: var(--text-3);
}
</style>
