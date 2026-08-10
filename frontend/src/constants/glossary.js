/**
 * 统一术语词表与文案规范（T-054）
 *
 * 解决问题：全站文案分散硬编码，同一概念存在多种表述
 * （如「加载中 / 正在加载」、「暂无数据 / 暂时没有数据」、「内部错误 / 操作失败」）。
 *
 * 用法：
 *   import { GLOSSARY, t, MESSAGES, ACTIONS, ENTITY_LABELS } from '@/constants/glossary'
 *   // 1. 通过 key 查询规范文案，未命中时回退
 *   t('loading')              // → '正在加载'
 *   t('not_exist', '默认文案') // → '默认文案'
 *   // 2. 直接使用语义化常量
 *   <a-spin>{{ MESSAGES.loading }}</a-spin>
 *   <EmptyState :description="MESSAGES.empty" />
 *   message.success(MESSAGES.saveSuccess)
 *
 * 与既有层的关系：
 * - utils/enumLabels.js：枚举值（API 返回的英文 code）→ 中文标签，保持不变；
 * - utils/errorHandler.js：HTTP/技术报错转译，仍由其负责，本文件仅提供共享术语；
 * - 本文件维护的是「面向用户的标准文案」，覆盖操作 / 状态 / 数据 / 消息四类。
 */

/**
 * 术语主表：术语键 → 规范中文文案
 *
 * 命名约定：键全部小写下划线，按类别分组注释，便于检索。
 */
export const GLOSSARY = {
  // ── 操作类（actions）──
  save: '保存草稿',
  submit: '提交',
  generate: '智能生成',
  create: '新建',
  delete: '删除',
  edit: '编辑',
  cancel: '取消',
  confirm: '确认',
  retry: '重试',

  // ── 状态类（status）──
  loading: '正在加载',
  empty: '暂无数据',
  error: '操作失败',
  success: '操作成功',
  internal_error: '操作失败', // 内部错误统一对外展示为「操作失败」
  no_data: '暂无相关数据',

  // ── 数据类（entities）──
  result: '实测/预测/模拟结果',
  data: '实验数据',
  candidate: '候选材料',
  formula: '配方',
  sample: '样品',
  experiment: '实验任务单',

  // ── 消息类（messages）──
  load_failed: '加载失败，请重试',
  save_success: '保存成功',
  save_failed: '保存失败',
  delete_confirm: '确认删除？此操作不可撤销',
}

/**
 * 翻译函数：按术语键取规范文案，未命中时返回 fallback。
 * @param {string} key - GLOSSARY 中的术语键
 * @param {string} [fallback=''] - 未命中时的回退文案
 * @returns {string} 规范文案；未命中且未提供 fallback 时返回空串
 */
export function t(key, fallback = '') {
  if (!Object.prototype.hasOwnProperty.call(GLOSSARY, key)) return fallback
  return GLOSSARY[key]
}

/**
 * 常见提示消息（按场景聚合，便于在 message.xxx() 与空状态中复用）。
 * 值全部派生自 GLOSSARY，保证单一数据源。
 */
export const MESSAGES = {
  loading: GLOSSARY.loading,
  empty: GLOSSARY.empty,
  noData: GLOSSARY.no_data,
  error: GLOSSARY.error,
  internalError: GLOSSARY.internal_error,
  success: GLOSSARY.success,
  loadFailed: GLOSSARY.load_failed,
  saveSuccess: GLOSSARY.save_success,
  saveFailed: GLOSSARY.save_failed,
  deleteConfirm: GLOSSARY.delete_confirm,
}

/**
 * 常见操作文案（按钮 / 链接 / 菜单项）。
 */
export const ACTIONS = {
  save: GLOSSARY.save,
  submit: GLOSSARY.submit,
  generate: GLOSSARY.generate,
  create: GLOSSARY.create,
  delete: GLOSSARY.delete,
  edit: GLOSSARY.edit,
  cancel: GLOSSARY.cancel,
  confirm: GLOSSARY.confirm,
  retry: GLOSSARY.retry,
}

/**
 * 实体名称映射（数据类术语，用于表格表头 / 详情页标题 / 空状态描述）。
 */
export const ENTITY_LABELS = {
  result: GLOSSARY.result,
  data: GLOSSARY.data,
  candidate: GLOSSARY.candidate,
  formula: GLOSSARY.formula,
  sample: GLOSSARY.sample,
  experiment: GLOSSARY.experiment,
}
