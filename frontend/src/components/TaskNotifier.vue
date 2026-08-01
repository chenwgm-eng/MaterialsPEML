<template>
  <div v-if="visible" class="task-notifier">
    <!-- 折叠态：徽章 -->
    <div v-if="!expanded" class="notifier-badge" @click="expanded = true">
      <a-badge :count="taskStore.activeCount" :offset="[6, 0]">
        <div class="badge-inner">
          <SyncOutlined v-if="taskStore.activeCount > 0" spin />
          <CheckCircleOutlined v-else />
        </div>
      </a-badge>
    </div>
    <!-- 展开态：任务列表 -->
    <div v-else class="notifier-panel">
      <div class="panel-header">
        <span class="panel-title">后台任务</span>
        <a-button type="text" size="small" @click="expanded = false">
          <CloseOutlined />
        </a-button>
      </div>
      <div class="panel-body">
        <div v-if="taskStore.tasks.length === 0" class="empty-tip">
          暂无任务记录
        </div>
        <div
          v-for="task in taskStore.tasks"
          :key="task.id"
          class="task-item"
          :class="`task-${task.status}`"
        >
          <div class="task-row">
            <span class="task-name">{{ task.name }}</span>
            <a-tag :color="statusColor(task.status)" size="small">{{ statusLabel(task.status) }}</a-tag>
          </div>
          <a-progress
            v-if="task.status === 'running'"
            :percent="task.progress"
            size="small"
            :show-info="false"
            :stroke-color="'var(--primary)'"
          />
          <div v-if="task.detail" class="task-detail">{{ task.detail }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { SyncOutlined, CheckCircleOutlined, CloseOutlined } from '@ant-design/icons-vue'
import { useTaskStore } from '@/stores/tasks'

const taskStore = useTaskStore()
const expanded = ref(false)

// 有任务时才显示
const visible = computed(() => taskStore.tasks.length > 0)

function statusColor(status) {
  if (status === 'running') return 'processing'
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  return 'default'
}

function statusLabel(status) {
  if (status === 'running') return '进行中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  return status
}
</script>

<style scoped>
.task-notifier {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 1000;
}

.notifier-badge {
  cursor: pointer;
}

.badge-inner {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--primary);
  transition: transform var(--transition);
}

.badge-inner:hover {
  transform: scale(1.05);
}

.notifier-panel {
  width: 320px;
  max-height: 400px;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-hover);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}

.empty-tip {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px 0;
}

.task-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.task-item:last-child {
  border-bottom: none;
}

.task-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.task-name {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.task-detail {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.task-completed .task-name {
  color: var(--text-muted);
}

.task-failed .task-name {
  color: var(--error);
}
</style>
