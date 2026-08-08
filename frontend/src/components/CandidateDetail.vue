<template>
  <div class="candidate-detail">
    <!-- 详情头部 -->
    <div class="detail-header">
      <div class="header-left">
        <div class="header-title">{{ title }}</div>
        <div class="header-subtitle">{{ subtitle }}</div>
      </div>
      <div class="header-tags">
        <a-button
          type="primary"
          size="small"
          @click="onCreateExperiment"
        >
          <template #icon><ExperimentOutlined /></template>
          创建实验任务
        </a-button>
        <a-tag v-if="candidate.source" :color="getSourceBadge(candidate).color">{{ getSourceBadge(candidate).label }}</a-tag>
        <a-tag v-if="candidate.risk_level" :color="riskColor(candidate.risk_level)">
          {{ riskLabel(candidate.risk_level) }}
        </a-tag>
        <a-tag v-if="candidate.committee_verdict" :color="verdictColor(candidate.committee_verdict)">
          {{ verdictLabel(candidate.committee_verdict) }}
        </a-tag>
      </div>
    </div>

    <!-- P1-2：AI 生成候选的可信度元信息（置信度/假设/证据/复核），统一展示不可隐藏 -->
    <AIOutputMeta
      v-if="candidateAIConfidence != null"
      :confidence="candidateAIConfidence"
      :agent-name="candidate.source === 'agent_creative' ? '首席材料学家' : ''"
      :assumptions="candidate.key_assumptions || []"
      :evidence-sources="candidate.evidence_sources || []"
      :human-review-required="!!candidate.human_review_required"
      style="margin-bottom: 8px"
    />

    <!-- Tab 区 -->
    <a-tabs v-model:activeKey="activeTab" class="detail-tabs" size="small">
      <!-- Tab 1: 结构可视化 -->
      <a-tab-pane key="structure" tab="结构可视化">
        <div class="tab-pane-content">
          <div class="structure-stage">
            <StructureView
              :smiles="smiles"
              :formula="candidate.formula || ''"
              :space-group="candidate.space_group || ''"
              :structure-type="candidate.structure_type || ''"
              :kind="structureKind"
              :size="320"
            />
          </div>
          <a-descriptions
            class="structure-meta"
            size="small"
            :column="2"
            bordered
            :colon="true"
          >
            <a-descriptions-item label="化学式">
              <ChemicalFormula v-if="candidate.formula" :formula="candidate.formula" size="small" />
              <span v-else>—</span>
            </a-descriptions-item>
            <a-descriptions-item label="SMILES">
              {{ smiles || '—' }}
            </a-descriptions-item>
            <a-descriptions-item label="空间群">
              {{ candidate.space_group || '—' }}
            </a-descriptions-item>
            <a-descriptions-item label="结构类型">
              {{ candidate.structure_type || '—' }}
            </a-descriptions-item>
            <a-descriptions-item v-if="candidate.material_id" label="材料 ID">
              {{ candidate.material_id }}
            </a-descriptions-item>
            <a-descriptions-item v-if="candidate.elements" label="元素组成">
              {{ formatElements(candidate.elements) }}
            </a-descriptions-item>
          </a-descriptions>
        </div>
      </a-tab-pane>

      <!-- Tab 2: 性质预测 -->
      <a-tab-pane key="properties" tab="性质预测">
        <div class="tab-pane-content">
          <div class="tab-toolbar">
            <span class="tab-hint">基于已预测属性 + 可选跨尺度建模补全</span>
            <a-button
              size="small"
              type="primary"
              @click="openCrossScaleDrawer"
            >
              <template #icon><ThunderboltOutlined /></template>
              跨尺度预测
            </a-button>
          </div>
          <!-- 审查意见0726：下沉模型版本与置信度信息，避免跳到管理后台 -->
          <div v-if="modelMeta" class="model-meta-bar">
            <a-tag color="blue">
              <ApiOutlined /> {{ modelMeta.model_name || '未知模型' }}
            </a-tag>
            <a-tag v-if="modelMeta.model_version" color="cyan">v{{ modelMeta.model_version }}</a-tag>
            <a-tooltip v-if="modelMeta.confidence != null" :title="`置信度：${(modelMeta.confidence * 100).toFixed(1)}%`">
              <a-tag :color="confidenceColor(modelMeta.confidence)">
                置信度 {{ (modelMeta.confidence * 100).toFixed(0) }}%
              </a-tag>
            </a-tooltip>
            <a-tag v-if="modelMeta.uncertainty" color="orange">
              不确定度 ±{{ (modelMeta.uncertainty * 100).toFixed(1) }}%
            </a-tag>
            <a-tooltip title="模型版本与置信度信息来自能力契约，可在管理后台 → 能力契约查看详情">
              <span class="meta-hint">数据来源：能力契约</span>
            </a-tooltip>
          </div>
          <a-table
            v-if="propRows.length > 0"
            :row-key="(r) => r.key"
            :columns="propColumns"
            :data-source="propRows"
            :pagination="false"
            size="small"
            class="prop-table"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'value'">
                <span class="prop-value" :class="{ 'prop-predicted': record.predicted }">
                  {{ record.value }}
                  <a-tag v-if="record.predicted" color="orange" size="small">预测</a-tag>
                  <a-tag v-if="record.evidence" color="blue" size="small">{{ record.evidence }}</a-tag>
                  <a-tooltip v-if="record.confidence != null" :title="`置信度 ${(record.confidence * 100).toFixed(1)}%`">
                    <a-tag :color="confidenceColor(record.confidence)" size="small">
                      {{ (record.confidence * 100).toFixed(0) }}%
                    </a-tag>
                  </a-tooltip>
                </span>
              </template>
            </template>
          </a-table>
          <div v-else-if="!crossScaleResult" class="empty-inline">
            <EmptyState
              type="data"
              description="该候选材料尚无属性数据，点击上方按钮触发跨尺度预测"
            />
          </div>

          <!-- 跨尺度预测结果 -->
          <div v-if="crossScaleResult" class="cross-scale-result">
            <div class="cs-result-title">
              <ThunderboltOutlined /> 跨尺度预测结果
              <a-tag v-if="crossScaleResult.executed_by" color="blue" size="small">
                agent: {{ crossScaleResult.executed_by }}
              </a-tag>
            </div>

            <!-- 分子尺度 -->
            <div v-if="crossScalePropRows.length" class="cs-result-section">
              <div class="cs-result-subtitle">分子尺度</div>
              <a-table
                :row-key="(r) => r.key"
                :columns="propColumns"
                :data-source="crossScalePropRows"
                :pagination="false"
                size="small"
                class="prop-table"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'value'">
                    <span class="prop-value prop-predicted">
                      {{ record.value }}
                      <a-tag color="orange" size="small">预测</a-tag>
                      <a-tooltip v-if="record.confidence != null" :title="`置信度 ${(record.confidence * 100).toFixed(1)}%`">
                        <a-tag :color="confidenceColor(record.confidence)" size="small">
                          {{ (record.confidence * 100).toFixed(0) }}%
                        </a-tag>
                      </a-tooltip>
                    </span>
                  </template>
                </template>
              </a-table>
            </div>

            <!-- 反应尺度 -->
            <div v-if="crossScaleResult.reaction" class="cs-result-section">
              <div class="cs-result-subtitle">反应尺度</div>
              <a-descriptions size="small" :column="2" bordered>
                <a-descriptions-item label="可行性评分">
                  {{ ((crossScaleResult.reaction.pathway?.feasibility_score ?? 0) * 100).toFixed(0) }}%
                </a-descriptions-item>
                <a-descriptions-item label="置信度">
                  {{ ((crossScaleResult.reaction.pathway?.confidence ?? 0) * 100).toFixed(0) }}%
                </a-descriptions-item>
                <a-descriptions-item label="合成步数">
                  {{ crossScaleResult.reaction.pathway?.num_steps ?? '—' }}
                </a-descriptions-item>
                <a-descriptions-item label="总产率">
                  {{ ((crossScaleResult.reaction.yield ?? 0) * 100).toFixed(0) }}%
                </a-descriptions-item>
              </a-descriptions>
            </div>

            <!-- 连续介质尺度 -->
            <div v-if="crossScaleResult.continuum" class="cs-result-section">
              <div class="cs-result-subtitle">连续介质尺度</div>
              <a-descriptions size="small" :column="2" bordered>
                <a-descriptions-item label="工作电压">
                  {{ crossScaleResult.continuum.electrochemical?.operating_voltage?.toFixed(2) ?? '—' }} {{ voltageUnit }}
                </a-descriptions-item>
                <a-descriptions-item label="理论容量">
                  {{ crossScaleResult.continuum.electrochemical?.theoretical_capacity?.toFixed(2) ?? '—' }} {{ capUnit }}
                </a-descriptions-item>
                <a-descriptions-item label="能量密度">
                  {{ crossScaleResult.continuum.electrochemical?.energy_density?.toFixed(2) ?? '—' }} {{ energyDensityUnit }}
                </a-descriptions-item>
                <a-descriptions-item label="功率密度">
                  {{ crossScaleResult.continuum.electrochemical?.power_density?.toFixed(2) ?? '—' }} {{ powerDensityUnit }}
                </a-descriptions-item>
                <a-descriptions-item label="热导率">
                  {{ crossScaleResult.continuum.thermal?.thermal_conductivity?.toFixed(2) ?? '—' }} {{ thermalConductivityUnit }}
                </a-descriptions-item>
                <a-descriptions-item label="最大温升">
                  {{ crossScaleResult.continuum.thermal?.max_temperature_rise?.toFixed(2) ?? '—' }} {{ temperatureDeltaUnit }}
                </a-descriptions-item>
                <a-descriptions-item label="弹性模量">
                  {{ crossScaleResult.continuum.mechanical?.elastic_modulus?.toFixed(2) ?? '—' }} {{ modulusUnit }}
                </a-descriptions-item>
                <a-descriptions-item label="密度">
                  {{ crossScaleResult.continuum.mechanical?.density?.toFixed(2) ?? '—' }} {{ densityUnit }}
                </a-descriptions-item>
              </a-descriptions>
            </div>

            <!-- 耦合分析 -->
            <div v-if="crossScaleResult.coupled" class="cs-result-section">
              <div class="cs-result-subtitle">耦合分析</div>
              <a-alert
                v-if="crossScaleResult.coupled.summary"
                :message="crossScaleResult.coupled.summary"
                type="info"
                show-icon
              />
              <div v-if="crossScaleResult.coupled.correlations?.length" class="cs-correlations">
                <div
                  v-for="(corr, idx) in crossScaleResult.coupled.correlations"
                  :key="idx"
                  class="cs-correlation-item"
                >
                  <a-tag :color="corr.correlation === 'positive' ? 'green' : 'red'" size="small">
                    {{ corr.correlation === 'positive' ? '正相关' : '负相关' }}
                  </a-tag>
                  <span class="cs-corr-prop">{{ corr.property }}</span>
                  <span class="cs-corr-desc">{{ corr.description }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </a-tab-pane>

      <!-- Tab 3: 合成路径 -->
      <a-tab-pane key="synthesis" tab="合成路径">
        <div class="tab-pane-content">
          <div class="tab-toolbar">
            <span class="tab-hint">
              {{ structureKind === 'crystal' ? '固相合成路径（AI4S大模型）' : '逆合成分析（ASKCOS / AI4S大模型）' }}
            </span>
            <a-button
              size="small"
              type="primary"
              :loading="synthLoading"
              :disabled="synthLoading"
              @click="openSynthDrawer"
            >
              <template #icon><BranchesOutlined /></template>
              生成合成路径
            </a-button>
          </div>
          <!-- P3-B2：持久化最佳可行性摘要（仅展示，不参与评分） -->
          <a-alert
            v-if="synthFeasibility && synthFeasibility.feasibility_score != null"
            type="info"
            show-icon
            style="margin-bottom: 12px"
            :message="`最佳路线可行性：${(Number(synthFeasibility.feasibility_score) * 100).toFixed(1)}%`"
          />
          <a-spin :spinning="synthLoading">
            <div v-if="!synthResult && !synthLoading" class="empty-inline">
              <EmptyState
                type="data"
                description="点击上方按钮生成合成路径"
              />
            </div>
            <div v-else-if="synthLoading && !synthResult" class="synth-loading-hint">
              <a-alert
                message="合成规划进行中"
                description="已提交任务到后台，大模型推理通常需要 1-3 分钟，请耐心等待…"
                type="info"
                show-icon
              />
            </div>
            <div v-else-if="synthResult" class="synth-result">
              <!-- Agent 信息条 -->
              <div v-if="synthResult.agent_info" class="synth-agent-bar">
                <a-tag color="blue">
                  <ApiOutlined /> {{ synthResult.agent_info.name || 'AI4S大模型' }}
                </a-tag>
                <a-tag v-if="synthResult.agent_info.model" color="cyan">
                  {{ synthResult.agent_info.model }}
                </a-tag>
                <a-tag v-if="synthResult.agent_info.role" color="purple" size="small">
                  {{ synthResult.agent_info.role }}
                </a-tag>
                <a-tag v-if="synthResult.engine" color="orange" size="small">
                  引擎: {{ synthResult.engine }}
                </a-tag>
                <a-tag v-if="synthResult.material_type === 'crystal'" color="geekblue" size="small">
                  晶体固相合成
                </a-tag>
              </div>

              <!-- 路线列表 -->
              <div v-if="synthResult.routes?.length" class="synth-routes">
                <div
                  v-for="(route, idx) in synthResult.routes"
                  :key="idx"
                  class="synth-route"
                  :class="{ 'synth-route-selected': selectedRouteId === (route.route_id || 'R' + (idx + 1)) }"
                >
                  <div class="route-header">
                    <a-radio
                      :checked="selectedRouteId === (route.route_id || 'R' + (idx + 1))"
                      @change="onSelectRoute(route, idx)"
                    >
                      <span class="route-num">路线 {{ idx + 1 }}</span>
                    </a-radio>
                    <a-tag v-if="route.overall_score != null" :color="route.overall_score >= 0.7 ? 'green' : 'orange'">
                      可行性 {{ (route.overall_score * 100).toFixed(0) }}%
                    </a-tag>
                    <a-tag v-else-if="route.score != null" :color="route.score >= 0.7 ? 'green' : 'orange'">
                      可行性 {{ (route.score * 100).toFixed(0) }}%
                    </a-tag>
                    <!-- P1-2：路线置信度（高≥0.8 绿 / 中 0.5–0.8 橙 / 低<0.5 红） -->
                    <a-tooltip
                      v-if="route.confidence != null"
                      :title="routeEvidenceTooltip(route)"
                    >
                      <a-tag :color="aiConfidenceColor(route.confidence)" size="small">
                        置信度 {{ (route.confidence * 100).toFixed(0) }}%
                      </a-tag>
                    </a-tooltip>
                    <a-tag
                      v-if="route.confidence != null && route.confidence < 0.5"
                      color="red"
                      size="small"
                    >需人工复核</a-tag>
                    <span v-if="route.steps" class="route-steps">
                      {{ route.steps.length }} 步
                    </span>
                    <a-tag v-if="route.reactants?.length" size="small" color="blue">
                      前驱体: {{ route.reactants.join(' + ') }}
                    </a-tag>
                  </div>
                  <div v-if="route.steps?.length" class="route-steps-list">
                    <div
                      v-for="(step, sidx) in route.steps"
                      :key="sidx"
                      class="route-step"
                    >
                      <span class="step-num">{{ sidx + 1 }}</span>
                      <span class="step-smiles">{{ step.conditions || step.reaction_type || step.reagent || step.smiles || step.product }}</span>
                      <a-tag v-if="step.reaction_type" size="small">{{ step.reaction_type }}</a-tag>
                    </div>
                  </div>
                </div>
              </div>
              <a-alert
                v-else-if="synthResult.message"
                :message="synthResult.message"
                type="info"
                show-icon
              />

              <!-- AI4S 推理过程 -->
              <div v-if="synthResult.reasoning" class="synth-reasoning">
                <div class="synth-reasoning-title">
                  <ThunderboltOutlined /> AI4S 推理过程
                </div>
                <div class="synth-reasoning-body">{{ synthResult.reasoning }}</div>
              </div>
            </div>
          </a-spin>
        </div>
      </a-tab-pane>

      <!-- Tab 4: 工业化验证 -->
      <a-tab-pane key="industrialization" tab="可制造性 / 工业化验证">
        <div class="tab-pane-content">
          <div class="tab-toolbar">
            <span class="tab-hint">合规检查、供应链、成本估算</span>
            <a-button
              size="small"
              type="primary"
              :loading="complianceLoading"
              @click="runComplianceCheck"
            >
              <template #icon><SafetyCertificateOutlined /></template>
              合规与可制造性检查
            </a-button>
          </div>
          <a-spin :spinning="complianceLoading">
            <div v-if="complianceResult" class="compliance-result">
              <a-row :gutter="12">
                <a-col :span="8">
                  <a-card size="small" class="kpi-card">
                    <a-statistic
                      title="综合得分"
                      :value="complianceResult.overall_score ?? 0"
                      :precision="2"
                      :value-style="{ color: scoreColor(complianceResult.overall_score ?? 0) }"
                    />
                  </a-card>
                </a-col>
                <a-col :span="8">
                  <a-card size="small" class="kpi-card">
                    <a-statistic
                      :title="`估算成本 (元/${massUnit})`"
                      :value="complianceResult.estimated_cost ?? 0"
                      :precision="2"
                    />
                  </a-card>
                </a-col>
                <a-col :span="8">
                  <a-card size="small" class="kpi-card">
                    <a-statistic
                      title="供应链风险"
                      :value="complianceResult.supply_risk ?? '未知'"
                    />
                  </a-card>
                </a-col>
              </a-row>
              <a-descriptions
                v-if="complianceResult.checks?.length"
                size="small"
                :column="1"
                bordered
                class="checks-list"
              >
                <a-descriptions-item
                  v-for="(check, idx) in complianceResult.checks"
                  :key="idx"
                  :label="check.name"
                >
                  <a-tag :color="check.passed ? 'green' : 'red'">
                    {{ check.passed ? '通过' : '不通过' }}
                  </a-tag>
                  <span class="check-detail">{{ check.detail || '—' }}</span>
                </a-descriptions-item>
              </a-descriptions>
            </div>
            <div v-else-if="!complianceLoading" class="empty-inline">
              <EmptyState
                type="data"
                description="点击上方按钮进行工业化验证"
              />
            </div>
          </a-spin>
        </div>
      </a-tab-pane>

      <!-- Tab 5: 相关知识 -->
      <a-tab-pane key="knowledge" tab="相关知识">
        <div class="tab-pane-content">
          <MaterialKnowledgeCard
            v-if="candidate && (candidate.formula || candidate.name)"
            :query="candidate.formula || candidate.name"
            :limit="5"
          />
          <EmptyState
            v-else
            type="data"
            description="暂无相关知识数据"
          />
        </div>
      </a-tab-pane>
    </a-tabs>

    <!-- 跨尺度预测抽屉（已抽取为子组件） -->
    <CrossScaleDrawer
      v-model:open="crossScaleDrawerOpen"
      :candidate="candidate"
      :smiles="smiles"
      :structure-kind="structureKind"
      :candidate-id="candidateId"
      :material-name="title"
      @predicted="onCrossScalePredicted"
    />

    <!-- 合成路径抽屉（已抽取为子组件） -->
    <SynthesisDrawer
      v-model:open="synthDrawerOpen"
      :candidate="candidate"
      :smiles="smiles"
      :structure-kind="structureKind"
      :candidate-id="candidateId"
      :loading="synthLoading"
      @submit="onSynthSubmit"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onBeforeUnmount, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import {
  ThunderboltOutlined,
  BranchesOutlined,
  SafetyCertificateOutlined,
  ApiOutlined,
  ExperimentOutlined,
} from '@ant-design/icons-vue'
import StructureView from './StructureView.vue'
import AIOutputMeta from './AIOutputMeta.vue'
import CrossScaleDrawer from './candidate/CrossScaleDrawer.vue'
import SynthesisDrawer from './candidate/SynthesisDrawer.vue'
import MaterialKnowledgeCard from './MaterialKnowledgeCard.vue'
import { formatNumber, formatSci } from '@/utils/format'
import { planSynthesisAsync, getSynthesisTask } from '@/api/synthesis'
import client from '@/api/client'
import { useUnitSymbols } from '@/utils/mdmDict'
import { getSourceBadge } from '@/utils/candidateSource'
import EmptyState from '@/components/EmptyState.vue'

const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const condUnit = computed(() => unitSymbols.value.conductivity || 'S/cm')
const energyUnit = computed(() => unitSymbols.value.energy || 'eV')
const densityUnit = computed(() => unitSymbols.value.density || 'g/cm³')
const capUnit = computed(() => unitSymbols.value.specific_capacity || 'mAh/g')
const massUnit = computed(() => unitSymbols.value.mass || 'kg')
const energyDensityUnit = computed(() => unitSymbols.value.energy_density || 'Wh/kg')
const powerDensityUnit = computed(() => unitSymbols.value.power_density || 'W/kg')
const thermalConductivityUnit = computed(() => unitSymbols.value.thermal_conductivity || 'W/mK')
const temperatureDeltaUnit = computed(() => unitSymbols.value.temperature_delta || 'K')
const modulusUnit = computed(() => unitSymbols.value.modulus || 'GPa')

onMounted(() => {
  loadUnitSymbols()
})

const props = defineProps({
  candidate: { type: Object, required: true },
  type: { type: String, default: 'crystal' },
})

// 向父组件通知选中的合成路径（供「进入配方设计」携带 route_id）
const emit = defineEmits(['route-selected'])

const router = useRouter()

const activeTab = ref('structure')
const synthLoading = ref(false)
const synthResult = ref(null)
// P3-B2：持久化的合成可行性摘要（最佳路线可行性，仅展示不参与评分）
const synthFeasibility = ref(null)
const complianceLoading = ref(false)
const complianceResult = ref(null)
// 用户在合成路径 Tab 中选中的路线 ID（供父组件跳转配方设计时携带）
const selectedRouteId = ref(null)
// 跨尺度预测完整结果（molecular/reaction/continuum/coupled）
const crossScaleResult = ref(null)

// 审查意见0726：模型版本与置信度信息（来自能力契约）
const modelMeta = ref(null)

// 按候选缓存跨尺度预测结果，切换候选时保存/恢复，避免重复预测
const crossScaleCache = reactive({})

const candidateKey = computed(() => {
  const c = props.candidate
  return (
    c.id ||
    c.material_id ||
    `${c.formula || ''}|${c.smiles || c.psmiles || c.monomer_smiles?.[0] || ''}`
  )
})

// 工具：获取候选 ID（用于后端持久化 API）
const candidateId = computed(() => {
  const c = props.candidate
  return c.id || c.candidate_id || c.material_id || ''
})

// Bug3: 轮询取消标志，使用 ref 绑定组件实例，避免模块级变量跨实例串扰
const synthPollingCancelled = ref(false)
onBeforeUnmount(() => {
  synthPollingCancelled.value = true
})

function confidenceColor(conf) {
  if (conf == null) return 'default'
  if (conf >= 0.8) return 'green'
  if (conf >= 0.6) return 'blue'
  if (conf >= 0.4) return 'orange'
  return 'red'
}

// P1-2：候选自身的 AI 置信度（Agent 创造性生成 / 委员会评估路径写入）
const candidateAIConfidence = computed(() => {
  const c = props.candidate?.confidence
  return typeof c === 'number' && c >= 0 && c <= 1 ? c : null
})

// P1-2：报告标准三档配色（高≥0.8 绿 / 中 0.5–0.8 橙 / 低<0.5 红）
function aiConfidenceColor(conf) {
  if (conf == null) return 'default'
  if (conf >= 0.8) return 'green'
  if (conf >= 0.5) return 'orange'
  return 'red'
}

// P1-2：路线证据来源 tooltip（ASKCOS provenance / 本地启发式）
function routeEvidenceTooltip(route) {
  const parts = []
  if (route.provenance?.length) {
    for (const p of route.provenance) {
      parts.push(p.source || p.engine || JSON.stringify(p))
    }
  }
  if (route.engine) parts.push(`引擎：${route.engine}`)
  return parts.length
    ? `证据来源：${parts.join('；')}`
    : '证据来源：合成规划引擎评分（ASKCOS/本地启发式）'
}

const smiles = computed(
  () =>
    props.candidate.smiles ||
    props.candidate.monomer_smiles?.[0] ||
    props.candidate.psmiles ||
    ''
)

const structureKind = computed(() =>
  props.type === 'polymer' ? 'molecule' : 'crystal'
)

const title = computed(
  () =>
    props.candidate.name ||
    props.candidate.formula ||
    smiles.value ||
    props.candidate.material_id ||
    '未命名候选材料'
)

const subtitle = computed(() => {
  if (props.type === 'polymer') {
    return smiles.value || props.candidate.psmiles || '—'
  }
  return (
    [props.candidate.structure_type, props.candidate.space_group]
      .filter(Boolean)
      .join(' · ') || '—'
  )
})

const propColumns = [
  { title: '属性', dataIndex: 'name', key: 'name', width: 180 },
  { title: '数值', key: 'value' },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 100 },
  { title: '来源', dataIndex: 'source', key: 'source', width: 120 },
]

const propRows = computed(() => {
  const c = props.candidate
  const rows = []
  if (c.band_gap != null)
    rows.push({
      key: 'band_gap',
      name: '带隙',
      value: formatNumber(c.band_gap, 4),
      unit: energyUnit.value,
      source: c.band_gap_source || 'DFT',
      predicted: true,
      evidence: c.band_gap_evidence,
    })
  if (c.formation_energy != null)
    rows.push({
      key: 'formation_energy',
      name: '形成能',
      value: formatNumber(c.formation_energy, 4),
      unit: `${energyUnit.value}/atom`,
      source: c.formation_energy_source || 'DFT',
      predicted: true,
    })
  if (c.ionic_conductivity_estimate != null)
    rows.push({
      key: 'cond1',
      name: '离子电导率',
      value: formatSci(c.ionic_conductivity_estimate, 3),
      unit: condUnit.value,
      source: 'ML 估计',
      predicted: true,
      evidence: 'computed',
    })
  if (c.predicted_ionic_conductivity != null)
    rows.push({
      key: 'cond2',
      name: '离子电导率（预测）',
      value: formatSci(c.predicted_ionic_conductivity, 3),
      unit: condUnit.value,
      source: 'ML 预测',
      predicted: true,
      evidence: 'auxiliary',
    })
  if (c.stability_score != null)
    rows.push({
      key: 'stab',
      name: '稳定性评分',
      value: formatNumber(c.stability_score, 3),
      // 无量纲评分，无对应 MDM 单位
      unit: '—',
      source: c.stability_source || '经验模型',
      predicted: true,
    })
  if (c.multi_objective_score != null)
    rows.push({
      key: 'mo',
      name: '综合评分',
      value: (c.multi_objective_score * 100).toFixed(1) + '%',
      // 百分比，无对应 MDM 单位
      unit: '—',
      source: '多目标优化',
      predicted: true,
    })
  return rows
})

// 属性中文映射 + 跨尺度预测结果行
const PROP_NAME_CN = {
  band_gap: '带隙',
  formation_energy: '形成能',
  ionic_conductivity: '离子电导率',
  glass_transition_temp: '玻璃化转变温度',
  dielectric_constant: '介电常数',
  elastic_modulus: '弹性模量',
  thermal_conductivity: '热导率',
  decomposition_temp: '分解温度',
  total_energy: '总能量',
  bulk_modulus: '体弹性模量',
  shear_modulus: '剪切模量',
  e_above_hull: '凸包上方能量',
}

const crossScalePropRows = computed(() => {
  const props_list = crossScaleResult.value?.molecular?.properties
  if (!Array.isArray(props_list) || !props_list.length) return []
  return props_list.map((p, idx) => ({
    key: 'cs_' + idx,
    name: PROP_NAME_CN[p.name] || p.name,
    value: p.value != null ? formatNumber(p.value, 4) : '—',
    unit: p.unit || '',
    source: p.model || '跨尺度预测',
    predicted: true,
    confidence: p.confidence,
  }))
})

// 切换候选时：保存旧候选的预测结果，恢复新候选的已缓存结果
// Bug4: 监听 candidateKey（字符串）而非 props.candidate（对象引用），
// 避免父组件传新引用但内容相同时误重置
// Race Condition 修复：切换候选时必须取消旧轮询，否则旧候选的轮询结果
// 会写入新候选的视图
watch(
  candidateKey,
  (newKey, oldKey) => {
    if (newKey === oldKey) return
    // 保存上一个候选的预测结果
    if (oldKey) {
      crossScaleCache[oldKey] = {
        result: crossScaleResult.value,
        meta: modelMeta.value,
      }
    }
    // Race Condition 修复：取消旧候选的轮询，避免结果串扰
    if (synthLoading.value) {
      synthPollingCancelled.value = true
      synthLoading.value = false
      synthResult.value = null
      message.info('已切换候选材料，上一个合成任务已取消')
    }
    // 恢复当前候选的已缓存结果
    const cached = crossScaleCache[newKey]
    crossScaleResult.value = cached?.result || null
    modelMeta.value = cached?.meta || null
    complianceResult.value = null
    selectedRouteId.value = null
    activeTab.value = 'structure'
  }
)

// ====== 后端持久化加载 ======
// 一次性拉取该候选的全部产出物 + 最新合成任务，恢复三个 Tab 状态
async function loadPersistedArtifacts() {
  const cid = candidateId.value
  if (!cid) return
  try {
    const data = await client.get(`/candidates/${cid}/artifacts`)
    // 恢复性质预测
    const prediction = (data.artifacts || []).find(
      (a) => a.artifact_type === 'prediction'
    )
    if (prediction && prediction.artifact_data) {
      crossScaleResult.value = prediction.artifact_data
    }
    // 恢复合规检查
    const compliance = (data.artifacts || []).find(
      (a) => a.artifact_type === 'compliance'
    )
    if (compliance && compliance.artifact_data) {
      complianceResult.value = compliance.artifact_data
    }
    // 恢复合成路径（保留 task_id 以便生成 BOM 时用）
    if (data.latest_synthesis_task && data.latest_synthesis_task.result) {
      const result = data.latest_synthesis_task.result
      synthResult.value = {
        ...result,
        task_id: data.latest_synthesis_task.task_id,
      }
    }
    // P3-B2：恢复持久化的合成可行性摘要（最佳路线可行性，仅展示不参与评分）
    synthFeasibility.value = data.synthesis_feasibility || null
  } catch (err) {
    // 404 或网络错误：忽略，保持 null
  }
}

// 候选变化（含首次加载）时拉取后端持久化数据
watch(candidateId, () => {
  loadPersistedArtifacts()
}, { immediate: true })

// ====== 跨尺度预测抽屉 ======
const crossScaleDrawerOpen = ref(false)

function openCrossScaleDrawer() {
  crossScaleDrawerOpen.value = true
}

// 子组件完成预测后，保存结果 + 模型元信息
function onCrossScalePredicted(res) {
  crossScaleResult.value = res
  // 模型信息条：优先用 molecular.properties[0].model 作为展示
  const firstProp = res?.molecular?.properties?.[0]
  if (firstProp?.model) {
    modelMeta.value = {
      model_name: firstProp.model,
      confidence: firstProp.confidence,
    }
  }
  // 执行 agent 标注
  if (res?.executed_by) {
    modelMeta.value = {
      ...(modelMeta.value || {}),
      executed_by: res.executed_by,
    }
  }
}

// ====== 合成路径抽屉 ======
const synthDrawerOpen = ref(false)

function openSynthDrawer() {
  // Bug8: 轮询进行中时禁止重复提交，避免状态冲突
  if (synthLoading.value) {
    message.info('合成规划正在进行中，请等待当前任务完成')
    return
  }
  synthDrawerOpen.value = true
}

// 子组件提交参数后，父组件负责 API 调用 + 轮询
async function onSynthSubmit(payload) {
  synthLoading.value = true
  synthResult.value = null
  // Bug3: 每次启动轮询前重置取消标志
  synthPollingCancelled.value = false
  try {
    const submit = await planSynthesisAsync(payload)
    const taskId = submit.task_id
    if (!taskId) {
      synthResult.value = submit
      return
    }
    // 关闭抽屉，开始轮询（600s 总时长，5s 间隔，匹配后端 _SYNTHESIS_TASK_TIMEOUT）
    synthDrawerOpen.value = false
    message.info('已提交合成规划任务，大模型推理可能需要 1-3 分钟，请耐心等待…')
    for (let i = 0; i < 120; i++) {
      // Bug3: 组件已卸载或轮询被取消则终止轮询
      if (synthPollingCancelled.value) return
      await new Promise((r) => setTimeout(r, 5000))
      if (synthPollingCancelled.value) return
      const task = await getSynthesisTask(taskId)
      if (task.status === 'done' || task.status === 'success') {
        // Bug2: 校验 result 非空对象，避免空 {} 被当作有效结果导致渲染空白
        const result = task.result || task
        const hasContent =
          (result.routes && result.routes.length) ||
          result.message ||
          result.reasoning ||
          result.agent_info
        if (hasContent) {
          synthResult.value = { ...result, task_id: taskId }
          message.success('合成规划完成')
        } else {
          synthResult.value = {
            message: '合成规划完成但返回内容为空，请检查后端服务或更换引擎重试',
          }
        }
        return
      }
      if (task.status === 'failed' || task.status === 'error') {
        synthResult.value = {
          message: '合成规划失败：' + (task.error || '服务暂不可用'),
        }
        return
      }
    }
    synthResult.value = { message: '合成规划超时，请稍后查看任务列表' }
  } catch (e) {
    // Bug5: 附带具体错误信息，便于排查
    const errMsg = e?.response?.data?.detail || e?.message || '未知错误'
    synthResult.value = {
      message: '合成规划请求失败：' + errMsg,
    }
  } finally {
    synthLoading.value = false
  }
}

// 选中合成路径：通知父组件，供「进入配方设计」携带 route_id
function onSelectRoute(route, idx) {
  const routeId = route.route_id || `R${idx + 1}`
  selectedRouteId.value = routeId
  emit('route-selected', {
    route_id: routeId,
    synthesis_task_id: synthResult.value?.task_id || '',
    route_index: idx,
  })
}

// 创建实验任务：跳转实验工作台，自动带出候选材料与项目
function onCreateExperiment() {
  router.push({
    path: '/experiment-workbench',
    query: {
      candidate_id: candidateId.value,
      project_id: props.candidate.project_id || '',
      create: '1',
    },
  })
}

async function runComplianceCheck() {
  complianceLoading.value = true
  complianceResult.value = null
  try {
    // 调用工业化合规检查接口
    const res = await client.post('/industrialization/check', {
      formula: props.candidate.formula || '',
      smiles: smiles.value,
      target_material: props.candidate,
      candidate_id: candidateId.value,
    })
    complianceResult.value = res
  } catch (e) {
    // 兜底：使用本地简单评估
    complianceResult.value = {
      overall_score: props.candidate.multi_objective_score ?? 0,
      estimated_cost: '—',
      supply_risk: '未知',
      checks: [
        {
          name: '合规检查接口',
          passed: false,
          detail: '服务暂不可用，请稍后再试',
        },
      ],
    }
  } finally {
    complianceLoading.value = false
  }
}

function formatElements(els) {
  if (Array.isArray(els)) return els.join(', ')
  if (typeof els === 'object') {
    return Object.entries(els)
      .map(([k, v]) => `${k}${v}`)
      .join(' ')
  }
  return String(els || '—')
}

function riskColor(level) {
  return { A: 'green', B: 'blue', C: 'orange', D: 'red' }[level] || 'default'
}

function riskLabel(level) {
  return { A: 'A 级·可自动', B: 'B 级·辅助', C: 'C 级·需审批', D: 'D 级·禁用' }[
    level
  ] || level
}

function verdictColor(v) {
  return {
    pass: 'green',
    reject: 'red',
    request_evidence: 'gold',
    human_review: 'volcano',
    failed: 'red',
  }[v] || 'default'
}

function verdictLabel(v) {
  return {
    pass: '委员会通过',
    reject: '委员会拒绝',
    request_evidence: '需补证据',
    human_review: '需人工复核',
  }[v] || v
}

function scoreColor(s) {
  if (s >= 0.8) return '#52c41a'
  if (s >= 0.6) return '#faad14'
  return '#ff4d4f'
}
</script>

<style scoped>
.candidate-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--light-bg-card, #fff);
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border, #f0f0f0);
}

.header-left {
  flex: 1;
  min-width: 0;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #1a1a1a);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-subtitle {
  font-size: 12px;
  color: var(--text-secondary, #666);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.detail-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0 16px;
}

.detail-tabs :deep(.ant-tabs-content) {
  flex: 1;
  overflow: hidden;
}

.detail-tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
  overflow: auto;
}

.tab-pane-content {
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

.tab-hint {
  flex: 1;
  font-size: 12px;
  color: var(--text-secondary, #666);
}

/* 跨尺度预测结果展示 */
.cross-scale-result {
  margin-top: 16px;
  padding: 12px;
  background: rgba(249, 115, 22, 0.03);
  border: 1px solid rgba(249, 115, 22, 0.1);
  border-radius: 6px;
}
.cs-result-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #1f1f1f);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.cs-result-section {
  margin-top: 12px;
}
.cs-result-subtitle {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #666);
  margin-bottom: 6px;
  padding-left: 8px;
  border-left: 3px solid var(--primary, #2050d0);
}
.cs-correlations {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cs-correlation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 4px 0;
}
.cs-corr-prop {
  font-weight: 500;
  color: var(--text-primary, #1f1f1f);
}
.cs-corr-desc {
  color: var(--text-secondary, #999);
  flex: 1;
}

/* 审查意见0726：模型版本与置信度信息条 */
.model-meta-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: rgba(249, 115, 22, 0.04);
  border: 1px solid rgba(249, 115, 22, 0.12);
  border-radius: 6px;
  font-size: 12px;
  flex-wrap: wrap;
}

.model-meta-bar .meta-hint {
  margin-left: auto;
  color: var(--text-muted, #8a92a6);
  font-size: 11px;
}

.structure-stage {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 340px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #f0f0f0);
  border-radius: 8px;
  padding: 12px;
}

.structure-meta {
  margin-top: 8px;
}

.prop-table :deep(.ant-table-thead > tr > th) {
  background: var(--light-bg-hover, #fafafa);
  font-size: 12px;
}

.prop-table :deep(.ant-table-tbody > tr > td) {
  font-size: 13px;
  padding: 6px 8px;
}

.prop-value {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.prop-predicted {
  color: var(--primary, #2050d0);
}

.empty-inline {
  padding: 32px 0;
  display: flex;
  justify-content: center;
}

.synth-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 合成路径 Agent 信息条 */
.synth-agent-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: rgba(249, 115, 22, 0.04);
  border: 1px solid rgba(249, 115, 22, 0.12);
  border-radius: 6px;
  font-size: 12px;
  flex-wrap: wrap;
}

/* AI4S 推理过程 */
.synth-reasoning {
  margin-top: 8px;
  padding: 10px 12px;
  background: rgba(250, 173, 20, 0.06);
  border: 1px solid rgba(250, 173, 20, 0.2);
  border-radius: 6px;
}
.synth-reasoning-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1f1f1f);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.synth-reasoning-body {
  font-size: 12px;
  color: var(--text-secondary, #555);
  line-height: 1.6;
  white-space: pre-wrap;
}

.synth-routes {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.synth-route {
  border: 1px solid var(--border, #f0f0f0);
  border-radius: 6px;
  padding: 10px 12px;
  background: var(--light-bg-hover, #fafafa);
  transition: border-color 0.2s ease, background 0.2s ease;
}

.synth-route-selected {
  border-color: #5b6ef5;
  background: #eef0ff;
}

.route-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.route-num {
  color: var(--text-primary, #1a1a1a);
}

.route-steps {
  color: var(--text-secondary, #666);
  font-size: 12px;
  font-weight: 400;
}

.route-steps-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.route-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 4px 8px;
  background: #fff;
  border-radius: 4px;
}

.step-num {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary-bg, #e6f4ff);
  color: var(--primary, #2050d0);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 11px;
}

.step-smiles {
  flex: 1;
  font-family: 'Consolas', monospace;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compliance-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kpi-card {
  text-align: center;
}

.kpi-card :deep(.ant-statistic-title) {
  font-size: 12px;
}

.kpi-card :deep(.ant-statistic-content) {
  font-size: 18px;
}

.checks-list {
  margin-top: 4px;
}

.check-detail {
  margin-left: 8px;
  color: var(--text-secondary, #666);
  font-size: 12px;
}
</style>
