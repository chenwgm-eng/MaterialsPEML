"""FEniCSx 求解器适配器（连续介质尺度）。

可选依赖 + 优雅降级：
- 通过 ``dolfinx`` Python 模块探测可用性（FEniCSx 体系）。
- 可用时执行薄片热-电化学耦合 PDE 弱形式求解。
- 不可用时返回 None，由调用方降级到模板近似并标记 estimate。
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np  # noqa: F401  # 供降级路径使用

logger = logging.getLogger(__name__)

# 探测缓存
_available: bool | None = None


def fenicsx_available() -> bool:
    """探测 FEniCSx（dolfinx）是否可导入。"""
    global _available
    if _available is not None:
        return _available
    try:
        import dolfinx  # noqa: F401
        _available = True
    except Exception:  # noqa: BLE001
        _available = False
    return _available


class FEniCSxAdapter:
    """FEniCSx 薄片热-电化学耦合 PDE 求解适配器。"""

    def __init__(self):
        self.available = fenicsx_available()

    def run(self, material: dict, **kwargs: Any) -> dict | None:
        """执行薄片热-电化学耦合 PDE 求解。

        Args:
            material: 含 formula / 分子尺度属性（供参数化）
            kwargs: L, W, thermal_k, ec_conductivity 等

        Returns:
            结构化结果 dict；不可用时返回 None。
        """
        if not self.available:
            return None
        try:
            return self._solve_thermo_ec(material, **kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("FEniCSx 求解失败: %s", e)
            return None

    def _solve_thermo_ec(self, material: dict, **kwargs: Any) -> dict:
        """薄片热-电化学耦合 PDE。

        求解二维薄片稳态热传导 + 电流位势耦合：
            -∇·(k ∇T) = Q       (热方程，k 热导率，Q 生热)
            -∇·(σ ∇φ) = 0       (电流守恒，σ 电导率)

        返回中心/边缘位置的温度场与位势场统计量。
        """
        import dolfinx
        from dolfinx import fem, mesh
        from dolfinx.fem.petsc import LinearProblem
        from mpi4py import MPI
        import ufl

        L = float(kwargs.get("L", 1.0))
        W = float(kwargs.get("W", 1.0))
        thermal_k = float(kwargs.get("thermal_k", 1.0))
        ec = float(kwargs.get("ec_conductivity", 1.0))
        heat_q = float(kwargs.get("heat_generation", 1.0))
        boundary_temp = float(kwargs.get("boundary_temp", 300.0))

        domain = mesh.create_rectangle(MPI.COMM_WORLD, [[0, 0], [L, W]], [40, 40])
        V = fem.functionspace(domain, ("P", 1))

        # 热方程
        T_func = fem.Function(V)
        T_test = ufl.TestFunction(V)
        T_trial = ufl.TrialFunction(V)
        a_T = thermal_k * ufl.dot(ufl.grad(T_trial), ufl.grad(T_test)) * ufl.dx
        L_T = heat_q * T_test * ufl.dx
        boundary_facets_T = mesh.locate_entities_boundary(domain, domain.topology.dim - 1, lambda x: np.isclose(x[0], 0.0) | np.isclose(x[0], L))
        bc_T = fem.dirichletbc(T_func, fem.locate_dofs_topological(V, domain.topology.dim - 1, boundary_facets_T))
        problem_T = LinearProblem(a_T, L_T, bcs=[bc_T], petsc_options={"ksp_type": "preonly", "pc_type": "lu"})
        T_sol = problem_T.solve()

        # 电流位势
        phi_func = fem.Function(V)
        phi_test = ufl.TestFunction(V)
        phi_trial = ufl.TrialFunction(V)
        a_phi = ec * ufl.dot(ufl.grad(phi_trial), ufl.grad(phi_test)) * ufl.dx
        L_phi = ufl.constant.Constant(domain, 1.0) * phi_test * ufl.dx
        boundary_facets_phi = mesh.locate_entities_boundary(domain, domain.topology.dim - 1, lambda x: np.isclose(x[0], 0.0))
        bc_phi = fem.dirichletbc(phi_func, fem.locate_dofs_topological(V, domain.topology.dim - 1, boundary_facets_phi))
        problem_phi = LinearProblem(a_phi, L_phi, bcs=[bc_phi], petsc_options={"ksp_type": "preonly", "pc_type": "lu"})
        phi_sol = problem_phi.solve()

        T_vals = T_sol.x.array
        phi_vals = phi_sol.x.array
        return {
            "task": "thermo_electrochemical_coupling",
            "max_temperature": round(float(np.max(T_vals)), 4),
            "min_temperature": round(float(np.min(T_vals)), 4),
            "mean_temperature": round(float(np.mean(T_vals)), 4),
            "max_potential": round(float(np.max(phi_vals)), 4),
            "min_potential": round(float(np.min(phi_vals)), 4),
            "thermal_conductivity": thermal_k,
            "ec_conductivity": ec,
            "dimensions": [L, W],
            "formula": material.get("formula", ""),
        }