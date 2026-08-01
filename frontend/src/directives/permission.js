import { canPerform } from '@/composables/useAuth'

/**
 * 按钮级权限控制指令。
 *
 * 用法：
 *   v-permission="'create_project'"
 *   v-permission="['create_project', 'delete_project']"
 *
 * 在元素 mounted 时检查当前用户是否具备给定操作权限；
 * 若无权限则从 DOM 中移除该元素（el.parentNode.removeChild(el)）。
 *
 * 与 v-if="isAdmin" 互补：v-permission 面向细粒度操作授权，
 * 不破坏已有的角色级控制模式。
 */
export const permissionDirective = {
  mounted(el, binding) {
    const value = binding.value
    if (value == null) return
    const actions = Array.isArray(value) ? value : [value]
    const allowed = actions.some((action) => canPerform(action))
    if (!allowed && el.parentNode) {
      el.parentNode.removeChild(el)
    }
  },
}
