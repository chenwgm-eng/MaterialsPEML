"""材料属性字段定义 - 基于化合物数据 API 标准 + 电池材料扩展。

参照摩熵数科开放平台化合物数据 API 的 4 大类数据集：
1. 化合物标识信息
2. 物化及计算性质
3. 化合物安全信息
4. 化合物分类
并扩展电池材料专属属性 + 用户自定义属性。
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any


# 属性优化方向字典：maximize = 越大越好，minimize = 越小越好。
# 作为系统级单一可信源，所有模块（ECML 引擎、候选生成器、性质预测器）应统一引用。
PROPERTY_DIRECTION: dict[str, str] = {
    "ionic_conductivity": "maximize",
    "electronic_conductivity": "maximize",
    "band_gap": "maximize",
    "formation_energy": "minimize",
    "electrochemical_window": "maximize",
    "theoretical_capacity": "maximize",
    "operating_voltage": "maximize",
    "cycle_stability": "maximize",
    "capacity_retention": "maximize",
    "total_energy": "minimize",
    "energy_above_hull": "minimize",
    "stability": "maximize",
    "molecular_weight": "minimize",
}


def get_property_direction(key: str) -> str:
    """获取属性优化方向，未定义的属性默认 maximize。"""
    return PROPERTY_DIRECTION.get(key, "maximize")


class PropertyField(BaseModel):
    """单个属性字段定义。"""
    key: str  # 英文键名，如 ionic_conductivity
    label_cn: str  # 中文标签，如 离子电导率
    label_en: str = ""  # 英文标签
    category: str  # 所属分类
    unit: str = ""  # 单位，如 S/cm
    value_type: str = "float"  # float | int | str | list | dict
    description: str = ""  # 字段说明
    is_custom: bool = False  # 是否用户自定义
    is_array: bool = False  # 是否数组类型（如 CAS 可能有多个）


class PropertyCategory(BaseModel):
    """属性分类。"""
    key: str  # 分类键名
    label_cn: str  # 中文标签
    label_en: str = ""  # 英文标签
    icon: str = ""  # 图标名
    description: str = ""  # 分类说明
    fields: list[PropertyField] = Field(default_factory=list)


# ========================================================================
# 内置属性字段定义（基于微信文章 4 大类 + 电池扩展）
# ========================================================================

BUILTIN_CATEGORIES: list[PropertyCategory] = [
    # 1. 化合物标识信息（参照标识数据集 API）
    PropertyCategory(
        key="identification",
        label_cn="化合物标识",
        label_en="Identification",
        icon="TagOutlined",
        description="化合物唯一标识与基础信息，参照化合物标识数据集",
        fields=[
            PropertyField(key="data_id", label_cn="数据ID", label_en="Data ID", category="identification", value_type="str", description="化合物在数据库中的唯一标识"),
            PropertyField(key="name_cn", label_cn="中文名称", label_en="Chinese Name", category="identification", value_type="str", is_array=True, description="化合物的中文名称列表"),
            PropertyField(key="name_en", label_cn="英文名称", label_en="English Name", category="identification", value_type="str", is_array=True, description="化合物的英文名称列表"),
            PropertyField(key="formula", label_cn="化学式", label_en="Formula", category="identification", value_type="str", description="化学式，如 C10H14N2O"),
            PropertyField(key="molecular_weight", label_cn="分子量", label_en="Molecular Weight", category="identification", value_type="float", unit="g/mol", description="相对分子质量"),
            PropertyField(key="cas_number", label_cn="CAS号", label_en="CAS Number", category="identification", value_type="str", is_array=True, description="CAS Registry Number"),
            PropertyField(key="inchi", label_cn="InChI", label_en="InChI", category="identification", value_type="str", description="International Chemical Identifier"),
            PropertyField(key="inchikey", label_cn="InChIKey", label_en="InChIKey", category="identification", value_type="str", description="InChI 的哈希键"),
            PropertyField(key="smiles", label_cn="SMILES", label_en="SMILES", category="identification", value_type="str", description="简化分子线性输入规范"),
            PropertyField(key="mol_file", label_cn="MOL文件", label_en="MOL File", category="identification", value_type="str", description="MOL 格式结构数据"),
            PropertyField(key="mdl_number", label_cn="MDL编号", label_en="MDL Number", category="identification", value_type="str", is_array=True, description="MDL 数据库编号"),
            PropertyField(key="einecs", label_cn="EINECS号", label_en="EINECS", category="identification", value_type="str", is_array=True, description="欧洲现有商业化学品目录编号"),
            PropertyField(key="beilstein", label_cn="Beilstein编号", label_en="Beilstein", category="identification", value_type="str", is_array=True, description="Beilstein 数据库编号"),
        ],
    ),
    # 2. 物化及计算性质（参照物化性质数据集 API）
    PropertyCategory(
        key="physicochemical",
        label_cn="物化性质",
        label_en="Physicochemical",
        icon="ExperimentOutlined",
        description="实测与预计算的物理化学性质参数",
        fields=[
            PropertyField(key="boiling_point", label_cn="沸点", label_en="Boiling Point", category="physicochemical", value_type="float", unit="C", description="常压沸点"),
            PropertyField(key="melting_point", label_cn="熔点", label_en="Melting Point", category="physicochemical", value_type="float", unit="C", description="常压熔点"),
            PropertyField(key="density", label_cn="密度", label_en="Density", category="physicochemical", value_type="float", unit="g/cm³", description="物质密度"),
            PropertyField(key="heat_of_combustion", label_cn="燃烧热", label_en="Heat of Combustion", category="physicochemical", value_type="float", unit="kJ/mol", description="标准燃烧热"),
            PropertyField(key="logp", label_cn="辛醇/水分配系数", label_en="LogP", category="physicochemical", value_type="float", description="辛醇-水分配系数的对数值"),
            PropertyField(key="num_heavy_atoms", label_cn="重原子数", label_en="Heavy Atom Count", category="physicochemical", value_type="int", description="非氢原子数量"),
            PropertyField(key="num_rotatable_bonds", label_cn="可旋转键数", label_en="Rotatable Bonds", category="physicochemical", value_type="int", description="可旋转化学键数量"),
            PropertyField(key="num_rings", label_cn="环数", label_en="Ring Count", category="physicochemical", value_type="int", description="环的总数"),
            PropertyField(key="fraction_csp3", label_cn="sp3杂化碳比例", label_en="Fraction CSP3", category="physicochemical", value_type="float", description="sp3 杂化碳原子占比"),
            PropertyField(key="tpsa", label_cn="拓扑极性表面积", label_en="TPSA", category="physicochemical", value_type="float", unit="Å²", description="拓扑极性表面积"),
            PropertyField(key="num_hbd", label_cn="氢键给体数", label_en="H-Bond Donors", category="physicochemical", value_type="int", description="氢键给体数量"),
            PropertyField(key="num_hba", label_cn="氢键受体数", label_en="H-Bond Acceptors", category="physicochemical", value_type="int", description="氢键受体数量"),
            PropertyField(key="solubility", label_cn="溶解度", label_en="Solubility", category="physicochemical", value_type="float", unit="g/L", description="水中溶解度"),
            PropertyField(key="vapor_pressure", label_cn="蒸气压", label_en="Vapor Pressure", category="physicochemical", value_type="float", unit="Pa", description="饱和蒸气压"),
            PropertyField(key="refractive_index", label_cn="折射率", label_en="Refractive Index", category="physicochemical", value_type="float", description="折射率"),
            PropertyField(key="flash_point", label_cn="闪点", label_en="Flash Point", category="physicochemical", value_type="float", unit="C", description="闪点温度"),
        ],
    ),
    # 3. 化合物安全信息（参照安全信息数据集 API）
    PropertyCategory(
        key="safety",
        label_cn="安全信息",
        label_en="Safety",
        icon="WarningOutlined",
        description="化学品安全与合规信息",
        fields=[
            PropertyField(key="hazard_symbols", label_cn="危险品标志", label_en="Hazard Symbols", category="safety", value_type="str", is_array=True, description="如 F, Xn, T 等"),
            PropertyField(key="safety_phrases", label_cn="安全说明", label_en="Safety Phrases (S-codes)", category="safety", value_type="str", is_array=True, description="S 码安全说明"),
            PropertyField(key="risk_phrases", label_cn="危险类别码", label_en="Risk Phrases (R-codes)", category="safety", value_type="str", is_array=True, description="R 码危险类别"),
            PropertyField(key="un_number", label_cn="危险品运输编号", label_en="UN Number", category="safety", value_type="str", is_array=True, description="联合国危险品运输编号"),
            PropertyField(key="ghs_hazard_statements", label_cn="GHS危险性说明", label_en="GHS Hazard Statements", category="safety", value_type="str", is_array=True, description="GHS H 码"),
            PropertyField(key="ghs_prevention_statements", label_cn="GHS防范说明", label_en="GHS Prevention Statements", category="safety", value_type="str", is_array=True, description="GHS P 码"),
            PropertyField(key="ghs_pictograms", label_cn="GHS危险性标志", label_en="GHS Pictograms", category="safety", value_type="str", is_array=True, description="如 GHS02, GHS07"),
            PropertyField(key="wgk_germany", label_cn="德国水危害等级", label_en="WGK Germany", category="safety", value_type="str", is_array=True, description="水危害分类等级"),
            PropertyField(key="rtecs_number", label_cn="RTECS号", label_en="RTECS Number", category="safety", value_type="str", is_array=True, description="毒理学数据编号"),
            PropertyField(key="customs_code", label_cn="海关编码", label_en="Customs Code", category="safety", value_type="str", is_array=True, description="中国海关编码"),
            PropertyField(key="packaging_group", label_cn="包装等级", label_en="Packaging Group", category="safety", value_type="str", is_array=True, description="如 I, II, III"),
            PropertyField(key="hazard_class", label_cn="危险类别", label_en="Hazard Class", category="safety", value_type="str", is_array=True, description="运输危险类别"),
        ],
    ),
    # 4. 化合物分类（参照分类数据集 API）
    PropertyCategory(
        key="classification",
        label_cn="化合物分类",
        label_en="Classification",
        icon="AppstoreOutlined",
        description="层级分类树信息",
        fields=[
            PropertyField(key="classification_en", label_cn="分类(英文)", label_en="Classification (EN)", category="classification", value_type="str", is_array=True, description="英文分类层级路径"),
            PropertyField(key="classification_cn", label_cn="分类(中文)", label_en="Classification (CN)", category="classification", value_type="str", is_array=True, description="中文分类层级路径"),
        ],
    ),
    # 5. 电池材料专属属性（扩展）
    PropertyCategory(
        key="battery",
        label_cn="电池材料属性",
        label_en="Battery Properties",
        icon="ThunderboltOutlined",
        description="电池材料关键性能参数",
        fields=[
            PropertyField(key="ionic_conductivity", label_cn="离子电导率", label_en="Ionic Conductivity", category="battery", value_type="float", unit="S/cm", description="离子传导能力，固态电解质核心指标"),
            PropertyField(key="electronic_conductivity", label_cn="电子电导率", label_en="Electronic Conductivity", category="battery", value_type="float", unit="S/cm", description="电子传导能力"),
            PropertyField(key="electrochemical_window", label_cn="电化学窗口", label_en="Electrochemical Window", category="battery", value_type="float", unit="V", description="电化学稳定电压范围"),
            PropertyField(key="transference_number", label_cn="锂离子迁移数", label_en="Transference Number", category="battery", value_type="float", description="锂离子电流占比，0-1"),
            PropertyField(key="theoretical_capacity", label_cn="理论容量", label_en="Theoretical Capacity", category="battery", value_type="float", unit="mAh/g", description="理论比容量"),
            PropertyField(key="operating_voltage", label_cn="工作电压", label_en="Operating Voltage", category="battery", value_type="float", unit="V", description="平均工作电压"),
            PropertyField(key="cycle_stability", label_cn="循环稳定性", label_en="Cycle Stability", category="battery", value_type="int", unit="cycles", description="可循环次数"),
            PropertyField(key="capacity_retention", label_cn="容量保持率", label_en="Capacity Retention", category="battery", value_type="float", unit="%", description="N 圈后容量保持百分比"),
            PropertyField(key="band_gap", label_cn="带隙", label_en="Band Gap", category="battery", value_type="float", unit="eV", description="电子带隙宽度"),
            PropertyField(key="formation_energy", label_cn="形成能", label_en="Formation Energy", category="battery", value_type="float", unit="eV/atom", description="形成能"),
            PropertyField(key="lattice_parameters", label_cn="晶格参数", label_en="Lattice Parameters", category="battery", value_type="dict", description="a, b, c, α, β, γ"),
            PropertyField(key="crystal_system", label_cn="晶系", label_en="Crystal System", category="battery", value_type="str", description="如 cubic, tetragonal, orthorhombic"),
            PropertyField(key="space_group", label_cn="空间群", label_en="Space Group", category="battery", value_type="str", description="如 Fm-3m, Pnma"),
        ],
    ),
    # 6. 催化剂材料属性（催化领域扩展）
    PropertyCategory(
        key="catalysis",
        label_cn="催化材料属性",
        label_en="Catalysis Properties",
        icon="FireOutlined",
        description="催化剂材料核心性能参数",
        fields=[
            PropertyField(key="turnover_frequency", label_cn="周转频率", label_en="Turnover Frequency (TOF)", category="catalysis", value_type="float", unit="s⁻¹", description="单位活性位点单位时间转化底物的分子数"),
            PropertyField(key="selectivity", label_cn="选择性", label_en="Selectivity", category="catalysis", value_type="float", unit="%", description="目标产物占总产物的百分比"),
            PropertyField(key="conversion", label_cn="转化率", label_en="Conversion", category="catalysis", value_type="float", unit="%", description="反应物转化为产物的百分比"),
            PropertyField(key="activation_energy", label_cn="活化能", label_en="Activation Energy", category="catalysis", value_type="float", unit="kJ/mol", description="反应活化能"),
            PropertyField(key="surface_area", label_cn="表面积", label_en="Surface Area", category="catalysis", value_type="float", unit="m²/g", description="比表面积（BET）"),
            PropertyField(key="pore_volume", label_cn="孔体积", label_en="Pore Volume", category="catalysis", value_type="float", unit="cm³/g", description="总孔体积"),
            PropertyField(key="metal_dispersion", label_cn="金属分散度", label_en="Metal Dispersion", category="catalysis", value_type="float", unit="%", description="表面金属原子占总金属原子的百分比"),
        ],
    ),
    # 7. 高分子材料属性（高分子领域扩展）
    PropertyCategory(
        key="polymer",
        label_cn="高分子材料属性",
        label_en="Polymer Properties",
        icon="BranchesOutlined",
        description="高分子材料关键性能参数",
        fields=[
            PropertyField(key="glass_transition_temp", label_cn="玻璃化转变温度", label_en="Glass Transition Temperature", category="polymer", value_type="float", unit="C", description="玻璃态与高弹态转变温度 Tg"),
            PropertyField(key="molecular_weight", label_cn="分子量", label_en="Molecular Weight", category="polymer", value_type="float", unit="g/mol", description="相对分子质量"),
            PropertyField(key="crystallinity", label_cn="结晶度", label_en="Crystallinity", category="polymer", value_type="float", unit="%", description="结晶区占总质量的百分比"),
            PropertyField(key="tensile_strength", label_cn="拉伸强度", label_en="Tensile Strength", category="polymer", value_type="float", unit="MPa", description="拉伸断裂时的最大应力"),
            PropertyField(key="elongation_at_break", label_cn="断裂伸长率", label_en="Elongation at Break", category="polymer", value_type="float", unit="%", description="断裂时的伸长量占原长的百分比"),
        ],
    ),
]


class PropertyRegistry:
    """属性字段注册管理器，支持内置 + 自定义属性。"""

    def __init__(self):
        self._categories: dict[str, PropertyCategory] = {}
        for cat in BUILTIN_CATEGORIES:
            self._categories[cat.key] = cat
        # 自定义属性分类
        if "custom" not in self._categories:
            self._categories["custom"] = PropertyCategory(
                key="custom",
                label_cn="自定义属性",
                label_en="Custom Properties",
                icon="PlusOutlined",
                description="用户自定义添加的属性字段",
            )

    def list_categories(self) -> list[PropertyCategory]:
        return list(self._categories.values())

    def get_category(self, key: str) -> PropertyCategory | None:
        return self._categories.get(key)

    def list_all_fields(self) -> list[PropertyField]:
        fields = []
        for cat in self._categories.values():
            fields.extend(cat.fields)
        return fields

    def get_field(self, key: str) -> PropertyField | None:
        for cat in self._categories.values():
            for f in cat.fields:
                if f.key == key:
                    return f
        return None

    def add_custom_field(self, field: PropertyField) -> bool:
        """添加自定义属性字段到指定分类（默认 custom 分类）。

        支持将自定义字段加入任意已注册的分类（如 physicochemical、battery），
        以满足属性字典页按 Tab 维护自定义属性的需求。
        """
        if self.get_field(field.key) is not None:
            return False  # 键名已存在
        field.is_custom = True
        cat_key = field.category or "custom"
        if cat_key not in self._categories:
            cat_key = "custom"
        field.category = cat_key
        self._categories[cat_key].fields.append(field)
        return True

    def remove_custom_field(self, key: str) -> bool:
        """移除自定义字段（可在任意分类中）。"""
        for cat in self._categories.values():
            for i, f in enumerate(cat.fields):
                if f.key == key and f.is_custom:
                    cat.fields.pop(i)
                    return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """返回属性字段统计信息。"""
        stats = {"total_fields": 0, "total_categories": len(self._categories), "by_category": {}}
        for cat in self._categories.values():
            n = len(cat.fields)
            stats["by_category"][cat.key] = {
                "label_cn": cat.label_cn,
                "count": n,
            }
            stats["total_fields"] += n
        return stats

    # ------------------------------------------------------------------
    # 供其他模块（prediction / verification / ecml）按用途查询字段
    # ------------------------------------------------------------------

    # 标识字段：用于唯一标识一个化合物
    IDENTIFICATION_KEYS = ("formula", "smiles", "inchi", "inchikey", "cas_number", "name_cn", "name_en")

    # 可预测字段：battery 分类下的数值型字段 + 部分 physicochemical 数值字段
    PREDICTABLE_KEYS = (
        "ionic_conductivity", "electronic_conductivity", "electrochemical_window",
        "transference_number", "theoretical_capacity", "operating_voltage",
        "cycle_stability", "capacity_retention",
        "band_gap", "formation_energy",
        "boiling_point", "melting_point", "density", "logp", "tpsa",
        "solubility", "vapor_pressure", "refractive_index", "flash_point",
    )

    # 可作为 ECML 目标性质的字段
    ECML_TARGET_KEYS = (
        "ionic_conductivity", "band_gap", "formation_energy",
        "electrochemical_window", "theoretical_capacity", "operating_voltage",
        "cycle_stability", "capacity_retention",
    )

    # 可由实验测量的字段
    EXPERIMENTAL_KEYS = (
        "ionic_conductivity", "electronic_conductivity", "electrochemical_window",
        "transference_number", "theoretical_capacity", "operating_voltage",
        "cycle_stability", "capacity_retention",
        "boiling_point", "melting_point", "density", "solubility",
    )

    def list_field_keys(self, category: str | None = None) -> list[str]:
        """列出字段 key（可按分类过滤）。"""
        if category:
            cat = self._categories.get(category)
            return [f.key for f in cat.fields] if cat else []
        return [f.key for f in self.list_all_fields()]

    def get_predictable_keys(self) -> list[str]:
        """返回可用于预测的属性 key 列表（内置 + 自定义数值型）。"""
        keys = [k for k in self.PREDICTABLE_KEYS if self.get_field(k) is not None]
        # 扫描所有分类中的自定义数值型字段（自定义字段可分布于任意分类）
        for cat in self._categories.values():
            for f in cat.fields:
                if f.is_custom and f.value_type in ("float", "int") and f.key not in keys:
                    keys.append(f.key)
        return keys

    def get_ecml_target_keys(self) -> list[str]:
        """返回可作为 ECML 目标性质的属性 key。"""
        return [k for k in self.ECML_TARGET_KEYS if self.get_field(k) is not None]

    def get_experimental_keys(self) -> list[str]:
        """返回可由实验测量的属性 key。"""
        return [k for k in self.EXPERIMENTAL_KEYS if self.get_field(k) is not None]

    def to_select_options(self, keys: list[str] | None = None) -> list[dict]:
        """把字段 key 列表转为前端下拉选项格式。"""
        if keys is None:
            keys = self.get_predictable_keys()
        options = []
        for k in keys:
            f = self.get_field(k)
            if f:
                label = f.label_cn
                if f.unit:
                    label += f" ({f.unit})"
                options.append({"label": label, "value": f.key})
        return options

    def is_supported(self, key: str) -> bool:
        """字段是否在 registry 中存在。"""
        return self.get_field(key) is not None


# 全局单例
_registry = PropertyRegistry()


def get_registry() -> PropertyRegistry:
    return _registry
