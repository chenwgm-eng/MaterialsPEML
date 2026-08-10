<template>
  <ErrorResult v-if="error" :details="details" @retry="retry" />
  <slot v-else />
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'
import ErrorResult from '@/components/ErrorResult.vue'

// 路由内容错误边界：页面组件渲染抛错时显示可见错误态（而非空白），
// 并提供重试入口；MainLayout 以 :key 绑定路由路径，路由切换自动重置。
const error = ref(null)
const details = ref([])

onErrorCaptured((err, instance, info) => {
  error.value = err
  details.value = [String(err?.message || err).slice(0, 200)]
  // 阻止继续向上冒泡（避免控制台重复告警由全局 handler 兜底）
  return false
})

function retry() {
  error.value = null
  details.value = []
  window.location.reload()
}
</script>
