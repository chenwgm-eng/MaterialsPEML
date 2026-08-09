<template>
  <div class="projects-page">
    <div
      class="split-layout"
      :class="{ 'is-resizing': isResizing }"
      @mousemove="onResize"
      @mouseup="stopResize"
      @mouseleave="stopResize"
    >
      <!-- Left Panel: Project List -->
      <div class="left-panel" :style="{ width: leftPanelWidth + 'px' }">
        <div class="search-row">
          <a-input-search
            v-model:value="searchText"
            placeholder="按项目名称搜索"
            allow-clear
            style="flex: 1"
          />
          <a-button type="primary" size="small" @click="onCreateNew">
            <PlusOutlined /> 新建项目
          </a-button>
        </div>
        <SmartLoading
          v-if="loading && paginatedProjects.length === 0"
          :loading="true"
          skeleton-type="list"
          tip="正在加载项目列表..."
          show-cancel
          @cancel="onCancelLoadProjects"
        />
        <div v-else class="project-list">
          <div
            v-for="project in paginatedProjects"
            :key="project.project_id"
            class="project-row"
            :class="{ selected: selectedProject?.project_id === project.project_id }"
            @click="onSelectProject(project)"
          >
            <div class="project-row-top">
              <span class="project-name">{{ project.name || '未命名项目' }}</span>
              <StatusBadge v-if="project.current_stage" :status="stageToBadge(project.current_stage)" :label="project.current_stage" />
            </div>
            <a-progress
              :percent="projectProgress(project)"
              size="small"
              :stroke-color="progressColorMap(projectProgress(project))"
              style="margin: 4px 0"
            />
            <div class="project-dates">
              <template v-if="project.start_date || project.end_date">
                <span v-if="project.start_date">{{ project.start_date }}</span>
                <span v-if="project.start_date && project.end_date"> ~ </span>
                <span v-if="project.end_date">{{ project.end_date }}</span>
              </template>
              <span v-else class="text-muted">未设置</span>
            </div>
          </div>
          <EmptyState
            v-if="!loading && paginatedProjects.length === 0"
            type="data"
            description="暂无项目"
          />
        </div>
        <a-pagination
          v-if="filteredProjects.length > pageSize"
          v-model:current="currentPage"
          :total="filteredProjects.length"
          :page-size="pageSize"
          size="small"
          show-total
          :show-size-changer="true"
          :page-size-options="['10', '20', '50']"
          @showSizeChange="onPageSizeChange"
          style="margin-top: 8px; text-align: center"
        />
      </div>

      <!-- Drag Handle -->
      <div class="drag-handle" @mousedown="startResize"></div>

      <!-- Right Panel: Gantt Chart / New Project Form -->
      <div class="right-panel">
        <!-- 新建项目模式：内嵌 ProjectNew 表单，参照研发工作台卡片流布局 -->
        <template v-if="rightView === 'new'">
          <div class="right-header">
            <div class="right-header-left">
              <ArrowLeftOutlined class="back-icon" @click="onBackToList" />
              <span class="right-header-title">新建项目</span>
            </div>
          </div>
          <div class="embedded-form-container">
            <ProjectNew
              embedded
              @created="onProjectCreated"
              @cancel="onBackToList"
            />
          </div>
        </template>

        <!-- 甘特图模式：选中项目后展示 -->
        <template v-else-if="selectedProject">
          <div class="right-header">
            <div class="right-header-left">
              <ArrowLeftOutlined class="back-icon" @click="selectedProject = null" />
              <span class="right-header-title">{{ selectedProject.name }}</span>
            </div>
            <a-space>
              <a-popconfirm
                title="确认删除该项目？"
                description="存在下游引用的项目将被拒绝删除"
                ok-text="删除"
                cancel-text="取消"
                @confirm="onDeleteSelected"
              >
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </div>

          <!-- Tab：基本信息 / 项目任务与交付要求 / 甘特图 / 实体图谱 -->
          <div class="right-tabs">
            <a-tabs v-model:activeKey="rightTab" size="small" class="right-tabs-inner">
              <a-tab-pane key="info" tab="基本信息">
                <div class="project-info-panel">
                  <a-spin :spinning="infoSaving">
                    <a-form layout="vertical" size="small" class="info-form">
                      <a-row :gutter="12">
                        <a-col :span="12">
                          <a-form-item label="项目名称" required>
                            <a-input v-model:value="infoForm.name" placeholder="项目名称" :disabled="!isEditing" />
                          </a-form-item>
                        </a-col>
                        <a-col :span="12">
                          <a-form-item label="项目编号">
                            <a-input :value="selectedProject.project_id" disabled />
                          </a-form-item>
                        </a-col>
                      </a-row>
                      <a-row :gutter="12">
                        <a-col :span="12">
                          <a-form-item label="目标应用">
                            <a-input v-model:value="infoForm.target_application" placeholder="如 锂镧锆氧（LLZO）固态电解质" :disabled="!isEditing" />
                          </a-form-item>
                        </a-col>
                        <a-col :span="6">
                          <a-form-item label="当前阶段">
                            <a-select v-model:value="infoForm.current_stage" :options="stageOptions" :disabled="!isEditing" />
                          </a-form-item>
                        </a-col>
                        <a-col :span="6">
                          <a-form-item label="负责人">
                            <a-select
                              v-model:value="infoForm.owner"
                              :options="userOptions"
                              placeholder="请选择负责人"
                              show-search
                              option-filter-prop="label"
                              :loading="usersLoading"
                              :disabled="!isEditing"
                              allow-clear
                            />
                          </a-form-item>
                        </a-col>
                      </a-row>
                      <a-row :gutter="12">
                        <a-col :span="12">
                          <a-form-item label="所属部门">
                            <a-input v-model:value="infoForm.department" placeholder="所属部门" :disabled="!isEditing" />
                          </a-form-item>
                        </a-col>
                        <a-col :span="6">
                          <a-form-item label="开始日期">
                            <a-date-picker
                              v-model:value="infoForm.start_date"
                              format="YYYY-MM-DD"
                              value-format="YYYY-MM-DD"
                              style="width: 100%"
                              :disabled="!isEditing"
                            />
                          </a-form-item>
                        </a-col>
                        <a-col :span="6">
                          <a-form-item label="结束日期">
                            <a-date-picker
                              v-model:value="infoForm.end_date"
                              format="YYYY-MM-DD"
                              value-format="YYYY-MM-DD"
                              style="width: 100%"
                              :disabled="!isEditing"
                            />
                          </a-form-item>
                        </a-col>
                      </a-row>
                      <a-row :gutter="12">
                        <a-col :span="12">
                          <a-form-item label="预算（万元）">
                            <a-input-number v-model:value="infoForm.budget" :min="0" style="width: 100%" placeholder="0" :disabled="!isEditing" />
                          </a-form-item>
                        </a-col>
                        <a-col :span="12">
                          <a-form-item label="迭代进度（%）">
                            <a-input-number v-model:value="infoForm.iteration_progress" :min="0" :max="100" style="width: 100%" placeholder="0" :disabled="!isEditing" />
                          </a-form-item>
                        </a-col>
                      </a-row>
                      <a-form-item label="目标属性">
                        <div class="info-props">
                          <a-tag
                            v-for="(p, idx) in (infoForm.target_properties || [])"
                            :key="idx"
                            :closable="isEditing"
                            @close="removeInfoProperty(idx)"
                          >
                            {{ p.name }}
                            <template v-if="p.direction === 'maximize'">↑</template>
                            <template v-else>↓</template>
                            <template v-if="p.min != null">≥{{ p.min }}</template>
                            <template v-if="p.max != null">≤{{ p.max }}</template>
                          </a-tag>
                          <span v-if="!infoForm.target_properties?.length" class="text-muted">无</span>
                        </div>
                      </a-form-item>
                      <a-form-item label="备注">
                        <a-textarea v-model:value="infoForm.notes" :rows="3" placeholder="项目备注" :disabled="!isEditing" />
                      </a-form-item>
                      <div class="info-footer">
                        <span class="info-meta">
                          创建于 {{ selectedProject.created_at?.slice(0, 19).replace('T', ' ') || '—' }}
                          <template v-if="selectedProject.updated_at">
                            · 更新于 {{ selectedProject.updated_at.slice(0, 19).replace('T', ' ') }}
                          </template>
                        </span>
                        <a-space>
                          <template v-if="isEditing">
                            <a-button @click="cancelEditInfoForm">取消</a-button>
                            <a-button type="primary" :loading="infoSaving" @click="saveInfoForm">保存</a-button>
                          </template>
                          <template v-else>
                            <a-button type="primary" @click="editInfoForm">编辑</a-button>
                          </template>
                        </a-space>
                      </div>
                    </a-form>
                  </a-spin>
                </div>
              </a-tab-pane>
              <a-tab-pane key="tasks" tab="项目任务与交付要求">
                <div class="project-tasks-panel">
                  <div class="tasks-panel-header">
                    <a-tag size="small">{{ selectedProjectTasks.length }} 个任务</a-tag>
                  </div>
                  <div v-if="selectedProjectTasks.length" class="tasks-list">
                    <div v-for="(task, idx) in selectedProjectTasks" :key="task.task_id || idx" class="task-card">
                      <div class="task-card-head">
                        <span class="task-idx">{{ idx + 1 }}</span>
                        <span class="task-title">{{ task.title || '未命名任务' }}</span>
                        <a-tag v-if="getTaskStageLabel(task)" :color="getTaskStageColor(task)" size="small" class="stage-tag">
                          {{ getTaskStageLabel(task) }}
                        </a-tag>
                        <a-button
                          type="text"
                          size="small"
                          class="task-edit-btn"
                          aria-label="编辑任务"
                          @click="onEditTask(task)"
                        >
                          <template #icon><EditOutlined /></template>
                          编辑
                        </a-button>
                      </div>
                      <div class="task-card-row">
                        <span class="row-label">交付物：</span>
                        <span class="row-value">{{ task.deliverable || '—' }}</span>
                      </div>
                      <div class="task-card-row">
                        <span class="row-label">交付物具体要求：</span>
                        <span class="row-value">
                          <a-tag
                            v-for="p in (task.target_properties || [])"
                            :key="p.name"
                            size="small"
                            class="prop-tag"
                          >
                            {{ p.name }}
                            <template v-if="p.direction === 'maximize'">↑</template>
                            <template v-else>↓</template>
                            <template v-if="p.min != null">≥{{ p.min }}</template>
                            <template v-if="p.max != null">≤{{ p.max }}</template>
                          </a-tag>
                          <span v-if="!task.target_properties?.length" class="text-muted">无</span>
                        </span>
                      </div>
                    </div>
                  </div>
                  <EmptyState
                    v-else
                    type="data"
                    description="该项目暂无任务"
                  />
                  <div class="tasks-panel-footer">
                    <a-button type="dashed" block @click="onAddTask">
                      <template #icon><PlusOutlined /></template>
                      新增任务
                    </a-button>
                  </div>
                </div>
              </a-tab-pane>
              <a-tab-pane key="gantt" tab="甘特图">
                <div class="gantt-container">
                  <GanttChart :project="selectedProject" />
                </div>
              </a-tab-pane>
              <a-tab-pane key="lineage" tab="实体血缘">
                <div class="lineage-panel">
                  <div class="lineage-toolbar">
                    <a-select
                      v-model:value="lineageTaskFilter"
                      size="small"
                      style="width: 220px"
                      placeholder="按任务过滤（默认全部）"
                      allow-clear
                      @change="onLineageTaskChange"
                    >
                      <a-select-option value="">全部任务</a-select-option>
                      <a-select-option v-for="t in selectedProjectTasks" :key="t.task_id" :value="t.task_id">
                        {{ t.title || t.task_id }}
                      </a-select-option>
                    </a-select>
                    <span class="lineage-summary">{{ lineageSummary }}</span>
                    <a-button size="small" :loading="lineageLoading" @click="reloadLineage">
                      <template #icon><ReloadOutlined /></template>
                      刷新
                    </a-button>
                  </div>
                  <a-spin :spinning="lineageLoading">
                    <div class="lineage-content">
                      <div class="lineage-tree-container">
                        <a-tree
                          v-if="lineageData.length"
                          :key="lineageTreeKey"
                          :tree-data="lineageData"
                          default-expand-all
                          :selectable="true"
                          v-model:selectedKeys="lineageSelectedKeys"
                          class="lineage-tree"
                        >
                          <template #title="node">
                            <span class="lineage-node">
                              <component :is="lineageIconMap[node.type]" v-if="node.type" class="lineage-node-icon" />
                              <span class="lineage-node-label">{{ node.title }}</span>
                              <a-tag v-if="node.status" size="small" class="lineage-node-status">{{ node.status }}</a-tag>
                              <span v-if="node.meta" class="lineage-node-meta">{{ node.meta }}</span>
                            </span>
                          </template>
                        </a-tree>
                        <EmptyState
                          v-else-if="!lineageLoading"
                          type="data"
                          description="暂无血缘数据"
                        />
                      </div>
                      <div class="lineage-detail-panel">
                        <a-card v-if="lineageSelectedNode" size="small" :bordered="true" class="lineage-detail-card">
                          <template #title>
                            <div class="lineage-detail-header">
                              <component :is="lineageIconMap[lineageSelectedNode.type]" v-if="lineageSelectedNode.type" class="lineage-node-icon" />
                              <span>{{ lineageSelectedNode.title }}</span>
                            </div>
                          </template>
                          <a-descriptions :column="1" size="small" bordered>
                            <a-descriptions-item label="类型">{{ lineageTypeLabel(lineageSelectedNode.type) }}</a-descriptions-item>
                            <a-descriptions-item v-if="lineageSelectedNode.status" label="状态">
                              <a-tag :color="lineageStatusColor(lineageSelectedNode.status)">{{ lineageSelectedNode.status }}</a-tag>
                            </a-descriptions-item>
                            <a-descriptions-item v-if="lineageSelectedNode.meta" label="元信息">{{ lineageSelectedNode.meta }}</a-descriptions-item>
                          </a-descriptions>
                          <div class="lineage-detail-actions" v-if="lineageSelectedNode">
                            <a-button type="link" size="small" @click="onLineageJump(lineageSelectedNode)"><EyeOutlined /> 查看详情</a-button>
                          </div>
                        </a-card>
                        <EmptyState
                          v-else
                          type="data"
                          description="点击左侧节点查看详情"
                        />
                      </div>
                    </div>
                  </a-spin>
                </div>
              </a-tab-pane>
            </a-tabs>
          </div>
        </template>
        <div v-else class="right-empty">
          <EmptyState type="data" description="请选择项目查看甘特图" />
        </div>
      </div>
    </div>

    <!-- 任务编辑抽屉：新增 / 编辑任务 -->
    <a-drawer
      v-model:open="taskDrawerOpen"
      :title="taskDrawerMode === 'create' ? '新增任务' : '编辑任务'"
      placement="right"
      :width="480"
      :mask="true"
      :destroy-on-close="true"
    >
      <div class="task-form">
        <div class="form-field">
          <label class="form-label">任务标题 <span class="required">*</span></label>
          <a-input
            v-model:value="taskForm.title"
            placeholder="如 高离子电导率 LLZO 电解质配方优化"
            allow-clear
          />
        </div>
        <div class="form-field">
          <label class="form-label">交付物（材料）</label>
          <a-input
            v-model:value="taskForm.deliverable"
            placeholder="如 锂镧锆氧（LLZO）固态电解质"
            allow-clear
          />
        </div>

        <div class="form-field">
          <label class="form-label">目标属性</label>
          <div class="prop-editor">
            <div class="prop-row prop-header">
              <span class="prop-name">属性名</span>
              <span class="prop-dir">方向</span>
              <span class="prop-min">最小</span>
              <span class="prop-max">最大</span>
              <span class="prop-op"></span>
            </div>
            <div v-for="(p, pidx) in taskForm.target_properties" :key="p._key" class="prop-row">
              <a-input
                v-model:value="p.name"
                size="small"
                class="prop-name"
                placeholder="如 ionic_conductivity"
              />
              <a-select v-model:value="p.direction" size="small" class="prop-dir" :options="directionOptions" />
              <a-input
                v-model:value="p._minText"
                size="small"
                class="prop-min prop-sci-input"
                placeholder="如 1e-3"
                @change="(e) => onPropNumberChange(p, 'min', e.target.value)"
              />
              <a-input
                v-model:value="p._maxText"
                size="small"
                class="prop-max prop-sci-input"
                placeholder="如 1e-2"
                @change="(e) => onPropNumberChange(p, 'max', e.target.value)"
              />
              <a-button
                type="text"
                danger
                size="small"
                class="prop-op"
                aria-label="删除属性"
                @click="removeProperty(pidx)"
              >
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
            <a-button size="small" type="dashed" block @click="addProperty">
              <template #icon><PlusOutlined /></template>
              添加目标属性
            </a-button>
          </div>
        </div>

        <div class="form-field">
          <label class="form-label">状态</label>
          <a-select v-model:value="taskForm.status" style="width: 100%" :options="taskStatusOptions" />
        </div>
      </div>

      <template #footer>
        <div class="drawer-footer">
          <a-button v-if="taskDrawerMode === 'edit'" danger @click="onDeleteTask" style="margin-right: auto">
            删除任务
          </a-button>
          <a-button @click="taskDrawerOpen = false">取消</a-button>
          <DisabledButton
            type="primary"
            :loading="taskSaving"
            :disabled="!taskForm.title.trim()"
            disabled-reason="请先填写任务标题"
            @click="onSaveTask"
          >
            保存
          </DisabledButton>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, ArrowLeftOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, ExperimentOutlined, DatabaseOutlined, AppstoreOutlined, BarChartOutlined, ProjectOutlined, FolderOutlined, ProfileOutlined, ThunderboltOutlined, EyeOutlined } from '@ant-design/icons-vue'
import GanttChart from '@/components/GanttChart.vue'
import EntityGraph from '@/components/EntityGraph.vue'
import DisabledButton from '@/components/DisabledButton.vue'
import SmartLoading from '@/components/SmartLoading.vue'
import ProjectNew from '@/views/ProjectNew.vue'
import {
  listProjects,
  getProjectProgress,
  getProjectStageStatus,
  updateProject,
  deleteProject,
  listProjectTasks,
  createProjectTask,
  updateProjectTask,
  deleteProjectTask,
  getProjectEntityGraph,
} from '@/api/projects'
import { listUsers } from '@/api/auth'
import { useMdmDict } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'

// 系统用户列表（负责人下拉）
const userOptions = ref([])
const usersLoading = ref(false)

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await listUsers()
    const list = Array.isArray(res) ? res : (res?.users || [])
    userOptions.value = list.map(u => ({
      label: u.display_name || u.name || u.username,
      value: u.id || u.user_id,
    }))
  } catch {
    userOptions.value = []
  } finally {
    usersLoading.value = false
  }
}

// 从 MDM 加载任务状态选项（失败时保留硬编码兜底）
const { statusOptions: mdmStatusOptions } = useMdmDict()
const taskStatusOptions = ref([
  { label: '草稿', value: 'draft' },
  { label: '进行中', value: 'active' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' },
])
const directionOptions = ref([
  { label: '最大化', value: 'maximize' },
  { label: '最小化', value: 'minimize' },
])

const projects = ref([])
const loading = ref(false)
const searchText = ref('')
const progressMap = ref({})
const selectedProject = ref(null)

// Step C 4.C2：资源型 URL——从路由参数选中项目（watch 局部刷新，不整页重建）
const route = useRoute()
watch(
  () => route.params.projectId,
  (pid) => {
    if (!pid) return
    const p = projects.value.find((x) => x.project_id === pid)
    if (p) selectedProject.value = p
  },
)
// 右侧面板视图：'list'（基本信息/任务/甘特图/空态）| 'new'（内嵌新建项目表单）
const rightView = ref('list')
// 右侧 Tab：'info'（基本信息）| 'tasks'（项目任务与交付要求）| 'gantt'（甘特图）| 'graph'（实体图谱）| 'lineage'（数据血缘）
const rightTab = ref('info')
const currentPage = ref(1)
const pageSize = ref(10)
const leftPanelWidth = ref(320)
const isResizing = ref(false)

const filteredProjects = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return projects.value
  return projects.value.filter((p) => (p.name || '').toLowerCase().includes(kw))
})

// 选中项目的任务列表（来自项目 tasks 字段）
const selectedProjectTasks = computed(() => {
  return selectedProject.value?.tasks || []
})

// 选中项目的阶段状态（含 ECML 细粒度 step + 实验任务汇总）
const stageStatus = ref(null)

// 实体关联图谱
const entityGraphData = ref({ nodes: [], edges: [], stats: {} })
const entityGraphLoading = ref(false)
const entityGraphTaskFilter = ref('')  // '' 表示不过滤，显示整个项目
const entityGraphLevel = ref('core')   // 'core' 核心 5 类 | 'full' 全量实体

// 数据血缘（使用 entity-graph 数据源，树形展示实体关联关系）
const lineageData = ref([])
const lineageLoading = ref(false)
const lineageLoaded = ref(false)  // 标记当前项目血缘数据是否已加载
const lineageSummary = ref('')
const lineageTreeKey = ref(0)     // 切换 key 以在数据更新后重新应用 default-expand-all
const lineageTaskFilter = ref('') // 按任务过滤

const lineageIconMap = {
  project: ProjectOutlined,
  task: ProfileOutlined,
  candidate: DatabaseOutlined,
  bom: AppstoreOutlined,
  process: ExperimentOutlined,
  experiment_order: ExperimentOutlined,
  test_task: BarChartOutlined,
  sample: AppstoreOutlined,
  result_record: BarChartOutlined,
  ecml_run: ThunderboltOutlined,
  group: FolderOutlined,
}

async function loadEntityGraph(projectId) {
  if (!projectId) return
  entityGraphLoading.value = true
  try {
    const params = {}
    if (entityGraphTaskFilter.value) params.task_id = entityGraphTaskFilter.value
    const res = await getProjectEntityGraph(projectId, params)
    entityGraphData.value = {
      nodes: res?.nodes || [],
      edges: res?.edges || [],
      stats: res?.stats || {},
    }
  } catch {
    entityGraphData.value = { nodes: [], edges: [], stats: {} }
  } finally {
    entityGraphLoading.value = false
  }
}

// 切换任务过滤
async function onEntityGraphTaskChange(taskId) {
  entityGraphTaskFilter.value = taskId || ''
  if (selectedProject.value) {
    await loadEntityGraph(selectedProject.value.project_id)
  }
}

// 切换核心/完整层级
function onEntityGraphLevelChange(level) {
  entityGraphLevel.value = level
}

// ──────────────────────────────────────────────────────────────
// 实体血缘 Tab：调用 /projects/{id}/entity-graph 获取全部实体节点与边，
// 用 parent_id 构建 a-tree 树形结构，展示 项目→任务→候选→BOM→工艺→实验 的完整血缘链路
// ──────────────────────────────────────────────────────────────

// 实体类型中文标签（用于树节点 meta 展示）
const _ENTITY_TYPE_LABELS = {
  project: '项目',
  task: '任务',
  candidate: '候选材料',
  bom: 'BOM 方案',
  process: '工艺方案',
  experiment_order: '实验任务单',
  test_task: '测试任务',
  sample: '样品',
  result_record: '实验数据',
  ecml_run: 'ECML 迭代',
}

function buildEntityLineageTree(nodes, edges) {
  if (!nodes?.length) return []
  // 构建 id → node 映射
  const nodeMap = new Map()
  nodes.forEach((n) => {
    nodeMap.set(n.id, { ...n, children: [] })
  })
  // 用 parent_id 构建父子关系
  const roots = []
  nodeMap.forEach((n) => {
    if (n.parent_id && nodeMap.has(n.parent_id)) {
      nodeMap.get(n.parent_id).children.push(n)
    } else {
      roots.push(n)
    }
  })
  // 转为 a-tree 需要的格式
  function toTreeNode(n) {
    const typeLabel = _ENTITY_TYPE_LABELS[n.type] || n.type || ''
    const metaParts = [typeLabel, n.candidate_type, n.iteration_id ? `第${n.iteration_id}轮` : ''].filter(Boolean)
    return {
      key: n.id,
      title: n.label || n.id,
      type: n.type,
      status: n.status || '',
      meta: metaParts.join(' · '),
      children: (n.children || []).map(toTreeNode),
    }
  }
  return roots.map(toTreeNode)
}

async function loadLineage(projectId) {
  if (!projectId) return
  lineageLoading.value = true
  try {
    const params = {}
    if (lineageTaskFilter.value) params.task_id = lineageTaskFilter.value
    const res = await getProjectEntityGraph(projectId, params)
    const nodes = res?.nodes || []
    const edges = res?.edges || []
    lineageData.value = buildEntityLineageTree(nodes, edges)
    // 统计各类型数量
    const typeCounts = {}
    nodes.forEach((n) => {
      const label = _ENTITY_TYPE_LABELS[n.type] || n.type || '其他'
      typeCounts[label] = (typeCounts[label] || 0) + 1
    })
    const summaryParts = Object.entries(typeCounts).map(([k, v]) => `${k} ${v}`)
    lineageSummary.value = `共 ${nodes.length} 个实体 · ${edges.length} 条关系` + (summaryParts.length ? `（${summaryParts.join(' · ')}）` : '')
    lineageLoaded.value = true
    lineageTreeKey.value += 1
  } catch {
    message.error('加载实体血缘失败')
    lineageData.value = []
    lineageSummary.value = ''
  } finally {
    lineageLoading.value = false
  }
}

function onLineageTaskChange(taskId) {
  lineageTaskFilter.value = taskId || ''
  if (selectedProject.value) {
    loadLineage(selectedProject.value.project_id)
  }
}

function reloadLineage() {
  if (selectedProject.value) {
    lineageLoaded.value = false
    loadLineage(selectedProject.value.project_id)
  }
}

const paginatedProjects = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredProjects.value.slice(start, start + pageSize.value)
})

const stageColorMap = {
  '立项': 'blue',
  '筛选': 'cyan',
  '中试': 'orange',
  '验证': 'purple',
  '定型': 'green',
}

// 项目阶段 → StatusBadge 规范态（用于左侧项目列表的阶段徽标）
function stageToBadge(stage) {
  const map = {
    '立项': 'running',
    '筛选': 'running',
    '中试': 'warning',
    '验证': 'running',
    '定型': 'success',
  }
  return map[stage] || 'default'
}

// 项目阶段选项（与 stageColorMap 保持一致）
const stageOptions = [
  { label: '立项', value: '立项' },
  { label: '筛选', value: '筛选' },
  { label: '中试', value: '中试' },
  { label: '验证', value: '验证' },
  { label: '定型', value: '定型' },
]

function progressColorMap(p) {
  if (p >= 80) return '#52c41a'
  if (p >= 40) return '#2050d0'
  return '#faad14'
}

function projectProgress(project) {
  const prog = progressMap.value[project.project_id]
  if (prog && prog.using_auto) return prog.auto_progress
  return project.iteration_progress || 0
}

function onSelectProject(project) {
  selectedProject.value = project
  // 选中项目时切回列表视图，默认显示「基本信息」tab
  rightView.value = 'list'
  rightTab.value = 'info'
  // 初始化基本信息表单
  fillInfoForm(project)
  // 拉取阶段状态（含 ECML step + 实验任务汇总），失败静默
  fetchStageStatus(project.project_id)
  // 重置血缘数据（切换到血缘 Tab 时再懒加载）
  lineageTaskFilter.value = ''
  lineageData.value = []
  lineageLoaded.value = false
  lineageSummary.value = ''
}

// 切换到"实体血缘"Tab 时懒加载
watch(rightTab, (newTab) => {
  if (newTab === 'lineage' && selectedProject.value && !lineageLoaded.value) {
    loadLineage(selectedProject.value.project_id)
  }
})

async function fetchStageStatus(projectId) {
  if (!projectId) {
    stageStatus.value = null
    return
  }
  try {
    stageStatus.value = await getProjectStageStatus(projectId)
  } catch {
    stageStatus.value = null
  }
}

// 任务卡片阶段标签：按 task_id 从 stageStatus.tasks 数组中匹配
// 匹配优先级：tasks[i].ecml.step_label > tasks[i].stage_label > 项目 current_stage
function getTaskStageInfo(task) {
  const s = stageStatus.value
  if (!s || !task) return null
  const tid = task.task_id
  if (tid && Array.isArray(s.tasks)) {
    const t = s.tasks.find((x) => x.task_id === tid)
    if (t) return t
  }
  return null
}

function getTaskStageLabel(task) {
  const t = getTaskStageInfo(task)
  if (t) {
    // 优先 ECML 细粒度 step
    if (t.ecml && t.ecml.step_label) {
      return `${t.ecml.step_label} · 第 ${t.ecml.iteration_id || 1} 轮`
    }
    // 回退到 stage_label（实验阶段 / 未启动）
    if (t.stage_label && t.stage_label !== '未启动') {
      return t.stage_label
    }
  }
  // 最终回退：项目 current_stage
  const s = stageStatus.value
  return s?.current_stage || ''
}

function getTaskStageColor(task) {
  const t = getTaskStageInfo(task)
  if (t && t.ecml) {
    if (t.ecml.is_complete) return 'success'
    return 'processing'
  }
  // 无 ECML run 时按项目 current_stage 取色
  const s = stageStatus.value
  if (!s) return 'default'
  return stageColorMap[s.current_stage] || 'default'
}

// 切换到新建项目视图
function onCreateNew() {
  selectedProject.value = null
  rightView.value = 'new'
}

// 返回项目列表视图
function onBackToList() {
  rightView.value = 'list'
}

// 新项目创建成功回调：刷新左侧列表并选中新建项目
async function onProjectCreated(project) {
  await fetchProjects()
  // 自动选中新创建的项目
  const created = projects.value.find((p) => p.project_id === project?.project_id)
  if (created) {
    onSelectProject(created)
  } else {
    rightView.value = 'list'
  }
}

watch(searchText, () => {
  currentPage.value = 1
})

function onPageSizeChange(current, size) {
  pageSize.value = size
  currentPage.value = 1
}

async function fetchProjects() {
  loading.value = true
  try {
    const data = await listProjects()
    projects.value = Array.isArray(data) ? data : []
    for (const p of projects.value) {
      getProjectProgress(p.project_id).then((res) => {
        progressMap.value = { ...progressMap.value, [p.project_id]: res }
      }).catch(() => { /* 进度加载失败不影响列表 */ })
    }
  } catch (e) {
    console.error('fetchProjects failed:', e)
    projects.value = []
  } finally { loading.value = false }
}

// 取消等待项目列表加载（仅隐藏骨架屏，后端请求仍会完成并填充数据）
function onCancelLoadProjects() {
  loading.value = false
}

async function onDelete(record) {
  try {
    await deleteProject(record.project_id)
    message.success('项目已删除')
    if (selectedProject.value?.project_id === record.project_id) {
      selectedProject.value = null
    }
    await fetchProjects()
  } catch { /* handled by interceptor（含 409 下游引用保护提示） */ }
}

function onDeleteSelected() {
  onDelete(selectedProject.value)
}

// ──────────────────────────────────────────────────────────────
// 任务编辑抽屉：手工新增 / 编辑 / 删除任务
// ──────────────────────────────────────────────────────────────
const taskDrawerOpen = ref(false)
// 'create' | 'edit'
const taskDrawerMode = ref('create')
const taskSaving = ref(false)
// 当前正在编辑的任务（编辑模式时存在）
const editingTaskId = ref('')
let propKeySeq = 0
const taskForm = reactive({
  title: '',
  deliverable: '',
  status: 'draft',
  target_properties: [],
})

function _makePropKey() {
  propKeySeq += 1
  return `p-${Date.now()}-${propKeySeq}`
}

function _resetTaskForm() {
  taskForm.title = ''
  taskForm.deliverable = ''
  taskForm.status = 'draft'
  taskForm.target_properties = []
}

function _fillPropText(prop) {
  // 为支持科学计数法输入，单独维护 _minText / _maxText
  prop._minText = prop.min != null ? String(prop.min) : ''
  prop._maxText = prop.max != null ? String(prop.max) : ''
  if (!prop._key) prop._key = _makePropKey()
}

function onPropNumberChange(prop, field, val) {
  // 支持科学计数法：先按 Number 解析，NaN 时保留 null
  if (val === '' || val == null) {
    prop[field] = null
    return
  }
  const n = Number(val)
  prop[field] = Number.isFinite(n) ? n : null
}

function addProperty() {
  const p = { name: '', direction: 'maximize', min: null, max: null, _minText: '', _maxText: '', _key: _makePropKey() }
  taskForm.target_properties.push(p)
}

function removeProperty(idx) {
  taskForm.target_properties.splice(idx, 1)
}

// 打开「新增任务」抽屉
function onAddTask() {
  if (!selectedProject.value) return
  taskDrawerMode.value = 'create'
  editingTaskId.value = ''
  _resetTaskForm()
  taskDrawerOpen.value = true
}

// 打开「编辑任务」抽屉
function onEditTask(task) {
  if (!task) return
  taskDrawerMode.value = 'edit'
  editingTaskId.value = task.task_id || ''
  taskForm.title = task.title || ''
  taskForm.deliverable = task.deliverable || ''
  taskForm.status = task.status || 'draft'
  taskForm.target_properties = (task.target_properties || []).map((p) => {
    const copy = { ...p }
    _fillPropText(copy)
    return copy
  })
  taskDrawerOpen.value = true
}

// 保存（新增 / 编辑）
async function onSaveTask() {
  if (!taskForm.title.trim()) {
    message.warning('请填写任务标题')
    return
  }
  if (!selectedProject.value) return
  const projectId = selectedProject.value.project_id
  // 构造后端期望的 target_properties（去掉 _minText/_maxText/_key 等临时字段）
  const cleanProps = (taskForm.target_properties || [])
    .filter((p) => (p.name || '').trim())
    .map((p) => ({
      name: p.name.trim(),
      direction: p.direction || 'maximize',
      min: p.min ?? null,
      max: p.max ?? null,
    }))
  const payload = {
    title: taskForm.title.trim(),
    deliverable: taskForm.deliverable.trim(),
    target_properties: cleanProps,
    status: taskForm.status || 'draft',
    assignee: '',
  }
  taskSaving.value = true
  try {
    if (taskDrawerMode.value === 'create') {
      await createProjectTask(projectId, payload)
      message.success('任务已新增')
    } else {
      await updateProjectTask(projectId, editingTaskId.value, payload)
      message.success('任务已更新')
    }
    taskDrawerOpen.value = false
    await refreshSelectedProjectTasks()
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    taskSaving.value = false
  }
}

// 删除当前编辑中的任务
async function onDeleteTask() {
  if (taskDrawerMode.value !== 'edit' || !editingTaskId.value || !selectedProject.value) return
  try {
    await deleteProjectTask(selectedProject.value.project_id, editingTaskId.value)
    message.success('任务已删除')
    taskDrawerOpen.value = false
    await refreshSelectedProjectTasks()
  } catch {
    // 错误提示由 axios 拦截器统一处理
  }
}

// 重新拉取选中项目的任务列表（增删改后刷新右侧卡片）
async function refreshSelectedProjectTasks() {
  if (!selectedProject.value) return
  const projectId = selectedProject.value.project_id
  try {
    const tasks = await listProjectTasks(projectId)
    // 直接更新 selectedProject.tasks，触发右侧列表重新渲染
    selectedProject.value = { ...selectedProject.value, tasks: Array.isArray(tasks) ? tasks : [] }
  } catch {
    // 静默：失败时不影响现有展示
  }
}

// ──────────────────────────────────────────────────────────────
// 基本信息 Tab：查看 / 编辑项目基本字段
// ──────────────────────────────────────────────────────────────
const infoSaving = ref(false)
const isEditing = ref(false) // 编辑状态机：默认只读，点击编辑后进入可编辑状态
const infoForm = reactive({
  name: '',
  target_application: '',
  current_stage: '立项',
  owner: '',
  department: '',
  start_date: '',
  end_date: '',
  budget: 0,
  iteration_progress: 0,
  target_properties: [],
  notes: '',
})

function fillInfoForm(project) {
  if (!project) return
  infoForm.name = project.name || ''
  infoForm.target_application = project.target_application || ''
  infoForm.current_stage = project.current_stage || '立项'
  infoForm.owner = project.owner || ''
  infoForm.department = project.department || ''
  infoForm.start_date = project.start_date || ''
  infoForm.end_date = project.end_date || ''
  infoForm.budget = project.budget ?? 0
  infoForm.iteration_progress = project.iteration_progress ?? 0
  infoForm.target_properties = (project.target_properties || []).map((p) => ({ ...p }))
  infoForm.notes = project.notes || ''
}

function resetInfoForm() {
  if (selectedProject.value) fillInfoForm(selectedProject.value)
}

function editInfoForm() {
  isEditing.value = true
}

function cancelEditInfoForm() {
  resetInfoForm()
  isEditing.value = false
}

function removeInfoProperty(idx) {
  infoForm.target_properties.splice(idx, 1)
}

async function saveInfoForm() {
  if (!infoForm.name.trim()) {
    message.warning('请填写项目名称')
    return
  }
  if (!selectedProject.value) return
  const projectId = selectedProject.value.project_id
  // 与后端 ProjectCreateRequest 字段保持一致；tasks 传当前值（不修改任务列表）
  const payload = {
    name: infoForm.name.trim(),
    target_application: infoForm.target_application,
    current_stage: infoForm.current_stage,
    target_properties: infoForm.target_properties,
    owner: infoForm.owner,
    notes: infoForm.notes,
    department: infoForm.department,
    start_date: infoForm.start_date || '',
    end_date: infoForm.end_date || '',
    budget: infoForm.budget ?? 0,
    iteration_progress: infoForm.iteration_progress ?? 0,
    tasks: selectedProject.value.tasks || [],
  }
  infoSaving.value = true
  try {
    const updated = await updateProject(projectId, payload)
    // 更新选中项目对象与左侧列表
    selectedProject.value = { ...selectedProject.value, ...updated }
    const idx = projects.value.findIndex((p) => p.project_id === projectId)
    if (idx >= 0) projects.value[idx] = { ...projects.value[idx], ...updated }
    message.success('基本信息已保存')
    isEditing.value = false // 保存成功后回到只读状态
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    infoSaving.value = false
  }
}

// Resize logic
let resizeStartX = 0
let resizeStartWidth = 0

function startResize(e) {
  isResizing.value = true
  resizeStartX = e.clientX
  resizeStartWidth = leftPanelWidth.value
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
}

function onResize(e) {
  if (!isResizing.value) return
  const delta = e.clientX - resizeStartX
  leftPanelWidth.value = Math.max(240, Math.min(600, resizeStartWidth + delta))
}

function stopResize() {
  if (!isResizing.value) return
  isResizing.value = false
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
}

onMounted(async () => {
  fetchProjects()
  loadUsers()
  // 从 MDM 加载任务状态选项（失败时保留硬编码兜底）
  try {
    const statusOpts = await mdmStatusOptions('task')
    if (statusOpts.length) taskStatusOptions.value = statusOpts
  } catch (e) {
    console.warn('从 MDM 加载项目任务选项失败，使用硬编码兜底:', e)
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})
</script>

<style scoped>
.projects-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.split-layout {
  display: flex;
  flex: 1;
  height: 100%;
  overflow: hidden;
}

.split-layout.is-resizing {
  cursor: col-resize;
}

/* Left Panel */
.left-panel {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-light, #f0f0f0);
  background: var(--bg-primary, #fff);
  overflow: hidden;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
}

.project-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.project-row {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light, #f5f5f5);
  transition: background 0.15s;
}

.project-row:hover {
  background: var(--bg-hover, #f5f5f5);
}

.project-row.selected {
  background: var(--primary-bg);
  border-left: 3px solid var(--primary);
  padding-left: 9px;
}

.project-row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.project-name {
  font-size: 13px;
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-dates {
  font-size: 11px;
  color: var(--text-muted, #8c8c8c);
  margin-top: 2px;
}

.text-muted {
  color: var(--text-muted, #8c8c8c);
  font-size: 11px;
}

/* Drag Handle */
.drag-handle {
  width: 4px;
  flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s;
}

.drag-handle:hover,
.split-layout.is-resizing .drag-handle {
  background: var(--primary);
}

/* Right Panel */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.right-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
  background: var(--bg-primary, #fff);
  flex-shrink: 0;
}

.right-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.back-icon {
  font-size: 14px;
  color: var(--text-secondary, #595959);
  cursor: pointer;
  transition: color 0.15s;
}

.back-icon:hover {
  color: var(--primary);
}

.right-header-title {
  font-size: 14px;
  font-weight: 600;
}

.right-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gantt-container {
  flex: 1;
  overflow: auto;
  padding: 0;
}

/* 实体图谱面板 */
.entity-graph-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 8px 12px;
}

.entity-graph-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.entity-graph-toolbar .stats-tag {
  margin-left: auto;
  color: #6b7280;
}

/* Tab 容器：占满右侧剩余空间 */
.right-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.right-tabs-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.right-tabs-inner :deep(.ant-tabs-nav) {
  margin: 0 16px;
  padding-top: 4px;
}

.right-tabs-inner :deep(.ant-tabs-content-holder) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.right-tabs-inner :deep(.ant-tabs-content) {
  height: 100%;
}

.right-tabs-inner :deep(.ant-tabs-tabpane) {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 项目任务与交付要求面板 */
.project-tasks-panel {
  flex: 1;
  padding: 12px 16px;
  background: var(--realsee-surface, #fff);
  overflow-y: auto;
}

/* 基本信息面板 */
.project-info-panel {
  flex: 1;
  padding: 12px 16px;
  background: var(--realsee-surface, #fff);
  overflow-y: auto;
}

.info-form {
  max-width: 900px;
}

/* 只读模式下的表单样式 */
.info-form :deep(.ant-input[disabled]),
.info-form :deep(.ant-select-disabled .ant-select-selector),
.info-form :deep(.ant-input-number-disabled),
.info-form :deep(.ant-picker-disabled),
.info-form :deep(.ant-input-textarea-disabled) {
  color: var(--text-primary);
  background: transparent;
  border-color: transparent;
  cursor: default;
}

.info-form :deep(.ant-select-disabled .ant-select-arrow) {
  display: none;
}

.info-props {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.info-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-light, #f0f0f0);
}

.info-meta {
  font-size: 11px;
  color: var(--text-muted, #8c8c8c);
}

.tasks-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-card {
  padding: 10px 12px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: 6px;
}

.task-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.task-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary-bg, #e6f0ff);
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.task-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  flex: 1;
  min-width: 0;
}

.stage-tag {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 11px;
}

.task-card-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  line-height: 1.6;
  margin-top: 2px;
  flex-wrap: wrap;
}

.row-label {
  color: var(--text-secondary, #666);
  flex-shrink: 0;
}

.row-value {
  color: var(--text-primary, #333);
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.prop-tag {
  font-family: var(--font-family-mono, "JetBrains Mono", Consolas, monospace);
  font-size: 11px;
}

.text-muted {
  color: var(--text-muted, #999);
}

/* 新建项目内嵌表单容器：占满剩余高度并允许滚动 */
.embedded-form-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 任务卡片上的「编辑」按钮：默认隐藏，hover 卡片时显示 */
.task-edit-btn {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--text-secondary, #666);
  opacity: 0;
  transition: opacity 0.15s;
}

.task-card:hover .task-edit-btn {
  opacity: 1;
}

/* 任务列表底部「新增任务」按钮区 */
.tasks-panel-footer {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-light, #f0f0f0);
}

/* 任务编辑抽屉表单 */
.task-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #333);
}

.form-label .required {
  color: var(--error-color, #ff4d4f);
  margin-left: 2px;
}

/* 目标属性编辑器（抽屉内） */
.prop-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: 6px;
  padding: 8px;
}

.prop-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr 1fr 28px;
  gap: 6px;
  align-items: center;
}

.prop-row.prop-header {
  font-size: 11px;
  color: var(--text-secondary, #999);
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--border-light, #f0f0f0);
  margin-bottom: 2px;
}

.prop-sci-input :deep(input) {
  font-family: var(--font-family-mono, "JetBrains Mono", Consolas, monospace);
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  align-items: center;
}

/* 数据血缘面板 */
.lineage-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 8px 16px;
  overflow: hidden;
}

.lineage-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.lineage-summary {
  font-size: 12px;
  color: var(--text-secondary, #666);
}

.lineage-tree-container {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.lineage-tree {
  font-size: 13px;
}

.lineage-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.lineage-node-icon {
  color: var(--primary);
  font-size: 14px;
}

.lineage-node-label {
  color: var(--text-primary, #333);
}

.lineage-node-meta {
  font-size: 11px;
  color: var(--text-muted, #999);
}

.lineage-node-status {
  margin: 0;
  font-size: 10px;
  line-height: 16px;
  padding: 0 4px;
}
</style>