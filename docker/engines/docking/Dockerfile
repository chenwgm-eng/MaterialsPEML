# 分子对接引擎容器 — AutoDock Vina + meeko + OpenBabel + RDKit
# 用于 molecular_docking 服务的真实分子对接计算
# AutoDock Vina: Apache 2.0 许可证，CPU 推理，无需 GPU 与模型权重
FROM python:3.10-slim

# 切换到清华 Debian 镜像源（避免 502 Bad Gateway）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null \
    || true

# 安装系统依赖：OpenBabel（PDB→PDBQT 转换）、libgomp1（Vina C++ 后端需要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends --fix-missing \
        openbabel \
        libgomp1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 库（pip 使用清华镜像源加速）
# pin numpy<2：vina 1.2 用 numpy 1.x 编译
# vina: AutoDock Vina 的 Python 绑定（pip install vina 提供 vina 包）
# meeko: SMILES → PDBQT 配体准备工具（0.7+ 需要 rdkit HasQuery，需 rdkit>=2023.3）
# gemmi: meeko 的 polymer 模块依赖（化学模板生成）
# rdkit: 分子描述符与格式转换（官方包，2023.3+ 含 HasQuery）
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    "numpy>=1.24,<2" \
    "scipy>=1.10" \
    "rdkit>=2023.3" \
    "gemmi>=0.6" \
    "meeko>=0.5" \
    "vina>=0.4"

# 验证关键库可导入（vina + meeko + gemmi + rdkit）
RUN python -c "from vina import Vina; from meeko import MoleculePreparation; import gemmi; from rdkit import Chem; print('all imports OK')" || echo "import check failed (non-fatal)"

WORKDIR /work
# 默认入口点 python，适配器通过 docker exec 调用对接脚本
ENTRYPOINT ["python"]
