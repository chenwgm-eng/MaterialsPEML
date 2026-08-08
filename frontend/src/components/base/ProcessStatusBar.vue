<template>
  <div class="ps-bar" :class="{ 'ps-bar--clickable': clickable }">
    <!-- 可选：当前状态描述 -->
    <div v-if="title" class="ps-title">{{ title }}</div>
    <div class="ps-track">
      <template v-for="(step, idx) in steps" :key="step.key">
        <div
          class="ps-step"
          :class="{
            'is-past': idx < currentIndex,
            'is-current': idx === currentIndex,
            'is-future': idx > currentIndex,
          }"
          @click="clickable && emit('select', step.key)"
        >
          <span class="ps-dot">
            <CheckOutlined v-if="idx < currentIndex" />
            <span v-else-if="idx === currentIndex" class="ps-dot-core" />
          </span>
          <span class="ps-step-label">{{ step.label }}</span>
        </div>
        <span v-if="idx < steps.length - 1" class="ps-connector" />
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CheckOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  // 流程步骤：{ key, label }
  steps: { type: Array, default: () => [] },
  // 当前步骤 key 或 index
  current: { type: [String, Number], default: 0 },
  // 可选标题（如"候选材料状态流转"）
  title: { type: String, default: '' },
  // 是否可点击步骤跳转到对应筛选
  clickable: { type: Boolean, default: false },
})

const emit = defineEmits(['select'])

const currentIndex = computed(() => {
  if (typeof props.current === 'number') return props.current
  const i = props.steps.findIndex((s) => s.key === props.current)
  return i < 0 ? 0 : i
})
</script>

<style scoped>
.ps-bar {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs, 4px);
}

.ps-title {
  font-size: var(--font-size-sm, 12px);
  font-weight: 600;
  color: var(--text-secondary);
}

.ps-track {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  overflow-x: auto;
}

.ps-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}

.ps-bar--clickable .ps-step {
  cursor: pointer;
}

.ps-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 11px;
  transition: all var(--transition, 0.2s);
}

.ps-step.is-past .ps-dot {
  background: var(--success);
  color: #fff;
}

.ps-step.is-current .ps-dot {
  background: var(--primary);
  color: #fff;
  box-shadow: 0 0 0 3px var(--primary-bg);
}

.ps-dot-core {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #fff;
}

.ps-step.is-future .ps-dot {
  background: var(--border);
  color: var(--text-muted);
}

.ps-step-label {
  font-size: var(--font-size-sm, 12px);
  color: var(--text-secondary);
}

.ps-step.is-current .ps-step-label {
  color: var(--primary);
  font-weight: 600;
}

.ps-step.is-future .ps-step-label {
  color: var(--text-muted);
}

.ps-connector {
  flex: 0 0 24px;
  height: 1px;
  background: var(--border);
  margin: 0 6px;
}
</style>