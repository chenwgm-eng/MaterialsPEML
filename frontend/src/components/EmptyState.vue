<template>
  <div class="app-empty-state">
    <a-empty>
      <template #image>
        <span class="empty-icon" :class="`empty-icon--${type}`">
          <component :is="iconComponent" />
        </span>
      </template>
      <p class="empty-description">{{ description }}</p>
      <div class="empty-actions" v-if="actionText || secondaryText">
        <a-button v-if="actionText" type="primary" size="small" @click="$emit('action')">
          <component v-if="actionIcon" :is="actionIcon" />
          {{ actionText }}
        </a-button>
        <a-button v-if="secondaryText" size="small" @click="$emit('secondary')">
          {{ secondaryText }}
        </a-button>
      </div>
    </a-empty>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  InboxOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  TeamOutlined,
} from '@ant-design/icons-vue'
import { MESSAGES } from '@/constants/glossary'

/**
 * 统一空状态组件（P1-EMPTY-001）
 *
 * 解决问题：部分空状态缺少下一步行动引导
 *
 * 三种情形（Section 7 规范）：
 * 1. 可创建 — 图标 + 说明 + 主操作按钮（如"新增"）
 * 2. 需先完成前置操作 — 说明前置条件 + 跳转按钮
 * 3. 无权限 — 不应使用此组件，应用 ForbiddenResult
 *
 * 用法：
 *   <EmptyState type="create" description="暂无设备数据" action-text="新增设备" @action="onAdd" />
 *   <EmptyState type="search" description="未找到匹配结果" secondary-text="重置筛选" @secondary="onReset" />
 */
const props = defineProps({
  type: {
    type: String,
    default: 'create',
    validator: (v) => ['create', 'search', 'data', 'team'].includes(v),
  },
  description: { type: String, default: MESSAGES.empty },
  actionText: { type: String, default: '' },
  actionIcon: { type: [Object, Function], default: null },
  secondaryText: { type: String, default: '' },
})

defineEmits(['action', 'secondary'])

const iconMap = {
  create: FolderOpenOutlined,
  search: FileSearchOutlined,
  data: InboxOutlined,
  team: TeamOutlined,
}

const iconComponent = computed(() => props.actionIcon || iconMap[props.type] || ExperimentOutlined)
</script>

<style scoped>
.app-empty-state {
  padding: 40px 16px;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  color: var(--text-muted, #94a3b8);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.empty-icon--create { color: var(--primary); }
.empty-icon--search { color: var(--text-muted, #94a3b8); }
.empty-icon--data { color: var(--text-muted, #94a3b8); }
.empty-icon--team { color: var(--primary); }

.empty-description {
  color: var(--text-secondary, #475569);
  font-size: 14px;
  margin: 12px 0 16px;
}

.empty-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
}
</style>
