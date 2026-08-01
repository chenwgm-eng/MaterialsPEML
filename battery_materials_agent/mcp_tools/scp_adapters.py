"""SCP Adapters — map internal DTOs to SCP tool parameters and back."""

from __future__ import annotations
from .scp_catalog import ToolBinding


class SCPAdapter:
    """Base adapter for mapping internal DTOs to SCP tool parameters and back."""

    def validate_and_map_input(self, args: dict, binding: ToolBinding) -> dict:
        return args

    def normalize_output(self, raw_result: dict, binding: ToolBinding) -> dict:
        return raw_result


class MoleculeDescriptorAdapter(SCPAdapter):
    """Maps SMILES input to descriptor tool params."""

    def validate_and_map_input(self, args: dict, binding: ToolBinding) -> dict:
        mapped = {"smiles": args.get("smiles", "")}
        if "descriptors" in args:
            mapped["descriptors"] = args["descriptors"]
        return mapped

    def normalize_output(self, raw_result: dict, binding: ToolBinding) -> dict:
        return {
            "canonical_smiles": raw_result.get("canonical_smiles", ""),
            "descriptors": raw_result.get("descriptors", {}),
            "warnings": raw_result.get("warnings", []),
        }


class ToxicityAssessmentAdapter(SCPAdapter):
    """Maps SMILES to toxicity assessment params."""

    def validate_and_map_input(self, args: dict, binding: ToolBinding) -> dict:
        mapped = {"smiles": args.get("smiles", "")}
        if "endpoints" in args:
            mapped["endpoints"] = args["endpoints"]
        return mapped

    def normalize_output(self, raw_result: dict, binding: ToolBinding) -> dict:
        return {
            "endpoints": raw_result.get("endpoints", {}),
            "risk_level": raw_result.get("risk_level", "unknown"),
            "confidence": raw_result.get("confidence", 0.0),
            "evidence": raw_result.get("evidence", "辅助证据"),
        }


class LiteratureSearchAdapter(SCPAdapter):
    """Maps query + filters to literature search params.

    远端 Origene-PubChem 的 search_pubchem_by_name 工具接受 ``name`` 参数。
    内部 DTO 使用 ``query``，需在此映射为 ``name``；若调用方已直接传入
    ``name``（如工具自测），则透传。
    """

    def validate_and_map_input(self, args: dict, binding: ToolBinding) -> dict:
        if "name" in args:
            mapped = {"name": args["name"]}
        else:
            mapped = {"name": args.get("query", "")}
        if "filters" in args:
            mapped["filters"] = args["filters"]
        if "limit" in args:
            mapped["limit"] = args["limit"]
        return mapped

    def normalize_output(self, raw_result: dict, binding: ToolBinding) -> dict:
        return {
            "documents": raw_result.get("documents", []),
            "claims": raw_result.get("claims", []),
            "sources": raw_result.get("sources", []),
        }


class ProtocolDraftAdapter(SCPAdapter):
    """Maps experiment order info to protocol draft params."""

    def validate_and_map_input(self, args: dict, binding: ToolBinding) -> dict:
        mapped = {"experiment_type": args.get("experiment_type", "")}
        if "materials" in args:
            mapped["materials"] = args["materials"]
        if "target_property" in args:
            mapped["target_property"] = args["target_property"]
        if "notes" in args:
            mapped["notes"] = args["notes"]
        return mapped

    def normalize_output(self, raw_result: dict, binding: ToolBinding) -> dict:
        return {
            "protocol": raw_result.get("protocol", {}),
            "materials": raw_result.get("materials", []),
            "equipment": raw_result.get("equipment", []),
            "hazards": raw_result.get("hazards", []),
        }


class MaterialTransformAdapter(SCPAdapter):
    """Maps structure to material transform params.

    远端 SciToolAgent-Mat 的 SMILESToCAS 等工具接受 ``smiles`` 参数。
    若调用方传入 ``structure``（内部 DTO），映射为 ``smiles``；若已直接
    传入 ``smiles``（如工具自测），则透传。
    """

    def validate_and_map_input(self, args: dict, binding: ToolBinding) -> dict:
        if "smiles" in args:
            mapped = {"smiles": args["smiles"]}
        else:
            mapped = {"smiles": args.get("structure", "")}
        if "transform_type" in args:
            mapped["transform_type"] = args["transform_type"]
        if "constraints" in args:
            mapped["constraints"] = args["constraints"]
        return mapped

    def normalize_output(self, raw_result: dict, binding: ToolBinding) -> dict:
        return {
            "candidates": raw_result.get("candidates", []),
            "assumptions": raw_result.get("assumptions", []),
        }
