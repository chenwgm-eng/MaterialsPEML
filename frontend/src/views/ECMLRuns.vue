<template>
  <div class="ecml-runs">
    <div class="page-header">
      <div class="header-text">
        <h1 class="page-title">迭代历史</h1>
        <p class="page-subtitle">查看、继续或管理历史实验闭环迭代运行</p>
      </div>
    </div>

    <a-card class="runs-card" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">运行记录</span>
          <a-space>
            <a-button type="primary" size="small" @click="goToNewRun">
              <PlusOutlined /> 新建实验闭环迭代
            </a-button>
            <a-radio-group v-model:value="envFilter" size="small" button-style="solid">
              <a-radio-button value="production">正式</a-radio-button>
              <a-radio-button value="sandbox">测试</a-radio-button>
              <a-radio-button value="all">全部</a-radio-button>
            </a-radio-group>
            <a-popconfirm
              v-if="selectedRowKeys.length > 0"
              :title="`确认批量删除选中的 ${selectedRowKeys.length} 条记录？该操作会保留审计日志。`"
              ok-text="删除"
              cancel-text="取消"
              @confirm="bulkRemove"
            >
              <a-button size="small" danger>批量删除 ({{ selectedRowKeys.length }})</a-button>
            </a-popconfirm>
            <a-popconfirm
              v-if="sandboxRuns.length > 0 && envFilter !== 'production'"
              :title="`确认清空 ${sandboxRuns.length} 条测试记录？该操作会保留审计日志。`"
              ok-text="删除"
              cancel-text="取消"
              @confirm="clearSandboxRuns"
            >
              <a-button size="small" danger>清空测试数据</a-button>
            </a-popconfirm>
          </a-space>
        </div>
      </template>

      <!-- 筛选条件 -->
      <div class="filter-bar">
        <a-select
          v-model:value="filterProjectId"
          :options="projectOptions"
          placeholder="选择项目"
          size="small"
          style="width: 180px"
          allow-clear
          show-search
          option-filter-prop="label"
          @change="onProjectChange"
        />
        <a-select
          v-model:value="filterTaskId"
          :options="taskOptions"
          :placeholder="filterProjectId ? '选择任务' : '请先选择项目'"
          :disabled="!filterProjectId"
          size="small"
          style="width: 180px"
          allow-clear
          show-search
          option-filter-prop="label"
        />
        <a-button size="small" @click="resetFilter">重置</a-button>
      </div>
      <a-table
        :data-source="filteredRuns"
        :columns="columns"
        :loading="loading"
        :pagination="{ pageSize: 10, showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'] }"
        :row-selection="{ selectedRowKeys, onChange: (keys) => (selectedRowKeys = keys) }"
        :scroll="{ x: 1400 }"
        row-key="run_id"
        :custom-row="runRowProps"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'is_complete'">
            <a-tag v-if="record.status === 'timeout'" color="red">超时失败</a-tag>
            <a-tag v-else-if="record.is_complete" color="green">已完成</a-tag>
            <a-tag v-else color="blue">进行中</a-tag>
          </template>
          <template v-else-if="column.key === 'updated_at'">
            {{ record.updated_at ? new Date(record.updated_at).toLocaleString() : '-' }}
          </template>
          <template v-else-if="column.key === 'env'">
            <a-tooltip v-if="isSandboxRun(record)" title="系统测试/调试数据，已从首页统计与生产视图中隔离">
              <a-tag color="orange">测试</a-tag>
            </a-tooltip>
            <a-tag v-else color="blue">正式</a-tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="viewRun(record)">查看</a-button>
              <a-button v-if="!record.is_complete" type="link" size="small" @click="continueRun(record)">
                继续
              </a-button>
              <a-popconfirm
                title="确认删除该运行记录？"
                ok-text="删除"
                cancel-text="取消"
                @confirm="removeRun(record)"
              >
                <a-button type="link" danger size="small">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { getEcmlRuns, deleteECMLRun, bulkDeleteECMLRuns } from '@/api/ecml'
import { listProjects } from '@/api/projects'
import { useProjectContextStore } from '@/stores/projectContext'
import client from '@/api/client'

const router = useRouter()
const projectCtx = useProjectContextStore()

const runs = ref([])
const loading = ref(false)
// P0-4：测试数据默认对生产视图隐藏，需主动切换"测试/全部"才可见
const envFilter = ref('production')
const selectedRowKeys = ref([])

// 筛选条件：项目 + 任务（#3：自动跟随左侧「项目定位」全局上下文）
const filterProjectId = ref(undefined)
const filterTaskId = ref(undefined)
const projectOptions = ref([])
const taskOptions = ref([])

// 全局上下文联动：左侧选择项目/任务后，本页筛选自动跟随
watch(
  () => [projectCtx.currentProjectId, projectCtx.currentTaskId],
  ([pid, tid]) => {
    if (pid && filterProjectId.value !== pid) {
      filterProjectId.value = pid
      loadProjectTasks(pid)
    }
    if (tid && filterTaskId.value !== tid) {
      filterTaskId.value = tid
    }
    if (!pid && filterProjectId.value) {
      filterProjectId.value = undefined
      filterTaskId.value = undefined
    }
  },
  { immediate: true },
)

// 数据来源以后端持久化的 run_source 为准（服务端对存量数据做懒迁移回填）
function isSandboxRun(record) {
  if (record.run_source) return record.run_source === 'test'
  // 兼容旧版本后端无 run_source 字段的情况
  const target = String(record.target || '').trim().toLowerCase()
  return target === 'test' || target.startsWith('test')
}

const filteredRuns = computed(() => {
  let result = runs.value
  // 环境筛选
  if (envFilter.value === 'sandbox') result = result.filter(isSandboxRun)
  else if (envFilter.value === 'production') result = result.filter((r) => !isSandboxRun(r))
  // 项目筛选
  if (filterProjectId.value) {
    result = result.filter(r => r.project_id === filterProjectId.value)
  }
  // 任务筛选
  if (filterTaskId.value) {
    result = result.filter(r => r.task_id === filterTaskId.value)
  }
  return result
})

const sandboxRuns = computed(() => runs.value.filter(isSandboxRun))

// 加载项目列表
async function loadProjects() {
  try {
    const res = await listProjects()
    const list = Array.isArray(res) ? res : []
    projectOptions.value = list.map(p => ({
      label: p.name || '未命名项目',
      value: p.project_id,
    }))
  } catch {
    projectOptions.value = []
  }
}

// 加载项目下的任务列表
async function loadProjectTasks(projectId) {
  if (!projectId) {
    taskOptions.value = []
    return
  }
  try {
    const res = await client.get(`/projects/${projectId}/tasks`)
    const list = Array.isArray(res) ? res : (res?.tasks || [])
    taskOptions.value = list.map(t => ({
      label: t.title || '未命名任务',
      value: t.task_id,
    }))
  } catch {
    taskOptions.value = []
  }
}

// 项目切换时清空任务选择并加载新任务
function onProjectChange() {
  filterTaskId.value = undefined
  loadProjectTasks(filterProjectId.value)
}

// 重置筛选条件
function resetFilter() {
  filterProjectId.value = undefined
  filterTaskId.value = undefined
  taskOptions.value = []
}

// 跳转到新建迭代页面
function goToNewRun() {
  router.push('/ecml')
}

async function clearSandboxRuns() {
  const ids = sandboxRuns.value.map((r) => r.run_id)
  try {
    const res = await bulkDeleteECMLRuns(ids)
    message.success(`已清空 ${res.deleted ?? ids.length} 条测试记录`)
  } catch {
    return /* error handled by interceptor */
  }
  selectedRowKeys.value = []
  await fetchRuns()
}

async function bulkRemove() {
  const ids = [...selectedRowKeys.value]
  try {
    const res = await bulkDeleteECMLRuns(ids)
    message.success(`已删除 ${res.deleted ?? ids.length} 条记录`)
  } catch {
    return /* error handled by interceptor */
  }
  selectedRowKeys.value = []
  await fetchRuns()
}

const columns = [
  { title: 'Run ID', dataIndex: 'run_id', key: 'run_id', width: 180, ellipsis: true },
  { title: '目标', dataIndex: 'target', key: 'target', width: 220, ellipsis: true },
  { title: '目标属性', dataIndex: 'target_property', key: 'target_property', width: 140, ellipsis: true },
  { title: '迭代次数', dataIndex: 'iteration', key: 'iteration', width: 100, align: 'center' },
  { title: '来源', key: 'env', width: 90, align: 'center' },
  { title: '状态', key: 'is_complete', width: 110, align: 'center' },
  { title: '更新时间', key: 'updated_at', width: 180 },
  { title: '操作', key: 'action', width: 180, fixed: 'right' },
]

async function fetchRuns() {
  loading.value = true
  try {
    const data = await getEcmlRuns()
    runs.value = (data.runs || []).map(run => {
      // 数据校验：可合成数不应超过候选总数
      if (run.synthesizable > run.candidates) {
        console.warn(`[ECML] 数据异常: run=${run.run_id}, synthesizable=${run.synthesizable} > candidates=${run.candidates}`)
        run.synthesizable = run.candidates
      }
      return run
    })
  } catch {
    runs.value = []
  } finally {
    loading.value = false
  }
}

function runRowProps(record) {
  return {
    style: { cursor: 'pointer' },
    onClick: () => viewRun(record),
  }
}

function viewRun(record) {
  router.push({ path: '/ecml', query: { run_id: record.run_id } })
}

function continueRun(record) {
  router.push({ path: '/ecml', query: { run_id: record.run_id } })
}

async function removeRun(record) {
  try {
    await deleteECMLRun(record.run_id)
    message.success('删除成功')
    await fetchRuns()
  } catch {
    /* error handled by interceptor */
  }
}

onMounted(() => {
  fetchRuns()
  loadProjects()
})
</script>

<style scoped>
.ecml-runs {
  width: 100%;
  max-width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.header-text {
  flex: 1;
}

.runs-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
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

.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--light-bg-hover, #fafafa);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light, #f0f0f0);
}
</style>
