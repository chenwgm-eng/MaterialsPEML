<template>
  <component
    :is="wrapperComponent"
    v-bind="wrapperProps"
    class="action-card"
    :class="{ 'action-card--link': !!to }"
  >
    <div class="action-card-main">
      <div v-if="icon" class="action-card-icon" aria-hidden="true">
        <component :is="icon" />
      </div>
      <div class="action-card-body">
        <div class="action-card-title">{{ title }}</div>
        <div v-if="description" class="action-card-desc">{{ description }}</div>
      </div>
    </div>
    <RightOutlined class="action-card-arrow" aria-hidden="true" />
  </component>
</template>

<script setup>
import { computed } from 'vue'
import { RightOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  to: { type: [String, Object], default: '' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: [Object, Function], default: null },
})

const emit = defineEmits(['click'])

const wrapperComponent = computed(() => (props.to ? 'router-link' : 'button'))
const wrapperProps = computed(() =>
  props.to
    ? { to: props.to }
    : { type: 'button', onClick: () => emit('click') },
)
</script>

<style scoped>
.action-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-lg) var(--space-xl);
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-fast), box-shadow var(--transition-fast), border-color var(--transition-fast);
  text-align: left;
  cursor: pointer;
  width: 100%;
}

.action-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
  border-color: var(--primary-border);
}

.action-card--link {
  color: inherit;
  text-decoration: none;
}

.action-card-main {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  min-width: 0;
}

.action-card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--radius-lg);
  background: var(--primary-bg);
  color: var(--primary);
  font-size: 20px;
  flex-shrink: 0;
}

.action-card-body {
  min-width: 0;
}

.action-card-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  line-height: 1.3;
}

.action-card-desc {
  font-size: var(--font-size-md);
  color: var(--text-secondary);
  margin-top: 2px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-card-arrow {
  color: var(--text-muted);
  font-size: 14px;
  transition: transform var(--transition-fast);
  flex-shrink: 0;
}

.action-card:hover .action-card-arrow {
  transform: translateX(3px);
  color: var(--primary);
}
</style>
