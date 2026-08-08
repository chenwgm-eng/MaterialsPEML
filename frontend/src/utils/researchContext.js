// P3-2：研发工作台 → 派生子任务视图的上下文映射
// 研发工作台是唯一顶层需求录入口；材料发现/性质预测/合成路径/实验闭环迭代
// 作为其派生子任务视图，通过 URL query 接收目标与约束参数，避免重复录入。

import { SCOPE_TO_PREDICTION_TYPE } from '@/constants/materialTypes'

export const RESEARCH_FROM = 'research'

// ECML 闭环迭代 → 下游页面（候选设计/实验工作台）传递推荐候选的 sessionStorage key
export const ECML_RECOMMENDED_TARGET_KEY = 'ecml_recommended_target'
export const ECML_RECOMMENDED_CANDIDATE_KEY = 'ecml_recommended_candidate'

/**
 * 构造派生子任务路由 query。
 * @param {'discovery'|'prediction'|'synthesis'|'ecml'} moduleKey
 * @param {{goal?: string, material_scope?: string, target_properties?: Array, scenario_id?: string}} ctx 工作台表单上下文
 * @returns {Record<string, string>}
 */
export function buildDerivedQuery(moduleKey, ctx = {}) {
  const props = (ctx.target_properties || []).filter((p) => p && p.name)
  const firstProp = props[0]?.name || ''
  const query = { from: RESEARCH_FROM }
  if (ctx.goal) query.goal = ctx.goal
  if (ctx.scenario_id) query.scenario_id = ctx.scenario_id

  if (moduleKey === 'discovery') {
    if (ctx.material_scope) query.material_scope = ctx.material_scope
    if (ctx.material_system) query.material_system = ctx.material_system
    if (firstProp) query.target_property = firstProp
  } else if (moduleKey === 'prediction') {
    query.material_type = SCOPE_TO_PREDICTION_TYPE[ctx.material_scope] || 'crystal'
    if (firstProp) query.target_property = firstProp
  } else if (moduleKey === 'ecml') {
    if (props.length > 1) {
      query.multi_props = props.map((p) => p.name).join(',')
    } else if (firstProp) {
      query.target_property = firstProp
    }
  }
  // synthesis：仅携带 goal（SMILES/化学式由候选产生后走既有 formula/smiles 参数传递）
  return query
}

/**
 * 解析子任务视图中的研发工作台上下文（用于派生横幅展示）。
 * @param {Record<string, unknown>} query 当前路由 query
 * @returns {{isDerived: boolean, goal: string, scenario_id: string}}
 */
export function parseResearchContext(query = {}) {
  return {
    isDerived: query.from === RESEARCH_FROM,
    goal: typeof query.goal === 'string' ? query.goal : '',
    scenario_id: typeof query.scenario_id === 'string' ? query.scenario_id : '',
  }
}
