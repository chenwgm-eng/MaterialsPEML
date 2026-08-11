/**
 * 全系统统一的材料类型枚举定义
 *
 * 两套体系：
 * 1. 科研侧材料范围（crystal/polymer/molecule/electrolyte）——用于候选发现、性质预测、研发工作台
 * 2. 工业化侧物料分类（BASE_POLYMER/LITHIUM_SALT/FILLER 等）——用于物料库存、属性字典模板
 *
 * 工业化侧物料类型支持自定义：通过 /properties/material-type-templates API 动态加载已定义的类型，
 * 并在属性字典页面允许新增。所有引用工业化侧物料类型的页面都应从该 API 或此常量获取。
 */

// ===== 科研侧材料范围 =====
export const RESEARCH_MATERIAL_SCOPES = [
  { value: 'crystal', label: '晶体' },
  { value: 'polymer', label: '聚合物' },
  { value: 'molecule', label: '分子' },
  { value: 'electrolyte', label: '电解质' },
]

// 科研侧 material_scope → 性质预测 material_type 映射
export const SCOPE_TO_PREDICTION_TYPE = {
  crystal: 'crystal',
  polymer: 'polymer',
  molecule: 'polymer',
  electrolyte: 'polymer',
}

// ===== 工业化侧物料分类（预置默认项，支持通过后端 API 扩展） =====
// value 与 DB mdm.classifications(domain=material) 实际播种值严格对齐
// （mdm 加载失败时回退到本列表；写入 raw_materials.category 有 FK → 必须用 DB 存在的 code）
// v4.1 改性塑料领域：基材 + 增强/阻燃/改性助剂体系
export const DEFAULT_INDUSTRIAL_CATEGORIES = [
  { value: 'BASE_POLYMER', label: '基材', color: 'blue' },
  { value: 'material.plastic_base', label: '塑料基材', color: 'blue' },
  { value: 'material.reinforcement', label: '增强填料', color: 'cyan' },
  { value: 'material.flame_retardant', label: '阻燃剂', color: 'volcano' },
  { value: 'material.impact_modifier', label: '增韧改性剂', color: 'purple' },
  { value: 'FILLER', label: '填料', color: 'cyan' },
  { value: 'ADDITIVE', label: '添加剂', color: 'orange' },
  { value: 'SOLVENT', label: '溶剂(配方)', color: 'green' },
  { value: 'BINDER', label: '粘结剂', color: 'magenta' },
  { value: 'material.raw_chemical', label: '原料化学品', color: 'geekblue' },
  { value: 'material.hazardous', label: '危险品', color: 'red' },
  { value: 'material.standard', label: '标准品', color: 'gold' },
]

// 工业化侧物料分类的标签/颜色映射工具函数
export function industrialCategoryLabel(value, categories = DEFAULT_INDUSTRIAL_CATEGORIES) {
  const item = categories.find((c) => c.value === value)
  return item ? item.label : value
}

export function industrialCategoryColor(value, categories = DEFAULT_INDUSTRIAL_CATEGORIES) {
  const item = categories.find((c) => c.value === value)
  return item ? item.color : 'default'
}

// ===== 执行偏好模式说明 =====
// value 保持与后端一致（balanced/rapid_exploration/conservative）
export const EXECUTION_PREFERENCE_MODES = [
  {
    value: 'balanced',
    label: '标准模式',
    description: '平衡速度与精度，适合日常研发迭代。DFT 计算使用中等精度，实验验证按常规流程执行。',
  },
  {
    value: 'rapid_exploration',
    label: '快速模式',
    description: '优先速度，适合初步筛选阶段。跳过部分高精度计算，快速生成候选方案，但结果精度较低。',
  },
  {
    value: 'conservative',
    label: '精确模式',
    description: '优先精度，适合最终验证阶段。使用高精度 DFT 计算和严格实验验证，耗时较长但结果可靠。',
  },
]
