<template>
  <div class="ub-filter-bar">
    <!-- 下拉筛选：统一"下拉 + 搜索框 + 重置"固定顺序与间距 -->
    <template v-for="f in filters" :key="f.key">
      <a-select
        v-if="f.type === 'select'"
        v-model:value="innerFilter[f.key]"
        :placeholder="f.placeholder || f.label"
        :options="f.options"
        :allow-clear="f.allowClear !== false"
        :show-search="f.showSearch !== false"
        option-filter-prop="label"
        :style="{ minWidth: f.width || '160px' }"
        size="small"
        :get-popup-container="getPopupContainer"
      />
      <a-select
        v-else-if="f.type === 'radio'"
        v-model:value="innerFilter[f.key]"
        :placeholder="f.placeholder || f.label"
        :options="f.options"
        size="small"
        :style="{ minWidth: f.width || '160px' }"
        :get-popup-container="getPopupContainer"
      />
    </template>

    <!-- 搜索框 -->
    <a-input
      v-if="searchPlaceholder"
      v-model:value="innerKeyword"
      :placeholder="searchPlaceholder"
      allow-clear
      size="small"
      class="ub-search"
      @press-enter="emit('search', innerKeyword)"
    >
      <template #prefix><SearchOutlined /></template>
    </a-input>

    <!-- 重置按钮 -->
    <a-button size="small" class="ub-reset" @click="onReset">
      <template #icon><ReloadOutlined /></template>
      重置
    </a-button>

    <slot name="extra" />
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  // 筛选器定义：{ key, label, type: 'select'|'radio', options, placeholder, width, allowClear, showSearch }
  filters: { type: Array, default: () => [] },
  // 搜索框占位文案；不传则隐藏搜索框
  searchPlaceholder: { type: String, default: '' },
  // 初始筛选值 { key: value }
  initial: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue', 'search', 'reset'])

const innerFilter = reactive({ ...props.initial })
const innerKeyword = ref('')

// 供 popup 挂载到 body，避免被父容器 overflow 裁剪
const getPopupContainer = () => document.body

// 外部变更 initial 时同步
watch(
  () => props.initial,
  (v) => {
    Object.entries(v).forEach(([k, val]) => {
      innerFilter[k] = val
    })
  },
  { deep: true },
)

// 筛选值变化时统一向外抛整包
watch(
  innerFilter,
  (v) => emit('update:modelValue', { ...v }),
  { deep: true },
)

function onReset() {
  Object.keys(innerFilter).forEach((k) => {
    innerFilter[k] = undefined
  })
  innerKeyword.value = ''
  emit('reset')
}
</script>

<style scoped>
.ub-filter-bar {
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
  flex-wrap: wrap;
  padding: var(--space-sm, 8px) var(--space-md, 12px);
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: var(--radius-md, 6px);
}

.ub-search {
  width: 200px;
}

.ub-reset {
  margin-left: auto;
}
</style>