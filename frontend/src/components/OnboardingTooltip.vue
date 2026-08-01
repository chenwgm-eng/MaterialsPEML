<template>
  <a-tour
    :open="open"
    :current="current"
    :steps="tourSteps"
    :mask="mask"
    :show-arrow="showArrow"
    :placement="placement"
    @close="onClose"
    @finish="onFinish"
    @change="onChange"
  >
    <template #indicators="{ current: idx, total }">
      <div class="tour-indicators">
        <span>{{ idx + 1 }} / {{ total }}</span>
      </div>
    </template>
    <template v-if="allowDismiss" #closeIcon>
      <CloseOutlined />
    </template>
  </a-tour>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { CloseOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  steps: {
    type: Array,
    required: true,
    // each: { target, title, description, placement?, cover?, mask?, arrow? }
  },
  initialCurrent: { type: Number, default: 0 },
  mask: { type: Boolean, default: false },
  showArrow: { type: Boolean, default: true },
  placement: { type: String, default: 'bottom' },
  allowDismiss: { type: Boolean, default: true },
  storageKey: { type: String, default: 'onboarding_seen' },
})

const emit = defineEmits(['close', 'finish', 'change', 'dismissForever'])

const current = ref(props.initialCurrent)

watch(() => props.open, (val) => {
  if (val) current.value = props.initialCurrent
})

const tourSteps = computed(() =>
  props.steps.map((s) => ({
    // Wrap target in a function so we can safely fall back to body
    // when the selector doesn't resolve (avoids "getBoundingClientRect
    // is not a function" crash from a-tour internals).
    target: () => {
      if (typeof s.target === 'string') {
        return document.querySelector(s.target) || document.body
      }
      if (typeof s.target === 'function') {
        try {
          return s.target() || document.body
        } catch {
          return document.body
        }
      }
      // If it's already an element
      if (s.target && typeof s.target.getBoundingClientRect === 'function') {
        return s.target
      }
      return document.body
    },
    title: s.title,
    description: s.description,
    placement: s.placement || props.placement,
    mask: s.mask ?? props.mask,
    cover: s.cover,
    arrow: s.arrow ?? props.showArrow,
  })),
)

function onClose() {
  emit('close')
}

function onFinish() {
  emit('finish')
}

function onChange(idx) {
  current.value = idx
  emit('change', idx)
}

function dismissForever() {
  try {
    localStorage.setItem(props.storageKey, 'true')
  } catch {
    /* ignore */
  }
  emit('dismissForever')
}

defineExpose({ dismissForever, current })
</script>

<style scoped>
.tour-indicators {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}
</style>
