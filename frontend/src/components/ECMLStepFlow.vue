<template>
  <div class="step-flow" role="list" aria-label="ECML 流程步骤">
    <div
      v-for="(step, idx) in steps"
      :key="step.key"
      class="step-item"
      :class="[getStepClass(step.key), { clickable: isStepClickable(step.key) }]"
      role="listitem"
      :tabindex="isStepClickable(step.key) ? 0 : -1"
      :aria-label="`查看 ${step.title} 步骤详情`"
      @click="onStepClick(step)"
      @keydown.enter.prevent="onStepClick(step)"
    >
      <div class="step-indicator">
        <div class="step-dot">
          <CheckOutlined v-if="isCompleted(step.key) && !isNoResultStep(step.key) && !isFailed(step.key)" aria-hidden="true" />
          <WarningOutlined v-else-if="isCompleted(step.key) && isNoResultStep(step.key)" aria-hidden="true" />
          <CloseOutlined v-else-if="isFailed(step.key)" aria-hidden="true" />
          <LoadingOutlined v-else-if="isCurrent(step.key)" spin aria-hidden="true" />
          <span v-else>{{ idx + 1 }}</span>
        </div>
        <div v-if="idx < steps.length - 1" class="step-line" aria-hidden="true" />
      </div>
      <div class="step-content">
        <div class="step-title">{{ step.title }}</div>
        <div class="step-desc">{{ step.desc }}</div>
        <AgentChip
          v-if="step.agentId"
          class="step-agent-chip"
          :agent-id="step.agentId"
          :fallback-name="step.agentName"
          :interactive="false"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { CheckOutlined, LoadingOutlined, WarningOutlined, CloseOutlined } from '@ant-design/icons-vue'
import AgentChip from './AgentChip.vue'

const props = defineProps({
  currentStep: { type: String, default: '' },
  completedSteps: { type: Array, default: () => [] },
  // 失败或需人工干预的步骤 key 列表
  failedSteps: { type: Array, default: () => [] },
  // 当迭代完成但未找到满足目标的候选时，传入 true，步骤显示为 warning 而非 success
  noResult: { type: Boolean, default: false },
  // 可点击的步骤 key 列表（有历史记录的步骤才可点击）
  clickableSteps: { type: Array, default: () => [] },
})

const emit = defineEmits(['step-click'])

// agentId/agentName 与后端 ecml_engine._STEP_AGENT_MAP 保持一致
// v4.1：描述切换为改性塑料领域（描述符/工程塑料体系）
const steps = [
  { key: 'step1_route', title: '材料路由', desc: '判断材料类型，选择处理分支', agentId: 'builtin_material_router', agentName: '材料路由调度员' },
  { key: 'step2_generate', title: '候选生成', desc: '生成 N 个候选配方（基材+增强/阻燃/增韧）', agentId: 'builtin_material_discovery', agentName: '首席材料学家' },
  { key: 'step3_industrialization', title: '工业化验证', desc: '配方合规审查与成本评估', agentId: 'builtin_industrialization', agentName: '配方工艺师' },
  { key: 'step4_predict', title: '性质预测', desc: '描述符/ML 模型预测力学与热学性能', agentId: 'builtin_battery_oracle', agentName: '材料性质预言者' },
  { key: 'step5_verify', title: '性能验证', desc: '候选性能交叉验证与证据核查', agentId: 'builtin_dft_verifier', agentName: 'DFT 计算专家' },
  { key: 'step6_experiment', title: '实验闭环', desc: '标准测试方法（GB/T/ISO/ASTM）表征', agentId: 'builtin_experiment_analyst', agentName: '实验数据分析员' },
  { key: 'step7_feedback', title: '反馈迭代', desc: '实测数据对比，调整策略', agentId: 'builtin_battery_learner', agentName: '材料数据学习者' },
]

function isCurrent(key) {
  return props.currentStep === key
}

function isCompleted(key) {
  return props.completedSteps.includes(key)
}

function isFailed(key) {
  return props.failedSteps.includes(key)
}

function isStepClickable(key) {
  return props.clickableSteps.includes(key)
}

// 当 noResult 为 true 时，"候选生成"步骤及之后都应显示为 warning
function isNoResultStep(key) {
  if (!props.noResult) return false
  const idx = steps.findIndex((s) => s.key === key)
  // 候选生成（index 1）及之后步骤都标记为 warning
  return idx >= 1
}

function getStepClass(key) {
  // 失败状态优先级高于 completed/no-result
  if (isFailed(key)) return 'failed'
  if (isCurrent(key)) return 'current'
  if (isCompleted(key)) {
    return isNoResultStep(key) ? 'no-result' : 'completed'
  }
  return 'pending'
}

function onStepClick(step) {
  if (isStepClickable(step.key)) {
    emit('step-click', step)
  }
}
</script>

<style scoped>
.step-flow {
  display: flex;
  gap: 0;
  padding: 12px 0;
  overflow-x: auto;
  scrollbar-width: thin;
}

.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 96px;
  position: relative;
}

/* 可点击的步骤显示 hover 反馈 */
.step-item.clickable {
  cursor: pointer;
}

.step-item.clickable:hover .step-dot {
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.step-item.clickable:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 4px;
  border-radius: var(--radius);
}

.step-indicator {
  display: flex;
  align-items: center;
  width: 100%;
}

.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 12px;
  flex-shrink: 0;
  background: var(--light-bg-hover);
  color: var(--text-muted);
  border: 1px solid var(--border);
  z-index: 1;
  font-variant-numeric: tabular-nums;
  transition: transform 0.2s, box-shadow 0.2s;
}

.step-item.completed .step-dot {
  background: var(--success);
  color: #fff;
  border-color: var(--success);
}

.step-item.no-result .step-dot {
  background: var(--warning, #faad14);
  color: #fff;
  border-color: var(--warning, #faad14);
}

.step-item.failed .step-dot {
  background: var(--error, #ff4d4f);
  color: #fff;
  border-color: var(--error, #ff4d4f);
}

.step-item.current .step-dot {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
  box-shadow: 0 0 0 4px var(--primary-bg);
  animation: step-pulse 2s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .step-item.current .step-dot {
    animation: none;
  }
  .step-item.clickable:hover .step-dot {
    transform: none;
  }
}

@keyframes step-pulse {
  0%, 100% {
    box-shadow: 0 0 0 4px var(--primary-bg);
  }
  50% {
    box-shadow: 0 0 0 6px var(--primary-bg-hover);
  }
}

.step-line {
  flex: 1;
  height: 1px;
  background: var(--border);
  margin: 0 4px;
}

.step-item.completed .step-line {
  background: var(--success);
}

.step-item.no-result .step-line {
  background: var(--warning, #faad14);
}

.step-item.failed .step-line {
  background: var(--error, #ff4d4f);
}

.step-item.current .step-line {
  background: linear-gradient(90deg, var(--primary), var(--border));
}

.step-content {
  text-align: center;
  margin-top: 8px;
  padding: 0 4px;
}

.step-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.step-item.pending .step-title {
  color: var(--text-muted);
  font-weight: 500;
}

.step-item.no-result .step-title {
  color: var(--warning, #faad14);
}

.step-item.failed .step-title {
  color: var(--error, #ff4d4f);
}

.step-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  line-height: 1.4;
}

.step-agent-chip {
  margin-top: 6px;
}
</style>
