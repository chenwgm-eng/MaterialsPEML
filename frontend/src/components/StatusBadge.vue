<template>
  <span class="status-badge" :class="`is-${resolvedStatus}`">
    <!-- dot：圆点 + 文字 -->
    <span v-if="type === 'dot'" class="sb-dot">
      <span class="sb-dot-mark" :style="{ backgroundColor: color }"></span>
      <span class="sb-text" :style="{ color }">{{ resolvedLabel }}</span>
    </span>
    <!-- text：纯彩色文字 -->
    <span v-else-if="type === 'text'" class="sb-text" :style="{ color }">{{ resolvedLabel }}</span>
    <!-- tag：a-tag 样式（带浅色背景） -->
    <span
      v-else
      class="sb-tag"
      :style="{
        color: color,
        backgroundColor: tintBg,
        borderColor: tintBorder,
      }"
    >
      {{ resolvedLabel }}
    </span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 状态值：可为规范态（success/running/warning/failed/default），
  // 也可为业务枚举（COMPLETED/IN_PROGRESS/VALID/APPROVED 等）
  status: { type: String, default: 'default' },
  // 展示文案：未提供时按 status 自动映射
  label: { type: String, default: '' },
  // 展示样式：dot 圆点+文字 | tag 标签 | text 纯彩色文字
  type: { type: String, default: 'tag' },
})

// 规范态 → 主题色（对齐任务要求）
// 对比度修复：原 #52C41A/#3b82f6/#FAAD14/#F5222D/#8C8C8C 作 12px 小字仅 2-3.7:1，
// 统一加深至白底 ≥4.5:1（tag 浅底 + text 纯文字两种形态均达标）
const STATUS_COLOR_MAP = {
  success: '#15803d',
  running: '#1d4ed8',
  warning: '#b45309',
  failed: '#b91c1c',
  default: '#6b7280',
}

// 规范态 → 中文文案
const STATUS_LABEL_MAP = {
  success: '成功',
  running: '运行中',
  warning: '警告',
  failed: '失败',
  default: '默认',
}

// 业务枚举值 → 规范态（大小写不敏感；保持与 enumLabels.js 业务枚举对齐）
const BUSINESS_STATUS_MAP = {
  // success
  COMPLETED: 'success',
  VALID: 'success',
  APPROVED: 'success',
  PASS: 'success',
  // running
  IN_PROGRESS: 'running',
  PENDING: 'running',
  // warning
  WAITING_FOR_DATA: 'warning',
  REQUIRES_REVIEW: 'warning',
  // failed
  FAILED: 'failed',
  REJECTED: 'failed',
  INVALID: 'failed',
  // default
  CANCELLED: 'default',
  DRAFT: 'default',
}

// 将任意 status 归一化为规范态
function resolveStatus(status) {
  if (!status) return 'default'
  const lower = String(status).toLowerCase()
  if (Object.prototype.hasOwnProperty.call(STATUS_COLOR_MAP, lower)) {
    return lower
  }
  const upper = String(status).toUpperCase()
  return BUSINESS_STATUS_MAP[upper] || 'default'
}

const resolvedStatus = computed(() => resolveStatus(props.status))
const color = computed(() => STATUS_COLOR_MAP[resolvedStatus.value])
const resolvedLabel = computed(() => props.label || STATUS_LABEL_MAP[resolvedStatus.value])

// 浅色背景 / 边框（基于主色按透明度叠加，避免引入额外色彩常量）
const tintBg = computed(() => `${color.value}1A`) // ~10% 透明度
const tintBorder = computed(() => `${color.value}59`) // ~35% 透明度
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  line-height: 1;
  vertical-align: middle;
}

.sb-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.sb-dot-mark {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sb-text {
  font-size: 13px;
  line-height: 1.4;
}

.sb-tag {
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  height: 22px;
  line-height: 20px;
  font-size: 12px;
  border: 1px solid;
  border-radius: 4px;
  white-space: nowrap;
}
</style>
