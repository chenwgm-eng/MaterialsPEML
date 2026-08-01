<template>
  <span class="sci-notation" :class="`size-${size}`">
    <span class="mantissa">{{ parts.mantissa }}</span>
    <template v-if="parts.exponent !== null">
      <span class="times">×</span>
      <span class="base">10</span>
      <sup class="exponent">{{ parts.exponent }}</sup>
    </template>
    <span v-if="unit" class="unit">{{ unit }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { formatPropValue, formatSci } from '@/utils/format'

const props = defineProps({
  value: { type: [Number, String], default: null },
  property: { type: String, default: '' },
  precision: { type: Number, default: 4 },
  unit: { type: String, default: '' },
  size: {
    type: String,
    default: 'medium',
    validator: (v) => ['small', 'medium', 'large'].includes(v),
  },
})

// formatSci 输出中的 Unicode 上标字符 → 常规字符，用于 <sup> 标签渲染（保证字体一致性）
const SUPERSCRIPT_REVERSE = {
  '⁻': '-', '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
  '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
}

function fromSuperscript(str) {
  return String(str)
    .split('')
    .map((ch) => SUPERSCRIPT_REVERSE[ch] || ch)
    .join('')
}

// 复用 format.js：property 给定时走 formatPropValue（属性感知自动选择格式），
// 否则走 formatSci（按 precision 截断）
const parts = computed(() => {
  const formatted = props.property
    ? formatPropValue(props.value, props.property)
    : formatSci(props.value, props.precision)
  // 解析 "mantissa×10exp" 形式（formatSci 科学计数法输出），将上标转为 <sup>
  const m = formatted && formatted.match(/^(.+?)×10(.+)$/)
  if (m) {
    return { mantissa: m[1], exponent: fromSuperscript(m[2]) }
  }
  return { mantissa: formatted, exponent: null }
})
</script>

<style scoped>
.sci-notation {
  display: inline;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.sci-notation sup {
  font-size: 0.72em;
  vertical-align: super;
  line-height: 0;
}

.sci-notation .times {
  margin: 0 0.1em;
}

.sci-notation .unit {
  margin-left: 0.25em;
  color: rgba(0, 0, 0, 0.45);
  font-size: 0.9em;
}

.size-small {
  font-size: 12px;
}

.size-medium {
  font-size: 14px;
}

.size-large {
  font-size: 18px;
}
</style>
