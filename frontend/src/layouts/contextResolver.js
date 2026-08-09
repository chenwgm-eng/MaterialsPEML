/**
 * ContextColumn 契约解析器（Step C 4.C3）。
 *
 * 把 route.meta.{context, contextEntity, contextMode} 规范化为 ContextColumn 消费的
 * 单一 model，ContextColumn 只消费该 model，不写 `if(route.name===...)`。
 *
 * 映射表（默认态）：
 * | 路由模式 | meta.context | mode | 中栏 | 默认 |
 * |---|---|---|---|---|
 * | 项目工作区 | project | project-overview | 项目定位+新建+任务+动态 | 展开 |
 * | 对象详情 | object | object-detail | 动态(关联对象/状态/操作记录) | 可收起(默认展开) |
 * | 能力库 | capability | capability-nav | 分类/筛选/二级菜单 | 收起或退化 |
 * | 管理页 | admin | admin-nav | 二级菜单/筛选 | 收起或退化 |
 * | 工作台 | workbench | workbench | 全局待办+动态(无项目选择器) | 展开 |
 * | 全局/无上下文 | global | degraded | 仅二级导航 | — |
 */

const CONTEXT_MODEL = {
  project: { mode: 'project-overview', showLocator: true, showTasks: true, showTimeline: true, showMenu: true },
  object: { mode: 'object-detail', showLocator: true, showTasks: false, showTimeline: true, showMenu: true },
  capability: { mode: 'capability-nav', showLocator: false, showTasks: false, showTimeline: false, showMenu: true },
  admin: { mode: 'admin-nav', showLocator: false, showTasks: false, showTimeline: false, showMenu: true },
  workbench: { mode: 'workbench', showLocator: false, showTasks: true, showTimeline: true, showMenu: true },
  global: { mode: 'degraded', showLocator: false, showTasks: false, showTimeline: false, showMenu: true },
}

/**
 * 解析路由上下文。
 * @param {import('vue-router').RouteLocationNormalized} route
 * @returns {{ context:string, mode:string, projectId:string, showLocator:boolean, showTasks:boolean, showTimeline:boolean, showMenu:boolean }}
 */
export function resolveContext(route) {
  const meta = route?.meta || {}
  const context = meta.context || 'global'
  const projectId = String(meta.projectId ?? route?.params?.projectId ?? '')
  const base = CONTEXT_MODEL[context] || CONTEXT_MODEL.global
  return {
    context,
    mode: base.mode,
    projectId,
    showLocator: base.showLocator,
    showTasks: base.showTasks,
    showTimeline: base.showTimeline,
    showMenu: base.showMenu,
  }
}

export const CONTEXT_MODES = Object.freeze(CONTEXT_MODEL)