// P2-3 数值格式化工具单元测试
// 运行方式：node --test frontend/tests/format.test.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatNumber, formatSci, formatPropValue } from '../src/utils/format.js'

test('formatNumber: 按有效数字截断', () => {
  assert.equal(formatNumber(2.9579000000000004), '2.958')
  assert.equal(formatNumber(0.847293), '0.8473')
  assert.equal(formatNumber(145.326), '145.3')
  assert.equal(formatNumber(123456.789), '123500')
  assert.equal(formatNumber(-0.5), '-0.5')
  assert.equal(formatNumber(0), '0')
})

test('formatNumber: 自定义有效数字位数', () => {
  assert.equal(formatNumber(2.9579, 3), '2.96')
  assert.equal(formatNumber(2.9579, 2), '3')
})

test('formatNumber: 非法输入返回 -', () => {
  assert.equal(formatNumber(null), '-')
  assert.equal(formatNumber(undefined), '-')
  assert.equal(formatNumber(''), '-')
  assert.equal(formatNumber('abc'), '-')
  assert.equal(formatNumber(NaN), '-')
  assert.equal(formatNumber(Infinity), '-')
})

test('formatNumber: 支持数字字符串', () => {
  assert.equal(formatNumber('2.9579000000000004'), '2.958')
})

test('formatSci: 小量级数值转科学计数法（3 位有效数字）', () => {
  assert.equal(formatSci(9.52e-4), '9.52×10⁻⁴')
  assert.equal(formatSci(0.0012), '1.2×10⁻³')
  assert.equal(formatSci(1e-5), '1×10⁻⁵')
  assert.equal(formatSci(-2.4e-7), '-2.4×10⁻⁷')
})

test('formatSci: 大量级数值转科学计数法', () => {
  assert.equal(formatSci(123456), '1.23×10⁵')
  assert.equal(formatSci(10000), '1×10⁴')
})

test('formatSci: 正常范围退化为普通有效数字', () => {
  assert.equal(formatSci(0.01), '0.01')
  assert.equal(formatSci(2.9579000000000004), '2.96')
  // 3 位有效数字下 9999 舍入为 10000，符合有效数字规则
  assert.equal(formatSci(9999), '10000')
  assert.equal(formatSci(0.85), '0.85')
})

test('formatSci: 小于 0.01 走科学计数法（电导率惯例）', () => {
  assert.equal(formatSci(0.001), '1×10⁻³')
  assert.equal(formatSci(0.00987), '9.87×10⁻³')
})

test('formatSci: 尾数进位到 10 时归一化', () => {
  // 9.996e-4 → 尾数四舍五入为 10.0 → 归一化为 1×10⁻³
  assert.equal(formatSci(9.996e-4, 3), '1×10⁻³')
})

test('formatSci: 非法输入返回 -', () => {
  assert.equal(formatSci(null), '-')
  assert.equal(formatSci(''), '-')
  assert.equal(formatSci('xyz'), '-')
  assert.equal(formatSci(0), '0')
})

test('formatPropValue: 电导率类属性走科学计数法', () => {
  assert.equal(formatPropValue(9.52e-4, 'ionic_conductivity'), '9.52×10⁻⁴')
  assert.equal(formatPropValue(9.52e-4, 'predicted_ionic_conductivity'), '9.52×10⁻⁴')
  assert.equal(formatPropValue(9.52e-4, 'ionic_conductivity_estimate'), '9.52×10⁻⁴')
})

test('formatPropValue: 其他属性走 4 位有效数字', () => {
  assert.equal(formatPropValue(2.9579000000000004, 'band_gap'), '2.958')
  assert.equal(formatPropValue(2.9579000000000004), '2.958')
  assert.equal(formatPropValue(-1.23456, 'formation_energy'), '-1.235')
})
