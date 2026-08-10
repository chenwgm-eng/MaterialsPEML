<template>
  <div class="capability-center">
    <div class="page-header">
      <h1 class="page-title">能力契约</h1>
      <p class="page-subtitle">管理 AI 能力契约：风险等级、降级链与 SLA，确保调用可追溯</p>
    </div>
    <!-- 统计条 -->
    <div class="stat-row">
      <div class="stat-item">
        <span class="stat-value">{{ capabilities.length }}</span>
        <span class="stat-label">契约总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ activeCount }}</span>
        <span class="stat-label">活跃</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ pendingCount }}</span>
        <span class="stat-label">待审批</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ highRiskCount }}</span>
        <span class="stat-label">高风险</span>
      </div>
    </div>

    <!-- 过滤栏 -->
    <div class="filter-bar">
      <a-space wrap>
        <a-select
          v-model:value="filters.domain"
          placeholder="适用域"
          allow-clear
          style="width: 160px"
          size="small"
        >
          <a-select-option v-for="d in domainOptions" :key="d" :value="d">{{ d }}</a-select-option>
        </a-select>
        <a-select
          v-model:value="filters.risk_level"
          placeholder="风险等级"
          allow-clear
          style="width: 120px"
          size="small"
        >
          <a-select-option value="low">低</a-select-option>
          <a-select-option value="medium">中</a-select-option>
          <a-select-option value="high">高</a-select-option>
        </a-select>
        <a-select
          v-model:value="filters.status"
          placeholder="状态"
          allow-clear
          style="width: 120px"
          size="small"
        >
          <a-select-option value="active">活跃</a-select-option>
          <a-select-option value="pending_approval">待审批</a-select-option>
          <a-select-option value="deprecated">已废止</a-select-option>
        </a-select>
        <a-input
          v-model:value="filters.keyword"
          placeholder="搜索名称 / ID / 提供方 / 负责人"
          allow-clear
          style="width: 220px"
          size="small"
          @press-enter="applyFilters"
        />
        <a-button size="small" type="primary" @click="applyFilters">
          <SearchOutlined /> 查询
        </a-button>
        <a-button size="small" @click="resetFilters">
          <FilterOutlined /> 重置
        </a-button>
        <a-button size="small" @click="fetchCapabilities" :loading="loading">
          <ReloadOutlined /> 刷新
        </a-button>
        <a-button size="small" type="primary" @click="openRegister">
          <PlusOutlined /> 登记能力
        </a-button>
      </a-space>
    </div>

    <!-- 契约表格 -->
    <a-card size="small" :body-style="{ padding: '12px' }">
      <a-table
        :columns="columns"
        :data-source="filteredCapabilities"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => r.capability_id"
        :loading="loading"
        :custom-row="customRow"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <div class="name-cell">
              <span class="name-text">{{ record.name || '-' }}</span>
              <span class="text-muted id-text">{{ record.capability_id }}</span>
            </div>
          </template>
          <template v-if="column.key === 'provider'">
            <a-tag color="blue">{{ record.provider || '-' }}</a-tag>
          </template>
          <template v-if="column.key === 'risk_level'">
            <a-tag :color="riskColor(record.risk_level)">{{ riskLabel(record.risk_level) }}</a-tag>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'uncertainty_method'">
            <span class="text-muted">{{ record.uncertainty_method || '-' }}</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space size="small">
              <a-tooltip title="详情">
                <a-button size="small" aria-label="详情" @click.stop="openDetail(record)">
                  <ProfileOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip title="编辑">
                <a-button size="small" aria-label="编辑" @click.stop="openEdit(record)">
                  <EditOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip v-if="record.status === 'pending_approval'" title="审批">
                <a-button
                  size="small"
                  type="primary"
                  aria-label="审批"
                  :loading="actingId === record.capability_id"
                  @click.stop="onApprove(record)"
                >
                  <CheckOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip v-if="record.status !== 'deprecated'" title="废止">
                <a-button
                  size="small"
                  danger
                  aria-label="废止"
                  :loading="actingId === record.capability_id"
                  @click.stop="onDeprecate(record)"
                >
                  <StopOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip title="删除">
                <a-button
                  size="small"
                  aria-label="删除"
                  :loading="actingId === record.capability_id"
                  @click.stop="onDelete(record)"
                >
                  <DeleteOutlined />
                </a-button>
              </a-tooltip>
            </a-space>
          </template>
        </template>
        <template #emptyText>
          <EmptyState
            type="create"
            description="暂无能力契约数据"
            action-text="注册能力"
            :action-icon="PlusOutlined"
            @action="openRegister"
          />
        </template>
      </a-table>
    </a-card>

    <!-- 模型卡抽屉 -->
    <a-drawer
      :open="drawerVisible"
      :title="detail ? `模型卡：${detail.name || detail.capability_id}` : '模型卡'"
      placement="right"
      width="720px"
      :footer="null"
      @update:open="(v) => (drawerVisible = v)"
    >
      <a-spin :spinning="detailLoading">
        <template v-if="detail">
          <a-descriptions size="small" :column="1" bordered>
            <a-descriptions-item label="能力 ID">{{ detail.capability_id }}</a-descriptions-item>
            <a-descriptions-item label="名称">{{ detail.name || '-' }}</a-descriptions-item>
            <a-descriptions-item label="提供方">{{ detail.provider || '-' }}</a-descriptions-item>
            <a-descriptions-item label="版本">{{ detail.version || '-' }}</a-descriptions-item>
            <a-descriptions-item label="风险等级">
              <a-tag :color="riskColor(detail.risk_level)">{{ riskLabel(detail.risk_level) }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="状态">
              <a-tag :color="statusColor(detail.status)">{{ statusLabel(detail.status) }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="时延 SLA">{{ detail.latency_sla || '-' }}</a-descriptions-item>
            <a-descriptions-item label="不确定性方法">{{ detail.uncertainty_method || '-' }}</a-descriptions-item>
            <a-descriptions-item label="OOD 方法">{{ detail.ood_method || '-' }}</a-descriptions-item>
            <a-descriptions-item label="验证数据集">{{ detail.validation_dataset || '-' }}</a-descriptions-item>
            <a-descriptions-item label="负责人">{{ detail.owner || '-' }}</a-descriptions-item>
            <a-descriptions-item label="许可证">{{ detail.license || '-' }}</a-descriptions-item>
            <a-descriptions-item label="登记来源">{{ detail.source === 'auto' ? '自动' : '人工' }}</a-descriptions-item>
            <a-descriptions-item label="更新时间">{{ detail.updated_at || '-' }}</a-descriptions-item>
          </a-descriptions>

          <div class="section-title">适用域</div>
          <a-space size="small" wrap>
            <a-tag v-for="d in detail.supported_domains || []" :key="d" color="geekblue">{{ d }}</a-tag>
            <span v-if="!(detail.supported_domains || []).length" class="text-muted">-</span>
          </a-space>

          <div class="section-title">已知局限</div>
          <ul v-if="(detail.limitations || []).length" class="limitation-list">
            <li v-for="(lim, idx) in detail.limitations" :key="idx">{{ lim }}</li>
          </ul>
          <span v-else class="text-muted">-</span>

          <div class="section-title">输入 Schema</div>
          <SchemaViewer :data="detail.input_schema" />
          <div class="section-title">输出 Schema</div>
          <SchemaViewer :data="detail.output_schema" />
          <div class="section-title">成本模型</div>
          <SchemaViewer :data="detail.cost_model" />

          <div class="section-title">回退链</div>
          <a-spin :spinning="chainLoading">
            <div v-if="fallbackChain.length" class="fallback-list">
              <template v-for="(item, idx) in fallbackChain" :key="item.capability_id">
                <div
                  class="fallback-node"
                  :class="{ clickable: item.capability_id !== detail.capability_id }"
                  @click="jumpTo(item)"
                >
                  <span class="fallback-name">{{ item.name || item.capability_id }}</span>
                  <span class="text-muted">{{ item.capability_id }} · {{ item.version }}</span>
                  <a-tag :color="riskColor(item.risk_level)" size="small">{{ riskLabel(item.risk_level) }}</a-tag>
                </div>
                <div v-if="idx < fallbackChain.length - 1" class="fallback-arrow">↓</div>
              </template>
            </div>
            <span v-else class="text-muted">无回退路径</span>
          </a-spin>
        </template>
      </a-spin>
    </a-drawer>

    <!-- 登记能力抽屉 -->
    <a-drawer
      :open="registerVisible"
      :title="formMode === 'edit' ? '编辑能力契约' : '登记能力契约'"
      placement="right"
      width="720px"
      @update:open="(v) => onRegisterDrawerUpdate(v)"
    >
      <a-form layout="vertical" size="small">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="能力 ID" required>
              <a-input
                v-model:value="form.capability_id"
                placeholder="仅字母/数字/下划线/连字符，如 my_model_v1"
                :disabled="formMode === 'edit'"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="名称" required>
              <a-input v-model:value="form.name" placeholder="能力中文名" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="提供方" required>
              <a-input v-model:value="form.provider" placeholder="如 local/m3gnet" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="版本">
              <a-input v-model:value="form.version" placeholder="v1" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="风险等级">
              <a-select v-model:value="form.risk_level">
                <a-select-option value="low">低</a-select-option>
                <a-select-option value="medium">中</a-select-option>
                <a-select-option value="high">高</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="时延 SLA">
              <a-input v-model:value="form.latency_sla" placeholder="如 P95 < 60s" />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item label="适用域（回车添加）">
              <a-select v-model:value="form.supported_domains" mode="tags" :options="[]" placeholder="输入后回车" />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item label="已知局限（回车添加）">
              <a-select v-model:value="form.limitations" mode="tags" :options="[]" placeholder="输入后回车" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="不确定性方法">
              <a-input v-model:value="form.uncertainty_method" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="OOD 方法">
              <a-input v-model:value="form.ood_method" />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item label="回退链（可多选已有契约）">
              <a-select
                v-model:value="form.fallback_chain"
                mode="multiple"
                placeholder="选择回退契约"
                :options="fallbackOptions"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="验证数据集">
              <a-input v-model:value="form.validation_dataset" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="负责人">
              <a-input v-model:value="form.owner" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="许可证">
              <a-input v-model:value="form.license" />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item label="输入 Schema（JSON，可选）">
              <a-textarea v-model:value="form.input_schema_text" :rows="2" placeholder='{"field": "说明"}' />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item label="输出 Schema（JSON，可选）">
              <a-textarea v-model:value="form.output_schema_text" :rows="2" placeholder='{"field": "说明"}' />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item label="成本模型（JSON，可选）">
              <a-textarea v-model:value="form.cost_model_text" :rows="2" placeholder='{"unit": "次"}' />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <div class="text-muted register-tip">提交后状态为「待审批」，审批通过后生效。</div>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="submitting" @click="closeRegister">取消</a-button>
          <a-button type="primary" :loading="submitting" @click="onSubmit">
            {{ formMode === 'edit' ? '保存修改' : '保存' }}
          </a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted, h, defineComponent } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  SearchOutlined,
  FilterOutlined,
  ReloadOutlined,
  PlusOutlined,
  ProfileOutlined,
  CheckOutlined,
  StopOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  getCapabilities,
  approveCapability,
  deprecateCapability,
  createCapability,
  updateCapability,
  deleteCapability,
  getCapabilityFallbackChain,
} from '@/api/capabilities'

// --- State ---
const capabilities = ref([])
const loading = ref(false)
const actingId = ref('')
let isMounted = true
onUnmounted(() => { isMounted = false })

const filters = reactive({
  domain: undefined,
  risk_level: undefined,
  status: undefined,
  keyword: undefined,
})
const appliedKeyword = ref('')

const drawerVisible = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const fallbackChain = ref([])
const chainLoading = ref(false)

const registerVisible = ref(false)
const submitting = ref(false)
const formMode = ref('register') // 'register' | 'edit'
const formDirty = ref(false) // 表单是否有未保存修改
const emptyForm = () => ({
  capability_id: '',
  name: '',
  provider: '',
  version: 'v1',
  risk_level: 'medium',
  latency_sla: '',
  supported_domains: [],
  limitations: [],
  uncertainty_method: '',
  ood_method: '',
  fallback_chain: [],
  validation_dataset: '',
  owner: '',
  license: '',
  input_schema_text: '',
  output_schema_text: '',
  cost_model_text: '',
})
const form = reactive(emptyForm())

// --- Table columns ---
const columns = [
  { title: '名称', key: 'name', width: 220 },
  { title: '提供方', key: 'provider', width: 130 },
  { title: '版本', dataIndex: 'version', key: 'version', width: 70 },
  { title: '风险等级', key: 'risk_level', width: 90 },
  { title: '状态', key: 'status', width: 90 },
  { title: '不确定性方法', key: 'uncertainty_method', ellipsis: true },
  { title: '负责人', dataIndex: 'owner', key: 'owner', width: 110 },
  { title: '操作', key: 'actions', width: 220, fixed: 'right' },
]

// --- Computed ---
// 后端已按过滤条件返回数据，前端仅做 domain 内存过滤（JSON 数组检查）
const filteredCapabilities = computed(() => {
  if (!filters.domain) return capabilities.value
  return capabilities.value.filter((c) => (c.supported_domains || []).includes(filters.domain))
})

const domainOptions = computed(() => {
  const set = new Set()
  capabilities.value.forEach((c) => (c.supported_domains || []).forEach((d) => set.add(d)))
  return Array.from(set).sort()
})

const activeCount = computed(() => capabilities.value.filter((c) => c.status === 'active').length)
const pendingCount = computed(() => capabilities.value.filter((c) => c.status === 'pending_approval').length)
const highRiskCount = computed(() => capabilities.value.filter((c) => c.risk_level === 'high').length)

const fallbackOptions = computed(() =>
  capabilities.value
    .filter((c) => c.capability_id !== form.capability_id)
    .map((c) => ({ value: c.capability_id, label: `${c.name || c.capability_id}（${c.version}）` })),
)

// --- Label helpers ---
const riskLabels = { low: '低', medium: '中', high: '高' }
function riskLabel(r) {
  return riskLabels[r] || r || '-'
}
const riskColors = { low: 'green', medium: 'orange', high: 'red' }
function riskColor(r) {
  return riskColors[r] || 'default'
}

const statusLabels = { active: '活跃', pending_approval: '待审批', deprecated: '已废止' }
function statusLabel(s) {
  return statusLabels[s] || s || '-'
}
const statusColors = { active: 'green', pending_approval: 'orange', deprecated: 'default' }
function statusColor(s) {
  return statusColors[s] || 'default'
}

// 递归展示 schema/对象/数组，避免直接显示原始 JSON
const SchemaViewer = defineComponent({
  name: 'SchemaViewer',
  props: {
    data: { default: null },
  },
  setup(props) {
    const renderValue = (val) => {
      if (val === null || val === undefined || val === '') {
        return h('span', { class: 'text-muted' }, '-')
      }
      if (Array.isArray(val)) {
        if (val.length === 0) return h('span', { class: 'text-muted' }, '空')
        return h(
          'div',
          { class: 'schema-array' },
          val.map((v, i) => {
            if (v !== null && typeof v === 'object') {
              return h('div', { class: 'schema-array-item', key: i }, [h(SchemaViewer, { data: v })])
            }
            return h('a-tag', { key: i, color: 'blue' }, () => String(v))
          })
        )
      }
      if (typeof val === 'object') {
        return h(SchemaViewer, { data: val })
      }
      if (typeof val === 'boolean') {
        return h('span', String(val ? '是' : '否'))
      }
      return h('span', String(val))
    }

    return () => {
      const data = props.data
      if (data === null || data === undefined || data === '') {
        return h('span', { class: 'text-muted' }, '-')
      }
      if (Array.isArray(data)) {
        return renderValue(data)
      }
      if (typeof data === 'object') {
        const entries = Object.entries(data)
        if (entries.length === 0) return h('span', { class: 'text-muted' }, '-')
        return h(
          'a-descriptions',
          { size: 'small', column: 1, bordered: true },
          () => entries.map(([k, v]) => h('a-descriptions-item', { label: k }, () => renderValue(v)))
        )
      }
      return h('span', String(data))
    }
  }
})

// --- API calls ---
async function fetchCapabilities() {
  loading.value = true
  try {
    const params = {}
    if (filters.risk_level) params.risk_level = filters.risk_level
    if (filters.status) params.status = filters.status
    if (appliedKeyword.value) params.q = appliedKeyword.value
    const res = await getCapabilities(params)
    if (!isMounted) return
    capabilities.value = res.capabilities || res.items || []
  } catch (e) {
    if (isMounted) {
      capabilities.value = []
      message.error('加载能力契约列表失败')
    }
  } finally {
    if (isMounted) loading.value = false
  }
}

function applyFilters() {
  appliedKeyword.value = filters.keyword || ''
  fetchCapabilities()
}

function resetFilters() {
  filters.domain = undefined
  filters.risk_level = undefined
  filters.status = undefined
  filters.keyword = undefined
  appliedKeyword.value = ''
  fetchCapabilities()
}

function customRow(record) {
  return {
    onClick: () => openDetail(record),
  }
}

async function openDetail(record) {
  detail.value = record
  drawerVisible.value = true
  chainLoading.value = true
  fallbackChain.value = []
  try {
    const res = await getCapabilityFallbackChain(record.capability_id)
    if (!isMounted) return
    fallbackChain.value = res.chain || []
  } catch {
    if (isMounted) fallbackChain.value = []
  } finally {
    if (isMounted) chainLoading.value = false
  }
}

function jumpTo(item) {
  if (!detail.value || item.capability_id === detail.value.capability_id) return
  const target = capabilities.value.find((c) => c.capability_id === item.capability_id)
  if (target) openDetail(target)
}

async function onApprove(record) {
  actingId.value = record.capability_id
  const prevStatus = record.status
  // 乐观更新：先在前端切换状态，失败再回滚
  record.status = 'active'
  try {
    await approveCapability(record.capability_id)
    if (!isMounted) return
    message.success(`${record.name || record.capability_id} 已审批通过`)
    // 后台异步刷新整表，保证统计数据一致
    fetchCapabilities()
  } catch (e) {
    if (isMounted) {
      record.status = prevStatus
      message.error('审批失败')
    }
  } finally {
    if (isMounted) actingId.value = ''
  }
}

async function onDeprecate(record) {
  Modal.confirm({
    title: `确认废止「${record.name || record.capability_id}」？`,
    content: h('div', [
      h('p', { style: 'margin: 8px 0 4px' }, '废止后，该能力契约将对系统运行产生强制约束力：'),
      h('ul', { style: 'padding-left: 20px; margin: 4px 0; color: var(--error)' }, [
        h('li', '调用该能力的直接 API 端点将返回 403（除非有可用 fallback）'),
        h('li', '走 orchestrator 的任务将自动降级到 fallback 链中的下一个契约'),
        h('li', '若 fallback 链全部不可调用，相关功能将被阻断'),
      ]),
      h('p', { style: 'margin: 8px 0 0; color: var(--text-secondary)' }, '如需恢复，需重新审批通过该契约。'),
    ]),
    okText: '确认废止',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      actingId.value = record.capability_id
      const prevStatus = record.status
      record.status = 'deprecated'
      try {
        await deprecateCapability(record.capability_id)
        if (!isMounted) return
        message.success(`${record.name || record.capability_id} 已废止`)
        fetchCapabilities()
      } catch (e) {
        if (isMounted) {
          record.status = prevStatus
          message.error('废止失败')
        }
      } finally {
        if (isMounted) actingId.value = ''
      }
    },
  })
}

async function onDelete(record) {
  Modal.confirm({
    title: `确认删除「${record.name || record.capability_id}」？`,
    content: h('div', { style: 'margin-top: 8px; color: var(--text-secondary)' }, [
      h('p', '删除后该能力契约将永久移除，无法恢复。'),
      h('p', { style: 'color: var(--error); margin-top: 4px' }, '此操作不可撤销。'),
    ]),
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      actingId.value = record.capability_id
      try {
        await deleteCapability(record.capability_id)
        if (!isMounted) return
        message.success(`${record.name || record.capability_id} 已删除`)
        await fetchCapabilities()
      } catch (e) {
        if (isMounted) message.error('删除失败')
      } finally {
        if (isMounted) actingId.value = ''
      }
    },
  })
}

function openRegister() {
  Object.assign(form, emptyForm())
  formMode.value = 'register'
  registerVisible.value = true
  nextTick(() => { formDirty.value = false })
}

function openEdit(record) {
  Object.assign(form, emptyForm(), {
    capability_id: record.capability_id,
    name: record.name || '',
    provider: record.provider || '',
    version: record.version || 'v1',
    risk_level: record.risk_level || 'medium',
    latency_sla: record.latency_sla || '',
    supported_domains: record.supported_domains || [],
    limitations: record.limitations || [],
    uncertainty_method: record.uncertainty_method || '',
    ood_method: record.ood_method || '',
    fallback_chain: record.fallback_chain || [],
    validation_dataset: record.validation_dataset || '',
    owner: record.owner || '',
    license: record.license || '',
    input_schema_text: record.input_schema ? JSON.stringify(record.input_schema, null, 2) : '',
    output_schema_text: record.output_schema ? JSON.stringify(record.output_schema, null, 2) : '',
    cost_model_text: record.cost_model ? JSON.stringify(record.cost_model, null, 2) : '',
  })
  formMode.value = 'edit'
  registerVisible.value = true
  nextTick(() => { formDirty.value = false })
}

function closeRegister() {
  if (formDirty.value) {
    Modal.confirm({
      title: '确认放弃未保存的修改？',
      okText: '放弃',
      okType: 'danger',
      cancelText: '继续编辑',
      onOk() {
        registerVisible.value = false
      },
    })
  } else {
    registerVisible.value = false
  }
}

function onRegisterDrawerUpdate(v) {
  if (!v && formDirty.value) {
    Modal.confirm({
      title: '确认放弃未保存的修改？',
      okText: '放弃',
      okType: 'danger',
      cancelText: '继续编辑',
      onOk() {
        registerVisible.value = false
      },
    })
  } else {
    registerVisible.value = v
  }
}

// 监听表单变化，标记 dirty
watch(form, () => { formDirty.value = true }, { deep: true })

function parseJsonField(text, label) {
  if (!text || !text.trim()) return {}
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`${label} 不是合法 JSON`)
  }
}

async function onSubmit() {
  if (!form.capability_id.trim()) {
    message.warning('请填写能力 ID')
    return
  }
  // capability_id 格式校验
  if (!/^[a-zA-Z0-9_-]+$/.test(form.capability_id.trim())) {
    message.warning('能力 ID 仅允许字母、数字、下划线和连字符')
    return
  }
  if (!form.name.trim()) {
    message.warning('请填写名称')
    return
  }
  if (!form.provider.trim()) {
    message.warning('请填写提供方')
    return
  }
  let payload
  try {
    payload = {
      capability_id: form.capability_id.trim(),
      name: form.name.trim(),
      provider: form.provider.trim(),
      version: form.version.trim() || 'v1',
      risk_level: form.risk_level,
      latency_sla: form.latency_sla.trim(),
      supported_domains: form.supported_domains,
      limitations: form.limitations,
      uncertainty_method: form.uncertainty_method.trim(),
      ood_method: form.ood_method.trim(),
      fallback_chain: form.fallback_chain,
      validation_dataset: form.validation_dataset.trim(),
      owner: form.owner.trim(),
      license: form.license.trim(),
      input_schema: parseJsonField(form.input_schema_text, '输入 Schema'),
      output_schema: parseJsonField(form.output_schema_text, '输出 Schema'),
      cost_model: parseJsonField(form.cost_model_text, '成本模型'),
    }
  } catch (e) {
    message.error(e.message)
    return
  }
  submitting.value = true
  try {
    if (formMode.value === 'edit') {
      await updateCapability(form.capability_id, payload)
      if (!isMounted) return
      message.success('修改已保存')
    } else {
      await createCapability(payload)
      if (!isMounted) return
      message.success('登记成功，等待审批')
    }
    formDirty.value = false
    registerVisible.value = false
    await fetchCapabilities()
  } catch (e) {
    if (isMounted) message.error(formMode.value === 'edit' ? '保存修改失败' : '登记失败')
  } finally {
    if (isMounted) submitting.value = false
  }
}

// --- Lifecycle ---
onMounted(fetchCapabilities)
</script>

<style scoped>
.capability-center {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

/* 统计条 */
.stat-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.stat-item {
  flex: 1;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 14px 18px;
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

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

/* 过滤栏 */
.filter-bar {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px 16px;
  margin-bottom: 16px;
}

/* 表格名称列 */
.name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.name-text {
  font-weight: 600;
  color: var(--text-primary);
}

.id-text {
  font-size: 12px;
  font-family: var(--font-family-mono);
}

/* 抽屉 */
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 16px 0 8px;
}

.limitation-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.8;
}

.schema-array {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.schema-array-item {
  width: 100%;
}

.fallback-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.fallback-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--light-bg-card);
}

.fallback-node.clickable {
  cursor: pointer;
}

.fallback-node.clickable:hover {
  background: var(--light-bg-hover);
}

.fallback-name {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13px;
}

.fallback-arrow {
  text-align: center;
  color: var(--text-muted);
  line-height: 1.4;
  font-size: 12px;
}

.text-muted {
  color: var(--text-muted);
  font-size: 13px;
}

.register-tip {
  margin-top: 4px;
}
</style>
