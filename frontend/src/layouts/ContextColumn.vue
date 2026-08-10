<template>
  <div class="context-column" :class="{ collapsed }">
    <!-- 内容区：项目定位 + 二级菜单（收起时隐藏） -->
    <div v-if="!collapsed" class="context-content">
      <!-- 上半部分：项目定位混合面板（固定）。
           仅「项目」一级入口（项目空间+实验与数据）展示项目/任务选择器与动态；
           工作台/能力库/管理入口不展示（#4） -->
      <template v-if="activeEntry === 'project'">
        <div class="col-top">
          <ProjectLocator :project-id="ctx.projectId" :create-items="createItems" @refresh="onProjectRefresh" />
          <ProjectTaskPanel v-if="ctx.showTasks" :project-id="effectiveProjectId" />
          <ProjectTimeline v-if="ctx.showTimeline" :project-id="effectiveProjectId" />
        </div>
      </template>

      <!-- 下半部分：当前分组二级菜单（独立滚动） -->
      <div v-if="ctx.showMenu" class="col-menu">
        <a-empty v-if="shellGroups.length === 0" :description="'暂无可用菜单'" class="col-menu-empty" />
        <template v-for="g in shellGroups" :key="g.key">
          <!-- 分组标题：图标 + 语义标签 + 细分隔线（非 uppercase 装饰） -->
          <div class="col-group-title">
            <component :is="g.icon" class="col-group-icon" aria-hidden="true" />
            <span>{{ g.title }}</span>
          </div>
          <a-menu :selected-keys="selectedKeys" mode="inline" theme="dark" class="col-menu-list">
            <a-menu-item v-for="item in g.items" :key="item.path" :aria-label="item.title">
              <router-link :to="item.path" class="menu-link">
                <span class="menu-icon"><component :is="item.icon" aria-hidden="true" /></span>
                <span class="menu-text">{{ item.title }}</span>
              </router-link>
            </a-menu-item>
          </a-menu>
        </template>
      </div>
    </div>

    <!-- 右侧边框：缩进/展开按钮（始终可见，紧贴列右侧） -->
    <div
      class="col-rail"
      :title="collapsed ? '展开二级菜单' : '收起二级菜单'"
      role="button"
      tabindex="0"
      aria-label="收起或展开二级菜单"
      @click="$emit('toggle')"
      @keydown.enter.prevent="$emit('toggle')"
    >
      <LeftOutlined v-if="!collapsed" class="rail-icon" />
      <RightOutlined v-else class="rail-icon" />
    </div>
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
  flex-direction: row;
  width: 220px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  height: 100%;
  overflow: hidden;
  transition: width 0.15s ease;
}
.context-column.collapsed {
  width: 16px;
}
.context-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* 右侧缩进/展开按钮：贴合列右侧边框，纵向占满 */
.col-rail {
  flex-shrink: 0;
  width: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-left: 1px solid var(--border);
  background: var(--sidebar-bg);
  color: var(--text-muted);
  transition: color 0.15s ease, background 0.15s ease;
}
.col-rail:hover {
  color: var(--primary, #1d4ed8);
  background: var(--sidebar-hover, rgba(255, 255, 255, 0.04));
}
.col-rail:focus-visible {
  outline: 2px solid var(--primary, #1d4ed8);
  outline-offset: -2px;
}
.rail-icon {
  font-size: 12px;
  line-height: 1;
}
.col-top {
  flex-shrink: 0;
  padding: 0 12px;
  overflow-y: auto;
  max-height: 55%;
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
/* 分组标题：图标 + 标签，去 uppercase/letter-spacing 装饰，带细分隔线 */
.col-group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--sidebar-text);
  font-size: 12px;
  font-weight: 600;
  padding: 14px 4px 8px;
  margin-top: 4px;
  border-bottom: 1px solid var(--sidebar-border);
}
.col-group-title:first-of-type {
  padding-top: 6px;
}
.col-group-icon {
  font-size: 13px;
  color: var(--sidebar-text);
  opacity: 0.85;
}
.col-menu-list {
  background: transparent !important;
  border-right: none;
  padding-top: 2px;
}
.col-menu-list :deep(.ant-menu-item) {
  color: var(--sidebar-text);
  margin: 2px 2px;
  border-radius: var(--radius-md);
  height: 38px;
  line-height: 38px;
  font-size: 13px;
  position: relative;
  transition: background var(--transition-fast), color var(--transition-fast);
}
/* hover：图标与文字同步提亮 */
.col-menu-list :deep(.ant-menu-item:hover) {
  color: var(--text-on-dark) !important;
  background: var(--sidebar-hover) !important;
}
.col-menu-list :deep(.ant-menu-item:hover .menu-icon) {
  color: var(--primary-light) !important;
}
/* 选中：橙色主题 + 左侧强调条（更强的当前页指示） */
.col-menu-list :deep(.ant-menu-item-selected) {
  background: var(--sidebar-active) !important;
  color: var(--sidebar-text-active) !important;
}
.col-menu-list :deep(.ant-menu-item-selected)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  border-radius: 2px;
  background: var(--primary);
}
.col-menu-list :deep(.ant-menu-item-selected .menu-icon) {
  color: var(--primary-light);
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
  color: inherit;
  transition: color var(--transition-fast);
}
.col-menu-list :deep(.menu-text) {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 键盘焦点可见性 */
.col-menu-list :deep(.ant-menu-item:focus-visible) {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}
</style>