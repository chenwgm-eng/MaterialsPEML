<template>
  <div class="cs-section" :class="{ 'is-open': open }">
    <div class="cs-header" @click="open = !open" role="button" :aria-expanded="open">
      <span class="cs-caret">
        <RightOutlined />
      </span>
      <span class="cs-title" v-if="title">{{ title }}</span>
      <span class="cs-extra"><slot name="extra" /></span>
    </div>
    <div v-show="open" class="cs-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { RightOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  title: { type: String, default: '' },
  // 默认展开状态
  defaultOpen: { type: Boolean, default: false },
})

const open = ref(props.defaultOpen)

watch(
  () => props.defaultOpen,
  (v) => {
    open.value = v
  },
)
</script>

<style scoped>
.cs-section {
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: var(--radius-md, 6px);
  overflow: hidden;
}

.cs-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--light-bg-hover, #fafafa);
  cursor: pointer;
  user-select: none;
  font-size: var(--font-size-md, 13px);
  font-weight: 500;
  color: var(--text-primary);
}

.cs-header:hover {
  background: var(--light-bg-active, #fff7ed);
}

.cs-caret {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  color: var(--text-muted);
  transition: transform var(--transition, 0.2s);
}

.cs-section.is-open .cs-caret {
  transform: rotate(90deg);
}

.cs-extra {
  margin-left: auto;
  font-weight: 400;
  color: var(--text-muted);
}

.cs-body {
  padding: 12px;
  border-top: 1px solid var(--border-light, #f0f0f0);
}
</style>