/**
 * 角色相关常量统一定义。
 *
 * 消除 router/index.js 与 composables/useAuth.js 中 ROLE_RANK 重复定义，
 * 以及 MainLayout 中 roleColor/roleLabel 散落映射。
 */

// 角色等级映射（数值越大权限越高）
export const ROLE_RANK = { viewer: 0, researcher: 1, data_engineer: 1, pm: 2, admin: 3 }

// 角色 → antd Tag 颜色
export const ROLE_COLOR_MAP = {
  admin: 'red',
  pm: 'orange',
  researcher: 'blue',
  reviewer: 'purple',
  experimenter: 'cyan',
  data_engineer: 'green',
  viewer: 'default',
}

// 角色 → 中文标签
export const ROLE_LABEL_MAP = {
  admin: '管理员',
  pm: '项目经理(PI)',
  researcher: '科学家',
  reviewer: '审核员',
  experimenter: '实验员',
  data_engineer: '数据工程师',
  viewer: '访客',
}

/**
 * 获取角色对应的 antd Tag 颜色。
 * @param {string} role
 * @returns {string}
 */
export function roleColor(role) {
  return ROLE_COLOR_MAP[role] || 'default'
}

/**
 * 获取角色的中文标签。
 * @param {string} role
 * @returns {string}
 */
export function roleLabel(role) {
  return ROLE_LABEL_MAP[role] || role
}
