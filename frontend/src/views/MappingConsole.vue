<template>
  <div class="mapping-console">
    <SectionHeader
      title="映射控制台"
      subtitle="业务活动 → 智能体 → 工具 三层绑定配置"
    />

    <!-- 统计条 -->
    <div class="stat-row">
      <div class="stat-item">
        <span class="stat-value">{{ overview.total_activities }}</span>
        <span class="stat-label">业务活动</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ agentCount }}</span>
        <span class="stat-label">绑定智能体</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ overview.total_tools }}</span>
        <span class="stat-label">注册工具</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ scpToolCount }}</span>
        <span class="stat-label">SCP 工具</span>
      </div>
    </div>

    <!-- 过滤栏 -->
    <div class="filter-bar">
      <a-space wrap>
        <a-select
          v-model:value="filters.category"
          placeholder="活动类别"
          allow-clear
          style="width: 140px"
          size="small"
          @change="loadOverview"
        >
          <a-select-option v-for="c in overview.categories" :key="c" :value="c">
            {{ categoryLabel(c) }}
          </a-select-option>
        </a-select>
        <a-input
          v-model:value="filters.keyword"
          placeholder="搜索活动 / 智能体 / 工具"
          allow-clear
          style="width: 240px"
          size="small"
        />
        <a-button size="small" @click="loadOverview">刷新</a-button>
        <a-button v-if="isAdmin" type="primary" size="small" @click="showToolRegister = true">
          注册新工具
        </a-button>
      </a-space>
    </div>

    <!-- 主从详情视图（决策 13-B） -->
    <a-table
      :columns="columns"
      :data-source="filteredActivities"
      :pagination="{ pageSize: 15, size: 'small' }"
      :expandable="{ expandedRowRender }"
      row-key="activity_id"
      size="small"
      :loading="loading"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'activity'">
          <div class="activity-cell">
            <div class="activity-name">{{ record.activity_name || record.activity_id }}</div>
            <div class="activity-id">{{ record.activity_id }}</div>
          </div>
        </template>
        <template v-else-if="column.key === 'category'">
          <a-tag :color="categoryColor(record.activity_category)">
            {{ categoryLabel(record.activity_category) }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'agent'">
          <div class="agent-cell">
            <a-tag color="blue">{{ record.agent_id }}</a-tag>
            <div v-if="record.capability_need" class="capability-need">
              能力: {{ record.capability_need }}
            </div>
          </div>
        </template>
        <template v-else-if="column.key === 'tools'">
          <div class="tools-cell">
            <a-tag v-for="tb in (record.tool_bindings || [])" :key="tb.binding_id" :color="toolColor(tb)">
              {{ toolLabel(tb) }}
            </a-tag>
            <span v-if="!record.tool_bindings?.length" class="empty-hint">未绑定</span>
          </div>
        </template>
        <template v-else-if="column.key === 'enabled'">
          <a-switch
            :checked="record.enabled"
            size="small"
            :disabled="!isAdmin"
            @change="(v) => toggleActivity(record, v)"
          />
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button size="small" type="link" @click="onViewDetail(record)">详情</a-button>
          <a-button size="small" type="link" @click="editActivity(record)">编辑</a-button>
        </template>
      </template>

      <!-- 展开行：工具绑定详情 -->
      <template #expandedRowRender="{ record }">
        <div class="expanded-detail">
          <a-table
            :columns="toolColumns"
            :data-source="record.tool_bindings || []"
            :pagination="false"
            row-key="binding_id"
            size="small"
          >
            <template #bodyCell="{ column, record: tb }">
              <template v-if="column.key === 'primary_tool'">
                <a-tag color="green">{{ tb.primary_tool_id }}</a-tag>
              </template>
              <template v-else-if="column.key === 'whitelist'">
                <div class="tag-list">
                  <a-tag v-for="t in tb.tools_whitelist" :key="t" color="blue">{{ t }}</a-tag>
                  <span v-if="!tb.tools_whitelist?.length" class="empty-hint">—</span>
                </div>
              </template>
              <template v-else-if="column.key === 'blacklist'">
                <div class="tag-list">
                  <a-tag v-for="t in tb.tools_blacklist" :key="t" color="red">{{ t }}</a-tag>
                  <span v-if="!tb.tools_blacklist?.length" class="empty-hint">—</span>
                </div>
              </template>
              <template v-else-if="column.key === 'model_override'">
                <div class="tag-list">
                  <a-tag v-for="(m, t) in tb.tool_model_override" :key="t" color="orange">
                    {{ t }} → {{ m }}
                  </a-tag>
                  <span v-if="!tb.tool_model_override || !Object.keys(tb.tool_model_override).length" class="empty-hint">
                    跟随智能体
                  </span>
                </div>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button v-if="isAdmin" size="small" type="link" @click="editToolBinding(tb)">编辑</a-button>
              </template>
            </template>
          </a-table>
        </div>
      </template>
    </a-table>

    <!-- 编辑业务活动绑定弹窗 -->
    <a-modal
      v-model:open="showEditActivity"
      title="编辑业务活动绑定"
      width="520px"
      @ok="saveActivity"
      :confirm-loading="saving"
    >
      <a-form layout="vertical">
        <a-form-item label="活动 ID">
          <a-input :value="editingActivity?.activity_id" disabled />
        </a-form-item>
        <a-form-item label="活动名称">
          <a-input v-model:value="editingActivity.activity_name" />
        </a-form-item>
        <a-form-item label="绑定智能体">
          <a-input v-model:value="editingActivity.agent_id" placeholder="builtin_xxx" />
        </a-form-item>
        <a-form-item label="能力需求（用于智能体不可用时回退）">
          <a-input v-model:value="editingActivity.capability_need" />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea v-model:value="editingActivity.notes" :rows="2" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 编辑工具绑定弹窗 -->
    <a-modal
      v-model:open="showEditTool"
      title="编辑智能体工具绑定"
      width="600px"
      @ok="saveToolBinding"
      :confirm-loading="saving"
    >
      <a-form layout="vertical">
        <a-form-item label="智能体">
          <a-input :value="editingTool?.agent_id" disabled />
        </a-form-item>
        <a-form-item label="能力">
          <a-input :value="editingTool?.capability" disabled />
        </a-form-item>
        <a-form-item label="主工具 ID">
          <a-input v-model:value="editingTool.primary_tool_id" />
        </a-form-item>
        <a-form-item label="白名单工具（追加到候选池）">
          <a-select
            v-model:value="editingTool.tools_whitelist"
            mode="tags"
            placeholder="输入工具 ID 回车添加"
          />
        </a-form-item>
        <a-form-item label="黑名单工具（从候选池排除）">
          <a-select
            v-model:value="editingTool.tools_blacklist"
            mode="tags"
            placeholder="输入工具 ID 回车添加"
          />
        </a-form-item>
        <a-form-item label="工具模型覆盖（JSON）">
          <a-textarea
            v-model:value="editingTool.model_override_json"
            :rows="3"
            placeholder='{"tool_id": "model_name"}'
          />
          <div class="form-help">为空时跟随智能体配置的模型</div>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 新工具注册向导（决策 11-C） -->
    <a-modal
      v-model:open="showToolRegister"
      title="注册新工具"
      width="640px"
      @ok="saveNewTool"
      :confirm-loading="saving"
    >
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="工具名称" required>
              <a-input v-model:value="newTool.name" placeholder="如 分子描述符计算" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="来源" required>
              <a-select v-model:value="newTool.source">
                <a-select-option value="local">本地</a-select-option>
                <a-select-option value="scp">SCP</a-select-option>
                <a-select-option value="skill">SKILL</a-select-option>
                <a-select-option value="mcp">MCP</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="关联能力标签" required>
          <a-select
            v-model:value="newTool.capability_refs"
            mode="tags"
            placeholder="输入能力标签回车添加"
          />
          <div class="form-help">工具按能力标签自动进入智能体候选池</div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="执行模式">
              <a-select v-model:value="newTool.execution_mode">
                <a-select-option value="sync">同步</a-select-option>
                <a-select-option value="async">异步</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="风险等级">
              <a-select v-model:value="newTool.risk_level">
                <a-select-option value="A">A（可自动）</a-select-option>
                <a-select-option value="B">B（辅助证据）</a-select-option>
                <a-select-option value="C">C（白名单）</a-select-option>
                <a-select-option value="D">D（禁止）</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item v-if="newTool.source === 'scp'" label="SCP 内部名">
          <a-input v-model:value="newTool.scp_internal_name" placeholder="scp_xxx" />
        </a-form-item>
        <a-form-item v-if="newTool.source === 'skill'" label="SKILL ID">
          <a-input v-model:value="newTool.skill_id" />
        </a-form-item>
        <a-form-item v-if="newTool.source === 'local' || newTool.source === 'mcp'" label="MCP 工具名">
          <a-input v-model:value="newTool.mcp_tool_name" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="newTool.description" :rows="2" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 详情抽屉 -->
    <a-drawer
      v-model:open="drawerVisible"
      title="映射详情"
      width="720"
      placement="right"
    >
      <a-tabs v-model:activeKey="detailTab">
        <a-tab-pane key="info" tab="详情">
          <!-- 基本信息 -->
          <div class="detail-section">
            <div class="detail-section-title">基本信息</div>
            <a-descriptions bordered size="small" :column="2">
              <a-descriptions-item label="业务活动 ID" :span="2">
                <span class="mono-text">{{ selectedMapping.activity_id }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="活动名称" :span="2">{{ selectedMapping.activity_name || '—' }}</a-descriptions-item>
              <a-descriptions-item label="活动类别">
                <a-tag :color="categoryColor(selectedMapping.activity_category)">
                  {{ categoryLabel(selectedMapping.activity_category) }}
                </a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="启用状态">
                <a-tag :color="selectedMapping.enabled ? 'green' : 'default'">
                  {{ selectedMapping.enabled ? '已启用' : '已禁用' }}
                </a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="能力需求" :span="2">{{ selectedMapping.capability_need || '—' }}</a-descriptions-item>
              <a-descriptions-item label="备注" :span="2">{{ selectedMapping.notes || '—' }}</a-descriptions-item>
            </a-descriptions>
          </div>

          <!-- 绑定关系 -->
          <div class="detail-section">
            <div class="detail-section-title">绑定关系</div>
            <a-descriptions bordered size="small" :column="1">
              <a-descriptions-item label="绑定智能体">
                <a-tag v-if="selectedMapping.agent_id" color="blue">{{ selectedMapping.agent_id }}</a-tag>
                <span v-else class="empty-hint">未绑定智能体</span>
              </a-descriptions-item>
              <a-descriptions-item label="工具绑定数">{{ selectedMapping.tool_bindings?.length || 0 }} 项</a-descriptions-item>
            </a-descriptions>
          </div>

          <!-- 工具配置 -->
          <div class="detail-section">
            <div class="detail-section-title">
              工具配置
              <a-tag color="blue" class="section-count-tag">{{ selectedMapping.tool_bindings?.length || 0 }} 项</a-tag>
            </div>
            <a-table
              v-if="selectedMapping.tool_bindings?.length"
              :columns="detailToolColumns"
              :data-source="selectedMapping.tool_bindings"
              :pagination="false"
              row-key="binding_id"
              size="small"
            >
              <template #bodyCell="{ column, record: tb }">
                <template v-if="column.key === 'capability'">
                  <a-tag color="cyan">{{ tb.capability || '—' }}</a-tag>
                </template>
                <template v-else-if="column.key === 'primary_tool'">
                  <a-tag color="green">{{ tb.primary_tool_id || '未设置' }}</a-tag>
                </template>
                <template v-else-if="column.key === 'whitelist'">
                  <div class="tag-list">
                    <a-tag v-for="t in tb.tools_whitelist" :key="t" color="blue">{{ t }}</a-tag>
                    <span v-if="!tb.tools_whitelist?.length" class="empty-hint">—</span>
                  </div>
                </template>
                <template v-else-if="column.key === 'blacklist'">
                  <div class="tag-list">
                    <a-tag v-for="t in tb.tools_blacklist" :key="t" color="red">{{ t }}</a-tag>
                    <span v-if="!tb.tools_blacklist?.length" class="empty-hint">—</span>
                  </div>
                </template>
                <template v-else-if="column.key === 'enabled'">
                  <a-tag :color="tb.enabled === false ? 'default' : 'green'">
                    {{ tb.enabled === false ? '禁用' : '启用' }}
                  </a-tag>
                </template>
              </template>
            </a-table>
            <a-empty v-else description="暂无工具绑定" />
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import SectionHeader from '@/components/SectionHeader.vue'
import {
  getMappingOverview,
  upsertActivityBinding,
  upsertToolBinding,
  registerTool,
} from '@/api/mappings'
import { useSystemStore } from '@/stores/system'
import { MESSAGES } from '@/constants/glossary'

const systemStore = useSystemStore()
const isAdmin = computed(() => systemStore.user?.role === 'admin')

const loading = ref(false)
const saving = ref(false)
const overview = reactive({
  activities: [],
  tools: [],
  categories: [],
  total_activities: 0,
  total_tools: 0,
})

const filters = reactive({
  category: '',
  keyword: '',
})

const columns = [
  { title: '业务活动', key: 'activity', width: 220 },
  { title: '类别', key: 'category', width: 100 },
  { title: '绑定智能体', key: 'agent', width: 200 },
  { title: '工具绑定', key: 'tools' },
  { title: '启用', key: 'enabled', width: 70 },
  { title: '操作', key: 'action', width: 120 },
]

const toolColumns = [
  { title: '能力', dataIndex: 'capability', width: 180 },
  { title: '主工具', key: 'primary_tool', width: 160 },
  { title: '白名单', key: 'whitelist' },
  { title: '黑名单', key: 'blacklist' },
  { title: '模型覆盖', key: 'model_override' },
  { title: '操作', key: 'action', width: 80 },
]

const detailToolColumns = [
  { title: '能力', dataIndex: 'capability', key: 'capability', width: 140 },
  { title: '主工具', key: 'primary_tool', width: 140 },
  { title: '白名单', key: 'whitelist' },
  { title: '黑名单', key: 'blacklist' },
  { title: '状态', key: 'enabled', width: 70 },
]

const filteredActivities = computed(() => {
  let items = overview.activities
  if (filters.category) {
    items = items.filter(a => a.activity_category === filters.category)
  }
  if (filters.keyword) {
    const kw = filters.keyword.toLowerCase()
    items = items.filter(a =>
      a.activity_id.toLowerCase().includes(kw) ||
      a.activity_name?.toLowerCase().includes(kw) ||
      a.agent_id?.toLowerCase().includes(kw) ||
      a.tool_bindings?.some(tb => tb.primary_tool_id?.toLowerCase().includes(kw))
    )
  }
  return items
})

const agentCount = computed(() =>
  new Set(overview.activities.map(a => a.agent_id)).size
)
const scpToolCount = computed(() =>
  overview.tools.filter(t => t.source === 'scp').length
)

const categoryLabels = {
  ecml: 'ECML',
  project: '项目',
  experiment: '实验',
  discovery: '发现',
  synthesis: '合成',
  battery: '电池',
  quality: '质量',
}

const categoryLabel = (c) => categoryLabels[c] || c
const categoryColor = (c) => ({
  ecml: 'processing',
  project: 'success',
  experiment: 'warning',
  discovery: 'cyan',
  synthesis: 'purple',
  battery: 'orange',
  quality: 'red',
}[c] || 'default')

const toolLabel = (tb) => {
  if (!tb.primary_tool_id) return '未设置'
  return tb.primary_tool_id
}
const toolColor = (tb) => tb.enabled ? 'green' : 'default'

// ----- 详情抽屉 -----
const drawerVisible = ref(false)
const detailTab = ref('info')
const selectedMapping = ref({})

function onViewDetail(record) {
  selectedMapping.value = record
  detailTab.value = 'info'
  drawerVisible.value = true
}

// ----- 编辑业务活动 -----
const showEditActivity = ref(false)
const editingActivity = ref({})

const editActivity = (record) => {
  editingActivity.value = { ...record }
  showEditActivity.value = true
}

const toggleActivity = async (record, enabled) => {
  try {
    await upsertActivityBinding(record.activity_id, {
      activity_id: record.activity_id,
      activity_name: record.activity_name,
      activity_category: record.activity_category,
      agent_id: record.agent_id,
      capability_need: record.capability_need,
      enabled,
      notes: record.notes || '',
    })
    record.enabled = enabled
    message.success(enabled ? '已启用' : '已禁用')
  } catch (e) {
    // 错误已由 client 拦截器处理
  }
}

const saveActivity = async () => {
  saving.value = true
  try {
    await upsertActivityBinding(editingActivity.value.activity_id, {
      activity_id: editingActivity.value.activity_id,
      activity_name: editingActivity.value.activity_name,
      activity_category: editingActivity.value.activity_category,
      agent_id: editingActivity.value.agent_id,
      capability_need: editingActivity.value.capability_need,
      enabled: editingActivity.value.enabled ?? true,
      notes: editingActivity.value.notes || '',
    })
    message.success(MESSAGES.saveSuccess)
    showEditActivity.value = false
    await loadOverview()
  } catch (e) {
    // 错误已由 client 拦截器处理
  } finally {
    saving.value = false
  }
}

// ----- 编辑工具绑定 -----
const showEditTool = ref(false)
const editingTool = ref({})

const editToolBinding = (tb) => {
  editingTool.value = {
    ...tb,
    model_override_json: JSON.stringify(tb.tool_model_override || {}, null, 2),
  }
  showEditTool.value = true
}

const saveToolBinding = async () => {
  saving.value = true
  try {
    let modelOverride = {}
    try {
      modelOverride = JSON.parse(editingTool.value.model_override_json || '{}')
    } catch {
      message.error('模型覆盖 JSON 格式错误')
      saving.value = false
      return
    }
    await upsertToolBinding(editingTool.value.agent_id, editingTool.value.capability, {
      agent_id: editingTool.value.agent_id,
      capability: editingTool.value.capability,
      primary_tool_id: editingTool.value.primary_tool_id,
      tools_whitelist: editingTool.value.tools_whitelist || [],
      tools_blacklist: editingTool.value.tools_blacklist || [],
      tool_model_override: modelOverride,
      enabled: editingTool.value.enabled ?? true,
    })
    message.success(MESSAGES.saveSuccess)
    showEditTool.value = false
    await loadOverview()
  } catch (e) {
    // 错误已由 client 拦截器处理
  } finally {
    saving.value = false
  }
}

// ----- 注册新工具 -----
const showToolRegister = ref(false)
const newTool = reactive({
  name: '',
  source: 'local',
  capability_refs: [],
  execution_mode: 'sync',
  scp_internal_name: '',
  skill_id: '',
  mcp_tool_name: '',
  risk_level: 'B',
  description: '',
})

const saveNewTool = async () => {
  if (!newTool.name) {
    message.warning('请填写工具名称')
    return
  }
  if (!newTool.capability_refs?.length) {
    message.warning('请关联至少一个能力标签')
    return
  }
  saving.value = true
  try {
    await registerTool({
      name: newTool.name,
      source: newTool.source,
      capability_refs: newTool.capability_refs,
      execution_mode: newTool.execution_mode,
      scp_internal_name: newTool.scp_internal_name,
      skill_id: newTool.skill_id,
      mcp_tool_name: newTool.mcp_tool_name,
      risk_level: newTool.risk_level,
      enabled: true,
      description: newTool.description,
    })
    message.success('工具注册成功')
    showToolRegister.value = false
    // 重置表单
    Object.assign(newTool, {
      name: '', source: 'local', capability_refs: [], execution_mode: 'sync',
      scp_internal_name: '', skill_id: '', mcp_tool_name: '',
      risk_level: 'B', description: '',
    })
    await loadOverview()
  } catch (e) {
    // 错误已由 client 拦截器处理
  } finally {
    saving.value = false
  }
}

// ----- 加载数据 -----
const loadOverview = async () => {
  loading.value = true
  try {
    const data = await getMappingOverview()
    Object.assign(overview, data)
  } catch (e) {
    // 错误已由 client 拦截器处理
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadOverview()
})
</script>

<style scoped>
.mapping-console {
  padding: 16px;
}

.stat-row {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 16px;
  background: var(--bg-card, #fff);
  border-radius: 8px;
  border: 1px solid var(--border-color, #f0f0f0);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary, #1f1f1f);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary, #8c8c8c);
  margin-top: 4px;
}

.filter-bar {
  margin-bottom: 16px;
}

.activity-cell .activity-name {
  font-weight: 500;
}

.activity-cell .activity-id {
  font-size: 11px;
  color: var(--text-secondary, #8c8c8c);
}

.agent-cell .capability-need {
  font-size: 11px;
  color: var(--text-secondary, #8c8c8c);
  margin-top: 2px;
}

.tools-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.empty-hint {
  color: var(--text-secondary, #8c8c8c);
  font-size: 12px;
}

.expanded-detail {
  padding: 12px;
  background: var(--bg-secondary, #fafafa);
  border-radius: 4px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.form-help {
  font-size: 12px;
  color: var(--text-secondary, #8c8c8c);
  margin-top: 4px;
}

/* —— 详情抽屉：分区样式 —— */
.detail-section {
  margin-bottom: 20px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1f1f1f);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-count-tag {
  font-size: 11px;
}

.mono-text {
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
}
</style>
