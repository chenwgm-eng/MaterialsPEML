import { ref, watch, onUnmounted } from 'vue'

/**
 * 加载超时 composable（T-044）
 *
 * 监听一个 loading ref：当 loading 变为 true 时启动计时器，
 * 超过 delay 毫秒后若仍处于 loading，则将 showProgress 置为 true，
 * 用于在骨架屏上展示「进度说明 + 取消按钮」。
 *
 * @param {import('vue').Ref<boolean>} loadingRef 响应式加载状态
 * @param {number} [delay=2000] 触发进度说明的延迟毫秒数
 * @returns {{ showProgress: import('vue').Ref<boolean>, cancel: () => void }}
 *
 * 用法：
 *   const loading = ref(false)
 *   const { showProgress, cancel } = useLoadingTimeout(loading, 2000)
 */
export function useLoadingTimeout(loadingRef, delay = 2000) {
  const showProgress = ref(false)
  let timer = null

  function clearTimer() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  function reset() {
    clearTimer()
    showProgress.value = false
  }

  watch(
    loadingRef,
    (loading) => {
      if (loading) {
        // 重新进入 loading：清理旧计时器后再启动
        clearTimer()
        showProgress.value = false
        timer = setTimeout(() => {
          // 计时器触发时再确认一次 loading 状态，避免被取消后仍触发
          if (loadingRef.value) {
            showProgress.value = true
          }
        }, delay)
      } else {
        reset()
      }
    },
    { immediate: true },
  )

  function cancel() {
    reset()
  }

  onUnmounted(() => {
    clearTimer()
  })

  return { showProgress, cancel }
}
