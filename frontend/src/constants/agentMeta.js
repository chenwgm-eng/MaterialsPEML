/**
 * Agent 角色相关常量统一定义。
 *
 * 消除 AgentCard.vue 与 AgentLogPanel.vue 中 ROLE_COLOR / ROLE_LABEL 重复定义，
 * 保证两处展示一致。颜色值与 global.css 中 --role-* 变量保持同步。
 */

// 角色 → 显示颜色（与 global.css --role-* 变量对应）
export const AGENT_ROLE_COLOR = {
  project_manager: '#1d4ed8',
  material_discovery: '#10b981',
  synthesis_planning: '#f59e0b',
  dft_verification: '#8b5cf6',
  experiment_analysis: '#06b6d4',
  literature_research: '#ec4899',
  quality_review: '#ef4444',
  custom: '#6b7280',
}

// 角色 → 中文标签
export const AGENT_ROLE_LABEL = {
  project_manager: '项目经理',
  material_discovery: '材料发现',
  synthesis_planning: '合成规划',
  dft_verification: 'DFT 验证',
  experiment_analysis: '实验分析',
  literature_research: '文献调研',
  quality_review: '质量审核',
  custom: '自定义',
}

// 兜底色（未知 agent / 无 agent_id）
export const AGENT_FALLBACK_COLOR = '#86909c'

/**
 * 获取角色对应的显示颜色。
 * @param {string} role
 * @returns {string}
 */
export function agentRoleColor(role) {
  return AGENT_ROLE_COLOR[role] || AGENT_ROLE_COLOR.custom
}

/**
 * 获取角色的中文标签。
 * @param {string} role
 * @returns {string}
 */
export function agentRoleLabel(role) {
  return AGENT_ROLE_LABEL[role] || AGENT_ROLE_LABEL.custom
}
