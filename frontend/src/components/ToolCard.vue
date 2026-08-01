<template>
  <div class="tool-card" :class="{ expanded }">
    <div
      class="tool-header"
      role="button"
      tabindex="0"
      :aria-expanded="expanded"
      aria-controls="tool-body"
      :aria-label="`展开/折叠工具 ${tool.name}`"
      @click="toggle"
      @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle"
    >
      <div class="tool-info">
        <div class="tool-name-row">
          <span class="tool-name">{{ tool.name }}</span>
          <a-tag v-if="tool.source" :color="tool.source === 'scp' ? 'purple' : 'blue'" class="tool-badge">
            {{ tool.source === 'scp' ? 'SCP' : '本地' }}
          </a-tag>
          <a-tag v-if="tool.risk_level" :color="riskColor(tool.risk_level)" class="tool-badge">
            {{ tool.risk_level }} 级
          </a-tag>
          <a-tag v-if="tool.availability" :color="availabilityColor(tool.availability)" class="tool-badge">
            {{ availabilityLabel(tool.availability) }}
          </a-tag>
          <a-tag v-if="testResult" :color="testStateColor" class="tool-badge">
            {{ testStateLabel }}
          </a-tag>
        </div>
        <div class="tool-desc">{{ tool.description }}</div>
      </div>
      <div class="tool-action" aria-hidden="true">
        <DownOutlined :class="{ rotated: expanded }" />
      </div>
    </div>

    <transition name="expand">
      <div v-if="expanded" id="tool-body" class="tool-body">
        <div class="param-list" v-if="paramSchema?.properties && Object.keys(paramSchema.properties).length">
          <div class="param-title">参数</div>
          <div v-for="(schema, key) in paramSchema.properties" :key="key" class="param-item">
            <div class="param-head">
              <span class="param-name">{{ key }}</span>
              <span class="param-type">{{ schema.type }}</span>
              <span v-if="isRequired(key)" class="param-required">必填</span>
            </div>
            <div class="param-desc">{{ schema.description }}</div>
          </div>
        </div>

        <div v-if="tool.input_schema" class="param-list">
          <div class="param-title">输入概要</div>
          <div class="param-desc">{{ tool.input_schema }}</div>
        </div>

        <div class="invoke-section">
          <a-button type="primary" size="small" @click="invoke" :loading="loading">
            <PlayCircleOutlined /> 测试
          </a-button>
        </div>

        <div v-if="testResult && testResult.state !== 'testing'" class="test-summary" :class="testResult.state">
          <span class="test-verdict">{{ testResult.state === 'passed' ? '测试通过' : '测试未通过' }}</span>
          <span v-if="testResult.latencyMs != null" class="test-meta">{{ testResult.latencyMs }}ms</span>
          <span v-if="testResult.message" class="test-meta">{{ testResult.message }}</span>
        </div>

        <div v-if="result !== null" class="result-section">
          <div class="result-title">返回结果</div>
          <pre class="result-json">{{ JSON.stringify(result, null, 2) }}</pre>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { DownOutlined, PlayCircleOutlined } from '@ant-design/icons-vue'
import {
  availabilityColor,
  availabilityLabel,
  testStateColor,
  testStateLabel,
} from '@/constants/toolMeta'

const props = defineProps({
  tool: { type: Object, required: true },
  // 自测结果：{ state: 'testing'|'passed'|'failed', message?, latencyMs? }
  testResult: { type: Object, default: null },
})

const emit = defineEmits(['invoke'])

const expanded = ref(false)
const loading = ref(false)
const result = ref(null)

// 参数 schema 归一化：/tools 返回 list 格式，/mcp/manifest 返回 JSON schema 格式
const paramSchema = computed(() => {
  const p = props.tool.parameters
  if (!p) return null
  if (Array.isArray(p)) {
    if (!p.length) return null
    return {
      properties: Object.fromEntries(p.map((x) => [x.name, { type: x.type, description: x.description }])),
      required: p.filter((x) => x.required).map((x) => x.name),
    }
  }
  if (p.properties) return p
  return null
})

const requiredParams = computed(() => paramSchema.value?.required || [])

function isRequired(key) {
  return requiredParams.value.includes(key)
}

function riskColor(level) {
  const map = { A: 'green', B: 'blue', C: 'orange', D: 'red' }
  return map[level] || 'default'
}

function toggle() {
  expanded.value = !expanded.value
}

async function invoke() {
  loading.value = true
  try {
    // 通过 emit 上报 invoke 事件，由父组件处理实际调用；
    // 父组件可通过 :result prop 传回结果（后续扩展）。
    emit('invoke', props.tool)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.tool-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  padding: 12px 14px;
  box-shadow: var(--shadow-card);
  transition: border-color var(--transition), box-shadow var(--transition);
}

.tool-card:hover {
  border-color: var(--primary-border);
}

.tool-card.expanded {
  border-color: var(--primary-border);
  box-shadow: var(--shadow-hover);
}

.tool-header {
  cursor: pointer;
}

.tool-header:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
  border-radius: var(--radius-md);
}

.tool-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.tool-info {
  flex: 1;
  min-width: 0;
}

.tool-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}

.tool-name-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.tool-badge {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
}

.tool-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 3px;
  line-height: 1.5;
}

.tool-action {
  color: var(--text-muted);
  font-size: 12px;
  transition: transform var(--transition);
  flex-shrink: 0;
  padding: 2px;
}

.tool-action .rotated {
  transform: rotate(180deg);
}

.tool-body {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-light);
}

.param-list {
  margin-bottom: 12px;
}

.param-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.param-item {
  padding: 6px 0;
  border-bottom: 1px solid var(--border-light);
}

.param-item:last-child {
  border-bottom: none;
}

.param-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-name {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
}

.param-type {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--light-bg-hover);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}

.param-required {
  font-size: 11px;
  color: var(--error);
}

.param-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 3px;
  line-height: 1.5;
}

.invoke-section {
  margin-top: 10px;
}

.test-summary {
  margin-top: 8px;
  font-size: 12px;
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.test-summary.passed .test-verdict {
  color: var(--success);
  font-weight: 600;
}

.test-summary.failed .test-verdict {
  color: var(--error);
  font-weight: 600;
}

.test-summary .test-meta {
  color: var(--text-muted);
  word-break: break-all;
}

.result-section {
  margin-top: 12px;
}

.result-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.result-json {
  background: var(--dark-bg-deep);
  color: #a8d8a8;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  font-size: 12px;
  line-height: 1.5;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  overflow-x: auto;
  margin: 0;
  max-height: 280px;
  overflow-y: auto;
}

.expand-enter-active,
.expand-leave-active {
  transition: opacity var(--transition-fast), max-height var(--transition);
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

@media (prefers-reduced-motion: reduce) {
  .expand-enter-active,
  .expand-leave-active {
    transition: none;
  }
}
</style>
