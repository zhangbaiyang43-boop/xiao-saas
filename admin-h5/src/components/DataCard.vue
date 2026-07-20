<template>
  <div class="data-card card" :class="{ 'gradient-card': gradient }" @click="handleClick">
    <div class="data-card-icon" v-if="icon">
      <van-icon :name="icon" :size="24" />
    </div>
    <div class="data-card-content">
      <div class="data-card-value">
        <span v-if="prefix">{{ prefix }}</span>
        {{ formattedValue }}
        <span v-if="suffix">{{ suffix }}</span>
      </div>
      <div class="data-card-label">{{ label }}</div>
    </div>
    <div v-if="trend" class="data-card-trend" :class="trendType">
      <van-icon :name="trendIcon" size="12" />
      <span>{{ trend }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon as VanIcon } from 'vant'

const props = defineProps({
  icon: {
    type: String,
    default: ''
  },
  value: {
    type: [Number, String],
    default: 0
  },
  label: {
    type: String,
    default: ''
  },
  prefix: {
    type: String,
    default: ''
  },
  suffix: {
    type: String,
    default: ''
  },
  trend: {
    type: String,
    default: ''
  },
  trendType: {
    type: String,
    default: 'up',
    validator: (val) => ['up', 'down', 'neutral'].includes(val)
  },
  gradient: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['click'])

const formattedValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString()
  }
  return props.value
})

const trendIcon = computed(() => {
  if (props.trendType === 'up') return 'arrow-up'
  if (props.trendType === 'down') return 'arrow-down'
  return 'minus'
})

const handleClick = () => {
  emit('click')
}
</script>

<style lang="scss" scoped>
.data-card {
  padding: $spacing-md;
  display: flex;
  align-items: center;
  gap: $spacing-base;
  
  &.gradient-card {
    background: $primary-color;
    color: #FFFFFF;
    
    .data-card-label,
    .data-card-trend,
    .data-card-icon {
      color: rgba(255, 255, 255, 0.8);
    }
  }
  
  &:active {
    transform: scale(0.98);
  }
}

.data-card-icon {
  width: 44px;
  height: 44px;
  border-radius: $radius-lg;
  background: rgba(124, 58, 237, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: $primary-main;
  flex-shrink: 0;
  
  .gradient-card & {
    background: rgba(255, 255, 255, 0.2);
    color: #FFFFFF;
  }
}

.data-card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.data-card-value {
  font-size: $font-size-xl;
  font-weight: 700;
  color: $text-primary;
  display: flex;
  align-items: baseline;
  gap: 2px;
  
  .gradient-card & {
    color: #FFFFFF;
  }
}

.data-card-label {
  font-size: $font-size-xs;
  color: $text-tertiary;
  
  .gradient-card & {
    color: rgba(255, 255, 255, 0.8);
  }
}

.data-card-trend {
  font-size: $font-size-xs;
  display: flex;
  align-items: center;
  gap: 2px;
  
  &.up {
    color: #52C41A;
  }
  
  &.down {
    color: #FF4757;
  }
  
  &.neutral {
    color: $text-tertiary;
  }
  
  .gradient-card &.up {
    color: #95DE64;
  }
  
  .gradient-card &.down {
    color: #FF7875;
  }
}
</style>
