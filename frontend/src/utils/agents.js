/**
 * 智能体列表加载与角色文案的共享工具。
 * 供 AgentChip / AgentDetailCard 等组件复用，避免各自重复拉取。
 */
import { listAgents } from '@/api/agents'

// 模块级缓存：同一页面多个智能体组件只拉取一次 agents 列表
// 带 TTL（5 分钟），避免在「智能体管理」编辑后其他页面仍显示旧信息
const AGENTS_CACHE_TTL = 5 * 60 * 1000
let agentsCache = null // { promise, timestamp }

export function loadAgentsOnce() {
  const now = Date.now()
  if (agentsCache && now - agentsCache.timestamp < AGENTS_CACHE_TTL) {
    return agentsCache.promise
  }
  agentsCache = {
    promise: listAgents()
      .then((res) => (Array.isArray(res) ? res : res?.agents || []))
      .catch(() => []),
    timestamp: now,
  }
  return agentsCache.promise
}

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

export function agentRoleLabel(role) {
  return role ? AGENT_ROLE_LABEL[role] || role : ''
}
