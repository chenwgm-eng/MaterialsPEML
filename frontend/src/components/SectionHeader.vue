<template>
  <div class="section-header">
    <div class="section-header-text">
      <h2 class="section-header-title">{{ title }}</h2>
      <p v-if="subtitle" class="section-header-subtitle">{{ subtitle }}</p>
    </div>
    <a-button
      v-if="actionText"
      type="primary"
      class="section-header-btn"
      @click="onAction"
    >
      {{ actionText }}
    </a-button>
    <slot name="extra" />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  actionText: { type: String, default: '' },
})

const emit = defineEmits(['action'])

function onAction() {
  emit('action')
}
</script>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.section-header-text {
  min-width: 0;
}

.section-header-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin: 0;
  line-height: 1.25;
}

.section-header-subtitle {
  font-size: var(--font-size-md);
  color: var(--text-secondary);
  margin: var(--space-xs) 0 0;
  line-height: 1.5;
}

.section-header-btn {
  border-radius: var(--radius-pill);
  height: 36px;
  padding: 0 18px;
  flex-shrink: 0;
}

@media (max-width: 699px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .section-header-btn {
    width: 100%;
  }
}
</style>
