<template>
  <div class="scientific-workbench">
    <!-- 顶部标题栏 -->
    <header class="wb-header">
      <div class="wb-title">
        <span class="wb-title-text">科学工作台</span>
        <span class="wb-subtitle">12 个原生科学服务 · 任务/Run/证据/审批 全生命周期</span>
      </div>
      <div class="wb-header-actions">
        <a-input v-model:value="projectId" size="small" placeholder="项目 ID" class="project-input" />
        <a-radio-group v-model:value="execMode" size="small" button-style="solid">
          <a-radio-button value="agent">智能体执行</a-radio-button>
          <a-radio-button value="direct">直接执行</a-radio-button>
          <a-radio-button value="full">全生命周期</a-radio-button>
        </a-radio-group>
        <a-button size="small" @click="refreshAll" :loading="refreshing">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
    </header>

    <!-- 主体三栏布局 -->
    <div class="wb-body">
      <!-- 左侧：服务目录 -->
      <aside class="wb-left">
        <div class="panel-head">服务目录</div>
        <div class="panel-scroll">
          <ServiceCatalog :selected-id="selectedService?.id" @select="onSelectService" />
        </div>
      </aside>

      <!-- 中间：操作区 -->
      <section class="wb-middle">
        <div class="panel-head">
          <span v-if="selectedService">{{ selectedService.name }} · 参数配置</span>
          <span v-else>请选择服务</span>
        </div>
        <div class="panel-scroll">
          <div v-if="!selectedService" class="empty-hint">
            <ExperimentOutlined class="empty-icon" />
            <p>从左侧选择一个科学服务开始</p>
          </div>
          <template v-else>
            <a-select
              v-if="currentCommands && Object.keys(currentCommands).length > 1"
              v-model:value="selectedCommand"
              size="small"
              style="margin-bottom: 12px; width: 100%"
              @change="onCommandChange"
            >
              <a-select-option v-for="(cmd, key) in currentCommands" :key="key" :value="key">{{ cmd.label }}</a-select-option>
            </a-select>
            <a-form layout="vertical" size="small" class="service-form">
              <a-form-item
                v-for="field in currentFields"
                :key="field.key"
                :label="field.label"
              >
                <!-- 候选材料选择：选中后自动加载配方成分/分子 -->
                <div v-if="field.type === 'candidate-select'" class="candidate-select-wrap">
                  <div class="candidate-select-row">
                    <a-select
                      v-model:value="formData[field.key]"
                      :options="candidateOptions"
                      :loading="candidatesLoading"
                      show-search
                      option-filter-prop="label"
                      placeholder="选择候选材料"
                      style="flex: 1"
                      @change="onCandidateChange(field)"
                    />
                    <a-button
                      size="small"
                      :loading="candidateCompLoading"
                      @click="onCandidateChange(field)"
                    >加载成分</a-button>
                  </div>
                  <div v-if="formData[field.targetKey] && formData[field.targetKey].length" class="candidate-hint">
                    已从候选材料加载 {{ formData[field.targetKey].length }} 个组分，可编辑比例范围
                  </div>
                </div>

                <!-- 组分可编辑表格：名称 / SMILES / 比例范围 -->
                <div v-else-if="field.type === 'comp-table'" class="comp-table-wrap">
                  <div v-for="(row, i) in formData[field.key] || []" :key="i" class="comp-row">
                    <a-input v-model:value="row.name" size="small" placeholder="名称" class="comp-name" />
                    <a-input v-model:value="row.smiles" size="small" placeholder="SMILES" class="comp-smiles" />
                    <a-input-number v-model:value="row.ratio_range_min" size="small" :min="0" :max="1" :step="0.1" class="comp-range" />
                    <a-input-number v-model:value="row.ratio_range_max" size="small" :min="0" :max="1" :step="0.1" class="comp-range" />
                    <a-button size="small" type="text" danger @click="removeCompRow(field.key, i)">
                      <template #icon><DeleteOutlined /></template>
                    </a-button>
                  </div>
                  <a-button size="small" type="dashed" block @click="addCompRow(field.key)">
                    <template #icon><PlusOutlined /></template>添加组分
                  </a-button>
                </div>

                <a-select
                  v-else-if="field.type === 'enum-multi'"
                  v-model:value="formData[field.key]"
                  mode="multiple"
                  :options="enumOptionsFor(field)"
                  :placeholder="field.placeholder || '选择'"
                />
                <a-select
                  v-else-if="field.type === 'dynamic-select'"
                  v-model:value="formData[field.key]"
                  :options="dynamicOptionsFor(field)"
                  :placeholder="field.placeholder"
                />
                <a-select
                  v-else-if="field.type === 'select'"
                  v-model:value="formData[field.key]"
                  :options="field.options"
                  @change="onSelectChange(field, $event)"
                />
                <a-input-number
                  v-else-if="field.type === 'number'"
                  v-model:value="formData[field.key]"
                  :placeholder="field.placeholder"
                  style="width: 100%"
                />
                <a-select
                  v-else-if="field.type === 'tags'"
                  v-model:value="formData[field.key]"
                  mode="tags"
                  :placeholder="field.placeholder || '输入后回车添加'"
                  :token-separators="[',', '\n']"
                />
                <a-textarea
                  v-else-if="field.type === 'textarea'"
                  v-model:value="formData[field.key]"
                  :rows="field.rows || 3"
                  :placeholder="field.placeholder"
                />
                <a-input
                  v-else
                  v-model:value="formData[field.key]"
                  :placeholder="field.placeholder"
                />
              </a-form-item>
            </a-form>
            <div class="form-actions">
              <a-button type="primary" :loading="executing" @click="executeService">
                <template #icon><PlayCircleOutlined /></template>
                {{ execMode === 'full' ? '执行全生命周期' : execMode === 'agent' ? '通过智能体执行' : '执行' }}
              </a-button>
              <a-button @click="resetForm">重置</a-button>
            </div>
            <div v-if="execMode === 'agent' && selectedService" class="agent-mode-hint">
              将通过「{{ agentForService(selectedService.id)?.agent_id }}」智能体调用
              <code>{{ agentForService(selectedService.id)?.capability }}</code> 工具执行
            </div>

            <!-- 执行结果摘要 -->
            <div v-if="lastResult" class="result-summary">
              <div class="result-summary-head">
                <span class="result-title">最近执行结果</span>
                <a-tag :color="lastResult.type === 'evidence' ? 'orange' : lastResult.type === 'agent' ? 'green' : 'blue'">
                  {{ lastResult.type === 'evidence' ? '证据包' : lastResult.type === 'agent' ? '智能体' : '工件' }} × {{ lastResult.data.length }}
                </a-tag>
              </div>
              <div class="result-meta" v-if="lastResult.agentInfo">
                <span>Agent: {{ lastResult.agentInfo.agent_id }} → 工具: {{ lastResult.agentInfo.tool_id }}</span>
                <span v-if="lastResult.agentInfo.used_fallback" class="fallback-tag">已回退</span>
              </div>
              <div class="result-meta" v-else-if="lastResult.runId">
                <span>Run: {{ lastResult.runId.slice(0, 8) }}…</span>
              </div>
            </div>
          </template>
        </div>
      </section>

      <!-- 右侧：结果区 -->
      <aside class="wb-right">
        <a-tabs v-model:activeKey="rightTab" size="small" class="right-tabs">
          <a-tab-pane key="runs" tab="运行记录">
            <div class="panel-scroll right-scroll">
              <a-empty v-if="runs.length === 0" description="暂无运行记录" :image="simpleImage" />
              <div v-else class="run-list">
                <div
                  v-for="r in runs"
                  :key="r.run_id"
                  class="run-item"
                  :class="{ active: selectedRunId === r.run_id }"
                  @click="openRunDetail(r.run_id)"
                >
                  <div class="run-item-head">
                    <a-badge :status="runBadge(r.status)" :text="runStatusLabel(r.status)" />
                    <span class="run-svc">{{ r.service_id }}</span>
                  </div>
                  <div class="run-item-meta">
                    <code>{{ r.run_id.slice(0, 8) }}</code>
                    <span class="run-cmd">{{ r.command }}</span>
                  </div>
                  <div class="run-item-time">{{ formatTime(r.created_at) }}</div>
                </div>
              </div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="artifacts" tab="工件">
            <div class="panel-scroll right-scroll">
              <a-empty v-if="artifacts.length === 0" description="选择 Run 查看工件" :image="simpleImage" />
              <div v-else class="artifact-compact-list">
                <div v-for="art in artifacts" :key="art.artifact_id" class="artifact-compact" @click="openRunDetail(selectedRunId)">
                  <span class="art-type" :class="`type-${art.type}`">{{ art.type }}</span>
                  <span class="art-name">{{ art.name }}</span>
                </div>
              </div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="evidence" tab="证据">
            <div class="panel-scroll right-scroll">
              <a-empty v-if="evidenceList.length === 0" description="选择 Run 查看证据" :image="simpleImage" />
              <EvidenceCard
                v-for="ev in evidenceList"
                :key="ev.evidence_id"
                :evidence="ev"
                @click="onEvidenceClick(ev)"
              />
            </div>
          </a-tab-pane>
        </a-tabs>
      </aside>
    </div>

    <!-- 底部状态栏 -->
    <footer class="wb-footer">
      <div class="status-item">
        <span class="status-dot" :class="workerStatusClass" />
        <span class="status-label">CPU Worker:</span>
        <span class="status-value">{{ workerStatusLabel }}</span>
      </div>
      <div class="status-item">
        <span class="status-label">队列:</span>
        <span class="status-value">{{ queueDepth }} 待执行</span>
      </div>
      <div class="status-item">
        <span class="status-label">运行中:</span>
        <span class="status-value">{{ runningCount }} 个</span>
      </div>
      <div class="status-item">
        <span class="status-label">累计:</span>
        <span class="status-value">{{ runs.length }} 个 Run</span>
      </div>
      <div class="status-item status-time">
        <span class="status-label">更新:</span>
        <span class="status-value">{{ lastRefreshLabel }}</span>
      </div>
    </footer>

    <!-- Run 详情抽屉 -->
    <TaskRunDetail
      :run-id="selectedRunId"
      :visible="showRunDetail"
      @close="showRunDetail = false"
      @evidence-click="onEvidenceClick"
    />

    <!-- 证据审批弹窗 -->
    <a-modal
      v-model:open="showApproval"
      :title="`审批证据 · ${selectedEvidence?.claim?.slice(0, 24) || ''}`"
      :confirm-loading="approving"
      @ok="handleApprove"
      @cancel="handleReject"
    >
      <template v-if="selectedEvidence">
        <EvidenceCard :evidence="selectedEvidence" />
        <a-form layout="vertical" size="small" class="approval-form">
          <a-form-item label="评审人">
            <a-input v-model:value="approvalReviewer" placeholder="输入评审人" />
          </a-form-item>
          <a-form-item label="评审意见">
            <a-textarea v-model:value="approvalComment" :rows="2" />
          </a-form-item>
        </a-form>
        <div class="approval-modal-hint">确定=通过 · 取消=驳回</div>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Empty, message } from 'ant-design-vue'
import { PlayCircleOutlined, ReloadOutlined, ExperimentOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import {
  listRuns, getArtifacts, getRunEvidence,
  requestApproval, approve, reject,
  formulation, structure, molecularSimulation, processModeling,
  SERVICE_API_MAP, SERVICE_AGENT_MAP, invokeAgentTool,
} from '@/api/scientific'
import { listCandidates } from '@/api/candidates'
import ServiceCatalog from './scientific/ServiceCatalog.vue'
import TaskRunDetail from './TaskRunDetail.vue'
import EvidenceCard from './EvidenceCard.vue'

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE
const route = useRoute()

// ── 全局状态 ────────────────────────────────────────────────
const projectId = ref(route.query.project_id || 'default')
// 默认通过智能体执行（设计理念：业务活动通过匹配的智能体调用服务）
const execMode = ref('agent')
const selectedService = ref(null)
const formData = reactive({})
const executing = ref(false)
const refreshing = ref(false)
const lastResult = ref(null)

// 候选材料 / 枚举加载状态
const candidateOptions = ref([])
const candidatesLoading = ref(false)
const candidateCompLoading = ref(false)
const structureFormats = ref([])
const mdMetrics = ref([])
const processModulesRaw = ref([])
const processCalcTypes = ref([])

// process_modeling 每模块参数模板（模块切换时预填）
const PM_CONDITIONS_TEMPLATE = {
  M1: { temperature_k: 298.15, pressure_pa: 101325 },
  M2: { temperature_k: 298.15 },
  M3: { temperature_k: 298.15, pressure_pa: 101325 },
  M4: { temperature_k: 298.15, pressure_pa: 101325 },
  M5: { temperature_k: 351.45, pressure_pa: 101325 },
  M6: {},
}
const PM_PARAMS_TEMPLATE = {
  M1: { method: 'hess' },
  M2: { method: 'wilke_chang' },
  M3: { calculation_type: 'batch_reactor' },
  M4: {},
  M5: { method: 'fenske_underwood_gilliland', x_d: 0.99, x_b: 0.01, x_f: 0.5, q: 1.0, alpha: 2.5 },
  M6: {},
}

// 右侧面板
const rightTab = ref('runs')
const runs = ref([])
const selectedRunId = ref(null)
const artifacts = ref([])
const evidenceList = ref([])

// Run 详情抽屉
const showRunDetail = ref(false)

// 审批
const showApproval = ref(false)
const selectedEvidence = ref(null)
const approvalReviewer = ref('')
const approvalComment = ref('')
const approving = ref(false)

// 状态栏
const lastRefresh = ref(null)
let pollTimer = null

// ── 服务表单 schema ─────────────────────────────────────────
// 每个服务定义其命令的参数表单；project_id 由顶部统一输入，不重复列出。
// commands 字典：key 为命令名，value 含 label/fullCmd/fields。
// 当 commands 仅一个 key 时，UI 不显示命令选择器；多个时显示。
const SERVICE_FORMS = {
  mpa: {
    api: 'mpa',
    commands: {
      predict: {
        label: '性质预测', fullCmd: 'predictFull',
        fields: [
          { key: 'molecule_revision_ids', label: '分子 SMILES 列表', type: 'tags', placeholder: '输入 SMILES 后回车', default: [] },
          { key: 'property_keys', label: '属性键（可选）', type: 'tags', placeholder: '留空预测全部 42 种', default: [] },
          { key: 'require_uncertainty', label: '要求不确定性', type: 'select', default: true, options: [{ value: true, label: '是' }, { value: false, label: '否' }] },
        ],
      },
    },
  },
  chemical: {
    api: 'chemical',
    commands: {
      query: {
        label: '性质查询', fullCmd: 'queryFull',
        fields: [
          { key: 'compound_name', label: '化合物', type: 'text', placeholder: '名称/SMILES/CAS；M3/M4 需 "A/B" 格式', default: '' },
          { key: 'module', label: '查询模块', type: 'select', default: 'M1', options: [
            { value: 'M1', label: 'M1 标准常数' }, { value: 'M2', label: 'M2 T/P 依赖' },
            { value: 'M3', label: 'M3 VLE' }, { value: 'M4', label: 'M4 闪蒸' }, { value: 'M5', label: 'M5 溶解度' },
          ] },
          { key: 'temperature_k', label: '温度 (K)', type: 'number', default: 298.15 },
          { key: 'pressure_pa', label: '压力 (Pa)', type: 'number', default: 101325 },
          { key: 'composition', label: '摩尔分数列表（M3/M4 必填）', type: 'textarea', placeholder: '[0.5, 0.5]', default: '[]' },
          { key: 'property_keys', label: '特定性质键（可选）', type: 'tags', placeholder: '留空查询全部', default: [] },
        ],
      },
    },
  },
  structure: {
    api: 'structure',
    commands: {
      generate: {
        label: '结构生成', fullCmd: null,
        fields: [
          { key: 'input_format', label: '输入格式', type: 'select', default: 'smiles', options: [
            { value: 'smiles', label: 'SMILES' }, { value: 'formula', label: 'Formula' },
            { value: 'cif', label: 'CIF' }, { value: 'xyz', label: 'XYZ' },
          ] },
          { key: 'input_data', label: '输入数据', type: 'textarea', placeholder: 'SMILES / 化学式 / CIF 内容', default: '' },
          { key: 'output_formats', label: '输出格式', type: 'enum-multi', loadSource: 'structureFormats', default: ['smiles', 'xyz', 'cif', 'mol'], placeholder: '从后端支持的格式中选择' },
          { key: 'optimization_level', label: '优化级别', type: 'select', default: 'none', options: [
            { value: 'none', label: '不优化' }, { value: 'basic', label: '基础' }, { value: 'full', label: '完整' },
          ] },
          { key: 'force_field', label: '力场（可选）', type: 'select', default: null, options: [
            { value: null, label: '默认' }, { value: 'uff', label: 'UFF' }, { value: 'mmff94', label: 'MMFF94' },
          ] },
        ],
      },
      optimize: {
        label: '结构优化', fullCmd: null,
        fields: [
          { key: 'structure_data', label: '结构数据', type: 'textarea', placeholder: '待优化的结构数据', default: '' },
          { key: 'format', label: '输入格式', type: 'select', default: 'smiles', options: [
            { value: 'smiles', label: 'SMILES' }, { value: 'cif', label: 'CIF' }, { value: 'xyz', label: 'XYZ' }, { value: 'mol', label: 'MOL' },
          ] },
          { key: 'optimization_level', label: '优化级别', type: 'select', default: 'basic', options: [
            { value: 'basic', label: '基础' }, { value: 'full', label: '完整' },
          ] },
          { key: 'max_iterations', label: '最大迭代次数', type: 'number', default: 500 },
        ],
      },
      convert: {
        label: '格式转换', fullCmd: null,
        fields: [
          { key: 'input_format', label: '输入格式', type: 'select', default: 'smiles', options: [
            { value: 'smiles', label: 'SMILES' }, { value: 'cif', label: 'CIF' }, { value: 'xyz', label: 'XYZ' }, { value: 'mol', label: 'MOL' }, { value: 'pdb', label: 'PDB' }, { value: 'sdf', label: 'SDF' }, { value: 'mol2', label: 'MOL2' },
          ] },
          { key: 'input_data', label: '输入数据', type: 'textarea', placeholder: '结构数据', default: '' },
          { key: 'output_format', label: '目标格式', type: 'select', default: 'xyz', options: [
            { value: 'smiles', label: 'SMILES' }, { value: 'cif', label: 'CIF' }, { value: 'xyz', label: 'XYZ' }, { value: 'mol', label: 'MOL' }, { value: 'pdb', label: 'PDB' }, { value: 'sdf', label: 'SDF' }, { value: 'mol2', label: 'MOL2' },
          ] },
        ],
      },
    },
  },
  formulation: {
    api: 'formulation',
    commands: {
      optimize: {
        label: '配方优化', fullCmd: null,
        fields: [
          { key: 'candidate_id', label: '候选材料', type: 'candidate-select', targetKey: 'components', placeholder: '选择候选材料自动加载配方成分', default: '' },
          { key: 'components', label: '配方成分', type: 'comp-table', default: [], placeholder: '名称 / SMILES / 比例范围' },
          { key: 'target_properties', label: '目标属性', type: 'tags', placeholder: '如: MW, logP, TPSA', default: ['MW', 'logP'] },
          { key: 'optimization_goal', label: '优化目标', type: 'select', default: 'maximize', options: [
            { value: 'maximize', label: '最大化' }, { value: 'minimize', label: '最小化' }, { value: 'target', label: '目标值' },
          ] },
          { key: 'constraints', label: '附加约束 (JSON)', type: 'textarea', placeholder: '{}', default: '{}' },
          { key: 'max_iterations', label: '最大迭代', type: 'number', default: 1000 },
        ],
      },
      pack: {
        label: '分子堆积', fullCmd: null,
        fields: [
          { key: 'candidate_id', label: '候选材料', type: 'candidate-select', targetKey: 'molecules', fillMode: 'smiles', placeholder: '选择候选材料自动加载分子 SMILES', default: '' },
          { key: 'molecules', label: '分子 SMILES 列表', type: 'tags', placeholder: '输入 SMILES 后回车，或从候选材料加载', default: [] },
          { key: 'packing_type', label: '堆积类型', type: 'select', default: 'amorphous', options: [
            { value: 'crystal', label: '晶体' }, { value: 'amorphous', label: '无定形' }, { value: 'solvation', label: '溶剂化' },
          ] },
          { key: 'target_density', label: '目标密度 (g/cm³，可选)', type: 'number', default: null, placeholder: '留空自动' },
          { key: 'box_size_nm', label: '盒子边长 (nm，可选)', type: 'number', default: null, placeholder: '留空自动' },
          { key: 'force_field', label: '力场', type: 'select', default: 'uff', options: [
            { value: 'uff', label: 'UFF' }, { value: 'mmff94', label: 'MMFF94' },
          ] },
        ],
      },
    },
  },
  molecular_simulation: {
    api: 'molecularSimulation',
    commands: {
      run: {
        label: 'MD 模拟', fullCmd: 'runFull',
        fields: [
          { key: 'system_type', label: '系统类型', type: 'select', default: 'B', options: [
            { value: 'A', label: 'A 晶体/无机' }, { value: 'B', label: 'B 有机/聚合物' }, { value: 'C', label: 'C 生物分子' },
          ] },
          { key: 'structure_data', label: '结构数据', type: 'textarea', placeholder: 'SMILES / CIF 路径 / data 文件路径', default: '' },
          { key: 'forcefield', label: '力场（可选）', type: 'text', placeholder: '留空使用默认', default: '' },
          { key: 'protocol', label: '系综协议', type: 'select', default: 'nvt', options: [
            { value: 'nvt', label: 'NVT' }, { value: 'npt', label: 'NPT' }, { value: 'nve', label: 'NVE' },
            { value: 'minimize', label: '能量最小化' }, { value: 'npt_nvt', label: 'NPT→NVT' },
          ] },
          { key: 'temperature_k', label: '温度 (K)', type: 'number', default: 300 },
          { key: 'pressure_atm', label: '压力 (atm，可选)', type: 'number', default: null, placeholder: 'NPT 时使用' },
          { key: 'timestep_fs', label: '时间步长 (fs)', type: 'number', default: 1.0 },
          { key: 'run_steps', label: '运行步数', type: 'number', default: 100000 },
          { key: 'requested_metrics', label: '分析指标', type: 'enum-multi', loadSource: 'mdMetrics', default: ['rdf', 'msd', 'energy'], placeholder: '从后端支持的指标中选择' },
        ],
      },
    },
  },
  battery_modeling: {
    api: 'batteryModeling',
    commands: {
      simulate: {
        label: '电池仿真', fullCmd: 'simulateFull',
        fields: [
          { key: 'track', label: '仿真轨道', type: 'select', default: 'p2d', options: [
            { value: 'p2d', label: 'P2D 准二维' }, { value: 'ecm', label: 'ECM 等效电路' }, { value: 'pybop', label: 'PyBOP 参数辨识' },
          ] },
          { key: 'model_type', label: '模型类型', type: 'select', default: 'DFN', options: [
            { value: 'SPM', label: 'SPM' }, { value: 'SPMe', label: 'SPMe' }, { value: 'DFN', label: 'DFN' },
          ] },
          { key: 'parameter_set', label: '参数集', type: 'text', default: 'Chen2020' },
          { key: 'experiment_protocol', label: '实验协议 (JSON，可选)', type: 'textarea', placeholder: '示例: [{"description":"1C 恒流放电","type":"constant_current","value":1.0,"unit":"C"}]', default: '[]' },
          { key: 'thermal_option', label: '热选项', type: 'select', default: 'isothermal', options: [
            { value: 'isothermal', label: '等温' }, { value: 'lumped', label: '集总' }, { value: 'x-full', label: 'X-full' },
          ] },
          { key: 'requested_variables', label: '输出变量', type: 'tags', placeholder: 'Terminal voltage [V], Current [A]', default: ['Terminal voltage [V]', 'Current [A]'] },
        ],
      },
    },
  },
  synthesis_planning: {
    api: 'synthesisPlanning',
    commands: {
      plan: {
        label: '逆合成分析', fullCmd: 'planFull',
        fields: [
          { key: 'target_smiles', label: '目标分子 SMILES', type: 'text', placeholder: '如: CC(=O)Oc1ccccc1C(=O)O', default: '' },
          { key: 'search_depth', label: '搜索深度', type: 'number', default: 3 },
          { key: 'max_paths', label: '最大路线数', type: 'number', default: 10 },
          { key: 'normalize_ions', label: '归一化离子/盐', type: 'select', default: true, options: [{ value: true, label: '是' }, { value: false, label: '否' }] },
          { key: 'include_literature', label: '包含文献验证', type: 'select', default: true, options: [{ value: true, label: '是' }, { value: false, label: '否' }] },
          { key: 'expansion_timeout', label: '搜索超时 (秒)', type: 'number', default: 300 },
        ],
      },
    },
  },
  process_modeling: {
    api: 'processModeling',
    commands: {
      calculate: {
        label: '过程计算', fullCmd: 'calculateFull',
        fields: [
          { key: 'module', label: '计算模块', type: 'select', default: 'M1', options: [], dynamic: 'processModules', placeholder: '选择模块后自动加载计算类型' },
          { key: 'calculation_type', label: '计算类型', type: 'dynamic-select', default: '', placeholder: '按所选模块自动提供可选计算类型' },
          { key: 'candidate_id', label: '从候选材料加载化合物', type: 'candidate-select', targetKey: 'compounds', placeholder: '选择候选材料自动加载化合物列表', default: '' },
          { key: 'compounds', label: '化合物列表', type: 'comp-table', default: [], placeholder: '名称 / SMILES / 比例范围' },
          { key: 'conditions', label: '操作条件 (JSON)', type: 'textarea', placeholder: '温度/压力等，按模块预填默认值', default: '' },
          { key: 'parameters', label: '模块专属参数 (JSON)', type: 'textarea', placeholder: '按模块预填默认参数', default: '' },
        ],
      },
    },
  },
  reaction_network: {
    api: 'reactionNetwork',
    commands: {
      enumerate: {
        label: '反应枚举', fullCmd: null,
        fields: [
          { key: 'reactant_smiles', label: '反应物 SMILES', type: 'tags', placeholder: '输入 SMILES 后回车', default: [] },
          { key: 'charge', label: '总电荷', type: 'number', default: 0 },
          { key: 'multiplicity', label: '自旋多重度', type: 'number', default: 1 },
          { key: 'max_break_bonds', label: '最多断键数', type: 'number', default: 1 },
          { key: 'max_form_bonds', label: '最多成键数', type: 'number', default: 1 },
          { key: 'max_candidates', label: '最大候选反应数', type: 'number', default: 300 },
        ],
      },
      tsSearch: {
        label: '过渡态搜索', fullCmd: null,
        fields: [
          { key: 'reaction_smiles', label: '反应 SMILES', type: 'text', placeholder: 'Reactant>>Product', default: '' },
          { key: 'charge', label: '总电荷', type: 'number', default: 0 },
          { key: 'multiplicity', label: '自旋多重度', type: 'number', default: 1 },
          { key: 'config', label: 'TS 搜索配置 (JSON，可选)', type: 'textarea', placeholder: '{}', default: '{}' },
        ],
      },
      grow: {
        label: '网络扩展', fullCmd: null,
        fields: [
          { key: 'reactants', label: '初始反应物 SMILES', type: 'tags', placeholder: '输入 SMILES 后回车', default: [] },
          { key: 'max_layers', label: '最大扩展层数', type: 'number', default: 3 },
          { key: 'max_species', label: '最大物种数', type: 'number', default: 250 },
          { key: 'barrier_threshold', label: '能垒阈值 (kcal/mol)', type: 'number', default: 40.0 },
        ],
      },
    },
  },
  wavefunction_analysis: {
    api: 'wavefunctionAnalysis',
    commands: {
      analyzeEsp: {
        label: 'ESP 分析', fullCmd: 'analyzeEspFull',
        fields: [
          { key: 'input_file', label: '波函数文件/SMILES', type: 'text', placeholder: 'SMILES 或文件路径', default: '' },
          { key: 'file_format', label: '文件格式', type: 'select', default: 'molden', options: [
            { value: 'molden', label: 'molden' }, { value: 'fchk', label: 'fchk' },
            { value: 'wfn', label: 'wfn' }, { value: 'wfx', label: 'wfx' },
          ] },
          { key: 'surface_type', label: 'ESP 表面类型', type: 'select', default: 'molecular', options: [
            { value: 'molecular', label: 'molecular' }, { value: 'vdw', label: 'vdw' }, { value: 'electron_density', label: 'electron_density' },
          ] },
          { key: 'bins', label: 'ESP 区间数', type: 'number', default: 100 },
          { key: 'generate_cubes', label: '生成 Cube 文件', type: 'select', default: true, options: [{ value: true, label: '是' }, { value: false, label: '否' }] },
        ],
      },
      analyzeOrbitals: {
        label: '轨道分析', fullCmd: 'analyzeOrbitalsFull',
        fields: [
          { key: 'input_file', label: '波函数文件/SMILES', type: 'text', placeholder: 'SMILES 或文件路径', default: '' },
          { key: 'file_format', label: '文件格式', type: 'select', default: 'molden', options: [
            { value: 'molden', label: 'molden' }, { value: 'fchk', label: 'fchk' },
            { value: 'wfn', label: 'wfn' }, { value: 'wfx', label: 'wfx' },
          ] },
          { key: 'below_homo', label: 'HOMO 以下轨道数', type: 'number', default: 3 },
          { key: 'above_lumo', label: 'LUMO 以上轨道数', type: 'number', default: 3 },
          { key: 'grid_quality', label: '网格质量', type: 'select', default: 'high', options: [
            { value: 'low', label: 'low' }, { value: 'medium', label: 'medium' }, { value: 'high', label: 'high' }, { value: 'very_high', label: 'very_high' },
          ] },
        ],
      },
      render: {
        label: '渲染', fullCmd: 'renderFull',
        fields: [
          { key: 'input_dir', label: 'Cube 文件目录路径', type: 'text', placeholder: '/path/to/cubes', default: '' },
          { key: 'render_type', label: '渲染类型', type: 'select', default: 'esp', options: [
            { value: 'esp', label: 'ESP' }, { value: 'orbital', label: '轨道' },
          ] },
          { key: 'image_format', label: '图片格式', type: 'select', default: 'png', options: [
            { value: 'png', label: 'PNG' }, { value: 'tiff', label: 'TIFF' }, { value: 'bmp', label: 'BMP' }, { value: 'jpg', label: 'JPG' }, { value: 'tga', label: 'TGA' },
          ] },
          { key: 'width', label: '渲染宽度 (px)', type: 'number', default: 1800 },
          { key: 'height', label: '渲染高度 (px)', type: 'number', default: 1200 },
        ],
      },
    },
  },
  fluid_simulation: {
    api: 'fluidSimulation',
    commands: {
      run: {
        label: '流体模拟', fullCmd: 'runFull',
        fields: [
          { key: 'solver', label: '求解器', type: 'select', default: 'ns2d', options: [
            { value: 'ns2d', label: 'ns2d' }, { value: 'ns3d', label: 'ns3d' },
            { value: 'ns2d_strat', label: 'ns2d_strat' }, { value: 'ns3d_strat', label: 'ns3d_strat' }, { value: 'sw1l', label: 'sw1l' },
          ] },
          { key: 'params', label: '模拟参数 (JSON)', type: 'textarea', placeholder: '{"grid": {...}, "physical": {...}}', default: '{}' },
          { key: 'initial_conditions', label: '初始条件 (JSON)', type: 'textarea', default: '{}' },
          { key: 'forcing', label: '强制力配置 (JSON，可选)', type: 'textarea', placeholder: 'null', default: 'null' },
          { key: 'output_config', label: '输出配置 (JSON，可选)', type: 'textarea', placeholder: 'null', default: 'null' },
        ],
      },
      resume: {
        label: '续跑模拟', fullCmd: null,
        fields: [
          { key: 'sim_dir', label: '已有模拟结果目录', type: 'text', placeholder: '/path/to/sim', default: '' },
          { key: 'extend_time', label: '延长模拟时间 (秒)', type: 'number', default: 1.0 },
        ],
      },
      analyze: {
        label: '结果分析', fullCmd: null,
        fields: [
          { key: 'sim_dir', label: '模拟结果目录', type: 'text', placeholder: '/path/to/sim', default: '' },
          { key: 'fields', label: '分析物理场', type: 'tags', placeholder: 'vorticity, velocity', default: ['vorticity', 'velocity'] },
          { key: 'compute_spectra', label: '计算能谱', type: 'select', default: true, options: [{ value: true, label: '是' }, { value: false, label: '否' }] },
        ],
      },
      sweep: {
        label: '参数扫描', fullCmd: null,
        fields: [
          { key: 'base_config', label: '基础配置 (JSON)', type: 'textarea', default: '{}' },
          { key: 'sweep_params', label: '扫描参数 (JSON)', type: 'textarea', placeholder: '{"grid": [32, 64]}', default: '{}' },
          { key: 'workers', label: '并行工作进程数', type: 'number', default: 1 },
        ],
      },
    },
  },
  molecular_docking: {
    api: 'molecularDocking',
    commands: {
      dock: {
        label: '单次对接', fullCmd: 'dockFull',
        fields: [
          { key: 'protein_path', label: '受体蛋白路径', type: 'text', placeholder: '如: /data/receptor.pdb', default: '' },
          { key: 'ligand', label: '配体', type: 'text', placeholder: 'SMILES 或文件路径', default: '' },
          { key: 'ligand_format', label: '配体格式', type: 'select', default: 'smiles', options: [
            { value: 'smiles', label: 'smiles' }, { value: 'sdf', label: 'sdf' }, { value: 'mol2', label: 'mol2' },
          ] },
          { key: 'samples_per_complex', label: '每复合物采样数', type: 'number', default: 10 },
          { key: 'inference_steps', label: '推理步数', type: 'number', default: 20 },
          { key: 'device', label: '推理设备', type: 'select', default: 'cpu', options: [
            { value: 'cpu', label: 'CPU' }, { value: 'cuda', label: 'CUDA' },
          ] },
        ],
      },
      batch: {
        label: '批量筛选', fullCmd: 'batchFull',
        fields: [
          { key: 'complexes', label: '复合物列表 (JSON)', type: 'textarea', placeholder: '[{"receptor_path":"...","ligand":"...","ligand_format":"smiles"}]', default: '[]' },
          { key: 'config', label: '全局配置 (JSON)', type: 'textarea', default: '{}' },
          { key: 'workers', label: '并行工作进程数', type: 'number', default: 1 },
        ],
      },
      analyze: {
        label: '结果分析', fullCmd: 'analyzeFull',
        fields: [
          { key: 'workdir', label: '对接结果工作目录', type: 'text', placeholder: '/path/to/results', default: '' },
          { key: 'top_n', label: '返回 Top-N 位姿', type: 'number', default: 20 },
          { key: 'confidence_threshold', label: '置信度过滤阈值', type: 'number', default: 0.0 },
        ],
      },
      export: {
        label: '结果导出', fullCmd: 'exportFull',
        fields: [
          { key: 'workdir', label: '对接结果工作目录', type: 'text', placeholder: '/path/to/results', default: '' },
          { key: 'format', label: '导出格式', type: 'select', default: 'sdf', options: [
            { value: 'sdf', label: 'SDF' }, { value: 'csv', label: 'CSV' }, { value: 'html', label: 'HTML' },
          ] },
        ],
      },
    },
  },
}

// 服务 ID → 显示信息映射，用于路由预选
const SERVICE_LOOKUP = {
  mpa: { id: 'mpa', capabilityId: 'mpa', name: '分子性质预测', description: '预测 42 种分子物化性质与不确定性' },
  chemical: { id: 'chemical', capabilityId: 'chem_properties', name: '化学性质查询', description: 'M1-M5 模块：常数、相平衡、闪蒸、溶解度' },
  structure: { id: 'structure', capabilityId: 'materials_structure', name: '材料结构生成', description: 'SMILES/Formula/CIF 互转与几何优化' },
  formulation: { id: 'formulation', capabilityId: 'formulation_packing', name: '配方与堆积', description: '配方比例优化与分子堆积结构生成' },
  molecular_simulation: { id: 'molecular_simulation', capabilityId: 'molecular_simulation', name: '分子动力学', description: 'OpenMM/LAMMPS 多系综 MD 模拟与轨迹分析' },
  battery_modeling: { id: 'battery_modeling', capabilityId: 'battery_modeling', name: '电池建模', description: 'PyBaMM P2D/ECM/PyBOP 多轨道仿真' },
  synthesis_planning: { id: 'synthesis_planning', capabilityId: 'synthesis_planning', name: '合成路线规划', description: 'RDKit 逆合成分析与文献验证' },
  process_modeling: { id: 'process_modeling', capabilityId: 'process_modeling', name: '化工过程建模', description: 'M1-M6 模块：精馏、反应器、传热传质' },
  reaction_network: { id: 'reaction_network', capabilityId: 'reaction_network', name: '反应网络分析', description: '反应枚举、过渡态搜索、网络扩展' },
  wavefunction_analysis: { id: 'wavefunction_analysis', capabilityId: 'wavefunction_analysis', name: '波函数分析', description: 'PySCF ESP/轨道分析与渲染' },
  fluid_simulation: { id: 'fluid_simulation', capabilityId: 'fluid_simulation', name: '流体模拟', description: 'FluidSim 求解器 NS 方程与参数扫描' },
  molecular_docking: { id: 'molecular_docking', capabilityId: 'molecular_docking', name: '分子对接', description: 'AutoDock Vina 单次/批量对接与位姿分析' },
}

// 当前选中服务的命令列表
const selectedCommand = ref('')
const currentCommands = computed(() => {
  if (!selectedService.value) return null
  const schema = SERVICE_FORMS[selectedService.value.id]
  return schema?.commands || null
})

const currentFields = computed(() => {
  if (!selectedService.value || !selectedCommand.value) return []
  const schema = SERVICE_FORMS[selectedService.value.id]
  return schema?.commands?.[selectedCommand.value]?.fields || []
})

// ── 服务选择与表单初始化 ────────────────────────────────────
function onSelectService (svc) {
  selectedService.value = svc
  const schema = SERVICE_FORMS[svc.id]
  const firstCmd = schema?.commands ? Object.keys(schema.commands)[0] : ''
  selectedCommand.value = firstCmd
  resetForm()
  loadServiceEnums(svc.id)
}

// 按需加载服务枚举与候选列表
function loadServiceEnums (serviceId) {
  if (serviceId === 'formulation' || serviceId === 'process_modeling') {
    loadCandidates()
  }
  if (serviceId === 'structure') {
    loadStructureFormats()
  }
  if (serviceId === 'molecular_simulation') {
    loadMdMetrics()
  }
  if (serviceId === 'process_modeling') {
    loadProcessModules()
  }
}

async function loadCandidates () {
  if (candidateOptions.value.length) return
  candidatesLoading.value = true
  try {
    const res = await listCandidates()
    const items = Array.isArray(res) ? res : (res?.items || res?.candidates || [])
    candidateOptions.value = items.map((c) => ({
      value: c.candidate_id || c.id || '',
      label: `${c.name || c.formula || c.candidate_id || '候选'}${c.smiles ? ' · ' + c.smiles : ''}`.slice(0, 64),
    })).filter((o) => o.value)
  } catch (e) {
    console.error('加载候选列表失败:', e)
  } finally {
    candidatesLoading.value = false
  }
}

async function loadStructureFormats () {
  if (structureFormats.value.length) return
  try {
    const res = await structure.listFormats()
    structureFormats.value = (res?.formats || []).map((f) => ({ value: f, label: f }))
  } catch (e) {
    console.error('加载结构格式失败:', e)
  }
}

async function loadMdMetrics () {
  if (mdMetrics.value.length) return
  try {
    const res = await molecularSimulation.listMetrics()
    mdMetrics.value = (res?.metrics || []).map((m) => ({ value: m.key, label: `${m.key} · ${m.description}` }))
  } catch (e) {
    console.error('加载 MD 指标失败:', e)
  }
}

async function loadProcessModules () {
  if (processModulesRaw.value.length) return
  try {
    const res = await processModeling.listModules()
    processModulesRaw.value = res?.modules || []
    // 用模块 key 作为下拉 value，name 作为展示
    const modField = SERVICE_FORMS.process_modeling.commands.calculate.fields.find((f) => f.key === 'module')
    if (modField) {
      modField.options = processModulesRaw.value.map((m) => ({ value: m.key, label: `${m.key} · ${m.name}` }))
    }
    syncProcessModuleState()
  } catch (e) {
    console.error('加载过程建模模块失败:', e)
  }
}

// 模块切换联动：刷新计算类型选项 + 预填参数模板
function syncProcessModuleState () {
  const module = formData.module
  const mod = processModulesRaw.value.find((m) => m.key === module)
  processCalcTypes.value = (mod?.calculation_types || []).map((ct) => ({ value: ct, label: ct }))
  if (!formData.calculation_type || !processCalcTypes.value.some((o) => o.value === formData.calculation_type)) {
    formData.calculation_type = processCalcTypes.value[0]?.value || ''
  }
  if (module) {
    formData.conditions = JSON.stringify(PM_CONDITIONS_TEMPLATE[module] || {}, null, 2)
    formData.parameters = JSON.stringify(PM_PARAMS_TEMPLATE[module] || {}, null, 2)
  }
}

// 通用 select 变化处理（目前仅 process_modeling.module 联动）
function onSelectChange (field) {
  if (field.key === 'module') {
    syncProcessModuleState()
  }
}

// 候选材料选中/点击加载：填充目标字段
async function onCandidateChange (field) {
  const cid = formData[field.key]
  if (!cid) {
    message.warning('请先选择候选材料')
    return
  }
  candidateCompLoading.value = true
  try {
    const res = await formulation.candidateComponents(cid)
    const comps = res?.components || []
    if (field.fillMode === 'smiles') {
      const smilesList = comps.map((c) => c.smiles || c.name).filter(Boolean)
      formData[field.targetKey] = [...new Set(smilesList)]
    } else {
      formData[field.targetKey] = comps.map((c) => ({
        name: c.name || '',
        smiles: c.smiles || '',
        ratio_range_min: c.ratio_range_min ?? 0,
        ratio_range_max: c.ratio_range_max ?? 1,
      }))
    }
    message.success(`已从候选材料加载 ${formData[field.targetKey].length} 个组分`)
  } catch (e) {
    console.error('加载候选成分失败:', e)
    message.error('加载候选成分失败，请确认候选材料信息完整')
  } finally {
    candidateCompLoading.value = false
  }
}

// 组分表格行操作
function addCompRow (key) {
  if (!Array.isArray(formData[key])) formData[key] = []
  formData[key].push({ name: '', smiles: '', ratio_range_min: 0, ratio_range_max: 1 })
}

function removeCompRow (key, idx) {
  if (Array.isArray(formData[key])) formData[key].splice(idx, 1)
}

// 动态枚举选项（structureFormats / mdMetrics）
function enumOptionsFor (field) {
  if (field.loadSource === 'structureFormats') return structureFormats.value
  if (field.loadSource === 'mdMetrics') return mdMetrics.value
  return field.options || []
}

// 联动下拉选项（process_modeling.calculation_type）
function dynamicOptionsFor (field) {
  if (field.key === 'calculation_type') return processCalcTypes.value
  return field.options || []
}

function onCommandChange () {
  resetForm()
}

function resetForm () {
  const schema = selectedService.value ? SERVICE_FORMS[selectedService.value.id] : null
  Object.keys(formData).forEach((k) => delete formData[k])
  if (schema && selectedCommand.value) {
    const cmdFields = schema.commands?.[selectedCommand.value]?.fields || []
    cmdFields.forEach((f) => {
      if (f.type === 'tags' || f.type === 'comp-table') {
        formData[f.key] = Array.isArray(f.default) ? f.default.map((x) => (typeof x === 'object' ? { ...x } : x)) : []
      } else {
        formData[f.key] = f.default
      }
    })
    // 恢复 process_modeling 联动初态
    if (selectedService.value.id === 'process_modeling' && processModulesRaw.value.length) {
      syncProcessModuleState()
    }
  }
}

// ── 执行服务 ────────────────────────────────────────────────
// 返回服务对应的智能体映射（智能体执行模式用）
function agentForService (serviceId) {
  return SERVICE_AGENT_MAP[serviceId] || null
}

async function executeService () {
  if (!selectedService.value) {
    message.warning('请先选择服务')
    return
  }
  if (!projectId.value.trim()) {
    message.warning('请输入项目 ID')
    return
  }
  const schema = SERVICE_FORMS[selectedService.value.id]
  if (!schema || !selectedCommand.value) return
  const cmdConfig = schema.commands[selectedCommand.value]

  // 组装参数：project_id + 表单字段，tags 类型转 list，textarea 尝试 JSON 解析
  const params = { project_id: projectId.value.trim() }
  cmdConfig.fields.forEach((f) => {
    // candidate-select 仅为 UI 辅助字段（数据已写入 targetKey），不传给后端
    if (f.type === 'candidate-select') return
    let val = formData[f.key]
    if (f.type === 'tags' && Array.isArray(val)) {
      val = val.filter((x) => x !== null && x !== undefined && String(x).trim() !== '')
    }
    if (f.type === 'comp-table' && Array.isArray(val)) {
      // 过滤完全空行
      val = val.filter((r) => r && (String(r.name || '').trim() || String(r.smiles || '').trim()))
    }
    if (f.type === 'textarea' && typeof val === 'string') {
      try {
        val = JSON.parse(val)
      } catch {
        // 非 JSON 字符串保留原值
      }
    }
    // 跳过 null 值的可选字段，由后端使用默认值
    if (val === null) return
    params[f.key] = val
  })

  executing.value = true
  try {
    // 智能体执行模式：通过 AgentProxy 调用（Agent → 工具 → 科学服务）
    if (execMode.value === 'agent') {
      const agentCfg = agentForService(selectedService.value.id)
      if (!agentCfg) {
        message.error(`服务 ${selectedService.value.name} 未配置智能体映射`)
        return
      }
      const res = await invokeAgentTool({
        agent_id: agentCfg.agent_id,
        capability: agentCfg.capability,
        params,
        activity_id: `sci.${selectedService.value.id}`,
      })
      if (!res.success) {
        message.error(`智能体调用失败：${res.error || '未知错误'}`)
        lastResult.value = {
          type: 'agent',
          data: [{ error: res.error || '调用失败' }],
          agentInfo: { agent_id: agentCfg.agent_id, tool_id: res.tool_id, used_fallback: res.used_fallback },
        }
        return
      }
      const artifacts = res.result?.artifacts || []
      lastResult.value = {
        type: 'agent',
        data: artifacts.length ? artifacts : [{ result: res.result }],
        runId: res.result?.run_id || res.invocation_id,
        agentInfo: { agent_id: agentCfg.agent_id, tool_id: res.tool_id, used_fallback: res.used_fallback },
      }
      message.success(`智能体 ${agentCfg.agent_id} 通过工具 ${res.tool_id} 执行完成，产生 ${artifacts.length} 个工件`)
      rightTab.value = 'runs'
      await refreshRuns()
      return
    }

    const apiNs = SERVICE_API_MAP[schema.api]
    const cmd = execMode.value === 'full' ? (cmdConfig.fullCmd || selectedCommand.value) : selectedCommand.value
    const fn = apiNs[cmd]
    if (!fn) {
      message.error(`服务 ${selectedService.value.name} 不支持命令 ${cmd}`)
      return
    }
    const result = await fn(params)
    const isEvidence = execMode.value === 'full' && cmdConfig.fullCmd
    lastResult.value = {
      type: isEvidence ? 'evidence' : 'artifact',
      data: Array.isArray(result) ? result : [result],
      runId: Array.isArray(result) ? result[0]?.run_id : result?.run_id,
    }
    message.success(`执行完成，产生 ${lastResult.value.data.length} 个${isEvidence ? '证据包' : '工件'}`)
    rightTab.value = isEvidence ? 'evidence' : 'runs'
    await refreshRuns()
  } catch (e) {
    console.error('Execute failed:', e)
  } finally {
    executing.value = false
  }
}

// ── 运行记录 ────────────────────────────────────────────────
async function refreshRuns () {
  refreshing.value = true
  try {
    const res = await listRuns({ limit: 50 })
    runs.value = Array.isArray(res) ? res : []
    lastRefresh.value = new Date()
  } catch (e) {
    console.error('Failed to load runs:', e)
  } finally {
    refreshing.value = false
  }
}

async function openRunDetail (runId) {
  selectedRunId.value = runId
  showRunDetail.value = true
  // 同时加载 artifact/evidence 到右侧面板
  try {
    const [arts, evs] = await Promise.all([
      getArtifacts(runId),
      getRunEvidence(runId),
    ])
    artifacts.value = arts || []
    evidenceList.value = evs || []
  } catch (e) {
    console.error('Failed to load run artifacts/evidence:', e)
  }
}

// ── 证据审批 ────────────────────────────────────────────────
function onEvidenceClick (ev) {
  selectedEvidence.value = ev
  showApproval.value = true
  approvalReviewer.value = ''
  approvalComment.value = ''
}

async function handleApprove () {
  if (!selectedEvidence.value) return
  approving.value = true
  try {
    const res = await requestApproval(selectedEvidence.value.evidence_id)
    const approvalId = res?.approval_id
    await approve(approvalId, approvalReviewer.value || 'system', approvalComment.value)
    message.success('审批已通过')
    showApproval.value = false
  } catch (e) {
    console.error('Approval failed:', e)
  } finally {
    approving.value = false
  }
}

async function handleReject () {
  if (!selectedEvidence.value) return
  approving.value = true
  try {
    const res = await requestApproval(selectedEvidence.value.evidence_id)
    const approvalId = res?.approval_id
    await reject(approvalId, approvalReviewer.value || 'system', approvalComment.value || '驳回')
    message.success('审批已驳回')
    showApproval.value = false
  } catch (e) {
    console.error('Rejection failed:', e)
  } finally {
    approving.value = false
  }
}

// ── 状态栏 ──────────────────────────────────────────────────
const queueDepth = computed(() => runs.value.filter((r) => r.status === 'queued').length)
const runningCount = computed(() => runs.value.filter((r) => ['preparing', 'running'].includes(r.status)).length)
const workerStatusClass = computed(() => (runningCount.value > 0 ? 'busy' : 'idle'))
const workerStatusLabel = computed(() => (runningCount.value > 0 ? `忙碌 (${runningCount.value})` : '空闲'))
const lastRefreshLabel = computed(() => (lastRefresh.value ? lastRefresh.value.toLocaleTimeString('zh-CN', { hour12: false }) : '—'))

function runBadge (s) {
  const map = { queued: 'default', preparing: 'processing', running: 'processing', succeeded: 'success', failed: 'error', cancelled: 'warning', cancelling: 'warning' }
  return map[s] || 'default'
}

function runStatusLabel (s) {
  const map = { queued: '排队', preparing: '准备', running: '运行', succeeded: '成功', failed: '失败', cancelled: '取消', cancelling: '取消中' }
  return map[s] || s
}

function formatTime (t) {
  if (!t) return '—'
  return new Date(t).toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ── 刷新与轮询 ──────────────────────────────────────────────
async function refreshAll () {
  await refreshRuns()
}

onMounted(() => {
  // 路由预选：从 ResearchWorkbench 跳转时携带 service 和 project_id 参数
  const serviceId = route.query.service
  if (serviceId && SERVICE_LOOKUP[serviceId]) {
    nextTick(() => {
      onSelectService(SERVICE_LOOKUP[serviceId])
    })
  }
  refreshRuns()
  // 每 15s 轮询运行状态（有运行中的任务时刷新更频繁由用户手动触发）
  pollTimer = setInterval(() => refreshRuns(), 15000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.scientific-workbench {
  display: grid;
  grid-template-rows: auto 1fr auto;
  height: 100%;
  min-height: 0;
  background: var(--light-bg);
}

/* 顶部标题栏 */
.wb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-sm) var(--space-lg);
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  gap: var(--space-md);
}
.wb-title {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.wb-title-text {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}
.wb-subtitle {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}
.wb-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex-shrink: 0;
}
.project-input {
  width: 140px;
}

/* 主体三栏 */
.wb-body {
  display: grid;
  grid-template-columns: 240px 1fr 360px;
  min-height: 0;
  gap: 1px;
  background: var(--border);
}

/* 面板通用 */
.wb-left,
.wb-middle,
.wb-right {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  min-height: 0;
  min-width: 0;
}
.panel-head {
  display: flex;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-card);
  flex-shrink: 0;
}
.panel-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-sm) var(--space-md);
  min-height: 0;
}
.right-scroll {
  padding: var(--space-xs) var(--space-sm);
}

/* 中间表单区 */
.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--space-sm);
}
.empty-icon {
  font-size: 40px;
  color: var(--border);
}
.empty-hint p {
  margin: 0;
  font-size: var(--font-size-md);
}
.service-form {
  margin-bottom: var(--space-md);
}
.candidate-select-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.candidate-select-row {
  display: flex;
  gap: 6px;
}
.candidate-hint {
  font-size: var(--font-size-xs);
  color: var(--primary);
}
.comp-table-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.comp-row {
  display: grid;
  grid-template-columns: 1fr 1.4fr 62px 62px 28px;
  gap: 4px;
  align-items: center;
}
.comp-name {
  min-width: 0;
}
.comp-smiles {
  min-width: 0;
}
.comp-range {
  width: 100%;
}
.form-actions {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}
.agent-mode-hint {
  font-size: 12px;
  color: var(--success-color, #52c41a);
  background: rgba(82, 196, 26, 0.06);
  border: 1px dashed var(--success-color, #52c41a);
  border-radius: var(--radius-md);
  padding: 6px 10px;
  margin-bottom: var(--space-md);
  word-break: break-all;
}
.agent-mode-hint code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}
.fallback-tag {
  color: #fa8c16;
  font-weight: 600;
}
.result-summary {
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-md);
  background: var(--primary-bg);
  padding: var(--space-sm) var(--space-md);
}
.result-summary-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.result-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--primary);
}
.result-meta {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin-top: var(--space-xs);
  font-family: 'SFMono-Regular', Consolas, monospace;
}

/* 右侧 tabs */
.right-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.right-tabs :deep(.ant-tabs-nav) {
  margin: 0;
  padding: 0 var(--space-sm);
  flex-shrink: 0;
}
.right-tabs :deep(.ant-tabs-content-holder) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.right-tabs :deep(.ant-tabs-content) {
  height: 100%;
}
.right-tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 运行记录列表 */
.run-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.run-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-xs) var(--space-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--bg-card);
}
.run-item:hover {
  border-color: var(--primary-border);
  background: var(--primary-bg);
}
.run-item.active {
  border-color: var(--primary);
  background: var(--primary-bg);
}
.run-item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-xs);
}
.run-svc {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  font-family: 'SFMono-Regular', Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-item-meta {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-top: 2px;
}
.run-item-meta code {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  font-family: 'SFMono-Regular', Consolas, monospace;
}
.run-cmd {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-item-time {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-top: 2px;
}

/* 工件紧凑列表 */
.artifact-compact-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.artifact-compact {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.artifact-compact:hover {
  border-color: var(--primary-border);
  background: var(--primary-bg);
}
.art-type {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
  color: var(--text-secondary);
  background: var(--light-bg-hover);
}
.art-type.type-result_table { color: var(--success); background: var(--success-bg); }
.art-type.type-structure { color: #7c3aed; background: rgba(124, 58, 237, 0.1); }
.art-type.type-report { color: var(--warning); background: var(--warning-bg); }
.art-type.type-plot { color: var(--primary); background: var(--primary-bg); }
.art-name {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 底部状态栏 */
.wb-footer {
  display: flex;
  align-items: center;
  gap: var(--space-xl);
  padding: var(--space-xs) var(--space-lg);
  background: var(--bg-card);
  border-top: 1px solid var(--border);
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
}
.status-item {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.idle {
  background: var(--success);
  box-shadow: 0 0 0 2px var(--success-bg);
}
.status-dot.busy {
  background: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-bg);
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.status-label {
  color: var(--text-muted);
}
.status-value {
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
  font-variant-numeric: tabular-nums;
}
.status-time {
  margin-left: auto;
}

/* 审批弹窗 */
.approval-form {
  margin-top: var(--space-md);
}
.approval-modal-hint {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  text-align: center;
  margin-top: var(--space-sm);
}
</style>
