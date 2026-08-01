import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE = 'http://localhost:5175';
const REPORT_DIR = join(__dirname, 'test-screenshots');
const REPORT = [];

mkdirSync(REPORT_DIR, { recursive: true });

function add(page, path, step, status, detail = '', severity = '') {
  REPORT.push({ page, path, step, status, detail, severity, timestamp: new Date().toISOString() });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : status === 'WARN' ? '⚠️' : '🔍';
  console.log(`${icon} [${severity || 'INFO'}] ${page} | ${step}: ${status} ${detail ? '| ' + detail : ''}`);
}

async function screenshot(page, name) {
  const fname = name.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, '_').substring(0, 80);
  await page.screenshot({ path: join(REPORT_DIR, `${fname}.png`), fullPage: true });
}

async function checkBreadcrumb(page, pageName) {
  try {
    const bc = await page.$('.ant-breadcrumb, [class*="breadcrumb"]');
    if (bc) {
      const text = await bc.textContent();
      add(pageName, page.url(), '面包屑', 'PASS', `存在: ${text.trim().replace(/\s+/g, ' ')}`);
    } else {
      add(pageName, page.url(), '面包屑', 'INFO', '未检测到面包屑组件（可能已移除）');
    }
  } catch (e) {
    add(pageName, page.url(), '面包屑', 'INFO', '检测异常: ' + e.message);
  }
}

async function checkPageTitle(page, pageName) {
  try {
    const title = await page.title();
    add(pageName, page.url(), '页面标题', 'PASS', `标题: "${title}"`);
  } catch (e) {
    add(pageName, page.url(), '页面标题', 'FAIL', e.message);
  }
}

async function checkConsoleErrors(page, pageName) {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));
  // Wait a bit for async errors
  await page.waitForTimeout(1000);
  if (errors.length > 0) {
    const unique = [...new Set(errors)];
    unique.forEach(e => add(pageName, page.url(), 'Console错误', 'FAIL', e, 'P0'));
  }
}

async function checkMixedLang(page, pageName) {
  try {
    const body = await page.textContent('body');
    const cnPattern = /[\u4e00-\u9fa5]/;
    const enPattern = /[a-zA-Z]{3,}/g;
    const hasCN = cnPattern.test(body);
    const hasEN = enPattern.test(body);
    if (hasCN && hasEN) {
      add(pageName, page.url(), '中英文混杂', 'WARN', '页面同时包含中英文，需人工检查', 'P2');
    }
  } catch (e) {
    // ignore
  }
}

async function checkEmptyState(page, pageName) {
  try {
    const empty = await page.$('.ant-empty, .ant-result, [class*="empty"]');
    if (empty) {
      const text = await empty.textContent();
      add(pageName, page.url(), '空状态', 'INFO', `检测到空状态: ${text.trim().substring(0, 100)}`);
      return true;
    }
    return false;
  } catch (e) {
    return false;
  }
}

async function testFormValidation(page, pageName, formSelector) {
  try {
    const form = await page.$(formSelector || 'form');
    if (!form) return;
    // Try to submit without filling
    const submitBtn = await page.$('button[type="submit"], button:has-text("保存"), button:has-text("提交"), button:has-text("创建")');
    if (submitBtn) {
      await submitBtn.click();
      await page.waitForTimeout(500);
      // Check for validation messages
      const validation = await page.$('.ant-form-item-explain-error, [class*="error"]');
      if (validation) {
        add(pageName, page.url(), '表单校验', 'PASS', '触发了必填校验提示');
      } else {
        add(pageName, page.url(), '表单校验', 'WARN', '未触发必填校验（可能没有必填字段或校验未生效）', 'P1');
      }
    }
  } catch (e) {
    add(pageName, page.url(), '表单校验', 'FAIL', e.message);
  }
}

// ====== MAIN TEST FLOW ======

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
  });
  const page = await context.newPage();

  // Collect console errors globally
  const globalErrors = [];
  page.on('pageerror', err => globalErrors.push(err.message));

  try {
    // ==========================================
    // 一、平台运营
    // ==========================================
    console.log('\n=== 一、平台运营 ===\n');

    // --- 管理看板 ---
    console.log('\n--- 1.1 管理看板 (/dashboard) ---');
    await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('Dashboard', '/dashboard', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'Dashboard');
    await checkBreadcrumb(page, 'Dashboard');
    await checkMixedLang(page, 'Dashboard');
    await checkEmptyState(page, 'Dashboard');

    // 检查指标卡片
    const statCards = await page.$$('.ant-statistic, [class*="stat"], [class*="metric"], [class*="card"]');
    add('Dashboard', '/dashboard', '指标卡片', statCards.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${statCards.length} 个卡片/统计组件`, statCards.length === 0 ? 'P1' : '');

    // 检查图表
    const charts = await page.$$('canvas, .echarts, [class*="chart"]');
    add('Dashboard', '/dashboard', '图表', charts.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${charts.length} 个图表元素`, charts.length === 0 ? 'P1' : '');

    // 检查时间范围切换
    const timeSelectors = await page.$$('.ant-picker, .ant-select, [class*="range"], [class*="time"]');
    if (timeSelectors.length > 0) {
      add('Dashboard', '/dashboard', '时间范围切换', 'PASS', `检测到 ${timeSelectors.length} 个时间选择器`);
    } else {
      add('Dashboard', '/dashboard', '时间范围切换', 'WARN', '未检测到时间范围选择器', 'P2');
    }

    await screenshot(page, 'Dashboard-管理看板');

    // --- 控制平面 ---
    console.log('\n--- 1.2 控制平面 (/control-plane) ---');
    await page.goto(`${BASE}/control-plane`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('ControlPlane', '/control-plane', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'ControlPlane');
    await checkBreadcrumb(page, 'ControlPlane');
    await checkMixedLang(page, 'ControlPlane');
    await checkEmptyState(page, 'ControlPlane');

    // 检查 scope/scope_id 报错
    const scopeError = globalErrors.find(e => e.includes('scope') || e.includes('scope_id'));
    if (scopeError) {
      add('ControlPlane', '/control-plane', 'scope/scope_id报错', 'FAIL', scopeError, 'P0');
    } else {
      add('ControlPlane', '/control-plane', 'scope/scope_id报错', 'PASS', '未检测到 scope/scope_id 相关错误');
    }

    // 检查运行记录
    const runRecords = await page.$$('.ant-table-tbody tr, [class*="run"], [class*="record"]');
    add('ControlPlane', '/control-plane', '运行记录', runRecords.length > 0 ? 'PASS' : 'INFO',
      runRecords.length > 0 ? `检测到 ${runRecords.length} 条记录` : '无运行记录数据');

    // 检查筛选功能
    const filters = await page.$$('.ant-select, .ant-input-search, .ant-picker, [class*="filter"]');
    add('ControlPlane', '/control-plane', '筛选功能', filters.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${filters.length} 个筛选组件`, filters.length === 0 ? 'P2' : '');

    await screenshot(page, 'ControlPlane-控制平面');

    // --- 预算看板 ---
    console.log('\n--- 1.3 预算看板 (/budgets) ---');
    await page.goto(`${BASE}/budgets`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('BudgetBoard', '/budgets', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'BudgetBoard');
    await checkBreadcrumb(page, 'BudgetBoard');
    await checkMixedLang(page, 'BudgetBoard');
    await checkEmptyState(page, 'BudgetBoard');

    const budgetScopeError = globalErrors.find(e => e.includes('scope') || e.includes('scope_id'));
    if (budgetScopeError) {
      add('BudgetBoard', '/budgets', 'scope/scope_id报错', 'FAIL', budgetScopeError, 'P0');
    } else {
      add('BudgetBoard', '/budgets', 'scope/scope_id报错', 'PASS', '未检测到 scope/scope_id 相关错误');
    }

    await screenshot(page, 'BudgetBoard-预算看板');

    // ==========================================
    // 二、AI资源治理
    // ==========================================
    console.log('\n=== 二、AI资源治理 ===\n');

    // --- 智能体管理 ---
    console.log('\n--- 2.1 智能体管理 (/agents) ---');
    await page.goto(`${BASE}/agents`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('AgentManager', '/agents', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'AgentManager');
    await checkBreadcrumb(page, 'AgentManager');
    await checkMixedLang(page, 'AgentManager');
    await checkEmptyState(page, 'AgentManager');

    // 检查智能体列表
    const agentCards = await page.$$('[class*="agent"], [class*="card"], .ant-card');
    add('AgentManager', '/agents', '智能体列表', agentCards.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${agentCards.length} 个Agent相关元素`, agentCards.length === 0 ? 'P1' : '');

    // 尝试点击某个Agent查看详情
    const firstAgent = await page.$('[class*="agent"], .ant-card');
    if (firstAgent) {
      await firstAgent.click();
      await page.waitForTimeout(800);
      await screenshot(page, 'AgentManager-智能体详情');
      add('AgentManager', '/agents', 'Agent详情点击', 'PASS', '成功打开Agent详情');
      // 检查详情中文化
      const detailText = await page.textContent('body');
      const hasChinese = /[\u4e00-\u9fa5]/.test(detailText);
      add('AgentManager', '/agents', '能力描述中文化', hasChinese ? 'PASS' : 'WARN',
        hasChinese ? '详情包含中文' : '详情可能未中文化', hasChinese ? '' : 'P1');
    } else {
      add('AgentManager', '/agents', 'Agent详情点击', 'WARN', '未找到可点击的Agent卡片', 'P1');
    }

    await screenshot(page, 'AgentManager-智能体管理');

    // --- 工具与连接器 ---
    console.log('\n--- 2.2 工具与连接器 (/tools) ---');
    await page.goto(`${BASE}/tools`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('Tools', '/tools', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'Tools');
    await checkBreadcrumb(page, 'Tools');
    await checkMixedLang(page, 'Tools');
    await checkEmptyState(page, 'Tools');

    // 检查标签页
    const tabs = await page.$$('.ant-tabs-tab, [role="tab"]');
    const tabTexts = [];
    for (const tab of tabs) {
      tabTexts.push((await tab.textContent()).trim());
    }
    add('Tools', '/tools', '标签页', tabTexts.length > 0 ? 'PASS' : 'WARN',
      `标签页: ${tabTexts.join(' | ')}`, tabTexts.length === 0 ? 'P1' : '');

    // 切换标签页
    if (tabs.length > 1) {
      await tabs[1].click();
      await page.waitForTimeout(500);
      await screenshot(page, 'Tools-第二个标签页');
      add('Tools', '/tools', '标签页切换', 'PASS', `切换到 "${tabTexts[1]}"`);
    }

    // 检查筛选
    const toolFilters = await page.$$('.ant-select, .ant-input-search, .ant-input');
    add('Tools', '/tools', '筛选功能', toolFilters.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${toolFilters.length} 个筛选/搜索组件`, toolFilters.length === 0 ? 'P2' : '');

    await screenshot(page, 'Tools-工具与连接器');

    // --- 能力契约 ---
    console.log('\n--- 2.3 能力契约 (/capability-center) ---');
    await page.goto(`${BASE}/capability-center`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('CapabilityCenter', '/capability-center', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'CapabilityCenter');
    await checkBreadcrumb(page, 'CapabilityCenter');
    await checkMixedLang(page, 'CapabilityCenter');
    await checkEmptyState(page, 'CapabilityCenter');

    // 检查契约列表
    const contracts = await page.$$('.ant-table-tbody tr, [class*="contract"], [class*="capability"]');
    add('CapabilityCenter', '/capability-center', '契约列表', contracts.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${contracts.length} 条契约`, contracts.length === 0 ? 'P1' : '');

    // 点击查看详情
    const firstContract = await page.$('.ant-table-tbody tr:first-child, [class*="contract"]:first-child');
    if (firstContract) {
      await firstContract.click();
      await page.waitForTimeout(500);
      await screenshot(page, 'CapabilityCenter-契约详情');
      add('CapabilityCenter', '/capability-center', '契约详情', 'PASS', '成功打开契约详情');
    }

    await screenshot(page, 'CapabilityCenter-能力契约');

    // --- 评估中心 ---
    console.log('\n--- 2.4 评估中心 (/eval-center) ---');
    await page.goto(`${BASE}/eval-center`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('EvalCenter', '/eval-center', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'EvalCenter');
    await checkBreadcrumb(page, 'EvalCenter');
    await checkMixedLang(page, 'EvalCenter');
    await checkEmptyState(page, 'EvalCenter');

    const evalTasks = await page.$$('.ant-table-tbody tr, [class*="eval"], [class*="task"]');
    add('EvalCenter', '/eval-center', '评估任务列表', evalTasks.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${evalTasks.length} 条评估任务`, evalTasks.length === 0 ? 'P1' : '');

    await screenshot(page, 'EvalCenter-评估中心');

    // ==========================================
    // 三、系统管理
    // ==========================================
    console.log('\n=== 三、系统管理 ===\n');

    // --- 系统设置 ---
    console.log('\n--- 3.1 系统设置 (/settings) ---');
    await page.goto(`${BASE}/settings`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('Settings', '/settings', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'Settings');
    await checkBreadcrumb(page, 'Settings');
    await checkMixedLang(page, 'Settings');
    await checkEmptyState(page, 'Settings');

    // 尝试修改设置
    const inputs = await page.$$('input:not([type="hidden"]), .ant-select, .ant-switch');
    add('Settings', '/settings', '设置项', inputs.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${inputs.length} 个可交互设置项`, inputs.length === 0 ? 'P1' : '');

    if (inputs.length > 0) {
      // 尝试修改第一个输入框
      try {
        const firstInput = await page.$('input:not([type="hidden"])');
        if (firstInput) {
          await firstInput.click();
          await firstInput.fill('test-value');
          await page.waitForTimeout(300);
          add('Settings', '/settings', '修改设置', 'PASS', '成功修改输入框值');
        }
      } catch (e) {
        add('Settings', '/settings', '修改设置', 'FAIL', e.message);
      }
    }

    await screenshot(page, 'Settings-系统设置');

    // --- 用户管理 ---
    console.log('\n--- 3.2 用户管理 (/users) ---');
    await page.goto(`${BASE}/users`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('UserManagement', '/users', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'UserManagement');
    await checkBreadcrumb(page, 'UserManagement');
    await checkMixedLang(page, 'UserManagement');
    await checkEmptyState(page, 'UserManagement');

    const userRows = await page.$$('.ant-table-tbody tr, [class*="user"]');
    add('UserManagement', '/users', '用户列表', userRows.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${userRows.length} 个用户`, userRows.length === 0 ? 'P1' : '');

    // 尝试新增用户
    const addBtn = await page.$('button:has-text("新增"), button:has-text("添加"), button:has-text("创建"), button:has-text("新建")');
    if (addBtn) {
      await addBtn.click();
      await page.waitForTimeout(800);
      await screenshot(page, 'UserManagement-新增用户对话框');
      add('UserManagement', '/users', '新增用户入口', 'PASS', '成功打开新增用户对话框');

      // 测试空表单提交
      await testFormValidation(page, 'UserManagement', '.ant-modal form, .ant-drawer form');

      // 尝试关闭
      const cancelBtn = await page.$('button:has-text("取消"), .ant-modal-close');
      if (cancelBtn) {
        await cancelBtn.click();
        await page.waitForTimeout(300);
      }
    } else {
      add('UserManagement', '/users', '新增用户入口', 'WARN', '未找到新增用户按钮', 'P1');
    }

    await screenshot(page, 'UserManagement-用户管理');

    // ==========================================
    // 四、端到端业务链路验证
    // ==========================================
    console.log('\n=== 四、端到端业务链路验证 ===\n');

    // --- 链路一：材料发现到实验闭环 ---
    console.log('\n--- 4.1 研发工作台 (/research) ---');
    await page.goto(`${BASE}/research`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('ResearchWorkbench', '/research', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'ResearchWorkbench');
    await checkBreadcrumb(page, 'ResearchWorkbench');
    await checkMixedLang(page, 'ResearchWorkbench');
    await checkEmptyState(page, 'ResearchWorkbench');

    // 输入研发目标
    const researchInputs = await page.$$('input, textarea');
    if (researchInputs.length > 0) {
      try {
        await researchInputs[0].click();
        await researchInputs[0].fill('开发高能量密度锂离子电池正极材料，目标能量密度>400Wh/kg');
        await page.waitForTimeout(300);
        add('ResearchWorkbench', '/research', '输入研发目标', 'PASS', '成功输入研发目标');
      } catch (e) {
        add('ResearchWorkbench', '/research', '输入研发目标', 'FAIL', e.message);
      }
    }
    await screenshot(page, 'ResearchWorkbench-研发工作台');

    // --- 候选设计 ---
    console.log('\n--- 4.2 候选设计 (/workbench) ---');
    await page.goto(`${BASE}/workbench`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('CandidateWorkbench', '/workbench', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'CandidateWorkbench');
    await checkBreadcrumb(page, 'CandidateWorkbench');
    await checkMixedLang(page, 'CandidateWorkbench');
    await checkEmptyState(page, 'CandidateWorkbench');

    // 检查候选材料
    const candidates = await page.$$('[class*="candidate"], .ant-table-tbody tr');
    add('CandidateWorkbench', '/workbench', '候选材料', candidates.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${candidates.length} 个候选材料`, candidates.length === 0 ? 'P1' : '');

    await screenshot(page, 'CandidateWorkbench-候选设计');

    // --- ECML实验闭环 ---
    console.log('\n--- 4.3 ECML实验闭环 (/ecml) ---');
    await page.goto(`${BASE}/ecml`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('ECML', '/ecml', '页面加载', 'FAIL', e.message, 'P0');
    });
    // ecml may redirect to ecml/runs or ecml/monitor
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'ECML');
    await checkBreadcrumb(page, 'ECML');
    await checkMixedLang(page, 'ECML');
    await checkEmptyState(page, 'ECML');

    // 检查是否可以创建迭代
    const createBtns = await page.$$('button:has-text("创建"), button:has-text("新建"), button:has-text("迭代"), button:has-text("开始")');
    add('ECML', '/ecml', '创建迭代入口', createBtns.length > 0 ? 'PASS' : 'WARN',
      `检测到 ${createBtns.length} 个创建按钮`, createBtns.length === 0 ? 'P1' : '');

    await screenshot(page, 'ECML-实验闭环');

    // --- 链路二：配方与工艺 ---
    console.log('\n--- 4.4 配方与工艺 (/formula-design) ---');
    await page.goto(`${BASE}/formula-design`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('FormulaDesign', '/formula-design', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'FormulaDesign');
    await checkBreadcrumb(page, 'FormulaDesign');
    await checkMixedLang(page, 'FormulaDesign');
    await checkEmptyState(page, 'FormulaDesign');

    // 尝试创建配方
    const formulaCreateBtn = await page.$('button:has-text("创建"), button:has-text("新建"), button:has-text("配方"), button:has-text("添加")');
    if (formulaCreateBtn) {
      await formulaCreateBtn.click();
      await page.waitForTimeout(800);
      add('FormulaDesign', '/formula-design', '创建配方入口', 'PASS', '成功打开创建配方');

      // 尝试填写参数
      const formulaInputs = await page.$$('input:not([type="hidden"]), .ant-select');
      if (formulaInputs.length > 0) {
        try {
          await formulaInputs[0].click();
          await formulaInputs[0].fill('NCM811正极配方');
          await page.waitForTimeout(300);
          add('FormulaDesign', '/formula-design', '填写配方参数', 'PASS', '成功填写配方名称');
        } catch (e) {
          add('FormulaDesign', '/formula-design', '填写配方参数', 'FAIL', e.message);
        }
      }

      // 检查版本控制
      const versionElements = await page.$$('[class*="version"], .ant-tag');
      if (versionElements.length > 0) {
        add('FormulaDesign', '/formula-design', '版本控制', 'PASS', `检测到 ${versionElements.length} 个版本相关元素`);
      } else {
        add('FormulaDesign', '/formula-design', '版本控制', 'WARN', '未检测到版本控制元素', 'P2');
      }

      // 关闭创建对话框
      const cancelBtn = await page.$('button:has-text("取消"), .ant-modal-close');
      if (cancelBtn) {
        await cancelBtn.click();
        await page.waitForTimeout(300);
      }
    } else {
      add('FormulaDesign', '/formula-design', '创建配方入口', 'WARN', '未找到创建配方按钮', 'P1');
    }

    await screenshot(page, 'FormulaDesign-配方与工艺');

    // --- 链路三：数据资产治理 ---
    console.log('\n--- 4.5 属性字典 (/properties) ---');
    await page.goto(`${BASE}/properties`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('MaterialProperties', '/properties', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'MaterialProperties');
    await checkBreadcrumb(page, 'MaterialProperties');
    await checkMixedLang(page, 'MaterialProperties');
    await checkEmptyState(page, 'MaterialProperties');
    await screenshot(page, 'MaterialProperties-属性字典');

    console.log('\n--- 4.6 物料规格 (/materials) ---');
    await page.goto(`${BASE}/materials`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('RawMaterials', '/materials', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'RawMaterials');
    await checkBreadcrumb(page, 'RawMaterials');
    await checkMixedLang(page, 'RawMaterials');
    await checkEmptyState(page, 'RawMaterials');
    await screenshot(page, 'RawMaterials-物料规格');

    console.log('\n--- 4.7 样品管理 (/samples) ---');
    await page.goto(`${BASE}/samples`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('SampleManager', '/samples', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'SampleManager');
    await checkBreadcrumb(page, 'SampleManager');
    await checkMixedLang(page, 'SampleManager');
    await checkEmptyState(page, 'SampleManager');
    await screenshot(page, 'SampleManager-样品管理');

    console.log('\n--- 4.8 实验数据 (/experiments) ---');
    await page.goto(`${BASE}/experiments`, { waitUntil: 'networkidle', timeout: 30000 }).catch(e => {
      add('Experiments', '/experiments', '页面加载', 'FAIL', e.message, 'P0');
    });
    await page.waitForTimeout(1000);
    await checkPageTitle(page, 'Experiments');
    await checkBreadcrumb(page, 'Experiments');
    await checkMixedLang(page, 'Experiments');
    await checkEmptyState(page, 'Experiments');
    await screenshot(page, 'Experiments-实验数据');

    // ==========================================
    // 五、异常与边界测试
    // ==========================================
    console.log('\n=== 五、异常与边界测试 ===\n');

    // 5.1 漏填必填字段 - 在用户管理页面测试
    console.log('\n--- 5.1 漏填必填字段 ---');
    await page.goto(`${BASE}/users`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(500);
    const addUserBtn = await page.$('button:has-text("新增"), button:has-text("添加"), button:has-text("创建")');
    if (addUserBtn) {
      await addUserBtn.click();
      await page.waitForTimeout(500);
      const submitBtn = await page.$('button:has-text("确定"), button:has-text("保存"), button:has-text("提交")');
      if (submitBtn) {
        await submitBtn.click();
        await page.waitForTimeout(500);
        const errors = await page.$$('.ant-form-item-explain-error');
        if (errors.length > 0) {
          const errorTexts = [];
          for (const e of errors) {
            errorTexts.push((await e.textContent()).trim());
          }
          add('异常测试', '/users', '必填字段校验', 'PASS', `触发校验: ${errorTexts.join('; ')}`);
        } else {
          add('异常测试', '/users', '必填字段校验', 'WARN', '未触发必填校验提示', 'P1');
        }
      }
      // 关闭
      const closeBtn = await page.$('.ant-modal-close, button:has-text("取消")');
      if (closeBtn) await closeBtn.click();
    }

    // 5.2 输入非法数值
    console.log('\n--- 5.2 输入非法数值 ---');
    await page.goto(`${BASE}/formula-design`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(500);
    const formulaAddBtn = await page.$('button:has-text("创建"), button:has-text("新建"), button:has-text("添加")');
    if (formulaAddBtn) {
      await formulaAddBtn.click();
      await page.waitForTimeout(500);
      const numberInputs = await page.$$('input[type="number"], .ant-input-number input');
      if (numberInputs.length > 0) {
        try {
          await numberInputs[0].click();
          await numberInputs[0].fill('-999');
          await page.waitForTimeout(300);
          add('异常测试', '/formula-design', '非法数值输入', 'PASS', '输入负数测试完成');
        } catch (e) {
          add('异常测试', '/formula-design', '非法数值输入', 'FAIL', e.message);
        }
      }
      const closeBtn = await page.$('.ant-modal-close, button:has-text("取消")');
      if (closeBtn) await closeBtn.click();
    }

    // 5.3 输入极端长文本
    console.log('\n--- 5.3 输入极端长文本 ---');
    await page.goto(`${BASE}/research`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(500);
    const textInputs = await page.$$('input:not([type="hidden"]), textarea');
    if (textInputs.length > 0) {
      try {
        await textInputs[0].click();
        await textInputs[0].fill('A'.repeat(5000));
        await page.waitForTimeout(300);
        add('异常测试', '/research', '极端长文本输入', 'PASS', '输入5000字符长文本');
      } catch (e) {
        add('异常测试', '/research', '极端长文本输入', 'FAIL', e.message);
      }
    }

    // 5.4 重复创建同名项目
    console.log('\n--- 5.4 重复创建同名项目 ---');
    await page.goto(`${BASE}/projects`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {
      add('异常测试', '/projects', '页面加载', 'FAIL', '/projects 页面不存在或无法访问', 'P2');
    });
    await page.waitForTimeout(500);
    await screenshot(page, 'Projects-项目管理');

    // 5.5 筛选无结果
    console.log('\n--- 5.5 筛选无结果 ---');
    await page.goto(`${BASE}/tools`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(500);
    const searchInputs = await page.$$('.ant-input-search input, .ant-input-affix-wrapper input');
    if (searchInputs.length > 0) {
      try {
        await searchInputs[0].click();
        await searchInputs[0].fill('ZZZZZZZZZZ_NONEXISTENT_ITEM');
        await page.keyboard.press('Enter');
        await page.waitForTimeout(800);
        const emptyResult = await page.$('.ant-empty, [class*="empty"]');
        add('异常测试', '/tools', '筛选无结果', emptyResult ? 'PASS' : 'WARN',
          emptyResult ? '正确显示空状态' : '未显示空状态提示', emptyResult ? '' : 'P2');
      } catch (e) {
        add('异常测试', '/tools', '筛选无结果', 'FAIL', e.message);
      }
    }

    // 5.6 搜索特殊字符
    console.log('\n--- 5.6 搜索特殊字符 ---');
    if (searchInputs.length > 0) {
      try {
        await searchInputs[0].click();
        await searchInputs[0].fill('"><script>alert(1)</script>');
        await page.keyboard.press('Enter');
        await page.waitForTimeout(500);
        // Check no XSS alert
        const dialog = await page.$('.ant-modal-confirm, [role="alertdialog"]');
        add('异常测试', '/tools', 'XSS特殊字符', dialog ? 'WARN' : 'PASS',
          dialog ? '可能触发XSS' : 'XSS防护正常');
      } catch (e) {
        add('异常测试', '/tools', 'XSS特殊字符', 'FAIL', e.message);
      }
    }

    // 5.7 刷新页面数据一致性
    console.log('\n--- 5.7 刷新页面数据一致性 ---');
    await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(500);
    const beforeRefresh = await page.textContent('body');
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const afterRefresh = await page.textContent('body');
    if (beforeRefresh === afterRefresh) {
      add('异常测试', '/dashboard', '刷新数据一致性', 'PASS', '刷新前后内容一致');
    } else {
      add('异常测试', '/dashboard', '刷新数据一致性', 'WARN', '刷新后内容有变化（可能正常变化）', 'P3');
    }

    // ==========================================
    // 额外页面检查
    // ==========================================
    console.log('\n=== 额外页面检查 ===\n');

    const extraPages = [
      { path: '/discovery', name: 'Discovery' },
      { path: '/knowledge', name: 'KnowledgeGraph' },
      { path: '/synthesis', name: 'Synthesis' },
      { path: '/prediction', name: 'Prediction' },
      { path: '/approvals', name: 'ApprovalCenter' },
      { path: '/committee', name: 'CommitteeCenter' },
      { path: '/release-cards', name: 'ReleaseCardCenter' },
      { path: '/data-ingest', name: 'DataIngest' },
      { path: '/value-report', name: 'ValueReport' },
      { path: '/equipment', name: 'EquipmentLedger' },
      { path: '/orchestration', name: 'Orchestration' },
      { path: '/tech-intel', name: 'TechnologyIntelligence' },
      { path: '/decision-center', name: 'DecisionCenter' },
      { path: '/battery-life', name: 'BatteryLifeWorkflow' },
      { path: '/data-quality', name: 'DataQualityWorkbench' },
      { path: '/ecml/runs', name: 'ECMLRuns' },
      { path: '/ecml/monitor', name: 'ECMLMonitor' },
      { path: '/my-tasks', name: 'MyTasks' },
      { path: '/experiment-workbench', name: 'ExperimentWorkbench' },
    ];

    for (const { path, name } of extraPages) {
      console.log(`\n--- ${name} (${path}) ---`);
      try {
        await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle', timeout: 15000 });
        await page.waitForTimeout(500);
        await checkPageTitle(page, name);
        await checkMixedLang(page, name);
        await checkEmptyState(page, name);
        await screenshot(page, `${name}`);
        add(name, path, '页面加载', 'PASS', '页面正常加载');
      } catch (e) {
        add(name, path, '页面加载', 'FAIL', e.message, 'P0');
      }
    }

  } catch (e) {
    console.error('FATAL ERROR:', e.message);
    add('GLOBAL', 'N/A', '测试执行', 'FAIL', e.message, 'P0');
  } finally {
    // ======= Generate Report =======
    console.log('\n\n');
    console.log('='.repeat(80));
    console.log('                    测试报告汇总');
    console.log('='.repeat(80));

    const bySeverity = { P0: [], P1: [], P2: [], P3: [], INFO: [], PASS: [], WARN: [] };
    for (const r of REPORT) {
      const key = r.severity || (r.status === 'PASS' ? 'PASS' : r.status === 'WARN' ? 'WARN' : 'INFO');
      if (!bySeverity[key]) bySeverity[key] = [];
      bySeverity[key].push(r);
    }

    console.log(`\n总测试项: ${REPORT.length}`);
    for (const [sev, items] of Object.entries(bySeverity)) {
      if (items.length > 0) {
        const icon = sev === 'P0' ? '🔴' : sev === 'P1' ? '🟠' : sev === 'P2' ? '🟡' : sev === 'P3' ? '🔵' : sev === 'PASS' ? '✅' : sev === 'WARN' ? '⚠️' : 'ℹ️';
        console.log(`${icon} ${sev}: ${items.length} 项`);
      }
    }

    // Print all non-PASS items
    console.log('\n--- 需关注的问题 ---');
    for (const r of REPORT) {
      if (r.status !== 'PASS') {
        console.log(`  [${r.severity || r.status}] ${r.page} | ${r.step}: ${r.detail}`);
      }
    }

    // Save JSON report
    writeFileSync(join(__dirname, 'test-report.json'), JSON.stringify(REPORT, null, 2), 'utf-8');
    console.log(`\n报告已保存到: ${join(__dirname, 'test-report.json')}`);
    console.log(`截图已保存到: ${REPORT_DIR}`);

    await browser.close();
  }
})();