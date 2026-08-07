<template>
  <div class="evidence-card" :class="[`level-${evidence.level}`]" @click="handleClick">
    <div class="evidence-header">
      <span class="evidence-method">{{ evidence.method || '未指定方法' }}</span>
      <span class="evidence-level-tag">{{ levelLabel }}</span>
    </div>
    <div class="evidence-claim">{{ evidence.claim }}</div>
    <div class="evidence-value" v-if="hasValue">
      <template v-if="typeof evidence.value === 'object'">
        <pre>{{ JSON.stringify(evidence.value, null, 2) }}</pre>
      </template>
      <template v-else>
        <strong class="evidence-num">{{ evidence.value }}</strong>
        <span class="evidence-unit" v-if="evidence.unit"> {{ evidence.unit }}</span>
      </template>
    </div>
    <div class="evidence-footer">
      <span class="evidence-source" :title="sourceTitle">
        <span class="evidence-source-type" :class="`tier-${tierKey}`">{{ sourceTypeLabel }}</span>
        <span class="evidence-source-sep" v-if="provider">/</span>
        <span class="evidence-source-svc" v-if="provider">{{ provider }}</span>
        <span class="evidence-fallback" v-if="fallbackReason" :title="fallbackReason">保险</span>
      </span>
      <span class="evidence-confidence">
        <span class="confidence-bar">
          <span class="confidence-fill" :style="{ width: `${confidencePct}%` }" />
        </span>
        <span class="confidence-text">{{ confidencePct }}%</span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  evidence: { type: Object, required: true }
})

const emit = defineEmits(['click'])

const levelLabel = computed(() => {
  const map = { high: '高置信', medium: '中置信', low: '低置信', assistive: '辅助' }
  return map[props.evidence.level] || props.evidence.level
})

const sourceTypeLabel = computed(() => {
  const map = {
    real_engine: '真实引擎',
    builtin_library: '内置库',
    llm_generated: 'LLM'
  }
  // 兼容旧字段：source_type 可能直接为 {tier}:{provider} 或旧取值
  const raw = props.evidence.source_type || ''
  const tier = raw.includes(':') ? raw.split(':')[0] : raw
  return map[tier] || tier || '未知来源'
})

// 来源层级 key（用于颜色编码）
const tierKey = computed(() => {
  const raw = props.evidence.source_type || ''
  const tier = raw.includes(':') ? raw.split(':')[0] : raw
  return ['real_engine', 'builtin_library', 'llm_generated'].includes(tier) ? tier : 'unknown'
})

// 从 source_service（{tier}:{provider}）或 source_type 中解析具体引擎名
const provider = computed(() => {
  const svc = props.evidence.source_service || ''
  if (svc) return svc.includes(':') ? svc.split(':')[1] : svc
  const raw = props.evidence.source_type || ''
  if (raw.includes(':')) return raw.split(':')[1]
  return props.evidence.metadata?.provider || ''
})

// 兜底原因（metadata.fallback_reason）
const fallbackReason = computed(() => props.evidence.metadata?.fallback_reason || '')

const sourceTitle = computed(() => {
  const tier = sourceTypeLabel.value
  const prov = provider.value
  const fb = fallbackReason.value
  return `来源层级：${tier}${prov ? `（${prov}）` : ''}${fb ? `；${fb}` : ''}`
})

const hasValue = computed(() => {
  const v = props.evidence.value
  return v !== null && v !== undefined && v !== ''
})

const confidencePct = computed(() => {
  const c = Number(props.evidence.confidence)
  if (Number.isNaN(c)) return 0
  return Math.round(c * 100)
})

function handleClick () {
  emit('click', props.evidence)
}
</script>

<style scoped>
.evidence-card {
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--bg-card);
}
.evidence-card:hover {
  box-shadow: var(--shadow-hover);
}
/* EvidenceLevel 颜色编码：绿/橙/红/蓝 对应 high/medium/low/assistive */
.evidence-card.level-high { border-left-color: var(--success); }
.evidence-card.level-medium { border-left-color: var(--warning); }
.evidence-card.level-low { border-left-color: var(--error); }
.evidence-card.level-assistive { border-left-color: var(--info); }

.evidence-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs);
}
.evidence-method {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}
.evidence-level-tag {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  line-height: 1.5;
}
.level-high .evidence-level-tag { color: var(--success); background: var(--success-bg); }
.level-medium .evidence-level-tag { color: var(--warning); background: var(--warning-bg); }
.level-low .evidence-level-tag { color: var(--error); background: var(--error-bg); }
.level-assistive .evidence-level-tag { color: var(--info); background: var(--info-bg); }

.evidence-claim {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
  line-height: 1.4;
}
.evidence-value {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
}
.evidence-num {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--primary);
}
.evidence-unit {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  margin-left: 2px;
}
.evidence-value pre {
  font-size: var(--font-size-xs);
  background: var(--light-bg);
  padding: var(--space-sm);
  border-radius: var(--radius-sm);
  max-height: 120px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--border-light);
}
.evidence-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}
.evidence-source {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.evidence-source-type {
  font-weight: var(--font-weight-semibold);
}
.evidence-source-type.tier-real_engine { color: var(--success); }
.evidence-source-type.tier-builtin_library { color: var(--warning); }
.evidence-source-type.tier-llm_generated { color: var(--error); }
.evidence-source-type.tier-unknown { color: var(--text-secondary); }
.evidence-fallback {
  font-size: 11px;
  color: var(--warning);
  border: 1px solid var(--warning);
  border-radius: var(--radius-sm);
  padding: 0 4px;
  line-height: 1.4;
  cursor: help;
  flex-shrink: 0;
}
.evidence-source-sep {
  color: var(--text-muted);
}
.evidence-source-svc {
  color: var(--text-secondary);
  font-family: 'SFMono-Regular', Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-confidence {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  flex-shrink: 0;
}
.confidence-bar {
  display: inline-block;
  width: 48px;
  height: 4px;
  background: var(--border);
  border-radius: var(--radius-pill);
  overflow: hidden;
}
.confidence-fill {
  display: block;
  height: 100%;
  background: var(--primary);
  border-radius: var(--radius-pill);
  transition: width var(--transition);
}
.confidence-text {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}
</style>
