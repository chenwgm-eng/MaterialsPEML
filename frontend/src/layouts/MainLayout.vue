<template>
  <a class="skip-link" href="#main-content">跳转到主内容</a>
  <a-layout class="main-layout">
    <a-layout-sider
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
            v-if="group.items.length === 1"
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
            <a-menu-item
              v-for="item in group.items"
              :key="item.path"
            >
              <router-link :to="item.path" class="menu-link">
                <span class="menu-icon"><component :is="item.icon" /></span>
                <span class="menu-text">{{ item.title }}</span>
              </router-link>
            </a-menu-item>
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

    <a-layout>
      <a-layout-header class="top-header">
        <div class="header-left">
          <a-dropdown placement="bottomLeft" trigger="click">
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
          <a-dropdown placement="bottomRight" trigger="click">
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
                <a-menu-item key="logout"><LogoutOutlined /> 退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <a-button v-else size="small" type="primary" @click="showLogin = true">
            <LoginOutlined /> 登录
          </a-button>
        </div>
      </a-layout-header>

      <a-layout-content id="main-content" class="main-content" tabindex="-1">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <suspense>
              <component :is="Component" />
              <template #fallback>
                <div class="route-loading">
                  <a-spin size="large" />
                  <span class="route-loading-text">{{ MESSAGES.loading }}…</span>
                </div>
              </template>
            </suspense>
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>

    <!-- 全局任务通知浮层 -->
    <TaskNotifier />

    <!-- 登录弹窗 -->
    <a-modal
      v-model:open="showLogin"
      title="登录"
      :confirm-loading="loginLoading"
      width="400px"
      @ok="onLogin"
    >
      <a-form layout="vertical">
        <a-form-item label="用户名">
          <a-input v-model:value="loginForm.username" name="username" autocomplete="username" placeholder="admin…" @press-enter="onLogin" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="loginForm.password" name="password" autocomplete="current-password" placeholder="admin123…" @press-enter="onLogin" />
        </a-form-item>
        <div class="login-hint">默认管理员：admin / admin123</div>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<script setup>
import { ref, computed, watch, onMounted, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSystemStore } from '@/stores/system'
import { getEcmlRuns } from '@/api/ecml'
import { login as authLogin, getCurrentUser, logout as authLogout } from '@/api/auth'
import { setUserId, getUserId } from '@/api/client'
import { useAuth } from '@/composables/useAuth'
import { roleColor, roleLabel } from '@/constants/roles'
import { message } from 'ant-design-vue'
import TaskNotifier from '@/components/TaskNotifier.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
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
  HistoryOutlined,
  ThunderboltOutlined,
  HomeOutlined,
  BellOutlined,
  DeploymentUnitOutlined,
} from '@ant-design/icons-vue'
import { MESSAGES } from '@/constants/glossary'

const route = useRoute()
const router = useRouter()
const systemStore = useSystemStore()

const collapsed = ref(false)
const selectedKeys = ref([route.path])
const openKeys = ref([])

// 根据当前路由同步菜单高亮与展开分组
function syncMenuState() {
  const path = route.path
  selectedKeys.value = [path]
  // P1-3：同一 path 若出现在多个分组，优先保留当前已展开的分组，
  // 避免点击后分组被强制切换
  const matchedGroups = menuGroups.value.filter((g) => g.items.some((it) => it.path === path))
  const stayOpen = matchedGroups.find((g) => openKeys.value.includes(g.title))
  const matchedGroup = stayOpen || matchedGroups[0]
  // 仅对多项分组（有 sub-menu）设置 openKeys，单项分组无 sub-menu 无需展开
  if (matchedGroup && matchedGroup.items.length > 1) {
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
const showLogin = ref(false)
const loginLoading = ref(false)
const loginForm = ref({ username: '', password: '' })

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

async function onLogin() {
  if (!loginForm.value.username?.trim() || !loginForm.value.password) {
    message.warning('请输入用户名和密码')
    return
  }
  loginLoading.value = true
  try {
    const data = await authLogin(loginForm.value)
    setUserId(data.user_id, data.token)
    setUser({ id: data.user_id, role: data.role, token: data.token })
    currentUser.value = data
    showLogin.value = false
    loginForm.value = { username: '', password: '' }
    message.success(`欢迎，${data.display_name || data.username}`)
    // 若当前页对新角色不可见，跳回总览
    if (!isMenuVisible(route.path, data.role) && route.path !== '/') {
      router.push('/')
    }
  } catch {
    // 错误由拦截器处理
  } finally {
    loginLoading.value = false
  }
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
  message.success('已退出登录')
  if (!isMenuVisible(route.path, 'viewer') && route.path !== '/') {
    router.push('/')
  }
}

function onUserMenuClick({ key }) {
  if (key === 'logout') {
    onLogout()
  } else if (key === 'users') {
    router.push('/users')
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
    // ── 2. 项目空间（以项目空间串联，减少跨菜单查找）──
    {
      title: '项目空间',
      icon: markRaw(ProjectOutlined),
      zone: 'research',
      items: [
        { path: '/projects', title: '项目管理', icon: markRaw(ProjectOutlined) },
        { path: '/projects/new', title: '项目新建', icon: markRaw(PlusOutlined) },
        { path: '/workbench', title: '候选材料设计', icon: markRaw(ExperimentOutlined) },
        { path: '/prediction', title: '性质预测', icon: markRaw(LineChartOutlined) },
        { path: '/synthesis', title: '合成路径', icon: markRaw(ShareAltOutlined) },
        { path: '/formula-design', title: '配方与工艺', icon: markRaw(ExperimentOutlined) },
        { path: '/ecml', title: '实验闭环迭代', icon: markRaw(SyncOutlined) },
        { path: '/ecml/runs', title: '迭代历史', icon: markRaw(HistoryOutlined) },
        { path: '/battery-life', title: '性能寿命预测', icon: markRaw(ThunderboltOutlined) },
      ],
    },
    // ── 3. 实验与数据（按实验执行对象组织）──
    {
      title: '实验与数据',
      icon: markRaw(FormOutlined),
      zone: 'research',
      items: [
        { path: '/experiment-workbench', title: '实验工作台', icon: markRaw(FormOutlined) },
        { path: '/experiments', title: '实验数据', icon: markRaw(DatabaseOutlined) },
        { path: '/samples', title: '样品与批次', icon: markRaw(InboxOutlined) },
        { path: '/equipment', title: '设备与校准', icon: markRaw(ToolOutlined) },
        { path: '/data-ingest', title: '数据接入', icon: markRaw(ImportOutlined) },
        { path: '/data-quality', title: '数据质量', icon: markRaw(SafetyCertificateOutlined) },
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
    // ── 5. AI 与编排（研发工作台 + 智能体 + 工具映射 + 评估）──
    {
      title: 'AI 与编排',
      icon: markRaw(RobotOutlined),
      zone: 'research',
      items: [
        { path: '/research', title: '研发工作台', icon: markRaw(ExperimentOutlined) },
        { path: '/orchestration', title: '智能编排', icon: markRaw(RobotOutlined) },
        { path: '/agents', title: '智能体管理', icon: markRaw(RobotOutlined) },
        { path: '/tools', title: '工具与连接器', icon: markRaw(AppstoreOutlined) },
        { path: '/mappings', title: '映射控制台', icon: markRaw(DeploymentUnitOutlined) },
        { path: '/capability-center', title: '能力契约', icon: markRaw(ApiOutlined) },
        { path: '/eval-center', title: '评估中心', icon: markRaw(ExperimentOutlined) },
      ],
    },
    // ── 6. 管理（低频或平台/商业化能力，仅 admin/pm 可见）──
    {
      title: '管理',
      icon: markRaw(ControlOutlined),
      zone: 'admin',
      items: [
        { path: '/dashboard', title: '管理看板', icon: markRaw(DashboardOutlined) },
        { path: '/control-plane', title: '控制平面', icon: markRaw(ControlOutlined) },
        { path: '/budgets', title: '预算看板', icon: markRaw(WalletOutlined) },
        { path: '/value-report', title: '收益账单', icon: markRaw(AccountBookOutlined) },
        { path: '/users', title: '用户与角色', icon: markRaw(UserOutlined) },
        { path: '/settings', title: '系统设置', icon: markRaw(SettingOutlined) },
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
        return { ...g, items: [] }
      }
      return {
        ...g,
        items: g.items.filter((it) => isMenuVisible(it.path, role)),
      }
    })
    .filter((g) => g.items.length > 0)
})

// 扁平化用于查找当前页标题
const menuItems = computed(() => menuGroups.value.flatMap((g) => g.items))

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
  router.push(key)
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
  () => {
    syncMenuState()
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
  // 恢复登录会话（依据 localStorage 中的 userId 调用 /auth/me 校验）
  await restoreSession()
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

.login-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: -8px;
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
