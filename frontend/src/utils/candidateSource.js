// ============================================================
// 候选来源标签统一映射（Task 16）
// 后端 source_type 规范集：
//   materials_project / gnome / local_db / internlm_generated /
//   algorithm_generated / mixed
// 兼容历史 raw source 值（gnome_mp_mirror / local_database / internlm / ...）
// ============================================================

// 原始 source → 规范 source_type 映射（与后端 _SOURCE_TYPE_MAP 对齐）
const SOURCE_TYPE_MAP = {
  // Materials Project
  materials_project: 'materials_project',
  mp: 'materials_project',
  // GNoME（MP 镜像或本地静态数据集）
  gnome: 'gnome',
  gnome_mp_mirror: 'gnome',
  gnome_local: 'gnome',
  // 本地数据库 / 已知库
  local_db: 'local_db',
  local_database: 'local_db',
  local_db_fallback: 'local_db',
  local: 'local_db',
  known: 'local_db',
  // InternLM LLM 生成
  internlm: 'internlm_generated',
  internlm_generated: 'internlm_generated',
  llm_generated: 'internlm_generated',
  // 算法生成
  algorithm_generated: 'algorithm_generated',
  rule_based: 'algorithm_generated',
  derivative: 'algorithm_generated',
  demo: 'algorithm_generated',
}

// 规范 source_type → { 颜色, 中文标签 } 徽章配置
const SOURCE_BADGE_MAP = {
  materials_project: { color: 'blue', label: 'MP' },
  gnome: { color: 'purple', label: 'GNoME' },
  local_db: { color: 'green', label: '本地' },
  internlm_generated: { color: 'orange', label: 'AI' },
  algorithm_generated: { color: 'default', label: '算法' },
  mixed: { color: 'cyan', label: '混合' },
}

const DEFAULT_BADGE = { color: 'default', label: '未知' }

/**
 * 将候选的 raw source / source_type 字段归一为规范 source_type。
 * 优先读取 candidate.source_type，回退到 candidate.source。
 * 多来源（provenance 中存在多种 source）归为 'mixed'。
 * @param {object} candidate
 * @returns {string}
 */
export function normalizeSourceType(candidate) {
  if (!candidate || typeof candidate !== 'object') return 'algorithm_generated'

  // 1. 优先用顶层 source_type（后端 Task 16 已写入）
  const topType = candidate.source_type
  if (topType && SOURCE_TYPE_MAP[topType] === topType) return topType

  // 2. 收集 source / source_type / provenance 中的所有来源
  const sources = new Set()
  const rawSource = candidate.source || ''
  if (rawSource) sources.add(SOURCE_TYPE_MAP[rawSource] || 'algorithm_generated')
  if (topType) sources.add(SOURCE_TYPE_MAP[topType] || topType)

  const provenance = candidate.provenance || []
  if (Array.isArray(provenance)) {
    for (const p of provenance) {
      if (!p || typeof p !== 'object') continue
      const s = p.source_type || p.source || ''
      if (s) sources.add(SOURCE_TYPE_MAP[s] || 'algorithm_generated')
    }
  }

  if (sources.size === 0) return 'algorithm_generated'
  if (sources.size > 1) return 'mixed'
  return Array.from(sources)[0]
}

/**
 * 获取来源徽章配置（颜色 + 中文标签）。
 * @param {object} candidate
 * @returns {{ color: string, label: string }}
 */
export function getSourceBadge(candidate) {
  const type = normalizeSourceType(candidate)
  return SOURCE_BADGE_MAP[type] || DEFAULT_BADGE
}
