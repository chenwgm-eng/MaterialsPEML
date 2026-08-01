<template>
  <a-tooltip
    :title="disabled ? disabledReason : ''"
    :mouse-enter-delay="0.3"
  >
    <span class="disabled-btn-wrap" :class="{ 'is-disabled': disabled }">
      <a-button
        v-bind="$attrs"
        :disabled="disabled"
        :loading="loading"
        @click="onClick"
      >
        <template v-for="name in slotNames" :key="name" #[name]="slotData">
          <slot :name="name" v-bind="slotData || {}" />
        </template>
      </a-button>
    </span>
  </a-tooltip>
</template>

<script setup>
/**
 * 禁用按钮统一组件（P1-TTIP-001）
 *
 * 解决问题：多处禁用按钮无 tooltip 说明禁用原因；修复 null key 渲染错误（BPEML-UI-P1-001）
 *
 * 用法：
 *   <DisabledButton :disabled="!selected" disabled-reason="请先选择一行数据" @click="onEdit">
 *     <EditOutlined /> 编辑
 *   </DisabledButton>
 *
 * 当 disabled=true 时，悬停按钮显示 disabledReason 说明；
 * 当 disabled=false 时，tooltip 不显示，按钮正常可点击。
 */
import { useSlots, computed } from 'vue'

const slots = useSlots()

// 过滤掉值为 null/undefined 的 slot，避免 v-for 遍历时触发 "Cannot read properties of null (reading 'key')"
const slotNames = computed(() =>
  Object.keys(slots).filter((k) => slots[k] != null)
)

const props = defineProps({
  disabled: { type: Boolean, default: false },
  disabledReason: { type: String, default: '当前操作不可用' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['click'])

function onClick(e) {
  if (!props.disabled && !props.loading) {
    emit('click', e)
  }
}
</script>

<style scoped>
.disabled-btn-wrap {
  display: inline-block;
}

.disabled-btn-wrap.is-disabled {
  cursor: not-allowed;
}

/* 禁用态按钮统一视觉规范（审查意见0726） */
.disabled-btn-wrap.is-disabled :deep(.ant-btn[disabled]) {
  background: #f5f5f5;
  border-color: #d9d9d9;
  color: #bfbfbf;
  cursor: not-allowed;
}

.disabled-btn-wrap.is-disabled :deep(.ant-btn-primary[disabled]) {
  background: #f5f5f5;
  border-color: #d9d9d9;
  color: #bfbfbf;
}
</style>
