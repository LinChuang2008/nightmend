"""
服务自动发现模块。

支持两种发现方式：
1. Docker 容器发现 — 通过 docker ps 获取运行中容器及端口映射
2. 宿主机进程发现 — 通过 ss -tlnp 获取监听端口和进程名，排除 Docker 管理的端口

两种方式互补，全面覆盖容器化和非容器化的服务。
"""
import json
import logging
import re
import shutil
import subprocess
from typing import List, Optional, Set

from vigilops_agent.config import LogSourceConfig, ServiceCheckConfig

logger = logging.getLogger(__name__)

# 常见 HTTP 端口集合，用于自动判断检查类型
HTTP_PORTS = {80, 443, 8080, 8000, 8001, 8443, 3000, 3001, 5000, 9090,
              8093, 8123, 8848, 13000, 15672, 18000, 18123, 48080, 48848}

# 需要跳过的系统服务（通常不需要监控）
SKIP_PROCESSES = {"sshd", "systemd", "systemd-resolve", "chronyd", "dbus-daemon",
                  "polkitd", "agetty", "containerd", "dockerd", "docker-proxy",
                  "rpcbind", "nscd", "cupsd"}

# 需要跳过的端口范围
SKIP_PORTS = {22}  # SSH 不需要监控


def discover_docker_services(interval: int = 30) -> List[ServiceCheckConfig]:
    """从运行中的 Docker 容器发现服务。

    解析容器的端口映射，根据端口号自动判断使用 HTTP 或 TCP 检查。

    Args:
        interval: 发现的服务默认检查间隔（秒）。

    Returns:
        服务检查配置列表。
    """
    if not shutil.which("docker"):
        logger.debug("Docker not found, skipping container discovery")
        return []

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(f"docker ps failed: {result.stderr.strip()}")
            return []
    except Exception as e:
        logger.warning(f"Docker discovery error: {e}")
        return []

    services = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            container = json.loads(line)
        except json.JSONDecodeError:
            continue

        name = container.get("Names", "").strip()
        ports_str = container.get("Ports", "")

        if not name or not ports_str:
            continue

        # 解析端口映射，格式如 "0.0.0.0:8001->8000/tcp, ..."
        for mapping in ports_str.split(","):
            mapping = mapping.strip()
            if "->" not in mapping:
                continue
            try:
                host_part, container_part = mapping.split("->")
                if ":" in host_part:
                    host_port = int(host_part.rsplit(":", 1)[1])
                else:
                    continue
                # 跳过 IPv6 重复映射
                if host_part.startswith("[::]:"):
                    continue
            except (ValueError, IndexError):
                continue

            # 根据端口号判断检查类型
            if host_port in HTTP_PORTS:
                svc = ServiceCheckConfig(
                    name=f"{name} (:{host_port})",
                    type="http",
                    url=f"http://localhost:{host_port}",
                    interval=interval,
                )
            else:
                svc = ServiceCheckConfig(
                    name=f"{name} (:{host_port})",
                    type="tcp",
                    host="localhost",
                    port=host_port,
                    interval=interval,
                )
            services.append(svc)

    logger.info(f"Docker discovery: found {len(services)} services from {_count_containers(result.stdout)} containers")
    return services


def _count_containers(stdout: str) -> int:
    """统计 docker ps 输出中的容器数量。"""
    return len([l for l in stdout.strip().splitlines() if l.strip()])


def _get_docker_ports() -> Set[int]:
    """获取 Docker 管理的宿主机端口集合，用于排除。"""
    ports = set()  # type: Set[int]
    if not shutil.which("docker"):
        return ports

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Ports}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return ports
    except Exception:
        return ports

    # 解析端口映射
    for line in result.stdout.strip().splitlines():
        for mapping in line.split(","):
            mapping = mapping.strip()
            if "->" not in mapping:
                continue
            try:
                host_part = mapping.split("->")[0]
                if ":" in host_part:
                    port = int(host_part.rsplit(":", 1)[1])
                    ports.add(port)
            except (ValueError, IndexError):
                continue

    return ports


def discover_host_services(interval: int = 30) -> List[ServiceCheckConfig]:
    """通过 ss 命令发现宿主机上直接运行的服务（非 Docker）。

    解析 ss -tlnp 输出，获取监听端口和进程名，
    过滤掉 Docker 管理的端口和系统服务。

    Args:
        interval: 发现的服务默认检查间隔（秒）。

    Returns:
        服务检查配置列表。
    """
    if not shutil.which("ss"):
        logger.debug("ss command not found, skipping host service discovery")
        return []

    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(f"ss failed: {result.stderr.strip()}")
            return []
    except Exception as e:
        logger.warning(f"Host service discovery error: {e}")
        return []

    # 获取 Docker 占用的端口，需要排除
    docker_ports = _get_docker_ports()
    logger.debug(f"Docker ports to exclude: {docker_ports}")

    services = []
    seen_ports = set()  # type: Set[int]

    for line in result.stdout.strip().splitlines():
        # 跳过表头
        if line.startswith("State") or not line.strip():
            continue

        # 解析 ss 输出
        # 格式: State Recv-Q Send-Q Local_Address:Port Peer_Address:Port Process
        parts = line.split()
        if len(parts) < 5:
            continue

        local_addr = parts[3]  # 如 0.0.0.0:80 或 [::]:80 或 127.0.0.1:6379
        process_info = parts[5] if len(parts) > 5 else ""

        # 提取端口号
        try:
            port = int(local_addr.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue

        # 提取监听地址
        listen_addr = local_addr.rsplit(":", 1)[0]

        # 跳过 IPv6 重复（只保留 IPv4）
        if listen_addr.startswith("[::"):
            continue

        # 跳过已处理的端口
        if port in seen_ports:
            continue
        seen_ports.add(port)

        # 跳过 Docker 管理的端口
        if port in docker_ports:
            continue

        # 跳过系统端口
        if port in SKIP_PORTS:
            continue

        # 跳过仅监听 127.0.0.1 的服务（内部服务，外部不可达）
        if listen_addr == "127.0.0.1":
            continue

        # 提取进程名
        process_name = _extract_process_name(process_info)
        if not process_name:
            continue

        # 跳过系统进程
        if process_name in SKIP_PROCESSES:
            continue

        # 生成友好的服务名
        service_name = f"{process_name} (:{port})"

        # 根据进程名和端口判断检查类型
        if _is_http_service(process_name, port):
            svc = ServiceCheckConfig(
                name=service_name,
                type="http",
                url=f"http://localhost:{port}",
                interval=interval,
            )
        else:
            svc = ServiceCheckConfig(
                name=service_name,
                type="tcp",
                host="localhost",
                port=port,
                interval=interval,
            )
        services.append(svc)

    logger.info(f"Host service discovery: found {len(services)} non-Docker services")
    return services


def _extract_process_name(process_info: str) -> Optional[str]:
    """从 ss 的 Process 列提取进程名。

    格式: users:(("nginx",pid=1234,fd=5),("nginx",pid=1235,fd=5))
    提取第一个进程名。
    """
    match = re.search(r'users:\(\("([^"]+)"', process_info)
    if match:
        return match.group(1)
    return None


def _is_http_service(process_name: str, port: int) -> bool:
    """判断是否为 HTTP 服务。

    根据进程名和端口号综合判断。
    """
    # 已知 HTTP 服务进程
    http_processes = {"nginx", "httpd", "apache2", "caddy", "traefik",
                      "node", "python", "python3", "java", "gunicorn",
                      "uvicorn", "php-fpm"}

    if process_name.lower() in http_processes:
        return True

    # 常见 HTTP 端口
    if port in HTTP_PORTS or port == 80 or port == 443:
        return True

    # 80xx, 90xx 端口段通常是 HTTP
    if 8000 <= port <= 9999:
        return True

    return False


def discover_docker_log_sources() -> List[LogSourceConfig]:
    """从运行中的 Docker 容器发现日志文件路径。

    通过 docker inspect 获取每个容器的 LogPath。

    Returns:
        日志源配置列表。
    """
    if not shutil.which("docker"):
        return []

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except Exception as e:
        logger.warning(f"Docker log discovery error: {e}")
        return []

    sources = []  # type: List[LogSourceConfig]
    for name in result.stdout.strip().splitlines():
        name = name.strip()
        if not name:
            continue
        try:
            insp = subprocess.run(
                ["docker", "inspect", "--format", "{{.LogPath}}", name],
                capture_output=True, text=True, timeout=10,
            )
            log_path = insp.stdout.strip()
            if insp.returncode == 0 and log_path and log_path != "<no value>":
                sources.append(LogSourceConfig(
                    path=log_path,
                    service=name,
                    docker=True,
                ))
        except Exception:
            continue

    logger.info(f"Docker log discovery: found {len(sources)} log sources")
    return sources
