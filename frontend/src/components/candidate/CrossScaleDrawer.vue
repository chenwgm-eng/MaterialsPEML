<template>
  <a-drawer
    v-model:open="innerOpen"
    title="跨尺度预测"
    placement="right"
    width="420"
    :destroy-on-close="true"
  >
    <div class="cs-drawer">
      <!-- 材料类型提示 -->
      <div class="cs-section">
        <div class="cs-section-title">材料类型</div>
        <a-tag :color="structureKind === 'crystal' ? 'blue' : 'purple'">
          {{ structureKind === 'crystal' ? '晶体' : '聚合物' }}
        </a-tag>
        <span class="cs-material-name">{{ materialName }}</span>
      </div>

      <!-- 模型选择 -->
      <div class="cs-section">
        <div class="cs-section-title">
          预测模型
          <a-tooltip title="默认选中系统设置中配置的模型；可临时切换为其他模型，仅本次预测有效">
            <InfoCircleOutlined class="cs-info-icon" />
          </a-tooltip>
        </div>
        <a-radio-group v-model:value="selectedModel" button-style="solid" class="cs-model-group">
          <a-radio-button
            v-for="m in availableModels"
            :key="m.value"
            :value="m.value"
            :disabled="m.disabled"
          >
            {{ m.label }}
            <a-tag v-if="m.disabled" size="small" color="default" class="cs-model-disabled-tag">不可用</a-tag>
          </a-radio-button>
        </a-radio-group>
        <div v-if="selectedModelMeta && !selectedModelMeta.disabled" class="cs-model-desc">{{ selectedModelMeta.desc }}</div>
        <div v-else-if="selectedModelMeta && selectedModelMeta.disabled" class="cs-model-desc cs-model-desc--disabled">
          该模型当前不可用，请在系统设置中启用
        </div>
      </div>

      <!-- 智能体选择 -->
      <div class="cs-section">
        <div class="cs-section-title">
          执行智能体
          <a-tooltip title="仅列出具备「性质预测」能力的智能体；可不选，由系统默认 predictor 执行">
            <InfoCircleOutlined class="cs-info-icon" />
          </a-tooltip>
        </div>
        <a-select
          v-model:value="selectedAgentId"
          :loading="agentsLoading"
          :options="agentOptions"
          placeholder="不指定，使用系统默认"
          allow-clear
          class="cs-agent-select"
        />
        <div v-if="!agentOptions.length && !agentsLoading" class="cs-empty-hint">
          暂无具备「性质预测」能力的智能体
        </div>
      </div>

      <!-- 尺度选择 -->
      <div class="cs-section">
        <div class="cs-section-title">预测尺度</div>
        <a-checkbox-group v-model:value="selectedScales" class="cs-scale-group">
          <a-checkbox value="molecular">分子尺度</a-checkbox>
          <a-checkbox value="reaction">反应尺度</a-checkbox>
          <a-checkbox value="continuum">连续介质尺度</a-checkbox>
        </a-checkbox-group>
      </div>

      <!-- 执行按钮 -->
      <div class="cs-actions">
        <a-button
          type="primary"
          block
          :loading="propsLoading"
          :disabled="!selectedScales.length"
          @click="runCrossScale"
        >
          <template #icon><ThunderboltOutlined /></template>
          {{ propsLoading ? '跨尺度求解中…' : '开始预测' }}
        </a-button>
        <div v-if="propsLoading" class="cs-progress">
          <a-progress :percent="taskProgress" :status="taskError ? 'exception' : 'active'" />
          <div class="cs-step-label">
            <LoadingOutlined v-if="!taskError" spin />
            <span>{{ taskError || taskStepLabel }}</span>
          </div>
        </div>
      </div>
    </div>
  </a-drawer>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { ThunderboltOutlined, InfoCircleOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import { crossScalePredictAsync, crossScaleStatus } from '@/api/properties'
import client from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
  candidate: { type: Object, required: true },
  smiles: { type: String, default: '' },
  structureKind: { type: String, default: 'crystal' },
  candidateId: { type: String, default: '' },
  materialName: { type: String, default: '' },
})

const emit = defineEmits(['update:open', 'predicted'])

const innerOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

const CRYSTAL_MODELS = [
  { value: 'cgcnn', label: 'CGCNN', desc: '晶体图卷积神经网络，通用性质预测' },
  { value: 'mt_cgcnn', label: 'MT-CGCNN', desc: '多任务 CGCNN，可同时预测多个性质' },
  { value: 'm3gnet', label: 'M3GNet', desc: '通用材料图网络，精度较高（需 matgl）' },
]
const POLYMER_MODELS = [
  { value: 'polymernn', label: 'PolymerGNN', desc: '聚合物图神经网络' },
  { value: 'descriptor', label: 'Descriptor', desc: '基于 RDKit 描述符的线性模型' },
  { value: 'mattersim', label: 'MatterSim', desc: '基于 ASE-EMT 的能量计算（需 ASE）' },
]

const selectedModel = ref('')
const selectedAgentId = ref(undefined)
const selectedScales = ref(['molecular', 'reaction', 'continuum'])
const agentsLoading = ref(false)
const agentOptions = ref([])
const propsLoading = ref(false)
// 异步任务轮询状态
const taskProgress = ref(0)
const taskStepLabel = ref('')
const taskError = ref('')
let pollTimer = null
// 系统设置中禁用的模型列表
const disabledModels = ref([])

// 根据系统设置计算可用模型（包含disabled标记）
const availableModels = computed(() => {
  const baseModels = props.structureKind === 'crystal' ? CRYSTAL_MODELS : POLYMER_MODELS
  return baseModels.map(m => ({
    ...m,
    disabled: disabledModels.value.includes(m.value),
  }))
})

const selectedModelMeta = computed(() =>
  availableModels.value.find((m) => m.value === selectedModel.value)
)

/** 拉取系统配置中的默认模型 + 具备 property_prediction 能力的智能体 */
async function loadCrossScaleContext() {
  // 1) 读取系统设置中默认模型和禁用列表
  try {
    const cfg = await client.get('/config')
    const defaults = cfg?.prediction_models || {}
    // 获取禁用的模型列表（系统设置中标记为不可用的模型）
    const modelConfig = cfg?.model_config || {}
    disabledModels.value = modelConfig.disabled_models || []

    const defaultModel =
      props.structureKind === 'crystal'
        ? defaults.crystal || 'cgcnn'
        : defaults.polymer || 'polymernn'
    // 如果默认模型被禁用，选择第一个可用的模型
    if (!selectedModel.value) {
      if (!disabledModels.value.includes(defaultModel)) {
        selectedModel.value = defaultModel
      } else {
        const firstAvailable = availableModels.value.find(m => !m.disabled)
        selectedModel.value = firstAvailable?.value || ''
      }
    }
  } catch {
    if (!selectedModel.value) {
      selectedModel.value = props.structureKind === 'crystal' ? 'cgcnn' : 'polymernn'
    }
  }

  // 2) 拉取有 property_prediction 能力的智能体
  agentsLoading.value = true
  try {
    const res = await client.get('/agents')
    const list = res?.agents || []
    agentOptions.value = list
      .filter((a) => (a.capabilities || []).includes('property_prediction'))
      .map((a) => ({
        value: a.id || a.agent_id,
        label: a.name || a.id || a.agent_id,
      }))
      .filter((opt) => opt.value)
  } catch {
    agentOptions.value = []
  } finally {
    agentsLoading.value = false
  }
}

// 抽屉打开时加载上下文 + 校验模型选择
watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    const validValues = availableModels.value.map((m) => m.value)
    if (!validValues.includes(selectedModel.value)) selectedModel.value = ''
    loadCrossScaleContext()
  }
)

// 材料类型切换时清空不匹配的模型选择
watch(
  () => props.structureKind,
  () => {
    const validValues = availableModels.value.map((m) => m.value)
    if (!validValues.includes(selectedModel.value)) selectedModel.value = ''
  }
)

async function runCrossScale() {
  if (!selectedScales.value.length) {
    message.warning('请至少选择一个预测尺度')
    return
  }
  propsLoading.value = true
  taskError.value = ''
  taskProgress.value = 0
  taskStepLabel.value = '正在提交…'
  try {
    const payload = {
      material_type: props.structureKind === 'crystal' ? 'crystal' : 'molecule',
      formula: props.candidate.formula || '',
      smiles: props.smiles,
      scales: selectedScales.value,
      model_type: selectedModel.value || undefined,
      agent_id: selectedAgentId.value || undefined,
      candidate_id: props.candidateId,
    }
    const { task_id } = await crossScalePredictAsync(payload)
    pollTimer = setInterval(() => pollTask(task_id), 2000)
  } catch {
    propsLoading.value = false
    taskError.value = '提交失败'
  }
}

async function pollTask(taskId) {
  try {
    const entry = await crossScaleStatus(taskId)
    taskProgress.value = entry.progress || 0
    taskStepLabel.value = entry.step_label || ''
    if (entry.status === 'completed') {
      clearInterval(pollTimer)
      pollTimer = null
      propsLoading.value = false
      message.success('跨尺度预测完成')
      innerOpen.value = false
      emit('predicted', entry.result)
    } else if (entry.status === 'failed') {
      clearInterval(pollTimer)
      pollTimer = null
      propsLoading.value = false
      taskError.value = entry.error || '跨尺度预测失败'
    }
  } catch {
    // 轮询失败则停止，等待提交侧容错
  }
}

// 组件卸载时清理轮询定时器
onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
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

.cs-model-desc--disabled {
  color: var(--error, #ff4d4f);
}

.cs-model-disabled-tag {
  margin-left: 4px;
  font-size: 10px;
  line-height: 16px;
  padding: 0 4px;
}

.cs-model-group :deep(.ant-radio-button-wrapper-disabled) {
  opacity: 0.6;
}

.cs-agent-select {
  width: 100%;
}

.cs-empty-hint {
  font-size: 12px;
  color: var(--text-secondary, #999);
}

.cs-scale-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cs-actions {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cs-progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cs-progress :deep(.ant-progress) {
  margin-bottom: 0;
}

.cs-step-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary, #666);
  min-height: 18px;
}
</style>
