# OpenMPA 本地材料性质预测 CLI 开发说明书

**版本**：V0.1  
**项目名**：`openmpa`  
**定位**：本地、可插拔、可校准的分子材料性质预测 CLI  
**命令行入口**：`ompa`

---

## 1. 目标与边界

OpenMPA 以 SMILES 为主输入，完成分子标准化、2D/3D 特征准备、多性质批量预测、不确定性估计、适用域判断、单位规范化和结构化报告输出。

所附 MPA 文档体现的是“一个 SMILES 列表 + 一个性质名 + 3D 构象数 + batch size -> 预测列表”的服务模式，并支持多性质聚合、性质元数据查询、重试、错误隔离和 JSON 输出。OpenMPA 应重构这些**功能接口与工程能力**，但不得调用、复制或依赖原始私有 GPU 服务、JWT、模型权重、API、部署地址或品牌标识。

V0.1 的模型必须是本地可部署、许可可核验的开源模型或由用户自行训练的模型。所有数值均应附带单位、模型版本、适用域和不确定性，不得视为实验真值。

---

## 2. 预测范围

### 2.1 V0.1 首批性质

按可用开源数据集和模型成熟度分阶段支持；每个性质均可独立启用：

| 分类 | 内部键名示例 | 单位 |
|---|---|---|
| 沸点 | `boiling_point_k` | K |
| 熔点 | `melting_point_k` | K |
| 闪点 | `flash_point_k` | K |
| 密度 | `density_liquid_298k_g_cm3` | g/cm3 |
| 水溶解度 | `log_solubility_water_mol_l` | log10(mol/L) |
| LogD | `logd_ph_7_4` | 无量纲 |
| 黏度 | `viscosity_liquid_298k_cp` | cP |
| 表面张力 | `surface_tension_298k_mn_m` | mN/m |
| 临界温度 | `critical_temperature_k` | K |
| 临界压力 | `critical_pressure_bar` | bar |
| 偶极矩 | `dipole_moment_debye` | D |
| 折射率 | `refractive_index_298k` | 无量纲 |

### 2.2 后续可扩展性质

- 汽化焓、生成焓、燃烧焓、Gibbs 自由能
- 热容、导热系数、热膨胀系数
- 蒸气压、Henry 常数
- 爆炸极限、自燃温度
- 毒理、环境归趋和吸附相关描述符

对缺少可靠训练集、定义不明确或实验条件高度依赖的性质，不得在 V0.1 中用未经校准的“通用模型”声称准确预测。

---

## 3. 总体架构

```text
SMILES / CSV / SDF
      │
      ▼
RDKit 标准化与化学有效性检查
      │
      ├── canonical SMILES / InChIKey
      ├── 电荷、元素、分子量、盐和片段处理
      └── 无效结构隔离
      ▼
特征与构象准备
      │
      ├── 2D descriptors / fingerprints
      ├── 图神经网络输入
      └── 可选 ETKDG + xTB 3D conformers
      ▼
性质路由与本地模型推理
      │
      ├── QSPR 基线模型
      ├── GNN/Transformer 模型
      └── 物理约束/规则基线
      ▼
集成、不确定性、适用域和单位校验
      │
      ▼
JSON / CSV / Parquet / Markdown 报告
```

---

## 4. 项目目录

```text
openmpa/
├── pyproject.toml
├── environment.yml
├── configs/
│   ├── predict.yaml
│   ├── properties.yaml
│   ├── models.yaml
│   └── calibration.yaml
├── data/
│   ├── registry/
│   ├── reference_sets/
│   └── benchmarks/
├── models/
│   ├── manifests/
│   ├── qsar/
│   └── gnn/
├── src/openmpa/
│   ├── cli/
│   │   ├── app.py
│   │   ├── init_cmd.py
│   │   ├── doctor_cmd.py
│   │   ├── properties_cmd.py
│   │   ├── predict_cmd.py
│   │   ├── benchmark_cmd.py
│   │   ├── calibrate_cmd.py
│   │   └── report_cmd.py
│   ├── core/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── units.py
│   │   └── errors.py
│   ├── chemistry/
│   │   ├── standardize.py
│   │   ├── descriptors.py
│   │   ├── fingerprints.py
│   │   ├── conformers.py
│   │   └── domain.py
│   ├── registry/
│   │   ├── property_registry.py
│   │   ├── model_registry.py
│   │   └── schema.py
│   ├── predictors/
│   │   ├── base.py
│   │   ├── sklearn_qspr.py
│   │   ├── torch_gnn.py
│   │   ├── ensemble.py
│   │   ├── rules.py
│   │   └── router.py
│   ├── calibration/
│   │   ├── conformal.py
│   │   ├── isotonic.py
│   │   ├── metrics.py
│   │   └── split.py
│   ├── io/
│   │   ├── input.py
│   │   ├── output.py
│   │   ├── artifacts.py
│   │   └── report.py
│   └── utils/
│       ├── hashes.py
│       ├── logging.py
│       └── paths.py
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

---

## 5. CLI 设计

```bash
# 初始化项目
ompa init ./projects/property_screening

# 检查本地模型、RDKit 和可选 3D 工具
ompa doctor --strict

# 查看性质注册表
ompa properties list
ompa properties show boiling_point_k

# 一分子多性质预测
ompa predict \
  --smiles "CCO" \
  --property boiling_point_k flash_point_k log_solubility_water_mol_l \
  --config configs/predict.yaml

# 多分子、多性质、写 CSV 和 JSON
ompa predict \
  --input molecules.csv \
  --smiles-column smiles \
  --property boiling_point_k density_liquid_298k_g_cm3 \
  --output results/predictions.csv \
  --json-output results/predictions.json

# 启用 3D 构象特征
ompa predict \
  --smiles "CCO" "c1ccccc1" \
  --property boiling_point_k \
  --num-confs 5 \
  --batch-size 16

# 评估/校准用户模型
ompa benchmark --dataset data/benchmarks/bp_test.csv --property boiling_point_k
ompa calibrate --dataset data/reference_sets/bp_calibration.csv --property boiling_point_k
```

---

## 6. API 与输出契约

### 6.1 Python API

```python
result = predict_properties(
    properties=["boiling_point_k", "flash_point_k"],
    smiles=["CCO", "Cc1ccccc1"],
    num_confs=1,
    batch_size=8,
)
```

返回结构：

```json
{
  "smiles_list": ["CCO", "Cc1ccccc1"],
  "properties": ["boiling_point_k", "flash_point_k"],
  "predictions": {
    "boiling_point_k": [351.2, 383.6],
    "flash_point_k": [286.1, 278.4]
  },
  "prediction_records": [
    {
      "input_smiles": "CCO",
      "canonical_smiles": "CCO",
      "property_name": "boiling_point_k",
      "value": 351.2,
      "unit": "K",
      "uncertainty": 18.5,
      "domain_status": "IN_DOMAIN",
      "model_id": "bp_qspr_v1",
      "model_hash": "sha256:..."
    }
  ],
  "errors": {}
}
```

### 6.2 错误隔离原则

- 某个 SMILES 无效：只影响该分子，写入 `molecule_errors`
- 某个性质模型不存在或失败：只影响该性质，写入 `property_errors`
- 一项失败不得中断其余分子和性质
- 命令退出码：全成功为 0；部分成功为 1；配置或运行环境错误为 2

---

## 7. 性质注册表

文件：`configs/properties.yaml`

```yaml
properties:
  boiling_point_k:
    display_name: Normal boiling point
    unit: K
    target_type: regression
    temperature_k: null
    pressure_bar: 1.01325
    required_conditions: [pressure_bar]
    valid_range: [100.0, 1500.0]
    model_family: qsar_or_gnn

  flash_point_k:
    display_name: Flash point
    unit: K
    target_type: regression
    temperature_k: null
    required_conditions: []
    valid_range: [150.0, 1000.0]
    model_family: qsar_or_gnn

  log_solubility_water_mol_l:
    display_name: Aqueous solubility
    unit: log10(mol/L)
    target_type: regression
    temperature_k: 298.15
    ph: null
    required_conditions: [temperature_k]
    valid_range: [-16.0, 2.0]
    model_family: qsar_or_gnn
```

每个性质必须定义测量条件、单位、合理数值范围、模型族和适用域策略。不同实验定义不应被错误混合，例如常压沸点、某压力下沸点和不同 pH 下溶解度必须是不同注册项。

---

## 8. 模型注册表与许可证

每个本地模型必须具备 `model_manifest.json`：

```json
{
  "model_id": "bp_qspr_v1",
  "property_name": "boiling_point_k",
  "model_type": "sklearn_random_forest",
  "artifact_path": "models/qsar/bp_qspr_v1.joblib",
  "artifact_sha256": "sha256:...",
  "feature_schema": "rdkit_descriptors_v1",
  "training_dataset": "user-curated-bp-v1",
  "training_dataset_license": "internal_or_verified",
  "split_strategy": "scaffold_split",
  "metrics": {
    "mae": 18.4,
    "rmse": 26.1,
    "r2": 0.86
  },
  "calibration": "conformal_v1",
  "created_at": "2026-08-01T00:00:00+08:00"
}
```

禁止无模型清单直接加载权重。模型输出必须带上 `model_id` 和 `artifact_sha256`。

---

## 9. 特征与 3D 策略

### 9.1 2D 默认路径

V0.1 默认用 RDKit 2D 特征，可包括：

- Morgan fingerprints
- 物化描述符：分子量、TPSA、LogP、HBD、HBA、环数、可旋转键、形式电荷
- 片段与官能团计数
- Bemis-Murcko scaffold 标识

优点是快速、确定性强，适合多数初筛性质。

### 9.2 可选 3D 路径

当某性质的模型清单要求 3D 特征时：

1. RDKit ETKDG 生成 `num_confs` 构象
2. MMFF/UFF 预优化
3. 可选 xTB 优化
4. 依据相对能量进行 Boltzmann 加权
5. 提取 3D 描述符或输入 3D GNN

若 3D 失败，且模型允许 2D fallback，则标记 `FALLBACK_2D`；否则该性质返回结构化错误。

---

## 10. 预测器接口

文件：`predictors/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PredictionBatch:
    values: list[float | None]
    uncertainty: list[float | None]
    metadata: list[dict]


class PropertyPredictor(ABC):
    model_id: str
    property_name: str

    @abstractmethod
    def predict(
        self,
        canonical_smiles: list[str],
        feature_bundle: "FeatureBundle",
        batch_size: int,
    ) -> PredictionBatch:
        ...
```

支持三类实现：

- `sklearn_qspr.py`：快速基线、可解释、CPU 优先
- `torch_gnn.py`：分子图或 3D 图网络，可选 GPU
- `ensemble.py`：多模型平均、分位数或堆叠集成

---

## 11. 不确定性与适用域

### 11.1 最低要求

每条预测必须返回：

- 数值
- 单位
- 预测不确定性或未提供原因
- 适用域状态：`IN_DOMAIN`、`BORDERLINE`、`OUT_OF_DOMAIN`
- 模型和校准版本

### 11.2 适用域方法

V0.1 至少实现其中一种：

- Morgan 指纹到训练集最近邻 Tanimoto 相似度
- 描述符空间 Mahalanobis 距离
- 模型集成方差

建议规则：

```text
similarity >= 0.60       -> IN_DOMAIN
0.40 <= similarity < .60 -> BORDERLINE
similarity < 0.40        -> OUT_OF_DOMAIN
```

阈值必须按具体模型训练集通过验证确定，而不是全局固定真理。

### 11.3 置信区间

优先使用保形预测或分位数模型；若尚未校准，则输出模型集成标准差并明确 `uncertainty_method=UNCALIBRATED_ENSEMBLE_STD`。

---

## 12. 配置文件

### 12.1 `configs/predict.yaml`

```yaml
runtime:
  batch_size: 8
  workers: 1
  fail_fast: false

input:
  standardize: true
  strip_salts: false
  allowed_elements: [H, C, N, O, F, Cl, Br, I, S, P, B, Si]

features:
  use_2d: true
  use_3d_when_required: true
  num_confs: 1
  conformer_engine: rdkit_etkdg
  optimize_conformers: mmff
  max_conformer_attempts: 20

prediction:
  domain_check: true
  uncertainty: true
  enforce_valid_range: false
  model_registry: models/manifests

output:
  include_descriptors: false
  include_model_metadata: true
  write_parquet: true
```

### 12.2 `configs/calibration.yaml`

```yaml
split:
  strategy: scaffold
  calibration_fraction: 0.2

conformal:
  alpha: 0.1
  method: absolute_residual

metrics:
  report: [mae, rmse, r2, coverage, interval_width]
```

---

## 13. 输出文件

```text
runs/property_screening/
├── inputs/
│   ├── molecules.csv
│   ├── resolved_config.yaml
│   └── run_manifest.json
├── features/
│   ├── standardized_molecules.csv
│   └── conformers/
├── results/
│   ├── predictions_long.csv
│   ├── predictions_wide.csv
│   ├── predictions.json
│   ├── predictions.parquet
│   ├── molecule_errors.csv
│   ├── property_errors.csv
│   └── summary.md
└── logs/
    └── predict.log
```

`predictions_long.csv`：

```text
molecule_id
input_smiles
canonical_smiles
inchikey
property_name
value
unit
uncertainty
uncertainty_method
domain_status
domain_score
model_id
model_hash
feature_schema
num_confs_requested
num_confs_used
status
error_code
```

`predictions_wide.csv`：每行一个分子；每个性质至少输出三列：`<property>_value`、`<property>_unit`、`<property>_uncertainty`。

---

## 14. 单位与合理性检查

- 不允许仅输出裸数值
- 不允许将 K、C、bar、Pa、cP、Pa*s、g/cm3、kg/m3、mol/L 和 ppm 混存而不声明转换
- 预测结果超出注册表 `valid_range` 时保留原值但标记 `OUT_OF_RANGE`
- `log_solubility_water_mol_l` 等对数单位必须保存明确对数基底和原单位
- 转换函数集中于 `core/units.py`，禁止散落在模型实现中

---

## 15. 测试计划

### 15.1 单元测试

- SMILES 标准化、盐/片段策略、无效结构
- 性质注册表、单位定义、范围检查
- 模型 manifest 的 schema、哈希校验、属性匹配
- 2D 描述符和指纹的确定性
- 3D 构象成功、失败和 fallback
- 模型路由、多性质矩阵对齐
- 部分失败不影响其他性质
- 适用域、保形区间和指标计算
- CSV/JSON/Parquet 输出

### 15.2 集成测试

- `ompa doctor --strict`
- `ompa properties list`
- 一分子多性质预测
- 多分子多性质预测与矩阵对齐
- 一个无效 SMILES + 一个有效 SMILES 的部分成功流程
- 模型缺失时写入 property error 而非全局崩溃
- 3D 模型在未安装 xTB 时正确 fallback 或结构化失败
- benchmark 与 calibration 输出指标报告

### 15.3 V0.1 冻结条件

- 所有推理均可在本地完成，无私有 API 或 Token 依赖
- 每项预测具备单位、模型版本、模型哈希、适用域和不确定性
- 多性质、多分子结果顺序稳定且可追溯
- 模型训练数据来源和许可证可核验
- 固定基准集上的评估指标和校准覆盖率已落盘

---

## 16. 里程碑

### M1：CLI、注册表和输入输出（2–3 天）

- `ompa init`、`ompa doctor`、`ompa properties list`
- SMILES 输入、标准化、JSON/CSV 输出
- 性质与模型 manifest schema

### M2：2D QSPR 基线（4–7 天）

- 描述符、Morgan 指纹
- sklearn 模型加载与多性质路由
- 宽表/长表输出、部分失败隔离

### M3：适用域与校准（3–5 天）

- 相似度或距离型适用域
- 保形预测或集成方差
- benchmark、scaffold split、校准报告

### M4：3D 构象与 GNN 插件（5–10 天）

- ETKDG/MMFF/xTB 可选路线
- 3D 特征缓存
- 本地 Torch 模型插件

### M5：报告与工程化（3–5 天）

- Markdown 报告
- 参数/模型/输入哈希运行清单
- 测试、错误码、性能日志

---

## 17. 合规边界

OpenMPA 仅可使用本地开源或用户有权使用的模型、数据和工具。不得调用、复制、逆向、提取或分发原 MPA 服务的私有 API、JWT、GPU 服务配置、模型权重、训练数据、实现细节或品牌标识。所有性质预测均为模型估计，必须与实验测量及适用域结论区分。