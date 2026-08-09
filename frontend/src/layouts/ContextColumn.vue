<template>
  <div class="context-column" :class="{ collapsed }">
    <!-- 折叠控制条 -->
    <div class="col-toggle" @click="$emit('toggle')">
      <a-button v-if="collapsed" type="text" size="small" class="toggle-btn" title="展开">
        <RightOutlined />
      </a-button>
      <a-button v-else type="text" size="small" class="toggle-btn" title="收起">
        <LeftOutlined />
      </a-button>
    </div>

    <template v-if="!collapsed">
      <!-- 上半部分：项目定位混合面板（固定） -->
      <div class="col-top">
        <ProjectLocator v-if="ctx.showLocator" :project-id="ctx.projectId" :create-items="createItems" @refresh="onProjectRefresh" />
        <ProjectTaskPanel v-if="ctx.showTasks" :project-id="effectiveProjectId" />
        <ProjectTimeline v-if="ctx.showTimeline" :project-id="effectiveProjectId" />
      </div>

      <!-- 上下分割与任务展开符号 -->
      <div class="col-divider" />

      <!-- 下半部分：当前分组二级菜单（独立滚动） -->
      <div v-if="ctx.showMenu" class="col-menu">
        <a-empty v-if="shellGroups.length === 0" :description="'暂无可用菜单'" class="col-menu-empty" />
        <template v-for="g in shellGroups" :key="g.key">
          <div class="col-group-title">{{ g.title }}</div>
          <a-menu :selected-keys="selectedKeys" mode="inline" theme="dark" class="col-menu-list">
            <a-menu-item v-for="item in g.items" :key="item.path">
              <router-link :to="item.path" class="menu-link">
                <span class="menu-icon"><component :is="item.icon" /></span>
                <span class="menu-text">{{ item.title }}</span>
              </router-link>
            </a-menu-item>
          </a-menu>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { LeftOutlined, RightOutlined } from '@ant-design/icons-vue'
import { resolveContext } from './contextResolver'
import ProjectLocator from './ProjectLocator.vue'
import ProjectTaskPanel from './ProjectTaskPanel.vue'
import ProjectTimeline from './ProjectTimeline.vue'

const props = defineProps({
  activeEntry: String,
  shellGroups: { type: Array, default: () => [] },
  selectedKeys: { type: Array, default: () => [] },
  collapsed: { type: Boolean, default: false },
  createItems: { type: Array, default: () => [] },
})

const emit = defineEmits(['toggle', 'refresh'])

const route = useRoute()

// 仅消费 contextResolver 规范化后的 model，不写 if(route.name===...)
const ctx = computed(() => resolveContext(route.value))

// 项目上下文：优先路由 projectId，否则取全局当前项目
const effectiveProjectId = computed(() => ctx.value.projectId || '')

function onProjectRefresh() {
  emit('refresh')
}
</script>

<style scoped>
.context-column {
  display: flex;
  flex-direction: column;
  width: 260px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  height: 100%;
  overflow: hidden;
}
.context-column.collapsed {
  width: 24px;
}
.col-toggle {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  border-bottom: 1px solid var(--border);
}
.toggle-btn {
  color: var(--text-muted);
}
.col-top {
  flex-shrink: 0;
  padding: 0 12px;
  overflow-y: auto;
  max-height: 55%;
}
.col-divider {
  flex-shrink: 0;
  height: 1px;
  background: var(--border);
  margin: 4px 12px;
}
.col-menu {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 12px 16px;
}
.col-menu-empty {
  margin-top: 24px;
  color: var(--sidebar-text) !important;
}
.col-group-title {
  color: var(--sidebar-text);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 12px 4px 4px;
}
.col-menu-list {
  background: transparent !important;
  border-right: none;
}
.col-menu-list :deep(.ant-menu-item) {
  color: var(--sidebar-text);
  margin: 2px 4px;
  border-radius: var(--radius-md);
  height: 36px;
  line-height: 36px;
  font-size: 13px;
}
.col-menu-list :deep(.ant-menu-item:hover) {
  color: var(--text-on-dark) !important;
  background: var(--sidebar-hover) !important;
}
.col-menu-list :deep(.ant-menu-item-selected) {
  background: var(--sidebar-active) !important;
  color: var(--sidebar-text-active) !important;
}
.col-menu-list :deep(.ant-menu-item .menu-link) {
  display: flex;
  align-items: center;
  gap: 10px;
  color: inherit;
  text-decoration: none;
  width: 100%;
  height: 100%;
}
.col-menu-list :deep(.menu-icon) {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  font-size: 14px;
  width: 18px;
}
.col-menu-list :deep(.menu-text) {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>