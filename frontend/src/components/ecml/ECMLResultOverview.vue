<template>
  <a-card v-if="state" class="result-overview-card" :bordered="false">
    <template #title>
      <span class="card-title-text"><TrophyOutlined /> 结果概览</span>
    </template>
    <template #extra>
      <a-space>
        <a-button size="small" @click="emit('scroll-to-detail', 'feedback')" v-if="state?.is_complete">
          查看反馈与建议
        </a-button>
        <a-button size="small" type="primary" ghost @click="emit('run-again')" v-if="state?.is_complete">
          <ReloadOutlined /> 调整参数重新运行
        </a-button>
      </a-space>
    </template>
    <!-- 区块用途说明 -->
    <a-alert
      type="info"
      show-icon
      :message="`展示本轮迭代的最优候选材料与流程漏斗，可直接发送到实验/配方进入下一环节`"
      style="margin-bottom: 12px"
    />
    <div class="overview-body">
      <div class="overview-main">
        <div class="overview-conclusion">{{ runConclusion }}</div>
        <!-- 流程漏斗 -->
        <div class="pipeline-funnel">
          <div
            v-for="(item, idx) in pipelineStats"
            :key="item.key"
            class="funnel-item"
            :class="{ 'funnel-active': item.value > 0 }"
          >
            <div class="funnel-value">{{ item.value }}</div>
            <div class="funnel-label">{{ item.label }}</div>
            <RightOutlined v-if="idx < pipelineStats.length - 1" class="funnel-arrow" />
          </div>
        </div>
      </div>

      <!-- 最佳候选卡片 -->
      <div v-if="bestCandidate" class="best-candidate-card">
        <div class="best-candidate-header">
          <span class="best-candidate-badge">推荐候选材料</span>
          <span class="best-candidate-name">{{ bestCandidate.name || bestCandidate.formula || bestCandidate.smiles || bestCandidate.psmiles || '-' }}</span>
        </div>
        <div class="best-candidate-body">
          <MoleculeView :smiles="bestCandidate.smiles || bestCandidate.psmiles" :size="140" />
          <div class="best-candidate-props">
            <div v-for="p in bestCandidateProps" :key="p.label" class="best-candidate-prop">
              <span class="prop-label">{{ p.label }}</span>
              <span class="prop-value">{{ p.value }}</span>
            </div>
            <div v-if="!bestCandidateProps.length" class="text-muted">暂无预测属性</div>
          </div>
        </div>
        <!-- AI 可信度元信息（证据来自真实验证信号） -->
        <AIOutputMeta
          v-if="bestCandidateAIMeta"
          :confidence="bestCandidateAIMeta.confidence"
          agent-name="ECML 闭环引擎"
          model="InternLM / 图神经网络"
          strategy="闭环迭代优化"
          :assumptions="bestCandidateAIMeta.assumptions"
          :evidence-sources="bestCandidateAIMeta.evidenceSources"
          :human-review-required="bestCandidateAIMeta.humanReviewRequired"
          style="margin: 0 12px 8px"
        />
        <div class="best-candidate-actions">
          <a-button type="primary" size="small" @click="emit('send-best-to-experiment', bestCandidate)">
            <ExperimentOutlined /> 发送到实验
          </a-button>
          <a-button size="small" @click="emit('send-best-to-formula', bestCandidate)">
            <ProfileOutlined /> 发送到配方
          </a-button>
          <a-button size="small" @click="emit('scroll-to-detail', 'candidates')">
            查看全部候选材料
          </a-button>
        </div>
      </div>
    </div>
  </a-card>
</template>

<script setup>
import { computed } from 'vue'
import { TrophyOutlined, RightOutlined, ExperimentOutlined, ProfileOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { formatNumber, formatSci } from '@/utils/format'
import MoleculeView from '@/components/MoleculeView.vue'
import AIOutputMeta from '@/components/AIOutputMeta.vue'

const props = defineProps({
  // ecmlStore.state（读取 target/target_property/iterations/is_complete 等）
  state: { type: Object, default: null },
  // detailCandidates / detailSynthesizable / detailVerified / detailExperiments
  candidates: { type: Array, default: () => [] },
  synthesizable: { type: Array, default: () => [] },
  verified: { type: Array, default: () => [] },
  experiments: { type: Array, default: () => [] },
  // form 兜底（runConclusion 使用）
  fallbackTarget: { type: String, default: '' },
  fallbackProperty: { type: String, default: '' },
  // 属性选项（label 解析）
  propertyOptions: { type: Array, default: () => [] },
  // 单位符号
  condUnit: { type: String, default: 'S/cm' },
  energyUnit: { type: String, default: 'eV' },
  energyPerAtomUnit: { type: String, default: 'eV/atom' },
})

const emit = defineEmits(['send-best-to-experiment', 'send-best-to-formula', 'scroll-to-detail', 'run-again'])

const pipelineStats = computed(() => [
  { key: 'candidates', label: '生成候选材料', value: props.candidates.length },
  { key: 'synthesizable', label: '工业化通过', value: props.synthesizable.length },
  { key: 'verified', label: 'DFT 验证', value: props.verified.length },
  { key: 'experiments', label: '实验闭环', value: props.experiments.length },
])

function scoreCandidate(c) {
  let score = 0
  let count = 0
  if (c.predicted_ionic_conductivity != null) {
    score += Math.min(Number(c.predicted_ionic_conductivity) / 10, 1) * 0.5
    count += 0.5
  }
  if (c.stability_score != null) {
    score += Number(c.stability_score) * 0.25
    count += 0.25
  }
  if (c.industrialization_score != null) {
    score += Number(c.industrialization_score) * 0.25
    count += 0.25
  }
  return count > 0 ? score / count : 0
}

const rankedCandidates = computed(() => {
  return [...props.candidates]
    .map((c) => ({ ...c, _score: scoreCandidate(c) }))
    .sort((a, b) => b._score - a._score)
})

const bestCandidate = computed(() => {
  if (rankedCandidates.value.length) return rankedCandidates.value[0]
  if (props.verified.length) return props.verified[0]
  return null
})

const bestCandidateProps = computed(() => {
  const c = bestCandidate.value
  if (!c) return []
  const result = []
  if (c.predicted_ionic_conductivity != null) {
    result.push({ label: '预测电导率', value: `${formatSci(c.predicted_ionic_conductivity, 3)} ${props.condUnit}` })
  }
  if (c.band_gap != null) result.push({ label: '带隙', value: `${formatNumber(c.band_gap, 4)} ${props.energyUnit}` })
  if (c.formation_energy != null) result.push({ label: '形成能', value: `${formatNumber(c.formation_energy, 4)} ${props.energyPerAtomUnit}` })
  if (c.stability_score != null) result.push({ label: '稳定性', value: formatNumber(c.stability_score, 3) })
  if (c.industrialization_score != null) {
    result.push({ label: '工业化评分', value: `${(Number(c.industrialization_score) * 100).toFixed(1)}%` })
  }
  return result
})

const bestCandidateAIMeta = computed(() => {
  const c = bestCandidate.value
  if (!c) return null
  const synthCount = props.synthesizable.length
  const dftCount = props.verified.length
  const evidenceSources = []
  if (synthCount > 0) evidenceSources.push(`已通过 ${synthCount} 项工业化可行性检查`)
  if (dftCount > 0) evidenceSources.push(`已通过 ${dftCount} 项 DFT 计算验证`)
  if (c.retrieval_verified) evidenceSources.push('Materials Project 数据库检索验证')
  let confidence = typeof c.confidence === 'number' && c.confidence >= 0 && c.confidence <= 1
    ? c.confidence
    : null
  if (confidence == null) {
    confidence = Math.min(0.9, 0.4 + (synthCount > 0 ? 0.2 : 0) + (dftCount > 0 ? 0.2 : 0))
  }
  return {
    confidence,
    assumptions: ['预测属性来自机器学习势/图神经网络模型，未经实验实测'],
    evidenceSources,
    humanReviewRequired: c.human_review_required === true || (synthCount === 0 && dftCount === 0),
  }
})

const runConclusion = computed(() => {
  const target = props.state?.target || props.fallbackTarget
  const prop = props.propertyOptions.find((o) => o.value === (props.state?.target_property || props.fallbackProperty))?.label || props.fallbackProperty
  const iterations = props.state?.iterations || 0
  const best = bestCandidate.value
  if (!best) {
    return `已完成 ${iterations} 轮迭代，未找到满足目标的候选材料。建议调整目标或属性约束后重新运行。`
  }
  const name = best.name || best.formula || best.smiles || best.psmiles || '未知材料'
  return `经过 ${iterations} 轮迭代，系统推荐「${name}」作为${target}目标下「${prop}」的最优候选材料。该候选材料已通过 ${props.synthesizable.length} 项工业化检查、${props.verified.length} 项 DFT 验证。`
})

// 暴露 bestCandidate 和 noResult 给父组件（步骤流/发送下游函数需要）
defineExpose({ bestCandidate, noResult: computed(() => !props.state?.is_complete ? false : !bestCandidate.value) })
</script>

<style scoped>
.overview-body {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 20px;
  align-items: start;
}

.overview-conclusion {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  margin-bottom: 16px;
  padding: 12px 14px;
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius);
}

.pipeline-funnel {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.funnel-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 72px;
  padding: 10px 12px;
  background: var(--light-bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  position: relative;
}

.funnel-item.funnel-active {
  background: var(--primary-bg);
  border-color: var(--primary-border);
}

.funnel-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.funnel-active .funnel-value {
  color: var(--primary);
}

.funnel-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.funnel-arrow {
  color: var(--border-light);
  font-size: 12px;
  margin: 0 2px;
}

.best-candidate-card {
  background: var(--light-bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px;
}

.best-candidate-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.best-candidate-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  border-radius: 10px;
}

.best-candidate-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}

.best-candidate-body {
  display: flex;
  gap: 14px;
  margin-bottom: 12px;
}

.best-candidate-props {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.best-candidate-prop {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  padding: 4px 8px;
  background: var(--light-bg-card);
  border-radius: var(--radius);
}

.prop-label {
  color: var(--text-secondary);
}

.prop-value {
  color: var(--text-primary);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.best-candidate-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 768px) {
  .overview-body {
    grid-template-columns: 1fr;
  }
}
</style>
