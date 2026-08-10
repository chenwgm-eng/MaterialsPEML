<template>
  <div class="project-locator">
    <!-- 项目选择器：下拉 + 顶部 MRU(≤5, localStorage recentProjectIds) -->
    <div class="locator-head">
      <div class="locator-title">项目定位</div>
      <a-button
        type="text"
        size="small"
        class="mru-reload"
        :loading="loading"
        @click="$emit('refresh')"
      >
        <ReloadOutlined />
      </a-button>
    </div>

    <a-select
      v-model:value="selectedId"
      show-search
      option-filter-prop="label"
      placeholder="选择项目（全部项目）"
      class="locator-select"
      :loading="loading"
      @change="onSelect"
    >
      <a-select-option value="" label="全部项目">
        <span class="locator-all-opt">全部项目</span>
      </a-select-option>
      <a-select-option v-for="p in projectOptions" :key="p.value" :value="p.value" :label="p.label">
        {{ p.label }}
      </a-select-option>
    </a-select>

    <!-- 任务选择器（项目空间 #1：联动当前项目，可全部任务） -->
    <a-select
      v-if="selectedId"
      v-model:value="selectedTaskId"
      show-search
      option-filter-prop="label"
      placeholder="选择任务（全部任务）"
      class="locator-select locator-task-select"
      :loading="tasksLoading"
      :not-found-content="tasksLoading ? '加载中…' : '暂无任务'"
      @change="onTaskSelect"
    >
      <a-select-option value="" label="全部任务">
        <span class="locator-all-opt">全部任务</span>
      </a-select-option>
      <a-select-option v-for="t in taskOptions" :key="t.value" :value="t.value" :label="t.label">
        {{ t.label }}
      </a-select-option>
    </a-select>

    <!-- 新建下拉（权限过滤） -->
    <div class="locator-actions">
      <a-dropdown placement="bottomLeft" trigger="click">
        <a-button type="primary" size="small" block>
          <PlusOutlined /> 新建 <DownOutlined />
        </a-button>
        <template #overlay>
          <a-menu @click="onCreateClick">
            <a-menu-item v-for="item in createItems" :key="item.path">{{ item.label }}</a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PlusOutlined, DownOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useProjectContextStore } from '@/stores/projectContext'

const props = defineProps({
  projectId: { type: String, default: '' },
  createItems: { type: Array, default: () => [] },
})

const emit = defineEmits(['refresh'])

const router = useRouter()
const projectCtx = useProjectContextStore()

const selectedId = ref(props.projectId || '')
const selectedTaskId = ref('')
const loading = ref(false)

const projectOptions = computed(() =>
  projectCtx.projectList.map((p) => ({ value: p.project_id, label: p.name || p.project_id })),
)

const taskOptions = computed(() =>
  projectCtx.taskList.map((t) => ({
    value: t.task_id,
    label: t.title || t.task_id,
  })),
)

const tasksLoading = computed(() => projectCtx.tasksLoading)

function selectProject(p) {
  // p=null 表示「全部项目」：清空上下文，任务选择器隐藏
  selectedId.value = p?.project_id || ''
  projectCtx.setCurrentProject(p)
  selectedTaskId.value = ''
  projectCtx.setCurrentTask(null)
  if (p) {
    // 联动加载当前项目任务（供任务选择器）
    projectCtx.fetchTasks(p.project_id)
  }
  emit('refresh')
}

function onSelect(value) {
  const p = value ? projectCtx.projectList.find((x) => x.project_id === value) : null
  selectProject(p)
}

function onTaskSelect(value) {
  const t = value ? projectCtx.taskList.find((x) => x.task_id === value) : null
  projectCtx.setCurrentTask(t)
  emit('refresh')
}

function onCreateClick({ key }) {
  // createItems 以 path 为键（旧实现误用 item.key 导致点击无效，#2）
  const item = props.createItems.find((i) => i.path === key)
  if (item?.path) router.push(item.path)
}

async function boot() {
  loading.value = true
  try {
    await projectCtx.fetchProjects()
    if (props.projectId && projectCtx.projectList.length) {
      const p = projectCtx.projectList.find((x) => x.project_id === props.projectId)
      if (p) projectCtx.setCurrentProject(p)
    } else if (!projectCtx.currentProject && projectCtx.projectList.length) {
      projectCtx.setCurrentProject(projectCtx.projectList[0])
    }
    selectedId.value = projectCtx.currentProjectId || props.projectId || ''
    // 恢复任务上下文（若有）
    if (selectedId.value) {
      await projectCtx.fetchTasks(selectedId.value)
      selectedTaskId.value = projectCtx.currentTaskId || ''
    }
  } finally {
    loading.value = false
  }
}

onMounted(boot)
</script>

<style scoped>
.project-locator {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}
.locator-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.locator-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--sidebar-text);
}
.mru-reload {
  color: var(--text-muted);
}
.locator-select {
  width: 100%;
}
.locator-task-select {
  margin-top: -2px;
}
.locator-all-opt {
  color: var(--text-muted);
  font-weight: 600;
}
.locator-actions {
  margin-top: 2px;
}
</style>