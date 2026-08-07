"""分子/晶体结构生成与优化适配器。"""
from __future__ import annotations

from typing import Any

from .execution_adapter import ExecutionAdapter


class StructureAdapter(ExecutionAdapter):
    """分子/晶体结构生成与优化适配器。

    支持的操作：
    - generate: 从 SMILES 生成 3D 结构
    - optimize: 几何优化
    - convert: 格式转换
    - validate: 结构验证
    """

    _SUPPORTED_OPERATIONS = {"generate", "optimize", "convert", "validate"}

    def __init__(self) -> None:
        self._rdkit_available = self._try_import_rdkit()
        self._pybel_available = self._try_import_pybel()
        self._openbabel_available = self._try_import_openbabel()

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    def _try_import_rdkit(self) -> bool:
        try:
            import rdkit  # noqa: F401
            return True
        except ImportError:
            return False

    def _try_import_pybel(self) -> bool:
        try:
            import pybel  # noqa: F401
            return True
        except ImportError:
            return False

    def _try_import_openbabel(self) -> bool:
        try:
            import openbabel  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Handle structure operations based on *operation* field.

        Input format::

            {
                "operation": "generate" | "optimize" | "convert" | "validate",
                "input_format": "...",
                "input_data": "...",
                ...operation-specific fields...
            }
        """
        operation = prepared_input.get("operation", "")
        if operation not in self._SUPPORTED_OPERATIONS:
            return {
                "error": f"Unsupported operation: {operation}. "
                f"Supported: {', '.join(sorted(self._SUPPORTED_OPERATIONS))}",
            }

        dispatch = {
            "generate": self._handle_generate,
            "optimize": self._handle_optimize,
            "convert": self._handle_convert,
            "validate": self._handle_validate,
        }
        return dispatch[operation](prepared_input)

    def parse_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Parse raw structure output into structured format."""
        return raw_output

    def get_resource_requirements(
        self, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        return {"cpu": 2, "memory_mb": 1024, "walltime_minutes": 10}

    # ------------------------------------------------------------------
    # Operation handlers
    # ------------------------------------------------------------------

    def _handle_generate(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Generate 3D structure from SMILES.

        Fields: smiles (str), num_conformers (int, default 1),
                optimize (bool, default True), output_format (str, default "pdb").
        """
        smiles = prepared_input.get("smiles", "")
        if not smiles:
            return {"error": "SMILES string is required"}

        num_conformers = prepared_input.get("num_conformers", 1)
        optimize = prepared_input.get("optimize", True)
        output_format = prepared_input.get("output_format", "pdb").lower()

        if not self._rdkit_available:
            return {
                "smiles": smiles,
                "warning": "RDKit not available, returning placeholder",
                "structure": None,
            }

        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return {"error": f"Invalid SMILES: {smiles}"}

            mol = Chem.AddHs(mol)

            if num_conformers > 1:
                params = AllChem.EmbedMultipleConfs(mol, numConfs=num_conformers)
                if optimize:
                    for conf_id in range(num_conformers):
                        AllChem.MMFFOptimizeMolecule(mol, confId=conf_id)
                num_generated = len(params)
            else:
                AllChem.EmbedMolecule(mol)
                if optimize:
                    AllChem.MMFFOptimizeMolecule(mol)
                num_generated = 1

            # xyz/sdf 格式保留氢原子；pdb/mol 移除氢以符合常规约定
            if output_format in ("xyz", "sdf"):
                mol_out = mol
            else:
                mol_out = Chem.RemoveHs(mol)
            smiles_out = Chem.MolToSmiles(mol_out)

            if output_format == "xyz":
                structure_block = Chem.MolToXYZBlock(mol_out)
            elif output_format == "pdb":
                structure_block = Chem.MolToPDBBlock(mol_out)
            elif output_format in ("mol", "molblock"):
                structure_block = Chem.MolToMolBlock(mol_out)
            elif output_format in ("smi", "smiles"):
                structure_block = smiles_out
            elif output_format == "sdf":
                structure_block = Chem.MolToMolBlock(mol_out)
            else:
                structure_block = Chem.MolToPDBBlock(mol_out)
                output_format = "pdb"

            return {
                "smiles": smiles_out,
                "num_conformers": num_generated,
                "format": output_format,
                "structure": structure_block,
            }
        except Exception as exc:
            return {"error": f"Structure generation failed: {exc}"}

    def _handle_optimize(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Geometry optimization.

        Fields: input_format (str), input_data (str),
                method (str, default "mmff"), max_iterations (int, default 200).
        """
        input_format = prepared_input.get("input_format", "smi")
        input_data = prepared_input.get("input_data", "")
        method = prepared_input.get("method", "mmff")
        max_iterations = prepared_input.get("max_iterations", 200)

        if not input_data:
            return {"error": "input_data is required"}

        if not self._rdkit_available:
            return {
                "warning": "RDKit not available, returning input unchanged",
                "input_format": input_format,
                "structure": input_data,
            }

        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem

            if input_format.lower() in ("smi", "smiles"):
                mol = Chem.MolFromSmiles(input_data)
            elif input_format.lower() in ("mol", "molblock"):
                mol = Chem.MolFromMolBlock(input_data)
            elif input_format.lower() == "pdb":
                mol = Chem.MolFromPDBBlock(input_data)
            else:
                return {"error": f"Unsupported input format: {input_format}"}

            if mol is None:
                return {"error": "Failed to parse input structure"}

            mol = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol)

            if method == "mmff":
                converged = AllChem.MMFFOptimizeMolecule(mol, maxIters=max_iterations)
            elif method == "uff":
                converged = AllChem.UFFOptimizeMolecule(mol, maxIters=max_iterations)
            else:
                return {"error": f"Unsupported optimization method: {method}"}

            mol = Chem.RemoveHs(mol)
            pdb_block = Chem.MolToPDBBlock(mol)

            return {
                "converged": bool(converged == 0),
                "method": method,
                "format": "pdb",
                "structure": pdb_block,
            }
        except Exception as exc:
            return {"error": f"Optimization failed: {exc}"}

    def _handle_convert(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Format conversion.

        Fields: input_format (str), input_data (str),
                output_format (str, default "pdb").
        """
        input_format = prepared_input.get("input_format", "")
        input_data = prepared_input.get("input_data", "")
        output_format = prepared_input.get("output_format", "pdb")

        if not input_data or not input_format:
            return {"error": "input_format and input_data are required"}

        if self._pybel_available or self._openbabel_available:
            try:
                return self._convert_with_openbabel(
                    input_data, input_format, output_format
                )
            except Exception as exc:
                return {"error": f"Format conversion failed: {exc}"}

        if self._rdkit_available:
            try:
                return self._convert_with_rdkit(
                    input_data, input_format, output_format
                )
            except Exception as exc:
                return {"error": f"Format conversion failed: {exc}"}

        return {
            "warning": "No conversion libraries available, returning input unchanged",
            "structure": input_data,
        }

    def _handle_validate(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Structure validation.

        Fields: input_format (str), input_data (str).
        """
        input_format = prepared_input.get("input_format", "smi")
        input_data = prepared_input.get("input_data", "")

        if not input_data:
            return {"error": "input_data is required"}

        if not self._rdkit_available:
            return {"valid": False, "warning": "RDKit not available"}

        try:
            from rdkit import Chem

            if input_format.lower() in ("smi", "smiles"):
                mol = Chem.MolFromSmiles(input_data)
            elif input_format.lower() in ("mol", "molblock"):
                mol = Chem.MolFromMolBlock(input_data)
            elif input_format.lower() == "pdb":
                mol = Chem.MolFromPDBBlock(input_data)
            else:
                mol = None

            if mol is None:
                return {"valid": False, "warnings": ["Failed to parse structure"]}

            warnings: list[str] = []
            try:
                Chem.SanitizeMol(mol)
            except Exception as e:
                warnings.append(f"Sanitization warning: {e}")

            num_atoms = mol.GetNumAtoms()
            num_heavy = mol.GetNumHeavyAtoms()

            return {
                "valid": len(warnings) == 0,
                "num_atoms": num_atoms,
                "num_heavy_atoms": num_heavy,
                "warnings": warnings,
            }
        except Exception as exc:
            return {"valid": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _convert_with_openbabel(
        self, input_data: str, input_format: str, output_format: str
    ) -> dict[str, Any]:
        """Convert using OpenBabel (via pybel or openbabel directly)."""
        if self._pybel_available:
            import pybel

            mol = pybel.readstring(input_format, input_data)
            output_data = mol.write(output_format)
        else:
            import openbabel

            conv = openbabel.OBConversion()
            conv.SetInAndOutFormats(input_format, output_format)
            mol = openbabel.OBMol()
            conv.ReadString(mol, input_data)
            output_data = conv.WriteString(mol)

        return {
            "input_format": input_format,
            "output_format": output_format,
            "structure": output_data,
        }

    def _convert_with_rdkit(
        self, input_data: str, input_format: str, output_format: str
    ) -> dict[str, Any]:
        """Convert using RDKit (limited format support)."""
        from rdkit import Chem

        if input_format.lower() in ("smi", "smiles"):
            mol = Chem.MolFromSmiles(input_data)
        elif input_format.lower() in ("mol", "molblock"):
            mol = Chem.MolFromMolBlock(input_data)
        elif input_format.lower() == "pdb":
            mol = Chem.MolFromPDBBlock(input_data)
        else:
            raise ValueError(f"Unsupported input format: {input_format}")

        if mol is None:
            raise ValueError("Failed to parse input structure")

        output_format_lower = output_format.lower()
        if output_format_lower in ("pdb",):
            output_data = Chem.MolToPDBBlock(mol)
        elif output_format_lower in ("smi", "smiles"):
            output_data = Chem.MolToSmiles(mol)
        elif output_format_lower in ("mol", "molblock"):
            output_data = Chem.MolToMolBlock(mol)
        elif output_format_lower == "xyz":
            mol_h = Chem.AddHs(mol)
            output_data = Chem.MolToXYZBlock(mol_h)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

        return {
            "input_format": input_format,
            "output_format": output_format,
            "structure": output_data,
        }