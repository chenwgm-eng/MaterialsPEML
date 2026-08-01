<template>
  <div class="app-skeleton-loader" :class="`skeleton--${type}`">
    <!-- 骨架主体 -->
    <div v-if="type === 'table'" class="skeleton-table">
      <div class="skeleton-table-row skeleton-table-header" :style="tableRowStyle">
        <a-skeleton-button
          v-for="c in columns"
          :key="`th-${c}`"
          :active="true"
          size="small"
          style="width: 100%"
        />
      </div>
      <div
        v-for="r in rows"
        :key="`tr-${r}`"
        class="skeleton-table-row"
        :style="tableRowStyle"
      >
        <a-skeleton-button
          v-for="c in columns"
          :key="`td-${r}-${c}`"
          :active="true"
          size="small"
          style="width: 100%"
        />
      </div>
    </div>

    <a-skeleton
      v-else-if="type === 'card'"
      :active="true"
      :paragraph="{ rows }"
    />

    <div v-else-if="type === 'list'" class="skeleton-list">
      <a-skeleton
        v-for="r in rows"
        :key="`li-${r}`"
        :active="true"
        :avatar="true"
        :paragraph="{ rows: 1 }"
        class="skeleton-list-item"
      />
    </div>

    <div v-else-if="type === 'detail'" class="skeleton-detail">
      <a-skeleton :active="true" :paragraph="{ rows: 1 }" />
      <div
        v-for="r in rows"
        :key="`d-${r}`"
        class="skeleton-detail-row"
      >
        <a-skeleton-button :active="true" size="small" style="width: 96px" />
        <a-skeleton-input :active="true" size="small" style="width: 60%" />
      </div>
    </div>

    <div v-else-if="type === 'form'" class="skeleton-form">
      <div
        v-for="r in rows"
        :key="`f-${r}`"
        class="skeleton-form-row"
      >
        <a-skeleton-button :active="true" size="small" style="width: 80px" />
        <a-skeleton-input :active="true" size="small" style="width: 100%" />
      </div>
    </div>

    <!-- 进度说明 + 取消按钮（超过 delay 后显示） -->
    <div v-if="showProgress" class="skeleton-progress">
      <span class="skeleton-progress-text">{{ loadingText }}</span>
      <a-button
        v-if="cancellable"
        size="small"
        @click="onCancel"
      >取消</a-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useLoadingTimeout } from '@/composables/useLoadingTimeout'

/**
 * 通用骨架屏组件（T-044）
 *
 * 设计要点：
 * - 组件本身不接收 loading 状态：父级用 v-if="loading" 控制其挂载/卸载，
 *   组件挂载期间视为「加载中」，由 useLoadingTimeout 内部计时。
 * - 超过 delay 毫秒仍挂载时，展示进度说明文案与可选的取消按钮。
 * - 不同 type 渲染不同骨架形状，覆盖表格/卡片/列表/详情/表单等常见区域。
 *
 * 用法：
 *   <SkeletonLoader v-if="loading" type="card" :rows="3" :delay="2000" cancellable @cancel="onCancel" />
 *   <ActualContent v-else />
 */
const props = defineProps({
  type: {
    type: String,
    default: 'card',
    validator: (v) => ['table', 'card', 'list', 'detail', 'form'].includes(v),
  },
  rows: { type: Number, default: 3 },
  columns: { type: Number, default: 3 },
  delay: { type: Number, default: 2000 },
  cancellable: { type: Boolean, default: false },
  loadingText: { type: String, default: '正在加载...' },
})

const emit = defineEmits(['cancel'])

// 组件仅在加载中渲染，内部 loading 恒为 true
const loading = ref(true)
const { showProgress, cancel } = useLoadingTimeout(loading, props.delay)

// grid-template-columns 不能用 CSS 变量作为 repeat 计数，需在 JS 侧计算后内联
const tableRowStyle = computed(() => ({
  gridTemplateColumns: `repeat(${props.columns}, minmax(0, 1fr))`,
}))

function onCancel() {
  cancel()
  emit('cancel')
}
</script>

<style scoped>
.app-skeleton-loader {
  padding: 16px;
  width: 100%;
}

/* ===== table ===== */
.skeleton-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-table-row {
  display: grid;
  gap: 8px;
}

.skeleton-table-header {
  margin-bottom: 4px;
}

/* ===== list ===== */
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== detail ===== */
.skeleton-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ===== form ===== */
.skeleton-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skeleton-form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ===== progress ===== */
.skeleton-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-light, #f0f0f0);
}

.skeleton-progress-text {
  font-size: 13px;
  color: var(--text-secondary, #595959);
}
</style>
