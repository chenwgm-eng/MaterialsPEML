/**
 * 内部 Agent 标识符 → 中文名称的集中映射表。
 *
 * 用于将后端返回的 builtin_* / 内部标识符统一转换为用户可读的中文名称，
 * 避免在各组件中散落硬编码文案。与后端 builtin agent 注册保持一致。
 */
export const AGENT_ID_NAME = {
  builtin_material_router: '材料路由调度员',
  builtin_material_discovery: '首席材料学家',
  builtin_industrialization: '配方工艺师',
  builtin_battery_oracle: '电池寿命预言者',
  builtin_dft_verifier: 'DFT 计算专家',
  builtin_experiment_analyst: '实验数据分析员',
  builtin_battery_learner: '电池衰减学习者',
  builtin_synthesis_planner: '合成路径规划师',
  builtin_project_manager: '项目经理',
}

/**
 * 获取内部标识符对应的中文名称；未命中时返回原标识符。
 * @param {string} agentId
 * @returns {string}
 */
export function agentDisplayName(agentId) {
  if (!agentId) return ''
  return AGENT_ID_NAME[agentId] || agentId
}