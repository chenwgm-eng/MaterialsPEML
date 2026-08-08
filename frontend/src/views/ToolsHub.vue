<template>
  <div class="tools-hub">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">工具与连接器</h1>
        <p class="page-subtitle">Agent 可调用的工具与外部科研能力接入</p>
      </div>
      <div class="header-actions">
        <a-button :loading="loading" @click="refreshAll">
          <template #icon><ReloadOutlined /></template>
          {{ loading ? MESSAGES.loading + '…' : '刷新' }}
        </a-button>
      </div>
    </div>

    <!-- 顶部引导条（默认折叠） -->
    <a-collapse :bordered="false" class="intro-collapse" :default-active-key="[]">
      <a-collapse-panel key="intro" header="这张页面是干什么的？">
        <div class="intro-content">
          <p>本页管理 Agent 在研发流程中可调用的工具，按数据流分 3 层：</p>
          <ol class="intro-list">
            <li><b>外部能力源</b>：接入的外部科研工具平台（SCP 服务器），启用后扩展系统能力边界</li>
            <li><b>能力绑定</b>：将外部能力封装为 Agent 可调用工具，标注 ECML 研发闭环的接入步骤</li>
            <li><b>本地兜底工具</b>：系统内置工具，外部能力不可用时自动降级到本地</li>
          </ol>
          <p class="intro-impact">
            <BulbOutlined /> 改动「启用开关」会影响 ECML 研发闭环 Step 2/3/4/6 的自动调用。
            <span v-if="!isAdmin" class="intro-readonly">（当前为只读模式，仅管理员可操作）</span>
          </p>
        </div>
      </a-collapse-panel>
    </a-collapse>

    <!-- 第 1 层：外部能力源（SCP 服务器） -->
    <section class="layer">
      <div class="layer-header">
        <div class="layer-title">
          <span class="layer-number">1</span>
          <span class="layer-name">外部能力源</span>
          <a-tag color="cyan" class="layer-count">{{ scpServerBindings.length }} 个 SCP 服务器</a-tag>
        </div>
        <div class="layer-desc">接入的外部科研工具平台，启用后 Agent 可自动调用</div>
      </div>
      <a-spin :spinning="scpLoading">
        <div class="card-grid">
          <div
            v-for="binding in scpServerBindings"
            :key="binding.internal_name"
            class="scp-card"
            role="button"
            tabindex="0"
            :aria-label="`SCP 服务器 ${binding.summary || binding.internal_name}，按 Enter 或 Space 查看详情`"
            @click="(e) => onSCPCardClick(binding, e)"
            @keydown.enter="openSCPDetail(binding)"
            @keydown.space.prevent="openSCPDetail(binding)"
          >
            <div class="scp-card-header">
              <div class="scp-card-title" :title="binding.summary || binding.internal_name">
                {{ binding.summary || binding.internal_name }}
              </div>
              <a-tooltip :title="!isAdmin ? '仅管理员可启用/停用' : ''">
                <span class="tt-btn-wrap">
                  <a-switch
                    :checked="binding.enabled"
                    size="small"
                    :disabled="!isAdmin"
                    :loading="scpUpdating === binding.internal_name"
                    @change="(checked) => toggleSCPEnabled(binding, checked)"
                  />
                </span>
              </a-tooltip>
            </div>
            <div class="scp-card-meta">
              <a-tag color="blue">{{ binding.provider || '-' }}</a-tag>
              <span class="scp-card-tools">{{ binding.tool_count ?? '-' }} 工具</span>
              <a-tag :color="riskLevelColor(binding.risk_level)">风险 {{ binding.risk_level }}</a-tag>
            </div>
            <div class="scp-card-desc" :title="binding.description">{{ binding.description || '-' }}</div>
            <div class="scp-card-actions">
              <a-button size="small" type="link" @click="openSCPDetail(binding)">
                <template #icon><EyeOutlined /></template>
                查看详情
              </a-button>
              <a-tooltip :title="!isAdmin ? '仅管理员可执行自检' : ''">
                <span class="tt-btn-wrap">
                  <a-button
                    size="small"
                    type="link"
                    :loading="testingId === binding.internal_name"
                    :disabled="!isAdmin"
                    @click="onTest(binding)"
                  >
                    <template #icon><PlayCircleOutlined /></template>
                    {{ isAdmin ? '自检' : '自检（需 admin）' }}
                  </a-button>
                </span>
              </a-tooltip>
            </div>
          </div>
        </div>
        <EmptyState v-if="!scpLoading && scpServerBindings.length === 0" type="data" description="暂无 SCP 服务器" />
      </a-spin>

      <a-alert
        v-if="scpError"
        type="error"
        :message="scpError"
        show-icon
        closable
        style="margin-top: 12px"
        @close="scpError = ''"
      />
    </section>

    <!-- 第 2 层：能力绑定 -->
    <section class="layer">
      <div class="layer-header">
        <div class="layer-title">
          <span class="layer-number">2</span>
          <span class="layer-name">能力绑定</span>
          <a-tag color="purple" class="layer-count">{{ capabilityBindings.length }} 个能力</a-tag>
        </div>
        <div class="layer-desc">将外部能力封装为 Agent 可调用工具，标注 ECML 研发闭环的接入步骤</div>
      </div>
      <a-table
        :columns="capabilityColumns"
        :data-source="capabilityBindings"
        :pagination="false"
        size="small"
        row-key="internal_name"
        :loading="scpLoading"
        :scroll="{ x: 800 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <span class="cap-name">{{ capabilityLabel(record.internal_name) }}</span>
          </template>
          <template v-if="column.key === 'source'">
            <a-tooltip :title="sourceTooltip(record)">
              <a-tag color="cyan">{{ sourceLabel(record.server_id) }}</a-tag>
            </a-tooltip>
          </template>
          <template v-if="column.key === 'ecml_steps'">
            <template v-if="record.ecml_steps && record.ecml_steps.length">
              <a-tag v-for="step in record.ecml_steps" :key="step" color="orange">Step {{ step }}</a-tag>
            </template>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'risk_level'">
            <a-tag :color="riskLevelColor(record.risk_level)">{{ record.risk_level }}</a-tag>
          </template>
          <template v-if="column.key === 'enabled'">
            <a-tooltip :title="!isAdmin ? '仅管理员可启用/停用' : ''">
              <span class="tt-btn-wrap">
                <a-switch
                  :checked="record.enabled"
                  size="small"
                  :disabled="!isAdmin"
                  :loading="scpUpdating === record.internal_name"
                  @change="(checked) => toggleSCPEnabled(record, checked)"
                />
              </span>
            </a-tooltip>
          </template>
          <template v-if="column.key === 'actions'">
            <a-button size="small" type="link" @click="openSCPDetail(record)">
              <template #icon><EyeOutlined /></template>
              查看详情
            </a-button>
          </template>
        </template>
      </a-table>
    </section>

    <!-- SKILL 层：声明式组合能力 -->
    <section class="layer">
      <div class="layer-header">
        <div class="layer-title">
          <span class="layer-number">3</span>
          <span class="layer-name">SKILL 组合能力</span>
          <a-tag color="geekblue" class="layer-count">{{ skills.length }} 个 SKILL</a-tag>
        </div>
        <div class="layer-desc">声明式编排多个 SCP 工具的顺序流水线，一键调用组合能力</div>
      </div>
      <a-spin :spinning="skillLoading">
        <div class="card-grid">
          <div
            v-for="skill in skills"
            :key="skill.skill_id"
            class="scp-card"
          >
            <div class="scp-card-header">
              <div class="scp-card-title" :title="skill.name">{{ skill.name }}</div>
              <a-tag v-if="skill.official" color="green" style="font-size: 11px">官方认证</a-tag>
            </div>
            <div class="scp-card-meta">
              <a-tag color="blue">{{ skill.provider || '-' }}</a-tag>
              <span class="scp-card-tools">{{ skill.pipeline?.length || 0 }} 步 · {{ skill.server_count }} 个 server</span>
              <a-tag :color="riskLevelColor(skill.risk_level)">风险 {{ skill.risk_level }}</a-tag>
            </div>
            <div class="scp-card-desc" :title="skill.description">{{ skill.description || '-' }}</div>
            <div class="scp-card-actions">
              <a-button size="small" type="link" @click="openSkillDetail(skill)">
                <template #icon><EyeOutlined /></template>
                查看详情
              </a-button>
              <a-tooltip :title="!isAdmin ? '仅管理员可执行自检' : ''">
                <span class="tt-btn-wrap">
                  <a-button
                    size="small"
                    type="link"
                    :loading="skillTestingId === skill.skill_id"
                    :disabled="!isAdmin"
                    @click="onSkillTest(skill)"
                  >
                    <template #icon><PlayCircleOutlined /></template>
                    {{ isAdmin ? '自检' : '自检（需 admin）' }}
                  </a-button>
                </span>
              </a-tooltip>
            </div>
          </div>
        </div>
        <EmptyState v-if="!skillLoading && skills.length === 0" type="data" description="暂无 SKILL" />
      </a-spin>
    </section>

    <!-- 第 4 层：本地兜底工具 -->
    <section class="layer">
      <div class="layer-header">
        <div class="layer-title">
          <span class="layer-number">4</span>
          <span class="layer-name">本地兜底工具</span>
          <a-tag color="green" class="layer-count">{{ localTools.length }} 个工具</a-tag>
        </div>
        <div class="layer-desc">系统内置工具，外部能力不可用时自动降级到本地</div>
      </div>
      <a-alert
        v-if="toolsError"
        type="error"
        :message="toolsError"
        show-icon
        closable
        style="margin-bottom: 12px"
        @close="toolsError = ''"
      />
      <a-table
        :columns="localToolColumns"
        :data-source="localTools"
        :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
        size="small"
        row-key="name"
        :loading="toolsLoading"
        :scroll="{ x: 900 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <span class="tool-name">{{ record.name }}</span>
          </template>
          <template v-if="column.key === 'risk_level'">
            <a-tag v-if="record.risk_level" :color="riskLevelColor(record.risk_level)">{{ record.risk_level }}</a-tag>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'availability'">
            <a-tag v-if="record.availability" :color="availabilityColor(record.availability)">{{ availabilityLabel(record.availability) }}</a-tag>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'description'">
            <a-tooltip v-if="record.description" :title="record.description">
              <span class="text-muted">{{ record.description }}</span>
            </a-tooltip>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'test'">
            <a-tag v-if="testStatus[record.name]" :color="testStateColor(testStatus[record.name].state)">
              {{ testStateLabel(testStatus[record.name].state) }}
            </a-tag>
            <span v-else class="text-muted">—</span>
          </template>
          <template v-if="column.key === 'actions'">
            <a-button size="small" type="link" @click="openLocalDetail(record)">详情</a-button>
            <a-tooltip :title="!isAdmin ? '仅管理员可执行自检' : ''">
              <span class="tt-btn-wrap">
                <a-button
                  size="small"
                  type="link"
                  :loading="testStatus[record.name]?.state === 'testing'"
                  :disabled="!isAdmin"
                  @click="onLocalTest(record)"
                >{{ isAdmin ? '自检' : '自检（需 admin）' }}</a-button>
              </span>
            </a-tooltip>
          </template>
        </template>
      </a-table>
    </section>

    <!-- SCP 详情抽屉 -->
    <a-drawer
      :open="scpDetailVisible"
      :title="scpDetailBinding?.summary || scpDetailBinding?.internal_name || ''"
      placement="right"
      width="680px"
      :footer="null"
      @update:open="(v) => (scpDetailVisible = v)"
    >
      <div v-if="scpDetailBinding" class="scp-detail">
        <div class="scp-detail-section">
          <div class="scp-detail-title">基础信息</div>
          <a-descriptions size="small" :column="2" bordered>
            <a-descriptions-item label="Internal Name" :span="2">
              <span class="mono">{{ scpDetailBinding.internal_name }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="Server ID">
              <span class="mono">{{ scpDetailBinding.server_id || '-' }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="Provider">
              <a-tag color="blue">{{ scpDetailBinding.provider || '-' }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="风险等级">
              <a-tag :color="riskLevelColor(scpDetailBinding.risk_level)">{{ scpDetailBinding.risk_level }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="工具数">
              {{ scpDetailBinding.tool_count ?? '-' }}
            </a-descriptions-item>
            <a-descriptions-item label="启用状态">
              <a-tooltip :title="!isAdmin ? '仅管理员可启用/停用' : ''">
                <span class="tt-btn-wrap">
                  <a-switch
                    :checked="scpDetailBinding.enabled"
                    size="small"
                    :disabled="!isAdmin"
                    :loading="scpUpdating === scpDetailBinding.internal_name"
                    @change="(checked) => toggleSCPEnabled(scpDetailBinding, checked)"
                  />
                </span>
              </a-tooltip>
            </a-descriptions-item>
            <a-descriptions-item label="超时（秒）">
              {{ scpDetailBinding.timeout_seconds ?? '-' }}
            </a-descriptions-item>
            <a-descriptions-item label="Endpoint" :span="2">
              <span class="mono endpoint">{{ scpDetailBinding.server_url || '-' }}</span>
            </a-descriptions-item>
          </a-descriptions>
        </div>

        <div class="scp-detail-section">
          <div class="scp-detail-title">中文描述</div>
          <div class="scp-detail-text">{{ scpDetailBinding.description || '暂无详细说明，请联系管理员补充' }}</div>
        </div>

        <div class="scp-detail-section">
          <div class="scp-detail-title">简介</div>
          <div v-if="scpDetailBinding.summary" class="scp-detail-summary">{{ scpDetailBinding.summary }}</div>
          <div class="scp-detail-text">{{ scpDetailBinding.introduction || '暂无详细说明，请联系管理员补充' }}</div>
        </div>

        <div class="scp-detail-section">
          <div class="scp-detail-title">特点</div>
          <ul v-if="(scpDetailBinding.features || []).length" class="feature-list">
            <li v-for="(feat, idx) in scpDetailBinding.features" :key="idx" class="feature-item">
              <span class="feature-dot"></span>
              <span>{{ feat }}</span>
            </li>
          </ul>
          <div v-else class="scp-detail-text">暂无详细说明，请联系管理员补充</div>
        </div>

        <div class="scp-detail-section">
          <div class="scp-detail-title">用途</div>
          <div v-if="(scpDetailBinding.use_cases || []).length" class="usecase-wrap">
            <a-tag v-for="(uc, idx) in scpDetailBinding.use_cases" :key="idx" class="usecase-tag">
              {{ uc }}
            </a-tag>
          </div>
          <div v-else class="scp-detail-text">暂无详细说明，请联系管理员补充</div>
        </div>

        <div v-if="scpDetailBinding.ecml_steps && scpDetailBinding.ecml_steps.length" class="scp-detail-section">
          <div class="scp-detail-title">ECML 接入</div>
          <div class="ecml-steps">
            <span class="text-secondary">在研发闭环的以下步骤自动调用：</span>
            <a-tag v-for="step in scpDetailBinding.ecml_steps" :key="step" color="orange">Step {{ step }}</a-tag>
          </div>
        </div>
      </div>
      <EmptyState v-else type="data" description="暂无详情" />
    </a-drawer>

    <!-- 本地工具详情抽屉 -->
    <a-drawer
      :open="localDetailVisible"
      :title="`本地工具 — ${localDetailTool?.name || ''}`"
      placement="right"
      width="640px"
      :footer="null"
      @update:open="(v) => (localDetailVisible = v)"
    >
      <div v-if="localDetailTool" class="local-detail">
        <div class="scp-detail-section">
          <div class="scp-detail-title">基础信息</div>
          <a-descriptions size="small" :column="2" bordered>
            <a-descriptions-item label="名称" :span="2">
              <span class="tool-name">{{ localDetailTool.name }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="风险等级">
              <a-tag v-if="localDetailTool.risk_level" :color="riskLevelColor(localDetailTool.risk_level)">{{ localDetailTool.risk_level }}</a-tag>
              <span v-else class="text-muted">—</span>
            </a-descriptions-item>
            <a-descriptions-item label="可用性">
              <a-tag v-if="localDetailTool.availability" :color="availabilityColor(localDetailTool.availability)">{{ availabilityLabel(localDetailTool.availability) }}</a-tag>
              <span v-else class="text-muted">—</span>
            </a-descriptions-item>
            <a-descriptions-item label="描述" :span="2">{{ localDetailTool.description || '—' }}</a-descriptions-item>
          </a-descriptions>
        </div>

        <div v-if="paramList.length" class="scp-detail-section">
          <div class="scp-detail-title">参数</div>
          <a-table
            :columns="paramColumns"
            :data-source="paramList"
            :pagination="false"
            size="small"
            row-key="name"
            :scroll="{ x: 480 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <span class="param-name">{{ record.name }}</span>
              </template>
              <template v-if="column.key === 'required'">
                <span v-if="record.required" class="param-required">必填</span>
                <span v-else class="text-muted">—</span>
              </template>
            </template>
          </a-table>
        </div>

        <div class="scp-detail-section">
          <div class="scp-detail-title">自检</div>
          <div class="test-action-row">
            <a-tooltip :title="!isAdmin ? '仅管理员可执行自检' : ''">
              <span class="tt-btn-wrap">
                <a-button
                  type="primary"
                  :loading="testStatus[localDetailTool.name]?.state === 'testing'"
                  :disabled="!isAdmin"
                  @click="onLocalTest(localDetailTool)"
                >
                  <template #icon><PlayCircleOutlined /></template>
                  {{ isAdmin ? '执行自检' : '执行自检（需 admin）' }}
                </a-button>
              </span>
            </a-tooltip>
          </div>
          <div v-if="currentLocalTestResult && currentLocalTestResult.state !== 'testing'" class="test-summary" :class="currentLocalTestResult.state">
            <span class="test-verdict">{{ currentLocalTestResult.state === 'passed' ? '自检通过' : '自检未通过' }}</span>
            <span v-if="currentLocalTestResult.latencyMs != null" class="test-meta">{{ currentLocalTestResult.latencyMs }}ms</span>
            <span v-if="currentLocalTestResult.message" class="test-meta">{{ currentLocalTestResult.message }}</span>
          </div>
        </div>
      </div>
      <EmptyState v-else type="data" description="暂无详情" />
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  ReloadOutlined,
  BulbOutlined,
  EyeOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons-vue'
import { useSystemStore } from '@/stores/system'
import { testTool } from '@/api/system'
import { getSCPBindings, updateSCPBinding, getSkills, testSkill } from '@/api/controlPlane'
import {
  CAPABILITY_LABELS,
  capabilityLabel,
  sourceLabel,
  riskLevelColor,
  availabilityColor,
  availabilityLabel,
  testStateColor,
  testStateLabel,
} from '@/constants/toolMeta'
import { useAuth } from '@/composables/useAuth'
import { MESSAGES } from '@/constants/glossary'

const systemStore = useSystemStore()
const { isAdmin } = useAuth()

// --- 5 个能力级绑定的白名单（区别于 7 个 server 级绑定） ---
const CAPABILITY_BINDING_NAMES = new Set(Object.keys(CAPABILITY_LABELS))

// 状态
const scpBindings = ref([])
const scpLoading = ref(false)
const scpError = ref('')
const scpUpdating = ref('')
const toolsLoading = ref(false)
const toolsError = ref('')
const loading = computed(() => scpLoading.value || toolsLoading.value || skillLoading.value)

// SKILL 状态
const skills = ref([])
const skillLoading = ref(false)
const skillTestingId = ref('')
const skillTestStatus = ref({})

// 自检状态
const testingId = ref('')
const testStatus = ref({}) // { [name]: { state, message, latencyMs } }

// 详情抽屉当前选中的 key（避免直接持有对象引用，刷新后从当前数组重新查找）
const scpDetailVisible = ref(false)
const scpDetailName = ref('')
const scpDetailBinding = computed(() =>
  scpBindings.value.find((b) => b.internal_name === scpDetailName.value) || null
)
const localDetailVisible = ref(false)
const localDetailToolName = ref('')
const localDetailTool = computed(() =>
  localTools.value.find((t) => t.name === localDetailToolName.value) || null
)

// --- 衍生数据 ---
// 第 1 层：server 级 SCP 绑定（7 个）
const scpServerBindings = computed(() =>
  scpBindings.value.filter((b) => !CAPABILITY_BINDING_NAMES.has(b.internal_name))
)

// 第 2 层：能力级绑定（5 个）
const capabilityBindings = computed(() =>
  scpBindings.value.filter((b) => CAPABILITY_BINDING_NAMES.has(b.internal_name))
)

// 第 3 层：本地工具（source === 'local'）
const localTools = computed(() => {
  const all = systemStore.tools || []
  return all.filter((t) => t.source === 'local')
})

// 本地工具详情抽屉的参数列表
const paramList = computed(() => {
  if (!localDetailTool.value) return []
  const p = localDetailTool.value.parameters
  if (!p) return []
  if (Array.isArray(p)) {
    return p.map((x) => ({
      name: x.name,
      type: x.type || '—',
      required: !!x.required,
      description: x.description || '—',
    }))
  }
  if (p.properties) {
    const required = p.required || []
    return Object.entries(p.properties).map(([name, schema]) => ({
      name,
      type: schema.type || '—',
      required: required.includes(name),
      description: schema.description || '—',
    }))
  }
  return []
})

const currentLocalTestResult = computed(() => {
  if (!localDetailTool.value) return null
  return testStatus.value[localDetailTool.value.name] || null
})

// --- 表格列 ---
const capabilityColumns = [
  { title: '能力名', key: 'name', width: 180 },
  { title: '数据源', key: 'source', width: 140 },
  { title: 'ECML 接入', key: 'ecml_steps', width: 160 },
  { title: '风险', key: 'risk_level', width: 80, align: 'center' },
  { title: '启用', key: 'enabled', width: 80, align: 'center' },
  { title: '操作', key: 'actions', width: 100 },
]

const localToolColumns = [
  { title: '工具名', key: 'name', width: 240, fixed: 'left' },
  { title: '风险', key: 'risk_level', width: 70, align: 'center' },
  { title: '可用性', key: 'availability', width: 90 },
  { title: '描述', key: 'description', ellipsis: true },
  { title: '自检', key: 'test', width: 100, align: 'center' },
  { title: '操作', key: 'actions', width: 140, fixed: 'right' },
]

const paramColumns = [
  { title: '参数名', key: 'name', width: 180, ellipsis: true },
  { title: '类型', dataIndex: 'type', key: 'type', width: 100 },
  { title: '必填', key: 'required', width: 70, align: 'center' },
  { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
]

// --- 标签辅助（其他通用映射已抽取到 @/constants/toolMeta） ---
function sourceTooltip(binding) {
  if (!binding.server_id) return '使用 LLM 内部能力，无远端 SCP 服务器'
  const b = scpServerBindings.value.find((x) => x.server_id === binding.server_id)
  return b ? `来自「${b.summary || b.internal_name}」` : `Server ID: ${binding.server_id}`
}

// --- API 调用 ---
async function fetchSCPBindings() {
  scpLoading.value = true
  scpError.value = ''
  try {
    const res = await getSCPBindings()
    scpBindings.value = res.bindings || []
    return true
  } catch (e) {
    scpBindings.value = []
    scpError.value = e?.message || '加载 SCP 绑定失败'
    return false
  } finally {
    scpLoading.value = false
  }
}

async function fetchLocalTools() {
  toolsLoading.value = true
  toolsError.value = ''
  try {
    await systemStore.fetchTools()
    return true
  } catch (e) {
    toolsError.value = e?.message || '加载本地工具失败'
    return false
  } finally {
    toolsLoading.value = false
  }
}

async function loadAll() {
  await Promise.all([fetchSCPBindings(), fetchLocalTools(), fetchSkills()])
}

async function refreshAll() {
  const [scpOk, toolsOk, skillOk] = await Promise.all([fetchSCPBindings(), fetchLocalTools(), fetchSkills()])
  if (scpOk && toolsOk && skillOk) {
    message.success('已刷新')
  } else {
    message.warning('部分数据刷新失败，请查看错误提示')
  }
}

async function fetchSkills() {
  skillLoading.value = true
  try {
    const res = await getSkills()
    skills.value = res.skills || []
    return true
  } catch (e) {
    skills.value = []
    return false
  } finally {
    skillLoading.value = false
  }
}

function openSkillDetail(skill) {
  // 复用 SCP 详情抽屉的样式，简化为弹窗展示 pipeline
  Modal.info({
    title: skill.name,
    width: 600,
    content: h('div', [
      h('p', { style: 'color:var(--text-secondary);margin-bottom:8px' }, skill.description),
      h('p', { style: 'font-size:12px;color:var(--text-muted);margin-bottom:12px' }, skill.introduction),
      h('div', { style: 'font-weight:600;margin-bottom:8px' }, 'Pipeline 步骤：'),
      ...skill.pipeline.map((step, i) =>
        h('div', {
          style: 'padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:13px',
        }, [
          h('span', { style: 'color:var(--primary);margin-right:8px' }, `${i + 1}.`),
          h('span', { style: 'font-weight:500' }, step.tool_name),
          h('span', { style: 'color:var(--text-muted);margin-left:8px' }, `(server ${step.server_id})`),
          h('div', { style: 'color:var(--text-secondary);font-size:12px;margin-left:24px' }, step.description || ''),
        ])
      ),
    ]),
  })
}

async function onSkillTest(skill) {
  if (!isAdmin.value) return
  skillTestingId.value = skill.skill_id
  try {
    const res = await testSkill(skill.skill_id)
    const ok = res?.status === 'success'
    skillTestStatus.value = {
      ...skillTestStatus.value,
      [skill.skill_id]: {
        state: ok ? 'passed' : 'failed',
        message: ok ? '全部步骤通过' : (res?.error || '未知错误'),
        steps: res?.steps || [],
      },
    }
    if (ok) message.success(`${skill.name} 自检通过`)
    else message.warning(`${skill.name} 自检未通过：${res?.error || '未知错误'}`)
  } catch (e) {
    skillTestStatus.value = {
      ...skillTestStatus.value,
      [skill.skill_id]: { state: 'failed', message: e?.message || '请求失败' },
    }
    message.error(`${skill.name} 自检失败：${e.message}`)
  } finally {
    skillTestingId.value = ''
  }
}

async function toggleSCPEnabled(record, enabled) {
  if (!isAdmin.value) {
    message.warning('仅管理员可操作')
    return
  }
  scpUpdating.value = record.internal_name
  try {
    await updateSCPBinding(record.internal_name, { enabled })
    message.success(`${capabilityLabel(record.internal_name)} 已${enabled ? '启用' : '禁用'}`)
    await fetchSCPBindings()
    // scpDetailBinding 为 computed，刷新后会自动从 scpBindings 重新查找
  } catch {
    // 全局拦截器已提示错误
  } finally {
    scpUpdating.value = ''
  }
}

async function onTest(binding) {
  if (!isAdmin.value) return
  testingId.value = binding.internal_name
  try {
    const res = await testTool(binding.internal_name)
    const ok = res?.available === true
    testStatus.value = {
      ...testStatus.value,
      [binding.internal_name]: {
        state: ok ? 'passed' : 'failed',
        message: res?.message || (ok ? '调用成功' : '未知错误'),
        latencyMs: res?.latency_ms,
      },
    }
    if (ok) message.success(`${binding.summary || binding.internal_name} 自检通过`)
    else message.warning(`${binding.summary || binding.internal_name} 自检未通过：${res?.message || '未知错误'}`)
  } catch (e) {
    testStatus.value = {
      ...testStatus.value,
      [binding.internal_name]: { state: 'failed', message: e?.message || '请求失败' },
    }
    message.error(`${binding.internal_name} 自检失败：${e.message}`)
  } finally {
    testingId.value = ''
  }
}

async function onLocalTest(tool) {
  if (!isAdmin.value) return
  testStatus.value = {
    ...testStatus.value,
    [tool.name]: { state: 'testing' },
  }
  try {
    const res = await testTool(tool.name)
    const ok = res?.available === true
    testStatus.value = {
      ...testStatus.value,
      [tool.name]: {
        state: ok ? 'passed' : 'failed',
        message: res?.message || (ok ? '调用成功' : '未知错误'),
        latencyMs: res?.latency_ms,
      },
    }
    if (ok) message.success(`${tool.name} 自检通过`)
    else message.warning(`${tool.name} 自检未通过：${res?.message || '未知错误'}`)
  } catch (e) {
    testStatus.value = {
      ...testStatus.value,
      [tool.name]: { state: 'failed', message: e?.message || '请求失败' },
    }
    message.error(`${tool.name} 自检失败: ${e.message}`)
  }
}

function openSCPDetail(binding) {
  scpDetailName.value = binding.internal_name
  scpDetailVisible.value = true
}

function openLocalDetail(tool) {
  localDetailToolName.value = tool.name
  localDetailVisible.value = true
}

function onSCPCardClick(binding, event) {
  // 点击卡片内部的可交互元素（按钮、链接、开关）时不触发详情
  if (event.target.closest('button, a, .ant-switch')) return
  openSCPDetail(binding)
}

// --- 生命周期 ---
onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.tools-hub {
  width: 100%;
  padding: 0 8px;
}

/* 页面头部 */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 引导条 */
.intro-collapse {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
}

.intro-collapse :deep(.ant-collapse-header) {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  padding: 10px 16px;
}

.intro-collapse :deep(.ant-collapse-content-box) {
  padding: 0 16px 12px;
}

.intro-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.intro-list {
  margin: 8px 0;
  padding-left: 20px;
}

.intro-list li {
  margin-bottom: 4px;
}

.intro-list b {
  color: var(--text-primary);
  font-weight: 600;
}

.intro-impact {
  margin: 12px 0 0;
  padding: 8px 12px;
  background: var(--light-bg-hover);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}

.intro-readonly {
  color: var(--text-muted);
  margin-left: 8px;
}

/* 层 */
.layer {
  margin-bottom: 24px;
}

.layer-header {
  margin-bottom: 12px;
}

.layer-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.layer-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.layer-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.layer-count {
  margin-left: 4px;
  font-size: 11px;
}

.layer-desc {
  font-size: 12px;
  color: var(--text-muted);
  padding-left: 32px;
}

/* 卡片网格 */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.scp-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color 0.2s, box-shadow 0.2s;
  cursor: pointer;
  outline: none;
}

.scp-card:hover {
  border-color: var(--primary);
}

.scp-card:focus-visible {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-light, rgba(24, 144, 255, 0.2));
}

.scp-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.scp-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.scp-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.scp-card-tools {
  font-size: 12px;
  color: var(--text-secondary);
}

.scp-card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  min-height: 36px;
}

.scp-card-actions {
  display: flex;
  gap: 4px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}

.scp-card-actions :deep(.ant-btn) {
  padding: 0 8px;
  height: 24px;
  font-size: 12px;
}

/* 表格 */
:deep(.ant-table) {
  font-size: 13px;
}

:deep(.ant-table-thead > tr > th) {
  background: var(--light-bg-hover);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
}

:deep(.ant-table-tbody > tr > td) {
  padding: 10px 16px;
}

.cap-name {
  font-weight: 600;
  color: var(--text-primary);
}

.tool-name {
  font-family: var(--font-family-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 详情抽屉 */
.scp-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.scp-detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.scp-detail-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  padding-left: 8px;
  border-left: 3px solid var(--primary);
}

.scp-detail-text {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.scp-detail-summary {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  font-weight: 500;
  padding: 8px 12px;
  background: var(--light-bg-hover);
  border-radius: var(--radius-sm);
}

.mono {
  font-family: var(--font-family-mono);
  font-size: 12px;
  word-break: break-all;
}

.endpoint {
  color: var(--primary);
}

.feature-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.feature-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  margin-top: 7px;
  border-radius: 50%;
  background: var(--primary);
}

.usecase-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.usecase-tag {
  margin: 0;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--light-bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.ecml-steps {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}

.local-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.param-name {
  font-family: var(--font-family-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
}

.param-required {
  font-size: 11px;
  color: var(--error);
}

.test-action-row {
  display: flex;
  gap: 8px;
}

.test-summary {
  font-size: 12px;
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: var(--light-bg-hover);
  border-radius: var(--radius-sm);
  margin-top: 8px;
}

.test-summary.passed .test-verdict {
  color: var(--success);
  font-weight: 600;
}

.test-summary.failed .test-verdict {
  color: var(--error);
  font-weight: 600;
}

.test-summary .test-meta {
  color: var(--text-muted);
  word-break: break-all;
}

/* 通用 */
.text-muted {
  color: var(--text-muted);
  font-size: 13px;
}

.text-secondary {
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
