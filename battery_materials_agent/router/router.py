"""Material type router - classifies input and routes to polymer or crystal branch."""

from enum import Enum
from pydantic import BaseModel, Field


class MaterialType(str, Enum):
    CRYSTAL = "crystal"
    POLYMER = "polymer"
    ORGANIC = "organic"
    UNKNOWN = "unknown"


class MaterialBranch(str, Enum):
    CRYSTAL_BRANCH = "crystal_branch"
    POLYMER_BRANCH = "polymer_branch"
    ORGANIC_BRANCH = "organic_branch"


class MaterialInput(BaseModel):
    name: str = ""
    smiles: str = ""
    psmiles: str = ""
    cif_path: str = ""
    poscar: str = ""
    formula: str = ""
    material_type_hint: MaterialType = MaterialType.UNKNOWN


class RouterResult(BaseModel):
    material_type: MaterialType
    branch: MaterialBranch
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class MaterialRouter:
    """Routes materials to the correct processing branch based on input format."""

    # v4.1 改性塑料领域：工程塑料缩写（精确整名匹配）+ 高分子通用词
    POLYMER_ABBREVIATIONS = {
        "PA6", "PA66", "PA12", "PA46", "PA610", "PA1010",
        "PC", "ABS", "PP", "PE", "PS", "PBT", "PET", "POM",
        "PPS", "PTFE", "PMMA", "PEI", "PEEK", "TPU", "EVA",
        "PLA", "PBAT", "LCP", "PPO", "SAN", "PCT", "PVDF", "PVA",
    }
    POLYMER_KEYWORDS = {
        "polymer", "peo", "pan", "pvdf", "pmma", "polystyrene", "polyethylene", "polypropylene",
        "nylon", "polyamide", "polycarbonate", "polyacetal", "polyoxymethylene",
        "polybutylene", "polylactic", "polylactide", "polyether", "polyurethane",
        "尼龙", "聚酰胺", "聚碳酸酯", "聚丙烯", "聚乙烯", "聚苯乙烯", "聚甲醛",
        "聚酯", "聚氨酯", "聚乳酸", "玻纤增强", "碳纤增强", "阻燃", "改性塑料",
        "工程塑料", "pa6", "pa66", "abs", "pbt", "pet", "pom", "pps", "ptfe",
        "peek", "tpu", "eva", "pla", "pbse", "lcp", "ppo",
    }
    CRYSTAL_KEYWORDS = {"crystal", "cubic", "tetragonal", "orthorhombic", "spinel", "layered", "nasicon", "garnet"}

    def route(self, material: MaterialInput) -> RouterResult:
        if material.psmiles:
            return RouterResult(
                material_type=MaterialType.POLYMER,
                branch=MaterialBranch.POLYMER_BRANCH,
                confidence=0.95,
                reason="PSMILES notation detected",
            )

        if material.cif_path or material.poscar:
            return RouterResult(
                material_type=MaterialType.CRYSTAL,
                branch=MaterialBranch.CRYSTAL_BRANCH,
                confidence=0.95,
                reason="CIF/POSCAR structure file detected",
            )

        if material.smiles:
            try:
                from rdkit import Chem
            except ImportError:
                return RouterResult(
                    material_type=MaterialType.ORGANIC,
                    branch=MaterialBranch.ORGANIC_BRANCH,
                    confidence=0.5,
                    reason="SMILES provided but rdkit unavailable; defaulting to organic",
                )
            mol = Chem.MolFromSmiles(material.smiles)
            if mol is not None:
                heavy_atoms = mol.GetNumHeavyAtoms()
                if heavy_atoms > 50:
                    return RouterResult(
                        material_type=MaterialType.POLYMER,
                        branch=MaterialBranch.POLYMER_BRANCH,
                        confidence=0.7,
                        reason="Large SMILES likely represents polymer fragment",
                    )
                return RouterResult(
                    material_type=MaterialType.ORGANIC,
                    branch=MaterialBranch.ORGANIC_BRANCH,
                    confidence=0.8,
                    reason="Small molecule SMILES detected",
                )

        if material.material_type_hint != MaterialType.UNKNOWN:
            hint_branch = {
                MaterialType.CRYSTAL: MaterialBranch.CRYSTAL_BRANCH,
                MaterialType.POLYMER: MaterialBranch.POLYMER_BRANCH,
                MaterialType.ORGANIC: MaterialBranch.ORGANIC_BRANCH,
            }
            return RouterResult(
                material_type=material.material_type_hint,
                branch=hint_branch.get(material.material_type_hint, MaterialBranch.CRYSTAL_BRANCH),
                confidence=0.6,
                reason="User-provided type hint",
            )

        name_upper = material.name.strip().upper()
        if name_upper in self.POLYMER_ABBREVIATIONS:
            return RouterResult(
                material_type=MaterialType.POLYMER,
                branch=MaterialBranch.POLYMER_BRANCH,
                confidence=0.9,
                reason=f"Engineering plastic abbreviation match: {name_upper}",
            )

        name_lower = material.name.lower()
        for kw in self.POLYMER_KEYWORDS:
            if kw in name_lower:
                return RouterResult(
                    material_type=MaterialType.POLYMER,
                    branch=MaterialBranch.POLYMER_BRANCH,
                    confidence=0.75,
                    reason=f"Keyword match: {kw}",
                )

        for kw in self.CRYSTAL_KEYWORDS:
            if kw in name_lower:
                return RouterResult(
                    material_type=MaterialType.CRYSTAL,
                    branch=MaterialBranch.CRYSTAL_BRANCH,
                    confidence=0.75,
                    reason=f"Keyword match: {kw}",
                )

        return RouterResult(
            material_type=MaterialType.UNKNOWN,
            branch=MaterialBranch.CRYSTAL_BRANCH,
            confidence=0.2,
            reason="无法判定材料类型：输入不含可识别的 PSMILES/SMILES/结构文件或材料类型关键词",
        )
