import { ref, computed } from 'vue'
import { ROLE_RANK } from '@/constants/roles'

// 全局响应式登录态（模块级单例，跨组件共享）
const _userRole = ref(localStorage.getItem('userRole') || 'viewer')
const _userId = ref(localStorage.getItem('userId') || '')
const _isLoggedIn = ref(!!localStorage.getItem('authToken'))

/**
 * 操作-角色映射表（action → 允许的角色列表）。
 *
 * 用于按钮级权限控制（canPerform / v-permission 指令），
 * 与路由级权限（ROLE_RANK）互补，提供更细粒度的操作授权。
 */
export const ACTION_ROLE_MAP = {
  create_project: ['admin', 'pm'],
  delete_project: ['admin'],
  create_experiment: ['admin', 'pm', 'researcher', 'data_engineer'],
  approve_experiment: ['admin', 'pm', 'reviewer'],
  create_candidate: ['admin', 'pm', 'researcher'],
  publish_formula: ['admin', 'pm'],
  manage_agents: ['admin'],
  manage_tools: ['admin'],
  manage_mdm: ['admin', 'data_engineer'],
  view_dashboard: ['admin', 'pm', 'researcher', 'reviewer', 'data_engineer', 'viewer'],
}

/**
 * 判断当前用户是否可执行指定操作。
 * 支持单个操作或操作数组（数组时任意一项通过即视为有权限）。
 * @param {string|string[]} action
 * @returns {boolean}
 */
export function canPerform(action) {
  const actions = Array.isArray(action) ? action : [action]
  return actions.some((a) => {
    const allowed = ACTION_ROLE_MAP[a]
    return allowed ? allowed.includes(_userRole.value) : false
  })
}

/**
 * 统一的登录态管理 composable。
 *
 * 替代各页面散落的 `localStorage.getItem('userRole')` 读取，
 * 提供单一来源的响应式角色/登录状态。
 *
 * 使用方式：
 *   import { useAuth } from '@/composables/useAuth'
 *   const { isAdmin, currentRole, isLoggedIn } = useAuth()
 */
export function useAuth() {
  const currentRole = computed(() => _userRole.value || 'viewer')
  const isAdmin = computed(() => _userRole.value === 'admin')
  const isPmOrAdmin = computed(() => ['admin', 'pm'].includes(_userRole.value))
  const isLoggedIn = computed(() => _isLoggedIn.value)
  const userId = computed(() => _userId.value)

  /** 登录成功后写入登录态（由 MainLayout.onLogin 调用） */
  function setUser({ id, role, token }) {
    if (id) {
      _userId.value = id
      localStorage.setItem('userId', id)
    }
    if (role) {
      _userRole.value = role
      localStorage.setItem('userRole', role)
    }
    if (token) {
      _isLoggedIn.value = true
      localStorage.setItem('authToken', token)
    }
  }

  /** 退出登录时清理（由 MainLayout.onLogout 调用） */
  function clearUser() {
    _userId.value = ''
    _userRole.value = 'viewer'
    _isLoggedIn.value = false
    localStorage.removeItem('userId')
    localStorage.removeItem('userRole')
    localStorage.removeItem('authToken')
  }

  /** 角色等级比较（用于权限判断） */
  function hasRole(minRole) {
    return (ROLE_RANK[_userRole.value] || 0) >= (ROLE_RANK[minRole] || 0)
  }

  return {
    currentRole,
    isAdmin,
    isPmOrAdmin,
    isLoggedIn,
    userId,
    setUser,
    clearUser,
    hasRole,
    canPerform,
  }
}
