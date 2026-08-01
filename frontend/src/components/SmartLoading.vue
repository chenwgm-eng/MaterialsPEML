<template>
  <div class="smart-loading">
    <template v-if="loading">
      <LoadingSkeleton :type="skeletonType" />
      <!-- 超过 2s 显示进度说明与取消按钮 -->
      <div v-if="showProgress" class="smart-loading-progress">
        <span v-if="tip" class="smart-loading-tip">{{ tip }}</span>
        <a-button v-if="showCancel" size="small" @click="onCancel">取消</a-button>
      </div>
    </template>
    <!-- loading 为 false 时透传默认插槽内容（可选） -->
    <slot v-else />
  </div>
</template>

<script setup>
import { toRef } from 'vue'
import LoadingSkeleton from './LoadingSkeleton.vue'
import { useLoadingTimeout } from '@/composables/useLoadingTimeout'

/**
 * 智能加载组件（T-044）
 *
 * 行为：
 * - loading 为 true 时显示骨架屏（委托 LoadingSkeleton）
 * - 加载超过 2s 显示进度说明（tip）和取消按钮（showCancel）
 * - 取消按钮点击触发 cancel 事件
 * - loading 为 false 时透传默认插槽内容（可选）
 *
 * 用法一（外部 v-if 控制 mount，最贴近原 SkeletonLoader 用法）：
 *   <SmartLoading v-if="loading" :loading="true" tip="..." show-cancel @cancel="..." />
 *   <RealContent v-else />
 *
 * 用法二（内部 loading 控制显隐 + 默认插槽）：
 *   <SmartLoading :loading="loading" tip="..." show-cancel @cancel="...">
 *     <RealContent />
 *   </SmartLoading>
 */
const props = defineProps({
  loading: { type: Boolean, default: false },
  tip: { type: String, default: '' },
  showCancel: { type: Boolean, default: false },
  skeletonType: {
    type: String,
    default: 'list',
    validator: (v) => ['table', 'card', 'list', 'detail'].includes(v),
  },
})

const emit = defineEmits(['cancel'])

// 复用 useLoadingTimeout：内部使用 setTimeout + onUnmounted 清理定时器
const loadingRef = toRef(props, 'loading')
const { showProgress, cancel } = useLoadingTimeout(loadingRef, 2000)

function onCancel() {
  cancel()
  emit('cancel')
}
</script>

<style scoped>
.smart-loading {
  width: 100%;
}

.smart-loading-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-light, #f0f0f0);
}

.smart-loading-tip {
  font-size: 13px;
  color: var(--text-secondary, #595959);
}
</style>
