<template>
  <div class="equipment-ledger">
    <SectionHeader title="设备台账" subtitle="实验室设备全生命周期管理 — 状态、校准、负责人" />

    <!-- 汇总卡片 -->
    <div class="stat-row" v-if="equipment.length > 0">
      <div class="stat-item">
        <span class="stat-value">{{ equipment.length }}</span>
        <span class="stat-label">设备总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ idleCount }}</span>
        <span class="stat-label">空闲</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ inUseCount }}</span>
        <span class="stat-label">使用中</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ calibrationDueCount }}</span>
        <span class="stat-label">校准即将到期</span>
      </div>
    </div>

    <!-- 设备表格 -->
    <a-card class="table-card" size="small" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">设备清单</span>
          <a-tag color="blue" class="count-tag">{{ equipment.length }} 台</a-tag>
        </div>
      </template>
      <template #extra>
        <a-space wrap>
          <a-select
            v-model:value="filterCategory"
            :options="categoryOptions"
            placeholder="全部类别"
            aria-label="设备类别"
            style="width: 140px"
            allow-clear
            @change="onQuery"
          />
          <a-select
            v-model:value="filterStatus"
            :options="statusOptions"
            placeholder="全部状态"
            aria-label="设备状态"
            style="width: 120px"
            allow-clear
            @change="onQuery"
          />
          <a-button type="primary" size="small" :loading="loading" @click="onQuery">
            <SearchOutlined /> 查询
          </a-button>
          <a-divider type="vertical" />
          <a-tooltip title="新增设备将写入设备台账">
            <a-button type="primary" size="small" @click="onAdd">
              <PlusOutlined /> 新增设备
            </a-button>
          </a-tooltip>
          <a-tooltip :title="selectedEquipment ? '' : '请先选择一台设备'">
            <span class="tt-btn-wrap">
              <a-button size="small" :disabled="!selectedEquipment" @click="onEdit">
                <EditOutlined /> 编辑
              </a-button>
            </span>
          </a-tooltip>
        </a-space>
      </template>
      <a-table
        v-if="equipment.length > 0 || loading"
        :data-source="equipment"
        :loading="loading"
        :pagination="{ pageSize: 10, showTotal: (t) => `共 ${t} 台`, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'] }"
        :columns="columns"
        size="middle"
        :row-key="(r) => r.equipment_id"
        :row-selection="{ selectedRowKeys: selectedRowKeys, onChange: onSelectChange, type: 'radio' }"
        :scroll="{ x: 1200 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'equipment_id'">
            <span class="eq-id">{{ record.equipment_id }}</span>
          </template>
          <template v-else-if="column.key === 'category'">
            <span>{{ categoryLabel(record.category) }}</span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">
              {{ statusLabel(record.status) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'last_calibration'">
            <span>{{ record.last_calibration || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'next_calibration'">
            <a-tag v-if="isCalibrationDue(record.next_calibration)" color="#f59e0b">
              <WarningOutlined aria-hidden="true" /> {{ record.next_calibration }}
            </a-tag>
            <span v-else>{{ record.next_calibration || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button type="link" size="small" @click="onEditRow(record)">编辑</a-button>
              <a-dropdown>
                <a-button size="small" type="text">操作 <DownOutlined /></a-button>
                <template #overlay>
                  <a-menu @click="({ key }) => onActionClick(record, key)">
                    <a-menu-item key="idle"><a-tag color="#047857">空闲</a-tag></a-menu-item>
                    <a-menu-item key="in_use"><a-tag color="#1d4ed8">使用中</a-tag></a-menu-item>
                    <a-menu-item key="maintenance"><a-tag color="#b45309">维护中</a-tag></a-menu-item>
                    <a-menu-item key="calibration"><a-tag color="#1d4ed8">校准中</a-tag></a-menu-item>
                    <a-menu-item key="retired"><a-tag color="#4b5563">退役</a-tag></a-menu-item>
                    <a-menu-divider />
                    <a-menu-item key="delete" danger><DeleteOutlined /> 删除设备</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </a-space>
          </template>
        </template>
      </a-table>
      <div v-else class="empty-state">
        <EmptyState type="create" description="暂无设备数据" action-text="新增设备" @action="onAdd" />
      </div>
    </a-card>

    <!-- 新增/编辑设备抽屉 -->
    <a-drawer
      :open="formModalVisible"
      :title="formMode === 'create' ? '新增设备' : `编辑设备 ${form.equipment_id}`"
      placement="right"
      width="720px"
      :z-index="1000"
      @update:open="(v) => (formModalVisible = v)"
    >
      <a-form ref="formRef" class="compact-form" layout="vertical" size="small" :model="form" :rules="formRules">
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="设备编号" name="equipment_id">
              <a-input
                v-model:value="form.equipment_id"
                name="equipment_id"
                :disabled="formMode === 'edit'"
                placeholder="留空自动生成 EQUIP-xxx"
                autocomplete="off"
                :spellcheck="false"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="设备名称" name="name">
              <a-input
                v-model:value="form.name"
                name="name"
                id="equipment-name-input"
                autocomplete="off"
                placeholder="如 电化学工作站…"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="型号">
              <a-input v-model:value="form.model" name="model" autocomplete="off" placeholder="如 CHI660E…" :spellcheck="false" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="类别" name="category">
              <a-select v-model:value="form.category" name="category" :options="categoryOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="序列号">
              <a-input v-model:value="form.serial_number" name="serial_number" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="存放位置">
              <a-input v-model:value="form.location" name="location" autocomplete="off" placeholder="如 Lab-A-203…" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="状态">
              <a-select v-model:value="form.status" name="status" :options="statusOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="负责人">
              <a-input v-model:value="form.responsible_person" name="responsible_person" autocomplete="name" placeholder="如 张三…" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="采购日期">
              <a-date-picker v-model:value="form.purchase_date" name="purchase_date" style="width: 100%" value-format="YYYY-MM-DD" :get-popup-container="(trigger) => trigger.parentNode" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="上次校准日期">
              <a-date-picker v-model:value="form.last_calibration" name="last_calibration" style="width: 100%" value-format="YYYY-MM-DD" :get-popup-container="(trigger) => trigger.parentNode" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="下次校准日期">
              <a-date-picker v-model:value="form.next_calibration" name="next_calibration" style="width: 100%" value-format="YYYY-MM-DD" :get-popup-container="(trigger) => trigger.parentNode" />
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
  </div>
</template>

<script setup>
import { h, ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { SearchOutlined, PlusOutlined, EditOutlined, DownOutlined, WarningOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { listEquipment, createEquipment, updateEquipment, deleteEquipment } from '@/api/equipment'
import { message, Tag, Modal } from 'ant-design-vue'
import { useMdmDict } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'
import SectionHeader from '@/components/SectionHeader.vue'

const equipment = ref([])
const loading = ref(false)
const route = useRoute()
const filterCategory = ref(undefined)
const filterStatus = ref(undefined)

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

// 行选择（单选模式，用于编辑）
const selectedRowKeys = ref([])
const selectedEquipment = ref(null)

// 新增/编辑表单
const formModalVisible = ref(false)
const formSubmitting = ref(false)
const formRef = ref()
const formMode = ref('create')
// P1-3：前端表单校验规则
const formRules = {
  name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择设备类别', trigger: 'change' }],
}
const emptyForm = () => ({
  equipment_id: '',
  name: '',
  model: '',
  category: 'electrochemical',
  serial_number: '',
  location: '',
  status: 'idle',
  last_calibration: '',
  next_calibration: '',
  responsible_person: '',
  purchase_date: '',
  notes: '',
})
const form = ref(emptyForm())

const categoryOptions = ref([
  { label: '合成', value: 'synthesis' },
  { label: '测试', value: 'test' },
  { label: '分析', value: 'analysis' },
  { label: '前处理', value: 'pretreatment' },
  { label: '电化学', value: 'electrochemical' },
  { label: '表征', value: 'characterization' },
  { label: '安全', value: 'safety' },
])

const statusOptions = ref([
  { label: '空闲', value: 'idle' },
  { label: '使用中', value: 'in_use' },
  { label: '维护中', value: 'maintenance' },
  { label: '校准中', value: 'calibration' },
  { label: '退役', value: 'retired' },
])

// 从 MDM 加载设备类别和状态选项
const { classificationOptions: mdmClassificationOptions, statusOptions: mdmStatusOptions } = useMdmDict()

const columns = [
  { title: '设备编号', key: 'equipment_id', dataIndex: 'equipment_id', width: 110, className: 'id-col' },
  { title: '名称', dataIndex: 'name', key: 'name', width: 140, ellipsis: true, customRender: ({ text }) => renderTextOrCorrupted(text) },
  { title: '型号', dataIndex: 'model', key: 'model', width: 100, ellipsis: true },
  { title: '类别', dataIndex: 'category', key: 'category', width: 80 },
  { title: '序列号', dataIndex: 'serial_number', key: 'serial_number', width: 120, ellipsis: true },
  { title: '位置', dataIndex: 'location', key: 'location', width: 100, ellipsis: true, customRender: ({ text }) => renderTextOrCorrupted(text) },
  { title: '状态', key: 'status', width: 80 },
  { title: '负责人', dataIndex: 'responsible_person', key: 'responsible_person', width: 90, ellipsis: true, customRender: ({ text }) => renderTextOrCorrupted(text) },
  { title: '上次校准', key: 'last_calibration', width: 110, className: 'tabular-nums' },
  { title: '下次校准', key: 'next_calibration', width: 110, className: 'tabular-nums' },
  { title: '操作', key: 'actions', width: 160, fixed: 'right' },
]

const idleCount = computed(() => equipment.value.filter((e) => e.status === 'idle').length)
const inUseCount = computed(() => equipment.value.filter((e) => e.status === 'in_use').length)
const calibrationDueCount = computed(() =>
  equipment.value.filter((e) => isCalibrationDue(e.next_calibration)).length,
)

function statusColor(status) {
  // 实底 tag（白字）：底色加深保证 5:1+（原 #10b981/#f59e0b 白字仅 2.2-2.5:1）
  const map = { idle: '#047857', in_use: '#1d4ed8', maintenance: '#b45309', calibration: '#1d4ed8', retired: '#4b5563' }
  return map[status] || '#4b5563'
}

function statusLabel(status) {
  const found = statusOptions.value.find(o => o.value === status)
  return found ? found.label : status
}

function categoryLabel(cat) {
  const found = categoryOptions.value.find(o => o.value === cat)
  return found ? found.label : cat
}

function isCalibrationDue(dateStr) {
  if (!dateStr) return false
  const target = new Date(dateStr)
  const now = new Date()
  const diff = (target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
  return diff >= 0 && diff <= 30
}

async function onQuery() {
  loading.value = true
  try {
    const params = {}
    if (filterCategory.value) params.category = filterCategory.value
    if (filterStatus.value) params.status = filterStatus.value
    const data = await listEquipment(params)
    equipment.value = Array.isArray(data) ? data : []
  } catch {
    message.error('设备查询失败')
    equipment.value = []
  } finally {
    loading.value = false
  }
}

function onSelectChange(keys, rows) {
  selectedRowKeys.value = keys
  selectedEquipment.value = rows[0] || null
}

function onAdd() {
  formMode.value = 'create'
  form.value = emptyForm()
  formModalVisible.value = true
}

function onEdit() {
  if (!selectedEquipment.value) {
    message.warning('请先选择一台设备')
    return
  }
  formMode.value = 'edit'
  form.value = { ...emptyForm(), ...selectedEquipment.value }
  formModalVisible.value = true
}

// P3-3：操作列直接编辑，无需先选择行
function onEditRow(record) {
  if (!record) return
  formMode.value = 'edit'
  form.value = { ...emptyForm(), ...record }
  formModalVisible.value = true
}

async function onSubmitForm() {
  try {
    await formRef.value.validate()
  } catch {
    return // 校验未通过，不提交
  }
  formSubmitting.value = true
  try {
    if (formMode.value === 'create') {
      await createEquipment(form.value)
      message.success('设备已新增')
    } else {
      await updateEquipment(form.value.equipment_id, form.value)
      message.success('设备已更新')
    }
    formModalVisible.value = false
    selectedRowKeys.value = []
    selectedEquipment.value = null
    await onQuery()
  } catch {
    // 错误由拦截器处理
  } finally {
    formSubmitting.value = false
  }
}

async function onStatusChange(record, newStatus) {
  try {
    await updateEquipment(record.equipment_id, { ...record, status: newStatus })
    message.success(`状态已变更为「${statusLabel(newStatus)}」`)
    await onQuery()
  } catch {
    // 错误由拦截器处理
  }
}

// 操作菜单：状态变更 / 删除（2B 数据治理：被实验引用的设备后端会拒绝删除）
async function onActionClick(record, key) {
  if (key === 'delete') {
    Modal.confirm({
      title: '删除设备',
      content: `确定删除设备「${record.name || record.equipment_id}」吗？删除后不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteEquipment(record.equipment_id)
          message.success('设备已删除')
          await onQuery()
        } catch {
          // 错误（含被引用 409）由拦截器统一提示
        }
      },
    })
    return
  }
  await onStatusChange(record, key)
}

onMounted(async () => {
  onQuery()
  if (route.query.create === '1') {
    onAdd()
  }
  // 从 MDM 加载设备类别和状态选项（失败则保留硬编码兜底）
  try {
    const [categoryOpts, statusOpts] = await Promise.all([
      mdmClassificationOptions('equipment'),
      mdmStatusOptions('equipment'),
    ])
    if (categoryOpts.length) categoryOptions.value = categoryOpts
    if (statusOpts.length) statusOptions.value = statusOpts
  } catch (e) {
    console.warn('从 MDM 加载设备选项失败，使用硬编码兜底:', e)
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})
</script>

<style scoped>
.equipment-ledger {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.table-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  margin-bottom: 12px;
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

/* 统计卡语义着色：总数蓝 / 空闲绿 / 使用中橙 / 校准到期红 */
.stat-item:nth-child(1) .stat-value { color: var(--primary, #1d4ed8); }
.stat-item:nth-child(2) .stat-value { color: #047857; }
.stat-item:nth-child(3) .stat-value { color: #1d4ed8; }
.stat-item:nth-child(4) .stat-value { color: #dc2626; }

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
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

.eq-id {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state {
  padding: 24px 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.compact-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.compact-form :deep(.ant-form-item:last-child) {
  margin-bottom: 0;
}

/* P1-011：确保日期选择器弹出层不遮挡模态框底部的保存按钮 */
.equipment-ledger :deep(.ant-modal-footer) {
  position: relative;
  z-index: 1051;
}

/* P3-VIS-001：数据密集表格视觉层级优化 —— 数值/日期列等宽显示，单位与数值分层 */
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

/* P3-VIS-001：设备编号等宽加粗，便于扫描 */
.eq-id {
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-weight: 600;
  color: var(--text-primary);
}
</style>