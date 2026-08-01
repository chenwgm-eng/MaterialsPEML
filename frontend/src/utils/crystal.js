/**
 * 晶体结构共享工具：元素配色、化学式解析、空间群→晶系推断。
 * 供 CrystalCellSvg / StructureView 等结构渲染组件统一使用。
 */

// 常用元素配色（CPK 风格，适配浅色背景）
const ELEMENT_COLORS = {
  Li: '#7ed321', Na: '#a06ee1', K: '#c77dff', Mg: '#8fb400', Ca: '#6a9a00',
  O: '#e5484d', S: '#e3b505', F: '#90c860', Cl: '#52b788', Br: '#a1612c', I: '#7d3c98',
  P: '#f58518', N: '#4c8dff', C: '#5c6670', H: '#b0b7bf',
  Fe: '#b5651d', Co: '#3d6fb4', Ni: '#7f8c8d', Mn: '#9b59b6', Cu: '#c87533',
  Zn: '#7a8b99', Ti: '#9aa7b2', Zr: '#45b8ac', La: '#1abc9c', Ge: '#8e9eab',
  In: '#b19cd9', Al: '#8fa6b8', Si: '#d4a017', Sn: '#9aa5ad', V: '#e67e22',
  Nb: '#16a085', Mo: '#5dade2', W: '#616a6b', Ta: '#48c9b0',
}

const DEFAULT_ATOM_COLOR = '#8a8f98'

export function elementColor(el) {
  return ELEMENT_COLORS[el] || DEFAULT_ATOM_COLOR
}

// 解析化学式为去重后的元素列表，如 Li3PS4 → ['Li', 'P', 'S']
export function parseFormula(formula) {
  if (!formula || typeof formula !== 'string') return []
  const out = []
  const re = /([A-Z][a-z]?)/g
  let m
  while ((m = re.exec(formula)) !== null) out.push(m[1])
  return [...new Set(out)]
}

/**
 * 由 Hermann–Mauguin 空间群符号推断晶系。
 * 判定顺序：菱方(R) → 六方(P6) → 三方(P3/P-3) → 四方(P4/I4) → 立方(含3) → 单斜 → 正交。
 */
export function detectCrystalSystem(spaceGroup) {
  if (!spaceGroup || typeof spaceGroup !== 'string') return 'cubic'
  const s = spaceGroup.trim()
  if (!s) return 'cubic'
  if (/^R/.test(s)) return 'trigonal'
  if (/^P-?6/.test(s)) return 'hexagonal'
  if (/^P-?3/.test(s)) return 'trigonal'
  if (/^[PI]-?4/.test(s)) return 'tetragonal'
  if (s.slice(1).includes('3')) return 'cubic'
  const rest = s.slice(1)
  // 单斜：仅含单一二次轴/镜面方向（如 2/m、21/m、2、m、c）
  if (/^(21?|m|c|a|n)(\/.*)?$/i.test(rest)) return 'monoclinic'
  if (rest.length <= 2 || rest.includes('/')) return 'monoclinic'
  return 'orthorhombic'
}

// 由空间群符号首字母推断布拉维点阵居中方式（P/I/F/C/A/B/R）
export function detectLatticeCentering(spaceGroup) {
  if (!spaceGroup || typeof spaceGroup !== 'string') return 'P'
  const c = spaceGroup.trim().charAt(0).toUpperCase()
  return 'PIFCABR'.includes(c) ? c : 'P'
}

export const CRYSTAL_SYSTEM_LABELS = {
  cubic: '立方晶系',
  tetragonal: '四方晶系',
  orthorhombic: '正交晶系',
  monoclinic: '单斜晶系',
  trigonal: '三方晶系',
  hexagonal: '六方晶系',
}
