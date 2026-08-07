<template>
  <div class="experiments">
    <div class="page-header">
      <div class="header-main">
        <div class="header-text">
          <h1 class="page-title">实验数据</h1>
          <p class="page-subtitle">查询、筛选与可视化湿实验测量记录</p>
          <p class="page-usage-hint">说明：数据来自 experiment_result_records 表；可按样品、批次、实验类型、来源、操作员等维度筛选</p>
        </div>
        <div class="header-actions">
          <a-button type="primary" @click="goToNewExperiment">
            <template #icon><PlusOutlined /></template>
            新建实验任务
          </a-button>
        </div>
      </div>
    </div>

    <!-- Filter -->
    <a-card class="filter-card" :bordered="false">
      <a-form layout="vertical" size="small" class="filter-form">
        <a-row :gutter="12" align="bottom">
          <a-col :span="5">
            <a-form-item label="样品编号">
              <a-auto-complete
                v-model:value="filterForm.sample_id"
                :options="sampleIdOptions"
                placeholder="输入或选择样品编号…"
                allow-clear
                autocomplete="off"
                :filter-option="fuzzyFilter"
              />
            </a-form-item>
          </a-col>
          <a-col :span="5">
            <a-form-item label="批次号">
              <a-auto-complete
                v-model:value="filterForm.batch_id"
                :options="batchIdOptions"
                placeholder="输入或选择批次号…"
                allow-clear
                autocomplete="off"
                :filter-option="fuzzyFilter"
              />
            </a-form-item>
          </a-col>
          <a-col :span="5">
            <a-form-item label="实验类型">
              <a-select
                v-model:value="filterForm.experiment_type"
                :options="typeOptions"
                placeholder="全部类型"
                show-search
                allow-clear
              />
            </a-form-item>
          </a-col>
          <a-col :span="5">
            <a-form-item label="候选材料">
              <a-auto-complete
                v-model:value="filterForm.formula"
                :options="formulaOptions"
                placeholder="输入或选择候选材料 ID…"
                allow-clear
                autocomplete="off"
                :filter-option="fuzzyFilter"
              />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item>
              <a-space style="width: 100%" wrap>
                <a-button type="primary" :loading="experimentsStore.loading" block @click="onQuery">
                  <SearchOutlined aria-hidden="true" /> 查询
                </a-button>
                <a-button block size="small" @click="onReset">
                  清空
                </a-button>
                <a-button block size="small" @click="showAdvanced = !showAdvanced">
                  <DownOutlined v-if="!showAdvanced" aria-hidden="true" />
                  <UpOutlined v-else aria-hidden="true" />
                  高级查询
                </a-button>
              </a-space>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row v-if="showAdvanced" :gutter="12" align="bottom" style="margin-top: 8px;">
          <a-col :span="5">
            <a-form-item label="数据来源">
              <a-select
                v-model:value="filterForm.source_type"
                :options="sourceOptions"
                placeholder="全部来源"
                show-search
                allow-clear
              />
            </a-form-item>
          </a-col>
          <a-col :span="5">
            <a-form-item label="操作员">
              <a-auto-complete
                v-model:value="filterForm.operator"
                :options="operatorOptions"
                placeholder="输入或选择操作员…"
                allow-clear
                autocomplete="off"
                :filter-option="fuzzyFilter"
              />
            </a-form-item>
          </a-col>
          <a-col :span="5">
            <a-form-item label="关联任务单">
              <a-auto-complete
                v-model:value="filterForm.order_id"
                :options="orderIdOptions"
                placeholder="输入或选择任务单号…"
                allow-clear
                autocomplete="off"
                :filter-option="fuzzyFilter"
              />
            </a-form-item>
          </a-col>
          <a-col :span="5">
            <a-form-item label="时间范围">
              <a-range-picker
                v-model:value="filterForm.dateRange"
                size="small"
                style="width: 100%"
                :placeholder="['开始时间', '结束时间']"
                show-time
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DDTHH:mm:ss"
              />
            </a-form-item>
          </a-col>
          <a-col :span="4"></a-col>
        </a-row>
      </a-form>
    </a-card>

    <!-- 内容 Tabs：实验记录 + 测量值分布 -->
    <a-tabs v-model:activeKey="activeTab" class="content-tabs" size="small">
      <a-tab-pane key="records" tab="实验记录">
        <a-card class="table-card" :bordered="false">
          <template #title>
            <div class="card-title-row">
              <span class="card-title-text">实验记录</span>
              <a-tag color="blue" class="count-tag">{{ experimentsStore.records.length }} 条</a-tag>
            </div>
          </template>
          <SmartLoading
            v-if="experimentsStore.loading && experimentsStore.records.length === 0"
            :loading="true"
            skeleton-type="table"
            tip="正在加载实验数据..."
            show-cancel
            @cancel="onCancelLoadExperiments"
          />
          <a-table
            v-else-if="experimentsStore.records.length > 0"
            :data-source="experimentsStore.records"
            :row-key="(r) => r.record_id || r.result_id || r.id"
            :loading="experimentsStore.loading"
            :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
            :columns="columns"
            size="small"
            :scroll="{ x: 1300, y: 520 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'measured_values'">
                <a-tag v-if="record.measured_values && Object.keys(record.measured_values).length" color="blue" class="value-tag">
                  <span v-for="(v, k) in record.measured_values" :key="k" class="value-entry">
                    {{ k }}: <span class="num">{{ formatNumber(v) }}</span>
                    <span v-if="record.units && record.units[k]" class="unit">{{ record.units[k] }}</span>
                  </span>
                </a-tag>
                <span v-else class="text-muted">-</span>
              </template>
              <template v-else-if="column.key === 'source'">
                <span>{{ sourceTypeLabel(record.source || record.source_type) }}</span>
              </template>
              <template v-else-if="column.key === 'timestamp'">
                <span class="num">{{ formatDateTime(record.timestamp) }}</span>
              </template>
              <template v-else-if="column.key === 'order_id'">
                <a-tooltip v-if="record.order_id" title="点击查看关联的闭环迭代任务">
                  <router-link :to="{ path: '/ecml', query: { run_id: record.order_id } }" class="trace-link">
                    {{ record.order_id }}
                  </router-link>
                </a-tooltip>
                <span v-else class="text-muted">-</span>
              </template>
              <template v-else-if="column.key === 'candidate_id'">
                <a-tooltip v-if="record.candidate_id" title="点击查看候选材料详情">
                  <router-link :to="{ path: '/workbench', query: { candidate_id: record.candidate_id } }" class="trace-link">
                    {{ record.candidate_id }}
                  </router-link>
                </a-tooltip>
                <span v-else class="text-muted">-</span>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="link" size="small" aria-label="查看实验记录详情" @click="onDetail(record)">
                  <EyeOutlined aria-hidden="true" /> 详情
                </a-button>
                <a-button type="link" size="small" aria-label="编辑实验记录" @click="onEdit(record)">编辑</a-button>
                <a-popconfirm
                  title="确认删除该实验记录？"
                  ok-text="删除"
                  cancel-text="取消"
                  @confirm="onDelete(record)"
                >
                  <a-button type="link" size="small" danger aria-label="删除实验记录">删除</a-button>
                </a-popconfirm>
              </template>
            </template>
          </a-table>
          <EmptyState v-else type="search" description="暂无实验数据，请调整筛选条件后查询" action-text="重置筛选" class="table-empty" @action="onReset" />
        </a-card>
      </a-tab-pane>
      <a-tab-pane key="chart" tab="测量值分布">
        <a-card class="chart-card" :bordered="false">
          <ResultChart
            v-if="facetChartData.length > 0"
            type="bar"
            :data="facetChartData"
            title="测量值分布"
            :height="facetChartHeight"
            :facet="true"
          />
          <EmptyState v-else type="data" description="暂无测量数据可用于分布可视化" class="chart-empty" />
        </a-card>
      </a-tab-pane>
    </a-tabs>

    <!-- 详情抽屉 -->
    <a-drawer
      :open="detailVisible"
      title="实验记录详情"
      placement="right"
      width="640px"
      @update:open="onDetailClose"
    >
      <a-descriptions v-if="detailRecord" :column="2" size="small" bordered>
        <a-descriptions-item label="样品编号">{{ detailRecord.sample_id || '-' }}</a-descriptions-item>
        <a-descriptions-item label="批次号">{{ detailRecord.batch_id || '-' }}</a-descriptions-item>
        <a-descriptions-item label="实验类型">{{ detailRecord.experiment_type || '-' }}</a-descriptions-item>
        <a-descriptions-item label="来源">{{ sourceTypeLabel(detailRecord.source || detailRecord.source_type) }}</a-descriptions-item>
        <a-descriptions-item label="操作员">{{ detailRecord.operator || '-' }}</a-descriptions-item>
        <a-descriptions-item label="时间">{{ formatDateTime(detailRecord.timestamp) }}</a-descriptions-item>
        <a-descriptions-item label="关联任务单">{{ detailRecord.order_id || '-' }}</a-descriptions-item>
        <a-descriptions-item label="候选材料">{{ detailRecord.candidate_id || detailRecord.formula || '-' }}</a-descriptions-item>
        <a-descriptions-item label="记录 ID" :span="2">{{ detailRecord.record_id || detailRecord.result_id || detailRecord.id || '-' }}</a-descriptions-item>
        <a-descriptions-item label="测量值" :span="2">
          <div v-if="detailRecord.measured_values && Object.keys(detailRecord.measured_values).length" class="detail-measured">
            <div v-for="(v, k) in detailRecord.measured_values" :key="k" class="detail-measured-row">
              <span class="detail-key">{{ k }}:</span>
              <span class="num">{{ formatNumber(v) }}</span>
              <span v-if="detailRecord.units && detailRecord.units[k]" class="unit">{{ detailRecord.units[k] }}</span>
            </div>
          </div>
          <span v-else class="text-muted">-</span>
        </a-descriptions-item>
      </a-descriptions>

      <!-- 来源追溯：从结果反查至项目 / 实验任务 / 样品 / 候选 / 设备 / QC -->
      <!-- 评测修复 P1-5：抽屉关闭动画期间 detailRecord 已置 null，必须加 v-if 防 空引用 -->
      <a-descriptions v-if="detailRecord" title="来源追溯" size="small" bordered :column="3" class="lineage-trace" style="margin-top: 16px">
        <a-descriptions-item label="所属项目">
          <a v-if="detailRecord.project_id" class="trace-link" @click="goToProject(detailRecord.project_id)">{{ detailRecord.project_id }}</a>
          <span v-else class="text-muted">-</span>
        </a-descriptions-item>
        <a-descriptions-item label="实验任务">
          <a v-if="detailRecord.order_id" class="trace-link" @click="goToOrder(detailRecord.order_id)">{{ detailRecord.order_id }}</a>
          <span v-else class="text-muted">-</span>
        </a-descriptions-item>
        <a-descriptions-item label="样品编号">
          <a v-if="detailRecord.sample_id" class="trace-link" @click="goToSample(detailRecord.sample_id)">{{ detailRecord.sample_id }}</a>
          <span v-else class="text-muted">-</span>
        </a-descriptions-item>
        <a-descriptions-item label="候选材料">
          <span v-if="detailRecord.candidate_id">{{ detailRecord.candidate_id }}</span>
          <span v-else class="text-muted">-</span>
        </a-descriptions-item>
        <a-descriptions-item label="测量设备">
          <span v-if="detailRecord.equipment_id">{{ detailRecord.equipment_id }}</span>
          <span v-else class="text-muted">-</span>
        </a-descriptions-item>
        <a-descriptions-item label="QC 状态">
          <StatusBadge :status="qcStatusToBadge(detailRecord.qc_status)" :label="qcStatusLabel(detailRecord.qc_status)" />
        </a-descriptions-item>
        <!-- 评测修复 P2-5：数据质量分层标记展示 -->
        <a-descriptions-item label="数据质量" :span="3">
          <a-tag :color="dataQualityColor(detailRecord.data_quality)">{{ dataQualityLabel(detailRecord.data_quality) }}</a-tag>
        </a-descriptions-item>
      </a-descriptions>
      <template #footer>
        <div style="display: flex; justify-content: flex-end">
          <a-button @click="onDetailClose(false)">关闭</a-button>
        </div>
      </template>
    </a-drawer>

    <!-- 编辑实验记录抽屉 -->
    <a-drawer
      :open="editModalVisible"
      title="编辑实验记录"
      placement="right"
      width="800px"
      @update:open="onEditDrawerClose"
    >
      <a-form class="compact-form" layout="vertical" size="small">
        <!-- 基本信息 -->
        <div class="form-group-label">基本信息</div>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="样品编号" required>
              <a-input v-model:value="editForm.sample_id" autocomplete="off" placeholder="如 S_20240726_001" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="批次号">
              <a-input v-model:value="editForm.batch_id" autocomplete="off" placeholder="如 B_001" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="实验类型">
              <a-select v-model:value="editForm.experiment_type" :options="typeOptions" allow-clear placeholder="选择类型" />
            </a-form-item>
          </a-col>
        </a-row>

        <!-- 测量值 -->
        <div class="form-group-label">测量值</div>
        <div class="measured-editor">
          <div v-if="editForm.measured_items.length > 0" class="measured-header">
            <span class="header-key">属性名</span>
            <span class="header-value">数值</span>
            <span class="header-unit">单位</span>
            <span class="header-action">操作</span>
          </div>
          <div v-for="(item, idx) in editForm.measured_items" :key="idx" class="measured-row">
            <a-input
              v-model:value="item.key"
              placeholder="属性名（如 ionic_conductivity）"
              class="measured-key"
              autocomplete="off"
              aria-label="属性名"
            />
            <a-input-number
              v-model:value="item.value"
              placeholder="数值"
              :step="0.0001"
              class="measured-value"
              style="width: 100%"
              inputmode="decimal"
              aria-label="数值"
            />
            <a-input
              v-model:value="item.unit"
              placeholder="单位"
              class="measured-unit"
              autocomplete="off"
              aria-label="单位"
            />
            <a-button type="text" danger size="small" aria-label="删除测量值" @click="removeMeasuredItem(idx)">
              <DeleteOutlined aria-hidden="true" />
            </a-button>
          </div>
          <EmptyState v-if="editForm.measured_items.length === 0" type="data" description="暂无测量值，点击下方按钮添加" class="measured-empty" />
          <a-button type="dashed" size="small" block @click="addMeasuredItem">
            <PlusOutlined aria-hidden="true" /> 添加测量值
          </a-button>
        </div>

        <!-- 溯源信息 -->
        <div class="form-group-label">溯源信息</div>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="来源">
              <a-select v-model:value="editForm.source" :options="sourceOptions" allow-clear placeholder="选择来源" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="操作员">
              <a-input v-model:value="editForm.operator" autocomplete="off" placeholder="操作人姓名" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="时间戳">
              <a-date-picker
                v-model:value="editForm.created_at"
                show-time
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DDTHH:mm:ss"
                placeholder="选择时间"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="关联任务单">
              <a-input v-model:value="editForm.order_id" autocomplete="off" placeholder="如 EXP_xxx" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="关联候选材料">
              <a-input v-model:value="editForm.candidate_id" autocomplete="off" placeholder="如 CAND_xxx" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-tooltip :title="editSubmitting ? '正在提交，请稍候' : ''">
            <span class="tt-btn-wrap">
              <a-button :disabled="editSubmitting" @click="onEditDrawerClose(false)">取消</a-button>
            </span>
          </a-tooltip>
          <a-button type="primary" :loading="editSubmitting" @click="onSaveEdit">保存</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import {
  SearchOutlined,
  PlusOutlined,
  DeleteOutlined,
  EyeOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useExperimentsStore } from '@/stores/experiments'
import {
  listExperimentTypes,
  updateExperiment,
  deleteExperiment,
} from '@/api/experiments'
import ResultChart from '@/components/ResultChart.vue'
import { useMdmDict } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'
import SmartLoading from '@/components/SmartLoading.vue'
import { sourceTypeLabel, sourceTypeOptions as ENUM_SOURCE_OPTIONS } from '@/utils/enumLabels'

const experimentsStore = useExperimentsStore()
const route = useRoute()
const router = useRouter()
const isMounted = ref(true)

// 新建实验任务：进入实验工作台并打开创建入口
function goToNewExperiment() {
  router.push('/experiment-workbench?create=1')
}

// 内容 Tab 与高级查询开关
const activeTab = ref('records')
const showAdvanced = ref(false)

// 详情抽屉
const detailVisible = ref(false)
const detailRecord = ref(null)

// 编辑表单
const editModalVisible = ref(false)
const editSubmitting = ref(false)
const editingId = ref('')
const editDirty = ref(false)
const emptyEditForm = () => ({
  sample_id: '',
  formula: '',
  batch_id: '',
  experiment_type: undefined,
  source: '',
  operator: '',
  order_id: '',
  candidate_id: '',
  created_at: null,
  measured_items: [],
})
const editForm = ref(emptyEditForm())

function addMeasuredItem() {
  editForm.value.measured_items.push({ key: '', value: null, unit: '' })
}
function removeMeasuredItem(idx) {
  editForm.value.measured_items.splice(idx, 1)
}

watch(
  () => editForm,
  () => {
    if (editModalVisible.value) editDirty.value = true
  },
  { deep: true }
)

const LAST_FORMULA_KEY = 'battery_experiments:last_formula'

const filterForm = reactive({
  sample_id: '',
  batch_id: '',
  experiment_type: undefined,
  source_type: undefined,
  operator: '',
  order_id: '',
  formula: '',
  dateRange: [],
})

// 模糊匹配选项：从已查询的记录中提取候选值
function buildFieldOptions(field) {
  const set = new Set()
  experimentsStore.records.forEach((r) => {
    const v = r[field]
    if (v) set.add(String(v))
  })
  return [...set].sort().map((v) => ({ value: v }))
}
const sampleIdOptions = computed(() => buildFieldOptions('sample_id'))
const batchIdOptions = computed(() => buildFieldOptions('batch_id'))
const operatorOptions = computed(() => buildFieldOptions('operator'))
const orderIdOptions = computed(() => buildFieldOptions('order_id'))
// 候选材料：合并 formula 与 candidate_id 字段
const formulaOptions = computed(() => {
  const set = new Set()
  experimentsStore.records.forEach((r) => {
    if (r.formula) set.add(String(r.formula))
    if (r.candidate_id) set.add(String(r.candidate_id))
  })
  return [...set].sort().map((v) => ({ value: v }))
})
function fuzzyFilter(input, option) {
  const v = String(option?.value ?? '')
  return v.toLowerCase().includes(String(input || '').toLowerCase())
}

const { dimensionOptions: mdmDimensionOptions } = useMdmDict()

// 数据来源选项：默认使用枚举中文化映射，onMounted 时尝试从 MDM 动态获取
const DEFAULT_SOURCE_OPTIONS = [
  ...ENUM_SOURCE_OPTIONS,
  { label: '手动录入', value: 'manual_entry' },
  { label: '设备导入', value: 'device_import' },
  { label: 'LIMS', value: 'lims' },
]
const sourceOptions = ref([...DEFAULT_SOURCE_OPTIONS])

// P2-5：实验类型选项默认硬编码兜底，onMounted 时尝试从 GET /experiments/types 动态获取
const DEFAULT_TYPE_OPTIONS = [
  { label: '离子电导率', value: 'ionic_conductivity' },
  { label: '电化学', value: 'electrochemical' },
  { label: 'XRD', value: 'xrd' },
  { label: 'SEM', value: 'sem' },
  { label: 'DSC', value: 'dsc' },
  { label: 'TGA', value: 'tga' },
  { label: 'EIS', value: 'eis' },
  { label: 'CV', value: 'cv' },
]
const typeOptions = ref([...DEFAULT_TYPE_OPTIONS])

async function fetchExperimentTypes() {
  // 数据来源选项仍从 MDM 主数据加载，失败时保留硬编码兜底
  try {
    const sourceOpts = await mdmDimensionOptions('data_source_type')
    if (sourceOpts.length > 0) {
      sourceOptions.value = sourceOpts
    } else {
      message.warning('数据来源选项未能从主数据加载，已使用本地兜底')
    }
  } catch (e) {
    console.warn('从 MDM 加载数据来源失败，使用硬编码兜底:', e)
    message.warning('数据来源选项未能从主数据加载，已使用本地兜底')
  }
  // 实验类型选项：优先 GET /experiments/types 动态获取；
  // 请求失败（含端点不存在 404）时保留硬编码选项，不报错
  try {
    const res = await listExperimentTypes()
    const types = Array.isArray(res?.types) ? res.types : []
    if (types.length > 0) {
      typeOptions.value = types.map((t) => ({ label: t.label ?? t.value, value: t.value }))
    }
  } catch {
    // 端点不存在或请求失败：静默保留 DEFAULT_TYPE_OPTIONS 兜底
  }
}

const columns = [
  { title: '样品编号', dataIndex: 'sample_id', key: 'sample_id', width: 130, ellipsis: true, className: 'id-col' },
  { title: '批次号', dataIndex: 'batch_id', key: 'batch_id', width: 110, ellipsis: true },
  { title: '实验类型', dataIndex: 'experiment_type', key: 'experiment_type', width: 120, ellipsis: true },
  { title: '测量值', key: 'measured_values', width: 200, ellipsis: true },
  { title: '来源', dataIndex: 'source', key: 'source', width: 110, ellipsis: true },
  { title: '操作员', dataIndex: 'operator', key: 'operator', width: 100, ellipsis: true },
  { title: '时间', key: 'timestamp', width: 160, className: 'tabular-nums' },
  { title: '关联任务', dataIndex: 'order_id', key: 'order_id', width: 130, ellipsis: true },
  { title: '候选材料', dataIndex: 'candidate_id', key: 'candidate_id', width: 130, ellipsis: true },
  { title: '操作', key: 'action', width: 220, fixed: 'right' },
]

const facetChartData = computed(() => {
  const records = experimentsStore.records
  if (records.length === 0) return []

  // 收集所有 measured_values 的键名
  const keySet = new Set()
  records.forEach((r) => {
    Object.keys(r.measured_values || {}).forEach((k) => keySet.add(k))
  })
  const keys = [...keySet].slice(0, 8)

  return keys
    .map((key) => ({
      name: key,
      values: records
        .map((r) => Number(r.measured_values?.[key]))
        .filter((v) => v != null && !Number.isNaN(v)),
    }))
    .filter((g) => g.values.length > 0)
})

const facetChartHeight = computed(() => {
  const n = facetChartData.value.length
  if (n === 0) return 260
  return Math.max(260, n * 100)
})

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function formatDateTime(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return dateFormatter.format(d)
}

function formatNumber(value) {
  if (value == null) return '-'
  if (typeof value !== 'number') return value
  if (value === 0) return '0'
  const abs = Math.abs(value)
  if (abs >= 10000 || abs < 0.001) return value.toExponential(2)
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

async function onQuery() {
  const params = {}
  if (filterForm.sample_id) params.sample_id = filterForm.sample_id
  if (filterForm.batch_id) params.batch_id = filterForm.batch_id
  if (filterForm.experiment_type) params.experiment_type = filterForm.experiment_type
  if (filterForm.source_type) params.source_type = filterForm.source_type
  if (filterForm.operator) params.operator = filterForm.operator
  if (filterForm.order_id) params.order_id = filterForm.order_id
  if (filterForm.formula) params.formula = filterForm.formula
  if (filterForm.dateRange && filterForm.dateRange.length === 2) {
    params.date_from = filterForm.dateRange[0]
    params.date_to = filterForm.dateRange[1]
  }
  await router.replace({ path: route.path, query: params })
  await experimentsStore.query(params)
}

// 取消等待实验数据加载（仅隐藏骨架屏，后端请求仍会完成并填充数据）
function onCancelLoadExperiments() {
  experimentsStore.loading = false
}

function onReset() {
  filterForm.sample_id = ''
  filterForm.batch_id = ''
  filterForm.experiment_type = undefined
  filterForm.source_type = undefined
  filterForm.operator = ''
  filterForm.order_id = ''
  filterForm.formula = ''
  filterForm.dateRange = []
  router.replace({ path: route.path, query: {} })
  onQuery()
}

function onEdit(record) {
  editingId.value = record.record_id || record.result_id || record.id || ''
  const measured = record.measured_values || {}
  const units = record.units || {}
  editForm.value = {
    sample_id: record.sample_id || '',
    formula: record.formula || '',
    batch_id: record.batch_id || '',
    experiment_type: record.experiment_type || undefined,
    source: record.source || '',
    operator: record.operator || '',
    order_id: record.order_id || '',
    candidate_id: record.candidate_id || '',
    created_at: record.timestamp ? dayjs(record.timestamp) : null,
    measured_items: Object.entries(measured).map(([k, v]) => ({ key: k, value: v, unit: units[k] || '' })),
  }
  editDirty.value = false
  editModalVisible.value = true
}

function onEditDrawerClose(v) {
  if (!v && editDirty.value) {
    const stay = window.confirm('有未保存的修改，确定要关闭吗？')
    if (!stay) return
  }
  editModalVisible.value = v
  if (!v) {
    editingId.value = ''
    editDirty.value = false
  }
}

async function onSaveEdit() {
  if (!editingId.value) {
    message.warning('未找到记录 ID')
    return
  }
  if (!editForm.value.sample_id?.trim()) {
    message.warning('请填写样品编号')
    return
  }
  // 将 measured_items 转回 measured_values 字典
  const measuredValues = {}
  const units = {}
  for (const item of editForm.value.measured_items) {
    const k = (item.key || '').trim()
    if (k && item.value != null && !Number.isNaN(item.value)) {
      measuredValues[k] = item.value
      if (item.unit) units[k] = item.unit
    }
  }
  const payload = {
    sample_id: editForm.value.sample_id,
    formula: editForm.value.formula,
    batch_id: editForm.value.batch_id,
    experiment_type: editForm.value.experiment_type,
    source: editForm.value.source,
    operator: editForm.value.operator,
    order_id: editForm.value.order_id,
    candidate_id: editForm.value.candidate_id,
    measured_values: measuredValues,
    units,
  }
  if (editForm.value.created_at) {
    payload.created_at = dayjs(editForm.value.created_at).toISOString()
  }
  editSubmitting.value = true
  try {
    await updateExperiment(editingId.value, payload)
    if (!isMounted.value) return
    message.success('实验记录已更新')
    editModalVisible.value = false
    editingId.value = ''
    editDirty.value = false
    await onQuery()
  } catch {
    // 错误由拦截器处理
  } finally {
    if (isMounted.value) {
      editSubmitting.value = false
    }
  }
}

async function onDelete(record) {
  const rid = record.record_id || record.result_id || record.id || ''
  if (!rid) {
    message.warning('未找到记录 ID，无法删除')
    return
  }
  try {
    await deleteExperiment(rid)
    if (!isMounted.value) return
    message.success('实验记录已删除')
    await onQuery()
  } catch {
    // 错误由拦截器处理
  }
}

function onDetail(record) {
  detailRecord.value = record
  detailVisible.value = true
}

function onDetailClose(v) {
  detailVisible.value = v
  if (!v) {
    detailRecord.value = null
  }
}

// 来源追溯：从实验结果反查至项目 / 实验任务 / 样品
function goToProject(id) { if (id) router.push(`/projects?project_id=${id}`) }
function goToOrder(id) { if (id) router.push(`/experiment-workbench?order_id=${id}`) }
function goToSample(id) { if (id) router.push(`/samples?sample_id=${id}`) }

// QC 状态展示（后端未返回 qc_status 时显示"未检"）
function qcStatusToBadge(status) {
  const map = { pass: 'success', fail: 'failed', pending: 'running', review: 'warning' }
  return map[status] || 'default'
}
function qcStatusLabel(status) {
  const map = { pass: '通过', fail: '失败', pending: '待检', review: '复核中' }
  return map[status] || status || '未检'
}

// 评测修复 P2-5：数据质量分层标记展示（verified 实测已审 / estimated 估算 / simulated 模拟 / literature 文献）
function dataQualityColor(quality) {
  const map = { verified: 'green', estimated: 'orange', simulated: 'blue', literature: 'purple' }
  return map[quality] || 'default'
}
function dataQualityLabel(quality) {
  const map = { verified: '实测已审', estimated: '估算', simulated: '模拟', literature: '文献' }
  return map[quality] || quality || '估算'
}

watch(
  () => filterForm.formula,
  (val) => {
    if (val) sessionStorage.setItem(LAST_FORMULA_KEY, val)
  }
)

onMounted(async () => {
  isMounted.value = true
  await fetchExperimentTypes()
  // 优先从 URL query 恢复
  if (route.query.sample_id) filterForm.sample_id = String(route.query.sample_id)
  if (route.query.batch_id) filterForm.batch_id = String(route.query.batch_id)
  if (route.query.experiment_type) filterForm.experiment_type = String(route.query.experiment_type)
  if (route.query.source_type) filterForm.source_type = String(route.query.source_type)
  if (route.query.operator) filterForm.operator = String(route.query.operator)
  if (route.query.order_id) filterForm.order_id = String(route.query.order_id)
  if (route.query.formula) {
    filterForm.formula = String(route.query.formula)
  } else if (route.query.smiles) {
    filterForm.formula = String(route.query.smiles)
  } else {
    // 无参数时从 sessionStorage 兜底恢复
    const saved = sessionStorage.getItem(LAST_FORMULA_KEY)
    if (saved) filterForm.formula = saved
  }
  if (route.query.date_from && route.query.date_to) {
    filterForm.dateRange = [dayjs(String(route.query.date_from)), dayjs(String(route.query.date_to))]
  }
  await onQuery()
})

onUnmounted(() => {
  isMounted.value = false
})
</script>

<style scoped>
.experiments {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.filter-card,
.table-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  margin-bottom: 12px;
}

.filter-card :deep(.ant-card-body) {
  padding: 12px 16px;
}

.filter-form :deep(.ant-form-item) {
  margin-bottom: 0;
}

.content-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 12px;
}

.chart-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.chart-empty {
  padding: 40px 0;
}

.detail-measured-row {
  line-height: 1.8;
}

.detail-measured-row .detail-key {
  color: var(--text-secondary);
  margin-right: 6px;
}

.detail-measured-row .num {
  font-variant-numeric: tabular-nums;
}

.detail-measured-row .unit {
  margin-left: 4px;
  opacity: 0.85;
}

.page-header {
  margin-bottom: 12px;
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.header-actions {
  flex-shrink: 0;
}

.card-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.card-title-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.count-tag {
  font-variant-numeric: tabular-nums;
}

.value-tag {
  max-width: 100%;
  white-space: normal;
  line-height: 1.6;
}

.value-tag .value-entry {
  display: inline-block;
  margin-right: 8px;
}

.value-tag .num {
  font-variant-numeric: tabular-nums;
}

.value-tag .unit {
  margin-left: 4px;
  opacity: 0.85;
}

.measured-editor {
  margin-bottom: 12px;
}

.measured-header {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  padding: 0 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.measured-header .header-key,
.measured-row .measured-key {
  flex: 1;
}

.measured-header .header-value,
.measured-row .measured-value {
  flex: 1;
}

.measured-header .header-unit,
.measured-row .measured-unit {
  width: 110px;
  flex-shrink: 0;
}

.measured-header .header-action {
  width: 32px;
  flex-shrink: 0;
  text-align: center;
}

.measured-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.measured-empty {
  margin: 8px 0;
}

.form-group-label {
  font-weight: 600;
  color: var(--text-primary);
  margin: 12px 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.form-group-label:first-child {
  margin-top: 0;
}

.text-muted {
  color: var(--text-secondary);
}

.trace-link {
  color: var(--primary-color);
}

/* P3-VIS-001：数据密集表格视觉层级优化 —— 时间列等宽显示 */
:deep(.tabular-nums) {
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 13px;
  color: var(--text-primary);
}

/* P2-4：关键 ID 列加粗 + 等宽字体 */
:deep(.id-col) {
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}
</style>
