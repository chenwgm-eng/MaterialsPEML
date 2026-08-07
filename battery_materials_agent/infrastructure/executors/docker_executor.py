"""Docker 常驻容器执行工具 — 统一管理引擎容器的启停和命令执行。

设计目标：
- 替代 ``docker run --rm`` 模式，改为常驻容器 + ``docker exec``
- 首次调用时自动启动常驻容器，后续复用，提高效率、便于调试
- 统一封装路径规范化、容器命名、健康检查、超时处理

容器命名约定：``batteryemcl-{engine}-persistent``，确保同一镜像只启动一个常驻实例。

挂载策略：
    常驻容器在创建时挂载 ``_ENGINE_TMP_ROOT``（所有引擎工作目录的公共父目录）
    到 ``/work``。每次调用 ``run_in_persistent_container`` 时，根据 ``work_dir``
    计算其在容器内的相对路径（``/work/<rel>``），通过 ``docker exec -w`` 设置
    工作目录。这样无需为每次调用重建容器。
"""
from __future__ import annotations

import os
import subprocess
import threading
from typing import Any

from .execution_adapter import _ENGINE_TMP_ROOT

# ── 常驻容器注册表（进程内单例）──────────────────────────────────
# key: container_name, value: 容器是否已确认运行
_running_containers: dict[str, bool] = {}
_lock = threading.Lock()


def _normalize_path_for_mount(path: str) -> str:
    """Windows 路径规范化为 Docker 挂载格式。

    Docker Desktop on Windows 要求路径使用正斜杠：
    ``D:\\foo\\bar`` → ``D:/foo/bar``
    """
    return path.replace("\\", "/")


def _container_is_running(container_name: str) -> bool:
    """检查指定容器是否正在运行。"""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container_name],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.SubprocessError, OSError):
        return False


def _start_persistent_container(
    container_name: str,
    image: str,
    entrypoint: str | None = None,
    extra_run_args: list[str] | None = None,
) -> bool:
    """启动常驻容器（若已存在则启动；若镜像不存在返回 False）。

    Args:
        container_name: 容器名（固定，用于复用）
        image: Docker 镜像
        entrypoint: 可选，覆盖镜像 ENTRYPOINT
        extra_run_args: 额外 ``docker run`` 参数（如 -v 挂载）

    Returns:
        True 若容器已运行；False 若镜像不可用或启动失败
    """
    # 镜像可用性检查
    try:
        check = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=15,
        )
        if check.returncode != 0:
            return False
    except (subprocess.SubprocessError, OSError):
        return False

    # 若容器已运行，直接复用
    if _container_is_running(container_name):
        return True

    # 若容器已存在但停止，先删除（避免名字冲突）
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True, timeout=15,
    )

    # 启动常驻容器
    # --rm 不使用（常驻）；-d 后台运行；--restart unless-stopped 便于调试
    cmd = ["docker", "run", "-d", "--name", container_name,
           "--restart", "unless-stopped"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint]
    if extra_run_args:
        cmd += extra_run_args
    cmd += [image]

    # 常驻容器需要一个保持运行的命令，否则会立即退出
    # 对于不同镜像，使用 sleep infinity 保持存活
    cmd += ["tail", "-f", "/dev/null"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return False
        return _container_is_running(container_name)
    except (subprocess.SubprocessError, OSError):
        return False


def ensure_container(
    engine_key: str,
    image: str,
    entrypoint: str | None = None,
    extra_run_args: list[str] | None = None,
) -> str | None:
    """确保常驻容器已启动并返回容器名。

    线程安全：多线程调用时同一 engine_key 只启动一个容器实例。

    Args:
        engine_key: 引擎标识（如 "lammps", "packmol", "science", "docking"）
        image: Docker 镜像名
        entrypoint: 可选，覆盖镜像 ENTRYPOINT（仅启动时生效）
        extra_run_args: 额外 ``docker run`` 参数

    Returns:
        容器名；若镜像不可用或启动失败返回 None
    """
    container_name = f"batteryemcl-{engine_key}-persistent"
    with _lock:
        if _running_containers.get(container_name):
            # 快速路径：进程内已记录运行中，但仍需验证
            if _container_is_running(container_name):
                return container_name
            _running_containers.pop(container_name, None)

        ok = _start_persistent_container(
            container_name, image, entrypoint, extra_run_args
        )
        if ok:
            _running_containers[container_name] = True
            return container_name
        return None


def docker_exec(
    container_name: str,
    cmd_args: list[str],
    workdir: str = "/work",
    timeout: int = 600,
) -> tuple[int, str, str]:
    """在常驻容器中执行命令。

    Args:
        container_name: 容器名
        cmd_args: 要执行的命令参数（如 ``["python", "/work/script.py", "arg1"]``）
        workdir: 容器内工作目录
        timeout: 超时秒数

    Returns:
        (exit_code, stdout, stderr)
    """
    full_cmd = ["docker", "exec", "-w", workdir, container_name] + cmd_args
    try:
        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", (e.stderr or "") + "\n[TIMEOUT]"
    except (subprocess.SubprocessError, OSError) as e:
        return 1, "", str(e)


def copy_to_container(container_name: str, src: str, dst: str) -> bool:
    """将主机文件/目录复制到容器内。

    Args:
        container_name: 容器名
        src: 主机源路径
        dst: 容器内目标路径

    Returns:
        True 若成功
    """
    try:
        result = subprocess.run(
            ["docker", "cp", src, f"{container_name}:{dst}"],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def copy_from_container(container_name: str, src: str, dst: str) -> bool:
    """将容器内文件/目录复制到主机。

    Args:
        container_name: 容器名
        src: 容器内源路径
        dst: 主机目标路径

    Returns:
        True 若成功
    """
    try:
        result = subprocess.run(
            ["docker", "cp", f"{container_name}:{src}", dst],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def stop_all_persistent_containers() -> None:
    """停止并删除所有 batteryemcl-* 常驻容器（用于清理）。"""
    with _lock:
        for name in list(_running_containers.keys()):
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True, timeout=15,
            )
        _running_containers.clear()


def run_in_persistent_container(
    engine_key: str,
    image: str,
    cmd_args: list[str],
    work_dir: str,
    entrypoint: str | None = None,
    extra_run_args: list[str] | None = None,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """高层封装：确保容器运行 + 在其中执行命令。

    替代旧的 ``docker run --rm`` 模式。常驻容器挂载 ``_ENGINE_TMP_ROOT`` 到
    ``/work``，本函数根据 ``work_dir`` 计算 ``/work/<rel>`` 作为容器工作目录。

    Args:
        engine_key: 引擎标识
        image: Docker 镜像名
        cmd_args: 容器内要执行的命令（应使用相对路径，如 ``["python", "script.py"]``）
        work_dir: 主机工作目录（须为 ``_ENGINE_TMP_ROOT`` 的子目录）
        entrypoint: 可选，覆盖镜像 ENTRYPOINT（仅启动时生效）
        extra_run_args: 额外 ``docker run`` 参数
        timeout: 超时秒数

    Returns:
        (exit_code, stdout, stderr)

    若容器无法启动（镜像不可用等），返回 (1, "", "镜像不可用")。
    """
    # 确保容器运行（首次调用时启动，后续复用）
    # 常驻容器始终挂载 _ENGINE_TMP_ROOT 到 /work
    mount_source = _normalize_path_for_mount(_ENGINE_TMP_ROOT)
    run_args = ["-v", f"{mount_source}:/work"]
    if extra_run_args:
        run_args += extra_run_args

    container_name = ensure_container(
        engine_key, image, entrypoint, run_args
    )
    if container_name is None:
        return 1, "", f"Docker 镜像不可用或容器启动失败: {image}"

    # 计算 work_dir 在容器内的路径：/work/<相对路径>
    # work_dir 须为 _ENGINE_TMP_ROOT 的子目录
    try:
        rel = os.path.relpath(work_dir, _ENGINE_TMP_ROOT).replace("\\", "/")
    except ValueError:
        # Windows 跨盘符时 relpath 抛 ValueError
        rel = os.path.basename(work_dir)
    if rel == ".":
        container_workdir = "/work"
    else:
        container_workdir = f"/work/{rel}"

    # 在常驻容器中执行命令，工作目录设为 /work/<rel>
    return docker_exec(container_name, cmd_args, workdir=container_workdir, timeout=timeout)


__all__ = [
    "ensure_container",
    "docker_exec",
    "copy_to_container",
    "copy_from_container",
    "stop_all_persistent_containers",
    "run_in_persistent_container",
]
