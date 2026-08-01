<template>
  <div class="approval-card">
    <div class="approval-header">
      <span class="order-id">{{ order.order_id }}</span>
      <a-tag color="orange" size="small">{{ order.priority }}</a-tag>
    </div>
    <div class="approval-body">
      <div class="approval-info">
        <span v-if="order.project_id">项目：{{ order.project_id }}</span>
        <span v-if="order.assignee">负责人：{{ order.assignee}}</span>
      </div>
    </div>
    <div class="approval-actions">
      <a-button type="primary" size="small" :aria-label="`通过任务 ${order.order_id}`" @click="$emit('approve', order)">通过</a-button>
      <a-button danger size="small" :aria-label="`拒绝任务 ${order.order_id}`" @click="$emit('reject', order)">拒绝</a-button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  order: { type: Object, required: true },
})
defineEmits(['approve', 'reject'])
</script>

<style scoped>
.approval-card {
  border: 1px solid var(--light-border, #e8e8e8);
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafafa;
}
.approval-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.order-id {
  font-weight: 600;
  font-size: 13px;
}
.approval-info {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted, #999);
  margin-bottom: 8px;
}
.approval-actions {
  display: flex;
  gap: 8px;
}
</style>
