# 科学计算引擎容器 — pyscf (量子化学) + openmm (分子动力学) + rdkit
# 用于 wavefunction_analysis (ESP/HOMO/LUMO) 和 molecular_simulation (有机小分子 MD)
FROM python:3.10-slim

# 切换到清华 Debian 镜像源（避免 502 Bad Gateway）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null \
    || true

# 安装运行时必需的最小系统库（pyscf/openmp 需要 libgomp）
RUN apt-get update \
    && apt-get install -y --no-install-recommends --fix-missing \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 安装科学计算库（pip 使用清华镜像源加速）
# pin numpy<2：rdkit-pypi 2022.9 用 numpy 1.x 编译，numpy 2.x 会导致 _ARRAY_API not found
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    "pyscf>=2.4" \
    "openmm>=8.1" \
    "rdkit-pypi>=2022.9" \
    "numpy>=1.24,<2" \
    "scipy>=1.10"

WORKDIR /work
ENTRYPOINT ["python"]
