<template>
  <div class="data-ingest">
    <div class="page-header">
      <div>
        <h1 class="page-title">数据接入</h1>
        <p class="page-subtitle">Excel/CSV 历史数据导入：自动字段映射、质量检查、幂等写入统一数据模型</p>
        <p class="page-usage-hint">使用说明：上传历史实验表格后系统自动匹配字段；导入完成后数据进入实验数据页可查询</p>
      </div>
    </div>

    <a-card size="small" :body-style="{ padding: '12px' }">
      <a-steps :current="currentStep" size="small" class="ingest-steps">
        <a-step title="上传文件" />
        <a-step title="字段映射" />
        <a-step title="质量报告" />
        <a-step title="确认导入" />
      </a-steps>

      <!-- 步骤 1：上传文件 -->
      <div v-show="currentStep === 0" class="step-body">
        <div class="entity-bar">
          <span class="bar-label">实体类型：</span>
          <a-radio-group v-model:value="entityType" size="small" @change="resetFile">
            <a-radio-button v-for="opt in entityTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</a-radio-button>
          </a-radio-group>
        </div>

        <a-upload-dragger
          accept=".xlsx,.xls,.csv"
          :show-upload-list="false"
          :before-upload="beforeUpload"
          class="upload-area"
          data-testid="ingest-file-upload"
        >
          <p class="ant-upload-drag-icon"><InboxOutlined /></p>
          <p class="ant-upload-text">点击或拖拽 Excel/CSV 文件到此区域</p>
          <p class="ant-upload-hint">前端解析，单次最多 500 行；支持 .xlsx / .xls / .csv</p>
        </a-upload-dragger>

        <template v-if="fileName">
          <a-alert type="info" show-icon class="file-alert">
            <template #message>
              文件：{{ fileName }}，共 {{ totalRowCount }} 行
              <template v-if="truncated">（超出 500 行，已截断取前 500 行）</template>
            </template>
          </a-alert>
          <a-table
            :columns="previewColumns"
            :data-source="rows.slice(0, 5)"
            :pagination="false"
            size="small"
            :row-key="previewRowKey"
            :scroll="{ x: true }"
            class="preview-table"
          >
            <template #title>前 5 行预览</template>
          </a-table>
        </template>
      </div>

      <!-- 步骤 2：字段映射 -->
      <div v-show="currentStep === 1" class="step-body">
        <a-spin :spinning="mappingLoading">
          <div class="ratio-bar">
            <span class="bar-label">自动映射率：</span>
            <a-progress
              :percent="Math.round(autoMappedRatio * 100)"
              size="small"
              style="width: 240px"
              :status="autoMappedRatio >= 0.8 ? 'success' : 'active'"
            />
            <span class="ratio-hint">目标 ≥ 80%，未自动映射的字段可手动选择源列</span>
          </div>
          <a-alert
            v-if="unmappedColumns.length"
            type="warning"
            show-icon
            class="unmapped-alert"
            :message="`未映射源列（不会导入）：${unmappedColumns.join('、')}`"
          />
          <a-table
            :columns="mappingColumns"
            :data-source="fieldDict"
            :pagination="false"
            size="small"
            row-key="key"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'label'">
                <span :class="{ 'required-star': record.required }">{{ record.label }}</span>
                <a-tag class="type-tag" :color="typeColor(record.type)">{{ typeLabel(record.type) }}</a-tag>
              </template>
              <template v-if="column.key === 'source'">
                <a-select
                  :value="mapping[record.key] ? mapping[record.key].column : ''"
                  size="small"
                  style="width: 220px"
                  placeholder="选择源列"
                  allow-clear
                  :options="sourceColumnOptions"
                  @change="(val) => onMappingChange(record.key, val)"
                />
              </template>
              <template v-if="column.key === 'confidence'">
                <a-tag v-if="confidenceOf(record.key) === 'exact'" color="green">精确</a-tag>
                <a-tag v-else-if="confidenceOf(record.key) === 'alias'" color="blue">别名</a-tag>
                <a-tag v-else-if="confidenceOf(record.key) === 'fuzzy'" color="orange">模糊</a-tag>
                <a-tag v-else-if="confidenceOf(record.key) === 'manual'" color="purple">手动</a-tag>
                <span v-else class="text-muted">未映射</span>
              </template>
            </template>
          </a-table>
        </a-spin>
      </div>

      <!-- 步骤 3：质量报告 -->
      <div v-show="currentStep === 2" class="step-body">
        <a-spin :spinning="qualityLoading">
          <template v-if="quality">
            <div class="stat-grid">
              <a-card size="small" :bordered="false" class="stat-card"><a-statistic title="缺失(必填)" :value="quality.summary.missing_required" /></a-card>
              <a-card size="small" :bordered="false" class="stat-card"><a-statistic title="非法值" :value="quality.summary.illegal_values" /></a-card>
              <a-card size="small" :bordered="false" class="stat-card"><a-statistic title="单位问题" :value="quality.summary.unit_issues" /></a-card>
              <a-card size="small" :bordered="false" class="stat-card"><a-statistic title="异常值(IQR)" :value="quality.summary.outliers" /></a-card>
              <a-card size="small" :bordered="false" class="stat-card"><a-statistic title="重复(文件内)" :value="quality.summary.duplicates" /></a-card>
              <a-card size="small" :bordered="false" class="stat-card"><a-statistic title="未映射字段" :value="quality.summary.unmapped_fields" /></a-card>
            </div>
            <a-table
              :columns="qualityColumns"
              :data-source="quality.rows"
              :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
              size="small"
              row-key="row_index"
              :scroll="{ y: 420 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'row_index'">{{ record.row_index + 1 }}</template>
                <template v-if="column.key === 'status'">
                  <a-tag :color="rowStatusColor(record.status)">{{ rowStatusLabel(record.status) }}</a-tag>
                </template>
                <template v-if="column.key === 'issues'">
                  <span v-if="record.issues.length">{{ record.issues.join('；') }}</span>
                  <span v-else class="text-muted">—</span>
                </template>
              </template>
            </a-table>
          </template>
        </a-spin>
      </div>

      <!-- 步骤 4：确认导入 -->
      <div v-show="currentStep === 3" class="step-body">
        <a-descriptions size="small" bordered :column="2" class="commit-summary">
          <a-descriptions-item label="实体类型">{{ entityTypeLabel(entityType) }}</a-descriptions-item>
          <a-descriptions-item label="文件名">{{ fileName }}</a-descriptions-item>
          <a-descriptions-item label="总行数">{{ rows.length }}</a-descriptions-item>
          <a-descriptions-item label="预计成功">{{ expectedSuccess }}</a-descriptions-item>
          <a-descriptions-item label="预计失败">{{ expectedFailed }}</a-descriptions-item>
          <a-descriptions-item label="幂等键">{{ idempotencyKey }}</a-descriptions-item>
        </a-descriptions>
        <div class="operator-bar">
          <span class="bar-label">操作人：</span>
          <a-input v-model:value="operator" size="small" style="width: 200px" placeholder="请输入操作人" />
        </div>

        <a-alert
          v-if="commitResult"
          :type="commitResult.failed_rows > 0 ? 'warning' : 'success'"
          show-icon
          class="commit-result"
        >
          <template #message>
            导入完成：成功 {{ commitResult.success_rows }} 行，失败 {{ commitResult.failed_rows }} 行
            <template v-if="commitResult.duplicated">（重复提交，已命中幂等键，未重复写入）</template>
            ，批次号 {{ commitResult.import_id }}
          </template>
          <template #description>
            <div v-if="commitResult.errors && commitResult.errors.length" class="error-list">
              <div v-for="e in commitResult.errors" :key="e.row_index">第 {{ e.row_index + 1 }} 行：{{ e.error }}</div>
            </div>
          </template>
        </a-alert>
      </div>

      <!-- 步骤操作按钮 -->
      <div class="step-actions">
        <a-button v-if="currentStep > 0" size="small" @click="currentStep--">上一步</a-button>
        <DisabledButton
          v-if="currentStep === 0"
          type="primary"
          size="small"
          :disabled="!rows.length"
          disabled-reason="请先上传或粘贴数据后再进入字段映射"
          @click="enterMapping"
        >下一步</DisabledButton>
        <a-button v-if="currentStep === 1" type="primary" size="small" :loading="qualityLoading" @click="enterQuality">下一步</a-button>
        <a-button v-if="currentStep === 2" type="primary" size="small" @click="currentStep = 3">下一步</a-button>
        <DisabledButton
          v-if="currentStep === 3"
          type="primary"
          size="small"
          :loading="committing"
          :disabled="!operator.trim()"
          disabled-reason="请先填写操作人姓名后再开始导入"
          @click="onCommit"
        >开始导入</DisabledButton>
      </div>
    </a-card>

    <!-- 导入历史 -->
    <a-card title="导入历史" size="small" :body-style="{ padding: '12px' }" class="history-card">
      <template #extra>
        <a-button size="small" @click="fetchImports"><ReloadOutlined /> 刷新</a-button>
      </template>
      <a-table
        :columns="historyColumns"
        :data-source="imports"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        row-key="import_id"
        :loading="importsLoading"
      >
        <template #emptyText>
          <div style="padding: 20px 0">
            <InboxOutlined style="font-size: 28px; color: var(--text-muted)" />
            <div style="margin-top: 8px; color: var(--text-muted)">暂无导入记录，请在上方上传第一个文件开始导入</div>
          </div>
        </template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'entity_type'">{{ entityTypeLabel(record.entity_type) || record.entity_type }}</template>
          <template v-if="column.key === 'status'">
            <a-tag :color="importStatusColor(record.status)">{{ importStatusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'created_at'">{{ formatTime(record.created_at) }}</template>
          <template v-if="column.key === 'actions'">
            <a-button type="link" size="small" @click="openDetail(record)">查看明细</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 批次明细抽屉 -->
    <a-drawer
      :open="detailVisible"
      title="导入批次明细"
      placement="right"
      width="720px"
      :footer="null"
      @update:open="(v) => (detailVisible = v)"
    >
      <a-spin :spinning="detailLoading">
        <template v-if="detail">
          <a-descriptions size="small" bordered :column="2" class="detail-desc">
            <a-descriptions-item label="批次号">{{ detail.import_id }}</a-descriptions-item>
            <a-descriptions-item label="实体">{{ entityTypeLabel(detail.entity_type) || detail.entity_type }}</a-descriptions-item>
            <a-descriptions-item label="文件名">{{ detail.file_name }}</a-descriptions-item>
            <a-descriptions-item label="操作人">{{ detail.operator || '—' }}</a-descriptions-item>
            <a-descriptions-item label="总数/成功/失败">{{ detail.total_rows }} / {{ detail.success_rows }} / {{ detail.failed_rows }}</a-descriptions-item>
            <a-descriptions-item label="状态">
              <a-tag :color="importStatusColor(detail.status)">{{ importStatusLabel(detail.status) }}</a-tag>
            </a-descriptions-item>
          </a-descriptions>
          <a-table
            :columns="detailRowColumns"
            :data-source="detail.rows"
            :pagination="{ pageSize: 10, size: 'small' }"
            size="small"
            row-key="id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'row_index'">{{ record.row_index + 1 }}</template>
              <template v-if="column.key === 'status'">
                <a-tag :color="record.status === 'success' ? 'green' : 'red'">{{ record.status === 'success' ? '成功' : '失败' }}</a-tag>
              </template>
              <template v-if="column.key === 'error'">
                <span v-if="record.error">{{ record.error }}</span>
                <span v-else class="text-muted">—</span>
              </template>
            </template>
          </a-table>
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import DisabledButton from '@/components/DisabledButton.vue'
import * as XLSX from 'xlsx'
import { getFieldDict, previewIngest, commitIngest, listImports, getImportDetail } from '@/api/ingest'
import { getUserId } from '@/api/client'
import { useMdmDict } from '@/utils/mdmDict'

const ENTITY_LABELS = { sample: '样品', equipment: '设备', raw_material: '原料', project: '项目' }
const entityTypeOptions = ref(
  Object.entries(ENTITY_LABELS).map(([value, label]) => ({ label, value })),
)
function entityTypeLabel(key) {
  const opt = entityTypeOptions.value.find((o) => o.value === key)
  return opt ? opt.label : key
}
const MAX_ROWS = 500

// 预览表行 key：行内容哈希，避免使用弃用的 index 参数
const previewRowKey = (r) => {
  if (!r) return Math.random().toString(36).slice(2)
  return JSON.stringify(r).slice(0, 64)
}

const currentStep = ref(0)
const entityType = ref('sample')

// 步骤 1：文件
const fileName = ref('')
const fileHash = ref('')
const rows = ref([])
const totalRowCount = ref(0)
const truncated = ref(false)

// 步骤 2：映射
const fieldDict = ref([])
const mapping = ref({})
const unmappedColumns = ref([])
const autoMappedRatio = ref(0)
const mappingLoading = ref(false)

// 步骤 3：质量
const quality = ref(null)
const qualityLoading = ref(false)

// 步骤 4：提交
const operator = ref(getUserId() || '')
const committing = ref(false)
const commitResult = ref(null)

// 导入历史
const imports = ref([])
const importsLoading = ref(false)
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
let isMounted = true
onUnmounted(() => { isMounted = false })

const previewColumns = computed(() => {
  if (!rows.value.length) return []
  return Object.keys(rows.value[0]).slice(0, 8).map((k) => ({
    title: k, dataIndex: k, key: k, ellipsis: true,
  }))
})

const sourceColumnOptions = computed(() => {
  if (!rows.value.length) return []
  return Object.keys(rows.value[0]).map((c) => ({ value: c, label: c }))
})

const mappingColumns = [
  { title: '目标字段', key: 'label', width: 180 },
  { title: '源列', key: 'source', width: 240 },
  { title: '匹配方式', key: 'confidence', width: 100 },
]

const qualityColumns = [
  { title: '行号', key: 'row_index', width: 60 },
  { title: '状态', key: 'status', width: 80 },
  { title: '问题描述', key: 'issues' },
]

const historyColumns = [
  { title: '批次号', dataIndex: 'import_id', key: 'import_id', width: 150 },
  { title: '实体', dataIndex: 'entity_type', key: 'entity_type', width: 70 },
  { title: '文件名', dataIndex: 'file_name', key: 'file_name', width: 160, ellipsis: true },
  { title: '操作人', dataIndex: 'operator', key: 'operator', width: 90 },
  { title: '总数', dataIndex: 'total_rows', key: 'total_rows', width: 60 },
  { title: '成功', dataIndex: 'success_rows', key: 'success_rows', width: 60 },
  { title: '失败', dataIndex: 'failed_rows', key: 'failed_rows', width: 60 },
  { title: '状态', key: 'status', width: 90 },
  { title: '时间', key: 'created_at', width: 150 },
  { title: '操作', key: 'actions', width: 90 },
]

const detailRowColumns = [
  { title: '行号', key: 'row_index', width: 60 },
  { title: '状态', key: 'status', width: 80 },
  { title: '错误/警告', key: 'error' },
]

const expectedSuccess = computed(() => {
  if (!quality.value) return rows.value.length
  return quality.value.summary.ok + quality.value.summary.warning
})
const expectedFailed = computed(() => (quality.value ? quality.value.summary.error : 0))
const idempotencyKey = computed(() => `${entityType.value}:${fileHash.value}`)

function cyrb53(buffer, seed = 0) {
  const bytes = new Uint8Array(buffer)
  let h1 = 0xdeadbeef ^ seed
  let h2 = 0x41c6ce57 ^ seed
  for (let i = 0; i < bytes.length; i++) {
    h1 = Math.imul(h1 ^ bytes[i], 2654435761)
    h2 = Math.imul(h2 ^ bytes[i], 1597334677)
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909)
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909)
  return (h2 >>> 0).toString(16).padStart(8, '0') + (h1 >>> 0).toString(16).padStart(8, '0')
}

function beforeUpload(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const buffer = e.target.result
      const wb = XLSX.read(buffer, { type: 'array' })
      const ws = wb.Sheets[wb.SheetNames[0]]
      const parsed = XLSX.utils.sheet_to_json(ws, { defval: '' })
      if (!parsed.length) {
        message.warning('文件解析结果为空')
        return
      }
      fileName.value = file.name
      fileHash.value = cyrb53(buffer)
      totalRowCount.value = parsed.length
      truncated.value = parsed.length > MAX_ROWS
      rows.value = parsed.slice(0, MAX_ROWS)
      if (truncated.value) {
        message.warning(`共 ${parsed.length} 行，超出 ${MAX_ROWS} 行上限，已截断`)
      }
      // 切换文件后重置后续步骤
      mapping.value = {}
      quality.value = null
      commitResult.value = null
      message.success(`解析成功：${parsed.length} 行`)
    } catch (err) {
      message.error(`文件解析失败：${err.message}`)
    }
  }
  reader.readAsArrayBuffer(file)
  return false // 阻止自动上传
}

function resetFile() {
  fileName.value = ''
  fileHash.value = ''
  rows.value = []
  totalRowCount.value = 0
  truncated.value = false
  mapping.value = {}
  quality.value = null
  commitResult.value = null
}

async function enterMapping() {
  mappingLoading.value = true
  try {
    const [dictResp, previewResp] = await Promise.all([
      getFieldDict(entityType.value),
      previewIngest({ entity_type: entityType.value, rows: rows.value }),
    ])
    if (!isMounted) return
    fieldDict.value = dictResp.fields
    mapping.value = { ...previewResp.mapping }
    unmappedColumns.value = previewResp.unmapped_columns
    autoMappedRatio.value = previewResp.auto_mapped_ratio
    currentStep.value = 1
  } catch {
    // 错误由拦截器处理
  } finally {
    if (isMounted) mappingLoading.value = false
  }
}

function onMappingChange(key, val) {
  mapping.value[key] = {
    column: val || '',
    confidence: val ? 'manual' : 'none',
    auto: false,
  }
}

function confidenceOf(key) {
  const m = mapping.value[key]
  if (!m || !m.column) return 'none'
  return m.confidence
}

async function enterQuality() {
  qualityLoading.value = true
  try {
    const resp = await previewIngest({
      entity_type: entityType.value,
      rows: rows.value,
      mapping: mapping.value,
    })
    if (!isMounted) return
    quality.value = resp.quality
    currentStep.value = 2
  } catch {
    // 错误由拦截器处理
  } finally {
    if (isMounted) qualityLoading.value = false
  }
}

async function onCommit() {
  committing.value = true
  commitResult.value = null
  try {
    const resp = await commitIngest({
      entity_type: entityType.value,
      rows: rows.value,
      mapping: mapping.value,
      idempotency_key: idempotencyKey.value,
      file_name: fileName.value,
      operator: operator.value.trim(),
    })
    if (!isMounted) return
    commitResult.value = resp
    if (resp.duplicated) {
      message.info('检测到重复提交，已返回首次导入结果，未重复写入')
    } else {
      message.success(`导入完成：成功 ${resp.success_rows} 行，失败 ${resp.failed_rows} 行`)
    }
    await fetchImports()
  } catch (err) {
    // 增加操作级错误提示，避免静默失败（BPEML-INGEST-P0-001）
    const detail = err?.response?.data?.detail || err?.message || '未知错误'
    message.error(`导入失败：${detail}`)
  } finally {
    if (isMounted) committing.value = false
  }
}

async function fetchImports() {
  importsLoading.value = true
  try {
    const resp = await listImports({ limit: 100 })
    if (!isMounted) return
    imports.value = resp.items || []
  } catch {
    if (isMounted) imports.value = []
  } finally {
    if (isMounted) importsLoading.value = false
  }
}

async function openDetail(record) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getImportDetail(record.import_id)
  } catch {
    // 错误由拦截器处理
  } finally {
    if (isMounted) detailLoading.value = false
  }
}

function typeLabel(t) {
  return { string: '文本', number: '数值', date: '日期' }[t] || t
}
function typeColor(t) {
  return { string: 'default', number: 'blue', date: 'cyan' }[t] || 'default'
}
function rowStatusColor(s) {
  return { ok: 'green', warning: 'orange', error: 'red' }[s] || 'default'
}
function rowStatusLabel(s) {
  return { ok: '通过', warning: '警告', error: '错误' }[s] || s
}
function importStatusColor(s) {
  return { processing: 'processing', success: 'green', partial: 'orange', failed: 'red' }[s] || 'default'
}
function importStatusLabel(s) {
  return { processing: '处理中', success: '成功', partial: '部分成功', failed: '失败' }[s] || s
}
function formatTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

onMounted(async () => {
  const { dimensionOptions } = useMdmDict()
  try {
    const loaded = await dimensionOptions('data_source_type')
    entityTypeOptions.value = loaded.length ? loaded : Object.entries(ENTITY_LABELS).map(([value, label]) => ({ label, value }))
    if (!loaded.length) {
      message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
    }
  } catch (e) {
    entityTypeOptions.value = Object.entries(ENTITY_LABELS).map(([value, label]) => ({ label, value }))
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
  fetchImports()
})
</script>

<style scoped>
.data-ingest {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 4px 0;
  color: var(--text-primary);
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.ingest-steps {
  margin-bottom: 16px;
}

.step-body {
  min-height: 300px;
}

.entity-bar,
.ratio-bar,
.operator-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.bar-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
}

.ratio-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.upload-area {
  margin-bottom: 12px;
}

.file-alert,
.unmapped-alert {
  margin-bottom: 12px;
}

.preview-table {
  margin-bottom: 8px;
}

.required-star::before {
  content: '*';
  color: #ff4d4f;
  margin-right: 4px;
}

.type-tag {
  margin-left: 6px;
  font-size: 11px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  border-radius: var(--radius-md);
  background: var(--light-bg-card);
  border: 1px solid var(--border);
}

.commit-summary {
  margin-bottom: 12px;
}

.commit-result {
  margin-top: 12px;
}

.error-list {
  font-size: 12px;
  max-height: 160px;
  overflow-y: auto;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border, #e8e8e8);
}

.history-card {
  margin-top: 16px;
}

.detail-desc {
  margin-bottom: 12px;
}

.text-muted {
  color: var(--text-muted);
}
</style>
