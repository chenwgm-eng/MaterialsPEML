# MPA (Material Property Axiom) 系统架构文档

> 技能名: `material-property-prediction`
> 服务 slug: `mpa-613bf0`
> 备份 slug: `axiom-mpa-gpu-service-ef6584`
> 生成日期: 2026-08-01

---

## 目录

1. [系统总览](#1-系统总览)
2. [文件架构](#2-文件架构)
3. [模块详解](#3-模块详解)
   - [3.1 Skill 层 (SKILL.md)](#31-skill-层-skillmd)
   - [3.2 独立客户端脚本 (mpa_predict.py)](#32-独立客户端脚本-mpa_predictpy)
4. [Mira 推理服务架构](#4-mira-推理服务架构)
5. [核心 API 详解](#5-核心-api-详解)
   - [5.1 POST /api/v1/predict](#51-post-apiv1predict)
   - [5.2 GET /api/v1/properties](#52-get-apiv1properties)
6. [完整调用关系图](#6-完整调用关系图)
7. [支持的 42 种属性](#7-支持的-42-种属性)
8. [错误处理](#8-错误处理)
9. [数据流](#9-数据流)

---

## 1. 系统总览

MPA (Material Property Axiom) 是一个**分子性质预测**服务，给定 SMILES 即可预测 42 种物理化学性质。

系统采用**三层架构**：

| 层级 | 组成 | 职责 |
|------|------|------|
| **Skill 层** | `SKILL.md` | 决策流：SMILES 解析 → 属性映射 → 调用推理 → 错误处理 |
| **Mira 推理层** | REST API (`mpa-613bf0`) | 深度学习模型推理，自动 3D 构象生成 |
| **独立客户端** | `scripts/mpa_predict.py` | 纯标准库 HTTP 客户端，适用于非 Mira 环境 |

**核心能力**:
- **42 种性质**：沸点、熔点、闪点、密度、蒸气压、临界常数、粘度、热导率、热容、生成焓/Gibbs、燃烧热、水溶性、logD、表面张力、折射率、介电常数、偶极矩、可燃极限等
- **批量预测**：一次请求支持多个 SMILES
- **多性质聚合**：客户端自动循环，生成分子×性质矩阵
- **自动预处理**：服务端自动生成临时 3D 构象
- **输出原始单位**：服务端返回原始单位值，无需反归一化

---

## 2. 文件架构

### 2.1 Skill 目录 (`/app/skills/material-property-prediction/`)

```
material-property-prediction/
├── SKILL.md                          # 主入口 (8.2KB): 决策流 + 属性表 + 实现说明
└── scripts/
    └── mpa_predict.py                # 独立 Python 客户端 (4.4KB)
```

### 2.2 Mira 推理服务

```
slug:        mpa-613bf0
显示名称:    mpa
GPU 服务:    axiom-mpa-gpu-service-ef6584 (A30 GPU)
状态:        RUNNING
副本数:      1
基 URL:      https://didi.deepprinciple.com/inference/mpa-613bf0/
```

**服务拓扑**:
```
mpa-613bf0 (生产服务)
    ├── 描述: "MPA inference service (recreated 2026-06-03 after default→didi ns migration)"
    ├── GPU: 未显式标注 (CPU worker?)
    ├── 副本: 1
    └── 认证: SciClaw JWT (自动)

axiom-mpa-gpu-service-ef6584 (GPU 服务)
    ├── 描述: "Axiom MPA GPU 性质预测(43 bundle)+ 在线微调 HTTP 服务。vke-prod A30"
    ├── GPU: 1 × NVIDIA A30
    └── 支持在线微调 (fine-tuning)
```

---

## 3. 模块详解

### 3.1 Skill 层 (SKILL.md)

#### 3.1.1 决策流

```
用户输入 (性质查询)
    │
    ├─ 1. SMILES 解析
    │   ├── 直接 SMILES → 使用
    │   ├── 名称/IUPAC/CAS/InChI → PubChem/web_search 解析
    │   └── 不确定 → 确认 SMILES 结构 (渲染 2D)
    │
    ├─ 排除: 盐、混合物、立体/互变异构敏感、小/无机分子 (水等)
    │
    ├─ 2. 属性选择
    │   ├── 精确 property_name (见属性表)
    │   └── 自然语言 → 映射到 property_name
    │       例: "沸点" → BP_K
    │           "闪点" → flash_point_K
    │           "溶解度" → log_solubility_water_molL / log_solubility_water_ppm
    │
    ├─ 3. 运行预测
    │   ├── 在 Mira chats: mira_inference_call POST /api/v1/predict
    │   └── 聚合多属性结果 → 分子×性质矩阵
    │
    └─ 4. 错误处理
```

#### 3.1.2 分子×性质矩阵输出格式

```json
{
    "smiles_list": ["CCO", "Cc1ccccc1"],
    "properties": ["BP_K", "flash_point_K"],
    "predictions": {
        "BP_K": [354.60694885111246, 381.3260243483708],
        "flash_point_K": [281.76129861849967, 278.99966747537945]
    }
}
```

`predictions[property_name][i]` 对应 `smiles_list[i]`。如果一个属性预测失败，记录到 `errors` 字段，其他属性继续返回。

#### 3.1.3 实现说明

- Mira chats 使用 `mira_inference_call` 工具
- `scripts/mpa_predict.py` 仅用于显式提供 `MPA_BASE_URL` + `MPA_API_TOKEN` 的独立环境
- 服务端自动处理 3D 构象生成和预处理
- `num_confs` 默认 1，除非用户明确要求构象系综

### 3.2 独立客户端脚本 (mpa_predict.py)

**文件**: `scripts/mpa_predict.py` (4,386 B)
**依赖**: 仅 Python 标准库 (`urllib`, `json`, `argparse`, `os`, `sys`)

#### 3.2.1 模块结构

```
mpa_predict.py
├── 常量
│   ├── BASE_URL   = os.environ["MPA_BASE_URL"]    (可配置)
│   └── API_TOKEN  = os.environ["MPA_API_TOKEN"]   (可配置)
│
├── 类
│   └── MPAError(Exception)                HTTP/网络错误异常
│
├── 函数
│   ├── _request(path, method, payload, timeout) → dict
│   │       底层 HTTP 请求 (urllib)
│   │       认证: Bearer Token
│   │
│   ├── predict_one(property_name, smiles, num_confs, batch_size) → dict
│   │       单个属性预测
│   │
│   ├── predict(properties, smiles, num_confs, batch_size) → (dict, dict)
│   │       多属性批量预测
│   │       循环调用 predict_one，聚合结果
│   │
│   ├── list_properties() → dict
│   │       列出可用属性
│   │
│   └── main()
│            CLI 入口: --property, --smiles, --num-confs, --batch-size,
│                      --list-properties
```

#### 3.2.2 函数详解

##### `_request(path, method, payload, timeout)` — 底层 HTTP 客户端

```python
def _request(path, method="GET", payload=None, timeout=120):
```
- 检查 `BASE_URL` 和 `API_TOKEN` 环境变量
- 构造 `Authorization: Bearer <API_TOKEN>` 头
- `Content-Type: application/json` (POST 时)
- 错误处理: `HTTPError` (4xx/5xx) → `MPAError` with body
- 网络错误: `URLError` → `MPAError`

##### `predict_one(property_name, smiles, num_confs, batch_size)` — 单属性预测

```python
def predict_one(property_name, smiles, num_confs=1, batch_size=8):
    payload = {
        "property_name": property_name,
        "smiles": smiles,           # str 列表
        "num_confs": num_confs,     # 每分子构象数
        "batch_size": batch_size,   # 推理批次大小
    }
    return _request("/api/v1/predict", method="POST", payload=payload)
```

##### `predict(properties, smiles, num_confs, batch_size)` — 批量多属性预测

```python
def predict(properties, smiles, num_confs=1, batch_size=8):
    predictions, errors = {}, {}
    for prop in properties:
        try:
            res = predict_one(prop, smiles, num_confs, batch_size)
            predictions[prop] = res.get("prediction_list")
        except MPAError as e:
            errors[prop] = str(e)
    # ... 组装输出字典
    return out, errors
```

**关键设计**:
- 服务端每次只接受一个属性 → 客户端循环聚合
- 一个属性失败不中止整个批次 → errors 单独记录
- 返回值中 `out["predictions"][prop][i]` 对应 `smiles[i]`

##### `main()` — CLI 入口

```
usage: mpa_predict.py [--property ...] [--smiles ...] [--num-confs N]
                      [--batch-size N] [--list-properties]
```

| 参数 | 说明 |
|------|------|
| `--property` | 一个或多个 property_name (如 BP_K flash_point_K) |
| `--smiles` | 一个或多个 SMILES 字符串 |
| `--num-confs` | 每分子 3D 构象数 (默认 1) |
| `--batch-size` | 推理批次大小 (默认 8) |
| `--list-properties` | 列出可用属性并退出 |

#### 3.2.3 依赖图

```
mpa_predict.py
├── urllib.request (标准库)
│   ├── Request (构造 HTTP 请求)
│   └── urlopen (发送请求)
├── urllib.error (标准库)
│   ├── HTTPError
│   └── URLError
├── json (标准库)
├── argparse (标准库)
├── os (标准库)
└── sys (标准库)
```

---

## 4. Mira 推理服务架构

### 4.1 服务信息

| 属性 | 值 |
|------|-----|
| Slug | `mpa-613bf0` (生产) / `axiom-mpa-gpu-service-ef6584` (GPU) |
| 基 URL | `https://didi.deepprinciple.com/inference/mpa-613bf0/` |
| 状态 | RUNNING |
| 副本 | 1 |
| GPU | mpa-613bf0 未标 GPU；axiom-mpa-gpu-service-ef6584 有 1×A30 |
| 认证 | SciClaw JWT (自动) |
| 上线日期 | 2026-06-03 (重建) |

### 4.2 端点

| 方法 | 路径 | 用途 | 调用工具 |
|------|------|------|----------|
| POST | `/api/v1/predict` | 预测一个属性 | `mira_inference_call` |
| GET | `/api/v1/properties` | 列出可用属性 | `mira_inference_call` GET |

### 4.3 模型架构 (推断)

```
输入: SMILES 列表
    │
    ├─→ 3D 构象生成 (服务端自动)
    │     └─ num_confs 控制每分子构象数
    │
    ├─→ 分子图编码 (GNN/Transformer?)
    │
    ├─→ 属性预测头 (回归/分类)
    │     └─ 42 个任务特定输出头
    │
    ├─→ 反归一化 (服务端)
    │     └─ 输出原始物理单位
    │
    └─→ 返回: {prediction_list: [值1, 值2, ...]}
```

---

## 5. 核心 API 详解

### 5.1 POST /api/v1/predict

**用途**: 预测一个属性的值

**请求体**:

```json
{
    "property_name": "BP_K",
    "smiles": ["CCO", "c1ccccc1"],
    "num_confs": 1,
    "batch_size": 8
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `property_name` | str | 是 | — | 属性名 (见 §7 完整列表) |
| `smiles` | list[str] | 是 | — | 一个或多个 SMILES |
| `num_confs` | int | 否 | 1 | 3D 构象数 |
| `batch_size` | int | 否 | 8 | 推理批次大小 |

**响应**:

```json
{
    "prediction_list": [354.60694885111246, 381.3260243483708]
}
```

`prediction_list[i]` 对应 `smiles[i]`，值已经在该属性的原始物理单位 (K, g/cm³, etc.)。

**Mira 调用**:

```python
mira_inference_call(
    slug="mpa-613bf0",
    path="/api/v1/predict",
    method="POST",
    json_body={
        "property_name": "BP_K",
        "smiles": ["CCO", "c1ccccc1"],
        "num_confs": 1,
        "batch_size": 8,
    },
)
```

### 5.2 GET /api/v1/properties

**用途**: 列出当前服务支持的属性列表

**Mira 调用**:

```python
mira_inference_call(
    slug="mpa-613bf0",
    path="/api/v1/properties",
    method="GET",
)
```

**响应结构** (推断):
```json
{
    "properties": [
        {"name": "BP_K", "unit": "K", "description": "Normal boiling temperature"},
        ...
    ]
}
```

---

## 6. 完整调用关系图

```
用户输入 (性质查询 + 分子)
    │
    ▼
╔══════════════════════════════════════════════╗
║  SKILL.md 层 (Agent 编排)                      ║
║                                                ║
║  1. SMILES 解析                                ║
║     ├── 名称→SMILES (PubChem/web_search)        ║
║     └── 排除: 盐/混合物/无机/水                  ║
║                                                ║
║  2. 属性映射                                    ║
║     └── 自然语言 → property_name               ║
║                                                ║
║  3. API 调用                                   ║
║     │                                           ║
║     ├── Mira 环境:                              ║
║     │   mira_inference_call(                   ║
║     │       slug="mpa-613bf0",                 ║
║     │       path="/api/v1/predict",            ║
║     │       method="POST",                     ║
║     │       json_body={property_name, smiles}  ║
║     │   )                                       ║
║     │           │                               ║
║     │           ▼                               ║
║     │   ┌───────────────────────┐              ║
║     │   │  MPA Inference Service │              ║
║     │   │  mpa-613bf0            │              ║
║     │   │                        │              ║
║     │   │  POST /api/v1/predict  │              ║
║     │   │    ├─ SMILES → 3D 构象 │              ║
║     │   │    ├─ 深度学习推理     │              ║
║     │   │    └─ 反归一化→原单位  │              ║
║     │   └───────────────────────┘              ║
║     │                                           ║
║     └── 独立环境:                                ║
║         python mpa_predict.py                  ║
║           --property BP_K                      ║
║           --smiles CCO c1ccccc1                ║
║             │                                   ║
║             ├── predict_one(prop, smiles)      ║
║             │     └── _request("/api/v1/        ║
║             │           predict", POST)         ║
║             │         └── urllib.request        ║
║             │             Bearer MPA_API_TOKEN  ║
║             │                                   ║
║             └── predict(props, smiles)          ║
║                   └── for prop in props:        ║
║                         predict_one(prop, ...)  ║
║                   └── 聚合 predictions{}        ║
║                                                ║
║  4. 错误处理                                    ║
║     ├── 400: 无效 SMILES/构象失败               ║
║     ├── 401: 认证配置问题                       ║
║     ├── 404: 缺少模型检查点                     ║
║     ├── 422: 请求 schema 错误                   ║
║     └── 500: 模型加载/推理失败                   ║
╚══════════════════════════════════════════════╝
```

---

## 7. 支持的 42 种属性

### 热力学性质

| property_name | 性质 | 单位 |
|---------------|------|------|
| `BP_K` | 常压沸点 (1 atm) | K |
| `fusion_T_K` | 熔点/三相点 | K |
| `autoignition_K` | 自燃温度 | K |
| `flash_point_K` | 闪点 | K |
| `Pc_bar` | 临界压力 | bar |
| `Tc_K` | 临界温度 | K |
| `Vc_cm3mol` | 临界摩尔体积 | cm³/mol |
| `omega` | Pitzer 偏心因子 | 无量纲 |
| `Hf_gas_kJmol` | 标准气态生成焓 (298K) | kJ/mol |
| `Hf_liq_kJmol` | 标准液态生成焓 (298K) | kJ/mol |
| `Gf_gas_kJmol` | 标准气态 Gibbs 自由能 (298K) | kJ/mol |
| `H_combus_kJmol` | 标准燃烧热 (HHV, 298K) | kJ/mol |
| `Hfus_at_TF_kJmol` | 熔化焓 (熔点) | kJ/mol |
| `Hvap_at_TB_kJmol` | 蒸发焓 (沸点) | kJ/mol |
| `S_gas_JmolK` | 标准气态熵 (298K) | J/(mol·K) |
| `Sf_gas_JmolK` | 气态生成熵 (298K) | J/(mol·K) |

### 输运性质

| property_name | 性质 | 单位 |
|---------------|------|------|
| `density_liq_298K_gcm3` | 液态密度 (25°C) | g/cm³ |
| `visc_liq_298K_cP` | 液态动力粘度 (25°C) | cP = mPa·s |
| `visc_gas_298K_uPas` | 气态动力粘度 (25°C) | µPa·s |
| `k_liq_298K` | 液态热导率 (25°C) | W/(m·K) |
| `k_gas_298K` | 气态热导率 (25°C) | W/(m·K) |
| `ST_298K_mNm` | 表面张力 (25°C) | mN/m |
| `expand_coeff_liq_K-1_log10` | log10(液态热膨胀系数) | log10(1/K) |

### 热容

| property_name | 性质 | 单位 |
|---------------|------|------|
| `Cp_gas_298K` | 气态热容 (298K) | J/(mol·K) |
| `Cp_liq_298K` | 液态热容 (298K) | J/(mol·K) |

### 相平衡

| property_name | 性质 | 单位 |
|---------------|------|------|
| `Pvap_log10mmHg` | 蒸气压 (298K) | log10(mmHg) |
| `log_Henry_atmmolfrac` | Henry 常数 (Yaws 约定) | log10(atm/molfrac) |

### 溶解度与分配

| property_name | 性质 | 单位 |
|---------------|------|------|
| `log_solubility_water_molL` | 水溶性 (25°C, 摩尔浓度) | log10(mol/L) |
| `log_solubility_water_ppm` | 水溶性 (25°C, 重量 ppm) | log10(ppm wt) |
| `ESOL_logS` | 水溶性 log10(S) | log10(mol/L) |
| `freesolv_dG_kcalmol` | 水合自由能 | kcal/mol |
| `Lipophilicity_logD` | 辛醇/缓冲液分配系数 (pH 7.4) | logD |
| `log_Koc` | 土壤有机碳分配系数 | log10 |

### 电学/光学

| property_name | 性质 | 单位 |
|---------------|------|------|
| `dielectric_298K` | 静态介电常数 (25°C) | 无量纲 |
| `dipole_moment_D` | 分子偶极矩 | Debye |
| `RI_298K` | 折射率 (25°C) | 无量纲 |

### 安全相关

| property_name | 性质 | 单位 |
|---------------|------|------|
| `LEL_volpct` | 爆炸下限 (25°C) | vol% |
| `UEL_volpct` | 爆炸上限 (25°C) | vol% |

### 分子描述符 / 其他

| property_name | 性质 | 单位 |
|---------------|------|------|
| `gyration_radius_A` | 回转半径 | Å |
| `PPBR_pct` | 血浆蛋白结合率 | % |
| `Q_10ppmv_mgg` | 活性炭吸附容量 (10 ppmv) | mg/g |
| `CEP_PCE` | 清洁能源项目光电转换效率代理 | 未指定 |

---

## 8. 错误处理

### 8.1 HTTP 状态码

| 状态码 | 含义 | 处理 |
|--------|------|------|
| `400` | 无效 SMILES、构象生成失败、空 SMILES | 检查输入 |
| `401` | 认证/访问配置问题 | 报告服务访问配置需要检查 |
| `404` | 缺少检查点或缺训练数据 | 检查 property_name |
| `422` | 请求 schema 验证错误 | 检查必填字段、batch_size |
| `500` | 模型加载或推理失败 | 报告服务内部错误 |

### 8.2 客户端错误 (mpa_predict.py)

| 异常 | 原因 | 处理 |
|------|------|------|
| `MPAError("MPA_BASE_URL and MPA_API_TOKEN are required...")` | 环境变量未设置 | 设置环境变量或使用 Mira 工具 |
| `MPAError("HTTP 400: ...")` | 无效 SMILES | 验证输入 |
| `MPAError("Network error: ...")` | DNS/TLS/连接问题 | 检查网络 |

### 8.3 多属性批处理容错

```python
# predict() 函数设计: 一个属性失败不中止整个批次
for prop in properties:
    try:
        predictions[prop] = predict_one(prop, ...)
    except MPAError as e:
        errors[prop] = str(e)  # 记录错误，继续下一个属性
```

---

## 9. 数据流

```
SMILES 列表 (输入)
    │
    ▼
┌─────────────────────────────────┐
│  服务端 (mpa-613bf0)             │
│                                  │
│  1. SMILES → 3D 构象生成        │
│     (自动，num_confs 控制)       │
│                                  │
│  2. 分子图编码                   │
│     (GNN / 深度学习架构)         │
│                                  │
│  3. 属性特定预测头               │
│     (回归: 沸点等; 分类: 可燃限)  │
│                                  │
│  4. 反归一化                     │
│     (模型内部值 → 原始物理单位)   │
│                                  │
│  5. 返回: {prediction_list: [...]}│
└─────────────────────────────────┘
    │
    ▼
属性值 (原始物理单位)
    ├── 温度: K
    ├── 压力: bar, log10(mmHg)
    ├── 密度: g/cm³
    ├── 粘度: cP, µPa·s
    ├── 热导率: W/(m·K)
    ├── 能量: kJ/mol, kcal/mol
    ├── 溶解度: log10(mol/L), log10(ppm)
    ├── 电学: 无量纲, Debye
    └── 其他: vol%, Å, %, mg/g
```

---

## 附录

### A. 与 ReactNavi / ReactNet 对比

| 维度 | MPA | ReactNavi | ReactNet |
|------|-----|-----------|----------|
| 问题 | 分子性质预测 | 合成路线设计 | TS 搜索与反应网络 |
| 方法 | 深度学习 (GNN) | 模板匹配 + 树搜索 | 半经验/DFT 量子化学 |
| 计算 | GPU 推理 (毫秒-秒) | HTTP API (秒-分钟) | 本地/云端 xTB (分钟-小时) |
| 输入 | SMILES | 目标分子 SMILES | 反应 SMILES |
| 输出 | 物理化学性质值 | 合成路线 + 反应条件 | 能垒 + TS 结构 |
| 服务 | Mira mpa-613bf0 | Retrosynthesis API + TOS | Mira reactnet-19d712 |

### B. 关键约束

| 约束 | 说明 |
|------|------|
| 不支持盐/混合物 | 仅纯分子 |
| 不支持水等小分子 | 用水请直接 web_search |
| 不支持立体化学敏感 | 可能不准确 |
| num_confs 默认 1 | 仅在明确要求构象系综时调高 |
| batch_size 默认 8 | 仅在必要时调整 |
| 每请求单属性 | 多属性需多次请求，客户端聚合 |
