<template>
  <div class="settings-page">
    <SectionHeader
      title="系统设置"
      subtitle="配置 API 密钥、模型参数与 AI4S 引擎选项"
    />

    <!-- 左侧主区 + 右侧侧栏 -->
    <a-row :gutter="24" class="settings-row">
      <a-col :xs="24" :xl="isAdmin ? 16 : 24" class="settings-main">
    <!-- 1. LLM 配置 -->
    <a-card :bordered="false" class="settings-card">
      <div class="card-head">
        <div>
          <div class="card-title">LLM 配置</div>
          <div class="card-subtitle">配置 LLM 服务连接与密钥</div>
        </div>
      </div>

      <a-form ref="apiFormRef" :model="config" :rules="apiRules" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="24" :lg="12">
            <a-form-item label="Materials Project API Key">
              <a-space>
                <a-tag :color="config.mpApiKeySet ? 'success' : 'default'">
                  {{ config.mpApiKeySet ? '已配置' : '未配置' }}
                </a-tag>
                <a-button size="small" @click="toggleKeyEdit('mp')">
                  {{ editingKeys.mp ? '取消' : (config.mpApiKeySet ? '更新' : '配置') }}
                </a-button>
              </a-space>
              <a-input-password
                v-if="editingKeys.mp"
                v-model:value="config.mpApiKey"
                placeholder="输入 MP API Key…"
                autocomplete="off"
                name="mp_api_key"
                class="key-input"
              />
              <div class="form-help">用于获取晶体结构与热力学数据。</div>
            </a-form-item>
          </a-col>
          <a-col :span="24" :lg="12">
            <a-form-item label="LLM API Key">
              <a-space>
                <a-tag :color="config.llmApiKeySet ? 'success' : 'default'">
                  {{ config.llmApiKeySet ? '已配置' : '未配置' }}
                </a-tag>
                <a-button size="small" @click="toggleKeyEdit('llm')">
                  {{ editingKeys.llm ? '取消' : (config.llmApiKeySet ? '更新' : '配置') }}
                </a-button>
              </a-space>
              <a-input-password
                v-if="editingKeys.llm"
                v-model:value="config.llmApiKey"
                placeholder="输入 LLM API Key…"
                autocomplete="off"
                name="llm_api_key"
                class="key-input"
              />
              <div class="form-help">用于 Agent 推理与自然语言生成。</div>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="24" :lg="12">
            <a-form-item label="LLM 服务地址" name="llmBaseUrl">
              <a-input
                v-model:value="config.llmBaseUrl"
                placeholder="https://api.longcat.chat/openai"
                :spellcheck="false"
                autocomplete="off"
                name="llm_base_url"
              />
            </a-form-item>
          </a-col>
          <a-col :span="24" :lg="12">
            <a-form-item label="LLM 模型">
              <a-input
                v-model:value="config.llmModel"
                placeholder="LongCat-2.0"
                :spellcheck="false"
                autocomplete="off"
                name="llm_model"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item>
          <a-button id="settings-save-api" type="primary" :loading="saving.api" @click="saveApi">
            保存 LLM 配置
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 2. AI4S 引擎：AI4S + SCP -->
    <a-card :bordered="false" class="settings-card">
      <div class="card-head">
        <div>
          <div class="card-title">AI4S 引擎</div>
          <div class="card-subtitle">AI4S 辅助推理与 SCP 外部工具平台</div>
        </div>
        <a-space>
          <a-tag :color="internlmStatus.connected ? 'success' : 'error'">
            AI4S {{ internlmStatus.connected ? '已连接' : '未连接' }}
          </a-tag>
          <a-tag :color="scpStatus.enabled ? 'success' : 'default'">
            SCP {{ scpStatus.enabled ? '已启用' : '未启用' }}
          </a-tag>
        </a-space>
      </div>

      <a-form ref="engineFormRef" :model="config" :rules="engineRules" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="24" :lg="12">
            <a-form-item label="AI4S 服务地址" name="internlmBaseUrl">
              <a-input
                v-model:value="config.internlmBaseUrl"
                placeholder="https://chat.intern-ai.org.cn/api/v1"
                :spellcheck="false"
                autocomplete="off"
                name="internlm_base_url"
              />
              <div class="form-help">例如 https://chat.intern-ai.org.cn/api/v1</div>
            </a-form-item>
          </a-col>
          <a-col :span="24" :lg="12">
            <a-form-item label="AI4S 模型名">
              <a-input
                v-model:value="config.internlmModelName"
                placeholder="intern-s2-preview-397b"
                :spellcheck="false"
                autocomplete="off"
                name="internlm_model"
              />
              <div class="form-help">默认推荐使用 intern-s2-preview-397b。</div>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="24" :lg="12">
            <a-form-item label="AI4S API Key">
              <a-space>
                <a-tag :color="config.internlmApiKeySet ? 'success' : 'default'">
                  {{ config.internlmApiKeySet ? '已配置' : '未配置' }}
                </a-tag>
                <a-button size="small" @click="toggleKeyEdit('internlm')">
                  {{ editingKeys.internlm ? '取消' : (config.internlmApiKeySet ? '更新' : '配置') }}
                </a-button>
              </a-space>
              <a-input-password
                v-if="editingKeys.internlm"
                v-model:value="config.internlmApiKey"
                placeholder="可选，输入 API 密钥…"
                autocomplete="off"
                name="internlm_api_key"
                class="key-input"
              />
            </a-form-item>
          </a-col>
          <a-col :span="24" :lg="12">
            <a-form-item label="请求超时（秒）">
              <a-input-number v-model:value="config.internlmTimeout" :min="1" :max="300" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item>
          <div class="switch-row">
            <a-switch v-model:checked="config.scpEnabled" id="settings-scp-switch" />
            <label for="settings-scp-switch" class="switch-label">启用 SCP 外部工具平台</label>
          </div>
          <div class="form-help">开启后可调用外部工具（毒理/文献/分子描述符等）。</div>
        </a-form-item>

        <a-row v-if="config.scpEnabled" :gutter="16">
          <a-col :span="24" :lg="12">
            <a-form-item label="SCP 外部工具平台地址" name="scpBaseUrl">
              <a-input
                v-model:value="config.scpBaseUrl"
                placeholder="SCP 外部工具平台地址（留空使用默认）…"
                :spellcheck="false"
                autocomplete="off"
                name="scp_base_url"
              />
            </a-form-item>
          </a-col>
          <a-col :span="24" :lg="12">
            <a-form-item label="SCP API Key">
              <a-space>
                <a-tag :color="config.scpApiKeySet ? 'success' : 'default'">
                  {{ config.scpApiKeySet ? '已配置' : '未配置' }}
                </a-tag>
                <a-button size="small" @click="toggleKeyEdit('scp')">
                  {{ editingKeys.scp ? '取消' : (config.scpApiKeySet ? '更新' : '配置') }}
                </a-button>
              </a-space>
              <a-input-password
                v-if="editingKeys.scp"
                v-model:value="config.scpApiKey"
                placeholder="输入 SCP API Key…"
                autocomplete="off"
                name="scp_api_key"
                class="key-input"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item>
          <a-button id="settings-save-engine" type="primary" :loading="saving.engine" @click="saveEngine">
            保存 AI4S 引擎配置
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 3. 传统专家模型 -->
    <a-card :bordered="false" class="settings-card">
      <div class="card-head">
        <div>
          <div class="card-title">传统专家模型</div>
          <div class="card-subtitle">预测与模拟默认使用的模型</div>
        </div>
      </div>

      <a-form ref="modelsFormRef" :model="config" :rules="modelsRules" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="24" :lg="12">
            <a-form-item label="晶体预测模型">
              <a-radio-group v-model:value="config.crystalModel" button-style="solid">
                <a-tooltip v-for="m in crystalModels" :key="m.id" :title="m.note">
                  <a-radio-button :value="m.id" :disabled="m.grayed_out">
                    {{ m.name }}
                    <span v-if="m.grayed_out" class="model-tag-grayed">扩展</span>
                  </a-radio-button>
                </a-tooltip>
              </a-radio-group>
            </a-form-item>
          </a-col>
          <a-col :span="24" :lg="12">
            <a-form-item label="聚合物预测模型">
              <a-radio-group v-model:value="config.polymerModel" button-style="solid">
                <a-tooltip v-for="m in polymerModels" :key="m.id" :title="m.note">
                  <a-radio-button :value="m.id" :disabled="m.grayed_out">
                    {{ m.name }}
                    <span v-if="m.grayed_out" class="model-tag-grayed">扩展</span>
                  </a-radio-button>
                </a-tooltip>
              </a-radio-group>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="24" :lg="12">
            <a-form-item label="DFT 方法">
              <a-select v-model:value="config.dftMethod" style="width: 100%" :disabled="dftDisabled">
                <a-select-option v-for="f in dftFunctionals" :key="f.id" :value="f.id" :disabled="!f.available">
                  {{ f.name }}
                  <span v-if="!f.available" class="model-tag-grayed">扩展</span>
                </a-select-option>
              </a-select>
              <div v-if="dftDisabled" class="dft-note">{{ dftNote }}</div>
            </a-form-item>
          </a-col>
          <a-col :span="24" :lg="12">
            <a-form-item label="基组">
              <a-select v-model:value="config.basisSet" style="width: 100%" :disabled="dftDisabled">
                <a-select-option v-for="b in dftBasisSets" :key="b.id" :value="b.id" :disabled="!b.available">
                  {{ b.name }}
                  <span v-if="!b.available" class="model-tag-grayed">扩展</span>
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item>
          <a-button id="settings-save-models" type="primary" :loading="saving.models" @click="saveModels">
            保存模型配置
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 4. 我的画像 -->
    <a-card :bordered="false" class="settings-card">
      <div class="card-head">
        <div>
          <div class="card-title">我的画像</div>
          <div class="card-subtitle">标注专业方向，仅影响默认展示与排序，不影响权限与数据范围</div>
        </div>
      </div>

      <a-form layout="vertical">
        <a-form-item label="专业画像（可多选）">
          <a-select
            v-model:value="disciplines"
            mode="multiple"
            :options="DISCIPLINE_OPTIONS"
            placeholder="选择专业方向…"
            style="width: 100%"
            allow-clear
          />
          <div class="form-help">可同时选择多个专业方向；为空时按通用视角展示全部模块。</div>
        </a-form-item>

        <a-form-item label="主专业（仅可选已选画像）">
          <a-select
            v-model:value="primaryDiscipline"
            :options="primaryOptions"
            placeholder="选择主专业…"
            style="width: 100%"
            allow-clear
          />
          <div class="form-help">主专业决定项目内模块的默认聚焦顺序；为空时回退到通用落点（概览）。</div>
        </a-form-item>

        <a-form-item>
          <a-button id="settings-save-disciplines" type="primary" :loading="saving.disciplines" @click="saveMyDisciplines">
            保存专业画像
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>
      </a-col>
      <a-col v-if="isAdmin" :xs="24" :xl="8" class="settings-aside">
    <!-- 运行模式（仅管理员可见） -->
    <a-card :bordered="false" class="settings-card">
      <div class="card-head">
        <div>
          <div class="card-title">运行模式</div>
          <div class="card-subtitle">控制系统运行环境，影响数据隔离与功能范围</div>
        </div>
      </div>

      <a-form ref="runModeFormRef" :model="config" :rules="runModeRules" layout="vertical">
        <a-form-item label="运行模式">
          <a-select
            v-model:value="config.runMode"
            placeholder="选择运行模式…"
            style="width: 100%"
            :options="runModeOptions"
          />
          <div class="form-help">
            <strong>Demo</strong>：演示模式，使用模拟数据，适合体验功能；<br>
            <strong>Production</strong>：生产模式，连接真实外部服务，适合实际研发。
          </div>
        </a-form-item>

        <a-form-item>
          <a-button id="settings-save-runmode" type="primary" :loading="saving.runMode" @click="saveRunMode">
            保存运行模式
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>
      </a-col>
    </a-row>

    <!-- 关于 -->
    <div class="about-footer">
      <span class="about-name">MaterialsPEML Lab</span>
      <span class="about-sep">·</span>
      <span class="about-version">v1.0.0</span>
      <span class="about-sep">·</span>
      <span class="about-tagline">面向新材料、化工研发的 AI 驱动实验闭环平台</span>
    </div>

    <OnboardingTooltip
      :open="tourOpen"
      :steps="tourSteps"
      storage-key="settings_onboarding_seen"
      @close="onTourClose"
      @finish="onTourFinish"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import SectionHeader from '@/components/SectionHeader.vue'
import OnboardingTooltip from '@/components/OnboardingTooltip.vue'
import { updateConfig, getModelCatalog } from '@/api/system'
import { updateMyDisciplines, getCurrentUser } from '@/api/auth'
import { DISCIPLINE_OPTIONS } from '@/constants/roles'
import { useSystemStore } from '@/stores/system'
import { useAuth } from '@/composables/useAuth'
import { useMdmDict } from '@/utils/mdmDict'
import { required, url } from '@/utils/formRules'
import { MESSAGES } from '@/constants/glossary'

const systemStore = useSystemStore()

const saving = reactive({ api: false, models: false, engine: false, runMode: false, disciplines: false })

// ── 我的画像 ──
const disciplines = ref([])
const primaryDiscipline = ref('')
const primaryOptions = computed(() =>
  (disciplines.value || []).map(v => ({ value: v, label: DISCIPLINE_OPTIONS.find(o => o.value === v)?.label || v }))
)

async function loadMyDisciplines() {
  try {
    const me = await getCurrentUser()
    disciplines.value = me?.data?.disciplines || me?.disciplines || []
    primaryDiscipline.value = me?.data?.primary_discipline || me?.primary_discipline || ''
  } catch {
    // 后端不可达时保持空画像（通用视角），不阻塞设置页
  }
}

async function saveMyDisciplines() {
  const ds = disciplines.value || []
  const primary = primaryDiscipline.value || ''
  if (primary && !ds.includes(primary)) {
    message.warning('主专业必须是已选的专业画像之一')
    return
  }
  saving.disciplines = true
  try {
    await updateMyDisciplines({ disciplines: ds, primary_discipline: primary })
    await loadMyDisciplines()
    message.success('专业画像已保存')
  } catch (e) {
    message.error('专业画像' + MESSAGES.saveFailed + '，请检查网络或联系管理员')
  } finally {
    saving.disciplines = false
  }
}

// P1-FORM-001：表单校验 ref 与规则
const apiFormRef = ref()
const engineFormRef = ref()
const modelsFormRef = ref()
const runModeFormRef = ref()

// API Key 字段不强制必填（可能未配置）；URL 字段做格式校验
const apiRules = {
  llmBaseUrl: url('请输入有效的 LLM 服务地址'),
}
const engineRules = {
  internlmBaseUrl: url('请输入有效的 AI4S 服务地址'),
  scpBaseUrl: url('请输入有效的 SCP 平台地址'),
}
const modelsRules = {}
const runModeRules = {}

// 模型目录（从后端 /settings/model_catalog 动态拉取）
const modelCatalog = reactive({
  expert_models: [],
  dft_methods: { enabled: false, grayed_out: true, note: '', functionals: [], basis_sets: [] },
})

const crystalModels = computed(() => modelCatalog.expert_models.filter(m => m.category === 'crystal'))
const polymerModels = computed(() => modelCatalog.expert_models.filter(m => m.category === 'polymer'))
const dftFunctionals = computed(() => modelCatalog.dft_methods.functionals || [])
const dftBasisSets = computed(() => modelCatalog.dft_methods.basis_sets || [])
const dftDisabled = computed(() => modelCatalog.dft_methods.grayed_out !== false)
const dftNote = computed(() => modelCatalog.dft_methods.note || '晶体 DFT 为可扩展灰色功能')

const config = reactive({
  mpApiKey: '',
  mpApiKeySet: false,
  llmApiKey: '',
  llmApiKeySet: false,
  llmModel: 'LongCat-2.0',
  llmBaseUrl: 'https://api.longcat.chat/openai',
  llmMaxTokens: 128000,
  llmContextWindow: 1000000,
  askcosUrl: 'http://localhost:5000',
  crystalModel: 'cgcnn',
  polymerModel: 'polymernn',
  dftMethod: 'b3lyp',
  basisSet: '6-31g*',
  engineMode: 'legacy',
  internlmBaseUrl: 'https://chat.intern-ai.org.cn/api/v1',
  internlmModelName: 'intern-s2-preview-397b',
  internlmApiKey: '',
  internlmApiKeySet: false,
  internlmTimeout: 60,
  scpEnabled: false,
  scpApiKey: '',
  scpApiKeySet: false,
  scpBaseUrl: '',
  runMode: 'demo',
})

// 管理员权限检测：统一走 useAuth composable
const { isAdmin } = useAuth()

const RUN_MODE_OPTIONS_FALLBACK = [
  { value: 'demo', label: 'Demo（演示模式）' },
  { value: 'production', label: 'Production（生产模式）' },
]
const runModeOptions = ref([...RUN_MODE_OPTIONS_FALLBACK])

// Tracks which API key fields are in "edit" mode (input visible).
const editingKeys = reactive({ mp: false, llm: false, internlm: false, scp: false })

function toggleKeyEdit(key) {
  editingKeys[key] = !editingKeys[key]
  if (!editingKeys[key]) {
    // Cancelled: clear stale input.
    if (key === 'mp') config.mpApiKey = ''
    if (key === 'llm') config.llmApiKey = ''
    if (key === 'internlm') config.internlmApiKey = ''
    if (key === 'scp') config.scpApiKey = ''
  } else {
    // Entering edit: start empty for a new value.
    if (key === 'mp') config.mpApiKey = ''
    if (key === 'llm') config.llmApiKey = ''
    if (key === 'internlm') config.internlmApiKey = ''
    if (key === 'scp') config.scpApiKey = ''
  }
}

const internlmStatus = reactive({
  enabled: false,
  model_name: '',
  base_url: '',
  connected: false,
})

const scpStatus = reactive({
  enabled: false,
  api_key_set: false,
  tool_count: 0,
  recent_error: '',
})

// Load config from backend on mount (in addition to localStorage)
async function fetchBackendConfig() {
  try {
    const data = await systemStore.fetchConfig()
    if (data.engine_mode) config.engineMode = data.engine_mode
    if (data.run_mode) config.runMode = data.run_mode
    if (data.internlm) {
      if (data.internlm.base_url !== undefined) config.internlmBaseUrl = data.internlm.base_url
      // Backend field is `model` (not `model_name`); fall back to model_name
      // only for legacy compatibility.
      const modelName = data.internlm.model ?? data.internlm.model_name
      if (modelName !== undefined) config.internlmModelName = modelName
      // Backend returns api_key_set (bool), never the raw key. Surface it as
      // a status badge; the actual key input is only revealed on user action.
      if (data.internlm.api_key_set !== undefined) config.internlmApiKeySet = !!data.internlm.api_key_set
      if (data.internlm.timeout !== undefined) config.internlmTimeout = data.internlm.timeout
      internlmStatus.enabled = data.internlm.enabled !== false
      internlmStatus.model_name = modelName || ''
      internlmStatus.base_url = data.internlm.base_url || ''
      internlmStatus.connected = data.internlm.connected || false
    }
    // Also handle legacy logos key for backward compat
    if (data.logos && !data.internlm) {
      if (data.logos.base_url !== undefined) config.internlmBaseUrl = data.logos.base_url
      if (data.logos.model_name !== undefined) config.internlmModelName = data.logos.model_name
      if (data.logos.api_key_set !== undefined) config.internlmApiKeySet = !!data.logos.api_key_set
      if (data.logos.timeout !== undefined) config.internlmTimeout = data.logos.timeout
    }
    if (data.scp) {
      scpStatus.enabled = data.scp.enabled !== false
      scpStatus.api_key_set = !!data.scp.api_key_set
      scpStatus.tool_count = data.scp.tool_count ?? 0
      scpStatus.recent_error = data.scp.recent_error || ''
      config.scpEnabled = data.scp.enabled !== false
      config.scpApiKeySet = !!data.scp.api_key_set
      if (data.scp.base_url !== undefined) config.scpBaseUrl = data.scp.base_url
    }
    if (data.llm) {
      if (data.llm.model) config.llmModel = data.llm.model
      if (data.llm.base_url) config.llmBaseUrl = data.llm.base_url
      if (data.llm.max_tokens) config.llmMaxTokens = data.llm.max_tokens
      if (data.llm.api_key_set !== undefined) config.llmApiKeySet = !!data.llm.api_key_set
    }
    if (data.askcos?.base_url) config.askcosUrl = data.askcos.base_url
    if (data.materials_project?.api_key_set !== undefined) config.mpApiKeySet = !!data.materials_project.api_key_set
    // Legacy field for backward compat
    if (data.mp_api_key_set !== undefined) config.mpApiKeySet = !!data.mp_api_key_set
    if (data.llm_api_key_set !== undefined) config.llmApiKeySet = !!data.llm_api_key_set
  } catch (err) {
    // 后端不可达时给出可见提示，避免静默回退到过时的 localStorage 缓存
    console.warn('[Settings] 从后端加载配置失败，使用本地默认值：', err)
  }
}

onMounted(async () => {
  // 先用 localStorage 恢复用户上次保存的表单状态（避免渲染闪烁）
  const saved = localStorage.getItem('bma_config')
  if (saved) {
    try {
      Object.assign(config, JSON.parse(saved))
    } catch {
      /* ignore */
    }
  }
  // 再用后端实时配置覆盖（后端为单一事实来源，避免 localStorage 旧值粘滞）
  await fetchBackendConfig()
  // 拉取模型目录（动态渲染模型选择器 + 灰色不可选项）
  try {
    const res = await getModelCatalog()
    if (res?.data) {
      Object.assign(modelCatalog, res.data)
    } else if (res) {
      Object.assign(modelCatalog, res)
    }
  } catch {
    // 后端不可达时保留空目录，模板 v-for 渲染为空（用户无法选择）
  }

  // 从 MDM 加载运行模式下拉选项
  const { statusOptions } = useMdmDict()
  try {
    const options = await statusOptions('run')
    if (options && options.length > 0) {
      runModeOptions.value = options
    } else {
      throw new Error('empty')
    }
  } catch {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }

  maybeStartTour()
  loadMyDisciplines()
})

async function saveApi() {
  // P1-FORM-001：提交前触发前端表单校验
  try {
    await apiFormRef.value?.validate()
  } catch {
    return
  }
  saving.api = true
  localStorage.setItem('bma_config', JSON.stringify(config))
  try {
    const updates = {
      llm_model: config.llmModel,
      llm_base_url: config.llmBaseUrl,
      llm_max_tokens: config.llmMaxTokens,
      askcos_url: config.askcosUrl,
    }
    if (editingKeys.mp && config.mpApiKey) updates.mp_api_key = config.mpApiKey
    if (editingKeys.llm && config.llmApiKey) updates.llm_api_key = config.llmApiKey
    await updateConfig(updates)
    await fetchBackendConfig()
    editingKeys.mp = false
    editingKeys.llm = false
    config.mpApiKey = ''
    config.llmApiKey = ''
    message.success('API 配置已保存到本地与后端')
  } catch (e) {
    message.error('API 配置' + MESSAGES.saveFailed + '，请检查网络或联系管理员')
  } finally {
    saving.api = false
  }
}

async function saveModels() {
  // P1-FORM-001：提交前触发前端表单校验
  try {
    await modelsFormRef.value?.validate()
  } catch {
    return
  }
  saving.models = true
  localStorage.setItem('bma_config', JSON.stringify(config))
  try {
    await updateConfig({
      crystal_model: config.crystalModel,
      polymer_model: config.polymerModel,
      dft_method: config.dftMethod,
      basis_set: config.basisSet,
    })
    message.success('模型配置已保存到本地与后端')
  } catch {
    message.warning('后端' + MESSAGES.saveFailed + '，配置仅保存到本地存储')
  } finally {
    saving.models = false
  }
}

async function saveEngine() {
  // P1-FORM-001：提交前触发前端表单校验
  try {
    await engineFormRef.value?.validate()
  } catch {
    return
  }
  saving.engine = true
  const payload = {
    internlm_base_url: config.internlmBaseUrl,
    internlm_model: config.internlmModelName,
    internlm_timeout: config.internlmTimeout,
    scp_enabled: config.scpEnabled,
    scp_base_url: config.scpBaseUrl,
  }
  // Only send the key when the user typed a new value in edit mode.
  if (editingKeys.internlm && config.internlmApiKey) {
    payload.internlm_api_key = config.internlmApiKey
  }
  if (editingKeys.scp && config.scpApiKey) {
    payload.scp_api_key = config.scpApiKey
  }
  try {
    await systemStore.saveConfig(payload)
    // Refresh backend status (api_key_set) and exit edit mode
    await fetchBackendConfig()
    editingKeys.internlm = false
    editingKeys.scp = false
    config.internlmApiKey = ''
    config.scpApiKey = ''
    message.success('引擎配置已保存')
  } catch (e) {
    message.error(MESSAGES.saveFailed + '，请检查网络或联系管理员')
  } finally {
    saving.engine = false
  }
}

async function saveRunMode() {
  // P1-FORM-001：提交前触发前端表单校验
  try {
    await runModeFormRef.value?.validate()
  } catch {
    return
  }
  saving.runMode = true
  try {
    await systemStore.saveConfig({ run_mode: config.runMode })
    message.success(`运行模式已切换为 ${config.runMode === 'production' ? '生产模式' : '演示模式'}，重启后生效`)
  } catch (e) {
    message.error('运行模式' + MESSAGES.saveFailed + '，请检查网络或联系管理员')
  } finally {
    saving.runMode = false
  }
}

// ── 引导 ──
const tourOpen = ref(false)
const STORAGE_KEY = 'settings_onboarding_seen'

function maybeStartTour() {
  try {
    if (!localStorage.getItem(STORAGE_KEY)) {
      tourOpen.value = true
    }
  } catch {
    /* ignore */
  }
}

function markOnboardingSeen() {
  try {
    localStorage.setItem(STORAGE_KEY, 'true')
  } catch {
    /* ignore */
  }
}

function onTourFinish() {
  tourOpen.value = false
  markOnboardingSeen()
}

function onTourClose() {
  tourOpen.value = false
  markOnboardingSeen()
}

const tourSteps = [
  {
    target: '#settings-save-api',
    title: '保存 API 配置',
    description: '填写密钥和服务地址后，点击保存即可生效。',
    placement: 'top',
  },
  {
    target: '#settings-scp-switch',
    title: '启用 SCP 外部工具',
    description: '开启后可调用文献、毒理等外部工具扩展研发能力。',
    placement: 'bottom',
  },
  {
    target: '#settings-save-engine',
    title: '保存 AI4S 引擎配置',
    description: '确认 AI4S 和 SCP 配置后保存，系统将自动检测连接状态。',
    placement: 'top',
  },
]
</script>

<style scoped>
.settings-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0 var(--space-sm);
}

.settings-card {
  background: var(--realsee-surface);
  border: 1px solid var(--realsee-outline);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
  margin-bottom: 20px;
}

.settings-card :deep(.ant-card-body) {
  padding: var(--space-md) var(--space-lg);
}

.settings-row {
  padding: var(--space-sm) 0 var(--space-md);
}

/* 左侧主区：3 个垂直卡片 */
.settings-main :last-child {
  margin-bottom: 0;
}

/* 右侧侧栏：运行模式粘性定位，滚动时保持可见 */
.settings-aside {
  position: sticky;
  top: var(--space-md);
  align-self: flex-start;
}

.settings-aside .settings-card {
  margin-bottom: 0;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.card-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  line-height: 1.3;
}

.card-subtitle {
  font-size: var(--font-size-md);
  color: var(--text-muted);
  margin-top: 2px;
}

.form-help {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin-top: var(--space-xs);
  line-height: 1.5;
}

.key-input {
  margin-top: var(--space-sm);
}

.switch-row {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
}

.switch-label {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  cursor: pointer;
}

.about-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md);
  color: var(--text-muted);
  font-size: var(--font-size-sm);
  border-top: 1px solid var(--border-light);
  margin-top: var(--space-sm);
}

.about-name {
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
}

.about-version {
  font-variant-numeric: tabular-nums;
}

.about-sep {
  color: var(--text-muted);
  opacity: 0.6;
}

.about-tagline {
  color: var(--text-muted);
}

@media (max-width: 699px) {
  .card-head {
    flex-direction: column;
    align-items: flex-start;
  }
}

/* 灰色不可选模型标记 */
.model-tag-grayed {
  display: inline-block;
  margin-left: 4px;
  padding: 0 4px;
  font-size: 10px;
  line-height: 16px;
  color: var(--text-muted, #999);
  background: var(--realsee-outline, #e8e8e8);
  border-radius: 2px;
}

/* DFT 灰色提示文本 */
.dft-note {
  margin-top: 4px;
  font-size: var(--font-size-sm, 12px);
  color: var(--text-muted, #999);
  line-height: 1.4;
}
</style>
