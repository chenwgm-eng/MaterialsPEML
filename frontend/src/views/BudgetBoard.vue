<template>
  <div class="budget-board">
    <!-- Filter Bar -->
    <div class="filter-bar">
      <a-space wrap>
        <a-select
          v-model:value="filters.scope"
          placeholder="范围"
          allow-clear
          style="width: 160px"
          size="small"
        >
          <a-select-option value="organization">组织</a-select-option>
          <a-select-option value="project">项目</a-select-option>
          <a-select-option value="ecml_run">ECML 运行</a-select-option>
          <a-select-option value="committee_case">委员会案件</a-select-option>
          <a-select-option value="user">用户</a-select-option>
        </a-select>
        <a-select
          v-model:value="filters.scope_id"
          :options="scopeIdOptions"
          :loading="scopeIdLoading"
          :placeholder="filters.scope ? '范围 ID' : '请先选择范围'"
          :disabled="!filters.scope"
          allow-clear
          show-search
          style="width: 200px"
          size="small"
        />
        <a-button size="small" type="primary" @click="fetchBudgets" :loading="loading">
          <SearchOutlined /> 查询
        </a-button>
        <a-button size="small" @click="resetFilters">
          <FilterOutlined /> 重置
        </a-button>
        <a-button size="small" @click="fetchBudgets" :loading="loading">
          <ReloadOutlined /> 刷新
        </a-button>
        <a-button
          v-if="isAdmin"
          size="small"
          type="primary"
          ghost
          @click="openSetBudget"
        >
          <SettingOutlined /> 设置预算
        </a-button>
      </a-space>
    </div>

    <!-- Budget Table -->
    <a-card size="small" :body-style="{ padding: '12px' }">
      <a-table
        :columns="columns"
        :data-source="budgets"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(r) => (r.scope + '-' + r.scope_id + '-' + r.category)"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'scope'">
            <a-tag>{{ scopeLabel(record.scope) }}</a-tag>
          </template>
          <template v-if="column.key === 'category'">
            <a-tag>{{ categoryLabel(record.category) }}</a-tag>
          </template>
          <template v-if="column.key === 'usage'">
            <div class="usage-cell">
              <a-progress
                :percent="usagePercent(record)"
                :stroke-color="usageColor(usagePercent(record))"
                size="small"
                :show-info="false"
              />
              <span class="usage-text">{{ usagePercent(record) }}%</span>
            </div>
          </template>
          <template v-if="column.key === 'amount'">
            <span class="tabular-nums">{{ (record.reserved || 0) + (record.settled || 0) }} / {{ record.limit || 0 }}</span>
          </template>
          <template v-if="column.key === 'action_on_exhaustion'">
            <a-tag :color="exhaustionColor(record.action_on_exhaustion)">
              {{ exhaustionLabel(record.action_on_exhaustion) }}
            </a-tag>
          </template>
        </template>
        <template #emptyText>
          <div class="empty-hint">
            <a-empty :description="emptyDescription" />
            <a-button
              v-if="isAdmin && !budgets.length"
              size="small"
              type="primary"
              ghost
              style="margin-top: 8px"
              @click="openSetBudget"
            >
              <SettingOutlined /> 设置预算
            </a-button>
          </div>
        </template>
      </a-table>
    </a-card>

    <!-- Set Budget Drawer -->
    <a-drawer
      :open="modalVisible"
      title="设置预算"
      placement="right"
      width="480px"
      @update:open="(v) => (modalVisible = v)"
    >
      <a-form layout="vertical">
        <a-form-item label="范围">
          <a-select v-model:value="form.scope" placeholder="选择范围">
            <a-select-option value="organization">组织</a-select-option>
            <a-select-option value="project">项目</a-select-option>
            <a-select-option value="ecml_run">ECML 运行</a-select-option>
            <a-select-option value="committee_case">委员会案件</a-select-option>
            <a-select-option value="user">用户</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="范围 ID">
          <a-input v-model:value="form.scope_id" placeholder="范围 ID" />
        </a-form-item>
        <a-form-item label="类别">
          <a-select v-model:value="form.category" :options="categoryOptions" placeholder="选择类别" allow-clear show-search />
        </a-form-item>
        <a-form-item label="限额">
          <a-input-number v-model:value="form.limit" style="width: 100%" :min="0" placeholder="限额" />
        </a-form-item>
        <a-form-item label="耗尽时动作">
          <a-select v-model:value="form.action_on_exhaustion" placeholder="选择动作">
            <a-select-option value="block">阻断</a-select-option>
            <a-select-option value="warn">警告</a-select-option>
            <a-select-option value="degrade">降级</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="saving" @click="modalVisible = false">取消</a-button>
          <a-button type="primary" :loading="saving" @click="saveBudget">保存</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  SearchOutlined,
  FilterOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { useSystemStore } from '@/stores/system'
import { getBudgets, updateBudget, getRuns } from '@/api/controlPlane'
import client from '@/api/client'
import { listUsers } from '@/api/auth'
import { getCommitteeCases } from '@/api/committees'
import { useMdmDict } from '@/utils/mdmDict'
import { useAuth } from '@/composables/useAuth'

const systemStore = useSystemStore()
const { isAdmin } = useAuth()

// --- State ---
const budgets = ref([])
const loading = ref(false)
const modalVisible = ref(false)
const saving = ref(false)
let isMounted = true
onUnmounted(() => { isMounted = false })

const filters = reactive({
  scope: undefined,
  scope_id: undefined,
})

// 空状态提示：区分有/无项目过滤、admin/非 admin
const emptyDescription = computed(() => {
  if (filters.scope && filters.scope_id) {
    return isAdmin.value
      ? `该范围尚未配置预算信封，请点击下方「设置预算」创建`
      : `该范围尚未配置预算信封，请联系管理员配置`
  }
  return isAdmin.value
    ? `尚未配置任何预算信封，请点击上方「设置预算」创建`
    : `尚未配置任何预算信封，请联系管理员配置`
})

// --- Scope ID options (linked to filters.scope) ---
const scopeIdOptions = ref([])
const scopeIdLoading = ref(false)

async function loadScopeIdOptions() {
  // 保留仍合法的已选值（如项目上下文默认带入的 scope_id）；用户切换 scope 后旧值不在新选项中时才会清空
  const preserve = filters.scope_id
  filters.scope_id = undefined
  scopeIdOptions.value = []
  if (!filters.scope) return
  scopeIdLoading.value = true
  try {
    let list = []
    switch (filters.scope) {
      case 'organization':
        list = [{ value: 'default', label: '默认组织' }]
        break
      case 'project': {
        const res = await client.get('/projects')
        const arr = Array.isArray(res) ? res : (res.projects || res.items || [])
        list = arr.map((p) => ({ value: p.project_id, label: p.name || p.project_id }))
        break
      }
      case 'ecml_run': {
        const res = await getRuns()
        const arr = res.runs || res.items || []
        list = arr.map((r) => ({ value: r.run_id, label: r.run_id }))
        break
      }
      case 'committee_case': {
        const res = await getCommitteeCases({ limit: 200 })
        const arr = res.cases || res || []
        list = arr.map((c) => ({ value: c.case_id, label: c.case_id }))
        break
      }
      case 'user': {
        const res = await listUsers()
        const arr = Array.isArray(res) ? res : []
        list = arr.map((u) => ({ value: u.user_id, label: u.username || u.display_name || u.user_id }))
        break
      }
    }
    if (isMounted) scopeIdOptions.value = list
    if (preserve && list.some((o) => o.value === preserve)) filters.scope_id = preserve
  } catch {
    if (isMounted) scopeIdOptions.value = []
  } finally {
    if (isMounted) scopeIdLoading.value = false
  }
}

watch(() => filters.scope, loadScopeIdOptions)

const form = reactive({
  scope: undefined,
  scope_id: '',
  category: undefined,
  limit: 0,
  action_on_exhaustion: 'block',
})

// --- Table columns ---
const columns = [
  { title: '范围', key: 'scope', width: 120 },
  { title: '范围 ID', dataIndex: 'scope_id', key: 'scope_id', width: 140, ellipsis: true },
  { title: '类别', key: 'category', width: 120 },
  { title: '预留', dataIndex: 'reserved', key: 'reserved', width: 90 },
  { title: '已结算', dataIndex: 'settled', key: 'settled', width: 90 },
  { title: '用量 / 限额', key: 'amount', width: 140 },
  { title: '使用率', key: 'usage', width: 160 },
  { title: '耗尽动作', key: 'action_on_exhaustion', width: 100 },
]

// --- Label helpers ---
const scopeLabels = {
  organization: '组织',
  project: '项目',
  ecml_run: 'ECML 运行',
  committee_case: '委员会案件',
  user: '用户',
}
function scopeLabel(s) {
  return scopeLabels[s] || s || '-'
}

const CATEGORY_OPTIONS = [
  { label: '令牌', value: 'token' },
  { label: '外部调用', value: 'external_call' },
  { label: 'DFT CPU 时长', value: 'dft_cpu_hour' },
  { label: '成本', value: 'cost' },
  { label: '并发', value: 'concurrency' },
]
const categoryOptions = ref([...CATEGORY_OPTIONS])
function categoryLabel(c) {
  const found = categoryOptions.value.find((o) => o.value === c)
  return found ? found.label : c || '-'
}

const { dimensionOptions: mdmDimensionOptions } = useMdmDict()
async function loadMdmOptions() {
  try {
    const opts = await mdmDimensionOptions('cost_category')
    if (opts.length) {
      categoryOptions.value = opts
    } else {
      categoryOptions.value = [...CATEGORY_OPTIONS]
      message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
    }
  } catch (e) {
    categoryOptions.value = [...CATEGORY_OPTIONS]
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
}

const exhaustionLabels = {
  block: '阻断',
  warn: '警告',
  degrade: '降级',
}
function exhaustionLabel(a) {
  return exhaustionLabels[a] || a || '-'
}

const exhaustionColors = {
  block: 'error',
  warn: 'warning',
  degrade: 'orange',
}
function exhaustionColor(a) {
  return exhaustionColors[a] || 'default'
}

// --- Usage helpers ---
function usagePercent(b) {
  const used = (b.reserved || 0) + (b.settled || 0)
  const limit = b.limit
  if (!limit || limit <= 0) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

function usageColor(pct) {
  if (pct >= 90) return '#f97316'
  if (pct >= 70) return '#fb923c'
  return '#fdba74'
}

// --- API calls ---
async function fetchBudgets() {
  loading.value = true
  try {
    const params = {}
    if (filters.scope) params.scope = filters.scope
    if (filters.scope_id) params.scope_id = filters.scope_id
    const res = await getBudgets(params)
    if (!isMounted) return
    budgets.value = res.budgets || res.items || []
  } catch {
    if (isMounted) budgets.value = []
  } finally {
    if (isMounted) loading.value = false
  }
}

function resetFilters() {
  filters.scope = undefined
  filters.scope_id = undefined
  fetchBudgets()
}

function openSetBudget() {
  form.scope = undefined
  form.scope_id = ''
  form.category = undefined
  form.limit = 0
  form.action_on_exhaustion = 'block'
  modalVisible.value = true
}

async function saveBudget() {
  if (!form.scope || !form.scope_id || !form.category) {
    message.warning('请填写完整信息')
    return
  }
  saving.value = true
  try {
    await updateBudget(form.scope, {
      scope_id: form.scope_id,
      category: form.category,
      limit: form.limit,
      action_on_exhaustion: form.action_on_exhaustion,
    })
    if (!isMounted) return
    message.success('预算已更新')
    modalVisible.value = false
    await fetchBudgets()
  } catch {
    // handled by interceptor
  } finally {
    if (isMounted) saving.value = false
  }
}

// --- Lifecycle ---
onMounted(() => {
  // 进入页面时按当前显示的过滤条件查询（默认无过滤，显示全部预算）
  fetchBudgets()
  loadMdmOptions()
})
</script>

<style scoped>
.budget-board {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

/* Filter Bar */
.filter-bar {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px 16px;
  margin-bottom: 16px;
}

/* Usage Cell */
.usage-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.usage-cell :deep(.ant-progress) {
  flex: 1;
  min-width: 80px;
}

.usage-text {
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* Misc */
.tabular-nums {
  font-variant-numeric: tabular-nums;
}

/* Empty Hint */
.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
}
</style>
