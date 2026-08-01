<template>
  <span class="chemical-formula" :class="`size-${size}`">
    <template v-for="(token, i) in tokens" :key="i">
      <sub v-if="token.type === 'sub'">{{ token.value }}</sub>
      <sup v-else-if="token.type === 'sup'">{{ token.value }}</sup>
      <span v-else>{{ token.value }}</span>
    </template>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  formula: { type: String, default: '' },
  size: {
    type: String,
    default: 'medium',
    validator: (v) => ['small', 'medium', 'large'].includes(v),
  },
})

const tokens = computed(() => parseFormula(props.formula))

/**
 * 解析化学式字符串为 token 序列。
 * 支持：元素符号（大写+可选小写）、数字下标、嵌套括号 ()[]{}、
 * 水合物点号 ·/.、电荷上标 ^2+ ^3-。
 * 未识别字符原样展示。
 */
function parseFormula(formula) {
  if (!formula || typeof formula !== 'string') return []
  const tokens = []
  const s = formula
  const len = s.length
  let i = 0

  while (i < len) {
    const ch = s[i]

    // 电荷标记 ^2+ ^3- 等 → 上标
    if (ch === '^') {
      i++
      let charge = ''
      while (i < len && /[0-9]/.test(s[i])) {
        charge += s[i]
        i++
      }
      if (i < len && (s[i] === '+' || s[i] === '-')) {
        charge += s[i]
        i++
      }
      if (charge) tokens.push({ type: 'sup', value: charge })
      continue
    }

    // 左括号原样输出
    if (ch === '(' || ch === '[' || ch === '{') {
      tokens.push({ type: 'text', value: ch })
      i++
      continue
    }

    // 右括号：输出括号 + 紧跟的数字下标
    if (ch === ')' || ch === ']' || ch === '}') {
      tokens.push({ type: 'text', value: ch })
      i++
      let num = ''
      while (i < len && /[0-9]/.test(s[i])) {
        num += s[i]
        i++
      }
      if (num) tokens.push({ type: 'sub', value: num })
      continue
    }

    // 元素符号：大写字母 + 可选小写字母
    if (/[A-Z]/.test(ch)) {
      let element = ch
      i++
      if (i < len && /[a-z]/.test(s[i])) {
        element += s[i]
        i++
      }
      tokens.push({ type: 'text', value: element })
      // 元素后的数字 → 下标
      let num = ''
      while (i < len && /[0-9]/.test(s[i])) {
        num += s[i]
        i++
      }
      if (num) tokens.push({ type: 'sub', value: num })
      continue
    }

    // 其他字符（含 · . - 数字开头、Unicode 下标等）原样展示
    tokens.push({ type: 'text', value: ch })
    i++
  }

  return tokens
}
</script>

<style scoped>
.chemical-formula {
  display: inline;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.chemical-formula sub {
  font-size: 0.72em;
  vertical-align: sub;
  line-height: 0;
}

.chemical-formula sup {
  font-size: 0.72em;
  vertical-align: super;
  line-height: 0;
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
