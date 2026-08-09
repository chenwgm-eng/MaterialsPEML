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
      placeholder="选择项目"
      class="locator-select"
      :loading="loading"
      @change="onSelect"
    >
      <a-select-option v-for="p in projectOptions" :key="p.value" :value="p.value" :label="p.label">
        {{ p.label }}
      </a-select-option>
    </a-select>

    <!-- 常用项目（最近访问 MRU，≤5） -->
    <div v-if="mruProjects.length" class="mru-list">
      <div
        v-for="p in mruProjects"
        :key="p.project_id"
        :class="['mru-item', { active: p.project_id === selectedId }]"
        @click="selectProject(p)"
      >
        <span class="mru-name" :title="p.name">{{ p.name }}</span>
      </div>
    </div>

    <!-- 新建下拉（权限过滤） -->
    <div class="locator-actions">
      <a-dropdown placement="bottomLeft" trigger="click">
        <a-button type="primary" size="small" block>
          <PlusOutlined /> 新建 <DownOutlined />
        </a-button>
        <template #overlay>
          <a-menu @click="onCreateClick">
            <a-menu-item v-for="item in createItems" :key="item.key">{{ item.label }}</a-menu-item>
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
const loading = ref(false)
const mruProjects = ref([])

const MRU_KEY = 'recentProjectIds'

const projectOptions = computed(() =>
  projectCtx.projectList.map((p) => ({ value: p.project_id, label: p.name || p.project_id })),
)

function readMru() {
  try {
    const raw = JSON.parse(localStorage.getItem(MRU_KEY) || '[]')
    const pool = projectCtx.projectList
    mruProjects.value = raw
      .map((id) => pool.find((p) => p.project_id === id))
      .filter(Boolean)
      .slice(0, 5)
  } catch {
    mruProjects.value = []
  }
}

function touchMru(p) {
  if (!p?.project_id) return
  try {
    const raw = JSON.parse(localStorage.getItem(MRU_KEY) || '[]')
    const next = [p.project_id, ...raw.filter((id) => id !== p.project_id)]
    localStorage.setItem(MRU_KEY, JSON.stringify(next.slice(0, 5)))
  } catch {
    /* ignore */
  }
}

function selectProject(p) {
  if (!p) return
  selectedId.value = p.project_id
  projectCtx.setCurrentProject(p)
  touchMru(p)
  readMru()
  emit('refresh')
}

function onSelect(value) {
  const p = projectCtx.projectList.find((x) => x.project_id === value)
  selectProject(p)
}

function onCreateClick({ key }) {
  const item = props.createItems.find((i) => i.key === key)
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
    readMru()
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
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.mru-reload {
  color: var(--text-muted);
}
.locator-select {
  width: 100%;
}
.mru-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mru-item {
  padding: 6px 10px;
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.mru-item:hover {
  background: var(--surface-hover);
}
.mru-item.active {
  background: var(--sidebar-active);
  color: var(--sidebar-text-active);
}
.mru-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
}
.locator-actions {
  margin-top: 2px;
}
</style>