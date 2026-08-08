import { createRouter, createWebHistory } from 'vue-router'
import { message } from 'ant-design-vue'
import MainLayout from '@/layouts/MainLayout.vue'
import { getUserId } from '@/api/client'
import { ROLE_RANK } from '@/constants/roles'

const routes = [
  {
    path: '/',
    component: MainLayout,
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '总览', icon: 'DashboardOutlined' } },
      { path: 'dashboard', name: 'ManagementDashboard', component: () => import('@/views/ManagementDashboard.vue'), meta: { title: '管理看板', icon: 'DashboardOutlined' } },
      { path: 'my-tasks', name: 'MyTasks', component: () => import('@/views/MyTasks.vue'), meta: { title: '我的待办', icon: 'BellOutlined' } },
      { path: 'projects', name: 'Projects', component: () => import('@/views/Projects.vue'), meta: { title: '项目管理', icon: 'ProjectOutlined' } },
      { path: 'projects/new', name: 'ProjectNew', component: () => import('@/views/ProjectNew.vue'), meta: { title: '项目新建', icon: 'ProjectOutlined' } },
      // 审查意见0726：材料发现已合并到候选工作台，路径 /discovery 由顶部 redirect 处理
      { path: 'workbench', name: 'CandidateWorkbench', component: () => import('@/views/CandidateWorkbench.vue'), meta: { title: '候选材料设计', icon: 'ExperimentOutlined' } },
      { path: 'prediction', name: 'Prediction', component: () => import('@/views/Prediction.vue'), meta: { title: '性质预测', icon: 'LineChartOutlined' } },
      { path: 'ecml', name: 'ECMLMonitor', component: () => import('@/views/ECMLMonitor.vue'), meta: { title: '实验闭环迭代', icon: 'SyncOutlined' } },
      { path: 'ecml/runs', name: 'ECMLRuns', component: () => import('@/views/ECMLRuns.vue'), meta: { title: '迭代历史', icon: 'HistoryOutlined' } },
      { path: 'experiments', name: 'Experiments', component: () => import('@/views/Experiments.vue'), meta: { title: '实验数据', icon: 'DatabaseOutlined' } },
      { path: 'experiment-workbench', name: 'ExperimentWorkbench', component: () => import('@/views/ExperimentWorkbench.vue'), meta: { title: '实验工作台', icon: 'FormOutlined' } },
      // 审查意见0726：决策放行已整合进「我的待办」，旧路径重定向
      { path: 'approvals', redirect: '/my-tasks?tab=approval' },
      { path: 'committees', redirect: '/my-tasks?tab=committee' },
      { path: 'release-cards', redirect: '/my-tasks?tab=release' },
      { path: 'value-report', name: 'ValueReport', component: () => import('@/views/ValueReport.vue'), meta: { title: '收益账单', icon: 'AccountBookOutlined', requiredRole: 'admin' } },
      { path: 'data-ingest', name: 'DataIngest', component: () => import('@/views/DataIngest.vue'), meta: { title: '数据接入', icon: 'ImportOutlined' } },
      { path: 'capability-center', name: 'CapabilityCenter', component: () => import('@/views/CapabilityCenter.vue'), meta: { title: '能力契约', icon: 'ApiOutlined', requiredRole: 'admin' } },
      { path: 'control-plane', name: 'ControlPlaneDashboard', component: () => import('@/views/ControlPlaneDashboard.vue'), meta: { title: '控制平面', icon: 'ControlOutlined', requiredRole: 'admin' } },
      { path: 'budgets', name: 'BudgetBoard', component: () => import('@/views/BudgetBoard.vue'), meta: { title: '预算看板', icon: 'WalletOutlined', requiredRole: 'admin' } },
      // 审查意见0726：工具目录已合并到「工具与连接器」(/tools)
      // /tool-catalog 路径重定向到 /tools
      { path: 'tool-catalog', redirect: '/tools' },
      { path: 'tool-catalog/:id', redirect: '/tools' },
      { path: 'eval-center', name: 'EvalCenter', component: () => import('@/views/EvalCenter.vue'), meta: { title: '评估中心', icon: 'ExperimentOutlined', requiredRole: 'admin' } },
      { path: 'data-quality', name: 'DataQualityWorkbench', component: () => import('@/views/DataQualityWorkbench.vue'), meta: { title: '数据质量', icon: 'SafetyCertificateOutlined' } },
      { path: 'materials', name: 'RawMaterials', component: () => import('@/views/RawMaterials.vue'), meta: { title: '物料规格库', icon: 'ShopOutlined' } },
      { path: 'samples', name: 'SampleManager', component: () => import('@/views/SampleManager.vue'), meta: { title: '样品管理', icon: 'InboxOutlined' } },
      { path: 'synthesis', name: 'Synthesis', component: () => import('@/views/Synthesis.vue'), meta: { title: '合成路径', icon: 'BranchesOutlined' } },
      { path: 'formula-design', name: 'FormulaDesign', component: () => import('@/views/FormulaDesign.vue'), meta: { title: '配方与工艺', icon: 'ExperimentOutlined' } },
      { path: 'tools', name: 'Tools', component: () => import('@/views/ToolsHub.vue'), meta: { title: '工具与连接器', icon: 'AppstoreOutlined' } },
      { path: 'topology', name: 'Topology', component: () => import('@/views/TopologyView.vue'), meta: { title: '调用关系', icon: 'ShareAltOutlined' } },
      // 审查意见0726：智能编排菜单已合并到研发工作台；路由保留以便直接访问
      { path: 'orchestration', name: 'Orchestration', component: () => import('@/views/Orchestration.vue'), meta: { title: '智能编排', icon: 'RobotOutlined' } },
      { path: 'research', name: 'ResearchWorkbench', component: () => import('@/views/ResearchWorkbench.vue'), meta: { title: '研发工作台', icon: 'ExperimentOutlined' } },
      { path: 'agents', name: 'AgentManager', component: () => import('@/views/AgentManager.vue'), meta: { title: '智能体管理', icon: 'TeamOutlined' } },
      { path: 'mappings', name: 'MappingConsole', component: () => import('@/views/MappingConsole.vue'), meta: { title: '映射控制台', icon: 'DeploymentUnitOutlined', requiredRole: 'admin' } },
      { path: 'technology-intelligence', name: 'TechnologyIntelligence', component: () => import('@/views/TechnologyIntelligence.vue'), meta: { title: '技术情报', icon: 'BookOutlined' } },
      { path: 'knowledge-base', name: 'KnowledgeBase', component: () => import('@/views/KnowledgeBase.vue'), meta: { title: '知识库', icon: 'DatabaseOutlined' } },
      { path: 'knowledge-graph', name: 'KnowledgeGraph', component: () => import('@/views/KnowledgeGraph.vue'), meta: { title: '知识图谱', icon: 'ShareAltOutlined' } },
      { path: 'properties', name: 'MaterialProperties', component: () => import('@/views/MaterialProperties.vue'), meta: { title: '属性字典', icon: 'ProfileOutlined' } },
      { path: 'mdm', name: 'MdmCenter', component: () => import('@/views/MdmCenter.vue'), meta: { title: '主数据治理', icon: 'DatabaseOutlined' } },
      { path: 'equipment', name: 'EquipmentLedger', component: () => import('@/views/EquipmentLedger.vue'), meta: { title: '设备台账', icon: 'ToolOutlined' } },
      { path: 'users', name: 'UserManagement', component: () => import('@/views/UserManagement.vue'), meta: { title: '用户管理', icon: 'UserOutlined' } },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings.vue'), meta: { title: '系统设置', icon: 'SettingOutlined' } },
      // P0-3：无权限状态统一页面
      { path: 'forbidden', name: 'Forbidden', component: () => import('@/components/ForbiddenResult.vue'), meta: { title: '无权限访问' } },
      // M19: 404 通配路由作为主布局的子路由，保留侧栏/页头并返回首页（P2-101）
      { path: ':pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFound.vue'), meta: { title: '页面未找到' } },
    ],
  },
  // P2-101: 常见错误路径 301 重定向到规范路径
  { path: '/raw-materials', redirect: '/materials' },
  { path: '/capabilities', redirect: '/capability-center' },
  { path: '/value-reports', redirect: '/value-report' },
  { path: '/value-reports/:id', redirect: to => `/value-report/${to.params.id}` },
  { path: '/knowledge', redirect: '/knowledge-graph' },
  { path: '/technology', redirect: '/technology-intelligence' },
  { path: '/tech-intelligence', redirect: '/technology-intelligence' },
  { path: '/agent-manager', redirect: '/agents' },
  { path: '/research-workbench', redirect: '/research' },
  { path: '/experiment-data', redirect: '/experiments' },
  // 审查意见0726：菜单合并后的旧路径重定向
  { path: '/discovery', redirect: '/workbench' },        // 材料发现 → 候选设计
]

const router = createRouter({
  // L: 使用 Vite 提供的 base URL，确保子路径部署时路由解析正确
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// H1: 全局导航守卫。
// 审查意见0726：根路径 '/' 默认显示总览页面（Dashboard.vue），不再按角色跳转。
// - 所有角色（含未登录用户）访问根路径时都显示「总览」首页
// - 角色权限差异通过菜单可见性控制，而非首页分流
router.beforeEach((to, from, next) => {
  // 统一使用 getUserId() 判断登录态（检查 authToken 是否存在）
  const userId = getUserId()
  const publicPages = ['/'] // 总览允许未登录访问
  const isPublic = publicPages.includes(to.path)

  // C1: 未登录访问非公开页面，重定向到首页并提示登录
  if (!userId && !isPublic) {
    message.warning('请先登录')
    return next('/')
  }

  // C2: 角色权限校验
  if (to.meta.requiredRole) {
    // user_role 来自登录后写入 localStorage 的值（auth/login 与 restoreSession
    // 均会更新），后端 /config 不返回 user_role，不能从 systemStore.config 取。
    const userRole = localStorage.getItem('userRole') || 'viewer'
    if ((ROLE_RANK[userRole] || 0) < (ROLE_RANK[to.meta.requiredRole] || 0)) {
      // P0-3：权限不足时跳转统一的 403 页面，而非仅 toast 提示后重定向首页
      return next('/forbidden')
    }
  }
  next()
})

// T1: 切换路由时同步更新浏览器标签页标题
router.afterEach((to) => {
  const pageTitle = to.meta?.title
  if (pageTitle) {
    document.title = `${pageTitle} - MaterialsPEML`
  } else {
    document.title = 'MaterialsPEML'
  }
})

export default router
