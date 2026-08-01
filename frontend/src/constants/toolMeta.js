/**
 * 工具 / SCP / 能力契约 相关共享元数据与显示映射
 * 这些常量被 ToolsHub、TopologyView 等视图共用，避免重复硬编码。
 */

// 能力级 SCP 绑定的中文显示名（ToolsHub「能力绑定」层使用）
export const CAPABILITY_LABELS = {
  scp_molecule_descriptors: '分子描述符计算',
  scp_toxicity_assessment: '毒性 / ADMET 评估',
  scp_literature_search: '化合物 / 文献检索',
  scp_protocol_draft: '实验协议草案生成',
  scp_material_transform: '材料结构转换',
}

// server_id → 数据源显示名（用于 ToolsHub「能力绑定」表格）
export const SERVER_SOURCE_LABELS = {
  '': 'LLM 内部',
  '8': 'Origene-PubChem',
  '4': 'Origene-ChEMBL',
  '31': 'SciToolAgent-Chem',
  '30': 'SciToolAgent-Mat',
  '40': 'SciGraph-Material',
  '24': '化学反应计算',
  '20': '材料力学分析',
  '27': '物理量与单位换算',
  '26': '数据处理与统计分析',
  '28': 'InternAgent',
  '37': 'SciGraph',
}

export function capabilityLabel(name) {
  return CAPABILITY_LABELS[name] || name
}

export function sourceLabel(serverId) {
  return SERVER_SOURCE_LABELS[serverId ?? ''] || `Server ${serverId}`
}

export function riskLevelColor(level) {
  const map = { A: 'success', B: 'blue', C: 'warning', D: 'error' }
  return map[level] || 'default'
}

export function availabilityColor(avail) {
  const map = {
    enabled: 'green',
    disabled: 'default',
    unhealthy: 'red',
    always: 'green',
    conditional: 'orange',
  }
  return map[avail] || 'default'
}

export function availabilityLabel(avail) {
  const map = {
    enabled: '可用',
    disabled: '禁用',
    unhealthy: '异常',
    always: '可用',
    conditional: '条件可用',
  }
  return map[avail] || avail || '—'
}

export function testStateColor(state) {
  const map = { testing: 'processing', passed: 'success', failed: 'error' }
  return map[state] || 'default'
}

export function testStateLabel(state) {
  const map = { testing: '检测中', passed: '可用', failed: '不可用' }
  return map[state] || '—'
}
