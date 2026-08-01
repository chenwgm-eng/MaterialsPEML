# BatteryEMCL Lab 前端核心研发链路 Playwright 实操评测报告

> 生成时间：2026-07-29T10:57:51.891Z

## 1. 环境信息

- 前端地址：http://localhost:5173
- 后端地址：http://localhost:8000
- 后端健康检查：✅ 200
- 登录用户：U-9AF74283（角色：admin）
- 测试项目/任务：
  - PROJ-34890B52 / PEO-LiTFSI-2026Q3_1
  - PROJ-3DB94354 / ASSB-LPSCl-2026Q3-V2_1
- 任务 ID 验证：✅

## 2. 覆盖清单

| 序号 | 页面 | 路由 | 加载状态 | 核心操作 | 可点击元素数 | 初始截图 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 首页 | / | ok | - | 12 | EV-20260729-100_home_initial.png |
| 2 | 我的待办 | /my-tasks | ok | - | 26 | EV-20260729-102_my-tasks_initial.png |
| 3 | 项目管理 | /projects | ok | - | 11 | EV-20260729-104_projects_initial.png |
| 4 | 项目新建 | /projects/new | ok | success | 7 | EV-20260729-106_projects_new_initial.png |
| 5 | 候选材料设计 | /workbench | ok | success | 11 | EV-20260729-109_workbench_initial.png |
| 6 | 性质预测 | /prediction | ok | failed_or_empty | 16 | EV-20260729-112_prediction_initial.png |
| 7 | 合成路径 | /synthesis | ok | success | 18 | EV-20260729-115_synthesis_initial.png |
| 8 | 配方与工艺 | /formula-design | ok | failed_or_empty | 45 | EV-20260729-118_formula-design_initial.png |
| 9 | 实验闭环迭代 | /ecml | ok | completed | 19 | EV-20260729-121_ecml_initial.png |
| 10 | 迭代历史 | /ecml/runs | ok | - | 8 | EV-20260729-124_ecml_runs_initial.png |
| 11 | 性能寿命预测 | /battery-life | ok | - | 9 | EV-20260729-126_battery-life_initial.png |
| 12 | 实验工作台 | /experiment-workbench | ok | success | 41 | EV-20260729-128_experiment-workbench_initial.png |

## 3. 端到端核心链路

### 项目新建

- 路由：/projects/new
- 预填参数：{"status":"success","projectName":"PW核心测评项目-1785322087636","phase2":true,"screenshot":"d:\\BattleFish\\BatteryEMCL Lab\\frontend\\screenshots\\pw_core\\EV-20260729-107_projects_new_core.png","errors":[],"failedRequests":[]}
- 操作结果：**success**
- 截图：EV-20260729-107_projects_new_core.png

### 候选材料设计

- 路由：/workbench
- 预填参数：{"status":"success","candidateCount":2,"hasMessage":false,"screenshot":"d:\\BattleFish\\BatteryEMCL Lab\\frontend\\screenshots\\pw_core\\EV-20260729-110_workbench_core.png","errors":[],"failedRequests":[]}
- 操作结果：**success**
- 候选数量：2
- 截图：EV-20260729-110_workbench_core.png

### 性质预测

- 路由：/prediction
- 预填参数：{"status":"failed_or_empty","candidateCount":0,"hasMessage":false,"screenshot":"d:\\BattleFish\\BatteryEMCL Lab\\frontend\\screenshots\\pw_core\\EV-20260729-113_prediction_core.png","errors":["[warning] [Vue warn]: Unhandled error during execution of render function \n  at <CandidateTable data= [Object, Object, Object, Object, Object] loading=false type=\"crystal\"  ... > \n  at <ACard key=0 class=\"app-card\" bordered=false > \n  at <ASpin key=1 spinning=false > \n  at <Prediction onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< Proxy(Object) > > \n  at <BaseTransition mode=\"out-in\" appear=false ","[warning] [Vue warn]: Unhandled error during execution of component update \n  at <Prediction onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< Proxy(Object) > > \n  at <BaseTransition mode=\"out-in\" appear=false persisted=false  ... > \n  at <Transition name=\"fade\" mode=\"out-in\" > \n  at <RouterView> \n  at <Anonymous hasSider=undefined prefixCls=\"ant-layout-content\" tagName=\"main\"  ... > \n  at <ALayoutCo","[warning] [Vue warn]: Unhandled error during execution of component update \n  at <ASpin key=1 spinning=false > \n  at <Prediction onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< Proxy(Object) > > \n  at <BaseTransition mode=\"out-in\" appear=false persisted=false  ... > \n  at <Transition name=\"fade\" mode=\"out-in\" > \n  at <RouterView> \n  at <Anonymous hasSider=undefined prefixCls=\"ant-layout-content\" ta","[pageerror] ReferenceError: energyPerAtomUnit is not defined"],"failedRequests":[]}
- 操作结果：**failed_or_empty**
- 候选数量：0
- 操作期报错：[warning] [Vue warn]: Unhandled error during execution of render function 
  at <CandidateTable data= [Object, Object, Object, Object, Object] loading=false type="crystal"  ... > 
  at <ACard key=0 class="app-card" bordered=false > 
  at <ASpin key=1 spinning=false > 
  at <Prediction onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< Proxy(Object) > > 
  at <BaseTransition mode="out-in" appear=false ; [warning] [Vue warn]: Unhandled error during execution of component update 
  at <Prediction onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< Proxy(Object) > > 
  at <BaseTransition mode="out-in" appear=false persisted=false  ... > 
  at <Transition name="fade" mode="out-in" > 
  at <RouterView> 
  at <Anonymous hasSider=undefined prefixCls="ant-layout-content" tagName="main"  ... > 
  at <ALayoutCo; [warning] [Vue warn]: Unhandled error during execution of component update 
  at <ASpin key=1 spinning=false > 
  at <Prediction onVnodeUnmounted=fn<onVnodeUnmounted> ref=Ref< Proxy(Object) > > 
  at <BaseTransition mode="out-in" appear=false persisted=false  ... > 
  at <Transition name="fade" mode="out-in" > 
  at <RouterView> 
  at <Anonymous hasSider=undefined prefixCls="ant-layout-content" ta
- 截图：EV-20260729-113_prediction_core.png

### 合成路径

- 路由：/synthesis
- 预填参数：{"status":"success","routeCount":1,"serviceError":"","screenshot":"d:\\BattleFish\\BatteryEMCL Lab\\frontend\\screenshots\\pw_core\\EV-20260729-116_synthesis_core.png","errors":[],"failedRequests":[]}
- 操作结果：**success**
- 路线数量：1
- 截图：EV-20260729-116_synthesis_core.png

### 配方与工艺

- 路由：/formula-design
- 预填参数：{"status":"failed_or_empty","bomRows":0,"hasError":false,"screenshot":"d:\\BattleFish\\BatteryEMCL Lab\\frontend\\screenshots\\pw_core\\EV-20260729-119_formula-design_core.png","errors":["[error] Failed to load resource: the server responded with a status of 500 (Internal Server Error)"],"failedRequests":[{"url":"http://localhost:5173/api/mcp/tools/design_formula/call","status":500}]}
- 操作结果：**failed_or_empty**
- BOM 行数：0
- 操作期报错：[error] Failed to load resource: the server responded with a status of 500 (Internal Server Error)
- 操作期失败请求：http://localhost:5173/api/mcp/tools/design_formula/call
- 截图：EV-20260729-119_formula-design_core.png

### 实验闭环迭代

- 路由：/ecml
- 预填参数：{"status":"completed","screenshot":"d:\\BattleFish\\BatteryEMCL Lab\\frontend\\screenshots\\pw_core\\EV-20260729-122_ecml_core.png","errors":[],"failedRequests":[]}
- 操作结果：**completed**
- 截图：EV-20260729-122_ecml_core.png

### 实验工作台

- 路由：/experiment-workbench
- 预填参数：{"status":"success","message":"","screenshot":"d:\\BattleFish\\BatteryEMCL Lab\\frontend\\screenshots\\pw_core\\EV-20260729-129_experiment-workbench_core.png","errors":[],"failedRequests":[]}
- 操作结果：**success**
- 截图：EV-20260729-129_experiment-workbench_core.png

## 4. 缺陷清单

| 编号 | 模块 | 级别 | 标题 | 复现步骤 | 期望结果 | 实际结果 | 证据 | 建议 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BEMCL-PRED-P0-001 | PRED | P0 | 性质预测 核心操作未返回有效结果 | 执行 性质预测 | 操作成功并展示结果 | 状态=failed_or_empty;  | EV-20260729-113_prediction_core.png | 修复对应业务链路 |
| BEMCL-PRED-P1-002 | PRED | P1 | 性质预测 操作期间报错 | 执行 性质预测 | 无 console error | [pageerror] ReferenceError: energyPerAtomUnit is not defined | EV-20260729-113_prediction_core.png | 检查前端事件与数据流 |
| BEMCL-FORMULA-P0-003 | FORMULA | P0 | 配方与工艺 核心操作未返回有效结果 | 执行 配方与工艺 | 操作成功并展示结果 | 状态=failed_or_empty;  | EV-20260729-119_formula-design_core.png | 修复对应业务链路 |
| BEMCL-FORMULA-P1-004 | FORMULA | P1 | 配方与工艺 操作期间报错 | 执行 配方与工艺 | 无 console error | [error] Failed to load resource: the server responded with a status of 500 (Internal Server Error) | EV-20260729-119_formula-design_core.png | 检查前端事件与数据流 |
| BEMCL-FORMULA-P0-005 | FORMULA | P0 | 配方与工艺 操作接口失败 | 执行 配方与工艺 | 接口返回 200 | HTTP 500 http://localhost:5173/api/mcp/tools/design_formula/call | EV-20260729-119_formula-design_core.png | 检查后端的业务接口 |
| BEMCL-FE-P2-006 | FE | P2 | 首页 部分可点击元素无法交互 | 遍历点击 / | 所有可点击元素正常响应 | 2 个点击异常：48
合成路径
服务可用率 93%, 下一步 | EV-20260729-101_home_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-007 | FE | P2 | 我的待办 部分可点击元素无法交互 | 遍历点击 /my-tasks | 所有可点击元素正常响应 | 17 个点击异常：委员会Case, 状态 | EV-20260729-103_my-tasks_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-008 | FE | P2 | 项目管理 部分可点击元素无法交互 | 遍历点击 /projects | 所有可点击元素正常响应 | 1 个点击异常： | EV-20260729-105_projects_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-009 | FE | P2 | 候选材料设计 部分可点击元素无法交互 | 遍历点击 /workbench | 所有可点击元素正常响应 | 1 个点击异常：Agent 生成中… | EV-20260729-111_workbench_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-010 | FE | P2 | 性质预测 部分可点击元素无法交互 | 遍历点击 /prediction | 所有可点击元素正常响应 | 8 个点击异常：, LiCoO2 | EV-20260729-114_prediction_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-011 | FE | P2 | 合成路径 部分可点击元素无法交互 | 遍历点击 /synthesis | 所有可点击元素正常响应 | 4 个点击异常：综合成本-可行性-步骤数 三维对比, 反应机理网络 | EV-20260729-117_synthesis_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-012 | FE | P2 | 配方与工艺 部分可点击元素无法交互 | 遍历点击 /formula-design | 所有可点击元素正常响应 | 44 个点击异常：新建, 最近 | EV-20260729-120_formula-design_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-013 | FE | P2 | 实验闭环迭代 部分可点击元素无法交互 | 遍历点击 /ecml | 所有可点击元素正常响应 | 1 个点击异常：最近 | EV-20260729-123_ecml_final.png | 检查元素覆盖与事件绑定 |
| BEMCL-FE-P2-014 | FE | P2 | 实验工作台 部分可点击元素无法交互 | 遍历点击 /experiment-workbench | 所有可点击元素正常响应 | 30 个点击异常：录入数据, 查看结果 | EV-20260729-130_experiment-workbench_final.png | 检查元素覆盖与事件绑定 |

## 5. 截图目录

d:/BattleFish/BatteryEMCL Lab/frontend/screenshots/pw_core

## 6. 统计

- P0：3，P1：2，P2：9，P3：0
- 总页面数：12
