<template>
  <a class="skip-link" href="#main-content">跳转到主内容</a>
  <a-layout class="main-layout">
    <a-layout-sider
      v-if="!navShellEnabled"
      v-model:collapsed="collapsed"
      collapsible
      :width="220"
      :collapsed-width="64"
      theme="dark"
      class="sidebar"
    >
      <div class="logo" :class="{ 'logo-collapsed': collapsed }">
        <div class="logo-icon">
          <svg viewBox="0 0 32 32" width="24" height="24" aria-hidden="true">
            <defs>
              <linearGradient id="logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="var(--primary)" />
                <stop offset="100%" stop-color="var(--primary-light)" />
              </linearGradient>
            </defs>
            <rect width="32" height="32" rx="6" fill="url(#logo-grad)" />
            <path d="M8 22V10h2v10h6v2H8z" fill="white" opacity="0.95" />
            <circle cx="22" cy="16" r="3.5" fill="none" stroke="white" stroke-width="1.5" />
            <path d="M22 13v6M19 16h6" stroke="white" stroke-width="1.2" />
          </svg>
        </div>
        <span v-if="!collapsed" class="logo-text">MaterialsPEML</span>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        v-model:open-keys="openKeys"
        mode="inline"
        theme="dark"
        class="sidebar-menu"
        @openChange="onMenuOpenChange"
      >
        <template v-for="group in menuGroups">
          <!-- 单项分组直接渲染为一级菜单项，无需展开二级 -->
          <a-menu-item
            v-if="group.items && group.items.length === 1"
            :key="group.items[0].path"
          >
            <router-link :to="group.items[0].path" class="menu-link">
              <span class="menu-icon"><component :is="group.icon" /></span>
              <span class="menu-text">{{ group.items[0].title }}</span>
            </router-link>
          </a-menu-item>
          <a-sub-menu v-else :key="group.title" class="menu-group">
            <template #icon>
              <component :is="group.icon" />
            </template>
            <template #title>
              <span v-if="!collapsed">{{ group.title }}</span>
            </template>
            <!-- 次级分组：将配置/管理类内容折叠进次级分组，减少一级平铺项 -->
            <template v-if="group.subGroups">
              <a-menu-item-group
                v-for="sub in group.subGroups"
                :key="sub.title"
                :title="sub.title"
              >
                <a-menu-item
                  v-for="item in sub.items"
                  :key="item.path"
                >
                  <router-link :to="item.path" class="menu-link">
                    <span class="menu-icon"><component :is="item.icon" /></span>
                    <span class="menu-text">{{ item.title }}</span>
                  </router-link>
                </a-menu-item>
              </a-menu-item-group>
            </template>
            <template v-else>
              <a-menu-item
                v-for="item in group.items"
                :key="item.path"
              >
                <router-link :to="item.path" class="menu-link">
                  <span class="menu-icon"><component :is="item.icon" /></span>
                  <span class="menu-text">{{ item.title }}</span>
                </router-link>
              </a-menu-item>
            </template>
          </a-sub-menu>
        </template>
      </a-menu>
      <div class="sidebar-footer">
        <div class="role-badge" v-if="!collapsed">
          <UserOutlined />
          <span class="role-badge-name">{{ currentUser ? (currentUser.display_name || currentUser.username) : '未登录' }}</span>
          <a-tag :color="roleColor(currentRole)" class="role-badge-tag">{{ roleLabel(currentRole) }}</a-tag>
        </div>
        <div class="health-indicator" :class="healthClass" :title="healthText">
          <span class="health-dot"></span>
          <span v-if="!collapsed" class="health-text">{{ healthText }}</span>
        </div>
      </div>
    </a-layout-sider>

    <!-- Step B：稳定导航壳层（IconRail 64px + 一级入口联动分组）。VITE_FF_NAV_SHELL=true 时启用 -->
    <div v-else class="nav-shell">
      <IconRail
        :active-entry="activeEntry"
        :entries="stableNavEntries"
        :user="currentUser"
        :health-text="healthText"
        :health-class="healthClass"
        @select="onEntrySelect"
      />
      <!-- Step C：项目中心中栏（ContextColumn 260px，VITE_FF_PROJECT_CENTER=true 时启用） -->
      <ContextColumn
        v-if="projectCenterEnabled"
        :active-entry="activeEntry"
        :shell-groups="shellGroups"
        :selected-keys="selectedKeys"
        :collapsed="contextCollapsed"
        :create-items="createMenuItems"
        @toggle="contextCollapsed = !contextCollapsed"
        @refresh="onContextRefresh"
      />
      <div v-else class="nav-groups">
        <a-empty v-if="shellGroups.length === 0" :description="'暂无可用菜单'" class="nav-groups-empty" />
        <template v-for="g in shellGroups" :key="g.key">
          <div class="shell-group-title">{{ g.title }}</div>
          <a-menu
            :selected-keys="selectedKeys"
            mode="inline"
            theme="dark"
            class="shell-menu"
          >
            <a-menu-item v-for="item in g.items" :key="item.path">
              <router-link :to="item.path" class="menu-link">
                <span class="menu-icon"><component :is="item.icon" /></span>
                <span class="menu-text">{{ item.title }}</span>
              </router-link>
            </a-menu-item>
          </a-menu>
        </template>
      </div>
    </div>

    <a-layout>
      <a-layout-header class="top-header">
        <div class="header-left">
          <!-- Step E：navShell 开启时精简 Header（新建入口由 ContextColumn 提供），隐藏旧 Header 残留 -->
          <a-dropdown v-if="!navShellEnabled" placement="bottomLeft" trigger="click">
            <a-tooltip title="快速发起研发任务">
              <a-button type="primary" size="small" @click.stop>
                <PlusOutlined /> 新建 <DownOutlined />
              </a-button>
            </a-tooltip>
            <template #overlay>
              <a-menu @click="onCreateMenuClick">
                <a-menu-item-group key="g1" title="研发任务">
                  <a-menu-item
                    v-for="item in createMenuItems"
                    :key="item.path"
                  >
                    <component :is="item.icon" /> {{ item.label }}
                  </a-menu-item>
                </a-menu-item-group>
              </a-menu>
            </template>
          </a-dropdown>
          <span class="page-label">{{ currentPageTitle }}</span>
        </div>
        <div class="header-right">
          <a-dropdown v-if="!navShellEnabled" placement="bottomRight" trigger="click">
            <a-tooltip title="最近的闭环迭代运行记录，点击可跳转查看">
              <a-button size="small" :loading="recentLoading" @click.stop>
                <ClockCircleOutlined /> 最近 <DownOutlined />
              </a-button>
            </a-tooltip>
            <template #overlay>
              <a-menu class="recent-menu">
                <a-menu-item-group key="rg" title="闭环迭代运行记录">
                  <a-menu-item v-if="recentLoading" key="loading" disabled>
                    <a-spin size="small" /> {{ MESSAGES.loading }}…
                  </a-menu-item>
                  <template v-else>
                    <a-menu-item v-if="recentRuns.length === 0" key="empty" disabled>
                      暂无最近运行
                    </a-menu-item>
                    <a-menu-item
                      v-for="run in recentRuns"
                      :key="run.run_id"
                    >
                      <router-link :to="{ path: '/ecml', query: { run_id: run.run_id } }" class="recent-run-link">
                        <div class="recent-run-item">
                          <span class="recent-run-target">{{ run.target || '-' }}</span>
                          <span class="recent-run-meta">迭代 {{ run.iteration || 0 }}</span>
                        </div>
                      </router-link>
                    </a-menu-item>
                  </template>
                </a-menu-item-group>
              </a-menu>
            </template>
          </a-dropdown>
          <!-- T-048：双主题切换 -->
          <ThemeToggle />
          <!-- 用户登录区域 -->
          <a-dropdown v-if="currentUser" placement="bottomRight" trigger="click">
            <a-button size="small" type="text" class="user-btn">
              <UserOutlined />
              <span class="user-name-text">{{ currentUser.display_name || currentUser.username }}</span>
              <a-tag :color="roleColor(currentUser.role)" class="role-tag">{{ roleLabel(currentUser.role) }}</a-tag>
            </a-button>
            <template #overlay>
              <a-menu @click="onUserMenuClick">
                <a-menu-item v-if="currentUser.role === 'admin'" key="users">
                  <TeamOutlined /> 用户管理
                </a-menu-item>
                <!-- Step D：专业视角切换（只改默认体验，不改权限） -->
                <a-sub-menu key="perspective" title="专业视角">
                  <a-menu-item v-for="d in DISCIPLINE_OPTIONS" :key="`persp:${d.value}`">
                    <CheckOutlined v-if="systemStore.primaryDiscipline === d.value" class="persp-check" />
                    <span :class="{ 'persp-muted': systemStore.primaryDiscipline && systemStore.primaryDiscipline !== d.value }">{{ d.label }}</span>
                  </a-menu-item>
                  <a-menu-item key="persp:clear">
                    <span :class="{ 'persp-muted': systemStore.primaryDiscipline }">通用（关闭聚焦）</span>
                  </a-menu-item>
                </a-sub-menu>
                <a-menu-item key="logout"><LogoutOutlined /> 退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <a-button v-else size="small" type="primary" @click="goLogin">
            <LoginOutlined /> 登录
          </a-button>
        </div>
      </a-layout-header>

      <a-layout-content id="main-content" class="main-content" tabindex="-1">
        <!-- 路由内容错误边界：按路由重置，页面渲染异常时显示可见错误态而非空白 -->
        <RouteBoundary :key="route.path">
          <!-- 不使用 transition mode="out-in"，避免真实浏览器过渡事件未触发时新页面永不挂载（内容区空白） -->
          <router-view v-slot="{ Component }">
            <suspense>
              <component :is="Component" />
              <template #fallback>
                <div class="route-loading">
                  <a-spin size="large" />
                  <span class="route-loading-text">{{ MESSAGES.loading }}…</span>
                </div>
              </template>
            </suspense>
          </router-view>
        </RouteBoundary>
      </a-layout-content>
    </a-layout>

    <!-- 全局任务通知浮层 -->
    <TaskNotifier />

  </a-layout>
</template>

<script setup>
import { ref, computed, watch, onMounted, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSystemStore } from '@/stores/system'
import { useProjectContextStore } from '@/stores/projectContext'
import { getEcmlRuns } from '@/api/ecml'
import { getCurrentUser, logout as authLogout } from '@/api/auth'
import { setUserId, getUserId } from '@/api/client'
import { useAuth } from '@/composables/useAuth'
import { roleColor, roleLabel } from '@/constants/roles'
import { message } from 'ant-design-vue'
import TaskNotifier from '@/components/TaskNotifier.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import RouteBoundary from '@/components/base/RouteBoundary.vue'
import IconRail from '@/layouts/IconRail.vue'
import ContextColumn from '@/layouts/ContextColumn.vue'
import { STABLE_ENTRIES, MENU_GROUPS, ENTRY_TO_GROUP_KEYS } from '@/layouts/menuConfig'
import { sortItemsByDiscipline } from '@/utils/discipline'
import { track } from '@/utils/telemetry'
import { DISCIPLINE_OPTIONS } from '@/constants/roles'
import { updateMyDisciplines } from '@/api/auth'
import {
  DashboardOutlined,
  ProjectOutlined,
  ExperimentOutlined,
  SyncOutlined,
  DatabaseOutlined,
  SettingOutlined,
  RobotOutlined,
  LineChartOutlined,
  PlusOutlined,
  DownOutlined,
  ClockCircleOutlined,
  ShopOutlined,
  FormOutlined,
  SearchOutlined,
  ApartmentOutlined,
  BookOutlined,
  ShareAltOutlined,
  ToolOutlined,
  InboxOutlined,
  UserOutlined,
  LoginOutlined,
  LogoutOutlined,
  AppstoreOutlined,
  ControlOutlined,
  WalletOutlined,
  SafetyOutlined,
  ProfileOutlined,
  TeamOutlined,
  SafetyCertificateOutlined,
  AccountBookOutlined,
  ImportOutlined,
  ApiOutlined,
  HomeOutlined,
  BellOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  CheckOutlined,
} from '@ant-design/icons-vue'
import { MESSAGES } from '@/constants/glossary'

const route = useRoute()
const router = useRouter()
const systemStore = useSystemStore()
const projectStore = useProjectContextStore()

const collapsed = ref(false)
const selectedKeys = ref([route.path])
const openKeys = ref([])

// Step B：稳定导航壳层特性开关（VITE_FF_NAV_SHELL=true 时启用）
const navShellEnabled = import.meta.env.VITE_FF_NAV_SHELL === 'true'
// Step C：项目中心中栏特性开关（VITE_FF_PROJECT_CENTER=true 时启用）
const projectCenterEnabled = import.meta.env.VITE_FF_PROJECT_CENTER === 'true'
const contextCollapsed = ref(false)
const activeEntry = ref('workbench')

// 当前路径 → 所属稳定入口 key
function pathToEntry(path) {
  const g = MENU_GROUPS.find(
    (gr) =>
      gr.items?.some((i) => i.path === path) ||
      gr.subGroups?.some((s) => s.items.some((i) => i.path === path)),
  )
  return g ? g.entryKey : 'workbench'
}

// IconRail 可点入口：满足权限下限 ∧ 未被 nav_visibility 隐藏
const stableNavEntries = computed(() => {
  const perms = systemStore.permissions
  const visible = systemStore.visibleEntries
  return STABLE_ENTRIES.filter(
    (e) =>
      (!e.requiredAnyPermission?.length || e.requiredAnyPermission.some((p) => perms.includes(p))) &&
      visible.includes(e.key),
  )
})

// 当前选中入口下的分组（按权限点过滤 + 专业画像聚焦排序）
const shellGroups = computed(() => {
  const perms = systemStore.permissions
  const visible = systemStore.visibleEntries
  return MENU_GROUPS.filter(
    (g) => g.entryKey === activeEntry.value && visible.includes(g.entryKey),
  )
    .map((g) => {
      const items = g.subGroups ? g.subGroups.flatMap((s) => s.items) : g.items
      const filtered = items.filter(
        (it) => !it.requiredAnyPermission?.length || it.requiredAnyPermission.some((p) => perms.includes(p)),
      )
      // Step D：专业画像聚焦排序（只改默认顺序，空画像/无匹配保持原顺序，不改权限过滤）
      const sorted = sortItemsByDiscipline(filtered, systemStore.disciplines, systemStore.primaryDiscipline)
      return { ...g, items: sorted }
    })
    .filter((g) => g.items.length > 0)
})

// 入口默认页（图标点击且当前页不属于该入口时跳转，保证点击导航后右侧始终有内容）
const ENTRY_DEFAULT_PATH = {
  workbench: '/',
  project: '/projects',
  capability: '/research',
  admin: '/dashboard',
}

// 指定路径是否属于某稳定入口下的分组
function pathBelongsToEntry(entryKey, path) {
  const gkeys = ENTRY_TO_GROUP_KEYS[entryKey] || []
  return gkeys.some((gkey) => {
    const g = MENU_GROUPS.find((x) => x.key === gkey)
    if (!g) return false
    if (g.subGroups) return g.subGroups.some((s) => s.items.some((i) => i.path === path))
    return g.items.some((i) => i.path === path)
  })
}

function onEntrySelect(key) {
  activeEntry.value = key
  track('entry_select', { entry: key })
  // 当前页面不属于该入口时，导航到入口默认页（避免仅切换中栏、右侧无变化）
  if (!pathBelongsToEntry(key, route.path)) {
    const target = ENTRY_DEFAULT_PATH[key]
    if (target && target !== route.path) {
      router.push(target)
    }
  }
}

// 根据当前路由同步菜单高亮与展开分组
function syncMenuState() {
  const path = route.path
  selectedKeys.value = [path]
  // P1-3：同一 path 若出现在多个分组，优先保留当前已展开的分组，
  // 避免点击后分组被强制切换
  const matchedGroups = menuGroups.value.filter((g) => collectPaths(g).includes(path))
  const stayOpen = matchedGroups.find((g) => openKeys.value.includes(g.title))
  const matchedGroup = stayOpen || matchedGroups[0]
  // 仅对多项分组（有 sub-menu）设置 openKeys，单项分组无 sub-menu 无需展开
  if (matchedGroup && (matchedGroup.items?.length > 1 || matchedGroup.subGroups?.length > 0)) {
    openKeys.value = [matchedGroup.title]
  } else {
    // 单项分组或未匹配到分组时，折叠所有 sub-menu，避免残留展开状态
    openKeys.value = []
  }
}

// --- 用户登录状态 ---
// 统一使用 useAuth composable 管理登录态，避免与 localStorage 直接操作形成两份并行状态源。
const { currentRole, isPmOrAdmin: isAdminRole, setUser, clearUser } = useAuth()
// currentUser 仅承载展示用信息（display_name 等），role 一律从 useAuth 读取。
const currentUser = ref(null)  // { user_id, username, display_name, role, ... }

// 登录已迁移到独立登录页 /login，此处仅保留跳转入口
function goLogin() {
  router.push({ path: '/login', query: route.fullPath !== '/' ? { redirect: route.fullPath } : {} })
}

// 角色对应的菜单可见性规则（8.1 菜单重组后）：
// admin / viewer: 全部可见
// pm: 除「用户管理」「系统设置」外全部可见
// researcher: 我的研发 + 项目空间 + 实验与数据 + 知识资产 + AI 与编排（部分）
// reviewer: 仅我的研发、实验与数据相关、数据质量
// experimenter: 我的研发 + 实验与数据（待执行任务、样品、设备、数据录入）
function isMenuVisible(path, role) {
  if (role === 'admin' || role === 'viewer') return true
  // 8.1：管理菜单对研发人员完全隐藏（按权限收敛）
  // 我的研发/项目空间/实验与数据/知识资产/AI 与编排 对 pm/researcher 可见
  const adminOnly = [
    '/dashboard', '/control-plane', '/budgets', '/value-report',
    '/tools', '/topology', '/orchestration', '/mappings',
    '/capability-center', '/users', '/settings',
  ]
  if (adminOnly.includes(path)) return false
  if (role === 'reviewer') {
    // reviewer：聚焦实验与样品、数据质量、我的待办
    return [
      '/', '/my-tasks',
      '/experiment-workbench', '/experiments', '/samples', '/equipment',
      '/data-ingest', '/data-quality',
    ].includes(path)
  }
  if (role === 'experimenter') {
    // 实验员：聚焦实验执行、样品、设备、数据录入与质量
    return [
      '/', '/my-tasks',
      '/experiment-workbench', '/experiments', '/samples', '/equipment',
      '/data-ingest', '/data-quality',
      '/projects',
    ].includes(path)
  }
  // researcher/pm: 研发工作区全部可见，平台管理后台不可见（adminOnly 已过滤）
  return true
}

async function onLogout() {
  // 调用后端 logout 端点以记录审计日志；无状态鉴权下失败不影响本地清理
  try {
    await authLogout()
  } catch {
    // 后端不可达时仍允许本地注销
  }
  setUserId(null)
  clearUser()
  currentUser.value = null
  track('logout')
  message.success('已退出登录')
  // 退出后统一回登录页（路由守卫也会兜底拦截未登录访问）
  router.push('/login')
}

function onUserMenuClick({ key }) {
  if (key === 'logout') {
    onLogout()
  } else if (key === 'users') {
    router.push('/users')
  } else if (key.startsWith('persp:')) {
    switchPrimaryDiscipline(key.slice('persp:'.length))
  }
}

// Step D：切换专业视角（只改默认体验，不改权限）。
// 持久化到后端（保证 primary ∈ disciplines 不变量），成功后刷新本地画像与聚焦排序。
async function switchPrimaryDiscipline(disc) {
  const ds = systemStore.disciplines || []
  const nextPrimary = disc === 'clear' ? '' : disc
  const nextDs = nextPrimary && !ds.includes(nextPrimary) ? [...ds, nextPrimary] : ds
  try {
    await updateMyDisciplines({ disciplines: nextDs, primary_discipline: nextPrimary })
    await systemStore.fetchMe()
    const label = nextPrimary ? (DISCIPLINE_OPTIONS.find((o) => o.value === nextPrimary)?.label || nextPrimary) : '通用'
    track('discipline_switch', { discipline: nextPrimary })
    message.success(`专业视角已切换为「${label}」`)
  } catch {
    message.error('切换专业视角失败')
  }
}

function onMenuOpenChange(keys) {
  // 手风琴模式：只保留最后展开的一个分组
  openKeys.value = keys.length ? [keys[keys.length - 1]] : []
}

async function restoreSession() {
  const userId = getUserId()
  if (!userId) return
  try {
    const data = await getCurrentUser()
    currentUser.value = data
    setUser({ id: data.user_id, role: data.role, token: null })
    // 恢复会话时同步权限点与导航可见入口
    await systemStore.fetchMe()
    activeEntry.value = pathToEntry(route.path)
  } catch {
    // 会话失效（用户被禁用/删除），清理本地状态
    setUserId(null)
    clearUser()
  }
}

const menuGroups = computed(() => {
  const role = currentRole.value
  const admin = isAdminRole.value
  // 8.1 菜单重组：6 个一级菜单
  // 1. 我的研发 — 首页、我的待办
  // 2. 项目空间 — 以项目空间串联候选/预测/合成/配方/迭代
  // 3. 实验与数据 — 按实验执行对象组织
  // 4. 知识资产 — 统一知识资产入口
  // 5. AI 与编排 — 研发工作台、智能体、工具与映射
  // 6. 管理 — 低频或平台/商业化能力，按权限收敛
  const groups = [
    // ── 1. 我的研发（所有角色默认首页）──
    {
      title: '我的研发',
      icon: markRaw(HomeOutlined),
      zone: 'research',
      items: [
        { path: '/', title: '首页', icon: markRaw(HomeOutlined) },
        { path: '/my-tasks', title: '我的待办', icon: markRaw(BellOutlined) },
      ],
    },
    // ── 2. 项目空间（收敛为 5 项：项目管理/材料设计/合成路径/配方与工艺/实验闭环迭代）──
    {
      title: '项目空间',
      icon: markRaw(ProjectOutlined),
      zone: 'research',
      items: [
        { path: '/projects', title: '项目管理', icon: markRaw(ProjectOutlined) },
        { path: '/workbench', title: '材料设计', icon: markRaw(ExperimentOutlined) },
        { path: '/synthesis', title: '合成路径', icon: markRaw(ShareAltOutlined) },
        { path: '/formula-design', title: '配方与工艺', icon: markRaw(ExperimentOutlined) },
        { path: '/ecml', title: '实验闭环迭代', icon: markRaw(SyncOutlined) },
      ],
    },
    // ── 3. 实验与数据（按实验执行对象组织；设备/接入/质量折叠进「数据管理」次级分组）──
    {
      title: '实验与数据',
      icon: markRaw(FormOutlined),
      zone: 'research',
      subGroups: [
        {
          title: '实验执行',
          items: [
            { path: '/experiment-dashboard', title: '实验数据看板', icon: markRaw(DashboardOutlined) },
            { path: '/experiment-workbench', title: '实验工作台', icon: markRaw(FormOutlined) },
            { path: '/experiments', title: '实验数据', icon: markRaw(DatabaseOutlined) },
            { path: '/samples', title: '样品与批次', icon: markRaw(InboxOutlined) },
          ],
        },
        {
          title: '数据管理',
          items: [
            { path: '/equipment', title: '设备与校准', icon: markRaw(ToolOutlined) },
            { path: '/data-ingest', title: '数据接入', icon: markRaw(ImportOutlined) },
            { path: '/data-quality', title: '数据质量', icon: markRaw(SafetyCertificateOutlined) },
          ],
        },
      ],
    },
    // ── 4. 知识资产（统一知识资产入口）──
    {
      title: '知识资产',
      icon: markRaw(DatabaseOutlined),
      zone: 'research',
      items: [
        { path: '/technology-intelligence', title: '技术情报', icon: markRaw(BookOutlined) },
        { path: '/knowledge-graph', title: '知识图谱', icon: markRaw(ShareAltOutlined) },
        { path: '/materials', title: '物料规格库', icon: markRaw(ShopOutlined) },
        { path: '/properties', title: '属性字典', icon: markRaw(ProfileOutlined) },
        { path: '/mdm', title: '主数据治理', icon: markRaw(DatabaseOutlined) },
      ],
    },
    // ── 5. AI 与编排（研发/编排 + 智能体/工具/能力契约 折叠进次级分组）──
    {
      title: 'AI 与编排',
      icon: markRaw(RobotOutlined),
      zone: 'research',
      subGroups: [
        {
          title: '研发与编排',
          items: [
            { path: '/research', title: '研发工作台', icon: markRaw(ExperimentOutlined) },
            { path: '/orchestration', title: '智能编排', icon: markRaw(RobotOutlined) },
            { path: '/eval-center', title: '评估中心', icon: markRaw(ExperimentOutlined) },
          ],
        },
        {
          title: '智能体与工具',
          items: [
            { path: '/agents', title: '智能体管理', icon: markRaw(RobotOutlined) },
            { path: '/tools', title: '工具与连接器', icon: markRaw(AppstoreOutlined) },
            { path: '/mappings', title: '映射控制台', icon: markRaw(DeploymentUnitOutlined) },
            { path: '/capability-center', title: '能力契约', icon: markRaw(ApiOutlined) },
          ],
        },
      ],
    },
    // ── 6. 管理（低频或平台/商业化能力，仅 admin/pm 可见；运营/系统安全 折叠进次级分组）──
    {
      title: '管理',
      icon: markRaw(ControlOutlined),
      zone: 'admin',
      subGroups: [
        {
          title: '运营看板',
          items: [
            { path: '/dashboard', title: '管理看板', icon: markRaw(DashboardOutlined) },
            { path: '/control-plane', title: '控制平面', icon: markRaw(ControlOutlined) },
            { path: '/budgets', title: '预算看板', icon: markRaw(WalletOutlined) },
            { path: '/value-report', title: '收益账单', icon: markRaw(AccountBookOutlined) },
          ],
        },
        {
          title: '系统与安全',
          items: [
            { path: '/users', title: '用户与角色', icon: markRaw(UserOutlined) },
            { path: '/audit', title: '审计日志', icon: markRaw(FileSearchOutlined) },
            { path: '/settings', title: '系统设置', icon: markRaw(SettingOutlined) },
          ],
        },
      ],
    },
  ]
  // 按角色过滤：
  // - admin 区仅对 admin/pm 可见，研究员/reviewer 完全隐藏
  // - research 区对所有角色可见，但 reviewer 仅可见部分
  return groups
    .map((g) => {
      // admin 区对非管理员完全隐藏
      if (g.zone === 'admin' && !admin) {
        return { ...g, items: [], subGroups: [] }
      }
      if (g.subGroups) {
        return {
          ...g,
          subGroups: g.subGroups
            .map((s) => ({ ...s, items: s.items.filter((it) => isMenuVisible(it.path, role)) }))
            .filter((s) => s.items.length > 0),
        }
      }
      return {
        ...g,
        items: g.items.filter((it) => isMenuVisible(it.path, role)),
      }
    })
    .filter((g) => (g.subGroups ? g.subGroups.length > 0 : g.items.length > 0))
})

// 收集分组内所有叶子路径（兼容 items 与 subGroups 两种结构）
function collectPaths(group) {
  if (group.subGroups) return group.subGroups.flatMap((s) => s.items.map((it) => it.path))
  return group.items.map((it) => it.path)
}

// 扁平化用于查找当前页标题（兼容 items 与 subGroups 两种结构）
const menuItems = computed(() =>
  menuGroups.value.flatMap((g) => (g.subGroups ? g.subGroups.flatMap((s) => s.items) : g.items)),
)

// 「新建」下拉菜单项：根据当前页面动态生成上下文快捷入口
const createMenuItems = computed(() => {
  const path = route.path
  if (path.startsWith('/samples')) {
    return [
      { path: '/samples?create=1', label: '新建样品', icon: markRaw(InboxOutlined) },
      { path: '/experiment-workbench?create=1', label: '新建实验任务', icon: markRaw(FormOutlined) },
    ]
  }
  if (path.startsWith('/experiment-workbench') || path.startsWith('/experiments')) {
    return [
      { path: '/experiment-workbench?create=1', label: '新建实验任务', icon: markRaw(FormOutlined) },
      { path: '/samples?create=1', label: '新建样品', icon: markRaw(InboxOutlined) },
    ]
  }
  if (path.startsWith('/equipment')) {
    return [
      { path: '/equipment?create=1', label: '新增设备', icon: markRaw(ToolOutlined) },
    ]
  }
  if (path.startsWith('/materials')) {
    return [
      { path: '/materials?create=1', label: '新增物料', icon: markRaw(ShopOutlined) },
    ]
  }
  if (path.startsWith('/projects')) {
    return [
      { path: '/projects?create=1', label: '新建项目', icon: markRaw(ProjectOutlined) },
    ]
  }
  if (path.startsWith('/users')) {
    return [
      { path: '/users?create=1', label: '新增用户', icon: markRaw(UserOutlined) },
    ]
  }
  // 默认研发任务入口
  return [
    { path: '/research', label: '新建研发任务', icon: markRaw(ExperimentOutlined) },
    { path: '/workbench', label: '新建候选材料设计', icon: markRaw(ExperimentOutlined) },
    { path: '/ecml', label: '新建闭环迭代', icon: markRaw(SyncOutlined) },
  ]
})

const recentRuns = ref([])
const recentLoading = ref(false)
const healthFailed = ref(false)

const healthText = computed(() => {
  if (systemStore.health?.status === 'ok') return '系统正常'
  if (healthFailed.value || systemStore.health?.status) return '连接失败'
  return '连接中…'
})

const healthClass = computed(() => {
  if (systemStore.health?.status === 'ok') return 'health-ok'
  if (healthFailed.value || systemStore.health?.status) return 'health-error'
  return 'health-pending'
})

const currentPageTitle = computed(() => {
  const item = menuItems.value.find((m) => m.path === route.path)
  return item?.title || route.meta?.title || '新材料研发平台'
})

function onCreateMenuClick({ key }) {
  track('create_click', { path: key })
  router.push(key)
}

// Step C：项目定位变更后刷新（由 ContextColumn 触发，不整页重建）
async function onContextRefresh() {
  try {
    useProjectContextStore().fetchProjects()
  } catch {
    /* ignore */
  }
}

async function fetchRecentRuns() {
  recentLoading.value = true
  try {
    const data = await getEcmlRuns(5)
    recentRuns.value = data.runs || []
  } catch {
    recentRuns.value = []
  } finally {
    recentLoading.value = false
  }
}

watch(
  () => route.path,
  (to) => {
    syncMenuState()
    if (navShellEnabled) {
      activeEntry.value = pathToEntry(route.path)
    }
    track('page_view', { path: to })
  },
)

// 角色过滤导致分组变化时同步高亮与展开
watch(
  () => menuGroups.value.map((g) => g.title),
  () => {
    syncMenuState()
  },
  { immediate: true },
)

onMounted(async () => {
  // 恢复登录会话（依据本地凭证调用 /auth/me 校验）
  await restoreSession()
  // 会话失效/未登录：清除 useAuth 残留内存态并跳转登录页
  if (!getUserId()) {
    clearUser()
    goLogin()
  }
  try {
    await systemStore.fetchHealth()
  } catch {
    healthFailed.value = true
  }
  await fetchRecentRuns()
})
</script>

<style scoped>
.main-layout {
  height: 100vh;
  overflow: hidden;
  /* 三栏重构：nav-shell 替代 a-layout-sider 后，外层须显式行布局，
     否则 antd Layout 默认 column 会把 header+内容区挤到视口下方（右侧空白） */
  flex-direction: row;
}

.skip-link {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1000;
  padding: 8px 16px;
  background: var(--primary);
  color: #fff;
  font-size: 13px;
  text-decoration: none;
  border-radius: 0 0 6px 0;
  transform: translateY(-100%);
  transition: transform 0.15s ease;
}

.skip-link:focus {
  transform: translateY(0);
  outline: none;
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px var(--primary);
}

/* —— 侧边栏 —— */
.sidebar {
  background: var(--sidebar-bg) !important;
  box-shadow: 2px 0 16px rgba(11, 18, 32, 0.22);
  position: relative;
}

/* —— Step B：稳定导航壳层 —— */
.nav-shell {
  display: flex;
  height: 100%;
  flex-shrink: 0;
  overflow: hidden;
}

.nav-groups {
  width: 220px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 0 16px;
}

.nav-groups-empty {
  margin-top: 40px;
  color: var(--sidebar-text) !important;
}

.shell-group-title {
  color: var(--sidebar-text);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 12px 16px 4px;
}

.shell-menu {
  background: transparent !important;
  border-right: none;
}

.shell-menu :deep(.ant-menu-item) {
  color: var(--sidebar-text);
  margin: 2px 10px;
  border-radius: var(--radius-md);
  height: 38px;
  line-height: 38px;
  font-size: 13px;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.shell-menu :deep(.ant-menu-item:hover) {
  color: var(--text-on-dark) !important;
  background: var(--sidebar-hover) !important;
}

.shell-menu :deep(.ant-menu-item-selected) {
  background: var(--sidebar-active) !important;
  color: var(--sidebar-text-active) !important;
}

.shell-menu :deep(.ant-menu-item-selected::after) {
  display: none;
}

.shell-menu :deep(.ant-menu-item .menu-link) {
  display: flex;
  align-items: center;
  gap: 10px;
  color: inherit;
  text-decoration: none;
  width: 100%;
  height: 100%;
}

.shell-menu :deep(.ant-menu-item .menu-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 14px;
  width: 18px;
}

.shell-menu :deep(.ant-menu-item .menu-text) {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar :deep(.ant-layout-sider-children) {
  display: flex;
  flex-direction: column;
}

.sidebar :deep(.ant-layout-sider-trigger) {
  background: rgba(0, 0, 0, 0.4);
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  height: 40px;
  line-height: 40px;
}

/* —— Logo 区域 —— */
.logo {
  height: 52px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  flex-shrink: 0;
}

.logo-collapsed {
  justify-content: center;
  padding: 0;
}

.logo-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.logo-text {
  color: var(--text-on-dark);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

/* —— 菜单 —— */
.sidebar-menu {
  background: transparent !important;
  border-right: none;
  padding-top: 6px;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-menu :deep(.ant-menu-item) {
  color: var(--sidebar-text);
  margin: 2px 10px;
  border-radius: var(--radius-md);
  height: 40px;
  line-height: 40px;
  font-size: 13px;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.sidebar-menu :deep(.ant-menu-item:hover) {
  color: var(--text-on-dark) !important;
  background: var(--sidebar-hover) !important;
}

.sidebar-menu :deep(.ant-menu-item-selected) {
  background: var(--sidebar-active) !important;
  color: var(--sidebar-text-active) !important;
}

.sidebar-menu :deep(.ant-menu-item-selected::after) {
  display: none;
}

.sidebar-menu :deep(.ant-menu-item .anticon) {
  font-size: 15px;
}

.sidebar-menu :deep(.ant-menu-item) .menu-link {
  display: flex;
  align-items: center;
  gap: 10px;
  color: inherit;
  text-decoration: none;
  width: 100%;
  height: 100%;
}

.sidebar-menu :deep(.ant-menu-item) .menu-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 15px;
  width: 20px;
}

.sidebar-menu :deep(.ant-menu-item) .menu-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* —— 子菜单分组标题 —— */
.sidebar-menu :deep(.ant-menu-submenu-title) {
  font-size: 12px;
  color: var(--sidebar-text);
  letter-spacing: 0.04em;
  padding: 0 16px !important;
  margin: 4px 10px !important;
  border-radius: var(--radius-md);
  height: 40px;
  line-height: 40px;
  font-weight: 600;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.sidebar-menu :deep(.ant-menu-submenu-title:hover) {
  color: var(--text-on-dark) !important;
  background: var(--sidebar-hover) !important;
}

.sidebar-menu :deep(.ant-menu-submenu-open > .ant-menu-submenu-title) {
  color: var(--text-on-dark) !important;
}

.sidebar-menu :deep(.ant-menu-submenu-arrow) {
  color: var(--sidebar-text);
}

.sidebar-menu :deep(.ant-menu-submenu-title:hover .ant-menu-submenu-arrow) {
  color: var(--text-on-dark);
}

/* 收起状态下子菜单标题保持图标居中 */
.sidebar-menu:deep(.ant-layout-sider-collapsed) .ant-menu-submenu-title {
  padding: 0 !important;
  margin: 4px auto !important;
  width: 48px;
}

/* —— 顶部 Header —— */
.top-header {
  background: var(--realsee-surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 56px;
  line-height: 56px;
  box-shadow: var(--shadow-sm);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* —— 最近运行菜单 —— */
.recent-menu {
  min-width: 220px;
}

.recent-run-link {
  display: block;
  color: inherit;
  text-decoration: none;
}

.recent-run-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.recent-run-target {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.recent-run-meta {
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
}

/* —— 侧边栏底部 —— */
.sidebar-footer {
  flex-shrink: 0;
  padding: 8px 16px 10px;
  border-top: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* —— 侧边栏底部角色徽标 —— */
.role-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-on-dark);
  padding: 2px 4px;
  overflow: hidden;
}

.role-badge :deep(.anticon) {
  color: var(--sidebar-text);
  flex-shrink: 0;
}

.role-badge-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.role-badge-tag {
  margin: 0;
  font-size: 11px;
  flex-shrink: 0;
}

/* —— 顶部用户按钮 —— */
.user-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.user-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--primary);
}

.user-name-text {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-tag {
  margin: 0;
  font-size: 11px;
}

/* —— 专业视角切换 —— */
.persp-check {
  color: var(--primary);
  margin-right: 8px;
}
.persp-muted {
  color: var(--text-muted);
}

/* —— 健康指示器 —— */
.health-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 0;
  border-radius: 20px;
}

.health-indicator .health-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.health-text {
  color: var(--sidebar-text);
  white-space: nowrap;
}

.health-ok .health-dot {
  background: var(--success);
  box-shadow: 0 0 4px var(--success);
}

.health-ok .health-text {
  color: var(--success);
}

.health-error .health-dot {
  background: var(--danger);
  box-shadow: 0 0 4px var(--danger);
}

.health-error .health-text {
  color: var(--danger);
}

.health-pending .health-dot {
  background: var(--text-on-dark-muted);
  animation: pulse 1.5s ease-in-out infinite;
}

.health-pending .health-text {
  color: var(--text-on-dark-muted);
}

/* —— 内容区 —— */
.main-content {
  background: var(--bg);
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow-y: auto;
  overflow-x: hidden;
}

/* 全局：所有页面容器自适应内容区宽度（不设固定 max-width）*/
.main-content > * {
  width: 100%;
  max-width: 100%;
  margin: 0;
}

.main-content:focus {
  outline: none;
}

.main-content:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.route-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  min-height: 400px;
}

.route-loading-text {
  font-size: 13px;
  color: var(--text-muted);
}

@media (prefers-reduced-motion: reduce) {
  .health-pending .health-dot {
    animation: none;
  }
}
</style>
