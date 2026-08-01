<template>
  <span class="animated-number">{{ displayValue }}</span>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'

const props = defineProps({
  value: { type: [Number, String], default: 0 },
  duration: { type: Number, default: 800 },
  decimals: { type: Number, default: 0 },
})

const displayValue = ref(0)

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function animate(to) {
  if (prefersReducedMotion()) {
    displayValue.value = Number(to.toFixed(props.decimals))
    return
  }

  const from = displayValue.value
  const start = performance.now()
  const diff = to - from

  function step(now) {
    const elapsed = now - start
    const progress = Math.min(elapsed / props.duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3)
    displayValue.value = Number((from + diff * eased).toFixed(props.decimals))
    if (progress < 1) requestAnimationFrame(step)
  }

  requestAnimationFrame(step)
}

watch(() => props.value, (v) => {
  const num = Number(v) || 0
  animate(num)
}, { immediate: true })

onMounted(() => {
  const num = Number(props.value) || 0
  animate(num)
})
</script>

<style scoped>
.animated-number {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}
</style>
