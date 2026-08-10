<template>
  <div class="value-report">
    <div class="page-header">
      <h1 class="page-title">收益账单</h1>
      <p class="page-subtitle">统计研发投入与收益，按项目查看成本与价值产出</p>
    </div>
    <!-- 顶部工具栏 -->
    <div class="filter-bar">
      <a-space wrap>
        <a-select
          v-model:value="currentProjectId"
          placeholder="选择项目"
          show-search
          option-filter-prop="label"
          style="width: 280px"
          size="small"
          :loading="projectsLoading"
          :get-popup-container="(trigger) => trigger.parentNode"
          @change="onProjectChange"
        >
          <a-select-option
            v-for="(p, idx) in projects"
            :key="p.project_id || `proj-${idx}`"
            :value="p.project_id"
            :label="`${p.name || p.project_id}（${p.project_id}）`"
          >
            {{ p.name || p.project_id }}（{{ p.project_id }}）
          </a-select-option>
        </a-select>
        <DisabledButton
          size="small"
          :disabled="!currentProjectId"
          disabled-reason="请先选择项目"
          @click="openBaselineModal"
        >
          <SettingOutlined /> 基线设置
        </DisabledButton>
        <DisabledButton
          size="small"
          type="primary"
          :disabled="!currentProjectId"
          :loading="exporting"
          disabled-reason="请先选择项目"
          @click="exportMarkdown"
        >
          <DownloadOutlined /> 导出 Markdown
        </DisabledButton>
        <DisabledButton
          size="small"
          :disabled="!currentProjectId"
          :loading="loading"
          disabled-reason="请先选择项目"
          @click="fetchReport"
        >
          <ReloadOutlined /> 刷新
        </DisabledButton>
      </a-space>
    </div>

    <EmptyState
      v-if="!currentProjectId"
      type="search"
      description="请选择项目以查看研发收益账单"
    />

    <template v-else>
      <!-- 指标分组卡片 -->
      <div class="section-grid">
        <a-card
          v-for="sectionKey in sectionOrder"
          :key="sectionKey"
          size="small"
          :body-style="{ padding: '8px 12px' }"
          class="section-card"
        >
          <template #title>
            <span class="card-title">{{ report?.sections?.[sectionKey]?.title || sectionTitles[sectionKey] }}</span>
          </template>
          <div
            v-for="(metric, metricKey) in report?.sections?.[sectionKey]?.metrics || {}"
            :key="metricKey"
            class="metric-row"
          >
            <span class="metric-label">{{ metric.label }}</span>
            <span class="metric-value tabular-nums">
              {{ metric.value === null || metric.value === undefined ? '—' : metric.value }}
              <span v-if="metric.value !== null && metric.value !== undefined && metric.unit" class="metric-unit">{{ metric.unit }}</span>
            </span>
            <a-tooltip :title="metric.assumption" :disabled="!metric.assumption">
              <a-tag v-if="metric.kind === 'verified'" color="success" class="metric-tag">已验证</a-tag>
              <a-tag v-else color="orange" class="metric-tag metric-tag-outline">预估</a-tag>
            </a-tooltip>
          </div>
          <EmptyState v-if="!report" type="data" :description="MESSAGES.empty" />
        </a-card>
      </div>

      <!-- 假设与不确定性 -->
      <a-collapse class="assumption-panel" ghost>
        <a-collapse-panel key="assumptions" :header="`假设与不确定性（${report?.assumptions?.length || 0} 条）`">
          <ul v-if="report?.assumptions?.length" class="assumption-list">
            <li v-for="(item, idx) in report.assumptions" :key="idx">
              <span class="assumption-metric">{{ item.metric }}：</span>{{ item.assumption }}
            </li>
          </ul>
          <EmptyState v-else type="data" description="无预估类指标" />
        </a-collapse-panel>
      </a-collapse>

      <!-- 证据溯源（默认折叠，与"假设与不确定性"一致） -->
      <a-collapse class="assumption-panel" ghost>
        <a-collapse-panel key="evidence" :header="`证据溯源（${report?.evidence_refs?.length || 0} 条，点击复制）`">
          <a-space wrap v-if="report?.evidence_refs?.length">
            <a-tag
              v-for="ref in report.evidence_refs"
              :key="ref"
              class="evidence-tag"
              @click="copyText(ref)"
            >
              {{ ref }}
            </a-tag>
          </a-space>
          <EmptyState v-else type="data" description="暂无证据引用" />
        </a-collapse-panel>
      </a-collapse>

      <!-- 成本规则管理 -->
      <a-card size="small" :body-style="{ padding: '12px' }" class="cost-card">
        <template #title>
          <span class="card-title">成本规则</span>
        </template>
        <template #extra>
          <a-button size="small" type="primary" @click="openRuleModal()">
            <PlusOutlined /> 新增规则
          </a-button>
        </template>
        <a-table
          :columns="ruleColumns"
          :data-source="costRules"
          :pagination="false"
          size="small"
          row-key="rule_id"
          :loading="rulesLoading"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'category'">
              <a-tag>{{ categoryLabel(record.category) }}</a-tag>
            </template>
            <template v-if="column.key === 'unit_price'">
              <span class="tabular-nums">{{ record.unit_price }} {{ record.currency }}/{{ record.unit || '次' }}</span>
            </template>
            <template v-if="column.key === 'enabled'">
              <a-tag :color="record.enabled ? 'success' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag>
            </template>
            <template v-if="column.key === 'actions'">
              <a-space>
                <a-button size="small" type="link" @click="openRuleModal(record)">编辑</a-button>
                <a-popconfirm title="确认删除该成本规则？" @confirm="removeRule(record)">
                  <a-button size="small" type="link" danger>删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
          <template #emptyText>
            <EmptyState
              type="create"
              description="暂无成本规则"
              action-text="新增规则"
              :action-icon="PlusOutlined"
              @action="openRuleModal()"
            />
          </template>
        </a-table>
      </a-card>
    </template>

    <!-- 基线设置抽屉 -->
    <a-drawer
      :open="baselineModalVisible"
      title="基线设置"
      placement="right"
      width="480px"
      @update:open="(v) => (baselineModalVisible = v)"
    >
      <a-form layout="vertical">
        <a-form-item label="历史筛选周期（天）">
          <a-input-number v-model:value="baselineForm.historical_cycle_days" style="width: 100%" :min="0" />
        </a-form-item>
        <a-form-item label="典型实验成本（元/次）">
          <a-input-number v-model:value="baselineForm.typical_experiment_cost" style="width: 100%" :min="0" />
        </a-form-item>
        <a-form-item label="历史命中率（%）">
          <a-input-number v-model:value="baselineForm.historical_hit_rate_pct" style="width: 100%" :min="0" :max="100" />
        </a-form-item>
        <a-form-item label="历史候选数（个）">
          <a-input-number v-model:value="baselineForm.past_candidate_count" style="width: 100%" :min="0" :precision="0" />
        </a-form-item>
        <a-form-item label="成功标准">
          <a-textarea v-model:value="baselineForm.success_criteria" :rows="2" :placeholder="`如：离子电导率 ≥ 1e-3 ${condUnit}`" />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea v-model:value="baselineForm.notes" :rows="2" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="savingBaseline" @click="baselineModalVisible = false">取消</a-button>
          <a-button type="primary" :loading="savingBaseline" @click="saveBaselineForm">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 成本规则抽屉 -->
    <a-drawer
      :open="ruleModalVisible"
      :title="ruleForm.rule_id ? '编辑成本规则' : '新增成本规则'"
      placement="right"
      width="480px"
      @update:open="(v) => (ruleModalVisible = v)"
    >
      <a-form layout="vertical">
        <a-form-item label="规则名称" required>
          <a-input v-model:value="ruleForm.name" placeholder="如：单次湿实验综合成本" />
        </a-form-item>
        <a-form-item label="类别" required>
          <a-select v-model:value="ruleForm.category" :options="costCategoryOptions" />
        </a-form-item>
        <a-form-item label="单价（元）" required>
          <a-input-number v-model:value="ruleForm.unit_price" style="width: 100%" :min="0" />
        </a-form-item>
        <a-form-item label="计价单位">
          <a-input v-model:value="ruleForm.unit" placeholder="如：次 / 样 / 小时" />
        </a-form-item>
        <a-form-item label="启用">
          <a-switch v-model:checked="ruleForm.enabled" />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea v-model:value="ruleForm.notes" :rows="2" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="savingRule" @click="ruleModalVisible = false">取消</a-button>
          <a-button type="primary" :loading="savingRule" @click="saveRuleForm">保存</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  SettingOutlined,
  DownloadOutlined,
  ReloadOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import EmptyState from '@/components/EmptyState.vue'
import DisabledButton from '@/components/DisabledButton.vue'
import client from '@/api/client'
import {
  getBaseline,
  saveBaseline,
  getCostRules,
  createCostRule,
  updateCostRule,
  deleteCostRule,
  getValueReport,
  getValueReportMarkdown,
} from '@/api/valueReports'
import { useMdmDict, useUnitSymbols } from '@/utils/mdmDict'
import { MESSAGES } from '@/constants/glossary'

// 从 MDM 加载成本类别选项（失败时使用硬编码兜底）
const { dimensionOptions: mdmDimensionOptions } = useMdmDict()
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const condUnit = computed(() => unitSymbols.value.conductivity || 'S/cm')
const costCategoryOptions = ref([
  { label: '材料', value: 'material' },
  { label: '设备', value: 'equipment' },
  { label: '人工', value: 'labor' },
  { label: '外协', value: 'outsourced' },
  { label: '能源', value: 'energy' },
  { label: '废料处理', value: 'waste' },
])
function categoryLabel(code) {
  const found = costCategoryOptions.value.find(o => o.value === code)
  return found ? found.label : code
}

const sectionOrder = ['candidate_convergence', 'experiment_savings', 'cycle_efficiency', 'economic_value']
const sectionTitles = {
  candidate_convergence: '候选收敛',
  experiment_savings: '实验节省',
  cycle_efficiency: '周期效率',
  economic_value: '经济收益',
}

// --- State ---
const projects = ref([])
const projectsLoading = ref(false)
const currentProjectId = ref(undefined)
const report = ref(null)
const loading = ref(false)
const exporting = ref(false)
const costRules = ref([])
const rulesLoading = ref(false)
const baselineModalVisible = ref(false)
const savingBaseline = ref(false)
const ruleModalVisible = ref(false)
const savingRule = ref(false)
let isMounted = true
onUnmounted(() => { isMounted = false })

const baselineForm = reactive({
  historical_cycle_days: 0,
  typical_experiment_cost: 0,
  historical_hit_rate_pct: 0,
  success_criteria: '',
  past_candidate_count: 0,
  notes: '',
})

const ruleForm = reactive({
  rule_id: '',
  name: '',
  category: 'labor',
  unit_price: 0,
  unit: '次',
  currency: 'CNY',
  enabled: true,
  notes: '',
})

const ruleColumns = [
  { title: '规则 ID', dataIndex: 'rule_id', key: 'rule_id', width: 120, ellipsis: true },
  { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '类别', key: 'category', width: 90 },
  { title: '单价', key: 'unit_price', width: 130 },
  { title: '状态', key: 'enabled', width: 70 },
  { title: '备注', dataIndex: 'notes', key: 'notes', ellipsis: true },
  { title: '操作', key: 'actions', width: 120 },
]

// --- API ---
async function fetchProjects() {
  projectsLoading.value = true
  try {
    const list = await client.get('/projects')
    if (!isMounted) return
    projects.value = list || []
  } catch {
    if (isMounted) projects.value = []
  } finally {
    if (isMounted) projectsLoading.value = false
  }
}

async function fetchReport() {
  if (!currentProjectId.value) return
  loading.value = true
  try {
    const data = await getValueReport(currentProjectId.value)
    if (!isMounted) return
    report.value = data
  } catch {
    if (isMounted) report.value = null
  } finally {
    if (isMounted) loading.value = false
  }
}

async function fetchCostRules() {
  rulesLoading.value = true
  try {
    const list = await getCostRules()
    if (!isMounted) return
    costRules.value = list || []
  } catch {
    if (isMounted) costRules.value = []
  } finally {
    if (isMounted) rulesLoading.value = false
  }
}

function onProjectChange() {
  report.value = null
  fetchReport()
}

// --- 基线 ---
async function openBaselineModal() {
  try {
    const b = await getBaseline(currentProjectId.value)
    baselineForm.historical_cycle_days = b.historical_cycle_days || 0
    baselineForm.typical_experiment_cost = b.typical_experiment_cost || 0
    baselineForm.historical_hit_rate_pct = Math.round((b.historical_hit_rate || 0) * 10000) / 100
    baselineForm.success_criteria = b.success_criteria || ''
    baselineForm.past_candidate_count = b.past_candidate_count || 0
    baselineForm.notes = b.notes || ''
  } catch {
    baselineForm.historical_cycle_days = 0
    baselineForm.typical_experiment_cost = 0
    baselineForm.historical_hit_rate_pct = 0
    baselineForm.success_criteria = ''
    baselineForm.past_candidate_count = 0
    baselineForm.notes = ''
  }
  baselineModalVisible.value = true
}

async function saveBaselineForm() {
  savingBaseline.value = true
  try {
    await saveBaseline(currentProjectId.value, {
      project_id: currentProjectId.value,
      historical_cycle_days: baselineForm.historical_cycle_days || 0,
      typical_experiment_cost: baselineForm.typical_experiment_cost || 0,
      historical_hit_rate: (baselineForm.historical_hit_rate_pct || 0) / 100,
      success_criteria: baselineForm.success_criteria || '',
      past_candidate_count: baselineForm.past_candidate_count || 0,
      notes: baselineForm.notes || '',
    })
    if (!isMounted) return
    message.success('基线已保存')
    baselineModalVisible.value = false
    await fetchReport()
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) savingBaseline.value = false
  }
}

// --- 导出 ---
async function exportMarkdown() {
  exporting.value = true
  try {
    const md = await getValueReportMarkdown(currentProjectId.value)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `value-report-${currentProjectId.value}.md`
    a.click()
    URL.revokeObjectURL(url)
    message.success('Markdown 已导出')
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) exporting.value = false
  }
}

// --- 成本规则 ---
function openRuleModal(record) {
  if (record) {
    ruleForm.rule_id = record.rule_id
    ruleForm.name = record.name
    ruleForm.category = record.category
    ruleForm.unit_price = record.unit_price
    ruleForm.unit = record.unit || '次'
    ruleForm.currency = record.currency || 'CNY'
    ruleForm.enabled = record.enabled
    ruleForm.notes = record.notes || ''
  } else {
    ruleForm.rule_id = ''
    ruleForm.name = ''
    ruleForm.category = 'labor'
    ruleForm.unit_price = 0
    ruleForm.unit = '次'
    ruleForm.currency = 'CNY'
    ruleForm.enabled = true
    ruleForm.notes = ''
  }
  ruleModalVisible.value = true
}

async function saveRuleForm() {
  if (!ruleForm.name) {
    message.warning('请填写规则名称')
    return
  }
  savingRule.value = true
  const payload = {
    rule_id: ruleForm.rule_id,
    name: ruleForm.name,
    category: ruleForm.category,
    unit_price: ruleForm.unit_price || 0,
    unit: ruleForm.unit || '',
    currency: ruleForm.currency || 'CNY',
    enabled: ruleForm.enabled,
    notes: ruleForm.notes || '',
  }
  try {
    if (ruleForm.rule_id) {
      await updateCostRule(ruleForm.rule_id, payload)
    } else {
      await createCostRule(payload)
    }
    if (!isMounted) return
    message.success('成本规则已保存')
    ruleModalVisible.value = false
    await fetchCostRules()
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) savingRule.value = false
  }
}

async function removeRule(record) {
  try {
    await deleteCostRule(record.rule_id)
    if (!isMounted) return
    message.success('已删除')
    await fetchCostRules()
  } catch {
    // handled by interceptor
  }
}

// --- 工具 ---
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制')
  } catch {
    message.warning('复制失败')
  }
}

// --- Lifecycle ---
onMounted(async () => {
  fetchProjects()
  fetchCostRules()
  loadUnitSymbols()
  // 从 MDM 加载成本类别选项（失败时保留硬编码兜底）
  try {
    const opts = await mdmDimensionOptions('cost_category')
    if (opts.length) costCategoryOptions.value = opts
  } catch (e) {
    console.warn('从 MDM 加载成本类别失败，使用硬编码兜底:', e)
    message.warning('成本类别未能从主数据加载，已使用本地兜底')
  }
})
</script>

<style scoped>
.value-report {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

.filter-bar {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px 16px;
  margin-bottom: 16px;
}

.section-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

.metric-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--border);
}

.metric-row:last-child {
  border-bottom: none;
}

.metric-label {
  flex: 1;
  font-size: 12px;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 13px;
  font-weight: 600;
}

.metric-unit {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-secondary);
  margin-left: 2px;
}

.metric-tag {
  margin-right: 0;
  font-size: 11px;
}

.metric-tag-outline {
  background: transparent;
}

.assumption-panel {
  margin-bottom: 16px;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

.assumption-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--text-secondary);
}

.assumption-list li {
  margin-bottom: 4px;
}

.assumption-metric {
  font-weight: 600;
  color: var(--text-primary);
}

.evidence-card {
  margin-bottom: 16px;
}

.evidence-tag {
  cursor: pointer;
  font-size: 11px;
}

.cost-card {
  margin-bottom: 16px;
}

.tabular-nums {
  font-variant-numeric: tabular-nums;
}
</style>
