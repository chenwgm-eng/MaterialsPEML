/**
 * 多目标优化共享常量（P1-A1）
 *
 * 统一供给两个视图的默认配置与可选项，避免重复硬编码漂移：
 * - TemporaryPrediction.vue（临时材料性能预测，已并入「材料设计」工作台）
 * - ECMLMonitor.vue（实验闭环迭代）
 *
 * v4.1 改性塑料领域：目标对齐后端 _SCORE_PROPS（4 个 maximize 力学属性）。
 *
 * 用法：
 *   import { DEFAULT_MULTI_OBJECTIVE_CONFIG, MULTI_OBJECTIVE_OPTIONS } from '@/constants/objectiveConfig'
 *   const multiObjectiveConfig = reactive({ ...DEFAULT_MULTI_OBJECTIVE_CONFIG })
 *   const multiObjectiveOptions = ref([...MULTI_OBJECTIVE_OPTIONS])
 */

// 默认多目标配置：权重 + 优化方向（与后端 _apply_multi_objective 语义一致）
// v4.1 改性塑料：4 属性等权（0.25×4=1.0），与后端 _SCORE_PROPS（4 个力学属性）严格对齐
export const DEFAULT_MULTI_OBJECTIVE_CONFIG = {
  tensile_strength: { weight: 0.25, direction: 'maximize', min: null, max: null },
  flexural_modulus: { weight: 0.25, direction: 'maximize', min: null, max: null },
  impact_strength: { weight: 0.25, direction: 'maximize', min: null, max: null },
  heat_deflection_temp: { weight: 0.25, direction: 'maximize', min: null, max: null },
}

// 多目标可选项（中文 label + value；与后端 _SCORE_PROPS 对齐，melt_flow_index 为可选扩展）
export const MULTI_OBJECTIVE_OPTIONS = [
  { label: '拉伸强度', value: 'tensile_strength' },
  { label: '弯曲模量', value: 'flexural_modulus' },
  { label: '冲击强度', value: 'impact_strength' },
  { label: '热变形温度', value: 'heat_deflection_temp' },
]
