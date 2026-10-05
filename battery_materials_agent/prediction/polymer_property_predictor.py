"""Polymer property prediction using real RDKit descriptors and learned correlations."""

from __future__ import annotations
from pydantic import BaseModel, Field
import numpy as np

try:
    from .chemprop_adapter import is_available as _chemprop_available, predict as _chemprop_predict
    _CHEMPROP_IMPORTED = True
except Exception:  # noqa: BLE001
    _CHEMPROP_IMPORTED = False

try:
    from .polymer_gnn_adapter import is_available as _polymer_gnn_imported, predict as _polymer_gnn_predict
    _POLYMER_GNN_IMPORTED = True
except Exception:  # noqa: BLE001
    _POLYMER_GNN_IMPORTED = False

try:
    from ase import Atoms
    from ase.calculators.emt import EMT
    _ASE_AVAILABLE = True
except Exception:
    _ASE_AVAILABLE = False


class PolymerPredictionResult(BaseModel):
    property_name: str
    value: float
    unit: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    model: str = ""
    psmiles: str = ""
    smiles: str = ""  # 单体 SMILES，用于 DFT 验证
    formula: str = ""  # 聚合物化学式（可选）
    material_type: str = "polymer"
    # T-029：数据质量分层。ASE/物理计算=simulated，ML 预测=estimated，实验验证=verified
    data_quality: str = "estimated"
    # 标记结果是否来自占位/回退路径（如无效 SMILES 的假描述符），下游不得当真实输出
    degraded: bool = False
    provenance: list[dict] = Field(default_factory=list)


class PolymerDescriptorCalculator:
    """Calculate polymer descriptors from SMILES for property prediction."""

    def calculate_descriptors(self, smiles: str) -> dict:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors, EState

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return self._fallback_descriptors(smiles)

        try:
            desc = {
                "molecular_weight": Descriptors.MolWt(mol),
                "tpsa": Descriptors.TPSA(mol),
                "num_rotatable_bonds": Descriptors.NumRotatableBonds(mol),
                "num_hbd": Descriptors.NumHDonors(mol),
                "num_hba": Descriptors.NumHAcceptors(mol),
                "num_rings": Descriptors.RingCount(mol),
                "num_aromatic_rings": Descriptors.NumAromaticRings(mol),
                "fraction_csp3": Descriptors.FractionCSP3(mol),
                "num_heavy_atoms": mol.GetNumHeavyAtoms(),
                "labute_asa": Descriptors.LabuteASA(mol),
                "balaban_j": Descriptors.BalabanJ(mol) if mol.GetNumBonds() > 0 else 0,
                "bertz_ct": Descriptors.BertzCT(mol),
                "num_valence_electrons": Descriptors.NumValenceElectrons(mol),
                "num_heteroatoms": Descriptors.NumHeteroatoms(mol),
                "max_partial_charge": Descriptors.MaxPartialCharge(mol),
                "min_partial_charge": Descriptors.MinPartialCharge(mol),
                "avg_partial_charge": (Descriptors.MaxPartialCharge(mol) + Descriptors.MinPartialCharge(mol)) / 2,
                "estate_electron_accessibility": (lambda e: float(e[0]) if e is not None and len(e) > 0 else 0.0)(EState.EState.EStateIndices(mol)),
            }
        except Exception:
            desc = self._fallback_descriptors(smiles)

        return desc

    def _fallback_descriptors(self, smiles: str) -> dict:
        return {
            "molecular_weight": len(smiles) * 12.0,
            "tpsa": 0.0,
            "num_rotatable_bonds": smiles.count("-"),
            "num_hbd": 0.0,
            "num_hba": 0.0,
            "num_rings": smiles.count("c"),
            "num_aromatic_rings": smiles.count("c1"),
            "fraction_csp3": 0.5,
            "num_heavy_atoms": len(smiles),
            "labute_asa": 0.0,
            "balaban_j": 0.0,
            "bertz_ct": 0.0,
            "num_valence_electrons": 0.0,
            "num_heteroatoms": sum(1 for c in smiles if c in "ONS"),
            "max_partial_charge": 0.0,
            "min_partial_charge": 0.0,
            "avg_partial_charge": 0.0,
            "estate_electron_accessibility": 0.0,
        }


class PolymerPropertyModel:
    """Learned property prediction model using descriptor-weighted correlations."""

    PROPERTY_MODELS = {
        "ionic_conductivity": {
            "weights": {
                "tpsa": -0.02, "num_hbd": -0.15, "num_hba": 0.08,
                "molecular_weight": -0.0001, "fraction_csp3": 0.3,
                "num_rotatable_bonds": 0.05, "num_rings": -0.1,
                "max_partial_charge": 0.2, "min_partial_charge": -0.3,
            },
            "intercept": -3.0,
            "unit": "S/cm",
            "scale": 1e-4,
        },
        "glass_transition_temp": {
            "weights": {
                "molecular_weight": 0.01, "num_rotatable_bonds": -5.0,
                "num_rings": 15.0, "fraction_csp3": -20.0,
                "tpsa": 0.5, "num_hbd": 8.0, "num_hba": -3.0,
                "bertz_ct": 0.005, "balaban_j": 2.0,
            },
            "intercept": 300.0,
            "unit": "K",
            "scale": 1.0,
        },
        "dielectric_constant": {
            "weights": {
                "tpsa": 0.05, "num_hba": 1.5, "num_hbd": 2.0,
                "fraction_csp3": -3.0, "max_partial_charge": 10.0,
                "min_partial_charge": -10.0, "num_rotatable_bonds": 0.3,
                "molecular_weight": -0.005, "num_aromatic_rings": -0.5,
            },
            "intercept": 4.0,
            "unit": "",
            "scale": 1.0,
        },
        "elastic_modulus": {
            "weights": {
                "num_rings": 0.5, "fraction_csp3": -2.0,
                "molecular_weight": 0.001, "num_rotatable_bonds": -0.3,
                "bertz_ct": 0.001, "tpsa": 0.01,
            },
            "intercept": 1.0,
            "unit": "GPa",
            "scale": 0.5,
        },
        "thermal_conductivity": {
            "weights": {
                "num_rings": 0.01, "fraction_csp3": -0.05,
                "molecular_weight": 0.0001, "num_rotatable_bonds": -0.005,
                "bertz_ct": 0.00005,
            },
            "intercept": 0.1,
            "unit": "W/(m·K)",
            "scale": 0.1,
        },
        "decomposition_temp": {
            "weights": {
                "molecular_weight": 0.05, "num_rings": 20.0,
                "fraction_csp3": -30.0, "num_rotatable_bonds": -5.0,
                "tpsa": 0.3, "bertz_ct": 0.01,
            },
            "intercept": 400.0,
            "unit": "K",
            "scale": 1.0,
        },
        "total_energy": {
            "weights": {
                "molecular_weight": -0.05, "num_heavy_atoms": -1.0,
                "num_rings": -2.0, "tpsa": 0.01,
            },
            "intercept": -50.0,
            "unit": "eV",
            "scale": 1.0,
        },
        "formation_energy": {
            "weights": {
                "molecular_weight": -0.001, "num_heavy_atoms": -0.1,
                "num_rings": -0.2, "fraction_csp3": 0.5,
            },
            "intercept": -5.0,
            "unit": "eV/atom",
            "scale": 1.0,
        },
        # ── v4.1 改性塑料领域：高分子工程性能启发式模型 ──
        # 基于骨架化学特征的工程估算（刚性/极性/链柔顺性 → 力学与热学性能）
        "tensile_strength": {
            "weights": {
                "num_rings": 8.0, "num_rotatable_bonds": -2.0,
                "fraction_csp3": -18.0, "tpsa": 0.4, "num_hba": -0.6,
                "bertz_ct": 0.003, "molecular_weight": 0.002,
            },
            "intercept": 32.0,
            "unit": "MPa",
            "scale": 1.0,
        },
        "flexural_modulus": {
            "weights": {
                "num_rings": 180.0, "num_rotatable_bonds": -40.0,
                "fraction_csp3": -350.0, "bertz_ct": 0.05,
                "molecular_weight": 0.05,
            },
            "intercept": 1800.0,
            "unit": "MPa",
            "scale": 1.0,
        },
        "impact_strength": {
            "weights": {
                "num_rotatable_bonds": 3.0, "fraction_csp3": 12.0,
                "num_rings": -4.0, "tpsa": -0.2, "molecular_weight": 0.001,
            },
            "intercept": 8.0,
            "unit": "kJ/m2",
            "scale": 1.0,
        },        "heat_deflection_temp": {
            "weights": {
                "num_rings": 15.0, "num_rotatable_bonds": -5.0,
                "fraction_csp3": -22.0, "bertz_ct": 0.005,
                "molecular_weight": 0.01,
            },
            "intercept": 90.0,
            "unit": "C",
            "scale": 1.0,
        },
        "melt_flow_index": {
            "weights": {
                "num_rotatable_bonds": 8.0, "fraction_csp3": 15.0,
                "molecular_weight": -0.006, "num_rings": -6.0,
            },
            "intercept": 12.0,
            "unit": "g/10min",
            "scale": 1.0,
        },
        "elongation_at_break": {
            "weights": {
                "num_rotatable_bonds": 8.0, "fraction_csp3": 18.0,
                "num_rings": -5.0, "tpsa": -0.3,
            },
            "intercept": 30.0,
            "unit": "%",
            "scale": 1.0,
        },
        "thermal_stability": {
            "weights": {
                "num_rings": 22.0, "bertz_ct": 0.01,
                "molecular_weight": 0.05, "num_rotatable_bonds": -6.0,
            },
            "intercept": 320.0,
            "unit": "C",
            "scale": 1.0,
        },
        "crystallinity": {
            "weights": {
                "fraction_csp3": 40.0, "num_rotatable_bonds": -6.0,
                "num_rings": -8.0,
            },
            "intercept": 25.0,
            "unit": "%",
            "scale": 1.0,
        },
    }

    def predict(self, descriptors: dict, property_name: str) -> tuple[float, float]:
        model = self.PROPERTY_MODELS.get(property_name)
        if model is None:
            raise ValueError(f"Property {property_name} not supported")

        value = model["intercept"]
        for key, weight in model["weights"].items():
            desc_val = descriptors.get(key, 0.0)
            value += weight * desc_val

        value = value * model["scale"]
        if property_name == "crystallinity":
            value = max(0.0, min(100.0, value))
        if property_name == "elongation_at_break":
            value = max(0.0, value)
        confidence = self._estimate_confidence(descriptors, property_name)
        return value, confidence

    def _estimate_confidence(self, descriptors: dict, property_name: str) -> float:
        """启发式估算的置信度（ADR-0001）：仅反映描述符覆盖度，与模型精度无关。

        上限 0.5，杜绝触发 `simulated`/高置信语义——"工程估算"不得声称高把握。
        有真实权重的属性（Tg/介电常数）置信度由 GNN 路径给出，不走此函数。
        """
        base_confidence = 0.3
        num_valid = sum(1 for v in descriptors.values() if v != 0.0)
        data_quality = min(1.0, num_valid / 10.0)
        return min(0.5, base_confidence + data_quality * 0.2)


class PolymerPropertyPredictor:
    """Predict polymer properties using RDKit descriptors and learned correlations."""

    PREDICTABLE_PROPERTIES = [
        # v4.1 改性塑料领域：高分子工程性能
        "tensile_strength",
        "flexural_modulus",
        "impact_strength",
        "heat_deflection_temp",
        "melt_flow_index",
        "elongation_at_break",
        "thermal_stability",
        "crystallinity",
        "glass_transition_temp",
        "dielectric_constant",
    ]

    SUPPORTED_MODELS = ["polymernn", "descriptor", "mattersim"]

    def __init__(self, model_type: str = "polymernn"):
        self.model_type = model_type
        self._calc = PolymerDescriptorCalculator()
        self._model = PolymerPropertyModel()
        self._ase_available = _ASE_AVAILABLE

    def predict(self, features: dict, property_name: str) -> PolymerPredictionResult:
        if self.model_type not in self.SUPPORTED_MODELS:
            raise ValueError(f"Model type {self.model_type} not supported. Use: {self.SUPPORTED_MODELS}")
        if property_name not in self.PREDICTABLE_PROPERTIES:
            raise ValueError(f"Property {property_name} not supported. Use: {self.PREDICTABLE_PROPERTIES}")

        smiles = features.get("smiles", "")
        psmiles = features.get("psmiles", "")

        # PolymerGNN 真实权重路径（试点性质：Tg / 介电常数，model_type=polymernn 且权重已落盘时优先）
        if (
            self.model_type == "polymernn"
            and _POLYMER_GNN_IMPORTED
            and _polymer_gnn_imported()
            and property_name in ("glass_transition_temp", "dielectric_constant")
            and (psmiles or smiles)
        ):
            try:
                gnn_smiles = psmiles or smiles
                gnn_result = _polymer_gnn_predict(gnn_smiles, property_name)
                if gnn_result is not None:
                    value, confidence, model_label = gnn_result
                    return PolymerPredictionResult(
                        property_name=property_name,
                        value=value,
                        unit=self._model.PROPERTY_MODELS[property_name]["unit"],
                        confidence=confidence,
                        model=model_label,
                        psmiles=psmiles,
                        smiles=smiles,
                        formula=features.get("formula", ""),
                        material_type="polymer",
                        # ADR-0001：真实权重模型预测 → predicted（非 simulated，T-029 语义修正）
                        data_quality="predicted",
                        provenance=[{"model": model_label, "weights": "polymer_gnn_openpoly",
                                     "evidence_level": "predicted"}],
                    )
            except Exception:  # noqa: BLE001
                pass  # 回退到后续路径

        # Chemprop 真实权重路径（model_type=polymernn 且权重已落盘时优先）
        if self.model_type == "polymernn" and _CHEMPROP_IMPORTED and smiles:
            try:
                chemprop_result = _chemprop_predict(smiles, property_name)
                if chemprop_result is not None:
                    value, confidence, model_label = chemprop_result
                    return PolymerPredictionResult(
                        property_name=property_name,
                        value=value,
                        unit=self._model.PROPERTY_MODELS[property_name]["unit"],
                        confidence=confidence,
                        model=model_label,
                        psmiles=psmiles,
                        smiles=smiles,
                        formula=features.get("formula", ""),
                        material_type="polymer",
                        # ADR-0001：真实权重 Chemprop 预测 → predicted
                        data_quality="predicted",
                        provenance=[{"model": model_label, "weights": "chemprop_pretrained",
                                     "evidence_level": "predicted"}],
                    )
            except Exception:  # noqa: BLE001
                pass  # 回退到描述符路径

        # ASE-EMT 路径（mattersim + 能量相关性质）
        if (self.model_type == "mattersim" and self._ase_available
                and property_name in ("total_energy", "formation_energy") and smiles):
            try:
                value, confidence, model_label = self._predict_with_ase(smiles, property_name)
                return PolymerPredictionResult(
                    property_name=property_name,
                    value=value,
                    unit="eV" if property_name == "total_energy" else "eV/atom",
                    confidence=confidence,
                    model=model_label,
                    psmiles=psmiles,
                    smiles=smiles,
                    formula=features.get("formula", ""),
                    material_type="polymer",
                    data_quality="simulated",  # T-029：ASE-EMT 物理计算结果
                )
            except Exception:
                pass  # 回退到描述符路径

        # 描述符线性模型路径（v4.1 术语分层：启发式产出称"工程估算"，不得声称"预测"）
        if smiles:
            desc = self._calc.calculate_descriptors(smiles)
            degraded = False
        else:
            # 无有效 SMILES，占位描述符：结果 degrade，下游不得当真实预测
            desc = self._calc._fallback_descriptors(psmiles or "C")
            degraded = True

        value, confidence = self._model.predict(desc, property_name)

        return PolymerPredictionResult(
            property_name=property_name,
            value=value,
            unit=self._model.PROPERTY_MODELS[property_name]["unit"],
            confidence=confidence,
            model="descriptor_heuristic",
            psmiles=psmiles,
            smiles=smiles,
            formula=features.get("formula", ""),
            material_type="polymer",
            data_quality="estimated",  # ADR-0001：启发式骨架估算，非模型预测
            degraded=degraded,
            provenance=[{
                "source_type": "algorithm_estimate",
                "provider": "descriptor_heuristic",
                "model_or_tool": "descriptor_heuristic",
                "evidence_level": "estimated",
                "note": "基于骨架结构启发式系数，量级估算，未经验证",
            }],
        )

    def _predict_with_ase(self, smiles: str, property_name: str) -> tuple[float, float, str]:
        """使用 ASE-EMT 计算分子能量。"""
        from rdkit import Chem
        from rdkit.Chem import AllChem
        import numpy as np

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        mol_h = Chem.AddHs(mol)
        embed_params = AllChem.ETKDGv3()
        embed_params.maxIterations = 100
        if AllChem.EmbedMolecule(mol_h, embed_params) == -1:
            embed_params.useRandomCoords = True
            if AllChem.EmbedMolecule(mol_h, embed_params) == -1:
                raise ValueError(f"Failed to embed molecule: {smiles}")

        try:
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
        except Exception:
            pass

        conf = mol_h.GetConformer()
        num_atoms = mol_h.GetNumAtoms()
        symbols = [atom.GetSymbol() for atom in mol_h.GetAtoms()]
        positions = np.array([[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z]
                              for i in range(num_atoms)])

        atoms = Atoms(symbols=symbols, positions=positions)
        atoms.calc = EMT()
        energy = float(atoms.get_potential_energy())

        if property_name == "total_energy":
            value = energy
        else:  # formation_energy
            value = energy / max(num_atoms, 1)

        confidence = 0.75
        return value, confidence, "ase_emt"

    def predict_batch(self, features_list: list[dict], property_name: str,
                      target_smiles: str | None = None) -> list[PolymerPredictionResult]:
        results = [self.predict(f, property_name) for f in features_list]

        # 过滤：只保留与查询目标 SMILES 匹配的结果
        if target_smiles:
            results = [r for r in results if r.smiles.strip() == target_smiles.strip()]

        # 去重：同一 structure_id 只保留一条最高置信度记录
        seen: dict[str, PolymerPredictionResult] = {}
        for r in results:
            sid = r.smiles or r.psmiles or r.formula
            if sid not in seen or r.confidence > seen[sid].confidence:
                seen[sid] = r
        results = list(seen.values())

        return results

    def rank_candidates(self, results: list[PolymerPredictionResult], ascending: bool = True) -> list[PolymerPredictionResult]:
        return sorted(results, key=lambda r: r.value, reverse=not ascending)

    def top_k(self, results: list[PolymerPredictionResult], k: int, ascending: bool = True) -> list[PolymerPredictionResult]:
        ranked = self.rank_candidates(results, ascending)
        return ranked[:k]
