"""DockingAdapter 降级语义回归测试。

Vina 引擎不可用时，回退必须返回 ``status: degraded`` + ``source: simulated``，
不得以 ``completed`` 呈现伪造对接结果（避免进入正式证据链）。
"""
from battery_materials_agent.infrastructure.executors.docking_adapter import DockingAdapter


class TestDockingFallbackDegraded:
    def test_fallback_is_degraded_not_completed(self):
        adapter = DockingAdapter()
        # 强制 Vina 不可用，走降级路径
        adapter._vina = None
        result = adapter.execute({
            "protein_path": "/tmp/receptor.pdb",
            "ligand": "CCO",
            "ligand_format": "smiles",
            "samples_per_complex": 5,
            "inference_steps": 10,
        })
        assert result["status"] == "degraded", \
            f"Vina 不可用时不得返回 completed，实际: {result['status']}"
        assert result.get("source") == "simulated"
        assert result["poses"]
        # 每个位姿都应明确标注为模拟数据
        assert all(p["metadata"]["method"] == "simulated" for p in result["poses"])

    def test_input_validation_still_fails_fast(self):
        adapter = DockingAdapter()
        adapter._vina = None
        result = adapter.execute({
            "protein_path": "",  # 空受体
            "ligand": "CCO",
            "ligand_format": "smiles",
        })
        assert result["status"] == "failed"
        assert result["errors"]