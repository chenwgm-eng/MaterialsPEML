<template>
  <div class="experiment-workbench">
    <!-- 审查意见0726：添加标准页面标题，保持全站一致性 -->
    <div class="page-header">
      <h1 class="page-title">实验工作台</h1>
      <p class="page-subtitle">创建、管理实验任务，跟踪实验执行状态，审批实验结果</p>
    </div>

    <!-- 来自 ECML 推荐候选的引导提示 -->
    <a-alert
      v-if="recommendedCandidate"
      type="info"
      show-icon
      closable
      message="来自实验闭环迭代的推荐候选材料"
      :description="`推荐候选材料：${recommendedCandidate}。已自动填入备注，请在下方表单中选择项目与执行模式后提交。`"
      style="margin-bottom: 12px"
      @close="recommendedCandidate = ''"
    />

    <a-card title="实验任务" size="small" :body-style="{ padding: '12px' }">
          <template #extra>
            <a-space>
              <a-select
                v-model:value="statusFilter"
                size="small"
                style="width: 140px"
                placeholder="状态筛选"
                :options="orderStatusOptions"
                allow-clear
                @change="fetchOrders"
              />
              <a-button size="small" @click="showImportModal = true">
                <UploadOutlined /> 批量导入
              </a-button>
              <a-button type="primary" size="small" @click="showCreateModal = true">
                <PlusOutlined /> 新建任务
              </a-button>
            </a-space>
          </template>
          <a-table
            :columns="orderColumns"
            :data-source="orders"
            :pagination="{ pageSize: 8, size: 'small' }"
            size="small"
            :row-key="(r) => r.order_id"
            :loading="loading"
            :scroll="{ y: 400 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <a-space>
                  <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
                  <a-tag v-if="record.ai_draft" color="#b45309" class="draft-badge">草案</a-tag>
                  <a-tag v-if="record.validation_failed" color="#dc2626" class="draft-badge">安全信息缺失</a-tag>
                </a-space>
              </template>
              <template v-if="column.key === 'source'">
                <a-tag v-if="record.protocol_provenance === 'ai' || record.ai_draft" color="orange">AI</a-tag>
                <a-tag v-else color="blue">人工</a-tag>
              </template>
              <template v-if="column.key === 'risk'">
                <a-tag v-if="record.risk_hint" :color="riskColor(record.risk_hint)">{{ record.risk_hint }}</a-tag>
                <span v-else class="text-muted">-</span>
              </template>
              <template v-if="column.key === 'priority'">
                <a-tag :color="record.priority === 'P0' ? '#dc2626' : record.priority === 'P1' ? '#b45309' : '#4b5563'">
                  {{ record.priority }}
                </a-tag>
              </template>
              <template v-if="column.key === 'actions'">
                <a-space size="small">
                  <a-tooltip
                    :title="record.status === 'PENDING_APPROVAL' ? '' : '仅待审批状态的任务可审批'"
                  >
                    <a-button
                      type="link"
                      size="small"
                      :disabled="record.status !== 'PENDING_APPROVAL'"
                      @click="onApprove(record)"
                    >审批</a-button>
                  </a-tooltip>
                  <a-tooltip
                    :title="(record.status === 'APPROVED' || record.status === 'WAITING_FOR_DATA') && !record.validation_failed ? '' : record.validation_failed ? '安全信息缺失，请补齐后再录入' : '仅已审批或待数据状态可录入'"
                  >
                    <a-button
                      type="link"
                      size="small"
                      :disabled="(record.status !== 'APPROVED' && record.status !== 'WAITING_FOR_DATA') || record.validation_failed"
                      @click="onEnterData(record)"
                    >录入数据</a-button>
                  </a-tooltip>
                  <a-button
                    type="link"
                    size="small"
                    :disabled="!record.result_count"
                    @click="onViewOrderResults(record)"
                  >查看结果</a-button>
                  <a-tooltip title="仅草稿/待审批状态可编辑">
                    <a-button
                      type="link"
                      size="small"
                      :disabled="!['DRAFT', 'PENDING_APPROVAL', 'APPROVED'].includes(record.status)"
                      @click="onEditOrder(record)"
                    >编辑</a-button>
                  </a-tooltip>
                  <a-popconfirm
                    title="确认删除该实验任务？仅草稿/待审批状态可删除。"
                    ok-text="删除"
                    cancel-text="取消"
                    @confirm="onDeleteOrder(record)"
                  >
                    <a-button
                      type="link"
                      danger
                      size="small"
                      :disabled="!['DRAFT', 'PENDING_APPROVAL'].includes(record.status)"
                    >删除</a-button>
                  </a-popconfirm>
                  <a-button
                    v-if="record.project_id"
                    type="link"
                    size="small"
                    @click="onViewExperiments(record)"
                  >项目数据</a-button>
                </a-space>
              </template>
            </template>
          </a-table>
        </a-card>

    <!-- 新建实验任务抽屉 -->
    <a-drawer
      :open="showCreateModal"
      title="新建实验任务"
      placement="right"
      width="600px"
      :destroy-on-close="false"
      @update:open="(v) => (showCreateModal = v)"
    >
      <a-form ref="formRef" :model="newOrder" :rules="orderRules" layout="vertical" size="small">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="项目" name="project_id" required>
              <a-select
                v-model:value="newOrder.project_id"
                show-search
                placeholder="搜索项目"
                :filter-option="filterProjectOption"
                size="small"
                @change="onProjectChange"
              >
                <a-select-option v-for="p in projectList" :key="p.project_id" :value="p.project_id">
                  {{ p.name }} ({{ p.project_id }})
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="候选材料">
              <a-select
                v-model:value="newOrder.candidate_id"
                show-search
                :placeholder="newOrder.project_id ? '搜索当前项目的候选材料' : '请先选择项目'"
                :filter-option="filterOption"
                size="small"
                :disabled="!newOrder.project_id"
              >
                <a-select-option v-for="c in filteredCandidateList" :key="c.id" :value="c.id">
                  {{ c.label }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="执行模式" name="execution_mode" required>
              <a-select v-model:value="newOrder.execution_mode" :options="executionModeOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="优先级" name="priority" required>
              <a-select v-model:value="newOrder.priority" :options="priorityOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="负责人">
              <a-input v-model:value="newOrder.assignee" placeholder="负责人" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="备注">
          <a-textarea v-model:value="newOrder.notes" :rows="2" placeholder="实验说明" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="creating" @click="showCreateModal = false">取消</a-button>
          <a-button type="primary" :loading="creating" @click="onCreateOrder">创建</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 编辑任务抽屉 -->
    <a-drawer
      :open="showEditModal"
      title="编辑实验任务"
      placement="right"
      width="480px"
      :destroy-on-close="false"
      @update:open="(v) => (showEditModal = v)"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="任务 ID">
          <a-input :value="editingOrder?.order_id" disabled />
        </a-form-item>
        <a-form-item label="状态">
          <a-tag :color="statusColor(editingOrder?.status)">{{ statusLabel(editingOrder?.status) }}</a-tag>
        </a-form-item>
        <a-form-item label="优先级">
          <a-select v-model:value="editForm.priority" :options="priorityOptions" />
        </a-form-item>
        <a-form-item label="负责人">
          <a-input v-model:value="editForm.assignee" placeholder="负责人" />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea v-model:value="editForm.notes" :rows="3" placeholder="实验说明" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="savingEdit" @click="showEditModal = false">取消</a-button>
          <a-button type="primary" :loading="savingEdit" @click="onSaveEditOrder">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 数据录入抽屉 -->
    <a-drawer
      :open="showDataModal"
      title="录入实验数据"
      placement="right"
      width="720px"
      :destroy-on-close="false"
      @update:open="(v) => (showDataModal = v)"
    >
      <experiment-data-form
        v-if="selectedOrder"
        ref="dataFormRef"
        :order="selectedOrder"
        :form-data="dataForm"
      />
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="submitting" @click="showDataModal = false">取消</a-button>
          <a-button type="primary" :loading="submitting" @click="onSubmitData">提交</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 审批规则说明弹窗 -->
    <a-modal
      v-model:open="showRulesModal"
      title="审批规则说明"
      width="640px"
      :footer="null"
    >
      <a-alert
        type="info"
        show-icon
        message="实验任务提交后，系统自动根据以下规则判断是否需要人工审批。"
        style="margin-bottom: 16px"
      />
      <a-table
        :columns="ruleColumns"
        :data-source="approvalRules"
        :pagination="false"
        size="small"
        :row-key="(r) => r.rule_id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action'">
            <a-tag :color="record.action === 'AUTO_APPROVE' ? '#047857' : record.action === 'BLOCK' ? '#dc2626' : '#b45309'">
              {{ record.action === 'AUTO_APPROVE' ? '自动放行' : record.action === 'BLOCK' ? '阻断' : '需人工审批' }}
            </a-tag>
          </template>
          <template v-if="column.key === 'condition'">
            {{ record.condition_field }} {{ record.operator }} {{ record.threshold }}
          </template>
        </template>
      </a-table>
      <div class="rules-note">
        <p><b>审批人：</b>当前由实验任务负责人或项目管理员审批（系统设置中可配置角色权限）。</p>
        <p><b>触发条件：</b>实验任务状态从「草稿」提交后，自动评估；命中「需人工审批」规则的任务进入审批队列。</p>
      </div>
    </a-modal>

    <!-- 批量导入弹窗 -->
    <a-modal
      v-model:open="showImportModal"
      title="批量导入实验数据"
      width="800px"
      :destroy-on-close="true"
      :ok-text="importPreview.length > 0 ? '确认导入' : '导入'"
      @ok="onImportSubmit"
      :confirm-loading="importing"
      :ok-button-props="{ disabled: importPreview.length === 0 && importFileList.length === 0 }"
    >
      <a-space direction="vertical" style="width: 100%">
        <a-alert
          type="info"
          show-icon
          message="支持 CSV / Excel (.xlsx) 格式。文件需包含列：样品 ID、属性、数值、单位、方法、录入人。"
          style="margin-bottom: 0"
        />
        <a-space>
          <a-upload
            :file-list="importFileList"
            :before-upload="beforeImportUpload"
            accept=".csv,.xlsx,.xls"
            :max-count="1"
            @remove="(file) => { importFileList = []; importPreview = [] }"
          >
            <a-button>
              <UploadOutlined /> 选择文件
            </a-button>
          </a-upload>
          <a-button @click="downloadTemplate">
            <DownloadOutlined /> 下载模板
          </a-button>
        </a-space>
        <!-- 预览表格 -->
        <a-table
          v-if="importPreview.length > 0"
          :columns="importPreviewColumns"
          :data-source="importPreview"
          :pagination="{ pageSize: 5, size: 'small' }"
          size="small"
          :row-key="(r, idx) => `${r.sample_id || ''}-${r.property_name || ''}-${idx}`"
          :scroll="{ y: 240 }"
          bordered
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'value'">
              <span :style="{ color: record._invalid ? 'red' : 'inherit' }">
                {{ record.value }}
              </span>
            </template>
          </template>
        </a-table>
      </a-space>
    </a-modal>

    <!-- 任务结果查看抽屉（含偏差检测，已抽取为子组件） -->
    <ExperimentResultsDrawer
      v-model:open="showResultsModal"
      :order="selectedOrder"
      :mass-unit="massUnit"
      @refresh-orders="fetchOrders"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined, UploadOutlined, DownloadOutlined } from '@ant-design/icons-vue'
import { orderStatusLabel, orderStatusColor } from '@/utils/enumLabels'
import {
  listExperimentOrders,
  createExperimentOrder,
  createExperimentResultManual,
  createExperimentResultsBatch,
  uploadExperimentFile,
  listApprovalRules,
  updateExperimentOrder,
  deleteExperimentOrder,
  approveExperimentOrder,
} from '@/api/experiments'
import { resumeECMLFromData } from '@/api/ecml'
import { listProjects } from '@/api/projects'
import { listCandidates } from '@/api/candidates'
import { getUserId } from '@/api/client'
import ExperimentDataForm from '@/components/ExperimentDataForm.vue'
import ExperimentResultsDrawer from '@/components/experiment/ExperimentResultsDrawer.vue'
import * as XLSX from 'xlsx'
import { useMdmDict, useUnitSymbols } from '@/utils/mdmDict'

// 从 MDM 加载状态、执行模式、优先级选项（失败时使用硬编码兜底）
const { statusOptions: mdmStatusOptions, dimensionOptions: mdmDimensionOptions } = useMdmDict()
// 从 MDM 加载单位符号（失败时 computed 使用默认单位兜底）
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const massUnit = computed(() => unitSymbols.value.mass || 'kg')
const orderStatusOptions = ref([
  { label: '草稿', value: 'DRAFT' },
  { label: '待审批', value: 'PENDING_APPROVAL' },
  { label: '已批准', value: 'APPROVED' },
  { label: '等待数据', value: 'WAITING_FOR_DATA' },
  { label: '已完成', value: 'COMPLETED' },
  { label: '已拒绝', value: 'REJECTED' },
])
const executionModeOptions = ref([
  { label: '人工录入', value: 'MANUAL_ENTRY' },
  { label: '自动设备', value: 'AUTO_DEVICE' },
  { label: '外部 LIMS', value: 'EXTERNAL_LIMS' },
  { label: '外部 ELN', value: 'EXTERNAL_ELN' },
])
const priorityOptions = ref([
  { label: 'P0 紧急', value: 'P0' },
  { label: 'P1 高', value: 'P1' },
  { label: 'P2 中', value: 'P2' },
  { label: 'P3 低', value: 'P3' },
])

const loading = ref(false)
const creating = ref(false)
const submitting = ref(false)
const orders = ref([])
const statusFilter = ref('')
const showCreateModal = ref(false)
// 评测修复 P1：每次打开新建抽屉生成幂等键，双击/重试重复提交时后端去重
const createIdempotencyKey = ref('')
watch(showCreateModal, (open) => {
  if (open) createIdempotencyKey.value = crypto.randomUUID()
})
const showDataModal = ref(false)
const selectedOrder = ref(null)
const dataFormRef = ref(null)
const router = useRouter()
const route = useRoute()
const showRulesModal = ref(false)
const approvalRules = ref([])
const showEditModal = ref(false)
const editingOrder = ref(null)
const editForm = ref({ assignee: '', priority: '', notes: '' })
const savingEdit = ref(false)

const projectList = ref([])
const candidateList = ref([])
const filteredCandidateList = computed(() => {
  const pid = newOrder.value.project_id
  if (!pid) return candidateList.value
  const matched = candidateList.value.filter((c) => c.project_id === pid)
  return matched.length > 0 ? matched : candidateList.value
})

const newOrder = ref({
  project_id: '',
  candidate_id: '',
  execution_mode: 'MANUAL_ENTRY',
  priority: 'P2',
  assignee: '当前用户',
  notes: '',
  scenario_id: '',
})

// P2-4：新建任务表单校验规则（项目/执行模式/优先级必填）
const formRef = ref(null)
const orderRules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  execution_mode: [{ required: true, message: '请选择执行模式', trigger: 'change' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
}

// P0-001：从路由获取 scenario_id，使实验任务可溯源到研发场景
const currentScenarioId = ref('')

// ECML 闭环迭代推荐候选（来自 sessionStorage，用于顶部提示条）
const recommendedCandidate = ref('')


const dataForm = ref({
  sample_id: '',
  sample_batch_id: '',
  property_name: '',
  value: 0,
  unit: '',
  test_method: '',
  uploaded_by: '',
  instrument_id: '',
  raw_file_uri: '',
  data_quality: 'estimated',
  test_conditions: {
    temperature_K: null,
    cycle_count: null,
    frequency_Hz: null,
    atmosphere: '',
  },
})

const orderColumns = [
  { title: '任务 ID', dataIndex: 'order_id', key: 'order_id', width: 120, className: 'tabular-nums' },
  { title: '项目', dataIndex: 'project_id', key: 'project_id', width: 100 },
  { title: '状态', key: 'status', width: 100 },
  { title: '来源', key: 'source', width: 80, align: 'center' },
  { title: '优先级', key: 'priority', width: 70, className: 'tabular-nums' },
  { title: '风险', key: 'risk', width: 80, align: 'center' },
  { title: '负责人', dataIndex: 'assignee', key: 'assignee', width: 80 },
  { title: '数据条数', dataIndex: 'result_count', key: 'result_count', width: 85, className: 'tabular-nums' },
  { title: '操作', key: 'actions', width: 240 },
]

const ruleColumns = [
  { title: '规则 ID', dataIndex: 'rule_id', key: 'rule_id', width: 80 },
  { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name' },
  { title: '条件', key: 'condition', width: 160 },
  { title: '动作', key: 'action', width: 110 },
  { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
]

// P2-1：状态色值统一引用 enumLabels.js 集中工具，避免多处分散维护
function statusColor(status) {
  const raw = orderStatusColor(status)
  const statusColorMap = {
    purple: '#8b5cf6',
    blue: '#3b82f6',
    green: '#047857',
    orange: '#b45309',
    red: '#dc2626',
    default: '#64748b',
  }
  return statusColorMap[raw] || raw
}

function statusLabel(status) {
  // 优先使用 MDM 下发的标签，兜底使用 enumLabels.js 集中映射
  const found = orderStatusOptions.value.find(o => o.value === status)
  return found ? found.label : orderStatusLabel(status)
}

async function fetchOrders() {
  loading.value = true
  try {
    const params = { include_result_count: true }
    if (statusFilter.value) params.status = statusFilter.value
    orders.value = await listExperimentOrders(params)
  } catch {
    orders.value = []
  } finally {
    loading.value = false
  }
}

async function fetchProjects() {
  try {
    projectList.value = await listProjects()
  } catch {
    projectList.value = []
    message.error('项目列表加载失败，请稍后重试')
  }
}

async function fetchCandidates() {
  try {
    const res = await listCandidates()
    const candidates = res.candidates || []
    candidateList.value = candidates.map((c) => ({
      id: c.candidate_id,
      label: c.formula || c.smiles || c.name || c.candidate_id,
      project_id: c.project_id || '',
      scenario_id: c.scenario_id || '',
    }))
  } catch { candidateList.value = [] }
}

function filterProjectOption(input, option) {
  return option.children?.toLowerCase().includes(input.toLowerCase())
}

function filterOption(input, option) {
  return option.children?.toLowerCase().includes(input.toLowerCase())
}

function onProjectChange(value) {
  // 选择项目后清空候选材料，避免跨项目关联错误
  newOrder.value.candidate_id = ''
}

async function onCreateOrder() {
  if (!formRef.value) {
    message.warning('表单尚未就绪，请稍后再试')
    return
  }
  try {
    await formRef.value.validate()
  } catch {
    message.warning('请填写所有必填字段（项目、执行模式、优先级）')
    return
  }
  if (!newOrder.value.project_id) {
    message.warning('请选择项目')
    return
  }
  creating.value = true
  try {
    const payload = { ...newOrder.value, scenario_id: currentScenarioId.value || newOrder.value.scenario_id || '', idempotency_key: createIdempotencyKey.value }
    await createExperimentOrder(payload)
    message.success('实验任务已创建')
    showCreateModal.value = false
    newOrder.value = {
      project_id: '',
      candidate_id: '',
      execution_mode: 'MANUAL_ENTRY',
      priority: 'P2',
      assignee: '当前用户',
      notes: '',
      scenario_id: '',
    }
    await fetchOrders()
  } catch {
    // 错误由拦截器处理
  } finally {
    creating.value = false
  }
}

function onApprove(record) {
  // 直接执行审批（审批队列同时迁移至「我的待办」汇总）
  Modal.confirm({
    title: '审批实验任务',
    content: `确认通过实验任务 ${record.order_id} 的审批？通过后状态变为「已审批」，可录入实验数据。`,
    okText: '审批通过',
    cancelText: '取消',
    onOk: async () => {
      try {
        await approveExperimentOrder(record.order_id, { approved_by: getUserId() || '', notes: '实验工作台审批通过' })
        message.success(`任务 ${record.order_id} 已审批通过`)
        await fetchOrders()
      } catch (e) {
        const detail = e?.response?.data?.detail
        message.error(typeof detail === 'string' ? detail : '审批失败，请检查权限或任务状态', 6)
      }
    },
  })
}

// ── 编辑/删除实验任务 ──
function onEditOrder(record) {
  editingOrder.value = record
  editForm.value = {
    assignee: record.assignee || '',
    priority: record.priority || 'P2',
    notes: record.notes || '',
  }
  showEditModal.value = true
}

async function onSaveEditOrder() {
  if (!editingOrder.value) return
  savingEdit.value = true
  try {
    await updateExperimentOrder(editingOrder.value.order_id, {
      assignee: editForm.value.assignee,
      priority: editForm.value.priority,
      notes: editForm.value.notes,
    })
    message.success('任务已更新')
    showEditModal.value = false
    await fetchOrders()
  } catch (e) {
    const detail = e?.response?.data?.detail
    message.error(typeof detail === 'string' ? detail : '更新失败，请稍后重试', 6)
  } finally {
    savingEdit.value = false
  }
}

async function onDeleteOrder(record) {
  try {
    await deleteExperimentOrder(record.order_id)
    message.success(`任务 ${record.order_id} 已删除`)
    await fetchOrders()
  } catch (e) {
    const detail = e?.response?.data?.detail
    message.error(typeof detail === 'string' ? detail : '删除失败，仅草稿/待审批任务可删除', 6)
  }
}

function onEnterData(record) {
  selectedOrder.value = record
  dataForm.value = {
    sample_id: '',
    sample_batch_id: '',
    property_name: '',
    value: 0,
    unit: '',
    test_method: '',
    uploaded_by: '',
    instrument_id: '',
    raw_file_uri: '',
    test_conditions: {
      temperature_K: null,
      cycle_count: null,
      frequency_Hz: null,
      atmosphere: '',
    },
  }
  showDataModal.value = true
}

function onViewExperiments(record) {
  router.push({ path: '/experiments', query: { project_id: record.project_id } })
}

async function onSubmitData() {
  if (!dataFormRef.value) return
  submitting.value = true
  try {
    // 获取模板字段数据
    const templatePayload = dataFormRef.value.getTemplatePayload()
    // 找到主属性字段（第一个模板字段）
    const templateFields = dataFormRef.value.templateFields || []
    const mainField = templateFields.length > 0 ? templateFields[0] : null

    // 提交前校验：必填数值字段必须解析成功（不再静默兜底为 0）
    if (mainField && (mainField.value_type === 'float' || mainField.value_type === 'int')) {
      const val = templatePayload[mainField.key]
      if (val === undefined || val === null || val === '' || (typeof val === 'number' && isNaN(val))) {
        message.error(`数值字段 ${mainField.label_cn || mainField.key} 解析失败，请检查输入`)
        submitting.value = false
        return
      }
    }

    // 清理 test_conditions 中的空值
    const cleanConditions = {}
    const tc = dataForm.value.test_conditions || {}
    for (const [k, v] of Object.entries(tc)) {
      if (v !== null && v !== '' && v !== undefined) cleanConditions[k] = v
    }

    const payload = {
      experiment_order_id: selectedOrder.value.order_id,
      sample_id: dataForm.value.sample_id,
      sample_batch_id: dataForm.value.sample_batch_id,
      property_name: mainField ? mainField.key : templatePayload.property_name || '',
      value: mainField ? templatePayload[mainField.key] : dataForm.value.value,
      unit: mainField ? (mainField.unit || '') : dataForm.value.unit,
      test_method: templatePayload.test_method || dataForm.value.test_method || '',
      uploaded_by: dataForm.value.uploaded_by,
      instrument_id: templatePayload.instrument_id || dataForm.value.instrument_id || '',
      raw_file_uri: dataForm.value.raw_file_uri,
      data_quality: dataForm.value.data_quality || 'estimated',
      test_conditions: cleanConditions,
      scenario_id: currentScenarioId.value || selectedOrder.value?.scenario_id || '',
    }

    const res = await createExperimentResultManual(payload)
    message.success('实验数据已录入，等待 QC 检查')
    showDataModal.value = false
    await fetchOrders()

    // 半自动闭环：若后端检测到关联的 WAITING_FOR_DATA ECML run，提示用户触发反馈分析
    if (res?.pending_resume?.runs?.length) {
      _promptResumeECML(res.pending_resume, payload)
    }
  } catch {
    // 错误由拦截器处理
  } finally {
    submitting.value = false
  }
}

/**
 * 半自动闭环：录入数据后，若检测到关联的 WAITING_FOR_DATA ECML run，
 * 弹窗询问用户是否触发反馈分析。确认后调 resume 端点注入数据唤醒 run。
 */
function _promptResumeECML(pendingResume, payload) {
  const runs = pendingResume.runs || []
  if (!runs.length) return
  const run = runs[0]
  const iterationDesc = run.iteration_id ? `（第 ${run.iteration_id} 轮）` : ''
  Modal.confirm({
    title: '检测到等待数据的 ECML 闭环',
    content: `实验任务 ${payload.experiment_order_id} 关联的 ECML run ${run.run_id}${iterationDesc} 正在等待真实数据。是否立即触发反馈分析？`,
    okText: '触发反馈分析',
    cancelText: '稍后手动处理',
    async onOk() {
      try {
        const res = await resumeECMLFromData(run.run_id, {
          from_order_id: payload.experiment_order_id,
        })
        const rec = res?.recommendation
        const recLabel = {
          converge: '已收敛，可终止迭代',
          continue_iteration: '建议继续迭代',
          expand_search_space: '建议扩大搜索空间',
        }[rec] || rec || '完成'
        message.success(`ECML 反馈分析完成：${recLabel}`)
        // 提供"查看详情"入口：跳转到 ECML 监控页
        if (res?.run_id) {
          Modal.info({
            title: '反馈分析结果',
            content: `Run ID: ${res.run_id}，建议：${recLabel}。可前往"实验闭环迭代"页面查看详情与启动下一轮。`,
            okText: '前往查看',
            onOk: () => router.push({ path: '/ecml', query: { run_id: res.run_id } }),
          })
        }
      } catch {
        // 错误由拦截器处理
      }
    },
  })
}

// 批量导入 CSV/Excel
const showImportModal = ref(false)
const importFileList = ref([])
const importPreview = ref([])
const importing = ref(false)

const importPreviewColumns = [
  { title: '#', key: 'index', width: 50, customRender: ({ index }) => index + 1 },
  { title: '样品 ID', dataIndex: 'sample_id', key: 'sample_id', width: 110 },
  { title: '属性', dataIndex: 'property_name', key: 'property_name', width: 140 },
  { title: '数值', dataIndex: 'value', key: 'value', width: 100 },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
  { title: '方法', dataIndex: 'test_method', key: 'test_method', width: 100 },
  { title: '录入人', dataIndex: 'uploaded_by', key: 'uploaded_by', width: 90 },
]

// 批量导入模板支持中文表头，导入时自动映射为内部英文字段
const IMPORT_HEADER_MAP = {
  '样品 ID': 'sample_id',
  '属性': 'property_name',
  '数值': 'value',
  '单位': 'unit',
  '方法': 'test_method',
  '录入人': 'uploaded_by',
  '仪器 ID': 'instrument_id',
  '批次 ID': 'sample_batch_id',
  '原始数据 URI': 'raw_file_uri',
}

function normalizeImportRow(row) {
  const normalized = {}
  for (const [key, val] of Object.entries(row)) {
    const engKey = IMPORT_HEADER_MAP[key] || key
    normalized[engKey] = val
  }
  return normalized
}

function beforeImportUpload(file) {
  importFileList.value = [file]
  // 解析文件预览
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const data = new Uint8Array(e.target.result)
      const workbook = XLSX.read(data, { type: 'array' })
      const sheet = workbook.Sheets[workbook.SheetNames[0]]
      const rows = XLSX.utils.sheet_to_json(sheet, { defval: '' })
      importPreview.value = rows.map((row, idx) => {
        const normalized = normalizeImportRow(row)
        const val = Number(normalized.value)
        return {
          ...normalized,
          _invalid: isNaN(val),
          _rowIndex: idx + 2, // Excel 首行为表头
        }
      })
    } catch {
      importPreview.value = []
      message.error('文件解析失败，请检查格式')
    }
  }
  reader.readAsArrayBuffer(file)
  return false // 阻止自动上传
}

function downloadTemplate() {
  const templateData = [
    { '样品 ID': 'SMP_001', '属性': 'tensile_strength', '数值': 45.2, '单位': 'MPa', '方法': '拉伸试验', '录入人': '操作员', '仪器 ID': '', '批次 ID': '', '原始数据 URI': '' },
    { '样品 ID': 'SMP_002', '属性': 'flexural_modulus', '数值': 2100, '单位': 'MPa', '方法': '弯曲试验', '录入人': '操作员', '仪器 ID': '', '批次 ID': '', '原始数据 URI': '' },
  ]
  const ws = XLSX.utils.json_to_sheet(templateData)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '实验数据')
  XLSX.writeFile(wb, '实验数据导入模板.xlsx')
}

async function onImportSubmit() {
  if (importFileList.value.length === 0 && importPreview.value.length === 0) {
    message.warning('请先选择文件')
    return
  }
  importing.value = true
  try {
    // 优先使用预览数据批量提交（跳过 _invalid 行，禁止 NaN→0 脏数据入库）
    if (importPreview.value.length > 0) {
      const invalidRows = importPreview.value.filter((r) => r._invalid)
      if (invalidRows.length > 0) {
        message.warning(`第 ${invalidRows.map((r) => r._rowIndex).join('、')} 行数值无效，已跳过`)
      }
      const payloads = importPreview.value
        .filter((r) => !r._invalid)
        .map((row) => ({
          experiment_order_id: selectedOrder.value?.order_id || '',
          sample_id: row.sample_id || '',
          sample_batch_id: row.sample_batch_id || '',
          property_name: row.property_name || '',
          value: Number(row.value) || 0,
          unit: row.unit || '',
          test_method: row.test_method || '',
          uploaded_by: row.uploaded_by || '',
          instrument_id: row.instrument_id || '',
          raw_file_uri: row.raw_file_uri || '',
          test_conditions: {},
        }))
      if (payloads.length === 0) {
        message.error('没有可导入的有效记录')
        return
      }
      const res = await createExperimentResultsBatch(payloads)
      message.success(`成功导入 ${res.imported} 条记录`)
    } else {
      // 降级：使用后端文件上传
      const formData = new FormData()
      formData.append('file', importFileList.value[0])
      const res = await uploadExperimentFile(formData)
      message.success(`成功导入 ${res.imported} 条记录`)
    }
    showImportModal.value = false
    importFileList.value = []
    importPreview.value = []
    await fetchOrders()
  } catch {
    // 错误由拦截器处理
  } finally {
    importing.value = false
  }
}

// 查看任务结果：仅设置选中任务并打开抽屉，数据拉取由 ExperimentResultsDrawer 子组件处理
const showResultsModal = ref(false)

function onViewOrderResults(record) {
  selectedOrder.value = record
  showResultsModal.value = true
}

function riskColor(risk) {
  const map = { '低': '#047857', '中': '#b45309', '高': '#dc2626' }
  return map[risk] || '#64748b'
}

onMounted(async () => {
  fetchOrders()
  fetchProjects()
  fetchCandidates()
  fetchApprovalRules()
  // 从 MDM 加载单位符号（失败时 computed 使用默认单位兜底）
  await loadUnitSymbols()
  // P0-001：从路由获取 scenario_id，使实验任务可溯源到研发场景
  if (route.query.scenario_id) {
    currentScenarioId.value = String(route.query.scenario_id)
    newOrder.value.scenario_id = currentScenarioId.value
  }
  // P1-1：从候选工作台「采纳进入湿实验」跳转时，自动带出项目与候选
  if (route.query.project_id) {
    newOrder.value.project_id = String(route.query.project_id)
  }
  if (route.query.candidate_id) {
    newOrder.value.candidate_id = String(route.query.candidate_id)
  }
  if (route.query.create === '1') {
    showCreateModal.value = true
  }
  // 配方/工艺 → 下达实验跳转：定位并自动打开该任务的结果抽屉
  if (route.query.order_id) {
    const targetId = String(route.query.order_id)
    await fetchOrders()
    const target = orders.value.find((o) => o.order_id === targetId)
    if (target) {
      selectedOrder.value = target
      showResultsModal.value = true
    } else {
      message.info(`任务 ${targetId} 可能尚未同步，请刷新后查看`)
    }
  }
  // 读取来自 ECML 闭环迭代推荐候选的上下文，自动填入备注
  const ecmlCandidate = sessionStorage.getItem('ecml_recommended_candidate')
  if (ecmlCandidate) {
    recommendedCandidate.value = ecmlCandidate
    newOrder.value.notes = `基于 ECML 推荐候选材料：${ecmlCandidate}`
    sessionStorage.removeItem('ecml_recommended_candidate')
  }
  // 从 MDM 加载状态/执行模式/优先级选项（失败时保留硬编码兜底）
  try {
    const [statusOpts, execOpts, priOpts] = await Promise.all([
      mdmStatusOptions('order'),
      mdmDimensionOptions('execution_mode'),
      mdmDimensionOptions('priority'),
    ])
    if (statusOpts.length) orderStatusOptions.value = statusOpts
    if (execOpts.length) executionModeOptions.value = execOpts
    if (priOpts.length) priorityOptions.value = priOpts
  } catch (e) {
    console.warn('从 MDM 加载实验任务选项失败，使用硬编码兜底:', e)
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})

async function fetchApprovalRules() {
  try {
    const data = await listApprovalRules()
    approvalRules.value = Array.isArray(data) ? data : (data.rules || [])
  } catch {
    approvalRules.value = []
  }
}
</script>

<style scoped>
.experiment-workbench {
  padding: 0;
  overflow-x: hidden;
}

.rules-note {
  margin-top: 16px;
  padding: 12px;
  background: var(--light-bg);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.rules-note p {
  margin: 0;
}

.draft-badge {
  margin: 0;
  font-size: 11px;
}

.text-muted {
  color: var(--text-muted);
}
</style>
