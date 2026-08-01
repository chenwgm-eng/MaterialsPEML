<template>
  <a-drawer
    v-model:open="innerOpen"
    title="生成合成路径"
    placement="right"
    width="420"
    :destroy-on-close="true"
  >
    <div class="cs-drawer">
      <!-- 目标材料提示 -->
      <div class="cs-section">
        <div class="cs-section-title">
          {{ structureKind === 'crystal' ? '目标晶体' : '目标分子' }}
        </div>
        <a-tag v-if="structureKind === 'crystal'" color="blue">化学式</a-tag>
        <a-tag v-else color="blue">SMILES</a-tag>
        <span class="cs-material-name">
          {{ structureKind === 'crystal' ? (candidate.formula || '—') : (smiles || '—') }}
        </span>
        <div v-if="structureKind === 'crystal' && candidate.space_group" class="cs-model-desc">
          空间群：{{ candidate.space_group }}
        </div>
      </div>

      <!-- 引擎选择（晶体不显示，强制走 AI4S大模型） -->
      <div v-if="structureKind !== 'crystal'" class="cs-section">
        <div class="cs-section-title">
          合成引擎
          <a-tooltip title="默认选中 ASKCOS；AI4S大模型走大模型推理，无需本地服务">
            <InfoCircleOutlined class="cs-info-icon" />
          </a-tooltip>
        </div>
        <a-radio-group v-model:value="selectedSynthEngine" button-style="solid" class="cs-model-group">
          <a-radio-button
            v-for="m in availableSynthEngines"
            :key="m.value"
            :value="m.value"
          >
            {{ m.label }}
          </a-radio-button>
        </a-radio-group>
        <div v-if="selectedSynthEngineMeta" class="cs-model-desc">{{ selectedSynthEngineMeta.desc }}</div>

        <!-- 引擎信息卡：鼠标移上/点击显示详情，参考首席材料科学家 AI 卡片 -->
        <div v-if="selectedEngineInfo" class="engine-info-row">
          <a-popover
            trigger="click"
            placement="bottomLeft"
            overlay-class-name="agent-popover"
          >
            <template #title>
              <span class="popover-title">{{ selectedEngineInfo.name }}</span>
            </template>
            <template #content>
              <div class="agent-detail-card">
                <div class="agent-head">
                  <div class="agent-avatar-lg">{{ selectedEngineInfo.avatar }}</div>
                  <div class="agent-meta">
                    <div class="agent-name-lg">{{ selectedEngineInfo.name }}</div>
                    <div class="agent-tags">
                      <a-tag color="blue" size="small">{{ selectedEngineInfo.provider }}</a-tag>
                      <a-tag v-if="selectedEngineInfo.tool_count" color="cyan" size="small">
                        {{ selectedEngineInfo.tool_count }} 个工具
                      </a-tag>
                    </div>
                  </div>
                </div>
                <div class="agent-section">
                  <div class="agent-section-title">引擎介绍</div>
                  <div class="agent-desc">{{ selectedEngineInfo.introduction }}</div>
                </div>
                <div v-if="selectedEngineInfo.features?.length" class="agent-section">
                  <div class="agent-section-title">核心能力</div>
                  <div class="agent-tags">
                    <a-tag v-for="f in selectedEngineInfo.features" :key="f" size="small">{{ f }}</a-tag>
                  </div>
                </div>
                <div v-if="selectedEngineInfo.use_cases?.length" class="agent-section">
                  <div class="agent-section-title">典型场景</div>
                  <div class="agent-tags">
                    <a-tag v-for="u in selectedEngineInfo.use_cases" :key="u" size="small">{{ u }}</a-tag>
                  </div>
                </div>
              </div>
            </template>
            <span class="agent-chip">
              <span class="agent-avatar">{{ selectedEngineInfo.avatar }}</span>
              <span class="agent-name">{{ selectedEngineInfo.name }}</span>
              <a-tag
                :color="selectedSynthEngine === 'scp' ? 'purple' : 'orange'"
                size="small"
                class="ai-tag"
              >
                {{ selectedSynthEngine === 'scp' ? 'SCP' : 'AI' }}
              </a-tag>
            </span>
          </a-popover>
        </div>
      </div>

      <!-- 智能体选择 -->
      <div class="cs-section">
        <div class="cs-section-title">
          {{ structureKind === 'crystal' ? '执行智能体（具备逆合成能力）' : '执行智能体' }}
          <a-tooltip :title="structureKind === 'crystal'
            ? '仅列出具备「合成证据」能力的智能体，由其调用 AI4S大模型生成固相合成路径'
            : '仅列出具备「合成证据」能力的智能体；可不选，由系统默认规划器执行'">
            <InfoCircleOutlined class="cs-info-icon" />
          </a-tooltip>
        </div>
        <a-select
          v-model:value="selectedSynthAgentId"
          :loading="synthAgentsLoading"
          :options="synthAgentOptions"
          :placeholder="structureKind === 'crystal' ? '请选择智能体' : '不指定，使用系统默认'"
          allow-clear
          class="cs-agent-select"
        />
        <div v-if="!synthAgentOptions.length && !synthAgentsLoading" class="cs-empty-hint">
          暂无具备「合成证据」能力的智能体
        </div>
      </div>

      <!-- 路线数量 -->
      <div class="cs-section">
        <div class="cs-section-title">候选路线数</div>
        <a-input-number
          v-model:value="synthNumRoutes"
          :min="1"
          :max="10"
          class="cs-num-routes"
        />
      </div>

      <!-- 执行按钮 -->
      <div class="cs-actions">
        <a-button
          type="primary"
          block
          :loading="loading"
          @click="onSubmit"
        >
          <template #icon><BranchesOutlined /></template>
          开始规划
        </a-button>
      </div>
    </div>
  </a-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { BranchesOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import client from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
  candidate: { type: Object, required: true },
  smiles: { type: String, default: '' },
  structureKind: { type: String, default: 'crystal' },
  candidateId: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['update:open', 'submit'])

const innerOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

const SYNTH_ENGINES = [
  { value: 'askcos', label: 'ASKCOS', desc: '基于反应模板的逆合成分析，需本地 ASKCOS 服务' },
  { value: 'internlm', label: 'AI4S大模型', desc: '基于 InternLM 大模型推理的逆合成，无需本地服务' },
  { value: 'scp', label: 'SCP 科学工具', desc: '基于 MCP/SCP 科学工具链的逆合成与反应计算' },
]

// 合成引擎（SCP）信息卡数据，与后端 SCPCatalog 的 scp_scitool_chem 保持一致
const SCP_ENGINE_INFO = {
  value: 'scp',
  name: 'SCP 科学工具',
  avatar: '⚗️',
  provider: '浙江大学',
  tool_count: 169,
  summary: '面向化学信息学、药物设计、反应工程及计算化学领域的综合性工具库',
  introduction:
    'SciToolAgent-Chem 由浙江大学开发，整合分子结构分析、化学反应预测、分子描述符计算、指纹生成、机器学习建模等多种功能，为化学研究与药物发现提供全流程计算支持。工具集涵盖 169 个原子级工具，覆盖化学结构格式互转、分子性质与描述符计算、化学反应预测与逆合成路径规划、分子相似度与子结构匹配、官能团识别与立体化学分配、安全性与爆炸性评估、分子聚类与机器学习分类等核心能力。',
  features: [
    '化学结构格式互转（SMILES / InChI / CAS / SELFIES）',
    '分子性质与描述符计算',
    '化学反应预测与逆合成路径规划',
    '分子相似度与子结构匹配',
    '安全性与爆炸性评估',
    '分子聚类与机器学习分类',
  ],
  use_cases: [
    '药物发现与先导化合物优化',
    '反应工程与路径规划',
    '材料化学与催化剂筛选',
    '化学信息学与 QSAR 建模',
  ],
}

const selectedSynthEngine = ref('askcos')
const selectedSynthAgentId = ref(undefined)
const synthNumRoutes = ref(3)
const synthAgentsLoading = ref(false)
const synthAgentOptions = ref([])

// 晶体支持 AI4S大模型 + SCP；分子显示全部（ASKCOS 不支持无机晶体）
const availableSynthEngines = computed(() =>
  props.structureKind === 'crystal'
    ? SYNTH_ENGINES.filter((m) => m.value === 'internlm' || m.value === 'scp')
    : SYNTH_ENGINES
)

const selectedSynthEngineMeta = computed(() =>
  SYNTH_ENGINES.find((m) => m.value === selectedSynthEngine.value)
)

// 当前选中引擎的详情（用于信息卡展示）
const selectedEngineInfo = computed(() => {
  if (selectedSynthEngine.value === 'scp') return SCP_ENGINE_INFO
  const meta = selectedSynthEngineMeta.value
  if (!meta) return null
  return {
    value: meta.value,
    name: meta.label,
    avatar: meta.value === 'askcos' ? '🔬' : '🧠',
    provider: meta.value === 'askcos' ? 'MIT' : '上海人工智能实验室',
    tool_count: meta.value === 'askcos' ? undefined : 1,
    summary: meta.desc,
    introduction: meta.desc,
    features: meta.value === 'askcos'
      ? ['基于反应模板的逆合成分析', '可解释的反应路径', '依赖本地 ASKCOS 服务']
      : ['基于大模型推理', '无需本地服务', '支持分子与晶体材料'],
    use_cases: meta.value === 'askcos'
      ? ['有机小分子合成规划', '已知反应模板覆盖的分子']
      : ['新颖分子逆合成', '晶体固相合成路径', 'ASKCOS 不可用时的兜底'],
  }
})

/** 拉取具备 synthesis_evidence 能力的智能体 */
async function loadSynthAgents() {
  synthAgentsLoading.value = true
  try {
    const res = await client.get('/agents')
    const list = res?.agents || []
    const options = list
      .filter((a) => (a.capabilities || []).includes('synthesis_evidence'))
      .map((a) => ({
        value: a.id || a.agent_id,
        label: a.name || a.id || a.agent_id,
      }))
      .filter((opt) => opt.value)
    synthAgentOptions.value = options
    // D7 修复：晶体材料默认选中合成规划智能体，减少用户操作
    if (props.structureKind === 'crystal' && !selectedSynthAgentId.value) {
      const defaultAgent = options.find((o) => o.value.includes('synthesis'))
        || options[0]
      if (defaultAgent) {
        selectedSynthAgentId.value = defaultAgent.value
      }
    }
  } catch {
    synthAgentOptions.value = []
  } finally {
    synthAgentsLoading.value = false
  }
}

// 抽屉打开时：校验 + 设置默认引擎 + 加载智能体
watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return
    // 晶体走 LOGOS 固相合成，不需要 SMILES；分子仍要求 SMILES
    if (props.structureKind !== 'crystal' && !props.smiles) {
      message.warning('该候选材料无 SMILES，无法进行逆合成分析')
      innerOpen.value = false
      return
    }
    if (props.structureKind === 'crystal' && !props.candidate.formula) {
      message.warning('该候选材料无化学式，无法进行固相合成规划')
      innerOpen.value = false
      return
    }
    // 按材料类型调整默认引擎
    if (props.structureKind === 'crystal') {
      selectedSynthEngine.value = 'internlm'
    } else if (!selectedSynthEngine.value) {
      selectedSynthEngine.value = 'askcos'
    }
    // 切换材料类型时若旧引擎不适用，重置
    const validValues = availableSynthEngines.value.map((m) => m.value)
    if (!validValues.includes(selectedSynthEngine.value)) {
      selectedSynthEngine.value = validValues[0]
    }
    // D7 修复：先加载智能体列表再打开抽屉，避免抽屉渲染时选项为空
    await loadSynthAgents()
  }
)

function onSubmit() {
  const isCrystal = props.structureKind === 'crystal'
  const payload = {
    smiles: isCrystal ? '' : (props.smiles || ''),
    num_routes: synthNumRoutes.value || 3,
    engine_type: selectedSynthEngine.value || undefined,
    agent_id: selectedSynthAgentId.value || undefined,
    material_type: isCrystal ? 'crystal' : 'molecule',
    formula: isCrystal ? (props.candidate.formula || '') : '',
    space_group: isCrystal ? (props.candidate.space_group || '') : '',
    candidate_id: props.candidateId,
  }
  emit('submit', payload)
}
</script>

<style scoped>
.cs-drawer {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.cs-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cs-section-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1f1f1f);
  display: flex;
  align-items: center;
  gap: 6px;
}

.cs-info-icon {
  color: var(--text-secondary, #999);
  font-size: 12px;
}

.cs-material-name {
  font-size: 13px;
  color: var(--text-secondary, #666);
  margin-left: 4px;
}

.cs-model-group {
  width: 100%;
  display: flex;
}

.cs-model-group :deep(.ant-radio-button-wrapper) {
  flex: 1;
  text-align: center;
}

.cs-model-desc {
  font-size: 12px;
  color: var(--text-secondary, #999);
  line-height: 1.5;
}

.cs-agent-select {
  width: 100%;
}

.cs-num-routes {
  width: 100%;
}

.cs-empty-hint {
  font-size: 12px;
  color: var(--text-secondary, #999);
}

.cs-actions {
  margin-top: 8px;
}

/* 合成引擎信息卡（参考首席材料科学家 AI 卡片） */
.engine-info-row {
  margin-top: 10px;
}

.agent-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px 2px 6px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 12px;
  line-height: 1;
  user-select: none;
}

.agent-chip:hover {
  border-color: var(--primary, #2050d0);
  background: #fff;
}

.agent-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fff7e6;
  font-size: 13px;
}

.agent-name {
  color: var(--text-primary, #333);
  font-weight: 500;
}

.ai-tag {
  margin-left: 2px;
  transform: scale(0.9);
  transform-origin: center;
}

.agent-detail-card {
  width: 280px;
  max-width: 100%;
}

.agent-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
}

.agent-avatar-lg {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #fff7e6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.agent-meta {
  flex: 1;
  min-width: 0;
}

.agent-name-lg {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #333);
  margin-bottom: 4px;
}

.agent-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.agent-section {
  margin-top: 10px;
}

.agent-section-title {
  font-size: 11px;
  color: var(--text-secondary, #666);
  margin-bottom: 4px;
  font-weight: 500;
}

.agent-desc {
  font-size: 12px;
  color: var(--text-primary, #333);
  line-height: 1.5;
}

.popover-title {
  font-weight: 600;
}
</style>
