<template>
  <div class="execution-result-panel">
    <div class="result-header">
      <div class="result-title">
        <CheckCircleOutlined class="success-icon" />
        <span>执行完成 · 共 {{ completedCount }}/{{ totalCount }} 步成功</span>
        <a-tag v-if="warningCount > 0" color="orange" size="small">{{ warningCount }} 步警告</a-tag>
      </div>
      <a-space>
        <a-button size="small" @click="$emit('viewRuns')">
          <HistoryOutlined /> 查看历史
        </a-button>
        <a-button type="primary" size="small" @click="$emit('runAgain')">
          <PlayCircleOutlined /> 再次运行
        </a-button>
      </a-space>
    </div>

    <div v-if="toolResults.length === 0" class="result-empty" role="status" aria-live="polite">
      暂无工具执行结果
    </div>
    <div v-else class="result-cards" role="list" aria-label="工具执行结果">
      <a-card
        v-for="item in toolResults"
        :key="item.step_id"
        size="small"
        :bordered="false"
        class="result-card"
        role="listitem"
      >
        <div class="card-top">
          <a-avatar :size="28" class="agent-avatar">
            <component :is="avatarIcon(item.avatar)" aria-hidden="true" />
          </a-avatar>
          <div class="agent-meta">
            <div class="agent-name">{{ item.agent_name }}</div>
            <div class="step-task">{{ item.task }}</div>
          </div>
          <a-tag size="small" :color="toolColor(item.tool)" class="tool-tag">
            {{ toolLabel(item.tool) }}
          </a-tag>
          <a-tag v-if="item.status === 'warning'" color="orange" size="small" class="tool-tag">警告</a-tag>
          <a-tag v-if="item.status === 'error'" color="red" size="small" class="tool-tag">失败</a-tag>
        </div>

        <div class="card-body">
          <template v-if="item.tool === 'generate_crystal_candidates' || item.tool === 'generate_polymer_candidates'">
            <div class="metric-row">
              <span class="metric-value">{{ item.result?.count || 0 }}</span>
              <span class="metric-label">个候选材料</span>
            </div>
            <div v-if="candidatesFor(item).length" class="candidate-list">
              <MoleculeView
                v-for="(c, cIdx) in candidatesFor(item)"
                :key="(c.smiles || c.formula || c.name || '') + '-' + cIdx"
                :smiles="c.smiles || ''"
                :size="80"
                class="candidate-mini"
              />
            </div>
          </template>

          <template v-else-if="item.tool === 'predict_crystal_properties' || item.tool === 'predict_polymer_properties'">
            <div class="metric-row">
              <span class="metric-value"><ScientificNotation :value="item.result?.predicted_value ?? item.result?.value" /></span>
              <span class="metric-label">{{ item.result?.property_name || '性质' }}</span>
            </div>
            <div v-if="item.result?.unit" class="metric-extra">单位：{{ item.result.unit }}</div>
          </template>

          <template v-else-if="item.tool === 'verify_dft'">
            <div class="metric-row">
              <span class="metric-value"><ScientificNotation :value="item.result?.value ?? item.result?.total_energy" /></span>
              <span class="metric-label">{{ item.result?.property_name || 'total_energy' }}</span>
            </div>
            <div class="metric-extra">
              <a-tag size="small" :color="item.result?.converged ? 'green' : 'orange'">
                {{ item.result?.converged ? '已收敛' : '未收敛' }}
              </a-tag>
            </div>
          </template>

          <template v-else-if="item.tool === 'check_synthesis_feasibility'">
            <div class="metric-row">
              <span class="metric-value">{{ formatScore(item.result?.feasibility_score) }}</span>
              <span class="metric-label">合成可行性</span>
            </div>
            <a-progress
              :percent="scorePercent(item.result?.feasibility_score)"
              size="small"
              :stroke-color="scoreColor(item.result?.feasibility_score)"
              :show-info="false"
            />
          </template>

          <template v-else-if="item.tool === 'design_formula'">
            <div class="metric-row">
              <span class="metric-label">配方状态</span>
              <a-tag size="small" :color="item.result?.is_passed ? 'green' : 'red'">
                {{ item.result?.is_passed ? '通过' : '未通过' }}
              </a-tag>
            </div>
            <div v-if="item.result?.estimated_unit_cost" class="metric-extra">
              估算成本：¥{{ Number(item.result.estimated_unit_cost).toFixed(2) }}/{{ massUnit }}
            </div>
          </template>

          <template v-else>
            <div class="metric-row">
              <span class="metric-value">{{ item.summary }}</span>
            </div>
          </template>
        </div>

        <div class="card-actions">
          <a-button size="small" type="link" @click="viewDetail(item)">查看详情</a-button>
          <a-button
            v-if="canRerun(item)"
            size="small"
            type="link"
            @click="$emit('rerunTool', item)"
          >
            重新执行
          </a-button>
        </div>
      </a-card>
    </div>

    <a-modal
      v-model:open="detailVisible"
      title="步骤执行详情"
      width="560px"
      :footer="null"
    >
      <a-descriptions :column="1" bordered size="small">
        <a-descriptions-item label="Agent">{{ detailItem?.agent_name }}</a-descriptions-item>
        <a-descriptions-item label="任务">{{ detailItem?.task }}</a-descriptions-item>
        <a-descriptions-item label="工具">{{ detailItem?.tool }}</a-descriptions-item>
        <a-descriptions-item label="摘要">{{ detailItem?.summary }}</a-descriptions-item>
      </a-descriptions>
      <div class="detail-data-title">原始结果</div>
      <pre class="detail-json">{{ JSON.stringify(detailItem?.result, null, 2) }}</pre>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import {
  CheckCircleOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons-vue'
import MoleculeView from './MoleculeView.vue'
import { useUnitSymbols } from '@/utils/mdmDict'
import { resolveAgentIcon } from '@/utils/agentAvatar'

// MDM 单位符号（mass 维度，用于成本单位）
const { load: loadUnitSymbols, get: getUnitSymbol } = useUnitSymbols()
const massUnit = computed(() => getUnitSymbol('mass'))
onMounted(() => { loadUnitSymbols() })

const props = defineProps({
  events: { type: Array, default: () => [] },
  agents: { type: Array, default: () => [] },
  totalCount: { type: Number, default: 0 },
  completedCount: { type: Number, default: 0 },
  warningCount: { type: Number, default: 0 },
})

const emit = defineEmits(['viewRuns', 'runAgain', 'rerunTool'])

const TOOL_LABEL = {
  generate_crystal_candidates: '候选生成',
  generate_polymer_candidates: '候选生成',
  predict_crystal_properties: '性质预测',
  predict_polymer_properties: '性质预测',
  verify_dft: 'DFT 验证',
  check_synthesis_feasibility: '合成评估',
  route_material: '材料路由',
  get_experiment_results: '实验查询',
  design_formula: '配方设计',
}

const TOOL_COLOR = {
  generate_crystal_candidates: 'blue',
  generate_polymer_candidates: 'blue',
  predict_crystal_properties: 'green',
  predict_polymer_properties: 'green',
  verify_dft: 'purple',
  check_synthesis_feasibility: 'orange',
  route_material: 'cyan',
  get_experiment_results: 'geekblue',
  design_formula: 'magenta',
}

const agentMap = computed(() => {
  const m = {}
  props.agents.forEach((a) => { m[a.id] = a })
  return m
})

const toolResults = computed(() => {
  const stepStatusMap = {}
  props.events
    .filter((e) => e.event_type === 'step_complete' && e.step_id)
    .forEach((e) => { stepStatusMap[e.step_id] = e.status || 'success' })
  return props.events
    .filter((e) => e.event_type === 'tool_result' && e.data?.tool)
    .map((e) => {
      const agent = agentMap.value[e.agent_id] || {}
      return {
        step_id: e.step_id,
        agent_id: e.agent_id,
        agent_name: e.agent_name || agent.name || e.agent_id,
        avatar: agent.avatar || '',
        task: e.task || agent.expertise?.[0] || e.data.tool,
        tool: e.data.tool,
        result: e.data.result || {},
        summary: e.content || '',
        status: stepStatusMap[e.step_id] || 'success',
      }
    })
})

function avatarIcon(avatar) {
  return resolveAgentIcon(avatar)
}

const RERUNNABLE_TOOLS = new Set([
  'generate_crystal_candidates', 'generate_polymer_candidates',
  'predict_crystal_properties', 'predict_polymer_properties',
  'verify_dft', 'check_synthesis_feasibility',
])

const detailVisible = ref(false)
const detailItem = ref(null)

function toolLabel(tool) {
  return TOOL_LABEL[tool] || tool
}

function toolColor(tool) {
  return TOOL_COLOR[tool] || 'default'
}

function formatScore(s) {
  if (s === undefined || s === null) return '-'
  const n = Number(s)
  if (isNaN(n)) return String(s)
  // 约定 score 范围 [0, 1]，展示为百分比
  if (n >= 0 && n <= 1) return `${(n * 100).toFixed(1)}%`
  // 兼容已经是 0-100 的输入
  return `${n.toFixed(1)}%`
}

// 生成 a-progress 可用的合法 percent（0-100 整数），避免 NaN
function scorePercent(s) {
  const n = Number(s)
  if (isNaN(n)) return 0
  // 范围 [0, 1]
  if (n >= 0 && n <= 1) return Math.round(n * 100)
  // 兼容 0-100
  if (n > 1 && n <= 100) return Math.round(n)
  // 越界值钳制
  return n > 100 ? 100 : 0
}

function scoreColor(s) {
  const n = Number(s)
  if (isNaN(n)) return '#ef4444'
  // 统一转换为 0-1 范围比较
  const norm = n > 1 ? n / 100 : n
  if (norm >= 0.8) return '#10b981'
  if (norm >= 0.5) return '#f59e0b'
  return '#ef4444'
}

function candidatesFor(item) {
  const result = item.result || {}
  if (Array.isArray(result.candidates)) return result.candidates.slice(0, 6)
  return []
}

function canRerun(item) {
  return RERUNNABLE_TOOLS.has(item.tool)
}

function viewDetail(item) {
  detailItem.value = item
  detailVisible.value = true
}
</script>

<style scoped>
.execution-result-panel {
  margin-top: 16px;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #e0e4ec;
}

.success-icon {
  color: #10b981;
  font-size: 18px;
}

.result-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.result-card {
  background: var(--dark-bg-card);
  border: 1px solid var(--dark-border);
  border-radius: var(--radius-lg);
}

.result-card :deep(.ant-card-body) {
  padding: 12px;
}

.card-top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}

.agent-avatar {
  flex-shrink: 0;
  background: var(--dark-bg-lighter);
}

.agent-meta {
  flex: 1;
  min-width: 0;
}

.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: #e0e4ec;
}

.step-task {
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-tag {
  flex-shrink: 0;
}

.card-body {
  padding: 10px;
  background: var(--dark-bg);
  border-radius: var(--radius-md);
  margin-bottom: 10px;
}

.metric-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  color: #e0e4ec;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}

.result-empty {
  color: var(--text-muted);
  text-align: center;
  padding: 30px 0;
  font-size: 14px;
}

.metric-label {
  font-size: 12px;
  color: var(--text-muted);
}

.metric-extra {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.candidate-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.candidate-mini {
  border-radius: 6px;
  background: var(--dark-bg-card);
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.detail-data-title {
  margin-top: 12px;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #e0e4ec;
}

.detail-json {
  max-height: 300px;
  overflow: auto;
  background: var(--dark-bg);
  color: var(--text-muted);
  padding: 10px;
  border-radius: var(--radius-md);
  font-size: 11px;
  line-height: 1.5;
}
</style>
