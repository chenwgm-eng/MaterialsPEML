<template>
  <div class="sample-manager">
    <div class="page-header">
      <h1 class="page-title">样品管理</h1>
      <p class="page-subtitle">实验室样品全生命周期管理 — 从创建到入库、使用、消耗的完整追踪</p>
    </div>

    <!-- 汇总卡片 -->
    <div class="stat-row" v-if="samples.length > 0">
      <div class="stat-item">
        <span class="stat-value">{{ samples.length }}</span>
        <span class="stat-label">样品总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ statusCount('in_storage') }}</span>
        <span class="stat-label">库存中</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ statusCount('in_use') }}</span>
        <span class="stat-label">使用中</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ statusCount('consumed') }}</span>
        <span class="stat-label">已消耗</span>
      </div>
    </div>

    <!-- 样品表格 -->
    <a-card class="table-card" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">样品清单</span>
          <a-tag color="blue" class="count-tag">{{ samples.length }} 条</a-tag>
        </div>
      </template>
      <template #extra>
        <a-space>
          <a-checkbox v-model:checked="showDemo" @change="fetchSamples">显示演示数据</a-checkbox>
          <a-button type="primary" size="small" @click="onAdd">
            <PlusOutlined /> 新建样品
          </a-button>
        </a-space>
      </template>
      <div class="search-row">
        <a-input-search
          v-model:value="searchText"
          placeholder="按样品名称或化学式搜索"
          allow-clear
          style="max-width: 240px"
        />
        <a-select
          v-model:value="filterSourceType"
          :options="sourceTypeOptions"
          placeholder="全部来源"
          allow-clear
          style="width: 140px"
          aria-label="来源筛选"
        />
        <a-select
          v-model:value="filterStatus"
          :options="statusOptions"
          placeholder="全部状态"
          allow-clear
          style="width: 140px"
          aria-label="状态筛选"
        />
      </div>
      <a-table
        v-if="samples.length > 0 || loading"
        :data-source="filteredSamples"
        :loading="loading"
        :pagination="{ pageSize: 10, showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'] }"
        :columns="columns"
        size="middle"
        :row-key="(r) => r.sample_id"
        :row-class-name="(record) => record.status === 'discarded' ? 'discarded-row' : ''"
        :scroll="{ x: 1300 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'sample_id'">
            <span class="sample-id">{{ record.sample_id }}</span>
            <a-tag v-if="record.is_demo" color="orange" size="small" style="margin-left: 4px">演示</a-tag>
          </template>
          <template v-else-if="column.key === 'source_type'">
            <a-tag :color="sourceTypeColor(record.source_type)">{{ sourceTypeLabel(record.source_type) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <StatusBadge :status="sampleStatusToBadge(record.status)" :label="statusLabel(record.status)" />
          </template>
          <template v-else-if="column.key === 'quantity'">
            <span v-if="record.quantity" class="num">{{ record.quantity }} {{ record.unit }}</span>
            <span v-else class="text-muted">未称量</span>
          </template>
          <template v-else-if="column.key === 'storage_condition'">
            <a-tag v-if="isCorrupted(record.storage_condition)" color="warning">数据已损坏</a-tag>
            <span v-else>{{ record.storage_condition || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'created_at'">
            <span class="time-text">{{ formatTime(record.created_at) }}</span>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="onDetail(record)">详情</a-button>
              <a-button type="link" size="small" @click="onEdit(record)">编辑</a-button>
              <a-button type="link" size="small" @click="onTransfer(record)">流转</a-button>
              <a-popconfirm
                title="确认删除该样品？"
                description="已有流转记录的样品将被拒绝删除"
                ok-text="删除"
                cancel-text="取消"
                @confirm="onDelete(record)"
              >
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
      <div v-else class="empty-state">
        <EmptyState type="create" description="暂无样品数据" action-text="新建样品" @action="onAdd" />
      </div>
    </a-card>

    <!-- 新建/编辑样品抽屉 -->
    <a-drawer
      :open="formModalVisible"
      :title="editingId ? '编辑样品' : '新建样品'"
      placement="right"
      width="720px"
      @update:open="(v) => (formModalVisible = v)"
    >
      <a-form ref="formRef" class="compact-form" layout="vertical" size="small" :model="form" :rules="formRules">
        <div class="form-group-label">基本信息</div>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="样品名称" name="name">
              <a-input v-model:value="form.name" name="name" autocomplete="off" placeholder="如 LiNiO₂ 正极粉料…" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="化学式">
              <a-input v-model:value="form.chemical_formula" name="chemical_formula" placeholder="如 Li6PS5Cl…" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
        </a-row>
        <div class="form-group-label">规格信息</div>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="数量" name="quantity">
              <a-input-number v-model:value="form.quantity" name="quantity" :min="0" :step="0.1" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="单位" name="unit">
              <a-select v-model:value="form.unit" name="unit" :options="unitOptions" :loading="optionsLoading" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="业务编号">
              <a-input v-model:value="form.sample_code" name="sample_code" placeholder="自定义，唯一（可选）…" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
        </a-row>
        <div class="form-group-label">来源信息</div>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="来源类型">
              <a-select v-model:value="form.source_type" name="source_type" :options="sourceTypeOptions" :loading="optionsLoading" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="批次号">
              <a-input v-model:value="form.batch_number" name="batch_number" placeholder="如 B2024-001…" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="关联候选材料">
              <a-select
                v-model:value="form.source_candidate_id"
                show-search
                allow-clear
                placeholder="选择候选材料"
                :options="candidateOptions"
                :filter-option="filterSelectOption"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="关联实验任务">
              <a-select
                v-model:value="form.source_order_id"
                show-search
                allow-clear
                placeholder="选择实验任务"
                :options="orderOptions"
                :filter-option="filterSelectOption"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="存储位置">
              <a-input v-model:value="form.storage_location" name="storage_location" autocomplete="off" placeholder="如 A-01-03…" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="存储条件">
              <a-select v-model:value="form.storage_condition" name="storage_condition" :options="conditionOptions" :loading="optionsLoading" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="备注">
              <a-textarea v-model:value="form.notes" name="notes" :rows="2" placeholder="备注信息…" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-tooltip :title="formSubmitting ? '正在提交，请稍候' : ''">
            <span>
              <a-button :disabled="formSubmitting" @click="formModalVisible = false">取消</a-button>
            </span>
          </a-tooltip>
          <a-button type="primary" :loading="formSubmitting" @click="onSubmitForm">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 流转抽屉 -->
    <a-drawer
      :open="transferModalVisible"
      :title="`样品流转: ${transferForm.sample_id || ''}`"
      placement="right"
      width="560px"
      @update:open="(v) => (transferModalVisible = v)"
    >
      <a-form class="compact-form" layout="vertical" size="small">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="当前状态">
              <StatusBadge :status="sampleStatusToBadge(transferForm.current_status)" :label="statusLabel(transferForm.current_status)" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="当前位置">
              <span>{{ transferForm.current_location || '-' }}</span>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="目标状态" required>
              <a-select v-model:value="transferForm.to_status" name="to_status" :options="statusOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="目标位置">
              <a-input v-model:value="transferForm.to_location" name="to_location" autocomplete="off" placeholder="新位置（可选）…" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="操作人">
              <a-input v-model:value="transferForm.transferred_by" name="transferred_by" autocomplete="name" placeholder="操作人姓名…" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="备注">
              <a-textarea v-model:value="transferForm.notes" name="notes" :rows="2" placeholder="流转备注…" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-tooltip :title="transferSubmitting ? '正在提交，请稍候' : ''">
            <span>
              <a-button :disabled="transferSubmitting" @click="transferModalVisible = false">取消</a-button>
            </span>
          </a-tooltip>
          <a-button type="primary" :loading="transferSubmitting" @click="onSubmitTransfer">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 详情抽屉 -->
    <a-drawer
      :open="detailModalVisible"
      :title="`样品详情: ${detailSample?.sample_id || ''}`"
      placement="right"
      width="720px"
      :footer="null"
      @update:open="(v) => (detailModalVisible = v)"
    >
      <template v-if="detailSample">
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="样品编号">{{ detailSample.sample_id }}</a-descriptions-item>
          <a-descriptions-item label="业务编号">{{ detailSample.sample_code || '-' }}</a-descriptions-item>
          <a-descriptions-item label="名称">{{ detailSample.name }}</a-descriptions-item>
          <a-descriptions-item label="化学式"><ChemicalFormula v-if="detailSample.chemical_formula" :formula="detailSample.chemical_formula" size="small" /><span v-else>-</span></a-descriptions-item>
          <a-descriptions-item label="来源类型">
            <a-tag :color="sourceTypeColor(detailSample.source_type)">{{ sourceTypeLabel(detailSample.source_type) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="状态">
            <StatusBadge :status="sampleStatusToBadge(detailSample.status)" :label="statusLabel(detailSample.status)" />
          </a-descriptions-item>
          <a-descriptions-item label="批次号">{{ detailSample.batch_number || '-' }}</a-descriptions-item>
          <a-descriptions-item label="数量">{{ detailSample.quantity }} {{ detailSample.unit }}</a-descriptions-item>
          <a-descriptions-item label="存储位置">{{ detailSample.storage_location || '-' }}</a-descriptions-item>
          <a-descriptions-item label="存储条件">{{ detailSample.storage_condition || '-' }}</a-descriptions-item>
          <a-descriptions-item label="关联实验任务">{{ detailSample.source_order_id || '-' }}</a-descriptions-item>
          <a-descriptions-item label="关联候选材料">{{ detailSample.source_candidate_id || '-' }}</a-descriptions-item>
          <a-descriptions-item label="创建时间">{{ formatTime(detailSample.created_at) }}</a-descriptions-item>
          <a-descriptions-item label="更新时间">{{ formatTime(detailSample.updated_at) }}</a-descriptions-item>
          <a-descriptions-item label="备注" :span="2">{{ detailSample.notes || '-' }}</a-descriptions-item>
        </a-descriptions>

        <!-- 来源追溯：从样品反查至项目 / 实验任务 / 候选材料 / 设备 -->
        <a-descriptions title="来源追溯" size="small" bordered :column="3" class="lineage-trace" style="margin-top: 16px">
          <a-descriptions-item label="所属项目">
            <a v-if="detailSample.project_id || detailSample.scenario_id" class="trace-link" @click="goToProject(detailSample.project_id || detailSample.scenario_id)">{{ detailSample.project_id || detailSample.scenario_id }}</a>
            <span v-else>-</span>
          </a-descriptions-item>
          <a-descriptions-item label="实验任务">
            <a v-if="detailSample.source_order_id" class="trace-link" @click="goToOrder(detailSample.source_order_id)">{{ detailSample.source_order_id }}</a>
            <span v-else>-</span>
          </a-descriptions-item>
          <a-descriptions-item label="候选材料">
            <a v-if="detailSample.source_candidate_id" class="trace-link" @click="goToCandidate(detailSample.source_candidate_id)">{{ detailSample.source_candidate_id }}</a>
            <span v-else>-</span>
          </a-descriptions-item>
          <a-descriptions-item label="关联设备" :span="3">
            <span v-if="detailSample.equipment_id">{{ detailSample.equipment_id }}</span>
            <span v-else>-</span>
          </a-descriptions-item>
        </a-descriptions>

        <!-- 相关知识：从知识库中检索与该样品相关的文献和主张 -->
        <MaterialKnowledgeCard
          v-if="detailSample && (detailSample.chemical_formula || detailSample.name)"
          :query="detailSample.chemical_formula || detailSample.name"
          :limit="5"
          style="margin-top: 16px"
        />

        <a-divider orientation="left" style="margin-top: 20px">流转记录</a-divider>
        <a-table
          :data-source="transfers"
          :loading="transfersLoading"
          :pagination="false"
          :columns="transferColumns"
          size="small"
          row-key="transfer_id"
          v-if="transfers.length > 0"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'from_status'">
              <StatusBadge :status="sampleStatusToBadge(record.from_status)" :label="statusLabel(record.from_status)" />
            </template>
            <template v-else-if="column.key === 'to_status'">
              <StatusBadge :status="sampleStatusToBadge(record.to_status)" :label="statusLabel(record.to_status)" />
            </template>
            <template v-else-if="column.key === 'transferred_at'">
              <span class="time-text">{{ formatTime(record.transferred_at) }}</span>
            </template>
          </template>
        </a-table>
        <div v-else-if="!transfersLoading" class="empty-transfers">暂无流转记录</div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { h, ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PlusOutlined } from '@ant-design/icons-vue'
import { listSamples, createSample, updateSample, deleteSample, transferSample, listSampleTransfers } from '@/api/samples'
import { listCandidates } from '@/api/candidates'
import { listExperimentOrders } from '@/api/experiments'
import MaterialKnowledgeCard from '@/components/MaterialKnowledgeCard.vue'
import { useMdmDict } from '@/utils/mdmDict'
import { message, Tag } from 'ant-design-vue'
import EmptyState from '@/components/EmptyState.vue'

const { statusOptions: mdmStatusOptions, unitOptions: mdmUnitOptions, dimensionOptions: mdmDimensionOptions, sampleTypeOptions: mdmSampleTypeOptions } = useMdmDict()

const route = useRoute()
const router = useRouter()
const samples = ref([])
const loading = ref(false)
const searchText = ref('')
const filterSourceType = ref(undefined)
const filterStatus = ref(undefined)
const showDemo = ref(false)
const scenarioId = ref('')

// P0-3 乱码检测：字段值全为 `?` 或包含 3+ 连续 `?` 视为数据已损坏
const CORRUPTION_RE = /^\?+$|\?{3,}/
function isCorrupted(value) {
  return typeof value === 'string' && CORRUPTION_RE.test(value)
}
function renderTextOrCorrupted(text) {
  if (isCorrupted(text)) {
    return h(Tag, { color: 'warning' }, () => '数据已损坏')
  }
  return text || '-'
}

const filteredSamples = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  return samples.value.filter((s) => {
    const matchKw = !kw ||
      (s.name || '').toLowerCase().includes(kw) ||
      (s.chemical_formula || '').toLowerCase().includes(kw)
    const matchSource = !filterSourceType.value || s.source_type === filterSourceType.value
    const matchStatus = !filterStatus.value || s.status === filterStatus.value
    return matchKw && matchSource && matchStatus
  })
})

// 新建/编辑表单
const formModalVisible = ref(false)
const formSubmitting = ref(false)
const formRef = ref()
const editingId = ref('')
// P1-FORM-001：前端表单校验规则
const formRules = {
  name: [
    { required: true, message: '请输入样品名称', trigger: 'blur' },
    { min: 3, max: 100, message: '样品名称长度需在 3-100 个字符之间', trigger: 'blur' },
  ],
  quantity: [
    { required: true, message: '请输入数量', type: 'number', trigger: 'blur' },
    {
      validator: (_rule, value) => {
        if (value === null || value === undefined || value === '') return Promise.resolve()
        const num = Number(value)
        if (Number.isNaN(num)) return Promise.reject('请输入有效数值')
        if (num < 0) return Promise.reject('数量不能为负数')
        return Promise.resolve()
      },
      trigger: 'blur',
    },
  ],
  unit: [{ required: true, message: '请选择单位', trigger: 'change' }],
}
const emptyForm = () => ({
  name: '',
  source_type: 'synthesis',
  source_order_id: '',
  source_candidate_id: '',
  batch_number: '',
  quantity: 0,
  unit: 'g',
  storage_location: '',
  storage_condition: '',
  notes: '',
  sample_code: '',
  chemical_formula: '',
  scenario_id: '',
})
const form = ref(emptyForm())

// 流转表单
const transferModalVisible = ref(false)
const transferSubmitting = ref(false)
const emptyTransfer = () => ({
  sample_id: '',
  current_status: '',
  current_location: '',
  to_status: '',
  to_location: '',
  transferred_by: '',
  notes: '',
})
const transferForm = ref(emptyTransfer())

// 详情
const detailModalVisible = ref(false)
const detailSample = ref(null)
const transfers = ref([])
const transfersLoading = ref(false)
const optionsLoading = ref(false)

// 下拉选项：从 MDM 主数据加载（带硬编码兜底）
const sourceTypeOptions = ref([
  { label: '合成', value: 'synthesis' },
  { label: '采购', value: 'purchase' },
  { label: '候选材料', value: 'candidate' },
  { label: '配方', value: 'formula' },
])
const unitOptions = ref([
  { label: '克 (g)', value: 'g' },
  { label: '毫克 (mg)', value: 'mg' },
  { label: '千克 (kg)', value: 'kg' },
  { label: '毫升 (mL)', value: 'mL' },
  { label: '片', value: '片' },
])
// P3-1：存储条件本地兜底选项（含手套箱/真空/惰性气体保护）；
// MDM storage_condition 维度加载成功时会整体覆盖此列表
const conditionOptions = ref([
  { label: '常温', value: '常温' },
  { label: '冷藏', value: '冷藏' },
  { label: '冷冻', value: '冷冻' },
  { label: '手套箱', value: '手套箱' },
  { label: '真空', value: '真空' },
  { label: '惰性气体', value: '惰性气体' },
  { label: '惰性气体保护', value: '惰性气体保护' },
  { label: '避光', value: '避光' },
  { label: '干燥', value: '干燥' },
])
const statusOptions = ref([
  { label: '已创建', value: 'created' },
  { label: '库存中', value: 'in_storage' },
  { label: '使用中', value: 'in_use' },
  { label: '已消耗', value: 'consumed' },
  { label: '已废弃', value: 'discarded' },
])

// 关联候选材料 / 实验任务下拉选项（从后端 API 拉取）
const candidateOptions = ref([])
const orderOptions = ref([])

async function fetchCandidateOptions() {
  try {
    const data = await listCandidates()
    const list = Array.isArray(data) ? data : (data?.items || [])
    candidateOptions.value = list.map((c) => ({
      label: c.name || c.formula || c.smiles || c.candidate_id,
      value: c.candidate_id,
    }))
  } catch {
    candidateOptions.value = []
  }
}

async function fetchOrderOptions() {
  try {
    const data = await listExperimentOrders()
    const list = Array.isArray(data) ? data : (data?.items || [])
    orderOptions.value = list.map((o) => ({
      label: o.project_id ? `${o.order_id} (${o.project_id})` : o.order_id,
      value: o.order_id,
    }))
  } catch {
    orderOptions.value = []
  }
}

function filterSelectOption(input, option) {
  return (option.label || '').toLowerCase().includes((input || '').toLowerCase())
}

const columns = [
  { title: '样品编号', key: 'sample_id', dataIndex: 'sample_id', width: 120, ellipsis: true, className: 'id-col' },
  { title: '名称', dataIndex: 'name', key: 'name', width: 150, ellipsis: true, sorter: (a, b) => (a.name || '').localeCompare(b.name || '') },
  { title: '化学式', dataIndex: 'chemical_formula', key: 'chemical_formula', width: 110, ellipsis: true },
  {
    title: '来源',
    key: 'source_type',
    dataIndex: 'source_type',
    width: 100,
    ellipsis: true,
  },
  { title: '批次', dataIndex: 'batch_number', key: 'batch_number', width: 120, ellipsis: true },
  { title: '数量', key: 'quantity', width: 100, className: 'tabular-nums' },
  {
    title: '状态',
    key: 'status',
    dataIndex: 'status',
    width: 100,
  },
  { title: '存储位置', dataIndex: 'storage_location', key: 'storage_location', width: 120, ellipsis: true, customRender: ({ text }) => renderTextOrCorrupted(text) },
  { title: '存储条件', key: 'storage_condition', width: 100, ellipsis: true },
  { title: '创建时间', key: 'created_at', dataIndex: 'created_at', width: 160, ellipsis: true, className: 'tabular-nums', sorter: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
  { title: '操作', key: 'action', width: 200, fixed: 'right' },
]

const transferColumns = [
  { title: '从状态', key: 'from_status', width: 100 },
  { title: '到状态', key: 'to_status', width: 100 },
  { title: '从位置', dataIndex: 'from_location', key: 'from_location', width: 100, customRender: ({ text }) => renderTextOrCorrupted(text) },
  { title: '到位置', dataIndex: 'to_location', key: 'to_location', width: 100, customRender: ({ text }) => renderTextOrCorrupted(text) },
  { title: '操作人', dataIndex: 'transferred_by', key: 'transferred_by', width: 100, customRender: ({ text }) => renderTextOrCorrupted(text) },
  { title: '时间', key: 'transferred_at', width: 160 },
  { title: '备注', dataIndex: 'notes', key: 'notes', ellipsis: true, customRender: ({ text }) => renderTextOrCorrupted(text) },
]

function sampleStatusToBadge(status) {
  const map = {
    created: 'running',
    in_storage: 'success',
    in_use: 'warning',
    consumed: 'default',
    discarded: 'failed',
  }
  return map[status] || 'default'
}

function statusLabel(status) {
  const map = {
    created: '已创建',
    in_storage: '库存中',
    in_use: '使用中',
    consumed: '已消耗',
    discarded: '已废弃',
  }
  return map[status] || status
}

function sourceTypeColor(type) {
  const map = { synthesis: 'purple', purchase: 'cyan', candidate: 'geekblue' }
  return map[type] || 'default'
}

function sourceTypeLabel(type) {
  const map = { synthesis: '合成', purchase: '采购', candidate: '候选材料' }
  return map[type] || type
}

function statusCount(status) {
  return samples.value.filter((s) => s.status === status).length
}

function formatTime(t) {
  if (!t) return '-'
  try {
    return new Date(t).toLocaleString('zh-CN')
  } catch {
    return t
  }
}

// 来源追溯：从样品反查至项目 / 实验任务 / 候选材料
function goToProject(id) { if (id) router.push(`/projects?project_id=${id}`) }
function goToOrder(id) { if (id) router.push(`/experiment-workbench?order_id=${id}`) }
function goToCandidate(id) { if (id) router.push(`/workbench?candidate_id=${id}`) }

async function fetchSamples() {
  loading.value = true
  try {
    const data = await listSamples({ include_demo: showDemo.value })
    samples.value = data || []
  } catch {
    samples.value = []
  } finally {
    loading.value = false
  }
}

function onAdd() {
  editingId.value = ''
  form.value = emptyForm()
  form.value.scenario_id = scenarioId.value || ''
  formModalVisible.value = true
}

function onEdit(record) {
  editingId.value = record.sample_id
  scenarioId.value = record.scenario_id || scenarioId.value || ''
  form.value = {
    name: record.name || '',
    source_type: record.source_type || 'synthesis',
    source_order_id: record.source_order_id || '',
    source_candidate_id: record.source_candidate_id || '',
    batch_number: record.batch_number || '',
    quantity: record.quantity || 0,
    unit: record.unit || 'g',
    storage_location: record.storage_location || '',
    storage_condition: record.storage_condition || '',
    notes: record.notes || '',
    sample_code: record.sample_code || '',
    chemical_formula: record.chemical_formula || '',
    scenario_id: record.scenario_id || scenarioId.value || '',
  }
  formModalVisible.value = true
}

async function onDelete(record) {
  try {
    await deleteSample(record.sample_id)
    message.success('样品已删除')
    await fetchSamples()
  } catch {
    // 错误由拦截器处理（含 409 流转记录保护提示）
  }
}

async function onSubmitForm() {
  try {
    await formRef.value.validate()
  } catch {
    return // 校验未通过，不提交
  }
  formSubmitting.value = true
  try {
    if (editingId.value) {
      await updateSample(editingId.value, form.value)
      message.success('样品已更新')
    } else {
      await createSample(form.value)
      message.success('样品已创建')
    }
    formModalVisible.value = false
    editingId.value = ''
    await fetchSamples()
  } catch {
    // 错误由拦截器处理
  } finally {
    formSubmitting.value = false
  }
}

function onTransfer(record) {
  transferForm.value = {
    ...emptyTransfer(),
    sample_id: record.sample_id,
    current_status: record.status,
    current_location: record.storage_location,
  }
  transferModalVisible.value = true
}

async function onSubmitTransfer() {
  if (!transferForm.value.to_status) {
    message.warning('请选择目标状态')
    return
  }
  transferSubmitting.value = true
  try {
    await transferSample(transferForm.value.sample_id, {
      to_status: transferForm.value.to_status,
      to_location: transferForm.value.to_location,
      transferred_by: transferForm.value.transferred_by,
      notes: transferForm.value.notes,
    })
    message.success('样品流转成功')
    transferModalVisible.value = false
    await fetchSamples()
  } catch {
    // 错误由拦截器处理
  } finally {
    transferSubmitting.value = false
  }
}

async function onDetail(record) {
  detailSample.value = record
  detailModalVisible.value = true
  transfersLoading.value = true
  transfers.value = []
  try {
    const data = await listSampleTransfers(record.sample_id)
    transfers.value = data || []
  } catch {
    transfers.value = []
  } finally {
    transfersLoading.value = false
  }
}

onMounted(async () => {
  await fetchSamples()
  fetchCandidateOptions()
  fetchOrderOptions()
  // 从 MDM 主数据加载下拉选项（失败时静默保留硬编码兜底）
  optionsLoading.value = true
  try {
    const [statusOpts, unitOpts, condOpts, sourceOpts] = await Promise.all([
      mdmStatusOptions('sample'),
      mdmUnitOptions('mass'),
      mdmDimensionOptions('storage_condition'),
      mdmDimensionOptions('sample_source_type'),
    ])
    if (statusOpts.length) statusOptions.value = statusOpts
    if (unitOpts.length) {
      // mass + volume 单位合并
      const volOpts = await mdmUnitOptions('volume')
      unitOptions.value = [...unitOpts, ...volOpts]
    }
    if (condOpts.length) conditionOptions.value = condOpts
    if (sourceOpts.length) sourceTypeOptions.value = sourceOpts
  } catch (e) {
    console.warn('从 MDM 加载下拉选项失败，使用硬编码兜底:', e)
  } finally {
    optionsLoading.value = false
  }
  // P0-001：携带全局场景 ID
  if (route.query.scenario_id) {
    scenarioId.value = String(route.query.scenario_id)
    form.value.scenario_id = scenarioId.value
  }
  // 从 URL query 预填表单（从 Discovery / FormulaDesign 跳转过来）
  if (route.query.candidate_id) {
    form.value.source_candidate_id = String(route.query.candidate_id)
    form.value.source_type = String(route.query.source_type || 'candidate')
    if (route.query.name) form.value.name = String(route.query.name)
    formModalVisible.value = true  // 自动展开表单
  } else if (route.query.formula_id) {
    // 从配方与工艺「制备样品」入口带入配方信息
    form.value.name = `配方 ${route.query.formula_id} 样品`
    form.value.source_type = 'formula'
    form.value.chemical_formula = String(route.query.target || '')
    form.value.notes = `来源配方：${route.query.formula_id}`
    if (route.query.target) form.value.chemical_formula = String(route.query.target)
    formModalVisible.value = true
  } else if (route.query.create === '1') {
    onAdd()
    // P1-1：从实验工作台「创建样品」跳转，预填关联实验任务与所属项目
    // 表单无独立 project 字段，所属项目沿用 scenario_id 字段承载
    if (route.query.order_id) form.value.source_order_id = String(route.query.order_id)
    if (route.query.project_id && !form.value.scenario_id) form.value.scenario_id = String(route.query.project_id)
  }
})
</script>

<style scoped>
.sample-manager {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.page-header {
  margin-bottom: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.stat-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.stat-item {
  flex: 1;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* 统计卡按语义着色：总数蓝 / 库存绿 / 使用橙 / 消耗灰 */
.stat-item:nth-child(1) .stat-value { color: var(--primary, #1d4ed8); }
.stat-item:nth-child(2) .stat-value { color: #047857; }
.stat-item:nth-child(3) .stat-value { color: #b45309; }
.stat-item:nth-child(4) .stat-value { color: var(--text-secondary, #6b7280); }

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.table-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title-text {
  font-size: 14px;
  font-weight: 600;
}

.count-tag {
  font-size: 12px;
}

.sample-id {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.num {
  font-family: monospace;
  font-size: 13px;
}

.time-text {
  font-size: 12px;
  color: var(--text-muted);
}

:deep(.discarded-row) {
  opacity: 0.6;
}

.search-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.empty-state {
  padding: 24px 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.empty-transfers {
  text-align: center;
  padding: 20px;
  color: var(--text-muted);
  font-size: 13px;
}

.trace-link {
  color: var(--primary-color);
  cursor: pointer;
}

.compact-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.compact-form :deep(.ant-form-item:last-child) {
  margin-bottom: 0;
}

.form-group-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 4px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
}

:deep(.tabular-nums) {
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 13px;
  color: var(--text-primary);
}

/* P2-4：关键 ID 列加粗 + 等宽字体，便于扫描 */
:deep(.id-col) {
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}
</style>