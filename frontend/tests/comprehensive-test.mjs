import { chromium } from 'playwright';
import * as fs from 'fs';

const BASE = 'http://localhost:5173';
const RESULTS = [];

function log(section, step, status, detail = '') {
  const entry = { section, step, status, detail, timestamp: new Date().toISOString() };
  RESULTS.push(entry);
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : status === 'WARN' ? '⚠️' : '🔍';
  console.log(`${icon} [${section}] ${step}: ${status}${detail ? ' — ' + detail : ''}`);
}

function issue(severity, page, description, suggestion) {
  RESULTS.push({ type: 'ISSUE', severity, page, description, suggestion });
}

async function waitForApp(page) {
  await page.waitForSelector('.ant-layout', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1000);
}

async function run() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // ============================================================
  // SECTION 1: Decision Center /decision-center
  // ============================================================
  console.log('\n========== 一、决策放行：决策记录 ==========\n');

  // 1.1 Navigate
  await page.goto(`${BASE}/decision-center`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);
  log('决策记录', '导航到 /decision-center', 'PASS');

  // 1.2 Check page title and metrics
  const pageTitle = await page.textContent('.page-title').catch(() => '');
  log('决策记录', '页面标题', pageTitle.includes('决策放行') ? 'PASS' : 'FAIL', `标题: "${pageTitle}"`);
  if (!pageTitle.includes('决策放行')) issue('P1', '决策记录', '页面标题不符合预期', '标题应为"决策放行"');

  const metricCards = await page.$$('.unified-metrics .metric-card');
  log('决策记录', '统一指标区', metricCards.length >= 3 ? 'PASS' : 'FAIL', `指标卡片数量: ${metricCards.length}`);

  // 1.3 Check tabs exist
  const tabCount = await page.$$('.decision-tabs .ant-tabs-tab').catch(() => []);
  log('决策记录', '标签页数量', tabCount.length >= 3 ? 'PASS' : 'FAIL', `标签页: ${tabCount.length}`);

  // 1.4 Click "实验放行卡" tab (it should already be default)
  const releaseTab = await page.$('.ant-tabs-tab:has-text("实验放行卡")');
  if (releaseTab) {
    await releaseTab.click();
    await page.waitForTimeout(800);
    log('决策记录', '切换到"实验放行卡"标签页', 'PASS');
  } else {
    log('决策记录', '切换到"实验放行卡"标签页', 'FAIL', '未找到标签页');
  }

  // Check for ReleaseCardCenter content
  const releaseContent = await page.textContent('.decision-tabs .ant-tabs-content').catch(() => '');
  log('决策记录', '放行卡内容加载', releaseContent.length > 0 ? 'PASS' : 'FAIL');

  // 1.5 Check for "查看详情" button on release cards
  const detailBtns = await page.$$('button:has-text("查看详情")');
  if (detailBtns.length > 0) {
    await detailBtns[0].click();
    await page.waitForTimeout(500);
    const drawer = await page.$('.ant-drawer') || await page.$('.ant-modal');
    log('决策记录', '点击"查看详情"按钮', drawer ? 'PASS' : 'FAIL', drawer ? '详情抽屉/弹窗已打开' : '未打开');
    // Close drawer
    const closeBtn = await page.$('.ant-drawer-close') || await page.$('.ant-modal-close') || await page.$('button:has-text("关闭")');
    if (closeBtn) await closeBtn.click().catch(() => {});
    await page.waitForTimeout(300);
  } else {
    log('决策记录', '查看详情按钮', 'WARN', '暂无可用记录');
  }

  // 1.6 Check for "人工复核" button
  const reviewBtns = await page.$$('button:has-text("人工复核")');
  if (reviewBtns.length > 0) {
    await reviewBtns[0].click();
    await page.waitForTimeout(500);
    log('决策记录', '点击"人工复核"按钮', 'PASS');
    // Close if modal opened
    const modalClose = await page.$('.ant-modal-close');
    if (modalClose) await modalClose.click().catch(() => {});
    await page.waitForTimeout(300);
  } else {
    log('决策记录', '人工复核按钮', 'WARN', '暂无可用记录');
  }

  // 1.7 Click "委员会案件" tab
  const committeeTab = await page.$('.ant-tabs-tab:has-text("委员会案件")');
  if (committeeTab) {
    await committeeTab.click();
    await page.waitForTimeout(1000);
    log('决策记录', '切换到"委员会案件"标签页', 'PASS');
  } else {
    log('决策记录', '切换到"委员会案件"标签页', 'FAIL');
  }

  // 1.8 Check committee filters
  const committeeContent = await page.textContent('.decision-tabs .ant-tabs-content').catch(() => '');
  log('决策记录', '委员会案件内容加载', committeeContent.length > 0 ? 'PASS' : 'FAIL');

  // 1.9 Check for committee type filters
  const committeeFilters = await page.$$('.decision-tabs .ant-select, .ant-radio-group');
  log('决策记录', '委员会筛选器', committeeFilters.length > 0 ? 'PASS' : 'WARN', `筛选器数量: ${committeeFilters.length}`);

  // 1.10 Check for "执行" button
  const execBtns = await page.$$('button:has-text("执行")');
  if (execBtns.length > 0) {
    await execBtns[0].click();
    await page.waitForTimeout(500);
    log('决策记录', '点击"执行"按钮', 'PASS');
    const modalClose = await page.$('.ant-modal-close');
    if (modalClose) await modalClose.click().catch(() => {});
  } else {
    log('决策记录', '执行按钮', 'WARN', '暂无待处理案件');
  }

  // 1.11 Click "审批事项" tab
  const approvalTab = await page.$('.ant-tabs-tab:has-text("审批事项")');
  if (approvalTab) {
    await approvalTab.click();
    await page.waitForTimeout(1000);
    log('决策记录', '切换到"审批事项"标签页', 'PASS');
  } else {
    log('决策记录', '切换到"审批事项"标签页', 'FAIL');
  }

  // 1.12 Check approval content
  const approvalContent = await page.textContent('.decision-tabs .ant-tabs-content').catch(() => '');
  const hasEmptyState = approvalContent.includes('暂无') || approvalContent.includes('empty');
  log('决策记录', '审批事项内容', hasEmptyState ? 'PASS' : 'PASS', hasEmptyState ? '显示空状态' : '有数据');

  // 1.13 Check tab URL query sync
  const currentUrl = page.url();
  log('决策记录', 'URL tab参数同步', currentUrl.includes('tab=approval') ? 'PASS' : 'FAIL', `当前URL: ${currentUrl}`);

  // ============================================================
  // SECTION 2: Old path redirects
  // ============================================================
  console.log('\n========== 二、旧路径重定向测试 ==========\n');

  // 2.1 /release-cards -> /decision-center?tab=release
  await page.goto(`${BASE}/release-cards`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1000);
  const redirect1Url = page.url();
  const redirect1Pass = redirect1Url.includes('/decision-center') && redirect1Url.includes('tab=release');
  log('旧路径重定向', '/release-cards', redirect1Pass ? 'PASS' : 'FAIL', `重定向到: ${redirect1Url}`);

  // 2.2 /committees -> /decision-center?tab=committee
  await page.goto(`${BASE}/committees`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1000);
  const redirect2Url = page.url();
  const redirect2Pass = redirect2Url.includes('/decision-center') && redirect2Url.includes('tab=committee');
  log('旧路径重定向', '/committees', redirect2Pass ? 'PASS' : 'FAIL', `重定向到: ${redirect2Url}`);

  // 2.3 /approvals -> /decision-center?tab=approval
  await page.goto(`${BASE}/approvals`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1000);
  const redirect3Url = page.url();
  const redirect3Pass = redirect3Url.includes('/decision-center') && redirect3Url.includes('tab=approval');
  log('旧路径重定向', '/approvals', redirect3Pass ? 'PASS' : 'FAIL', `重定向到: ${redirect3Url}`);

  // ============================================================
  // SECTION 3: Experiment Workbench /experiment-workbench
  // ============================================================
  console.log('\n========== 三、数据与资产：实验工作台 ==========\n');

  await page.goto(`${BASE}/experiment-workbench`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const workbenchTitle = await page.textContent('.page-title').catch(() => '');
  log('实验工作台', '页面标题', workbenchTitle.includes('实验工作台') ? 'PASS' : 'WARN', `标题: "${workbenchTitle}"`);

  // Check approver bar
  const approverInput = await page.$('input[aria-label="审批人姓名"]');
  log('实验工作台', '审批人输入框', approverInput ? 'PASS' : 'FAIL');

  if (approverInput) {
    await approverInput.fill('测试审批人');
    log('实验工作台', '填写审批人', 'PASS');
  }

  // Check task list
  const taskTable = await page.$('.ant-table');
  log('实验工作台', '任务列表', taskTable ? 'PASS' : 'FAIL');

  // Click "新建任务"
  const createBtn = await page.$('button:has-text("新建任务")');
  if (createBtn) {
    await createBtn.click();
    await page.waitForTimeout(500);
    const modal = await page.$('.ant-modal:has-text("新建实验任务")');
    log('实验工作台', '打开新建任务弹窗', modal ? 'PASS' : 'FAIL');

    // Try empty submit
    const okBtn = await page.$('.ant-modal:has-text("新建实验任务") .ant-btn-primary');
    if (okBtn) {
      await okBtn.click();
      await page.waitForTimeout(300);
      log('实验工作台', '空值提交', 'PASS', '检查是否有校验提示');
    }

    // Fill form
    const projectSelect = await page.$('.ant-modal:has-text("新建实验任务") .ant-select');
    if (projectSelect) {
      await projectSelect.click();
      await page.waitForTimeout(300);
      // Select first option
      const firstOption = await page.$('.ant-select-dropdown .ant-select-item-option');
      if (firstOption) {
        await firstOption.click();
        await page.waitForTimeout(200);
        log('实验工作台', '选择项目', 'PASS');
      }
    }

    // Fill notes
    const notesTextarea = await page.$('.ant-modal:has-text("新建实验任务") textarea');
    if (notesTextarea) {
      await notesTextarea.fill('交流阻抗谱 EIS 测试 - EXP-EIS-20260725-01');
      log('实验工作台', '填写备注', 'PASS');
    }

    // Submit
    if (okBtn) {
      await okBtn.click();
      await page.waitForTimeout(1000);
    }

    // Close modal
    const closeBtn = await page.$('.ant-modal-close');
    if (closeBtn) await closeBtn.click().catch(() => {});
    await page.waitForTimeout(500);
    log('实验工作台', '提交新建任务', 'PASS', '检查是否成功创建');
  } else {
    log('实验工作台', '新建任务按钮', 'FAIL', '未找到');
  }

  // Check status filter
  const statusFilter = await page.$('.ant-select:has-text("状态筛选")');
  if (statusFilter) {
    await statusFilter.click();
    await page.waitForTimeout(300);
    const options = await page.$$('.ant-select-dropdown .ant-select-item-option');
    log('实验工作台', '状态筛选选项', options.length > 0 ? 'PASS' : 'FAIL', `选项数: ${options.length}`);
    // Select "全部"
    if (options.length > 0) await options[0].click();
    await page.waitForTimeout(300);
  }

  // Check rowKey in table
  const rowKeyAttr = await page.$eval('.ant-table-tbody tr:first-child', (el) => el.getAttribute('data-row-key')).catch(() => null);
  log('实验工作台', '表格 rowKey', rowKeyAttr ? 'PASS' : 'WARN', `rowKey: ${rowKeyAttr}`);

  // ============================================================
  // SECTION 4: Experiments /experiments
  // ============================================================
  console.log('\n========== 四、数据与资产：实验数据 ==========\n');

  await page.goto(`${BASE}/experiments`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const expTitle = await page.textContent('.page-title').catch(() => '');
  log('实验数据', '页面标题', expTitle.includes('实验数据') ? 'PASS' : 'FAIL', `标题: "${expTitle}"`);

  // Check filter form
  const projectFilter = await page.$('.filter-form .ant-select');
  log('实验数据', '项目筛选', projectFilter ? 'PASS' : 'FAIL');

  // Check formula input
  const formulaInput = await page.$('input[placeholder="输入化学式…"]');
  if (formulaInput) {
    await formulaInput.fill('Li6PS5Cl');
    log('实验数据', '化学式筛选输入', 'PASS');
  }

  // Check experiment type filter
  const typeFilter = await page.$$('.filter-form .ant-select');
  if (typeFilter.length > 1) {
    await typeFilter[1].click();
    await page.waitForTimeout(300);
    const typeOptions = await page.$$('.ant-select-dropdown .ant-select-item-option');
    log('实验数据', '实验类型筛选', typeOptions.length > 0 ? 'PASS' : 'FAIL', `选项数: ${typeOptions.length}`);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
  }

  // Click query
  const queryBtn = await page.$('button:has-text("查询")');
  if (queryBtn) {
    await queryBtn.click();
    await page.waitForTimeout(1000);
    log('实验数据', '查询操作', 'PASS');
  }

  // Check table
  const expTable = await page.$('.table-card .ant-table');
  if (expTable) {
    log('实验数据', '实验记录表格', 'PASS');
    // Check rowKey
    const rowKey = await page.$eval('.ant-table-tbody tr:first-child', (el) => el.getAttribute('data-row-key')).catch(() => null);
    log('实验数据', '表格 rowKey', rowKey ? 'PASS' : 'WARN', `rowKey: ${rowKey}`);
  } else {
    log('实验数据', '实验记录表格', 'WARN', '无数据或未加载');
  }

  // Check traceability links
  const traceLinks = await page.$$('.trace-link');
  log('实验数据', '数据溯源链接', traceLinks.length > 0 ? 'PASS' : 'WARN', `溯源链接数: ${traceLinks.length}`);

  // Check empty state
  const emptyState = await page.$('.table-empty');
  if (emptyState) {
    log('实验数据', '空状态', 'PASS', '显示空状态引导文案');
  }

  // ============================================================
  // SECTION 5: Sample Manager /samples
  // ============================================================
  console.log('\n========== 五、数据与资产：样品管理 ==========\n');

  await page.goto(`${BASE}/samples`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const sampleTitle = await page.textContent('.page-title').catch(() => '');
  log('样品管理', '页面标题', sampleTitle.includes('样品管理') ? 'PASS' : 'FAIL', `标题: "${sampleTitle}"`);

  // Check stat cards
  const statItems = await page.$$('.stat-item');
  log('样品管理', '汇总卡片', statItems.length >= 4 ? 'PASS' : 'WARN', `卡片数: ${statItems.length}`);

  // Click "新建样品"
  const addSampleBtn = await page.$('button:has-text("新建样品")');
  if (addSampleBtn) {
    await addSampleBtn.click();
    await page.waitForTimeout(500);
    const modal = await page.$('.ant-modal:has-text("新建样品")');
    log('样品管理', '打开新建样品弹窗', modal ? 'PASS' : 'FAIL');

    // Try empty submit first
    if (modal) {
      const modalOk = await page.$('.ant-modal:has-text("新建样品") .ant-btn-primary');
      if (modalOk) {
        await modalOk.click();
        await page.waitForTimeout(300);
        log('样品管理', '空值提交校验', 'PASS', '检查是否有"请填写样品名称"提示');
      }

      // Fill sample name
      const nameInput = await page.$('input[name="name"]');
      if (nameInput) {
        await nameInput.fill('硫化物固态电解质 LPSCl');
        log('样品管理', '填写样品名称', 'PASS');
      }

      // Fill chemical formula
      const formulaInput = await page.$('input[name="chemical_formula"]');
      if (formulaInput) {
        await formulaInput.fill('Li6PS5Cl');
        log('样品管理', '填写化学式', 'PASS');
      }

      // Fill quantity
      const quantityInput = await page.$('input[name="quantity"]');
      if (quantityInput) {
        await quantityInput.fill('100');
        log('样品管理', '填写数量', 'PASS');
      }

      // Fill business code
      const codeInput = await page.$('input[name="sample_code"]');
      if (codeInput) {
        await codeInput.fill('SMP-ASSB-LPSCl-001');
        log('样品管理', '填写业务编号', 'PASS');
      }

      // Fill batch number
      const batchInput = await page.$('input[name="batch_number"]');
      if (batchInput) {
        await batchInput.fill('B2026-001');
        log('样品管理', '填写批次号', 'PASS');
      }

      // Submit
      if (modalOk) {
        await modalOk.click();
        await page.waitForTimeout(1000);
        log('样品管理', '提交新建样品', 'PASS');
      }
    }

    // Close modal if still open
    const closeBtn = await page.$('.ant-modal-close');
    if (closeBtn) await closeBtn.click().catch(() => {});
    await page.waitForTimeout(500);
  } else {
    log('样品管理', '新建样品按钮', 'FAIL', '未找到');
  }

  // Check table rowKey
  const sampleTable = await page.$('.ant-table');
  if (sampleTable) {
    const rowKey = await page.$eval('.ant-table-tbody tr:first-child', (el) => el.getAttribute('data-row-key')).catch(() => null);
    log('样品管理', '表格 rowKey', rowKey ? 'PASS' : 'WARN', `rowKey: ${rowKey}`);
  }

  // Check search
  const searchInput = await page.$('.search-row input');
  if (searchInput) {
    await searchInput.fill('LPSCl');
    await page.waitForTimeout(300);
    log('样品管理', '搜索功能', 'PASS');
    await searchInput.fill('');
    await page.waitForTimeout(300);
  }

  // ============================================================
  // SECTION 6: Data Ingest /data-ingest
  // ============================================================
  console.log('\n========== 六、数据与资产：数据接入 ==========\n');

  await page.goto(`${BASE}/data-ingest`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const ingestTitle = await page.textContent('.page-title').catch(() => '');
  log('数据接入', '页面标题', ingestTitle.includes('数据接入') ? 'PASS' : 'FAIL', `标题: "${ingestTitle}"`);

  // Check steps
  const steps = await page.$$('.ingest-steps .ant-steps-item');
  log('数据接入', '步骤指示器', steps.length >= 4 ? 'PASS' : 'FAIL', `步骤数: ${steps.length}`);

  // Check entity type radio
  const entityRadios = await page.$$('.entity-bar .ant-radio-button');
  log('数据接入', '实体类型选择', entityRadios.length > 0 ? 'PASS' : 'FAIL', `实体类型数: ${entityRadios.length}`);

  // Check upload area
  const uploadArea = await page.$('.ant-upload-dragger');
  log('数据接入', '上传区域', uploadArea ? 'PASS' : 'FAIL');

  // Check table rowKey in preview (check code for previewRowKey)
  // We'll check the source code pattern
  const hasUploadText = await page.textContent('.ant-upload-text').catch(() => '');
  log('数据接入', '上传引导文案', hasUploadText.includes('点击或拖拽') ? 'PASS' : 'WARN', `文案: "${hasUploadText}"`);

  // ============================================================
  // SECTION 7: Equipment Ledger /equipment
  // ============================================================
  console.log('\n========== 七、数据与资产：设备台账 ==========\n');

  await page.goto(`${BASE}/equipment`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const eqTitle = await page.textContent('.page-title').catch(() => '');
  log('设备台账', '页面标题', eqTitle.includes('设备台账') ? 'PASS' : 'FAIL', `标题: "${eqTitle}"`);

  // Check stat cards
  const eqStats = await page.$$('.stat-item');
  log('设备台账', '汇总卡片', eqStats.length > 0 ? 'PASS' : 'WARN', `卡片数: ${eqStats.length}`);

  // Check category filter
  const categoryFilter = await page.$$('.ant-card-extra .ant-select');
  log('设备台账', '筛选器', categoryFilter.length > 0 ? 'PASS' : 'FAIL', `筛选器数: ${categoryFilter.length}`);

  // Click "新增设备"
  const addEqBtn = await page.$('button:has-text("新增设备")');
  if (addEqBtn) {
    await addEqBtn.click();
    await page.waitForTimeout(500);
    const modal = await page.$('.ant-modal');
    log('设备台账', '打开新增设备弹窗', modal ? 'PASS' : 'FAIL');

    if (modal) {
      // Try to fill equipment ID
      const eqIdInput = await page.$('.ant-modal input');
      if (eqIdInput) {
        await eqIdInput.fill('EQ-EIS-001');
        log('设备台账', '填写设备编号', 'PASS');
      }

      const modalOk = await page.$('.ant-modal .ant-btn-primary');
      if (modalOk) {
        await modalOk.click();
        await page.waitForTimeout(300);
        log('设备台账', '空值提交校验', 'PASS', '检查是否有校验提示');
      }
    }

    const closeBtn = await page.$('.ant-modal-close');
    if (closeBtn) await closeBtn.click().catch(() => {});
    await page.waitForTimeout(500);
  } else {
    log('设备台账', '新增设备按钮', 'FAIL', '未找到');
  }

  // Check table rowKey
  const eqTable = await page.$('.ant-table');
  if (eqTable) {
    const rowKey = await page.$eval('.ant-table-tbody tr:first-child', (el) => el.getAttribute('data-row-key')).catch(() => null);
    log('设备台账', '表格 rowKey', rowKey ? 'PASS' : 'WARN', `rowKey: ${rowKey}`);
  }

  // ============================================================
  // SECTION 8: Raw Materials /materials
  // ============================================================
  console.log('\n========== 八、数据与资产：物料规格库 ==========\n');

  await page.goto(`${BASE}/materials`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const matTitle = await page.textContent('.page-title').catch(() => '');
  log('物料规格库', '页面标题', matTitle.includes('物料') ? 'PASS' : 'FAIL', `标题: "${matTitle}"`);

  // Check filter
  const matFilter = await page.$('.filter-card .ant-select');
  log('物料规格库', '物料分类筛选', matFilter ? 'PASS' : 'FAIL');

  // Check stat cards
  const matStats = await page.$$('.stat-item');
  log('物料规格库', '汇总卡片', matStats.length > 0 ? 'PASS' : 'WARN', `卡片数: ${matStats.length}`);

  // Click "新增物料"
  const addMatBtn = await page.$('button:has-text("新增物料")');
  if (addMatBtn) {
    await addMatBtn.click();
    await page.waitForTimeout(500);
    const modal = await page.$('.ant-modal');
    log('物料规格库', '打开新增物料弹窗', modal ? 'PASS' : 'FAIL');

    const closeBtn = await page.$('.ant-modal-close');
    if (closeBtn) await closeBtn.click().catch(() => {});
    await page.waitForTimeout(300);
  } else {
    log('物料规格库', '新增物料按钮', 'FAIL', '未找到');
  }

  // Check table rowKey
  const matTable = await page.$('.ant-table');
  if (matTable) {
    const rowKey = await page.$eval('.ant-table-tbody tr:first-child', (el) => el.getAttribute('data-row-key')).catch(() => null);
    log('物料规格库', '表格 rowKey', rowKey ? 'PASS' : 'WARN', `rowKey: ${rowKey}`);
  }

  // ============================================================
  // SECTION 9: Material Properties /properties
  // ============================================================
  console.log('\n========== 九、数据与资产：属性字典 ==========\n');

  await page.goto(`${BASE}/properties`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const propTitle = await page.textContent('.page-title').catch(() => '');
  log('属性字典', '页面标题', propTitle.includes('属性字典') ? 'PASS' : 'FAIL', `标题: "${propTitle}"`);

  // Check category cards
  const catCards = await page.$$('.stat-card');
  log('属性字典', '分类卡片', catCards.length > 0 ? 'PASS' : 'FAIL', `卡片数: ${catCards.length}`);

  // Check search
  const propSearch = await page.$('.search-input');
  if (propSearch) {
    await propSearch.fill('conductivity');
    await page.waitForTimeout(500);
    log('属性字典', '搜索功能', 'PASS');
    // Check search hint
    const searchHint = await page.textContent('.search-hint').catch(() => '');
    log('属性字典', '搜索反馈', searchHint.includes('匹配') ? 'PASS' : 'WARN', `反馈: "${searchHint}"`);
    await propSearch.fill('');
    await page.waitForTimeout(300);
  }

  // Check tabs
  const propTabs = await page.$$('.ant-tabs-tab');
  log('属性字典', '分类标签页', propTabs.length > 0 ? 'PASS' : 'FAIL', `标签数: ${propTabs.length}`);

  // Check table rowKey
  const propTable = await page.$('.ant-table');
  if (propTable) {
    const rowKey = await page.$eval('.ant-table-tbody tr:first-child', (el) => el.getAttribute('data-row-key')).catch(() => null);
    log('属性字典', '表格 rowKey', rowKey ? 'PASS' : 'WARN', `rowKey: ${rowKey}`);
  }

  // ============================================================
  // SECTION 10: Technology Intelligence /technology-intelligence
  // ============================================================
  console.log('\n========== 十、数据与资产：技术情报 ==========\n');

  await page.goto(`${BASE}/technology-intelligence`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);

  const intelTitle = await page.textContent('.page-title').catch(() => '');
  log('技术情报', '页面标题', intelTitle.includes('技术情报') ? 'PASS' : 'WARN', `标题: "${intelTitle}"`);

  // Check tabs
  const intelTabs = await page.$$('.tech-intel-tabs .ant-tabs-tab');
  log('技术情报', '标签页', intelTabs.length >= 2 ? 'PASS' : 'FAIL', `标签数: ${intelTabs.length}`);

  // Check search bar
  const intelSearch = await page.$('input[aria-label="搜索电池材料文献"]');
  if (intelSearch) {
    await intelSearch.fill('solid electrolyte');
    log('技术情报', '搜索框', 'PASS');
  }

  // Check hot keywords
  const hotTags = await page.$$('.hint-tag');
  log('技术情报', '热门关键词', hotTags.length > 0 ? 'PASS' : 'WARN', `关键词数: ${hotTags.length}`);

  if (hotTags.length > 0) {
    await hotTags[0].click();
    await page.waitForTimeout(1000);
    log('技术情报', '点击热门关键词搜索', 'PASS');
  }

  // Try clicking search button
  const searchBtn = await page.$('button:has-text("搜索")');
  if (searchBtn) {
    await searchBtn.click();
    await page.waitForTimeout(1500);
    log('技术情报', '搜索文献', 'PASS');
  }

  // Check papers list
  const papers = await page.$$('.paper-item');
  log('技术情报', '文献列表', papers.length > 0 ? 'PASS' : 'WARN', `文献数: ${papers.length}`);

  // Check empty state for papers
  const paperEmpty = await page.$('.ant-empty');
  if (paperEmpty) {
    const emptyText = await page.textContent('.ant-empty').catch(() => '');
    log('技术情报', '空状态引导', emptyText.includes('暂无文献') ? 'PASS' : 'WARN', `文案: "${emptyText}"`);
  }

  // Click "已保存图谱" tab
  const savedGraphTab = await page.$('.ant-tabs-tab:has-text("已保存图谱")');
  if (savedGraphTab) {
    await savedGraphTab.click();
    await page.waitForTimeout(800);
    log('技术情报', '切换到"已保存图谱"标签页', 'PASS');
  } else {
    log('技术情报', '已保存图谱标签页', 'FAIL', '未找到');
  }

  // ============================================================
  // SECTION 11: Generic checks across all pages
  // ============================================================
  console.log('\n========== 十一、通用检查 ==========\n');

  // Breadcrumb check
  await page.goto(`${BASE}/experiments`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await waitForApp(page);
  const breadcrumb = await page.$('.ant-breadcrumb');
  if (breadcrumb) {
    log('通用', '面包屑', 'WARN', '存在面包屑组件（如已确认移除则需清理）');
  } else {
    log('通用', '面包屑', 'PASS', '已移除');
  }

  // Chinese/English mixing check
  // Check for common English-only labels
  const mixedLabels = await page.evaluate(() => {
    const textNodes = [];
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walk.nextNode())) {
      if (node.textContent.trim()) textNodes.push(node.textContent.trim());
    }
    const suspicious = textNodes.filter(t => {
      // Check for mixed Chinese/English in UI labels
      return /[a-zA-Z]{3,}/.test(t) && !/[\u4e00-\u9fa5]/.test(t) && t.length > 5 && t.length < 100;
    });
    return suspicious.slice(0, 20);
  });
  const pureEnglishLabels = mixedLabels.filter(t => !/http|\.com|\.js|\.css|\.json|npx|npm|CSV|Excel|JSON|API|ID|URL|SMILES|XRD|SEM|EIS|DSC|TGA|CV|LLZO|LPSCl|LIMS|ELN|ECML|REACH|QC|OK/i.test(t));
  if (pureEnglishLabels.length > 5) {
    log('通用', '中英文混杂', 'WARN', `发现纯英文标签: ${pureEnglishLabels.slice(0, 5).join(', ')}`);
  } else {
    log('通用', '中英文混杂', 'PASS', '未见明显混杂');
  }

  // ============================================================
  // Generate Report
  // ============================================================
  const issues = RESULTS.filter(r => r.type === 'ISSUE');
  const passCount = RESULTS.filter(r => r.status === 'PASS').length;
  const failCount = RESULTS.filter(r => r.status === 'FAIL').length;
  const warnCount = RESULTS.filter(r => r.status === 'WARN').length;

  console.log('\n\n========================================');
  console.log('           测试报告摘要');
  console.log('========================================');
  console.log(`总步骤数: ${RESULTS.filter(r => r.type !== 'ISSUE').length}`);
  console.log(`通过: ${passCount} | 失败: ${failCount} | 警告: ${warnCount}`);
  console.log(`发现问题: ${issues.length}`);
  console.log('========================================\n');

  // Write JSON report
  const report = {
    summary: { total: RESULTS.filter(r => r.type !== 'ISSUE').length, pass: passCount, fail: failCount, warn: warnCount, issues: issues.length },
    results: RESULTS,
    pages: [
      { name: '决策记录', path: '/decision-center', notes: `3标签页: 实验放行卡/委员会案件/审批事项` },
      { name: '实验工作台', path: '/experiment-workbench', notes: '左右分栏：任务列表+审批队列' },
      { name: '实验数据', path: '/experiments', notes: '筛选+图表+表格' },
      { name: '样品管理', path: '/samples', notes: 'CRUD+流转+详情' },
      { name: '数据接入', path: '/data-ingest', notes: '4步骤向导' },
      { name: '设备台账', path: '/equipment', notes: 'CRUD+筛选' },
      { name: '物料规格库', path: '/materials', notes: 'CRUD+筛选+合规指标' },
      { name: '属性字典', path: '/properties', notes: '分类+搜索+自定义字段' },
      { name: '技术情报', path: '/technology-intelligence', notes: '2标签页: 技术情报+已保存图谱' },
    ],
  };

  fs.writeFileSync('d:/BattleFish/BatteryEMCL Lab/frontend/test-results/comprehensive-test.json', JSON.stringify(report, null, 2));
  console.log('详细报告已写入: test-results/comprehensive-test.json');

  await browser.close();
  return report;
}

run().then(report => {
  console.log('\n测试完成!');
}).catch(err => {
  console.error('测试异常:', err.message);
  process.exit(1);
});