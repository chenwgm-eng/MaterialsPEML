/**
 * 专业画像（discipline）默认体验工具（Step D）。
 *
 * discipline 只改默认体验（菜单排序/聚焦），决不改变权限过滤或 API 数据范围。
 * 纯函数，便于 node --test 单测（覆盖验收 T2/T3）。
 *
 * 排序规则（对应设计文档 4.D）：
 * - 材料研发 material_research   → 候选材料/预测/ECML
 * - 工艺设计 process_design      → 合成工艺/工艺库/配方编辑
 * - 实验分析 experiment_analysis → 实验任务/数据/QC
 * - 多选取并集加权；primaryDiscipline 命中的模块额外 +1（primary 优先）。
 * - 空画像（disciplines 空或 primary 为空）：权重恒为 0，保持默认顺序 —— 前端消费 primary 必先判空。
 */

// discipline → 优先项目内二级模块的路径前缀（按 startsWith 匹配）
export const DISCIPLINE_PREFERRED_PATHS = {
  material_research: ['/workbench', '/candidates', '/ecml', '/prediction'],
  process_design: ['/synthesis', '/formula-design', '/process', '/formula'],
  experiment_analysis: ['/experiment-workbench', '/experiments', '/data-quality', '/samples', '/data-ingest', '/experiment-dashboard'],
}

/**
 * 计算某 route path 在给定专业画像下的聚焦权重。
 * 空画像 / 无匹配 → 0（保持默认顺序）。primary 命中的画像额外 +1。
 * @param {string} path
 * @param {string[]} [disciplines]
 * @param {string} [primary]
 * @returns {number}
 */
export function disciplineFocusWeight(path, disciplines = [], primary = '') {
  const ds = new Set((disciplines || []).filter(Boolean))
  if (ds.size === 0 || !path) return 0
  let w = 0
  for (const d of ds) {
    const prefs = DISCIPLINE_PREFERRED_PATHS[d] || []
    if (prefs.some((p) => path === p || path.startsWith(p))) {
      w += 1
      if (d === primary) w += 1
    }
  }
  return w
}

/**
 * 按专业画像对菜单 item（含 path）稳定排序：权重降序，同权重保持原顺序。
 * 空画像返回原数组副本（顺序不变）。
 * @param {{path:string}[]} items
 * @param {string[]} [disciplines]
 * @param {string} [primary]
 * @returns {{path:string}[]}
 */
export function sortItemsByDiscipline(items, disciplines = [], primary = '') {
  const copy = (items || []).slice()
  if (!(disciplines || []).some(Boolean)) return copy
  return copy
    .map((it) => ({ it, w: disciplineFocusWeight(it.path, disciplines, primary) }))
    .sort((a, b) => b.w - a.w) // Array.prototype.sort 稳定，同权重保持原顺序
    .map((x) => x.it)
}