// ============================================================
// 数值格式化工具（P2-3）
// 统一数值精度截断，避免 2.9579000000000004 这类原始浮点直接展示，
// 配合 .tabular-nums / .num-cell 等宽数字样式保证多行数据视觉对齐。
// ============================================================

const SUPERSCRIPT_MAP = {
  '-': '⁻',
  0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴',
  5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹',
}

function toSuperscript(expStr) {
  return String(expStr)
    .split('')
    .map((ch) => SUPERSCRIPT_MAP[ch] || ch)
    .join('')
}

/**
 * 按有效数字截断数值。
 * 例：formatNumber(2.9579000000000004) → '2.958'
 * @param {number|string} value
 * @param {number} [sigDigits=4] 有效数字位数
 * @returns {string} 非法输入返回 '-'
 */
export function formatNumber(value, sigDigits = 4) {
  if (value == null || value === '') return '-'
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  if (n === 0) return '0'
  return String(parseFloat(n.toPrecision(sigDigits)))
}

/**
 * 科学计数法格式化（离子电导率等小量级数值）：
 *   formatSci(9.52e-4) → '9.52×10⁻⁴'
 * 正常范围 [1e-2, 1e4) 退化为普通有效数字，避免过度科学计数法。
 * @param {number|string} value
 * @param {number} [sigDigits=3] 有效数字位数
 * @returns {string}
 */
export function formatSci(value, sigDigits = 3) {
  if (value == null || value === '') return '-'
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  if (n === 0) return '0'
  const abs = Math.abs(n)
  // 正常范围 [1e-2, 1e4) 直接展示；小于 0.01 按电导率惯例走科学计数法
  if (abs >= 1e-2 && abs < 1e4) return formatNumber(n, sigDigits)
  const exp = Math.floor(Math.log10(abs))
  let m = Number((n / Math.pow(10, exp)).toPrecision(sigDigits))
  let e = exp
  // 尾数四舍五入后可能进位到 10（如 9.996 → 10.0），需归一化
  if (Math.abs(m) >= 10) {
    m = m / 10
    e = e + 1
  }
  return `${m}×10${toSuperscript(e)}`
}

// 小量级物理量属性 key：按科学计数法展示（3 位有效数字）
const SCI_KEYS = new Set([
  'ionic_conductivity',
  'ionic_conductivity_estimate',
  'predicted_ionic_conductivity',
  'electronic_conductivity',
  'diffusion_coefficient',
  'conductivity',
])

/**
 * 属性感知的数值格式化：
 * - 电导率等小量级属性 → 科学计数法（3 位有效数字）
 * - 其余数值 → 4 位有效数字截断
 * @param {number|string} value
 * @param {string} [key] 属性英文 key
 * @returns {string}
 */
export function formatPropValue(value, key) {
  if (key && SCI_KEYS.has(key)) return formatSci(value, 3)
  return formatNumber(value, 4)
}
