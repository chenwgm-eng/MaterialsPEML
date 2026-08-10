<template>
  <div class="project-task-panel">
    <div class="panel-head">
      <span class="panel-title">待办任务</span>
      <div class="panel-ops">
        <a-tooltip title="搜索任务">
          <a-button size="small" type="text" @click="searchOpen = !searchOpen">
            <SearchOutlined />
          </a-button>
        </a-tooltip>
        <a-tooltip :title="expanded ? '收起' : '展开全部'">
          <a-button size="small" type="text" @click="expanded = !expanded">
            <DownOutlined v-if="!expanded" />
            <UpOutlined v-else />
          </a-button>
        </a-tooltip>
      </div>
    </div>

    <a-input
      v-if="searchOpen"
      v-model:value="keyword"
      size="small"
      allow-clear
      placeholder="搜索本任务区"
      class="task-search"
    />

    <div v-if="loading" class="panel-loading"><a-spin size="small" /></div>

    <template v-else>
      <!-- 进行中/草稿（上方） -->
      <div v-if="activeTasks.length" class="task-section">
        <div class="task-group-label">进行中</div>
        <div
          v-for="t in activeTasks"
          :key="t.task_id"
          class="task-item"
          :class="`task-status-${(t.status || '').toLowerCase()}`"
          @click="openTask(t)"
        >
          <span class="task-dot" :class="`dot-${(t.status || '').toLowerCase()}`" />
          <span class="task-title" :title="t.title">{{ t.title }}</span>
        </div>
      </div>

      <!-- 已完成（下方） -->
      <div v-if="doneTasks.length" class="task-section">
        <div class="task-group-label">已完成</div>
        <div
          v-for="t in doneTasks"
          :key="t.task_id"
          class="task-item task-done"
          @click="openTask(t)"
        >
          <span class="task-dot dot-completed" />
          <span class="task-title" :title="t.title">{{ t.title }}</span>
        </div>
      </div>

      <div v-if="!activeTasks.length && !doneTasks.length" class="task-empty">
        暂无相关任务
        <router-link to="/my-tasks">去创建</router-link>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { SearchOutlined, DownOutlined, UpOutlined } from '@ant-design/icons-vue'
import { useSystemStore } from '@/stores/system'
import { listProjectTasks } from '@/api/projects'

const props = defineProps({
  projectId: { type: String, default: '' },
})

const router = useRouter()
const systemStore = useSystemStore()

const tasks = ref([])
const loading = ref(false)
const keyword = ref('')
const searchOpen = ref(false)
const expanded = ref(false)

const DONE_STATUS = new Set(['done', 'completed', 'closed', '已完成', '完成'])

const allTasks = computed(() => {
  const mine = tasks.value.filter((t) => isMine(t))
  const kw = (keyword.value || '').trim().toLowerCase()
  const filtered = kw
    ? mine.filter((t) => `${t.title} ${t.deliverable || ''}`.toLowerCase().includes(kw))
    : mine
  // 进行中优先上方，已完成在下方；各按更新时间倒序
  const active = filtered.filter((t) => !DONE_STATUS.has((t.status || '').replace(/\s/g, '')))
  const done = filtered.filter((t) => DONE_STATUS.has((t.status || '').replace(/\s/g, '')))
  return { active, done }
})

const activeTasks = computed(() => {
  const { active } = allTasks.value
  return expanded.value ? active : active.slice(0, 5)
})

const doneTasks = computed(() => {
  const { done } = allTasks.value
  return expanded.value ? done.slice(0, 10) : done.slice(0, 5)
})

function myIdentity() {
  const u = systemStore.currentUser
  if (!u) return ''
  return u.user_id || u.username || u.display_name || ''
}

function isMine(t) {
  const me = myIdentity()
  if (!me || !t) return false
  const assignee = String(t.assignee || t.owner || '')
  return assignee === me || assignee.includes(me)
}

async function loadTasks() {
  if (!props.projectId) {
    tasks.value = []
    return
  }
  loading.value = true
  try {
    const data = await listProjectTasks(props.projectId)
    tasks.value = Array.isArray(data) ? data : (data.tasks || [])
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function openTask(t) {
  if (!t?.task_id) return
  router.push({ path: '/my-tasks', query: { task_id: t.task_id } })
}

watch(() => props.projectId, loadTasks)
onMounted(loadTasks)
</script>

<style scoped>
.project-task-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
  border-top: 1px solid var(--border);
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--sidebar-text);
}
.panel-ops {
  display: flex;
  align-items: center;
  gap: 2px;
}
.task-search {
  width: 100%;
}
.panel-loading {
  padding: 12px 0;
  text-align: center;
}
.task-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.task-group-label {
  font-size: 11px;
  color: var(--text-muted);
  padding: 4px 2px;
}
.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.task-item:hover {
  background: var(--surface-hover);
}
.task-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.task-title {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.task-status-draft .task-dot,
.dot-draft { background: var(--text-on-dark-muted); }
.task-status-active .task-dot,
.task-status-in_progress .task-dot,
.dot-active,
.dot-in_progress { background: var(--primary); }
.task-done,
.task-status-done .task-title,
.task-status-completed .task-title { color: var(--text-muted); }
.dot-completed { background: var(--success); }
.task-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 4px;
}
</style>