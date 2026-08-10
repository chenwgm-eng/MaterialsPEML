/**
 * 稳定一级导航骨架 + 一级分组配置（Step B 导航壳层）。
 *
 * 设计文档 4.B3：最终显示 = requiredAnyPermission 命中 ∧ 用户有该最小权限 ∧ nav_visibility 未隐藏。
 * visible=true 不能把无最小权限入口变可见（权限下限由后端 permission 判定保证）。
 *
 * STABLE_ENTRIES：四大稳定一级入口（供 IconRail 使用）。
 * MENU_GROUPS：沿 MainLayout 的 6 个一级分组迁移而来，每个分组挂到所属稳定入口 key，
 *              每个 item 声明 requiredAnyPermission（与后端 permissions.py 一致）。
 * ENTRY_TO_GROUP_KEYS：entry key → 该入口下分组 key 列表，供联动。
 */
import { markRaw } from 'vue'
import {
  HomeOutlined,
  ProjectOutlined,
  DatabaseOutlined,
  SettingOutlined,
  BellOutlined,
  ExperimentOutlined,
  ShareAltOutlined,
  SyncOutlined,
  FormOutlined,
  DashboardOutlined,
  InboxOutlined,
  ToolOutlined,
  ImportOutlined,
  SafetyCertificateOutlined,
  BookOutlined,
  ShopOutlined,
  ProfileOutlined,
  RobotOutlined,
  AppstoreOutlined,
  DeploymentUnitOutlined,
  ApiOutlined,
  ControlOutlined,
  WalletOutlined,
  AccountBookOutlined,
  UserOutlined,
  FileSearchOutlined,
} from '@ant-design/icons-vue'

// ── 稳定一级入口骨架（供 IconRail 使用）──
export const STABLE_ENTRIES = [
  {
    key: 'workbench',
    label: '工作台',
    icon: markRaw(HomeOutlined),
    requiredAnyPermission: [],
    navVisibilityConfigurable: true,
  },
  {
    key: 'project',
    label: '项目',
    icon: markRaw(ProjectOutlined),
    requiredAnyPermission: [],
    navVisibilityConfigurable: true,
  },
  {
    key: 'capability',
    label: '能力库',
    icon: markRaw(DatabaseOutlined),
    requiredAnyPermission: [],
    navVisibilityConfigurable: true,
  },
  {
    key: 'admin',
    label: '管理',
    icon: markRaw(SettingOutlined),
    requiredAnyPermission: ['user.manage', 'tenant.manage', 'audit.view'],
    navVisibilityConfigurable: true,
  },
]

// ── 一级分组配置（迁移自 MainLayout 的 6 个分组）──
// entryKey 标记分组所属稳定入口；item.requiredAnyPermission 与后端权限点一致。
export const MENU_GROUPS = [
  // 1. 我的研发 → workbench
  {
    key: 'my-research',
    title: '我的研发',
    entryKey: 'workbench',
    icon: markRaw(HomeOutlined),
    zone: 'research',
    items: [
      { path: '/', title: '首页', icon: markRaw(HomeOutlined), requiredAnyPermission: ['project.view'] },
      { path: '/my-tasks', title: '我的待办', icon: markRaw(BellOutlined), requiredAnyPermission: ['project.view'] },
    ],
  },
  // 2. 项目空间 → project
  {
    key: 'project-space',
    title: '项目空间',
    entryKey: 'project',
    icon: markRaw(ProjectOutlined),
    zone: 'research',
    items: [
      { path: '/projects', title: '项目管理', icon: markRaw(ProjectOutlined), requiredAnyPermission: ['project.view'] },
      { path: '/workbench', title: '材料设计', icon: markRaw(ExperimentOutlined), requiredAnyPermission: ['candidate.view'] },
      { path: '/synthesis', title: '合成路径', icon: markRaw(ShareAltOutlined), requiredAnyPermission: ['experiment.view'] },
      { path: '/formula-design', title: '配方与工艺', icon: markRaw(ExperimentOutlined), requiredAnyPermission: ['experiment.view'] },
      { path: '/ecml', title: '实验闭环迭代', icon: markRaw(SyncOutlined), requiredAnyPermission: ['experiment.view'] },
    ],
  },
  // 3. 实验与数据 → project
  {
    key: 'experiment-data',
    title: '实验与数据',
    entryKey: 'project',
    icon: markRaw(FormOutlined),
    zone: 'research',
    subGroups: [
      {
        title: '实验执行',
        items: [
          { path: '/experiment-dashboard', title: '实验数据看板', icon: markRaw(DashboardOutlined), requiredAnyPermission: ['experiment.view'] },
          { path: '/experiment-workbench', title: '实验工作台', icon: markRaw(FormOutlined), requiredAnyPermission: ['experiment.create'] },
          { path: '/experiments', title: '实验数据', icon: markRaw(DatabaseOutlined), requiredAnyPermission: ['experiment.view'] },
          { path: '/samples', title: '样品与批次', icon: markRaw(InboxOutlined), requiredAnyPermission: ['experiment.view'] },
        ],
      },
      {
        title: '数据管理',
        items: [
          { path: '/equipment', title: '设备与校准', icon: markRaw(ToolOutlined), requiredAnyPermission: ['experiment.view'] },
          { path: '/data-ingest', title: '数据接入', icon: markRaw(ImportOutlined), requiredAnyPermission: ['experiment.create'] },
          { path: '/data-quality', title: '数据质量', icon: markRaw(SafetyCertificateOutlined), requiredAnyPermission: ['experiment.view'] },
        ],
      },
    ],
  },
  // 4. 知识资产 → capability
  {
    key: 'knowledge',
    title: '知识资产',
    entryKey: 'capability',
    icon: markRaw(DatabaseOutlined),
    zone: 'research',
    items: [
      { path: '/technology-intelligence', title: '技术情报', icon: markRaw(BookOutlined), requiredAnyPermission: ['project.view'] },
      { path: '/knowledge-graph', title: '知识图谱', icon: markRaw(ShareAltOutlined), requiredAnyPermission: ['candidate.view'] },
      { path: '/knowledge-base', title: '知识库', icon: markRaw(DatabaseOutlined), requiredAnyPermission: ['project.view'] },
      { path: '/materials', title: '物料规格库', icon: markRaw(ShopOutlined), requiredAnyPermission: ['project.view'] },
      { path: '/properties', title: '属性字典', icon: markRaw(ProfileOutlined), requiredAnyPermission: ['project.view'] },
      { path: '/mdm', title: '主数据治理', icon: markRaw(DatabaseOutlined), requiredAnyPermission: ['tenant.manage'] },
    ],
  },
  // 5. AI 与编排 → capability
  {
    key: 'ai-orchestration',
    title: 'AI 与编排',
    entryKey: 'capability',
    icon: markRaw(RobotOutlined),
    zone: 'research',
    subGroups: [
      {
        title: '研发与编排',
        items: [
          { path: '/research', title: '研发工作台', icon: markRaw(ExperimentOutlined), requiredAnyPermission: ['experiment.view'] },
          { path: '/orchestration', title: '智能编排', icon: markRaw(RobotOutlined), requiredAnyPermission: ['agent.manage'] },
          { path: '/eval-center', title: '评估中心', icon: markRaw(ExperimentOutlined), requiredAnyPermission: ['prediction.run'] },
        ],
      },
      {
        title: '智能体与工具',
        items: [
          { path: '/agents', title: '智能体管理', icon: markRaw(RobotOutlined), requiredAnyPermission: ['agent.manage'] },
          { path: '/tools', title: '工具与连接器', icon: markRaw(AppstoreOutlined), requiredAnyPermission: ['agent.manage'] },
          { path: '/mappings', title: '映射控制台', icon: markRaw(DeploymentUnitOutlined), requiredAnyPermission: ['agent.manage'] },
          { path: '/topology', title: '调用关系', icon: markRaw(ShareAltOutlined), requiredAnyPermission: ['agent.manage'] },
          { path: '/capability-center', title: '能力契约', icon: markRaw(ApiOutlined), requiredAnyPermission: ['agent.manage'] },
        ],
      },
    ],
  },
  // 6. 管理 → admin
  {
    key: 'admin-group',
    title: '管理',
    entryKey: 'admin',
    icon: markRaw(ControlOutlined),
    zone: 'admin',
    subGroups: [
      {
        title: '运营看板',
        items: [
          { path: '/dashboard', title: '管理看板', icon: markRaw(DashboardOutlined), requiredAnyPermission: ['user.manage'] },
          { path: '/control-plane', title: '控制平面', icon: markRaw(ControlOutlined), requiredAnyPermission: ['user.manage'] },
          { path: '/budgets', title: '预算看板', icon: markRaw(WalletOutlined), requiredAnyPermission: ['user.manage'] },
          { path: '/value-report', title: '收益账单', icon: markRaw(AccountBookOutlined), requiredAnyPermission: ['user.manage'] },
        ],
      },
      {
        title: '系统与安全',
        items: [
          { path: '/users', title: '用户与角色', icon: markRaw(UserOutlined), requiredAnyPermission: ['user.manage'] },
          { path: '/audit', title: '审计日志', icon: markRaw(FileSearchOutlined), requiredAnyPermission: ['audit.view'] },
          { path: '/settings', title: '系统设置', icon: markRaw(SettingOutlined), requiredAnyPermission: ['tenant.manage'] },
          { path: '/nav-visibility', title: '导航可见性', icon: markRaw(SettingOutlined), requiredAnyPermission: ['user.manage'] },
        ],
      },
    ],
  },
]

// entry key → 该入口下分组 key 列表（供联动）
export const ENTRY_TO_GROUP_KEYS = MENU_GROUPS.reduce((acc, g) => {
  if (!acc[g.entryKey]) acc[g.entryKey] = []
  acc[g.entryKey].push(g.key)
  return acc
}, {})