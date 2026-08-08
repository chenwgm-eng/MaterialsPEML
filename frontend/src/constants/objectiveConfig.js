/**
 * 多目标优化共享常量（P1-A1）
 *
 * 统一供给两个视图的默认配置与可选项，避免重复硬编码漂移：
 * - TemporaryPrediction.vue（临时材料性能预测，已并入「材料设计」工作台）
 * - ECMLMonitor.vue（实验闭环迭代）
 *
 * 用法：
 *   import { DEFAULT_MULTI_OBJECTIVE_CONFIG, MULTI_OBJECTIVE_OPTIONS } from '@/constants/objectiveConfig'
 *   const multiObjectiveConfig = reactive({ ...DEFAULT_MULTI_OBJECTIVE_CONFIG })
 *   const multiObjectiveOptions = ref([...MULTI_OBJECTIVE_OPTIONS])
 */

// 默认多目标配置：权重 + 优化方向（与后端 _apply_multi_objective 语义一致）
export const DEFAULT_MULTI_OBJECTIVE_CONFIG = {
  ionic_conductivity: { weight: 0.5, direction: 'maximize', min: null, max: null },
  band_gap: { weight: 0.3, direction: 'maximize', min: null, max: null },
  formation_energy: { weight: 0.3, direction: 'minimize', min: null, max: null },
  stability: { weight: 0.3, direction: 'maximize', min: null, max: null },
  energy_above_hull: { weight: 0.2, direction: 'minimize', min: null, max: null },
}

// 多目标可选项（中文 label + value）
export const MULTI_OBJECTIVE_OPTIONS = [
  { label: '离子电导率', value: 'ionic_conductivity' },
  { label: '带隙', value: 'band_gap' },
  { label: '形成能', value: 'formation_energy' },
  { label: '稳定性', value: 'stability' },
  { label: '能量高于凸包', value: 'energy_above_hull' },
]