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

// ── QC 状态（后端大写规范集） ──
const QC_STATUS_MAP = {
  PENDING: '待检查',
  VALID: '有效',
  VALID_WITH_WARNING: '有效(警告)',
  INVALID: '无效',
  REQUIRES_REVIEW: '需审核',
  REJECTED: '已拒绝',
}

export function qcStatusLabel(value) {
  return QC_STATUS_MAP[value] || value || '-'
}

export function qcStatusColor(value) {
  const map = {
    PENDING: 'blue', VALID: 'green', VALID_WITH_WARNING: 'cyan',
    INVALID: 'red', REQUIRES_REVIEW: 'orange', REJECTED: 'red',
  }
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

// ── 通用：从 Map 生成 options ──
export function optionsFromMap(map) {
  return Object.entries(map).map(([value, label]) => ({ label, value }))
}
