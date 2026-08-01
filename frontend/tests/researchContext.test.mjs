// P3-2 研发工作台派生上下文映射单元测试
// 运行方式：node --test frontend/tests/researchContext.test.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  RESEARCH_FROM,
  buildDerivedQuery,
  parseResearchContext,
} from '../src/utils/researchContext.js'

const baseCtx = {
  goal: '找到高离子电导率的固态电解质材料',
  material_scope: 'crystal',
  target_properties: [
    { name: 'ionic_conductivity', direction: 'maximize', min: null, max: null, weight: 0.7 },
  ],
}

test('buildDerivedQuery: discovery 携带材料范围与首个目标属性', () => {
  const q = buildDerivedQuery('discovery', baseCtx)
  assert.equal(q.from, RESEARCH_FROM)
  assert.equal(q.goal, baseCtx.goal)
  assert.equal(q.material_scope, 'crystal')
  assert.equal(q.target_property, 'ionic_conductivity')
})

test('buildDerivedQuery: prediction 将 electrolyte 映射为 polymer 通道', () => {
  const q = buildDerivedQuery('prediction', { ...baseCtx, material_scope: 'electrolyte' })
  assert.equal(q.material_type, 'polymer')
  assert.equal(q.target_property, 'ionic_conductivity')
})

test('buildDerivedQuery: prediction 晶体范围保持 crystal', () => {
  const q = buildDerivedQuery('prediction', baseCtx)
  assert.equal(q.material_type, 'crystal')
})

test('buildDerivedQuery: ecml 单属性用 target_property，多属性用 multi_props', () => {
  const single = buildDerivedQuery('ecml', baseCtx)
  assert.equal(single.target_property, 'ionic_conductivity')
  assert.equal(single.multi_props, undefined)

  const multi = buildDerivedQuery('ecml', {
    ...baseCtx,
    target_properties: [
      { name: 'ionic_conductivity', weight: 0.7 },
      { name: 'band_gap', weight: 0.3 },
    ],
  })
  assert.equal(multi.multi_props, 'ionic_conductivity,band_gap')
  assert.equal(multi.target_property, undefined)
})

test('buildDerivedQuery: synthesis 仅携带 from 与 goal', () => {
  const q = buildDerivedQuery('synthesis', baseCtx)
  assert.deepEqual(q, { from: RESEARCH_FROM, goal: baseCtx.goal })
})

test('buildDerivedQuery: 无目标属性时不产生属性参数', () => {
  const q = buildDerivedQuery('discovery', { goal: 'g', material_scope: 'crystal', target_properties: [] })
  assert.equal(q.target_property, undefined)
  assert.equal(q.material_scope, 'crystal')
})

test('buildDerivedQuery: 过滤无属性名的空行', () => {
  const q = buildDerivedQuery('ecml', {
    goal: 'g',
    target_properties: [{ name: '', weight: 0.5 }, { name: 'band_gap', weight: 0.5 }],
  })
  assert.equal(q.target_property, 'band_gap')
  assert.equal(q.multi_props, undefined)
})

test('buildDerivedQuery: 空 goal 不携带 goal 参数', () => {
  const q = buildDerivedQuery('discovery', { material_scope: 'crystal' })
  assert.equal(q.goal, undefined)
  assert.equal(q.from, RESEARCH_FROM)
})

test('parseResearchContext: 识别研发工作台派生来源', () => {
  const ctx = parseResearchContext({ from: RESEARCH_FROM, goal: '某目标' })
  assert.equal(ctx.isDerived, true)
  assert.equal(ctx.goal, '某目标')
})

test('parseResearchContext: 非派生来源返回 isDerived=false', () => {
  assert.equal(parseResearchContext({}).isDerived, false)
  assert.equal(parseResearchContext({ from: 'discovery' }).isDerived, false)
  assert.equal(parseResearchContext().goal, '')
})

test('parseResearchContext: goal 非字符串时兜底为空串', () => {
  const ctx = parseResearchContext({ from: RESEARCH_FROM, goal: 123 })
  assert.equal(ctx.isDerived, true)
  assert.equal(ctx.goal, '')
})
