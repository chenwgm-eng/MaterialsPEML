/**
 * 统一的颜色常量（供 echarts/inline 样式等无法使用 CSS 变量的场景）。
 *
 * 与 global.css 的语义色保持一致：
 *   - primary: 主色橙 #1d4ed8
 *   - success: 成功绿 #00b42a
 *   - warning: 警告橙 #ff7d00
 *   - error:   错误红 #f53f3f
 *   - info:    信息蓝 #165dff
 *
 * 注意：CSS 中应优先使用 `var(--primary)` 等变量；
 * 仅当 echarts 配置、JS 内联样式等不支持 CSS 变量时才使用本文件常量。
 */

// 主色板（与 global.css 同步）
export const PRIMARY = '#1d4ed8'
export const PRIMARY_HOVER = '#1e40af'
export const PRIMARY_LIGHT = '#3b82f6'
export const PRIMARY_BG_RGBA = 'rgba(249, 115, 22, 0.08)'
export const PRIMARY_BORDER_RGBA = 'rgba(249, 115, 22, 0.3)'

// 语义色
export const SUCCESS = '#00b42a'
export const WARNING = '#ff7d00'
export const ERROR = '#f53f3f'
export const INFO = '#165dff'

// 角色色（与 design-tokens.css --role-* 同步）
export const ROLE_COLORS = {
  project_manager: PRIMARY,
  discovery: SUCCESS,
  synthesis: '#f59e0b',
  dft: '#8b5cf6',
  experiment: '#06b6d4',
  literature: '#ec4899',
  quality: ERROR,
  router: '#64748b',
  custom: '#64748b',
}

// 图表配色序列（主色优先，后续为辅助色）
export const CHART_COLOR_SEQUENCE = [
  PRIMARY,
  '#16a34a',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
  '#64748b',
]

// 渐变区域色（用于 echarts areaStyle）
export const PRIMARY_AREA_GRADIENT = {
  type: 'linear',
  x: 0,
  y: 0,
  x2: 0,
  y2: 1,
  colorStops: [
    { offset: 0, color: 'rgba(249, 115, 22, 0.18)' },
    { offset: 1, color: 'rgba(249, 115, 22, 0.01)' },
  ],
}
