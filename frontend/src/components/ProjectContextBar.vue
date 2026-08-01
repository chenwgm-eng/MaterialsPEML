<template>
  <div v-if="showBar" class="project-context-bar">
    <div class="ctx-label">
      <FolderOutlined />
      <span>当前项目</span>
    </div>
    <a-select
      v-model:value="selectedProjectId"
      :options="projectOptions"
      :loading="store.loading"
      size="small"
      placeholder="请选择项目"
      show-search
      option-filter-prop="label"
      class="project-select"
      :get-popup-container="(trigger) => trigger.parentNode"
      @change="onChange"
    />
    <a-tooltip v-if="store.currentProject?.name" :title="`当前项目：${store.currentProject.name}`">
      <span class="project-name-hint">{{ store.currentProject.name }}</span>
    </a-tooltip>
    <span v-else class="project-name-hint empty">未选择项目</span>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { FolderOutlined } from '@ant-design/icons-vue'
import { useProjectContextStore } from '@/stores/projectContext'

const store = useProjectContextStore()

const projectOptions = computed(() =>
  store.projectList.map((p) => ({
    value: p.project_id,
    label: p.name || p.project_id,
  }))
)

const selectedProjectId = computed({
  get: () => store.currentProjectId,
  set: (val) => {
    const project = store.projectList.find((p) => p.project_id === val)
    if (project) store.setCurrentProject(project)
  },
})

// 仅在已选择项目时显示
const showBar = computed(() => store.projectList.length > 0)

function onChange(val) {
  const project = store.projectList.find((p) => p.project_id === val)
  if (project) store.setCurrentProject(project)
}

onMounted(async () => {
  // 先从 localStorage 恢复
  store.restoreFromStorage()
  // 拉取项目列表，若用户已选择项目则保留选择
  await store.fetchProjects()
})

// 项目列表加载完成后，如果 localStorage 中有项目 ID 但不在新列表中，需要重置
watch(
  () => store.projectList,
  (list) => {
    if (list.length > 0 && !store.currentProject) {
      store.setCurrentProject(list[0])
    }
  }
)
</script>

<style scoped>
.project-context-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(90deg, rgba(249, 115, 22, 0.06), rgba(249, 115, 22, 0.02));
  border: 1px solid rgba(249, 115, 22, 0.15);
  border-radius: 6px;
  padding: 6px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}

.ctx-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted, #8a92a6);
  font-size: 12px;
  flex-shrink: 0;
}

.project-select {
  width: 240px;
  flex-shrink: 0;
}

.project-name-hint {
  color: var(--text-secondary, #5a6478);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}

.project-name-hint.empty {
  color: var(--text-muted, #b0b8c8);
  font-style: italic;
}

@media (max-width: 768px) {
  .project-context-bar {
    flex-wrap: wrap;
  }
  .project-select {
    width: 100%;
  }
  .project-name-hint {
    max-width: 100%;
  }
}
</style>
