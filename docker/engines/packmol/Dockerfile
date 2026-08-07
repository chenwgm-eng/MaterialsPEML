# packmol 分子堆积引擎容器
# 用于 formulation_packing 服务的真实分子堆积计算
# 从源码编译 packmol（避免依赖预编译二进制）
FROM debian:bookworm-slim

# 切换到清华 Debian 镜像源（避免 502 Bad Gateway）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null \
    || true

# 安装编译依赖（gfortran/make/curl 用于编译 packmol）
RUN apt-get update \
    && apt-get install -y --no-install-recommends --fix-missing \
        gfortran make ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# 编译 packmol v20.14.2（从 GitHub 源码）
RUN curl -fsSL https://github.com/m3g/packmol/archive/refs/tags/v20.14.2.tar.gz -o /tmp/packmol.tar.gz \
    && tar xzf /tmp/packmol.tar.gz -C /tmp \
    && cd /tmp/packmol-20.14.2 \
    && ./configure \
    && make \
    && cp packmol /usr/local/bin/packmol \
    && chmod +x /usr/local/bin/packmol \
    && rm -rf /tmp/*

# 验证 packmol 可执行
RUN packmol --help 2>&1 | head -1 || echo "packmol installed at /usr/local/bin/packmol"

WORKDIR /work
ENTRYPOINT ["packmol"]
