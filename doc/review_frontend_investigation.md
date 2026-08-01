# 前端测试拦截排查与数据准备报告

## 1. 排查结论：Ant Design Vue 下拉框被 overlay 拦截的根因

### 1.1 相关源码位置

- `d:\BattleFish\BatteryEMCL Lab\frontend\src\views\ProjectNew.vue` 第 51–60 行：负责人 `a-select`
- `d:\BattleFish\BatteryEMCL Lab\frontend\src\views\CandidateWorkbench.vue` 第 18–41 行：项目/任务 `a-select`
- `d:\BattleFish\BatteryEMCL Lab\frontend\src\components\candidate\CandidateAgentBar.vue` 第 58–67 行：「调用智能体生成候选材料」按钮

### 1.2 根因分析

Ant Design Vue 的 `a-select` 默认会把下拉列表渲染到 `body` 下的独立 overlay/popup 容器（通过 teleport 实现），而不是触发元素所在的组件 DOM 子树里。`show-search` + `option-filter-prop="label"` 进一步要求 automation 必须：

1. 点击 trigger 展开 overlay；
2. 在 body 级 overlay 里找到选项；
3. 完成选择后再让 overlay 消失。

`browser_use` 子代理在步骤 2/3 时经常被该浮层遮挡或无法精确定位到 detached DOM 中的选项节点，表现为点击被 overlay 拦截、无法完成选择。

### 1.3 可选规避方案

- **注入脚本绕过**：直接修改组件内部 ref/state（推荐，见第 3 节）。
- **配置 `getPopupContainer`**：在 `a-select` 上添加 `:getPopupContainer="(trigger) => trigger.parentNode"`，让下拉列表挂载到 trigger 父级，减少跨 DOM 树的定位问题。
- **使用 URL query 预填**：`CandidateWorkbench.vue` 已支持 `?project_id=xxx&task_id=xxx`（第 714–732 行），可直接通过 URL 携带参数跳过 select 交互。

---

## 2. 测试数据创建结果

后端服务 `http://localhost:8000` 已运行。使用 Python `requests` 以 `admin` 登录后调用 `POST /projects` 创建项目，原名称已存在则自动添加 `_1` 后缀。

| 项目显示名称 | 项目 ID | 任务 ID |
|---|---|---|
| ASSB-LPSCl-2026Q3-V2_1 | PROJ-3DB94354 | c7952d32-41c4-40f2-94af-a01237a76422 |
| PEO-LiTFSI-2026Q3_1 | PROJ-34890B52 | c134d830-7193-4d4b-905f-a0301476cf4c |

### 任务详情

**ASSB-LPSCl-2026Q3-V2_1**

- 交付物：硫化物固态电解质（LPSCl）
- 目标属性：`ionic_conductivity` maximize，min = `0.001` S/cm

**PEO-LiTFSI-2026Q3_1**

- 交付物：PEO-LiTFSI 聚合物电解质
- 目标属性：
  - `ionic_conductivity` maximize，min = `0.0001` S/cm
  - `tensile_strength` maximize，min = `2` MPa

---

## 3. 浏览器注入脚本（console / browser_evaluate 用）

> 以下脚本基于 Vue 3 dev 模式下 DOM 节点上的 `__vue__` / `__vueParentComponent` 实例访问。若生产构建未暴露该属性，请先切换为 dev server（`npm run dev`，默认 `localhost:5173`）。

### 3.1 通用辅助：获取 Vue 组件实例

```js
function getVueInstance(selector) {
  const el = document.querySelector(selector);
  if (!el) return null;
  // dev 模式下通常有 __vue__ 或 __vueParentComponent
  let inst = el.__vue__;
  if (!inst && el.__vueParentComponent) {
    inst = el.__vueParentComponent.proxy || el.__vueParentComponent.ctx;
  }
  return inst;
}
```

### 3.2 ProjectNew.vue：直接设置负责人并触发校验

```js
(async () => {
  const ownerId = 'U-9AF74283'; // 实际使用时建议从 userOptions 中读取第一个 option.value
  const pn = getVueInstance('.project-new-layout') || getVueInstance('.project-new-page');
  if (!pn) { console.error('未找到 ProjectNew 实例'); return; }

  // 直接设置 form.owner（对应 <a-select v-model:value="form.owner">）
  pn.form.owner = ownerId;
  await pn.$nextTick();

  // 触发前端表单校验（对应 const formRef = ref()）
  try {
    await pn.formRef.validate();
    console.log('负责人已设置并通过校验，isFormValid =', pn.isFormValid);
  } catch (e) {
    console.error('表单校验未通过', e);
  }
})();
```

### 3.3 CandidateWorkbench.vue：直接设置项目/任务

```js
(async () => {
  const projectId = 'PROJ-3DB94354';
  const taskId    = 'c7952d32-41c4-40f2-94af-a01237a76422';

  const cw = getVueInstance('.candidate-workbench');
  if (!cw) { console.error('未找到 CandidateWorkbench 实例'); return; }

  // 设置项目并加载任务列表
  cw.selectedProjectId = projectId;
  await cw.onProjectChange(); // 内部会调用 loadProjectTasks()

  // 设置任务并加载已有候选
  cw.selectedTaskId = taskId;
  await cw.onTaskChange();    // 内部会调用 loadTaskCandidates()

  console.log('已选中项目/任务', cw.selectedProjectId, cw.selectedTaskId);
  console.log('当前任务', cw.selectedTask);
})();
```

### 3.4 触发「调用智能体生成候选材料」

```js
(async () => {
  const cw = getVueInstance('.candidate-workbench');
  if (!cw) { console.error('未找到 CandidateWorkbench 实例'); return; }

  if (!cw.selectedTaskId) {
    console.error('请先设置项目与任务');
    return;
  }

  // 直接调用组件内 onRun，等价于点击 CandidateAgentBar 的 emit('run')
  await cw.onRun();
  console.log('智能体生成已触发');
})();
```

---

## 4. Playwright 可用性检查

### 4.1 Python Playwright

- 检查结果：**不可用**
- 原因：`python -c "import playwright"` 报错 `ModuleNotFoundError: No module named 'playwright'`
- 恢复方案：`pip install playwright && playwright install chromium`

### 4.2 Node Playwright CLI（替代方案）

- 检查结果：**可用**，版本 `1.62.0`
- 已执行截图命令：

```powershell
npx playwright screenshot --wait-for-timeout=3000 http://localhost:5173/projects "D:\BattleFish\BatteryEMCL Lab\frontend\screenshots\playwright_test_projects.png"
```

- 输出：成功捕获 `http://localhost:5173/projects` 页面截图
- 截图路径：`d:\BattleFish\BatteryEMCL Lab\frontend\screenshots\playwright_test_projects.png`

### 4.3 建议

如需在子代理中继续使用 `browser_use`：

1. 优先使用第 3 节的注入脚本绕过 Ant Design Vue 的 overlay 选择。
2. 对 `CandidateWorkbench` 可直接通过 URL query 预填项目/任务：`http://localhost:5173/candidate-workbench?project_id=PROJ-3DB94354&task_id=c7952d32-41c4-40f2-94af-a01237a76422`（路由名以实际配置为准）。
3. 若必须使用 Playwright Python，先安装并同步浏览器二进制；当前环境可临时使用 `npx playwright screenshot` 完成截图验证。

---

## 5. 关键文件清单

- `d:\BattleFish\BatteryEMCL Lab\frontend\src\views\ProjectNew.vue`
- `d:\BattleFish\BatteryEMCL Lab\frontend\src\views\CandidateWorkbench.vue`
- `d:\BattleFish\BatteryEMCL Lab\frontend\src\views\Projects.vue`
- `d:\BattleFish\BatteryEMCL Lab\frontend\src\components\candidate\CandidateAgentBar.vue`
- `d:\BattleFish\BatteryEMCL Lab\battery_materials_agent\api.py`
- `d:\BattleFish\BatteryEMCL Lab\battery_materials_agent\projects.py`
- `d:\BattleFish\BatteryEMCL Lab\battery_materials_agent\auth\middleware.py`
- `d:\BattleFish\BatteryEMCL Lab\battery_materials_agent\auth\tokens.py`
- 输出报告：`d:\BattleFish\BatteryEMCL Lab\doc\review_frontend_investigation.md`
