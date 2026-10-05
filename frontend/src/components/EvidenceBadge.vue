<template>
  <a-tooltip :title="tooltip">
    <a-tag :color="color" size="small">{{ label }}</a-tag>
  </a-tooltip>
</template>

<script setup>
import { computed } from 'vue'

// ADR-0001/0002：数据可信度四档徽标（实测/模拟/模型预测/工程估算）
// 输入 level 或由 data_quality/provenance/model 推断
const props = defineProps({
  level: { type: String, default: '' }, // measured | simulated | predicted | estimated | verified | literature
  model: { type: String, default: '' },
  dataQuality: { type: String, default: '' },
})

const _LEVEL_META = {
  measured: { label: '实测', color: 'green', tooltip: '真实实验测量值（已过数据质量审批）' },
  verified: { label: '实测', color: 'green', tooltip: '真实实验测量值（已过数据质量审批）' },
  simulated: { label: '模拟', color: 'orange', tooltip: '系统仿真生成值，不进入学习池' },
  predicted: { label: '模型预测', color: 'blue', tooltip: '由带真实权重的模型产出' },
  estimated: { label: '工程估算', color: 'default', tooltip: '基于骨架结构启发式的量级估算，未经验证（ADR-0001）' },
  literature: { label: '文献', color: 'purple', tooltip: '来自文献参考值' },
}

const resolved = computed(() => {
  const level = (props.level || props.dataQuality || '').toLowerCase()
  if (_LEVEL_META[level]) return _LEVEL_META[level]
  const m = (props.model || '').toLowerCase()
  if (m.includes('heuristic') || m.includes('descriptor')) {
    return _LEVEL_META.estimated
  }
  if (m.includes('gnn') || m.includes('chemprop') || m.includes('mattersim')) {
    return _LEVEL_META.predicted
  }
  return { label: '未知', color: 'default', tooltip: '' }
})

const label = computed(() => resolved.value.label)
const color = computed(() => resolved.value.color)
const tooltip = computed(() => resolved.value.tooltip)
</script>
