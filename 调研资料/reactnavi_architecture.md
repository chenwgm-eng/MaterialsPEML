# ReactNavi 系统架构文档

> 版本: `reactnavi` v0.1.0 (Python 包) + ReactNavi Skill (SKILL.md)
> 生成日期: 2026-08-01

---

## 目录

1. [系统总览](#1-系统总览)
2. [文件架构](#2-文件架构)
3. [模块详解](#3-模块详解)
   - [3.1 Skill 层 (SKILL.md)](#31-skill-层-skillmd)
   - [3.2 reactnavi Python 包](#32-reactnavi-python-包)
   - [3.3 retrosynthesis_toolkit 模块](#33-retrosynthesis_toolkit-模块)
4. [核心 API: call_retrosynthesis](#4-核心-api-call_retrosynthesis)
5. [完整调用关系图](#5-完整调用关系图)
6. [数据流与输出解析](#6-数据流与输出解析)
7. [工作流算法](#7-工作流算法)
8. [错误诊断与回退策略](#8-错误诊断与回退策略)
9. [Mira 推理服务生态](#9-mira-推理服务生态)

---

## 1. 系统总览

ReactNavi 是一个**逆合成分析 (retrosynthesis)** 技能，目标是：给定一个目标分子，设计从可购买原料出发的合成路线。

系统采用**三层协作**架构：

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | `SKILL.md` (独文件) | 5 步交互工作流: 目标准备 → 方案确认 → 工具调用 → 错误诊断 → 路线评判 |
| **Python 包层** | `reactnavi` (v0.1.0, 5 文件) | 核心功能: `call_retrosynthesis` — 向 Retrosynthesis API 发送搜索请求 |
| **外部服务** | Retrosynthesis API (`http://101.126.18.187:8100`) + TOS 对象存储 | 多步逆合成树搜索 + 结果文件分发 |

**核心能力**:
- **数据驱动的单步模型**: 大规模模板库 (>文献报道范围) → 新颖路线
- **树搜索**: 从目标分子后向搜索直到可购买原料 (多步深度可配置)
- **多模态补充**: 结合 `web_search`, `search_scholar`, `search_patents` 获取文献/专利已验证路线
- **化学推理**: 盐形式归一化、立体化学保持、路线质量评判

---

## 2. 文件架构

### 2.1 Skill 目录 (`/app/skills/reactnavi/`)

```
reactnavi/
└── SKILL.md                          # 主入口 (11KB): 5 步工作流、参数表、诊断表、评判规则
```

### 2.2 Python 包目录 (`/root/miniconda3/lib/python3.11/site-packages/reactnavi/`)

```
reactnavi/
├── __init__.py                        # 顶层: 空 (不导出公共符号)
├── tools/
│   ├── __init__.py                    # 模块文档: "Agent/HTTP tools"
│   └── retrosynthesis_toolkit.cpython-311-x86_64-linux-gnu.so  # [Cython] 核心客户端 (86KB)
└── __pycache__/                       # 编译缓存
```

**总文件数**: 5 (含 .pyc)

---

## 3. 模块详解

### 3.1 Skill 层 (SKILL.md)

#### 3.1.1 5 步工作流

```
Step 1 — 目标准备
    ├── 1.1 解析目标分子为 SMILES (名称/IUPAC/CAS/InChI → SMILES)
    ├── 1.2 离子/盐形式归一化 → 中性母体 (最关键杠杆)
    │       [N+]/[P+]/[O-]/卤素反离子/金属盐/季铵盐 → 中性自由形式
    ├── 1.3 保留立体化学 (不剥离立体中心)
    └── 1.4 跳过工具 (若目标是商品化合物或其一步衍生物)

Step 2 — 方案确认
    ├── 目标: 确认的 SMILES + 归一化母体 + 搜索深度上限
    ├── 分工: ReactNavi 前驱体发现 / 推理补全 / 文献专利验证
    ├── 交付物: 少量审查过的候选路线 + 补全步骤
    └── 二选一:
        ├── A: ReactNavi-led (综合): 工具设计新路线 + 文献专利验证 (默认)
        └── B: 仅已报道路线 (简化): 仅文献专利路线

Step 3 — 调用工具
    ├── 默认搜索优先 (快速可靠基线)
    ├── 避免搜索爆炸:
    │   ├── 离子目标 → 搜索中性母体
    │   └── template_max_count=80 必须带 expansion_time=300 护栏
    ├── 每次一个目标 (不批量阻塞)
    └── 调用: call_retrosynthesis(target_smiles, output_dir, ...)

Step 4 — 错误诊断
    ├── 无模板匹配 (total_reactions=0): 回退到更简单前驱体 + 文献搜索
    ├── 有反应但无路径 (total_paths=0): 扩展深度或回退
    ├── 搜索挂起 (~640s): 离子目标爆炸 → 归一化未执行，重新做
    └── 升级 (用户同意后): template_max_count → 80 + expansion_time=300

Step 5 — 路线评判
    ├── 从 summary.json 读取路线
    ├── 化学标准排序: 步骤短、可购买原料、经典反应优先
    ├── 补充工具缺失: 产率/温度/先例 → web_search/scholar/patents
    ├── 标注来源: [model-predicted]/[literature:citation]/[inference:]/[speculative]
    ├── 立体化学验证
    └── 闭合归一化目标: 加盐步骤标记为推理步骤
```

#### 3.1.2 参数表 (call_retrosynthesis)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `target_smiles` | str | — | 目标 SMILES (离子目标用中性母体) |
| `output_dir` | str | `"runs"` | 本地结果目录 |
| `max_paths` | int | `10` | 返回路线数 |
| `max_draw` | int/None | `None`→10 | 路线图片数 |
| `max_depth` | int | `6` | 最大搜索深度 |
| `max_iterations` | int | `2000` | 迭代预算 |
| `template_max_count` | int | `20` | 每步 Top-N 模板 (≥80 需护栏) |
| `expansion_time` | int | `900` | 搜索时间预算 (秒) |
| `session_id` | str | `"prod-test-session"` | 会话 ID |
| `request_timeout` | int | `1200` | HTTP 超时 (秒) |

#### 3.1.3 诊断表 (Step 4)

| 返回特征 | 含义 | 行动 |
|----------|------|------|
| `total_reactions=0`, `total_templates=0`, <~2s | 无模板匹配 — 超出覆盖范围 | 回退到中性前驱体 + 文献/专利搜索 |
| `total_reactions>0`, `total_paths=0` | 前驱体不达可购买库 | 回退或扩展深度 |
| 挂起/~640s | 搜索树过膨胀 | 归一化重新执行；或带护栏升级 |
| 0 条路线 | 非 "不可合成"，仅工具覆盖缺口 | 不意味不可合成 |

#### 3.1.4 输出文件约定

| 文件 | 内容 |
|------|------|
| `api_response.json` | 全量 API JSON: `success`, `stats`, `pathways` |
| `retro_xxxxxxxx/summary.json` | **路线详情**: 嵌套 `tree` 含 `chemical`/`reaction` 节点，`reaction_smiles`, `ff_score`, `conditions`, `reactants` |
| `retro_xxxxxxxx/multi_step_pathway_N.png` | 路线 N 的图示 (对应 `route_rank`) |

---

### 3.2 reactnavi Python 包

#### 3.2.1 包结构

```
reactnavi (顶层包)
├── __init__.py          # 空模块，不导出公共符号
└── tools/
    ├── __init__.py      # 文档: "Agent/HTTP tools (e.g. multi-step retrosynthesis client)"
    └── retrosynthesis_toolkit.cpython-311.so  # [Cython] 编译核心
```

**关键特点**:
- 顶层 `reactnavi` 不导出任何公共符号 — 所有功能通过子模块调用
- `retrosynthesis_toolkit` 是 Cython 编译的 `.so` 文件 (86KB)
- 不依赖 RDKit、yamol 等重型化学库（仅标准库 + requests）

### 3.3 retrosynthesis_toolkit 模块

**源文件**: `tools/retrosynthesis_toolkit.cpython-311.so` [Cython]

**模块级常量**:

| 常量 | 值 | 说明 |
|------|-----|------|
| `RETROSYNTHESIS_API_URL` | `'http://101.126.18.187:8100/api/v1/multi-step'` | Retrosynthesis REST API 端点 |
| `TOS_ENDPOINT` | `'tos-cn-beijing.volces.com'` | 火山引擎 TOS 对象存储 |
| `TOS_BUCKET` | `'deepprinciple-services'` | TOS 存储桶 |
| `TOS_REGION` | `'cn-beijing'` | TOS 区域 |

**依赖**:
- `json` — 标准库
- `requests` — HTTP 客户端
- `uuid` — 唯一 ID 生成

#### `call_retrosynthesis` 函数

这是模块的**唯一公开函数**。

```
类型: cython_function_or_method (Cython 3.2.4 编译)
```

**签名**:
```python
call_retrosynthesis(
    target_smiles: str,
    output_dir: str,
    max_paths: int = 10,
    max_draw: Optional[int] = None,
    max_depth: int = 6,
    max_iterations: int = 2000,
    template_max_count: int = 20,
    expansion_time: int = 900,
    session_id: str = "prod-test-session",
    request_timeout: int = 1200,
) -> Dict[str, Any]
```

**内部工作流**:

```
call_retrosynthesis()
    │
    ├─ 1. 构造请求 payload
    │      └─ POST RETROSYNTHESIS_API_URL
    │         {target_smiles, max_paths, max_depth, max_iterations,
    │          template_max_count, expansion_time, session_id}
    │
    ├─ 2. 发送 HTTP 请求 (requests, timeout=request_timeout)
    │      └─ 阻塞等待直到 API 返回
    │
    ├─ 3. 接收 API 响应 JSON
    │      └─ 保存到 output_dir/api_response.json
    │
    ├─ 4. 解析 pathways 中的 image_file URL
    │      └─ 每个路线关联一个 TOS 上的 PNG 文件 URL
    │
    ├─ 5. 从 TOS 下载结果文件
    │      ├─ multi_step_pathway_N.png  (路线图示)
    │      └─ summary.json  (路线详情)
    │      └─ 保存到 output_dir/retro_xxxxxxxx/
    │
    └─ 6. 返回结果字典
           {success, download_dir, api_response_path, downloaded_files, error?}
```

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 调用是否成功 |
| `download_dir` | str | 下载目录路径 |
| `api_response_path` | str | `api_response.json` 路径 |
| `downloaded_files` | list[str] | 已下载文件列表 |
| `error` | str/None | 错误信息 (失败时) |

---

## 4. 外部服务架构

### 4.1 Retrosynthesis API

```
基础 URL:  http://101.126.18.187:8100
端点:      POST /api/v1/multi-step
超时:      request_timeout (默认 1200s)
```

**请求 Payload**:

```json
{
    "target_smiles": "CN(C)C1CCCCC1",
    "max_paths": 10,
    "max_depth": 6,
    "max_iterations": 2000,
    "template_max_count": 20,
    "expansion_time": 900,
    "session_id": "prod-test-session"
}
```

**响应结构** (api_response.json):

```json
{
    "success": true,
    "stats": {
        "total_iterations": 1500,
        "total_chemicals": 320,
        "total_reactions": 85,
        "total_templates": 12,
        "total_paths": 3,
        "search_time_s": 245.6
    },
    "pathways": [
        {
            "route_rank": 1,
            "avg_ff_score": 0.85,
            "min_ff_score": 0.72,
            "num_reactions": 3,
            "image_file": "https://tos-cn-beijing.volces.com/deepprinciple-services/retro_xxx/pathway_1.png"
        }
    ]
}
```

**stats 字段含义**:

| 字段 | 含义 |
|------|------|
| `total_iterations` | 搜索迭代总数 |
| `total_chemicals` | 探索到的分子数 |
| `total_reactions` | 匹配到的反应数 |
| `total_templates` | 使用的模板数 |
| `total_paths` | 找到的完整路线数 |
| `search_time_s` | 搜索耗时 (秒) |

### 4.2 TOS 对象存储

```
端点:  tos-cn-beijing.volces.com
桶:    deepprinciple-services
区域:  cn-beijing
```

API 返回路线 PNG 文件的 TOS URL，`call_retrosynthesis` 自动下载到本地。

### 4.3 Mira 推理服务 (生态系统)

ReactNavi Skill 提及关联的 Mira 推理服务:

| Slug | 名称 | 用途 |
|------|------|------|
| `retro-reaxys-service-e11206` | retro_reaxys_service | Reaxys 逆合成服务 |
| `forward-augmented-transformer-service-ed10db` | forward_augmented_transformer_service | 前向增强 Transformer |
| `parrot-service-5122b7` | parrot_service | 通用预测服务 |

---

## 5. 完整调用关系图

```
用户输入 (目标分子名称/结构)
    │
    ▼
╔══════════════════════════════════════════════╗
║  SKILL.md 层 (Agent 编排)                      ║
║                                                ║
║  Step 1: 目标准备                               ║
║    ├── 名称 → SMILES 解析                       ║
║    ├── 离子/盐归一化 (化学推理)                  ║
║    └── 立体化学保留                             ║
║                                                ║
║  Step 2: 方案确认 (用户交互)                     ║
║    └── 二选一: ReactNavi-led / 仅已报道路线       ║
║                                                ║
║  Step 3: 调用工具                               ║
║    │   call_retrosynthesis(target_smiles, ...)  ║
║    │                                            ║
║    ▼                                            ║
║  ┌──────────────────────────────┐              ║
║  │  reactnavi.tools             │              ║
║  │  retrosynthesis_toolkit      │              ║
║  │                              │              ║
║  │  call_retrosynthesis()       │              ║
║  │    │                         │              ║
║  │    ├─ POST → Retrosynthesis  │              ║
║  │    │         API             │              ║
║  │    │         /api/v1/        │              ║
║  │    │         multi-step      │              ║
║  │    │                         │              ║
║  │    └─ GET  ← TOS Object      │              ║
║  │              Storage         │              ║
║  └──────────────────────────────┘              ║
║                                                ║
║  Step 4: 错误诊断                               ║
║    └── 根据 stats 特征 → 行动决策               ║
║                                                ║
║  Step 5: 路线评判                               ║
║    ├── parse summary.json                       ║
║    ├── 化学标准排序                             ║
║    ├── web_search/scholar/patents → 补充验证    ║
║    └── 标注来源 → 交付                          ║
╚══════════════════════════════════════════════╝
```

---

## 6. 数据流与输出解析

### 6.1 请求流

```
SMILES (文本)
    │
    ▼
call_retrosynthesis()
    │
    ├─→ POST HTTP JSON  → Retrosynthesis API
    │                       {target_smiles, max_paths, max_depth, ...}
    │
    └─→ 阻塞等待 (≤ request_timeout)
        │
        ├─→ 成功: API 返回 JSON
        │      └── pathways[] → TOS image URLs
        │
        └─→ 失败/超时: 错误处理
```

### 6.2 响应解析流

```
api_response.json
    │
    ├── stats: 搜索统计
    │   ├── total_reactions  → 0? → 无模板匹配
    │   ├── total_paths      → 0? → 未到达可购买库
    │   └── search_time_s    → ~640s? → 搜索爆炸
    │
    ├── pathways[]: 路线列表
    │   ├── route_rank           (排名)
    │   ├── avg_ff_score          (搜索置信度，不意味质量)
    │   ├── min_ff_score          (最弱步骤置信度)
    │   ├── num_reactions         (步骤数)
    │   └── image_file            (TOS PNG URL)
    │
    └── summary.json (每个路线):
        └── tree: 嵌套 {chemical, reaction} 节点
            ├── reaction_smiles   (反应 SMILES)
            ├── ff_score           (该步骤置信度)
            ├── conditions         (预测反应条件)
            └── reactants[]        (前驱体)
                └── 继续递归...
```

### 6.3 路线质量标准 (Step 5)

| 标准 | 优先级 |
|------|--------|
| 步骤少、从可购买原料出发 | 高 |
| 经典反应 (非保护基绕路) | 高 |
| 无非安全中间体 (叠氮等) | 高 |
| 无双原子构建再剥离 | 高 |
| 无虚构反离子 | 高 |
| `ff_score` 值 | ⚠️ 仅搜索置信度，不用于质量评判 |

---

## 7. 工作流算法

### 7.1 逆合成树搜索

```
目标分子 (leaf)
    │
    ▼
单步逆合成模型
    │
    ├─ 从模板库 (template_max_count 控制) 匹配可应用的逆合成变换
    ├─ 生成前驱体集合 (多候选)
    └─ 对每个前驱体:
        │
        ├─ 可达可购买库? → 记录完整路线
        │
        └─ 未达? → 递归 (深度 ≤ max_depth)
                    └─ 迭代预算 ≤ max_iterations
                    └─ 时间预算 ≤ expansion_time

返回: max_paths 条完整路线，按内部评分排序
```

### 7.2 目标归一化算法 (Step 1)

```
输入: 离子/盐 SMILES
    │
    ├─ 检测: [N+], [P+], [O-], [OH-], 卤素反离子, 金属盐, 季铵盐
    │
    ├─ 归一化规则:
    │   ├─ 季铵盐 → 叔胺 (去季铵化)
    │   ├─ 季磷盐 → 膦
    │   ├─ 羧酸盐 → 羧酸
    │   ├─ 酚盐 → 酚
    │   ├─ 盐酸盐 → 自由胺
    │   └─ 金属配合物 → 自由配体
    │
    └─ 输出: 中性母体 SMILES (保留立体化学)
```

---

## 8. 错误诊断与回退策略

### 8.1 特征诊断

```
                    无模板匹配
total_reactions=0 ──────────────→ 超出覆盖范围
total_templates=0                    ↓
<~2s                             回退到更简单前驱体
                                  web_search + search_scholar + search_patents

                    有反应无路径
total_reactions>0 ──────────────→ 未达可购买库
total_paths=0                       ↓
                                 回退或扩展 max_depth

                    搜索爆炸
~640s 挂起 ─────────────────────→ 离子目标未归一化
                                  template_max_count/max_depth 过高
                                    ↓
                                 归一化重新执行
                                 或带护栏升级

                    升级路径
template_max_count → 80 ────────→ 仅用户同意
                                  expansion_time=300
                                  max_depth≤7
```

### 8.2 route 评判步骤

```
从 summary.json 解析每条路线
    │
    ├─ 每一步: reaction_smiles, ff_score, conditions, reactants
    │
    ├─ 标注每步来源:
    │   ├─ [model-predicted]      工具返回的步骤
    │   ├─ [literature: citation] 文献/专利验证的步骤
    │   ├─ [inference: basis]     化学推理补全的步骤
    │   └─ [speculative]          推测性步骤
    │
    ├─ 闭合归一化目标:
    │   └─ 中性母体路线 + 最后标注的盐形成步骤 = 完整合成
    │
    └─ 立体化学验证:
        ├─ 手性砌块引入?
        ├─ 立体专一性步骤 (Mitsunobu 等)?
        └─ 拆分?
```

---

## 附录

### A. 关键约束

| 约束 | 值 | 说明 |
|------|-----|------|
| 搜索深度上限 | ~6-7 步 (trial 版本) | 向用户声明 |
| template_max_count 护栏 | 80 时 expansion_time ≤ 300 | 防止搜索爆炸 |
| 单调用模式 | 每次一个目标 | 不批量，不阻塞循环 |
| 离子目标 | 必须归一化到中性母体 | 直接搜索带电形式会爆炸 |
| 立体化学 | 必须保留 | 剥离不增加覆盖率 |
| ff_score | 仅搜索置信度 | 不用于路线质量评判 |

### B. 与 ReactNet 对比

| 维度 | ReactNavi | ReactNet |
|------|-----------|----------|
| 问题 | 给定目标 → 合成路线 | 给定反应 → 能垒/TS |
| 方法 | 模板匹配 + 树搜索 | 量子化学 (xTB/g-xTB) |
| 计算 | HTTP API + TOS 下载 | 本地/云端 xTB/DFT |
| 复杂度 | 秒-分钟级搜索 | 分钟-小时级计算 |
| 输出 | 路线图 + reaction SMILES | 能垒 (kcal/mol) + TS 结构 |
