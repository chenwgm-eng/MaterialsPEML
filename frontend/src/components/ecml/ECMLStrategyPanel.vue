<template>
  <a-card class="strategy-card" :bordered="false">
    <template #title>
      <div class="strategy-title">
        <span>智能推荐下一批候选</span>
        <a-tag color="orange" class="strategy-role-tag">课题负责人配置</a-tag>
      </div>
    </template>

    <div class="strategy-subtitle">
      基于同一材料体系的历史实验数据，自动推荐下一轮最值得试的候选。保持默认即可，细节参数见「高级选项」。
    </div>

    <a-form layout="vertical" class="strategy-form">
      <!-- 第 1 段（默认可见）：训练数据池概况 + 数据不足前置告警 -->
      <div class="pool-block">
        <div class="pool-head">
          <span class="pool-title">训练数据池</span>
          <a-space>
            <a-tag v-if="stats && stats.total > 0" color="green" class="pool-state-tag">可启动智能推荐</a-tag>
            <a-tag v-else-if="stats" color="orange" class="pool-state-tag">暂不可启动</a-tag>
            <a-button size="small" :loading="loadingStats" @click="loadStats">刷新</a-button>
          </a-space>
        </div>

        <!-- 数据不足：前置告警，避免用户配完所有参数才被拦下 -->
        <a-alert
          v-if="stats && stats.total === 0"
          type="warning"
          show-icon
          banner
          class="pool-empty-alert"
        >
          <template #message>
            当前材料体系下还没有可用的实验数据，暂时无法运行智能推荐。
            <a-tag color="orange">请先积累至少 1 条实验数据</a-tag>
          </template>
          <template #description>
            数据会自动按「材料体系 + 目标属性」归类聚合，无需手动整理。已有 {{ formTargetPropertyLabel }} 的实验结果录入后，这里即可自动启用。
          </template>
        </a-alert>

        <div class="pool-body">
          <a-form-item label="材料体系" extra="已根据当前目标自动识别，如需调整可直接修改">
            <a-input v-model:value="materialFamily" placeholder="如 玻纤增强聚丙烯改性体系" allow-clear @blur="loadStats" />
          </a-form-item>
          <div class="pool-stats">
            <template v-if="stats">
              <div class="pool-stat">
                <span class="pool-stat-num" :class="{ muted: stats.total === 0 }">{{ stats.total }}</span>
                <span class="pool-stat-label">条有效数据</span>
              </div>
              <div class="pool-stat">
                <span class="pool-stat-num" :class="{ muted: stats.total === 0 }">{{ stats.project }}</span>
                <span class="pool-stat-label">条本项目</span>
              </div>
              <div class="pool-stat">
                <span class="pool-stat-num" :class="{ muted: stats.total === 0 }">{{ stats.cross_project }}</span>
                <span class="pool-stat-label">条可跨项目复用</span>
              </div>
            </template>
            <span v-else class="pool-stats-empty">加载中…</span>
          </div>
          <a-checkbox v-model:checked="includeCrossProject" class="pool-cross" @change="loadStats">
            纳入同一材料体系下的跨项目历史数据（相似化学空间的实验经验可复用，帮助更准地推荐）
          </a-checkbox>
          <div v-if="qualityHits > 0" class="pool-note">
            已自动剔除 {{ qualityHits }} 条未通过质量校验的数据点
          </div>
        </div>
      </div>

      <!-- 一键启动（默认可见） -->
      <div class="strategy-actions">
        <a-button type="primary" :loading="starting" :disabled="!canStart" @click="onStart">
          <PlayCircleOutlined /> 启动智能推荐
        </a-button>
        <span v-if="!canStart" class="strategy-actions-hint">无可用实验数据，暂无法启动</span>
        <span v-else class="strategy-actions-desc">生成候选后停在复核确认，由你决定是否下发实验</span>
      </div>

      <!-- 第 2 段（默认折叠）：算法细节，普通用户无需触碰 -->
      <a-collapse class="advanced-collapse" :bordered="false">
        <a-collapse-panel key="advanced">
          <template #header>
            <span class="advanced-header">高级选项（通常无需修改，系统已自动优化）</span>
          </template>

          <a-row :gutter="16">
            <!-- 代理模型 -->
            <a-col :xs="24" :sm="12" :md="6">
              <a-form-item
                label="预测模型"
                extra="用于从历史数据推测候选性能的工具，系统会按数据量自动选用最合适的"
              >
                <a-select v-model:value="modelFamily" style="width: 100%">
                  <a-select-option value="auto">自动推荐</a-select-option>
                  <a-select-option value="gp">高斯过程</a-select-option>
                  <a-select-option value="gbt">梯度提升树</a-select-option>
                  <a-select-option value="mlp">神经网络</a-select-option>
                </a-select>
                <div class="model-reason" @click="showModelReason = !showModelReason">
                  <template v-if="modelFamily === 'auto'">
                    {{ autoModelReason.short }}
                    <span class="model-reason-link">{{ showModelReason ? '收起' : '为什么这样选？' }}</span>
                  </template>
                  <template v-else>已手动指定 {{ modelLabel(modelFamily) }}</template>
                </div>
                <div v-if="showModelReason && modelFamily === 'auto'" class="model-reason-detail">
                  {{ autoModelReason.detail }}
                </div>
              </a-form-item>
            </a-col>

            <!-- 采集函数 -->
            <a-col :xs="24" :sm="12" :md="6">
              <a-form-item
                label="推荐策略"
                extra="决定系统在「稳妥推进」和「大胆尝试」之间的倾向"
              >
                <a-select v-model:value="acquisition" style="width: 100%" @change="onAcquisitionChange">
                  <a-select-option v-for="opt in acquisitionOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </a-select-option>
                </a-select>
                <div class="acq-hint">{{ acquisitionDesc }}</div>
              </a-form-item>
            </a-col>

            <!-- 探索强度 -->
            <a-col :xs="24" :sm="12" :md="6">
              <a-form-item>
                <template #label>
                  <span>实验倾向</span>
                </template>
                <a-slider
                  v-model:value="explorePercent"
                  :step="10"
                  :marks="{ 0: '更保守', 50: '平衡', 100: '更冒进' }"
                  :disabled="acquisition === 'pi'"
                />
                <div class="explore-hint">
                  <span>更保守：优先试预测最有把握的方向</span>
                  <span>更冒进：优先试数据不足但潜力未知的方向</span>
                </div>
              </a-form-item>
            </a-col>

            <!-- 每轮候选数量 + 预算 -->
            <a-col :xs="24" :sm="12" :md="6">
              <a-row :gutter="8">
                <a-col :span="12">
                  <a-form-item label="每轮候选数量">
                    <a-input-number v-model:value="numCandidates" :min="1" :max="10" style="width: 100%" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="预算上限（成本分）">
                    <a-input-number v-model:value="budget" :min="0" :precision="1" placeholder="不限" style="width: 100%" />
                  </a-form-item>
                </a-col>
              </a-row>
            </a-col>
          </a-row>
        </a-collapse-panel>
      </a-collapse>
    </a-form>
  </a-card>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { PlayCircleOutlined } from '@ant-design/icons-vue'
import { getECMLPoolStats } from '@/api/ecml'

const props = defineProps({
  runId: { type: String, default: '' },
  target: { type: String, default: '' },
  targetProperty: { type: String, default: '' },
  poolStats: { type: Object, default: null }, // 父组件可能已从 round 结果带回的 pool
})

const emit = defineEmits(['start', 'acquisition-change'])

// ---- 推荐策略选项与业务翻译 ----
const acquisitionOptions = [
  { value: 'ei', label: '稳健推进（推荐）', desc: '兼顾风险与收益，适合大多数常规迭代' },
  { value: 'ucb', label: '大胆尝试', desc: '更愿意尝试没把握但潜力大的方向' },
  { value: 'pi', label: '稳妥收敛', desc: '风险厌恶，适合想快速稳定的课题' },
  { value: 'ehvi', label: '多目标覆盖', desc: '多目标：一次性兼顾多个属性的帕累托最优（权重自动失效）' },
]

const acquisitionDesc = computed(() => {
  const opt = acquisitionOptions.find((o) => o.value === acquisition.value)
  return opt ? opt.desc : ''
})

function onAcquisitionChange() {
  if (acquisition.value === 'pi') explorePercent.value = 50
  emit('acquisition-change', acquisition.value)
}

const modelFamily = ref('auto')
const acquisition = ref('ei')
const explorePercent = ref(50)
const materialFamily = ref('')
const numCandidates = ref(5)
const budget = ref(null)
const includeCrossProject = ref(false)
const showModelReason = ref(false)

// ---- 训练池统计 ----
const stats = ref(null)
const qualityHits = ref(0)
const loadingStats = ref(false)

const modelLabel = (k) => ({ gp: '高斯过程', gbt: '梯度提升树', mlp: '神经网络' }[k] || k)

// 目标属性业务名（用于告警文案）
const formTargetPropertyLabel = computed(() => {
  const map = {
    tensile_strength: '拉伸强度',
    flexural_modulus: '弯曲模量',
    impact_strength: '冲击强度',
    heat_deflection_temp: '热变形温度',
    melt_flow_index: '熔体流动速率',
    glass_transition_temp: '玻璃化转变温度',
  }
  return map[props.targetProperty] || props.targetProperty || '目标属性'
})

const autoModelReason = computed(() => {
  const n = stats.value?.total ?? 0
  let rec = 'gp'
  let detail = ''
  if (n < 50) {
    rec = 'gp'
    detail = `当前数据 ${n} 条（较少），推荐高斯过程：在数据量小、需要严格量化不确定性的场景表现最佳，是材料研发早期最常用的选择。`
  } else if (n <= 300) {
    rec = 'gbt'
    detail = `当前数据 ${n} 条（适中），推荐梯度提升树：适合数据量适中、属性较多、关系复杂的场景。`
  } else {
    rec = 'mlp'
    detail = `当前数据 ${n} 条（较多），推荐神经网络：数据量大时能捕捉更复杂的映射关系。`
  }
  return { model: rec, short: `当前数据 ${n} 条，推荐 ${modelLabel(rec)}`, detail }
})

async function loadStats() {
  if (!props.runId) return
  loadingStats.value = true
  try {
    const res = await getECMLPoolStats(props.runId, {
      material_family: materialFamily.value,
      target_property: props.targetProperty,
    })
    stats.value = res?.stats || null
    qualityHits.value = Array.isArray(res?.quality_report) ? res.quality_report.length : 0
  } catch {
    stats.value = null
  } finally {
    loadingStats.value = false
  }
}

const canStart = computed(() => (stats.value?.total ?? 0) > 0)

// ---- 启动 ----
const starting = ref(false)
async function onStart() {
  if (!props.runId) {
    message.warning('请先在上方配置并启动一轮实验闭环迭代，再使用智能推荐')
    return
  }
  starting.value = true
  try {
    emit('start', {
      material_family: materialFamily.value,
      acquisition: acquisition.value,
      explore: explorePercent.value / 100,
      model_family: modelFamily.value === 'auto' ? '' : modelFamily.value,
      budget: budget.value ?? null,
      include_cross_project: includeCrossProject.value,
      num_candidates: Number(numCandidates.value) || 5,
    })
  } finally {
    starting.value = false
  }
}

// 父组件带回的 pool 统计优先展示
watch(
  () => props.poolStats,
  (p) => {
    if (p?.stats) stats.value = p.stats
  },
  { immediate: true }
)

onMounted(() => {
  if (props.target) {
    materialFamily.value = props.target
  }
  loadStats()
})
</script>

<style scoped>
.strategy-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.strategy-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.strategy-role-tag {
  margin: 0;
  font-size: 11px;
}

.strategy-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 12px;
}

.strategy-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

/* 训练数据池 */
.pool-block {
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}

.pool-empty-alert {
  margin-bottom: 12px;
}

.pool-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.pool-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.pool-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.pool-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 8px;
  background: var(--light-bg, #fafafa);
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: var(--radius-md, 8px);
}

.pool-stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.pool-stat-num.muted {
  color: var(--text-muted);
}

.pool-stat-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.pool-stats-empty {
  color: var(--text-muted);
  font-size: 12px;
}

.pool-cross {
  font-size: 12px;
  color: var(--text-secondary);
  display: block;
  margin-top: 4px;
}

.pool-note {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 高级选项 */
.advanced-collapse {
  margin-top: 4px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 8px;
}

.advanced-collapse :deep(.ant-collapse-content-box) {
  padding-top: 8px;
}

.advanced-header {
  font-size: 12px;
  color: var(--text-secondary);
}

/* 代理模型 */
.model-reason {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
  cursor: pointer;
}

.model-reason-link {
  color: var(--primary);
}

.model-reason-detail {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: 6px;
  padding: 6px 8px;
  margin-top: 4px;
  line-height: 1.5;
}

.acq-hint {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
  line-height: 1.4;
}

.explore-hint {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
  margin-top: 2px;
}

/* 启动区 */
.strategy-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px 16px;
  margin-bottom: 12px;
  background: var(--light-bg, #fafafa);
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: var(--radius-md, 8px);
}

.strategy-actions-hint,
.strategy-actions-desc {
  font-size: 12px;
  color: var(--text-muted);
}
</style>