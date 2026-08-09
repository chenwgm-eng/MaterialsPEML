// Step D 专业画像聚焦排序单元测试
// 覆盖验收 T2（切换 primary → 默认体验变化）与 T3（空画像 → 保持默认顺序、不崩溃）。
// 运行方式：node --test frontend/tests/discipline.test.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  DISCIPLINE_PREFERRED_PATHS,
  disciplineFocusWeight,
  sortItemsByDiscipline,
} from '../src/utils/discipline.js'

// 项目空间二级模块（与 menuConfig.js 一致）
const projectItems = [
  { path: '/projects', title: '项目管理' },
  { path: '/workbench', title: '材料设计' },
  { path: '/synthesis', title: '合成路径' },
  { path: '/formula-design', title: '配方与工艺' },
  { path: '/ecml', title: '实验闭环迭代' },
]

test('D: 空画像（disciplines 空 / primary 空）权重为 0', () => {
  assert.equal(disciplineFocusWeight('/workbench', [], ''), 0)
  assert.equal(disciplineFocusWeight('/workbench', undefined, undefined), 0)
  assert.equal(disciplineFocusWeight('', ['material_research'], 'material_research'), 0)
})

test('D: 材料研发主画像优先材料设计/ECML', () => {
  const sorted = sortItemsByDiscipline(projectItems, ['material_research'], 'material_research').map((i) => i.path)
  assert.deepEqual(sorted.slice(0, 2), ['/workbench', '/ecml'])
  // 材料设计权重最高（primary 命中 +1）
  assert.equal(disciplineFocusWeight('/workbench', ['material_research'], 'material_research'), 2)
  assert.equal(disciplineFocusWeight('/ecml', ['material_research'], 'material_research'), 2)
  assert.equal(disciplineFocusWeight('/synthesis', ['material_research'], 'material_research'), 0)
})

test('D: 工艺设计主画像优先合成路径/配方与工艺', () => {
  const sorted = sortItemsByDiscipline(projectItems, ['process_design'], 'process_design').map((i) => i.path)
  assert.deepEqual(sorted.slice(0, 2), ['/synthesis', '/formula-design'])
  assert.equal(disciplineFocusWeight('/synthesis', ['process_design'], 'process_design'), 2)
})

test('D: 实验分析主画像优先实验数据/看板', () => {
  const sorted = sortItemsByDiscipline(
    [
      { path: '/experiment-workbench' },
      { path: '/experiments' },
      { path: '/data-quality' },
      { path: '/projects' },
    ],
    ['experiment_analysis'],
    'experiment_analysis',
  ).map((i) => i.path)
  assert.deepEqual(sorted.slice(0, 3), ['/experiment-workbench', '/experiments', '/data-quality'])
})

test('D: 多画像并集加权，primary 优先', () => {
  // 材料研发 + 工艺设计，primary=process_design
  const wWorkbench = disciplineFocusWeight('/workbench', ['material_research', 'process_design'], 'process_design')
  const wSynthesis = disciplineFocusWeight('/synthesis', ['material_research', 'process_design'], 'process_design')
  // process 命中 synthesis（primary +1）权重 2；workbench 仅被 material 命中（非 primary）权重 1
  assert.equal(wSynthesis, 2)
  assert.equal(wWorkbench, 1)
  const sorted = sortItemsByDiscipline(projectItems, ['material_research', 'process_design'], 'process_design').map((i) => i.path)
  assert.equal(sorted[0], '/synthesis')
})

test('D: 命中路径按前缀匹配（/workbench 与 /workbench/xxx 均算）', () => {
  assert.equal(disciplineFocusWeight('/workbench/123', ['material_research'], 'material_research'), 2)
  assert.equal(disciplineFocusWeight('/experiments/abc', ['experiment_analysis'], 'experiment_analysis'), 2)
})

test('D: 空画像排序保持原顺序（T3 落点稳定、不崩溃）', () => {
  const sorted = sortItemsByDiscipline(projectItems, [], '').map((i) => i.path)
  assert.deepEqual(sorted, projectItems.map((i) => i.path))
  const sortedUndef = sortItemsByDiscipline(projectItems).map((i) => i.path)
  assert.deepEqual(sortedUndef, projectItems.map((i) => i.path))
})

test('D: 无匹配项保持相对顺序（稳定排序）', () => {
  // 全部无匹配 → 顺序不变
  const paths = sortItemsByDiscipline(projectItems, ['material_research'], 'material_research').map((i) => i.path)
  // synthesis 在原数组中位于 workbench 之后，即便不匹配也在匹配项之后
  assert.ok(paths.indexOf('/synthesis') < paths.indexOf('/formula-design'))
})

test('D: DISCIPLINE_PREFERRED_PATHS 三个画像均有定义', () => {
  for (const d of ['material_research', 'process_design', 'experiment_analysis']) {
    assert.ok(Array.isArray(DISCIPLINE_PREFERRED_PATHS[d]) && DISCIPLINE_PREFERRED_PATHS[d].length > 0)
  }
})