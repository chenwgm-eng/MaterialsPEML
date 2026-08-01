<template>
  <div
    class="stat-card"
    :class="{ clickable }"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    :aria-label="clickable ? `${label}: ${value}` : undefined"
    @click="onClick"
    @keydown.enter.prevent="onClick"
    @keydown.space.prevent="onClick"
  >
    <a-tooltip v-if="tooltip" :title="tooltip" placement="bottom">
      <div class="stat-icon" v-if="icon" :style="{ color: iconColor }">
        <component :is="icon" />
      </div>
      <div class="stat-body">
        <div class="stat-value">
          <AnimatedNumber :value="value" :decimals="decimals" />
        </div>
        <div class="stat-label">{{ label }}</div>
        <div v-if="subText" class="stat-sub" :class="{ 'stat-sub-alert': subAlert }">{{ subText }}</div>
        <div v-if="trend !== undefined" class="stat-trend" :class="trend >= 0 ? 'up' : 'down'">
          <span aria-hidden="true">{{ trend >= 0 ? '↑' : '↓' }}</span> {{ Math.abs(trend) }}%
        </div>
      </div>
    </a-tooltip>
    <template v-else>
      <div class="stat-icon" v-if="icon" :style="{ color: iconColor }">
        <component :is="icon" />
      </div>
      <div class="stat-body">
        <div class="stat-value">
          <AnimatedNumber :value="value" :decimals="decimals" />
        </div>
        <div class="stat-label">{{ label }}</div>
        <div v-if="subText" class="stat-sub" :class="{ 'stat-sub-alert': subAlert }">{{ subText }}</div>
        <div v-if="trend !== undefined" class="stat-trend" :class="trend >= 0 ? 'up' : 'down'">
          <span aria-hidden="true">{{ trend >= 0 ? '↑' : '↓' }}</span> {{ Math.abs(trend) }}%
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import AnimatedNumber from './AnimatedNumber.vue'

const props = defineProps({
  value: { type: [Number, String], default: 0 },
  label: { type: String, default: '' },
  icon: { type: null, default: null },
  iconColor: { type: String, default: '#f97316' },
  trend: { type: Number, default: undefined },
  decimals: { type: Number, default: 0 },
  clickable: { type: Boolean, default: false },
  tooltip: { type: String, default: '' },
  subText: { type: String, default: '' },
  subAlert: { type: Boolean, default: false },
})

const emit = defineEmits(['click'])

function onClick() {
  if (props.clickable) emit('click')
}
</script>

<style scoped>
.stat-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: var(--shadow-card);
  transition: box-shadow var(--transition), border-color var(--transition), transform var(--transition);
}

.stat-card.clickable {
  cursor: pointer;
}

.stat-card.clickable:hover {
  border-color: var(--primary-border);
  box-shadow: var(--shadow-hover);
  transform: translateY(-1px);
}

.stat-card:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.stat-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.stat-body {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.stat-sub {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 3px;
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
}

.stat-sub.stat-sub-alert {
  color: var(--error);
  font-weight: 600;
}

.stat-trend {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  margin-top: 4px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.stat-trend.up {
  color: var(--success);
}

.stat-trend.down {
  color: var(--error);
}
</style>
