/**
 * 枚举值中文化工具（P2-ENUM-001）
 *
 * 解决问题：英文接口枚举值暴露给用户（如 API_PUSH、LEGACY_MIGRATION）
 *
 * 用法：
 *   import { sourceTypeLabel, sourceTypeOptions, statusLabel } from '@/utils/enumLabels'
 *   // 筛选下拉
 *   <a-select :options="sourceTypeOptions" />
 *   // 文本展示
 *   <span>{{ sourceTypeLabel(record.source) }}</span>
 */

// ── 实验数据来源 ──
const SOURCE_TYPE_MAP = {
  API_PUSH: 'API 推送',
  LEGACY_MIGRATION: '历史迁移',
  MANUAL_ENTRY: '手动录入',
  FILE_UPLOAD: '文件上传',
  INSTRUMENT: '仪器采集',
  CALCULATED: '计算生成',
}

export function sourceTypeLabel(value) {
  return SOURCE_TYPE_MAP[value] || value || '-'
}

export const sourceTypeOptions = Object.entries(SOURCE_TYPE_MAP).map(([value, label]) => ({ label, value }))

// ── QC 状态 ──
const QC_STATUS_MAP = {
  valid: '有效',
  invalid: '无效',
  requires_review: '待复核',
  pending: '待检',
}

export function qcStatusLabel(value) {
  return QC_STATUS_MAP[value] || value || '-'
}

export function qcStatusColor(value) {
  const map = { valid: 'green', invalid: 'red', requires_review: 'orange', pending: 'blue' }
  return map[value] || 'default'
}

export const qcStatusOptions = Object.entries(QC_STATUS_MAP).map(([value, label]) => ({ label, value }))

// ── 实验任务状态 ──
const ORDER_STATUS_MAP = {
  DRAFT: '草稿',
  PENDING_APPROVAL: '待审批',
  APPROVED: '已审批',
  REJECTED: '已拒绝',
  IN_PROGRESS: '进行中',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
  WAITING_FOR_DATA: '等待数据',
}

export function orderStatusLabel(value) {
  return ORDER_STATUS_MAP[value] || value || '-'
}

export function orderStatusColor(value) {
  const map = {
    DRAFT: 'default',
    PENDING_APPROVAL: 'orange',
    APPROVED: 'blue',
    REJECTED: 'red',
    IN_PROGRESS: 'processing',
    COMPLETED: 'green',
    CANCELLED: 'default',
    WAITING_FOR_DATA: 'cyan',
  }
  return map[value] || 'default'
}

export const orderStatusOptions = Object.entries(ORDER_STATUS_MAP).map(([value, label]) => ({ label, value }))

// ── 样品状态 ──
const SAMPLE_STATUS_MAP = {
  created: '已创建',
  in_storage: '在库',
  in_use: '使用中',
  consumed: '已消耗',
  discarded: '已废弃',
}

export function sampleStatusLabel(value) {
  return SAMPLE_STATUS_MAP[value] || value || '-'
}

export function sampleStatusColor(value) {
  const map = {
    created: 'blue',
    in_storage: 'green',
    in_use: 'processing',
    consumed: 'default',
    discarded: 'red',
  }
  return map[value] || 'default'
}

export const sampleStatusOptions = Object.entries(SAMPLE_STATUS_MAP).map(([value, label]) => ({ label, value }))

// ── 设备状态 ──
const EQUIPMENT_STATUS_MAP = {
  idle: '空闲',
  in_use: '使用中',
  maintenance: '维护中',
  calibration: '校准中',
  retired: '退役',
}

export function equipmentStatusLabel(value) {
  return EQUIPMENT_STATUS_MAP[value] || value || '-'
}

export function equipmentStatusColor(value) {
  const map = {
    idle: 'green',
    in_use: 'blue',
    maintenance: 'orange',
    calibration: 'purple',
    retired: 'default',
  }
  return map[value] || 'default'
}

export const equipmentStatusOptions = Object.entries(EQUIPMENT_STATUS_MAP).map(([value, label]) => ({ label, value }))

// ── 优先级 ──
const PRIORITY_MAP = {
  P0: 'P0 紧急',
  P1: 'P1 高',
  P2: 'P2 中',
  P3: 'P3 低',
}

export function priorityLabel(value) {
  return PRIORITY_MAP[value] || value || '-'
}

export function priorityColor(value) {
  const map = { P0: 'red', P1: 'orange', P2: 'blue', P3: 'default' }
  return map[value] || 'default'
}

export const priorityOptions = Object.entries(PRIORITY_MAP).map(([value, label]) => ({ label, value }))

// ── 执行模式 ──
const EXECUTION_MODE_MAP = {
  wet_lab: '湿实验',
  dry_lab: '干实验',
  hybrid: '混合',
  simulation: '模拟计算',
}

export function executionModeLabel(value) {
  return EXECUTION_MODE_MAP[value] || value || '-'
}

export const executionModeOptions = Object.entries(EXECUTION_MODE_MAP).map(([value, label]) => ({ label, value }))

// ── 候选材料来源 ──
const CANDIDATE_SOURCE_MAP = {
  materials_project: 'Materials Project',
  gnome: 'GNoME',
  local_db: '本地数据库',
  internlm_generated: 'AI 生成',
  algorithm_generated: '算法生成',
  mixed: '混合来源',
}

export function candidateSourceLabel(value) {
  return CANDIDATE_SOURCE_MAP[value] || value || '-'
}

// ── 通用：从 Map 生成 options ──
export function optionsFromMap(map) {
  return Object.entries(map).map(([value, label]) => ({ label, value }))
}

// ============================================================
// 统一枚举中文标签映射（v9 全量枚举中文化）
//
// 用法：
//   import { enumLabel, ENUM_LABELS } from '@/utils/enumLabels'
//   <span>{{ enumLabel('materialCategory', record.category) }}</span>
//
// 说明：
// - 此处集中维护全页面英文枚举值 → 中文标签的映射，避免分散在各页面。
// - 上面已有的具体函数（sourceTypeLabel / qcStatusLabel / orderStatusLabel 等）
//   保留向下兼容；新页面优先使用通用 enumLabel() 函数。
// ============================================================

export const ENUM_LABELS = {
  // 物料分类
  materialCategory: {
    BASE_POLYMER: '基材聚合物',
    LITHIUM_SALT: '锂盐',
    FILLER: '填料',
    SOLVENT: '溶剂',
    ADDITIVE: '添加剂',
    ELECTROLYTE: '电解质',
    CATHODE: '正极材料',
    ANODE: '负极材料',
    SEPARATOR: '隔膜',
    CURRENT_COLLECTOR: '集流体',
    BINDER: '粘结剂',
    CONDUCTIVE_AGENT: '导电剂',
  },

  // 设备类别
  equipmentCategory: {
    ELECTROCHEMICAL: '电化学设备',
    CHARACTERIZATION: '表征设备',
    SYNTHESIS: '合成设备',
    TESTING: '测试设备',
    SAFETY: '安全设备',
    ANALYTICAL: '分析设备',
  },

  // 实验状态
  experimentStatus: {
    DRAFT: '草稿',
    PENDING: '待审批',
    APPROVED: '已批准',
    REJECTED: '已拒绝',
    IN_PROGRESS: '进行中',
    COMPLETED: '已完成',
    CANCELLED: '已取消',
  },

  // QC 状态
  qcStatus: {
    PASS: '通过',
    FAIL: '失败',
    PENDING: '待检',
    REQUIRES_REVIEW: '复核中',
    REJECTED: '已拒绝',
  },

  // 候选来源
  candidateSource: {
    AI_GENERATED: 'AI 生成',
    LITERATURE: '文献',
    DATABASE: '数据库',
    EXPERT: '专家',
    HYBRID: '混合',
  },

  // 项目阶段
  projectPhase: {
    INITIATION: '立项',
    PLANNING: '规划',
    EXECUTION: '执行',
    CLOSING: '收尾',
    COMPLETED: '已完成',
  },
}

/**
 * 获取枚举的中文标签（通用入口）
 * @param {string} type - 枚举类型，取值见 ENUM_LABELS 的 key（如 'materialCategory'）
 * @param {string} value - 枚举值（如 'BASE_POLYMER'）
 * @returns {string} 中文标签，未匹配时返回原值；value 为空时返回 '-'
 */
export function enumLabel(type, value) {
  if (value == null || value === '') return '-'
  return ENUM_LABELS[type]?.[value] || value
}
