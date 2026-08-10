<template>
  <!-- P1-2：统一 AI 输出元信息条（置信度/假设/证据/人工复核），不可隐藏 -->
  <div class="ai-output-meta" :class="{ compact }">
    <div class="meta-line">
      <a-tooltip :title="`置信度：${confidencePct}%（${confidenceLevelText}）`">
        <span class="conf-wrap">
          <span class="conf-label">置信度</span>
          <a-progress
            :percent="confidencePct"
            :stroke-color="confidenceColor"
            :show-info="false"
            :stroke-width="6"
            class="conf-bar"
          />
          <a-tag :color="confidenceColor" class="conf-tag">{{ confidencePct }}%</a-tag>
        </span>
      </a-tooltip>
      <a-tag v-if="agentName" color="orange" size="small">{{ agentName }}</a-tag>
      <a-tag v-if="model" size="small">{{ model }}</a-tag>
      <a-tag v-if="strategy" size="small">{{ strategy }}</a-tag>
      <a-tooltip v-if="humanReviewRequired" title="该 AI 输出置信度较低或缺少外部验证，请人工复核后再用于实验决策">
        <a-tag color="red" size="small" class="review-tag">
          <ExclamationCircleOutlined /> 需人工复核
        </a-tag>
      </a-tooltip>
      <a
        v-if="hasDetail"
        class="detail-toggle"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起依据' : '查看依据' }}
        <DownOutlined v-if="!expanded" />
        <UpOutlined v-else />
      </a>
    </div>
    <div v-if="expanded && hasDetail" class="meta-detail">
      <div v-if="assumptions?.length" class="detail-block">
        <div class="detail-title">关键假设</div>
        <ul class="detail-list">
          <li v-for="(a, i) in assumptions" :key="i">{{ a }}</li>
        </ul>
      </div>
      <div v-if="normalizedEvidence.length" class="detail-block">
        <div class="detail-title">证据来源</div>
        <div class="evidence-list">
          <span v-for="(e, i) in normalizedEvidence" :key="i" class="evidence-item">
            <component :is="evidenceIcon(e.type)" class="evidence-icon" />
            <a-tag v-if="e.url" size="small" class="evidence-tag">
              <a :href="e.url" target="_blank" rel="noopener noreferrer">{{ e.title }}</a>
            </a-tag>
            <a-tag v-else size="small" class="evidence-tag">{{ e.title }}</a-tag>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  DownOutlined,
  UpOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  ExperimentOutlined,
  NodeIndexOutlined,
  DatabaseOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'

// P1-2 统一 AI 输出元信息组件。
// 依据评测报告：高置信度（≥0.8）绿、中（0.5–0.8）橙、低（<0.5）红。
const props = defineProps({
  confidence: { type: Number, default: null },
  agentName: { type: String, default: '' },
  model: { type: String, default: '' },
  strategy: { type: String, default: '' },
  assumptions: { type: Array, default: () => [] },
  evidenceSources: { type: Array, default: () => [] },
  humanReviewRequired: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const expanded = ref(false)

const confidencePct = computed(() =>
  props.confidence == null ? null : Math.round(props.confidence * 100)
)

const confidenceColor = computed(() => {
  const c = props.confidence
  if (c == null) return 'default'
  if (c >= 0.8) return 'green'
  if (c >= 0.5) return 'orange'
  return 'red'
})

const confidenceLevelText = computed(() => {
  const c = props.confidence
  if (c == null) return '未知'
  if (c >= 0.8) return '高'
  if (c >= 0.5) return '中'
  return '低'
})

const hasDetail = computed(
  () => (props.assumptions?.length || 0) > 0 || (props.evidenceSources?.length || 0) > 0
)

// T-030：evidence_sources 结构化引用 {type, id, title, url}。
// 向后兼容纯字符串（旧数据 / agent.py 字符串数组）→ 视为 unknown 类型。
const EVIDENCE_ICONS = {
  literature: FileTextOutlined,
  experiment: ExperimentOutlined,
  kg_node: NodeIndexOutlined,
  database: DatabaseOutlined,
  tool_output: ToolOutlined,
}

const normalizedEvidence = computed(() => {
  const list = props.evidenceSources || []
  const out = []
  for (const e of list) {
    if (typeof e === 'string') {
      if (e.trim()) out.push({ type: 'unknown', id: '', title: e, url: '' })
    } else if (e && typeof e === 'object') {
      const title = String(e.title || '').trim()
      if (title) {
        out.push({
          type: String(e.type || 'unknown').trim() || 'unknown',
          id: String(e.id || '').trim(),
          title,
          url: String(e.url || '').trim(),
        })
      }
    }
  }
  return out
})

const evidenceIcon = (type) => EVIDENCE_ICONS[type] || FileTextOutlined
</script>

<style scoped>
.ai-output-meta {
  border: 1px solid var(--primary-border);
  border-left: none;
  border-radius: 6px;
  padding: 6px 10px;
  background: var(--primary-bg);
  font-size: 12px;
}
.ai-output-meta.compact {
  padding: 4px 8px;
}
.meta-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.conf-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.conf-label {
  color: var(--text-muted);
  white-space: nowrap;
}
.conf-bar {
  width: 72px;
  margin: 0;
}
.conf-tag {
  margin-inline-end: 0;
}
.review-tag {
  margin-inline-end: 0;
}
.detail-toggle {
  margin-left: auto;
  font-size: 12px;
  white-space: nowrap;
}
.meta-detail {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--border-light);
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}
.detail-block {
  min-width: 200px;
  flex: 1;
}
.detail-title {
  color: var(--text-muted);
  margin-bottom: 2px;
}
.detail-list {
  margin: 0;
  padding-left: 16px;
  color: var(--text-secondary);
  line-height: 1.7;
}
.evidence-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}
.evidence-item {
  display: inline-flex;
  align-items: center;
}
.evidence-icon {
  margin-right: 4px;
  color: var(--text-muted);
  font-size: 12px;
}
.evidence-tag {
  margin-inline-end: 0;
}
.evidence-tag a {
  color: inherit;
  text-decoration: none;
}
.evidence-tag a:hover {
  text-decoration: underline;
}
</style>
