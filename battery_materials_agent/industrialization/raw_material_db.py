"""Enterprise raw material database - PostgreSQL-backed material master data with RDKit similarity search."""

from __future__ import annotations
from pydantic import BaseModel, Field
import json
import logging

from sqlalchemy import text

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore

logger = logging.getLogger(__name__)


class MaterialSpec(BaseModel):
    material_id: str = ""
    name: str = ""
    smiles: str = ""
    category: str = ""
    inventory_quantity: float = 0.0  # 库存数量（单位见 inventory_unit）
    inventory_unit: str = "kg"      # 库存单位（从 MDM material_categories.default_unit 获取）
    unit_cost: float = 0.0          # 单位成本（货币+单位由 inventory_unit 决定）
    supplier: str = ""
    reach_compliant: bool = False
    is_toxic: bool = False
    batch_number: str = ""          # 批次号
    expiry_date: str = ""           # 有效期
    coa_uri: str = ""               # COA 检测报告链接
    # Task 13：合规证据字段 —— REACH/SDS/毒性合规声明必须有凭证支撑
    sds_uri: str = ""               # SDS 安全数据表链接
    test_report_uri: str = ""       # 第三方检测报告链接
    test_institution: str = ""      # 检测机构
    test_date: str = ""             # 检测日期（YYYY-MM-DD）
    min_order_quantity: float = 0.0  # 最小起订量（单位同 inventory_unit）
    # 版本追溯字段（G2.1）
    version: int = 1
    updated_by: str = ""
    update_reason: str = ""
    # 数据来源标注（G2.4）：measured 实测值 / predicted 预测值
    data_source: str = "measured"
    prediction_meta: dict = Field(default_factory=dict)  # {model, confidence, predicted_property, ...}
    # 按属性字典模板录入的物料属性值：{field_key: value}
    properties: dict = Field(default_factory=dict)


class RawMaterialDB:
    """Enterprise raw material master data backed by PostgreSQL."""

    def __init__(self, db_path: str = "data/raw_materials.db"):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()

    def _validate_category(self, category: str) -> None:
        """校验物料分类是否在 MDM classifications 中存在。空值允许。"""
        if not category:
            return
        if self._mdm.get_classification(category) is None:
            raise ValueError(
                f"物料分类 '{category}' 不存在于主数据分类表中，请先在 MDM 中创建"
            )

    def _row_to_spec(self, row) -> MaterialSpec:
        # Task 13：sds_uri/test_report_uri/test_institution/test_date 为新增列，
        # 通过 _get_col 安全取值，兼容迁移前的旧行与列顺序差异。
        # 0727：inventory_unit 为新增列，通过 _get_col 安全取值。
        # 0727b：inventory_kg → inventory_quantity, cost_per_kg → unit_cost（迁移 0023）
        return MaterialSpec(
            material_id=row[0],
            name=row[1],
            smiles=row[2] or "",
            category=row[3] or "",
            inventory_quantity=row[4] or 0.0,
            unit_cost=row[5] or 0.0,
            supplier=row[6] or "",
            reach_compliant=bool(row[7]),
            is_toxic=bool(row[8]),
            batch_number=(row[9] or "") if len(row) > 9 else "",
            expiry_date=(row[10] or "") if len(row) > 10 else "",
            coa_uri=(row[11] or "") if len(row) > 11 else "",
            min_order_quantity=(row[12] or 0.0) if len(row) > 12 else 0.0,
            version=(row[13] or 1) if len(row) > 13 else 1,
            updated_by=(row[14] or "") if len(row) > 14 else "",
            update_reason=(row[15] or "") if len(row) > 15 else "",
            data_source=(row[16] or "measured") if len(row) > 16 else "measured",
            prediction_meta=row[17] or {} if len(row) > 17 else {},
            sds_uri=(row[18] or "") if len(row) > 18 else "",
            test_report_uri=(row[19] or "") if len(row) > 19 else "",
            test_institution=(row[20] or "") if len(row) > 20 else "",
            test_date=(row[21] or "") if len(row) > 21 else "",
            properties=(row[22] or {}) if len(row) > 22 else {},
            inventory_unit=(row[23] or "kg") if len(row) > 23 else "kg",
        )

    def find_substitutes(self, target_smiles: str, threshold: float = 0.8) -> list[MaterialSpec]:
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem, DataStructs
        except ImportError:
            logger.warning("RDKit not available, cannot compute molecular similarity; returning empty list.")
            return []

        target_mol = Chem.MolFromSmiles(target_smiles)
        if target_mol is None:
            logger.warning("Invalid target SMILES: %s", target_smiles)
            return []

        target_fp = AllChem.GetMorganFingerprintAsBitVect(target_mol, radius=2, nBits=2048)

        candidates = self.get_all()
        results: list[MaterialSpec] = []
        for spec in candidates:
            if not spec.smiles:
                continue
            mol = Chem.MolFromSmiles(spec.smiles)
            if mol is None:
                logger.debug("Invalid SMILES for material %s: %s", spec.material_id, spec.smiles)
                continue
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
            similarity = DataStructs.TanimotoSimilarity(target_fp, fp)
            if similarity >= threshold:
                results.append(spec)
        return results

    def query_category(self, category: str) -> list[MaterialSpec]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM industrialization.raw_materials WHERE category = :category"),
                {"category": category},
            ).fetchall()
        return [self._row_to_spec(row) for row in rows]

    def get_spec(self, material_id: str) -> MaterialSpec | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM industrialization.raw_materials WHERE material_id = :material_id"),
                {"material_id": material_id},
            ).fetchone()
        return self._row_to_spec(row) if row else None

    # ---- Task 13：合规状态判定 ----

    @staticmethod
    def _has_evidence(spec: MaterialSpec) -> bool:
        """判断物料是否关联了合规证据（COA / SDS / 第三方检测报告任一即可）。"""
        return any([
            bool(spec.coa_uri and spec.coa_uri.strip()),
            bool(spec.sds_uri and spec.sds_uri.strip()),
            bool(spec.test_report_uri and spec.test_report_uri.strip()),
        ])

    def get_compliance_status(self, material_id: str) -> dict | None:
        """返回物料的结构化合规状态与关联证据。

        - compliant：声明合规且关联了检测报告凭证
        - pending_evidence：声明合规但缺失凭证（不可作为合规依据）
        - non_compliant：声明不合规

        返回 None 表示物料不存在。
        """
        spec = self.get_spec(material_id)
        if spec is None:
            return None
        return self.compute_compliance_status(spec)

    @classmethod
    def compute_compliance_status(cls, spec: MaterialSpec) -> dict:
        """根据 MaterialSpec 计算结构化合规状态（不查库，便于单元测试与批量调用）。"""
        if not spec.reach_compliant:
            status = "non_compliant"
        elif cls._has_evidence(spec):
            status = "compliant"
        else:
            # 声明合规但无任何检测报告凭证 → 待补充证据
            status = "pending_evidence"
        return {
            "status": status,
            "evidence": {
                "coa_uri": spec.coa_uri or None,
                "sds_uri": spec.sds_uri or None,
                "test_report_uri": spec.test_report_uri or None,
                "test_institution": spec.test_institution or None,
                "test_date": spec.test_date or None,
            },
        }

    def get_all(self) -> list[MaterialSpec]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM industrialization.raw_materials")
            ).fetchall()
        return [self._row_to_spec(row) for row in rows]

    def upsert_spec(self, spec: MaterialSpec) -> None:
        """插入或更新物料规格（含版本追溯与来源标注字段）。"""
        self._validate_category(spec.category)
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO industrialization.raw_materials
                (material_id, name, smiles, category, inventory_quantity, unit_cost,
                 supplier, reach_compliant, is_toxic,
                 batch_number, expiry_date, coa_uri, min_order_quantity,
                 version, updated_by, update_reason, data_source, prediction_meta,
                 sds_uri, test_report_uri, test_institution, test_date, properties, inventory_unit)
                VALUES (:material_id, :name, :smiles, :category, :inventory_quantity, :unit_cost,
                        :supplier, :reach_compliant, :is_toxic,
                        :batch_number, :expiry_date, :coa_uri, :min_order_quantity,
                        :version, :updated_by, :update_reason, :data_source,
                        CAST(:prediction_meta AS JSONB),
                        :sds_uri, :test_report_uri, :test_institution, :test_date,
                        CAST(:properties AS JSONB), :inventory_unit)
                ON CONFLICT (material_id) DO UPDATE SET
                    name=EXCLUDED.name,
                    smiles=EXCLUDED.smiles,
                    category=EXCLUDED.category,
                    inventory_quantity=EXCLUDED.inventory_quantity,
                    unit_cost=EXCLUDED.unit_cost,
                    supplier=EXCLUDED.supplier,
                    reach_compliant=EXCLUDED.reach_compliant,
                    is_toxic=EXCLUDED.is_toxic,
                    batch_number=EXCLUDED.batch_number,
                    expiry_date=EXCLUDED.expiry_date,
                    coa_uri=EXCLUDED.coa_uri,
                    min_order_quantity=EXCLUDED.min_order_quantity,
                    version=EXCLUDED.version,
                    updated_by=EXCLUDED.updated_by,
                    update_reason=EXCLUDED.update_reason,
                    data_source=EXCLUDED.data_source,
                    prediction_meta=EXCLUDED.prediction_meta,
                    sds_uri=EXCLUDED.sds_uri,
                    test_report_uri=EXCLUDED.test_report_uri,
                    test_institution=EXCLUDED.test_institution,
                    test_date=EXCLUDED.test_date,
                    properties=EXCLUDED.properties,
                    inventory_unit=EXCLUDED.inventory_unit"""),
                {
                    "material_id": spec.material_id,
                    "name": spec.name,
                    "smiles": spec.smiles,
                    "category": spec.category or None,
                    "inventory_quantity": spec.inventory_quantity,
                    "unit_cost": spec.unit_cost,
                    "supplier": spec.supplier,
                    "reach_compliant": spec.reach_compliant,
                    "is_toxic": spec.is_toxic,
                    "batch_number": spec.batch_number,
                    "expiry_date": spec.expiry_date,
                    "coa_uri": spec.coa_uri,
                    "min_order_quantity": spec.min_order_quantity,
                    "version": spec.version,
                    "updated_by": spec.updated_by,
                    "update_reason": spec.update_reason,
                    "data_source": spec.data_source,
                    "prediction_meta": json.dumps(spec.prediction_meta, ensure_ascii=False),
                    "sds_uri": spec.sds_uri,
                    "test_report_uri": spec.test_report_uri,
                    "test_institution": spec.test_institution,
                    "test_date": spec.test_date,
                    "properties": json.dumps(spec.properties, ensure_ascii=False),
                    "inventory_unit": spec.inventory_unit or "kg",
                },
            )

    def delete(self, material_id: str) -> bool:
        """硬删除物料记录（调用方须先做引用检查）。返回是否删除成功。"""
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM industrialization.raw_materials WHERE material_id = :material_id"),
                {"material_id": material_id},
            )
        return result.rowcount > 0

    # ---- 候选材料 ↔ 物料库联动 ----

    @staticmethod
    def _parse_formula_elements(formula: str) -> list[str]:
        """从化学式中提取元素符号列表（如 LiCoO2 → ['Li','Co','O']）。"""
        if not formula:
            return []
        try:
            from pymatgen.core import Composition
            comp = Composition(formula)
            return [str(e) for e in comp.elements]
        except Exception:
            # 退化为正则匹配
            import re
            matches = re.findall(r"[A-Z][a-z]?", formula)
            return list(dict.fromkeys(matches))

    def find_raw_materials_for_candidate(
        self, formula: str = "", smiles: str = "", similarity_threshold: float = 0.3,
    ) -> list[MaterialSpec]:
        """从候选材料反查物料库中可用原料。

        - 晶体（有 formula）：按元素匹配，返回含相同元素的物料（如 Li 元素 → 锂盐）。
        - 聚合物（有 smiles）：用 RDKit Morgan 相似度匹配物料库中相似物料。
        - 二者皆有时取并集。
        """
        matched: list[MaterialSpec] = []
        seen_ids: set[str] = set()
        all_materials = self.get_all()

        # 元素匹配（晶体）
        if formula:
            elements = self._parse_formula_elements(formula)
            if elements:
                for spec in all_materials:
                    if spec.material_id in seen_ids:
                        continue
                    # 物料 SMILES 或名称中含某元素符号
                    haystack = f"{spec.name} {spec.smiles} {spec.material_id}"
                    if any(e in haystack for e in elements):
                        matched.append(spec)
                        seen_ids.add(spec.material_id)

        # SMILES 相似度匹配（聚合物）
        if smiles:
            try:
                from rdkit import Chem
                from rdkit.Chem import AllChem, DataStructs
                target_mol = Chem.MolFromSmiles(smiles)
                if target_mol is not None:
                    target_fp = AllChem.GetMorganFingerprintAsBitVect(target_mol, radius=2, nBits=2048)
                    for spec in all_materials:
                        if spec.material_id in seen_ids or not spec.smiles:
                            continue
                        mol = Chem.MolFromSmiles(spec.smiles)
                        if mol is None:
                            continue
                        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
                        sim = DataStructs.TanimotoSimilarity(target_fp, fp)
                        if sim >= similarity_threshold:
                            matched.append(spec)
                            seen_ids.add(spec.material_id)
            except ImportError:
                logger.warning("RDKit not available, skipping similarity matching for SMILES.")

        return matched

    def estimate_cost(self, material_ids: list[str], quantity: float = 1.0) -> dict:
        """估算指定物料的采购成本。

        返回：
        - total_cost: 总成本（按单价 × 数量累加，假设每个物料各采购 quantity）
        - in_stock_value: 库存物料的成本（已入库可直接领用）
        - shortage: 缺口总量（库存不足部分，单位同 inventory_unit）
        - items: [{material_id, name, unit_price, quantity, cost, in_stock, inventory, unit}]
        """
        items = []
        total = 0.0
        in_stock_value = 0.0
        shortage = 0.0
        unit = "kg"
        for mid in material_ids:
            spec = self.get_spec(mid)
            if spec is None:
                items.append({
                    "material_id": mid, "name": mid, "unit_price": 0.0,
                    "quantity": quantity, "cost": 0.0,
                    "in_stock": False, "inventory": 0.0, "missing": True,
                    "unit": "kg",
                })
                continue
            unit = spec.inventory_unit or "kg"
            cost = spec.unit_cost * quantity
            total += cost
            in_stock = spec.inventory_quantity >= quantity
            if in_stock:
                in_stock_value += cost
            else:
                shortage += (quantity - spec.inventory_quantity)
            items.append({
                "material_id": spec.material_id, "name": spec.name,
                "unit_price": spec.unit_cost, "quantity": quantity,
                "cost": cost, "in_stock": in_stock, "inventory": spec.inventory_quantity,
                "supplier": spec.supplier, "missing": False,
                "unit": unit,
            })
        return {
            "total_cost": total,
            "in_stock_value": in_stock_value,
            "shortage": shortage,
            "unit": unit,
            "items": items,
        }

    def deduct_inventory(self, material_id: str, amount: float) -> bool:
        """原子扣减指定物料的库存，不足则返回 False。

        使用单条 UPDATE ... WHERE inventory_quantity >= :amount 保证读-改-写的原子性，
        避免并发场景下 get_spec 与 upsert_spec 之间的竞态导致超扣。
        """
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("UPDATE industrialization.raw_materials SET inventory_quantity = inventory_quantity - :amount "
                     "WHERE material_id = :material_id AND inventory_quantity >= :amount"),
                {"amount": amount, "material_id": material_id},
            )
        return cur.rowcount > 0

    # ---- 物料类型属性模板 ----

    def list_material_type_templates(self) -> list[dict]:
        """列出所有物料类型属性模板。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT material_type, field_keys, created_at, updated_at
                    FROM industrialization.material_type_templates
                    ORDER BY material_type
                """)
            ).fetchall()
        return [
            {
                "material_type": row[0],
                "field_keys": row[1] or [],
                "created_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def get_material_type_template(self, material_type: str) -> list[str]:
        """获取指定物料类型关联的属性字段 key 列表。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT field_keys
                    FROM industrialization.material_type_templates
                    WHERE material_type = :material_type
                """),
                {"material_type": material_type},
            ).fetchone()
        return row[0] if row and row[0] else []

    def set_material_type_template(self, material_type: str, field_keys: list[str]) -> None:
        """设置物料类型关联的属性字段 key 列表。"""
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO industrialization.material_type_templates
                    (material_type, field_keys, created_at, updated_at)
                    VALUES (:material_type, CAST(:field_keys AS JSONB), NOW(), NOW())
                    ON CONFLICT (material_type) DO UPDATE SET
                        field_keys = EXCLUDED.field_keys,
                        updated_at = NOW()
                """),
                {
                    "material_type": material_type,
                    "field_keys": json.dumps(list(field_keys), ensure_ascii=False),
                },
            )
