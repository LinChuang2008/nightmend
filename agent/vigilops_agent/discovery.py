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

from vigilops_agent.config import DatabaseMonitorConfig, LogSourceConfig, ServiceCheckConfig

logger = logging.getLogger(__name__)

# 常见 HTTP 端口集合，用于自动判断检查类型
HTTP_PORTS = {80, 443, 8080, 8000, 8001, 8443, 3000, 3001, 5000, 9090,
              8093, 8123, 8848, 13000, 15672, 18000, 18123, 48080, 48848}

# 需要跳过的系统服务（通常不需要监控）
SKIP_PROCESSES = {"sshd", "systemd", "systemd-resolve", "chronyd", "dbus-daemon",
                  "polkitd", "agetty", "containerd", "dockerd", "docker-proxy",
                  "rpcbind", "nscd", "cupsd",
                  "prlshprint", "prl_nettool", "prl_disp_service", "prltoolsd",
                  "sh", "sed", "awk", "grep", "cat", "sleep"}  # 常见工具进程，非真正服务

# 需要跳过的端口范围
SKIP_PORTS = {22, 30631}  # SSH、Parallels shared printing 不需要监控


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


def discover_stopped_docker_services(interval: int = 30) -> List[ServiceCheckConfig]:
    """从已停止的 Docker 容器发现服务（用于检测容器宕机）。

    使用 docker ps -a --filter status=exited 获取已停止容器的端口配置，
    通过 docker inspect 获取端口映射信息。

    Returns:
        已停止容器对应的服务配置列表（用于注册并标记为 down）。
    """
    if not shutil.which("docker"):
        return []

    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "status=exited", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except Exception:
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
        if not name:
            continue

        # 已停止容器的 Ports 字段可能为空，需要通过 docker inspect 获取端口映射
        try:
            inspect_result = subprocess.run(
                ["docker", "inspect", name, "--format", "{{json .HostConfig.PortBindings}}"],
                capture_output=True, text=True, timeout=5,
            )
            if inspect_result.returncode != 0:
                continue
            port_bindings = json.loads(inspect_result.stdout.strip())
            if not port_bindings:
                continue
        except Exception:
            continue

        for container_port, bindings in port_bindings.items():
            if not bindings:
                continue
            for binding in bindings:
                host_port_str = binding.get("HostPort", "")
                if not host_port_str:
                    continue
                try:
                    host_port = int(host_port_str)
                except ValueError:
                    continue

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

    if services:
        logger.info(f"Stopped Docker discovery: found {len(services)} services from stopped containers")
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

        # 注意：不再跳过监听在 127.0.0.1 的服务
        # VigilOps agent 运行在本地，可以通过 127.0.0.1 访问本地服务
        # 很多服务（数据库、缓存等）默认监听 127.0.0.1，这是正常的

        # 提取进程名
        process_name = _extract_process_name(process_info)
        if not process_name:
            continue

        # 跳过系统进程
        if process_name in SKIP_PROCESSES:
            continue

        # 确定用于健康检查的地址
        # - 0.0.0.0 表示监听所有接口，使用 localhost 连接
        # - 127.0.0.1 表示仅本地监听，使用 localhost 连接
        # - 其他IP（如10.0.49.101）表示仅监听该IP，必须使用该IP连接
        if listen_addr == "0.0.0.0" or listen_addr == "127.0.0.1":
            check_host = "localhost"
        else:
            check_host = listen_addr

        # 生成友好的服务名
        service_name = f"{process_name} (:{port})"

        # 根据进程名和端口判断检查类型
        if _is_http_service(process_name, port):
            svc = ServiceCheckConfig(
                name=service_name,
                type="http",
                url=f"http://{check_host}:{port}",
                interval=interval,
            )
        else:
            svc = ServiceCheckConfig(
                name=service_name,
                type="tcp",
                host=check_host,
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


# Docker 镜像名 → 数据库类型映射
_DB_IMAGE_MAP = {
    "mysql": "mysql",
    "mariadb": "mysql",
    "postgres": "postgres",
    "redis": "redis",
    "mongo": "mongodb",
    "oracle": "oracle",
}

# 数据库类型 → 常见环境变量中的密码字段名
_DB_PASSWORD_ENVS = {
    "mysql": ["MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD"],
    "postgres": ["POSTGRES_PASSWORD"],
    "redis": ["REDIS_PASSWORD", "REQUIREPASS"],
    "mongodb": ["MONGO_INITDB_ROOT_PASSWORD"],
    "oracle": ["ORACLE_PWD", "ORACLE_PASSWORD"],
}

# 数据库类型 → 用户名环境变量
_DB_USER_ENVS = {
    "mysql": ["MYSQL_USER"],
    "postgres": ["POSTGRES_USER"],
    "mongodb": ["MONGO_INITDB_ROOT_USERNAME"],
}

# 数据库类型 → 默认用户名
_DB_DEFAULT_USER = {
    "mysql": "root",
    "postgres": "postgres",
    "redis": "",
    "mongodb": "admin",
    "oracle": "system",
}

# 数据库类型 → 数据库名环境变量
_DB_NAME_ENVS = {
    "mysql": ["MYSQL_DATABASE"],
    "postgres": ["POSTGRES_DB"],
}

# 数据库类型 → 容器内默认端口
_DB_DEFAULT_PORTS = {
    "mysql": 3306,
    "postgres": 5432,
    "redis": 6379,
    "mongodb": 27017,
    "oracle": 1521,
}


def discover_docker_databases(interval: int = 60) -> List[DatabaseMonitorConfig]:
    """从运行中的 Docker 容器自动发现数据库实例。

    通过容器镜像名识别数据库类型，从环境变量提取连接凭据，
    从端口映射获取宿主机端口。

    Args:
        interval: 指标采集间隔（秒）。

    Returns:
        数据库监控配置列表。
    """
    if not shutil.which("docker"):
        return []

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except Exception as e:
        logger.warning(f"Docker DB discovery error: {e}")
        return []

    databases = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            container = json.loads(line)
        except json.JSONDecodeError:
            continue

        name = container.get("Names", "").strip()
        image = container.get("Image", "").strip().lower()
        ports_str = container.get("Ports", "")

        if not name or not image:
            continue

        # 通过镜像名匹配数据库类型
        db_type = None
        for img_key, dtype in _DB_IMAGE_MAP.items():
            if img_key in image.split(":")[0]:
                db_type = dtype
                break

        if not db_type:
            continue

        # 提取宿主机映射端口
        default_port = _DB_DEFAULT_PORTS.get(db_type, 0)
        host_port = default_port  # 回退到默认端口
        for mapping in ports_str.split(","):
            mapping = mapping.strip()
            if "->" not in mapping:
                continue
            try:
                host_part, container_part = mapping.split("->")
                container_port = int(container_part.split("/")[0])
                if container_port == default_port and ":" in host_part:
                    # 跳过 IPv6 映射
                    if host_part.startswith("[::]:"):
                        continue
                    host_port = int(host_part.rsplit(":", 1)[1])
                    break
            except (ValueError, IndexError):
                continue

        # 通过 docker inspect 获取环境变量
        env_vars = _get_container_env(name)
        if env_vars is None:
            continue

        # 提取密码
        password = ""
        for env_key in _DB_PASSWORD_ENVS.get(db_type, []):
            if env_key in env_vars:
                password = env_vars[env_key]
                break

        # Redis 不需要密码即可监控基本指标，其他数据库没密码则跳过
        if not password and db_type not in ("redis",):
            logger.debug(f"Skipping {name}: no password found in container env")
            continue

        # 提取用户名
        username = _DB_DEFAULT_USER.get(db_type, "")
        for env_key in _DB_USER_ENVS.get(db_type, []):
            if env_key in env_vars:
                username = env_vars[env_key]
                break

        # 提取数据库名
        database = ""
        for env_key in _DB_NAME_ENVS.get(db_type, []):
            if env_key in env_vars:
                database = env_vars[env_key]
                break

        db_config = DatabaseMonitorConfig(
            name=f"{name}",
            type=db_type,
            host="127.0.0.1",
            port=host_port,
            database=database,
            username=username,
            password=password,
            interval=interval,
        )
        databases.append(db_config)
        logger.info(f"Docker DB discovery: found {db_type} in container '{name}' on port {host_port}")

    if databases:
        logger.info(f"Docker DB discovery: found {len(databases)} database(s)")
    return databases


def _get_container_env(container_name: str) -> Optional[dict]:
    """获取 Docker 容器的环境变量。"""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format",
             '{{range .Config.Env}}{{println .}}{{end}}', container_name],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
    except Exception:
        return None

    env = {}
    for line in result.stdout.strip().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            env[key] = value
    return env


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
