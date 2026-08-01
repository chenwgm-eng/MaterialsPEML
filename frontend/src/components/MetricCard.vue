<template>
  <div class="metric-card" role="group" :aria-label="label">
    <div class="metric-card-value">
      <span class="metric-card-number">{{ displayValue }}</span>
      <span v-if="suffix" class="metric-card-suffix">{{ suffix }}</span>
    </div>
    <div class="metric-card-label">{{ label }}</div>
    <div v-if="trend != null" class="metric-card-trend" :class="trendClass">
      <component :is="trendIcon" aria-hidden="true" />
      <span>{{ Math.abs(trend) }}%</span>
      <span v-if="trendLabel" class="metric-card-trend-label">{{ trendLabel }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  value: { type: [Number, String], required: true },
  label: { type: String, required: true },
  suffix: { type: String, default: '' },
  trend: { type: Number, default: null },
  trendLabel: { type: String, default: '' },
})

const displayValue = computed(() => {
  const num = Number(props.value)
  if (Number.isFinite(num)) {
    return Number.isInteger(num) ? String(num) : num.toFixed(1)
  }
  return props.value
})

const trendClass = computed(() => {
  if (props.trend == null) return ''
  if (props.trend > 0) return 'metric-card-trend--up'
  if (props.trend < 0) return 'metric-card-trend--down'
  return 'metric-card-trend--flat'
})

const trendIcon = computed(() => {
  if (props.trend == null) return MinusOutlined
  if (props.trend > 0) return ArrowUpOutlined
  if (props.trend < 0) return ArrowDownOutlined
  return MinusOutlined
})
</script>

<style scoped>
.metric-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: var(--space-lg) var(--space-xl);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-fast), transform var(--transition-fast);
}

.metric-card:hover {
  box-shadow: var(--shadow-card);
  transform: translateY(-1px);
}

.metric-card-value {
  display: flex;
  align-items: baseline;
  gap: 4px;
  line-height: 1.2;
}

.metric-card-number {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-black);
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.metric-card-suffix {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.metric-card-label {
  font-size: var(--font-size-md);
  color: var(--text-muted);
  margin-top: var(--space-xs);
}

.metric-card-trend {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.metric-card-trend--up {
  color: var(--success);
}

.metric-card-trend--down {
  color: var(--error);
}

.metric-card-trend--flat {
  color: var(--text-muted);
}

.metric-card-trend-label {
  font-weight: var(--font-weight-normal);
  color: var(--text-muted);
  margin-left: 2px;
}
</style>
