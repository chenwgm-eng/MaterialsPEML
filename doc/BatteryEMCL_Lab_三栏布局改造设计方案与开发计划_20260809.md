# BatteryEMCL Lab 三栏布局改造与角色化设计方案（实施版）

- 日期：2026-08-09
- 状态：已收敛，进入实施。**本文档可直接交给 LLM 作为代码实现与测试的输入**。经六次评审收敛并落实 P0/P1 定稿（primaryDiscipline DB 约束、nav_visibility 权限下限、权限单源判定、ContextColumn 契约、ECML 回填三分类、T15–T17）。
- 读者：实施工程师 / LLM 编码代理。每节给出**精确实现锚点（文件 + 行号 + 函数/签名）**、**变更内容**、**验证方法**、**DoD**。

> 阅读约定：
> - 「锚点」= 当前代码中被修改/参照的位置，均为已核实的真实路径与行号。
> - 所有 DB 变更走 alembic；迁移命名规范见 §0.3。
> - 任何 API 的读/写授权**只**由后端 `require_permission` / `require_project_access` 决定；前端隐藏/守卫仅是体验层。

---

## 0. 代码现状核实（实施前必读，已逐项验证）

### 0.1 后端关键锚点

| 关注点 | 文件 | 行号 | 现状 |
|---|---|---|---|
| User 模型 | [user_store.py](../battery_materials_agent/auth/user_store.py) | 66-79 | 无 `disciplines` / `primary_discipline` 字段 |
| UserRole / ROLE_RANK | 同上 | 46-63 | 6 角色（admin/pm/researcher/reviewer/viewer/data_engineer），**保持不变** |
| `UserStore.save()` upsert | 同上 | 165-210 | `INSERT ... ON CONFLICT(user_id) DO UPDATE`，列清单硬编码，**新增列需同步改这里** |
| `_row_to_user` | 同上 | 251-264 | 按**位置索引** row[0..12] 解析，`SELECT *`；新增列需用 `_cell(row, idx, default)` 容错追加 |
| `project_ids` 已是 JSONB | 同上 | 177,200 | `CAST(:project_ids AS JSONB)` + `json.dumps`；disciplines 参照同写法 |
| 审计 `AuditLogger.log` | [audit.py](../battery_materials_agent/audit.py) | 52-84 | 字段含 `tenant_id/user_id/operator/before/after`；`AuditEntry` 见 30-45 |
| `require_permission` | [middleware.py](../battery_materials_agent/auth/middleware.py) | 122-156 | 匿名 401、缺权限 403 + 审计；`require_login` 106-119、`check_project_access` 159-170 |
| 权限点常量 + ROLE_PERMISSIONS | [permissions.py](../battery_materials_agent/auth/permissions.py) | 20-111 | 16 个权限点；`role_has_permission`（100）、`user_has_permission`（107） |
| `GET /auth/me` | [api.py](../battery_materials_agent/api.py) | 1655-1662 | 返回 `_user_to_dict(current)` + `permissions` |
| `PUT /auth/users/{user_id}` | 同上 | 1716-1739 | `require_permission("user.manage")`；逐字段 `if req.x is not None` 更新后 `store.save` |
| `_user_to_dict` | 同上 | 1508-1512 | `model_dump()` 后剔除 `password_hash`；新增字段会自动随之序列化 |
| `UserUpdateRequest` | 同上 | 1493-1499 | 全部 `Optional`，**需新增 disciplines/primary_discipline** |

**结论（重要）**：后端**没有** `PUT /auth/me` 自助资料端点。「我的画像」自助修改需**新增** `PUT /auth/me/disciplines`（或扩展），而管理员侧走既有 `PUT /auth/users/{user_id}`。

### 0.2 前端关键锚点

| 关注点 | 文件 | 行号 | 现状 |
|---|---|---|---|
| 路由守卫 | [router/index.js](../frontend/src/router/index.js) | 93-116 | `beforeEach` 内联；角色校验用 `meta.requiredRole` + `ROLE_RANK` + `localStorage.userRole` |
| 路由表 | 同上 | 7-81 | **无 `/projects/:projectId` 资源型路由**；项目页为 `/projects`、`/projects/new`；**无 `meta.context`**；无 `/nav-visibility` |
| 当前用户来源 | [api/auth.js](../frontend/src/api/auth.js) | 5 | `getCurrentUser() → GET /auth/me`；另有 listUsers/updateUser(8,9) |
| system store | [stores/system.js](../frontend/src/stores/system.js) | 7-66 | 仅存 health/tools/mcpManifest/config，**不含 currentUser** |
| 登录态 | [api/client.js](../frontend/src/api/client.js) | 8-26 | `localStorage: userId/authToken`；axios baseURL `/api`、拦截器注入 `X-Auth-Token` |
| roles 常量 | [constants/roles.js](../frontend/src/constants/roles.js) | 9-31 | `ROLE_RANK/ROLE_COLOR_MAP/ROLE_LABEL_MAP`；含冗余 `experimenter`（后端无此角色） |
| 设置页 | [views/Settings.vue](../frontend/src/views/Settings.vue) | 1-60 | a-card 分组表单，可在此加「我的画像」卡片 |
| 布局 | [layouts/MainLayout.vue](../frontend/src/layouts/MainLayout.vue) | — | 现有两栏（220px 侧栏 + Header + router-view），含 isMenuVisible / createMenuItems / recentRuns |

### 0.3 迁移命名规范（必须遵守）

- 目录：`alembic/versions/`；文件名形如 `0054_gnome_numeric_nullable.py`。
- **`revision` 用「序号_语义」字符串**，`down_revision` 指向前一个 `revision`：
  - 最新链：`0054_gnome_numeric_nullable`(rev) ← down `0053_gnome_material_id_unique` ← `0052_gnome_materials` ← `0050_add_tenant_isolation`。
  - 新增迁移文件名须为 `0055_...py`、`0056_...py`、`0057_...py`，且 `down_revision` 依次衔接：`0055` → down=`0054_gnome_numeric_nullable`；`0056` → down=`0055_...`；`0057` → down=`0056_...`。
- 模板（照抄 0054 风格）：`op.execute(...)` / `op.add_column(...)`，`from alembic import op`。

---

## 1. 目标与最终信息架构（设计已冻结，不在本期改动）

三栏：第一栏 64px 图标栏（IconRail）；第二列 260px ContextColumn（可折叠 24px）；第三栏内容区。
四个稳定一级入口：工作台 / 项目 / 能力库 / 管理。可见性 = `requiredAnyPermission` 资格 ∧ `nav_visibility` 未隐藏。
授权角色 6 个不变；材料/工艺/实验做成可多选 `discipline` + 单一 `primaryDiscipline`（只影响体验，不影响权限）。
项目上下文以资源型 URL 为真源（`/projects/:projectId/...`），Pinia/localStorage 仅缓存与 UI 偏好。

> 本文件聚焦**如何落地**。设计理由见各节内联说明。

---

## 2. 交付总览与实施顺序

按可回滚垂直切片推进，**每步独立可验收、可回滚（feature flag）**：

| Step | 范围 | 迁移 | 主要交付物 | 回滚开关 |
|---|---|---|---|---|
| **A 身份与兼容层** | discipline 字段 + 校验 + 审计 + 我的画像 | 0057 | user_store / api / 迁移 / 前端画像卡片 / 集成测试 | —（纯增量，无行为变化） |
| **B 稳定导航壳层** | 稳定骨架 + 权限推导 + nav_visibility + 路由 requiredPermissions 迁移 | 0056 | menuConfig / navVisibility store+api+管理页 / IconRail / 守卫 | `VITE_FF_NAV_SHELL` |
| **C 项目中心 MVP** | 资源型 URL + ContextColumn + 项目定位/任务/动态 + watch 刷新 + ECML project_id | 0055 | contextResolver / ProjectLocator / TaskPanel / Timeline / ECML 迁移 | `VITE_FF_PROJECT_CENTER` |
| **D 三类研发体验** | discipline 默认聚焦/排序/推荐 | — | menuConfig discipline 排序 + 视角切换 | `VITE_FF_DISCIPLINE_UX` |
| **E 治理收尾** | 管理页迁移、无障碍、埋点、删旧代码、T1–T17 | — | NavVisibility 完善 + E2E | — |

> 依赖：A 必须先做（0057 建列），B 依赖 A 的用户字段，C 依赖 B 的壳层，D 依赖 C 的项目中心，E 收尾。
> **本计划第 3 节给出 Step A 的逐文件实施细节**；B/C/D/E 在 §4 给出实施级规格。

---

## 3. Step A —— 身份与兼容层（本步实施，不改导航）

> 目标：让 `auth.users` 支持 `disciplines`/`primary_discipline`，前后端可读写并审计；**权限体系零改动、旧账号行为零变化**。

### 3.A1 后端：枚举与模型（user_store.py）

**锚点**：[user_store.py](../battery_materials_agent/auth/user_store.py) 66-79。

变更：
1. 在 `UserRole`（46-52）之后新增 `Discipline` 枚举：
```python
class Discipline(str, Enum):
    MATERIAL_RESEARCH = "material_research"      # 材料研发
    PROCESS_DESIGN = "process_design"            # 工艺设计
    EXPERIMENT_ANALYSIS = "experiment_analysis"  # 实验分析
```
2. `User` 模型新增两字段（放 `external_idp_id` 之后，保持可选与默认空）：
```python
disciplines: list[str] = Field(default_factory=list)  # 0-3 个 Discipline 值，去重
primary_discipline: str = ""  # 空串=NULL 语义；非空必须 ∈ disciplines
```
   - 用 `list[str]`/`str` 而非 Enum，避免 `_row_to_user` 位置解析与 JSONB 往返的类型摩擦；枚举校验集中在 service/API 层（见 3.A3）。
3. `save()`（171-209）INSERT/UPDATE 列清单追加 `disciplines`、`primary_discipline`，值分别为 `json.dumps(sorted(set(user.disciplines)))` 与 `user.primary_discipline or None`；`CAST(:disciplines AS JSONB)`。
4. `_row_to_user`（251-264）追加容错读取（`SELECT *` 顺序随迁移后列增加而变，用 `_cell` + 名称映射更稳；最小改动是改用 `row._mapping`）：
```python
m = row._mapping  # 推荐改为 mapping，避免新增列导致位置漂移
...
disciplines=list(m.get("disciplines") or []),
primary_discipline=m.get("primary_discipline") or "",
```
   - **注意**：当前实现用位置索引 `row[0..12]`，新增两列后位置会漂移，**必须**改为 `row._mapping` 按名读取，否则解析错位。

### 3.A2 迁移 0057（alembic/versions/0057_user_disciplines.py）

```python
revision = "0057_user_disciplines"
down_revision = "0056_nav_visibility"   # 见 §4.B1；若先单独落 A，则临时指到当前 head，合并前统一到 0056 之后
```
- upgrade：
```sql
ALTER TABLE auth.users ADD COLUMN disciplines JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE auth.users ADD COLUMN primary_discipline TEXT;
ALTER TABLE auth.users ADD CONSTRAINT disciplines_is_array CHECK (jsonb_typeof(disciplines)='array');
ALTER TABLE auth.users ADD CONSTRAINT disciplines_values_valid
  CHECK (disciplines <@ '["material_research","process_design","experiment_analysis"]'::jsonb);
ALTER TABLE auth.users ADD CONSTRAINT primary_discipline_in_disciplines
  CHECK (primary_discipline IS NULL OR disciplines ? primary_discipline);
```
- downgrade：按相反顺序 `DROP CONSTRAINT` ×3、`DROP COLUMN` ×2。

**P0 不变量（DB CHECK + 应用层双重强制，集成测试锁定）**：
- `primary_discipline IS NULL` 时 `disciplines` 可空/非空；
- 非 NULL 必 ∈ `disciplines`（杜绝 `disciplines=['material_research']` 而 `primary='experiment_analysis'`）；
- 枚举值变更只走 migration；前端自由字符串在 API 层 400；
- 删除当前主画像时须同事务置空 `primary_discipline` 或指定新主画像。

### 3.A3 后端：service 校验 + API（api.py）

新增一个纯函数（建议放 `auth/user_store.py` 或新建 `auth/discipline.py`），供两处复用：
```python
_VALID = {"material_research","process_design","experiment_analysis"}
def normalize_disciplines(disciplines, primary):
    ds = sorted({d for d in (disciplines or []) if d})        # 去重去空
    bad = [d for d in ds if d not in _VALID]
    if bad: raise ValueError(f"非法专业画像: {bad}")
    p = primary or ""
    if p and p not in ds: raise ValueError("primary_discipline 必须属于 disciplines")
    return ds, p
```

**API 变更**（[api.py](../battery_materials_agent/api.py)）：
1. `UserUpdateRequest`（1493-1499）新增 `disciplines: list[str] | None = None`、`primary_discipline: str | None = None`。
2. `update_user`（1716-1739，user.manage）：当任一字段非 None 时调用 `normalize_disciplines`；写库前/后写审计（`module="auth"`, `action="update_user_disciplines"`, `before/after` 含两字段，operator=当前管理员 username，tenant_id=目标用户 tenant）。
3. **新增自助端点**（当前用户改自己画像，无需 user.manage）：
```python
@app.put("/auth/me/disciplines")
async def update_my_disciplines(req: MyDisciplinesRequest, current: User = Depends(require_login)):
    ds, p = normalize_disciplines(req.disciplines, req.primary_discipline)  # ValueError→400
    before = {"disciplines": current.disciplines, "primary_discipline": current.primary_discipline}
    current.disciplines, current.primary_discipline = ds, p
    app.state.user_store.save(current)
    get_audit_logger().log(AuditEntry(event_type="human_edit", module="auth",
        action="update_my_disciplines", operator=current.username, user_id=current.user_id,
        resource_type="user", resource_id=current.user_id,
        before=before, after={"disciplines": ds, "primary_discipline": p}, tenant_id=current.tenant_id))
    return _user_to_dict(current)
```
   - `MyDisciplinesRequest`：`disciplines: list[str] = []`、`primary_discipline: str = ""`。
   - `GET /auth/me`（1655）无需改动：`_user_to_dict` 会自动带出新字段。

### 3.A4 前端：API + 「我的画像」卡片

- [api/auth.js](../frontend/src/api/auth.js) 新增：`updateMyDisciplines = (data) => client.put('/auth/me/disciplines', data)`。
- [constants/roles.js](../frontend/src/constants/roles.js) 新增：
```js
export const DISCIPLINE_LABEL_MAP = { material_research:'材料研发', process_design:'工艺设计', experiment_analysis:'实验分析' }
```
- [views/Settings.vue](../frontend/src/views/Settings.vue) 新增「我的画像」a-card：`a-select(mode="multiple")` 绑定 disciplines（选项=3 个画像）+ `a-select(allowClear)` 绑定 primary（选项=当前已选 disciplines）；保存调 `updateMyDisciplines`，成功后 `getCurrentUser()` 刷新。**判空**：`disciplines=[]` 或 `primary=''` 走通用分支，禁用任何按专业子页取数的逻辑。
- 前端**不**改路由/导航/权限。

### 3.A5 Step A 验证（DoD）

- 迁移：`alembic upgrade head` 成功；`alembic downgrade -1` 可回滚；`\d auth.users` 见两列三约束。
- 集成测试（pytest）：① `disciplines=['material_research'], primary='experiment_analysis'` 写入 → DB/后端拒绝；② 删除主画像时 primary 自动置空；③ 空画像读写正常；④ 旧账号 `GET /auth/me` 返回结构与权限不变。
- 手测：研发账号在设置页设置/清空画像并保存，刷新后保持；审计日志可见 before/after。

---

## 4. Step B–E 实施级规格

### 4.B Step B：稳定导航壳层（feature flag `VITE_FF_NAV_SHELL`）

**4.B1 迁移 0056（alembic/versions/0056_nav_visibility.py）**
```sql
CREATE TABLE auth.nav_visibility (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT current_setting('app.tenant_id', true),
  role TEXT NOT NULL, entry_key TEXT NOT NULL,
  visible BOOL NOT NULL DEFAULT TRUE,
  updated_by TEXT, updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tenant_id, role, entry_key)
);
```
`revision="0056_nav_visibility"`, `down_revision="0055_ecml_runs_index_project_id"`。
> 迁移链顺序：0054(head) → **0055(ECML)** → **0056(nav_visibility)** → **0057(user_disciplines)**。若 A 先行，0057 先临时接 0054，合并前统一重排到 0056 之后（仅改 `down_revision` 字符串）。

**4.B2 后端 nav_visibility**：新建 `auth/nav_visibility_store.py`（仿 `UserStore`，读/写覆盖行）；API：`GET /nav-visibility`（普通角色回其可见 entries；admin 全量）、`PUT /nav-visibility`（`require_permission("user.manage")`，批量 upsert + 审计 before/after + 缓存失效信号）。seed 写入与权限推导一致的默认矩阵。

**4.B3 权限下限（P0）**：前端 `layouts/menuConfig.js` 每个一级入口声明：
```js
{ key:'group.admin', label:'管理', icon:'SettingOutlined',
  requiredAnyPermission:['user.manage','tenant.manage','audit.view'], navVisibilityConfigurable:true }
```
最终显示 = `requiredAnyPermission` 命中 ∧ 用户有该最小权限 ∧ `nav_visibility` 未隐藏。**`visible=true` 不能把无最小权限入口变可见。**

**4.B4 权限单源迁移（P0）**：路由 `meta.requiredRole` → `meta.requiredPermissions`/`requiredAnyPermission`；守卫逻辑（[router/index.js](../frontend/src/router/index.js) 106-114）改为：权限点优先，二者并存取更严；`ROLE_RANK` 仅用于默认落地/兼容/排序，不作授权。后端不变（已是 permission 唯一判据）。

**4.B5 组件**：新增 `layouts/IconRail.vue`（64px 图标栏）、`layouts/menuConfig.js`、`views/NavVisibility.vue`（顶部固定「此设置仅影响导航是否显示，不影响实际数据权限」提示 + 表格 + 保存）、`api/navVisibility.js`。`stores/system.js` 增加 `currentUser/visibleEntries/disciplines/primaryDiscipline` 与 `fetchMe()`，登录/角色切换时失效重拉（T16）。

### 4.C Step C：项目中心 MVP（feature flag `VITE_FF_PROJECT_CENTER`）

**4.C1 迁移 0055（alembic/versions/0055_ecml_runs_index_project_id.py）**
```sql
ALTER TABLE ecml.ecml_runs_index ADD COLUMN project_id TEXT;
UPDATE ecml.ecml_runs_index i SET project_id=t.project_id FROM projects.tasks t WHERE i.task_id=t.task_id;
```
回填三分类（P1）：可唯一关联→写入并抽样核验；无法关联→保持 NULL、全局历史可查、出待处置清单；冲突/项目不存在→不写入、记原因交管理员。回填来源/时间/脚本版本/数量入审计日志。`ECMLRunStore.save()` 增加 project_id 列；`list_runs(limit, project_id="")` 加 `(:project_id='' OR i.project_id=:project_id)`；API `/ecml/runs` 加 `project_id` Query；前端 `api/ecml.js` 加 `projectId` 参数。

**4.C2 资源型 URL**：路由新增 `/projects/:projectId`、`/projects/:projectId/tasks`、`/candidates/:id`、`/experiments/:id`、`/ecml/runs/:runId` 等；页面从路由参取 projectId，`watch(projectId)` 重取（**不整页重建**），列表筛选/分页/滚动按 projectId 缓存；表单/未保存页加离开保护（T15）。

**4.C3 ContextColumn 契约（P1）**：新增 `layouts/contextResolver.js`，把 `route.meta.{context,contextEntity,contextMode}` 规范化为 `{mode, projectId, showLocator, showTasks, showTimeline}`；`ContextColumn.vue` 只消费该 model，不写 `if(route.name===...)`。映射表（默认态）：

| 路由模式 | meta.context | mode | 中栏 | 默认 |
|---|---|---|---|---|
| 项目工作区 | project | project-overview | 项目定位+新建+任务+动态 | 展开 |
| 对象详情 | object | object-detail | 所属项目/关联对象/状态/操作记录 | 可收起(默认展开) |
| 能力库 | capability | capability-nav | 分类/筛选/二级菜单 | 收起或退化 |
| 管理页 | admin | admin-nav | 二级菜单/筛选 | 收起或退化 |
| 工作台 | workbench | workbench | 全局待办+动态(无项目选择器) | 展开 |
| 全局/无上下文 | global | degraded | 仅二级导航 | — |

**4.C4 组件**：`ProjectLocator.vue`（选择器+MRU≤5 localStorage `recentProjectIds`+新建下拉权限过滤）、`ProjectTaskPanel.vue`（仅 `assignee=当前用户`，进行中/已完成分组，≤10，搜索/展开/空态）、`ProjectTimeline.vue`（四源聚合，关键>业务>技术，默认只显关键+业务≤5，深链跳转）。

### 4.D Step D：三类研发体验（feature flag `VITE_FF_DISCIPLINE_UX`）

- `menuConfig.js` 按 discipline 对项目内二级模块**默认排序/聚焦**（材料研发→候选材料/预测/ECML；工艺设计→合成工艺/工艺库/配方编辑；实验分析→实验任务/数据/QC）。多选取并集加权，`primaryDiscipline` 优先。
- 空画像（disciplines 空或 primary null）：默认落点=概览，能力库全分类，新建通用顺序，**前端消费 primary 必先判空**。
- Header 用户菜单加「专业视角」切换（只改体验不改权限）。**不生成新角色菜单。**

### 4.E Step E：治理与收尾

- NavVisibility 管理页完善、无障碍（键盘焦点/按钮文本/对比度/`prefers-reduced-motion`）、埋点、灰度、删除旧侧边栏/Header 残留。
- 执行 §5 测试矩阵 T1–T17 作为合并前强制清单。

---

## 5. 验收与测试

### 5.1 叙述性验收（P0）

- 6 个授权角色历史账号正常登录；角色等级、项目访问、API 权限**不变化**。
- discipline 只改默认体验；同权限集合下切换 discipline **不改变任一 API 数据范围或可执行动作**。
- viewer 改 URL/前端状态/直接调接口均无法获得编辑/运行/审批/管理权限（导航隐藏≠权限变更）。
- 项目页刷新/复制 URL/前进后退后恢复正确上下文。
- ECML 回填分三档输出并审计；项目切换未保存表单必确认、无编辑态不整页重建（列表状态按项目缓存）。
- **P0 不变量**：`primary_discipline` 为 NULL 或 ∈ `disciplines`；`nav_visibility` 只能隐藏不能越权显示；后端 `permission+project access+tenant scope` 为唯一授权，前端 `requiredPermissions` 优先、`requiredRole` 仅兼容、`ROLE_RANK` 不作授权。

### 5.2 可执行测试矩阵（角色 × 操作 × 预期，合并前强制）

| # | 角色 | 操作 | 预期 | 类型 |
|---|---|---|---|---|
| T1 | 全部6角色 | 历史账号登录 | 正常登录；权限零变化 | 自动化 |
| T2 | researcher(任一画像) | 切换 primaryDiscipline | 默认体验变化；API 数据范围/动作不变 | 自动化 |
| T3 | researcher(空画像) | 登录进入项目 | 落点=概览、能力库全量、不白屏 | 自动化 |
| T4 | viewer | 改 URL 到 create 页 | 守卫/后端 403 | 自动化 |
| T5 | viewer | 直接调写/管理接口 | 全 403 | 自动化 |
| T6 | 任意 | 刷新/复制URL/前进后退于项目/对象/ECML 详情 | 上下文正确恢复 | 自动化 |
| T7 | admin | 隐藏某入口后该角色从 URL 直达 | 仍可访问；页面顶部固定提示可见 | 手动 |
| T8 | admin | 修改 nav_visibility | 审计含 tenant/操作人/role/entry_key/前后值/时间；菜单缓存失效 | 自动化 |
| T9 | 非admin | 调 `PUT /nav-visibility` 无 user.manage | 403 | 自动化 |
| T10 | 任意 | 项目切换(有未保存表单) | 弹离开确认；无编辑态列表状态按项目缓存不整页重建 | 手动 |
| T11 | researcher/data_engineer | 查看项目 | 一级入口≤2–3；管理入口不干扰 | 手动 |
| T12 | 任意 | 打开项目时间线 | 仅关键+业务≤5倒序；技术事件折叠 | 手动 |
| T13 | 任意 | 键盘/折叠/对比度/reduced-motion | 全部通过 | 自动化 |
| T14 | admin | 迁移0055后校验回填 | 数量/准确率抽样通过；三分类+审计 | 自动化 |
| T15 | 任意 | 未保存修改后切项目/路由/刷新 | 必弹离开确认；留下时上下文不变 | 自动化(E2E) |
| T16 | 任意 | 换用户/角色/租户或改nav_visibility后 | Pinia/本地缓存/MRU不沿用前身份；菜单重拉 | 自动化(E2E) |
| T17 | 任意 | 访问不存在/无权/对象不属于项目的URL | 清晰404/403/“对象不属于该项目”，不白屏不串数据 | 自动化(E2E) |

---

## 6. 风险与边界

| 风险 | 对策 |
|---|---|
| 授权角色零改动 | 保留 6 角色与 ROLE_PERMISSIONS，权限体系零迁移 |
| 导航可见性被误当权限 | 管理页固定提示 + 权限下限 + 审计 + 缓存失效 |
| 专业画像聚焦隐藏模块 | 仅默认排序不锁定；空画像完整展示 |
| discipline 数据质量 | 三 CHECK + 后端去重/枚举校验 + 审计；MVP JSONB，演进落关联表 |
| primary 非法 | `primary_discipline_in_disciplines` 约束 + 同事务置空/指定 |
| ECML 历史无 project_id | task_id 回填 + 三分类 + 审计；不可关联全局可查 |
| 后端未就绪前端冷启动 | 前端内置默认矩阵（与权限推导一致）兜底首屏 |
| URL 改动量大 | 一期先项目资源型 URL；旧 query 路由过渡 |
| 项目切换丢编辑态 | 离开保护 + 确认；列表按 projectId 缓存 |
| 中栏 260+64=324px | 能力库/管理默认收起；已确认 |

## 7. 非目标（本次不做）

- 不改各 view 页面内部业务布局（工艺配方编辑为既有能力，仅放开权限）。
- 不动 `ROLE_PERMISSIONS` 权限点体系（nav_visibility 独立于操作权限，二者并存）。
- 不把菜单结构全 DB 化（仅可见性覆盖落库）。
- 不做后端聚合型时间线接口（前端并行聚合）。
- 不新增「收藏项目」（常用=最近访问）。
- 不把 disciplines 做成角色/权限主键（JSONB 为 MVP）。
