"""
数据上报模块。

AgentReporter 是 Agent 的核心调度器，负责：
- 向服务端注册主机和服务
- 周期性上报系统指标、服务检查结果、日志和数据库指标
- 管理心跳、自动发现和所有异步任务的生命周期
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

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

    def _get_local_ip(self) -> str:
        """获取本机主要 IP 地址（保留兼容性）。"""
        network_info = self._get_network_info()
        # 优先返回公网 IP，否则返回内网 IP
        return network_info.get("public_ip") or network_info.get("private_ip") or ""

    def _get_network_info(self) -> dict:
        """获取本机网络接口信息。

        返回格式：
        {
            "private_ip": "10.0.1.123",      # 主要内网 IP
            "public_ip": "54.255.123.45",     # 公网 IP（如果可检测）
            "all_private": ["10.0.1.123"],    # 所有内网 IP
            "all_public": ["54.255.123.45"],  # 所有公网 IP
            "interfaces": {                   # 网卡详细信息
                "eth0": {"ipv4": "10.0.1.123", "type": "private"}
            }
        }
        """
        import socket
        import platform

        result = {
            "private_ip": None,
            "public_ip": None,
            "all_private": [],
            "all_public": [],
            "interfaces": {},
        }

        # 1. 尝试通过外部服务获取公网 IP
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
                        result["all_public"].append(ip)
                        break
            except Exception:
                continue

        # 2. 获取本地网络接口信息
        try:
            # 尝试使用 netifaces 获取详细信息
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
                                if not result["private_ip"]:
                                    result["private_ip"] = ip
                                if ip not in result["all_private"]:
                                    result["all_private"].append(ip)
                            elif ip_type == "public":
                                if ip not in result["all_public"]:
                                    result["all_public"].append(ip)
        except ImportError:
            # netifaces 不可用，使用备用方法
            pass

        # 3. 备用方法：通过 socket 获取主要 IP
        if not result["private_ip"]:
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

    async def _heartbeat_loop(self):
        """心跳循环，每 60 秒发送一次。"""
        while True:
            try:
                await self.heartbeat()
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            await asyncio.sleep(60)

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
        ]
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
            if self._client:
                await self._client.aclose()
