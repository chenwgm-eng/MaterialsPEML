<template>
  <div class="loading-skeleton" :class="`skeleton--${type}`">
    <!-- table：表头 + N 行骨架行（每行 columns 个占位块） -->
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

    <!-- card：3-4 个卡片骨架 -->
    <div v-else-if="type === 'card'" class="skeleton-cards">
      <a-card
        v-for="n in cardCount"
        :key="`card-${n}`"
        size="small"
        :bordered="false"
        class="skeleton-card"
      >
        <a-skeleton :active="true" :paragraph="{ rows: 3 }" />
      </a-card>
    </div>

    <!-- list：N 行列表骨架（每行：图标 + 两行文本） -->
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

    <!-- detail：标题 + 描述项骨架 -->
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
  </div>
</template>

<script setup>
import { computed } from 'vue'

/**
 * 纯骨架屏组件（T-044）
 *
 * 仅负责按 type 渲染对应形状的骨架屏，不感知 loading 状态、不处理超时/取消。
 * 由 SmartLoading 包裹使用，或独立使用 v-if 控制 mount。
 *
 * Props：
 * - type: 'table' | 'card' | 'list' | 'detail'，默认 'list'
 * - rows: list/table/detail 生效，默认 5
 * - columns: table 生效，默认 3
 */
const props = defineProps({
  type: {
    type: String,
    default: 'list',
    validator: (v) => ['table', 'card', 'list', 'detail'].includes(v),
  },
  rows: { type: Number, default: 5 },
  columns: { type: Number, default: 3 },
})

// card 类型固定 4 个卡片（任务要求 3-4 个）
const cardCount = 4

// grid-template-columns 不能用 CSS 变量作为 repeat 计数，需在 JS 侧计算后内联
const tableRowStyle = computed(() => ({
  gridTemplateColumns: `repeat(${props.columns}, minmax(0, 1fr))`,
}))
</script>

<style scoped>
.loading-skeleton {
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

/* ===== card ===== */
.skeleton-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.skeleton-card {
  background: var(--light-bg-hover, #fafafa);
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
</style>
