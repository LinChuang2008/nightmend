"""
数据上报模块。

AgentReporter 是 Agent 的核心调度器，负责：
- 向服务端注册主机和服务
- 周期性上报系统指标、服务检查结果、日志和数据库指标
- 管理心跳、自动发现和所有异步任务的生命周期
"""
import asyncio
import logging
import sys
import threading
import time
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone

import ssl

import httpx
import websocket

from vigilops_agent import __version__
from vigilops_agent.collector import collect_system_info, collect_metrics
from vigilops_agent.checker import run_check
from vigilops_agent.config import AgentConfig, ServiceCheckConfig, DatabaseMonitorConfig
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class AgentReporter:
    """Agent 核心上报器，管理注册、心跳、指标采集和上报的全生命周期。"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.host_id: Optional[int] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._service_ids: Dict[str, int] = {}  # 服务名 -> 服务端分配的 service_id
        self._manual_service_names: set = set()  # 手动配置的服务名（不参与自动移除检测）
        # WebSocket 相关字段
        self._ws: Optional[websocket.WebSocket] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_connected: bool = False
        self._update_received: bool = False

    def _headers(self) -> dict:
        """构造 API 请求认证头。"""
        return {"Authorization": f"Bearer {self.config.server.token}"}

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端（惰性初始化）。"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.server.url,
                headers=self._headers(),
                timeout=30,
            )
        return self._client

    def _connect_websocket(self):
        """
        WebSocket 永久重连循环。
        连接断开后自动重试，指数退避（5s → 10s → 20s → ... 最大 60s）。
        无论是服务端重启、网络抖动还是容器重建，都能自动恢复。
        """
        ws_url = self.config.server.url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = ws_url.rstrip("/") + f"/api/v1/agent/ws/{self.host_id}"
        retry_delay = 5
        max_delay = 60
        ping_interval = 15

        while True:  # 永久重连循环
            try:
                logger.info(f"Attempting to connect WebSocket: {ws_url}")
                sslopt = {"cert_reqs": ssl.CERT_REQUIRED} if ws_url.startswith("wss://") else {}
                ws = websocket.create_connection(
                    ws_url,
                    timeout=10,
                    header={"Authorization": f"Bearer {self.config.server.token}"},
                    sslopt=sslopt,
                )
                self._ws = ws
                self._ws_connected = True
                retry_delay = 5  # 连接成功后重置退避时间
                logger.info("WebSocket connected")

                # ---- 消息收发循环 ----
                last_ping = time.time()
                while True:
                    try:
                        ws.settimeout(1.0)
                        try:
                            result = ws.recv()
                            if result:
                                try:
                                    msg = json.loads(result)
                                    if msg.get("type") == "update":
                                        logger.info(f"Received update notification: {msg.get('action')}")
                                        self._update_received = True
                                        self._do_update()
                                    elif msg.get("type") == "ping":
                                        ws.send(json.dumps({"type": "pong"}))
                                    elif msg.get("type") == "exec_command":
                                        # 在独立线程中执行命令，不阻塞 WebSocket 接收循环
                                        threading.Thread(
                                            target=self._execute_command,
                                            args=(ws, msg),
                                            daemon=True,
                                            name=f"CmdExec-{msg.get('request_id', 'x')[:8]}",
                                        ).start()
                                except json.JSONDecodeError:
                                    pass
                        except websocket.WebSocketTimeoutException:
                            pass  # 正常超时，继续检查心跳

                        # 定期发送心跳
                        if time.time() - last_ping >= ping_interval:
                            ws.send(json.dumps({"type": "ping"}))
                            last_ping = time.time()

                    except (websocket.WebSocketConnectionClosedException,
                            websocket.WebSocketException,
                            OSError) as e:
                        logger.warning(f"WebSocket disconnected: {e}")
                        break  # 跳出内层循环，触发重连

            except Exception as e:
                logger.warning(f"WebSocket connection failed: {e}, retry in {retry_delay}s")

            # 连接断开或失败，清理状态后等待重连
            self._ws_connected = False
            self._ws = None
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)  # 指数退避

    def _do_update(self):
        """执行更新操作：从后端下载 wheel 包并安装。 """
        logger.info("Starting agent self-update from server...")

        try:
            # 1. 获取最新版本信息
            server_url = self.config.server.url.rstrip("/")
            versions_url = f"{server_url}/api/v1/agent-updates/list"

            req = urllib.request.Request(versions_url)
            req.add_header("Authorization", f"Bearer {self.config.server.token}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                versions_data = json.loads(resp.read().decode())

            if not versions_data.get("versions"):
                logger.warning("No versions available from server")
                return

            # 获取最新版本
            latest_version = versions_data["versions"][0]["version"]
            wheel_file = versions_data["versions"][0]["wheel_files"][0]
            logger.info(f"Latest version available: {latest_version}")

            # 版本比较：已是最新版则跳过，避免无限重启循环
            if latest_version == __version__:
                logger.info(f"Already at latest version {__version__}, skipping update")
                return

            # 2. 下载 wheel 包
            download_url = f"{server_url}/api/v1/agent-updates/download/{latest_version}/{wheel_file}"
            logger.info(f"Downloading wheel package from: {download_url}")

            # 创建临时文件
            temp_dir = tempfile.mkdtemp()
            wheel_path = os.path.join(temp_dir, wheel_file)

            req = urllib.request.Request(download_url)
            req.add_header("Authorization", f"Bearer {self.config.server.token}")
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(wheel_path, "wb") as f:
                    f.write(resp.read())

            logger.info(f"Downloaded wheel package to: {wheel_path}")

            # 3. 安装 wheel 包
            # 优先使用当前 Python 解释器对应的 pip，确保装到正确的 venv
            python_path = sys.executable
            pip_path = os.path.join(os.path.dirname(python_path), "pip")
            if not os.path.exists(pip_path):
                pip_path = shutil.which("pip") or "pip3"
            logger.info(f"Installing wheel package with {pip_path} (python: {python_path})...")

            result = subprocess.run(
                [python_path, "-m", "pip", "install", "--upgrade", wheel_path],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"Pip install failed: {result.stderr}")
                return

            logger.info(f"Package installed successfully: {result.stdout}")

            # 4. 清理临时文件
            os.remove(wheel_path)
            os.rmdir(temp_dir)

            # 5. 重启服务（跨平台）
            # 使用 os._exit 而非 sys.exit，避免在 WebSocket 线程中触发 asyncio 清理报错
            import platform
            system = platform.system()
            if system == "Windows":
                # 检查 Windows 服务是否存在且运行中
                svc_check = subprocess.run(
                    ["sc", "query", "VigilOpsAgent"],
                    capture_output=True, text=True
                )
                if svc_check.returncode == 0 and "RUNNING" in svc_check.stdout:
                    logger.info("Triggering agent service restart via sc...")
                    subprocess.Popen(["sc", "stop", "VigilOpsAgent"])
                    import time as _time
                    _time.sleep(2)
                    subprocess.Popen(["sc", "start", "VigilOpsAgent"])
                else:
                    # 命令行模式：重启当前进程
                    logger.info("Not running as Windows service, restarting process...")
                    subprocess.Popen([sys.executable, "-m", "vigilops_agent.cli", "run"],
                                     creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                logger.info("Triggering agent service restart via systemctl...")
                subprocess.run(
                    ["systemctl", "restart", "vigilops-agent"],
                    capture_output=True,
                    timeout=10
                )
            logger.info("Restart command sent, exiting current process...")
            os._exit(0)

        except Exception as e:
            logger.error(f"Update failed: {e}")

    def _execute_command(self, ws, msg: dict):
        """
        执行后端下发的诊断命令，流式回传输出。

        msg 格式：
        {
            "type": "exec_command",
            "request_id": "uuid",
            "command": "...",
            "timeout": 120
        }
        """
        import queue
        import subprocess
        import time as _time

        request_id = msg.get("request_id", "")
        command = msg.get("command", "")
        timeout = msg.get("timeout", 120)

        # 安全: 命令白名单验证，只允许诊断类命令
        ALLOWED_COMMAND_PREFIXES = [
            "df ", "free ", "top ", "ps ", "uptime", "cat /proc/", "cat /etc/os-release",
            "systemctl status ", "systemctl is-active ", "journalctl ",
            "docker ps", "docker stats", "docker logs ", "docker inspect ",
            "netstat ", "ss ", "ip ", "ping ", "traceroute ", "dig ", "nslookup ",
            "du ", "ls ", "find ", "head ", "tail ", "wc ", "grep ",
            "mysql --version", "redis-cli info", "redis-cli ping",
            "nginx -t", "nginx -T", "curl ", "wget ",
            "vmstat", "iostat", "sar ", "lsof ", "who", "w ", "last ",
            "uname ", "hostname", "date", "timedatectl",
        ]

        def _send(payload: dict):
            try:
                ws.send(json.dumps(payload))
            except Exception as e:
                logger.warning(f"Failed to send command output: {e}")

        # 安全检查: 验证命令是否在白名单中
        cmd_stripped = command.strip()
        is_allowed = any(cmd_stripped.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES)
        if not is_allowed:
            logger.warning(f"Command rejected (not in whitelist) [request_id={request_id}]: {command[:100]}")
            _send({"type": "command_done", "request_id": request_id,
                   "exit_code": -1, "stdout": "", "stderr": f"Command rejected: not in allowed command whitelist",
                   "timed_out": False})
            return

        # 安全: 检查命令注入特殊字符
        DANGEROUS_CHARS = [';', '&&', '||', '|', '`', '$(', '${', '\n', '\r']
        for char in DANGEROUS_CHARS:
            if char in command:
                logger.warning(f"Command rejected (dangerous chars) [request_id={request_id}]: {command[:100]}")
                _send({"type": "command_done", "request_id": request_id,
                       "exit_code": -1, "stdout": "", "stderr": f"Command rejected: contains dangerous characters",
                       "timed_out": False})
                return

        logger.info(f"Executing command [request_id={request_id}]: {command[:100]}")
        start_time = _time.time()

        try:
            import shlex
            proc = subprocess.Popen(
                shlex.split(command),
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            output_q: queue.Queue[tuple[str, str]] = queue.Queue()
            stdout_acc: list[str] = []
            stderr_acc: list[str] = []

            def _reader(stream_name: str, stream_obj):
                try:
                    for line in iter(stream_obj.readline, ""):
                        output_q.put((stream_name, line))
                finally:
                    try:
                        stream_obj.close()
                    except Exception:
                        pass

            stdout_thread = threading.Thread(
                target=_reader,
                args=("stdout", proc.stdout),
                daemon=True,
                name=f"CmdStdout-{request_id[:8]}",
            )
            stderr_thread = threading.Thread(
                target=_reader,
                args=("stderr", proc.stderr),
                daemon=True,
                name=f"CmdStderr-{request_id[:8]}",
            )
            stdout_thread.start()
            stderr_thread.start()

            timed_out = False
            while True:
                # 优先消费实时输出
                try:
                    stream_name, line = output_q.get(timeout=0.2)
                    if stream_name == "stdout":
                        stdout_acc.append(line)
                        _send({"type": "command_output", "request_id": request_id,
                               "stdout": line, "stderr": ""})
                    else:
                        stderr_acc.append(line)
                        _send({"type": "command_output", "request_id": request_id,
                               "stdout": "", "stderr": line})
                except queue.Empty:
                    pass

                # 超时独立判定，不依赖是否有输出
                if _time.time() - start_time > timeout:
                    timed_out = True
                    proc.kill()
                    break

                # 进程退出且队列已清空后结束
                if proc.poll() is not None and output_q.empty():
                    break

            proc.wait()
            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)

            # 最后再清空一次队列，避免尾部日志丢失
            while True:
                try:
                    stream_name, line = output_q.get_nowait()
                    if stream_name == "stdout":
                        stdout_acc.append(line)
                        _send({"type": "command_output", "request_id": request_id,
                               "stdout": line, "stderr": ""})
                    else:
                        stderr_acc.append(line)
                        _send({"type": "command_output", "request_id": request_id,
                               "stdout": "", "stderr": line})
                except queue.Empty:
                    break

            duration_ms = int((_time.time() - start_time) * 1000)
            stderr_output = "".join(stderr_acc)
            stdout_output = "".join(stdout_acc)

            if timed_out:
                if "command timed out" not in stderr_output:
                    stderr_output = (stderr_output + "\ncommand timed out").strip()
                _send({"type": "command_result", "request_id": request_id,
                       "exit_code": -1, "stdout": stdout_output, "stderr": stderr_output,
                       "duration_ms": duration_ms})
                logger.warning(f"Command timeout [request_id={request_id}] after {duration_ms}ms")
                return

            _send({"type": "command_result", "request_id": request_id,
                   "exit_code": proc.returncode,
                   "stdout": stdout_output, "stderr": stderr_output,
                   "duration_ms": duration_ms})
            logger.info(f"Command done [request_id={request_id}] exit_code={proc.returncode} duration={duration_ms}ms")

        except Exception as e:
            logger.error(f"Command execution error [request_id={request_id}]: {e}")
            _send({"type": "command_result", "request_id": request_id,
                   "exit_code": -1, "stdout": "", "stderr": str(e), "duration_ms": 0})

    def _get_local_ip(self) -> str:
        """获取本机主要 IP 地址（保留兼容性）。"""
        network_info = self._get_network_info()
        # 优先返回公网 IP，否则返回内网 IP
        return network_info.get("public_ip") or network_info.get("private_ip") or ""

    def _get_network_info(self) -> dict:
        """获取本机网络接口信息。

        返回格式：
        {
            "private_ip": "10.0.1.123",      # 主要内网 IP（路由可达）
            "public_ip": "54.255.123.45",     # 公网 IP（如果可检测）
            "all_private": ["10.0.1.123"],    # 所有内网 IP
            "all_public": ["54.255.123.45"],  # 所有公网 IP
            "interfaces": {                   # 网卡详细信息
                "eth0": {"ipv4": "10.0.1.123", "type": "private"}
            }
        }
        """
        import socket

        result = {
            "private_ip": None,
            "public_ip": None,
            "all_private": [],
            "all_public": [],
            "interfaces": {},
        }

        # 1. 通过 socket 连接到服务端确定本机实际通信 IP（最可靠）
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.config.server.url)
            host = parsed.hostname or "10.211.55.2"
            port = parsed.port or 80
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((host, port))
                ip = s.getsockname()[0]
            if ip and self._is_valid_ip(ip):
                ip_type = self._classify_ip(ip)
                result["private_ip"] = ip
                result["all_private"].append(ip)
                result["interfaces"]["default"] = {"ipv4": ip, "type": ip_type}
        except Exception:
            pass

        # 2. 获取本地所有网络接口信息（补充，不覆盖 private_ip）
        # 优先使用 psutil.net_if_addrs()（跨平台），如不可用则回退到 netifaces
        # Prefer psutil.net_if_addrs() (cross-platform); fall back to netifaces if unavailable
        interfaces_found = False
        try:
            import psutil as _psutil
            import socket as _socket
            for iface_name, addrs in _psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == _socket.AF_INET:
                        ip = addr.address
                        if ip and self._is_valid_ip(ip):
                            ip_type = self._classify_ip(ip)
                            result["interfaces"][iface_name] = {
                                "ipv4": ip,
                                "type": ip_type
                            }
                            if ip_type == "private":
                                if ip not in result["all_private"]:
                                    result["all_private"].append(ip)
                            elif ip_type == "public":
                                if ip not in result["all_public"]:
                                    result["all_public"].append(ip)
            interfaces_found = True
        except Exception:
            pass

        # 如果 psutil 方式失败，回退到 netifaces（主要用于旧环境兼容）
        # Fall back to netifaces if psutil approach fails (for legacy environment compatibility)
        if not interfaces_found:
            try:
                import netifaces
                for interface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr_info in addrs[netifaces.AF_INET]:
                            ip = addr_info.get('addr')
                            if ip and self._is_valid_ip(ip):
                                ip_type = self._classify_ip(ip)
                                result["interfaces"][interface] = {
                                    "ipv4": ip,
                                    "type": ip_type
                                }
                                if ip_type == "private":
                                    if ip not in result["all_private"]:
                                        result["all_private"].append(ip)
                                elif ip_type == "public":
                                    if ip not in result["all_public"]:
                                        result["all_public"].append(ip)
            except ImportError:
                pass

        # 3. 尝试通过外部服务获取公网 IP
        for url in [
            "https://api.ipify.org",
            "https://ifconfig.me/ip",
            "https://checkip.amazonaws.com",
        ]:
            try:
                import urllib.request
                with urllib.request.urlopen(url, timeout=3) as resp:
                    ip = resp.read().decode().strip()
                    if ip and self._is_valid_public_ip(ip):
                        result["public_ip"] = ip
                        if ip not in result["all_public"]:
                            result["all_public"].append(ip)
                        break
            except Exception:
                continue

        return result

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """验证 IP 地址格式是否有效。"""
        import ipaddress
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_valid_public_ip(ip: str) -> bool:
        """验证是否为有效的公网 IP 地址。"""
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
            # 排除私网地址、本地回环和链路本地地址
            return not addr.is_private and not addr.is_loopback and not addr.is_link_local
        except ValueError:
            return False

    @staticmethod
    def _classify_ip(ip: str) -> str:
        """分类 IP 地址类型。"""
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_loopback:
                return "loopback"
            elif addr.is_link_local:
                return "link_local"
            elif addr.is_private:
                return "private"
            else:
                return "public"
        except ValueError:
            return "unknown"

    async def register(self):
        """向服务端注册本 Agent，获取 host_id。"""
        info = collect_system_info()
        network_info = self._get_network_info()

        payload = {
            "hostname": self.config.host.name or info["hostname"],
            "display_name": self.config.host.display_name or None,
            "ip_address": self.config.host.ip or (network_info.get("public_ip") or network_info.get("private_ip")),
            "private_ip": self.config.host.private_ip or network_info.get("private_ip"),
            "public_ip": self.config.host.public_ip or network_info.get("public_ip"),
            "network_info": network_info if network_info.get("interfaces") else None,
            "os": info["os"],
            "os_version": info["os_version"],
            "arch": info["arch"],
            "cpu_cores": info["cpu_cores"],
            "memory_total_mb": info["memory_total_mb"],
            "agent_version": __version__,
            "tags": {t: True for t in self.config.host.tags} if self.config.host.tags else None,
        }
        client = await self._get_client()
        resp = await client.post("/api/v1/agent/register", json=payload)
        resp.raise_for_status()
        data = resp.json()
        self.host_id = data["host_id"]
        logger.info(f"Registered as host_id={self.host_id} (created={data['created']})")

    async def heartbeat(self):
        """发送心跳保活。"""
        if not self.host_id:
            return
        client = await self._get_client()
        resp = await client.post("/api/v1/agent/heartbeat", json={"host_id": self.host_id})
        resp.raise_for_status()

    async def report_metrics(self):
        """采集并上报系统指标。"""
        if not self.host_id:
            return
        metrics = collect_metrics()
        metrics["host_id"] = self.host_id
        metrics["timestamp"] = datetime.now(timezone.utc).isoformat()
        client = await self._get_client()
        resp = await client.post("/api/v1/agent/metrics", json=metrics)
        resp.raise_for_status()
        logger.debug(f"Metrics reported: cpu={metrics['cpu_percent']}% mem={metrics['memory_percent']}%")

    async def register_services(self):
        """向服务端注册所有配置的服务，获取各服务的 service_id。"""
        client = await self._get_client()
        for svc in self.config.services:
            try:
                payload = {
                    "name": svc.name,
                    "type": svc.type,
                    "target": svc.url or f"{svc.host}:{svc.port}",
                    "host_id": self.host_id,
                    "check_interval": svc.interval,
                    "timeout": svc.timeout,
                }
                resp = await client.post("/api/v1/agent/services/register", json=payload)
                resp.raise_for_status()
                data = resp.json()
                self._service_ids[svc.name] = data["service_id"]
                logger.info(f"Service registered: {svc.name} -> id={data['service_id']}")
            except Exception as e:
                logger.warning(f"Failed to register service {svc.name}: {e}")

    async def report_service_check(self, svc: ServiceCheckConfig, result: dict):
        """上报单个服务的健康检查结果。"""
        service_id = self._service_ids.get(svc.name)
        if not service_id:
            return
        client = await self._get_client()
        payload = {
            "service_id": service_id,
            "status": result["status"],
            "response_time_ms": result["response_time_ms"],
            "status_code": result["status_code"],
            "error": result["error"],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = await client.post("/api/v1/agent/services", json=payload)
        resp.raise_for_status()
        logger.debug(f"Service check reported: {svc.name} = {result['status']}")

    async def report_logs(self, logs: List[Dict]) -> bool:
        """批量上报日志条目。

        Returns:
            上报成功返回 True，失败返回 False。
        """
        if not self.host_id or not logs:
            return False
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/agent/logs", json={"logs": logs})
            resp.raise_for_status()
            logger.debug(f"Reported {len(logs)} log entries")
            return True
        except Exception as e:
            logger.warning(f"Log report failed ({len(logs)} entries): {e}")
            return False

    @staticmethod
    def _sanitize_metrics(d: dict) -> dict:
        """确保指标值可 JSON 序列化（处理 Decimal 等类型）。"""
        from decimal import Decimal
        out = {}
        for k, v in d.items():
            if isinstance(v, Decimal):
                out[k] = float(v)
            else:
                out[k] = v
        return out

    async def report_db_metrics(self, metrics: dict):
        """上报数据库指标。"""
        if not self.host_id:
            return
        metrics = self._sanitize_metrics(metrics)
        metrics["host_id"] = self.host_id
        client = await self._get_client()
        resp = await client.post("/api/v1/agent/db-metrics", json=metrics)
        resp.raise_for_status()
        logger.debug("DB metrics reported: %s", metrics.get("db_name"))

    async def _db_monitor_loop(self, db_config: DatabaseMonitorConfig):
        """数据库指标周期性采集循环。"""
        from vigilops_agent.db_collector import collect_db_metrics
        while True:
            try:
                metrics = collect_db_metrics(db_config)
                if metrics:
                    await self.report_db_metrics(metrics)
            except Exception as e:
                logger.warning("DB monitor failed for %s: %s", db_config.name, e)
            await asyncio.sleep(db_config.interval)

    async def _service_check_loop(self, svc: ServiceCheckConfig):
        """单个服务的周期性健康检查循环。"""
        while True:
            try:
                result = await run_check(svc)
                await self.report_service_check(svc, result)
            except Exception as e:
                logger.warning(f"Service check failed for {svc.name}: {e}")
            await asyncio.sleep(svc.interval)

    async def _discovery_loop(self):
        """周期性重新扫描服务，动态感知新启动的服务并注册监控。"""
        interval = self.config.discovery.interval or 30
        # 首次发现已在 start() 完成，等一个周期再开始循环
        await asyncio.sleep(interval)

        while True:
            try:
                new_services = []
                known_names = {s.name for s in self.config.services}

                # Docker 服务重新发现
                if self.config.discovery.docker:
                    from vigilops_agent.discovery import discover_docker_services
                    for svc in discover_docker_services(interval=interval):
                        if svc.name not in known_names:
                            new_services.append(svc)
                            known_names.add(svc.name)

                # 宿主机服务重新发现
                if self.config.discovery.host_services:
                    from vigilops_agent.discovery import discover_host_services
                    for svc in discover_host_services(interval=interval):
                        if svc.name not in known_names:
                            new_services.append(svc)
                            known_names.add(svc.name)

                if new_services:
                    logger.info(f"Discovery: found {len(new_services)} new service(s), registering...")
                    # 追加到配置列表
                    self.config.services.extend(new_services)
                    # 向服务端注册新服务
                    client = await self._get_client()
                    for svc in new_services:
                        try:
                            payload = {
                                "name": svc.name,
                                "type": svc.type,
                                "target": svc.url or f"{svc.host}:{svc.port}",
                                "host_id": self.host_id,
                                "check_interval": svc.interval,
                                "timeout": svc.timeout,
                            }
                            resp = await client.post("/api/v1/agent/services/register", json=payload)
                            resp.raise_for_status()
                            data = resp.json()
                            self._service_ids[svc.name] = data["service_id"]
                            # 动态启动该服务的检查任务
                            asyncio.create_task(self._service_check_loop(svc))
                            logger.info(f"New service registered and monitoring started: {svc.name}")
                        except Exception as e:
                            logger.warning(f"Failed to register new service {svc.name}: {e}")

            except Exception as e:
                logger.warning(f"Discovery loop error: {e}")

            await asyncio.sleep(interval)

    async def _heartbeat_loop(self):
        """心跳循环，每 60 秒发送一次。"""
        while True:
            try:
                await self.heartbeat()
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            await asyncio.sleep(60)

    async def _discovery_loop(self):
        """周期性服务重新发现循环，每 60 秒扫描新增/移除的服务。"""
        while True:
            await asyncio.sleep(60)
            try:
                newly_discovered = []

                if self.config.discovery.docker:
                    from vigilops_agent.discovery import discover_docker_services, discover_stopped_docker_services
                    discovered = discover_docker_services(interval=self.config.discovery.interval)
                    newly_discovered.extend(discovered)

                    # 检测已停止的容器，注册并标记为 down
                    stopped = discover_stopped_docker_services(interval=self.config.discovery.interval)
                    running_names = {s.name for s in discovered}
                    stopped_new = [s for s in stopped if s.name not in running_names]

                if self.config.discovery.host_services:
                    from vigilops_agent.discovery import discover_host_services
                    host_discovered = discover_host_services(interval=self.config.discovery.interval)
                    newly_discovered.extend(host_discovered)

                # 找出尚未注册的新服务（运行中）
                known_names = {s.name for s in self.config.services}
                new_services = [s for s in newly_discovered if s.name not in known_names]

                if new_services:
                    logger.info(f"Re-discovery found {len(new_services)} new service(s)")
                    for svc in new_services:
                        self.config.services.append(svc)

                    # 注册新服务并启动健康检查
                    client = await self._get_client()
                    for svc in new_services:
                        try:
                            payload = {
                                "name": svc.name,
                                "type": svc.type,
                                "target": svc.url or f"{svc.host}:{svc.port}",
                                "host_id": self.host_id,
                                "check_interval": svc.interval,
                                "timeout": svc.timeout,
                            }
                            resp = await client.post("/api/v1/agent/services/register", json=payload)
                            resp.raise_for_status()
                            data = resp.json()
                            self._service_ids[svc.name] = data["service_id"]
                            logger.info(f"New service registered: {svc.name} -> id={data['service_id']}")
                            asyncio.create_task(self._service_check_loop(svc))
                        except Exception as e:
                            logger.warning(f"Failed to register new service {svc.name}: {e}")

                # 注册已停止容器的服务并上报 down
                if self.config.discovery.docker and stopped_new:
                    client = await self._get_client()
                    for svc in stopped_new:
                        if svc.name in known_names or svc.name in self._service_ids:
                            continue
                        try:
                            payload = {
                                "name": svc.name,
                                "type": svc.type,
                                "target": svc.url or f"{svc.host}:{svc.port}",
                                "host_id": self.host_id,
                                "check_interval": svc.interval,
                                "timeout": svc.timeout,
                            }
                            resp = await client.post("/api/v1/agent/services/register", json=payload)
                            resp.raise_for_status()
                            data = resp.json()
                            self._service_ids[svc.name] = data["service_id"]
                            self.config.services.append(svc)
                            logger.info(f"Stopped container service registered: {svc.name} -> id={data['service_id']}")
                            # 立即上报 down 状态
                            down_payload = {
                                "service_id": data["service_id"],
                                "status": "down",
                                "response_time_ms": 0,
                                "status_code": None,
                                "error": "Docker container is stopped",
                                "checked_at": datetime.now(timezone.utc).isoformat(),
                            }
                            await client.post("/api/v1/agent/services", json=down_payload)
                            logger.warning(f"Service {svc.name} reported as DOWN (container stopped)")
                        except Exception as e:
                            logger.warning(f"Failed to register stopped service {svc.name}: {e}")

                # 检测已消失的服务（运行中→消失）
                current_names = {s.name for s in newly_discovered}
                for svc in list(self.config.services):
                    if svc.name in self._manual_service_names:
                        continue
                    if svc.name not in current_names and svc.name in self._service_ids:
                        logger.warning(f"Service disappeared: {svc.name}")
                        try:
                            client = await self._get_client()
                            payload = {
                                "service_id": self._service_ids[svc.name],
                                "status": "down",
                                "response_time_ms": 0,
                                "status_code": None,
                                "error": "Service no longer detected by auto-discovery",
                                "checked_at": datetime.now(timezone.utc).isoformat(),
                            }
                            await client.post("/api/v1/agent/services", json=payload)
                        except Exception as e:
                            logger.warning(f"Failed to report disappeared service {svc.name}: {e}")

            except Exception as e:
                logger.warning(f"Service re-discovery failed: {e}")

    async def _metrics_loop(self):
        """系统指标采集循环，按配置间隔周期执行。"""
        interval = self.config.metrics.interval
        while True:
            try:
                await self.report_metrics()
            except Exception as e:
                logger.warning(f"Metrics report failed: {e}")
            await asyncio.sleep(interval)

    async def start(self):
        """启动 Agent：注册 → 自动发现 → 启动所有周期性任务。"""
        # 带重试的注册流程（指数退避，最多 10 次）
        for attempt in range(10):
            try:
                await self.register()
                break
            except Exception as e:
                wait = min(2 ** attempt, 60)
                logger.warning(f"Registration failed (attempt {attempt + 1}): {e}. Retry in {wait}s")
                await asyncio.sleep(wait)
        else:
            raise RuntimeError("Failed to register after 10 attempts")

        # 记录手动配置的服务名（不参与自动移除检测）
        self._manual_service_names = {s.name for s in self.config.services}

        # 连接 WebSocket 用于接收更新通知（在后台线程中，不阻塞async事件循环）
        ws_thread = threading.Thread(target=self._connect_websocket, daemon=True, name="WebSocketListener")
        ws_thread.start()
        logger.info("WebSocket connection thread started in background")

        # Docker 容器服务自动发现，与手动配置合并（去重）
        if self.config.discovery.docker:
            from vigilops_agent.discovery import discover_docker_services
            discovered = discover_docker_services(interval=self.config.discovery.interval)
            manual_names = {s.name for s in self.config.services}
            for svc in discovered:
                if svc.name not in manual_names:
                    self.config.services.append(svc)
            if discovered:
                logger.info(f"Auto-discovered {len(discovered)} Docker services, "
                            f"total after merge: {len(self.config.services)}")

        # 宿主机服务自动发现（非 Docker 的监听端口）
        if self.config.discovery.host_services:
            from vigilops_agent.discovery import discover_host_services
            host_discovered = discover_host_services(interval=self.config.discovery.interval)
            manual_names = {s.name for s in self.config.services}
            for svc in host_discovered:
                if svc.name not in manual_names:
                    self.config.services.append(svc)
            if host_discovered:
                logger.info(f"Auto-discovered {len(host_discovered)} host services, "
                            f"total after merge: {len(self.config.services)}")

        # Docker 数据库自动发现，与手动配置合并（去重）
        if self.config.discovery.docker:
            from vigilops_agent.discovery import discover_docker_databases
            db_discovered = discover_docker_databases()
            manual_db_names = {db.name for db in self.config.databases}
            for db in db_discovered:
                if db.name not in manual_db_names:
                    self.config.databases.append(db)
            if db_discovered:
                logger.info(f"Auto-discovered {len(db_discovered)} Docker database(s), "
                            f"total after merge: {len(self.config.databases)}")

        # 注册所有服务到服务端
        if self.config.services:
            await self.register_services()

        # 日志源：手动配置 + Docker 自动发现合并
        log_sources = list(self.config.log_sources)
        if self.config.discovery.docker:
            from vigilops_agent.discovery import discover_docker_log_sources
            docker_logs = discover_docker_log_sources()
            existing_paths = {s.path for s in log_sources}
            for src in docker_logs:
                if src.path not in existing_paths:
                    log_sources.append(src)
            if docker_logs:
                logger.info(f"Auto-discovered {len(docker_logs)} Docker log sources")

        # 启动所有并发任务
        tasks = [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._metrics_loop()),
            asyncio.create_task(self._discovery_loop()),
        ]

        # 启动周期性服务重新发现（动态感知新服务）
        if self.config.discovery.docker or self.config.discovery.host_services:
            tasks.append(asyncio.create_task(self._discovery_loop()))
        for svc in self.config.services:
            if svc.name in self._service_ids:
                tasks.append(asyncio.create_task(self._service_check_loop(svc)))

        # 数据库监控循环
        for db_config in self.config.databases:
            tasks.append(asyncio.create_task(self._db_monitor_loop(db_config)))
        if self.config.databases:
            logger.info("Database monitoring started for %d database(s)", len(self.config.databases))

        # 日志采集
        if log_sources:
            from vigilops_agent.log_collector import LogCollector
            collector = LogCollector(self.host_id, log_sources, self.report_logs)
            log_tasks = await collector.start()
            tasks.extend(log_tasks)

        logger.info("Agent running. Press Ctrl+C to stop.")
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            if self._ws_connected and self._ws:
                self._ws.close()
            if self._client:
                await self._client.aclose()
