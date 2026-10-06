"""材料录入契约校验：数值范围白名单、检测方法/单位/特性归一化（从 api.py 抽出，T12 模块化）。"""
from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# T-016：常见材料属性数值范围白名单（超出范围拒绝入库，由调用方转为 400）。
# key 为 property 裸名（_PROPERTY_ALIASES 的 key 或 prop.* 去前缀），
# value 为 (下限, 上限, 单位标签)；不在白名单中的属性仅做 NaN/Inf 校验。
_PROPERTY_VALUE_RANGES: dict[str, tuple[float, float, str]] = {
    "ionic_conductivity": (0.0, 1.0, "S/cm"),
    "electronic_conductivity": (0.0, 1e6, "S/cm"),
    "band_gap": (0.0, 20.0, "eV"),
    "formation_energy": (-100.0, 100.0, "eV/atom"),
    "electrochemical_window": (0.0, 10.0, "V"),
    "capacity_retention": (0.0, 100.0, "%"),
    "youngs_modulus": (0.0, 1000.0, "GPa"),
    "shear_modulus": (0.0, 500.0, "GPa"),
    # v4.1 改性塑料：高分子属性合理范围
    "tensile_strength": (0.0, 2000.0, "MPa"),
    "tensile_modulus": (0.0, 50000.0, "MPa"),
    "flexural_modulus": (0.0, 50000.0, "MPa"),
    "flexural_strength": (0.0, 2000.0, "MPa"),
    "impact_strength": (0.0, 500.0, "kJ/m2"),
    "heat_deflection_temp": (0.0, 500.0, "°C"),
    "melt_flow_index": (0.0, 500.0, "g/10min"),
    "elongation_at_break": (0.0, 1500.0, "%"),
    "melting_point": (0.0, 600.0, "°C"),
    "thermal_stability": (0.0, 900.0, "°C"),
    "weight_loss": (0.0, 100.0, "%"),
    "residual_mass": (0.0, 100.0, "%"),
}

# test_conditions 中温度字段的合法范围（°C），与前端 ExperimentDataForm.vue 软警告一致
_TEST_CONDITION_TEMPERATURE_RANGE: tuple[float, float, str] = (-50.0, 500.0, "°C")


def _validate_value_range(property_name: str, value: float, test_conditions: dict | None = None) -> None:
    """按属性名校验数值范围，超出白名单范围时抛出 ValueError（由调用方转为 400）。

    - property_name 为规范化后的 prop.* 形式或裸名，统一去前缀匹配白名单
    - 不在白名单中的属性不做范围限制（仅 NaN/Inf 由 _validate_value 拦截）
    - test_conditions.temperature 若存在且为数值，校验温度范围
    """
    bare = (property_name or "").strip()
    if bare.startswith("prop."):
        bare = bare[len("prop."):]
    if bare and bare in _PROPERTY_VALUE_RANGES:
        lo, hi, unit_label = _PROPERTY_VALUE_RANGES[bare]
        if value < lo or value > hi:
            raise ValueError(
                f"{bare} 数值 {value} 超出合法范围 [{lo}, {hi}] {unit_label}"
            )
    # 温度属于测试条件而非主值，单独校验
    if test_conditions:
        temp = test_conditions.get("temperature")
        # 排除 bool（bool 是 int 子类）与非数值类型
        if isinstance(temp, (int, float)) and not isinstance(temp, bool):
            lo, hi, unit_label = _TEST_CONDITION_TEMPERATURE_RANGE
            if temp < lo or temp > hi:
                raise ValueError(
                    f"test_conditions.temperature 数值 {temp} 超出合法范围 [{lo}, {hi}] {unit_label}"
                )


# 检测方法别名规范化：属性模板选项为 GB/T 1040 等标准名，而 mdm.test_methods 主键为 method.* 格式。
# test_method 列有 FK → mdm.test_methods.method_id，写入前统一映射；
# 未知值拒绝（400），既不静默置空丢数据，也不放任 FK 500。
_TEST_METHOD_ALIASES = {
    "EIS": "method.eis",
    "CV": "method.cv",
    "XRD": "method.xrd",
    "SEM": "method.sem",
    "DSC": "method.dsc",
    "TGA": "method.tga",
    "DC": "method.dc",
    "GA": "method.ga",
    "恒电流滴定": "method.gitt",
    # v4.1 改性塑料：标准检测方法（GB/T / ISO / ASTM）
    "GB/T 1040": "method.gbt_1040",
    "ISO 527": "method.iso_527",
    "ASTM D638": "method.astm_d638",
    "GB/T 1843": "method.gbt_1843",
    "ISO 180": "method.iso_180",
    "ASTM D256": "method.astm_d256",
    "GB/T 9341": "method.gbt_9341",
    "ISO 178": "method.iso_178",
    "ASTM D790": "method.astm_d790",
    "GB/T 1634": "method.gbt_1634",
    "ISO 75": "method.iso_75",
    "ASTM D648": "method.astm_d648",
    "GB/T 3682": "method.gbt_3682",
    "ISO 1133": "method.iso_1133",
    "ASTM D1238": "method.astm_d1238",
    "GB/T 2408": "method.gbt_2408",
    "UL94": "method.ul94",
    "ISO 1210": "method.iso_1210",
    "GB/T 1033": "method.gbt_1033",
    "ISO 1183": "method.iso_1183",
    "ASTM D792": "method.astm_d792",
    "GB/T 19466": "method.gbt_19466",
    "ISO 11357": "method.iso_11357",
    "GB/T 33047": "method.gbt_33047",
    "ISO 11358": "method.iso_11358",
}


def _normalize_test_method(raw: str) -> str:
    """规范化 test_method 为 mdm.test_methods 的合法 method_id。

    - 空串原样返回（存储层转 NULL）
    - 已是 method.* 形式的原样返回（合法性由 FK 兜底）
    - 命中别名表的映射为 method_id
    - 其余值拒绝（400），明确告知可选值
    """
    v = (raw or "").strip()
    if not v or v.startswith("method."):
        return v
    mapped = _TEST_METHOD_ALIASES.get(v) or _TEST_METHOD_ALIASES.get(v.upper())
    if mapped:
        return mapped
    raise HTTPException(
        status_code=400,
        detail=f"未知检测方法「{raw}」。可选值：{', '.join(sorted(_TEST_METHOD_ALIASES))}，或 mdm.test_methods 中的 method_id",
    )


# 特性别名：数据录入模板主字段 key（裸值）→ mdm.properties.property_id。
# 与 test_method 同类：property_name 列有 FK → mdm.properties.property_id。
from .properties import _PROPERTY_ALIASES, normalize_property_name as _properties_normalize

_PROPERTY_ALIASES_COMPAT = _PROPERTY_ALIASES


def _normalize_property_name(raw: str) -> str:
    return _properties_normalize(raw)


# 单位别名：模板/常用写法 → mdm.units.unit_code（°C → C，m²/g → m2/g 等）
_UNIT_ALIASES = {
    "°C": "C",
    "℃": "C",
    "m²/g": "m2/g",
    "μm": "um",
    "g/cm³": "g/cm3",
    "kJ/m²": "kJ/m2",
}

# mdm.units 存在性缓存（模块级，启动后加载；避免每次录入都开同步连接查库）
_unit_code_cache: set[str] | None = None


def _load_unit_cache() -> set[str]:
    global _unit_code_cache
    if _unit_code_cache is not None:
        return _unit_code_cache
    try:
        # 经 MDM 权威访问器读取（禁止穿透 experiment_controller._store.engine 私有成员）
        from .mdm.reference_dict import ReferenceDictStore
        _unit_code_cache = {u.unit_code for u in ReferenceDictStore().list_units()}
    except Exception as e:
        logger.warning("加载单位缓存失败（回退按次查询）: %s", e)
        _unit_code_cache = set()
    return _unit_code_cache


def _normalize_unit(raw: str) -> str:
    """规范化 unit 为 mdm.units 的合法 unit_code。未知单位 400（不放任 FK 500）。"""
    v = (raw or "").strip()
    if not v:
        return v
    v = _UNIT_ALIASES.get(v, v)
    from .mdm.reference_dict import ReferenceDictStore
    _mdm = ReferenceDictStore()
    cache = _load_unit_cache()
    if cache:
        # 缓存命中失败也放行缓存未覆盖（新播种单位未刷新时按次查询兜底）
        if v in cache:
            return v
        try:
            if _mdm.get_unit(v) is not None:
                _unit_code_cache.add(v)
                return v
        except Exception as e:
            logger.warning("单位存在性校验失败 unit=%s: %s", v, e)
            return v
        raise HTTPException(
            status_code=400,
            detail=f"未知单位「{raw}」。请使用 mdm.units 中登记的 unit_code（如 S/cm、V、mAh/g、C、%）",
        )
    # 缓存未就绪（启动早期）：按次查询（旧路径）
    try:
        if _mdm.get_unit(v) is not None:
            return v
    except Exception as e:
        # 单位表查询失败时不阻断录入，交由 FK 兜底
        logger.warning("单位存在性校验失败 unit=%s: %s", v, e)
        return v
    raise HTTPException(
        status_code=400,
        detail=f"未知单位「{raw}」。请使用 mdm.units 中登记的 unit_code（如 S/cm、V、mAh/g、C、%）",
    )
