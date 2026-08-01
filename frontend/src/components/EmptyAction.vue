<template>
  <div class="empty-action" role="status">
    <div class="empty-action-icon" aria-hidden="true">
      <component :is="iconComponent" />
    </div>
    <h3 class="empty-action-title">{{ title }}</h3>
    <p v-if="description" class="empty-action-desc">{{ description }}</p>
    <a-button
      v-if="actionText"
      type="primary"
      class="empty-action-btn"
      @click="onAction"
    >
      {{ actionText }}
    </a-button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { InboxOutlined } from '@ant-design/icons-vue'
import { MESSAGES } from '@/constants/glossary'

const props = defineProps({
  title: { type: String, default: MESSAGES.empty },
  description: { type: String, default: '' },
  actionText: { type: String, default: '' },
  icon: { type: [Object, Function], default: () => InboxOutlined },
})

const emit = defineEmits(['action'])

const iconComponent = computed(() => props.icon)

function onAction() {
  emit('action')
}
</script>

<style scoped>
.empty-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-4xl) var(--space-lg);
  text-align: center;
  background: var(--light-bg-card);
  border: 1px dashed var(--border);
  border-radius: var(--radius-xl);
}

.empty-action-icon {
  font-size: 48px;
  color: var(--text-muted);
  opacity: 0.5;
  margin-bottom: var(--space-md);
}

.empty-action-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--space-xs);
}

.empty-action-desc {
  font-size: var(--font-size-md);
  color: var(--text-muted);
  line-height: 1.6;
  max-width: 360px;
  margin: 0 0 var(--space-lg);
}

.empty-action-btn {
  border-radius: var(--radius-pill);
  height: 40px;
  padding: 0 24px;
}
</style>
