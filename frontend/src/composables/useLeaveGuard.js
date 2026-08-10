/**
 * 表单离开保护（三栏方案 T15）：
 * 页面有未保存修改时，路由离开弹确认、刷新/关闭拦截。
 * 用法：
 *   const { markDirty, markClean, isDirty } = useLeaveGuard()
 *   - 表单输入变化时 markDirty()；保存成功后 markClean()
 *   - 组件内无需再写 onBeforeRouteLeave —— composable 内部已注册
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { Modal } from 'ant-design-vue'

export function useLeaveGuard() {
  const dirty = ref(false)

  function markDirty() {
    dirty.value = true
  }

  function markClean() {
    dirty.value = false
  }

  function confirmLeave() {
    return new Promise((resolve) => {
      Modal.confirm({
        title: '有未保存的修改',
        content: '离开当前页面将丢失未保存的内容，确定继续吗？',
        okText: '离开',
        cancelText: '留在本页',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  }

  // 路由离开拦截（Suspense/懒加载场景下 onBeforeRouteLeave 同样生效）
  onBeforeRouteLeave(async () => {
    if (!dirty.value) return true
    return await confirmLeave()
  })

  // 刷新/关闭标签页拦截
  function beforeUnloadHandler(e) {
    if (!dirty.value) return
    e.preventDefault()
    e.returnValue = ''
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnloadHandler))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnloadHandler))

  return { markDirty, markClean, isDirty: dirty }
}
