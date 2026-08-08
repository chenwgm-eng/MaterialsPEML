<template>
  <a-drawer
    :open="modelValue"
    :title="title"
    :width="width"
    placement="right"
    :closable="true"
    :destroy-on-close="destroyOnClose"
    @update:open="(v) => emit('update:modelValue', v)"
  >
    <template #extra>
      <slot name="extra" />
    </template>

    <!-- 二级导航：页面标题下方、内容区上方的横向 Tab -->
    <div v-if="tabs.length" class="dd-tabs">
      <a-tabs v-model:activeKey="activeTab" size="small" :tabBarStyle="{ marginBottom: '8px' }">
        <a-tab-pane v-for="t in tabs" :key="t.key" :tab="t.label" />
      </a-tabs>
    </div>

    <!-- 内容体：统一滚动，避免嵌套滚动导致的截断 -->
    <div class="dd-body">
      <slot :active-tab="activeTab" />
    </div>
  </a-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  width: { type: [String, Number], default: 560 },
  // 横向 Tab：{ key, label }
  tabs: { type: Array, default: () => [] },
  destroyOnClose: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const activeTab = ref(props.tabs[0]?.key || '')

watch(
  () => props.tabs,
  (tabs) => {
    if (!tabs.some((t) => t.key === activeTab.value)) {
      activeTab.value = tabs[0]?.key || ''
    }
  },
  { deep: true },
)
</script>

<style scoped>
.dd-tabs {
  border-bottom: 1px solid var(--border-light, #f0f0f0);
  margin: 0 calc(-1 * var(--space-lg, 16px));
  padding: 0 var(--space-lg, 16px);
}

.dd-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 0;
}

.dd-body {
  margin: 0 calc(-1 * var(--space-lg, 16px));
  padding: 0 var(--space-lg, 16px);
  overflow-y: auto;
  height: 100%;
}
</style>