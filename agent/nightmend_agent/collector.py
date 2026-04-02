"""
系统指标采集模块。

使用 psutil 采集 CPU、内存、磁盘、网络等系统指标，
支持网络速率计算和丢包率统计。
兼容 Linux / Windows / macOS。
"""
import logging
import os
import platform
import time
from typing import Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)

# 平台常量 / Platform constant
IS_WINDOWS = platform.system() == "Windows"

# 模块级状态，用于网络速率的差值计算
_prev_net: Optional[dict] = None
_prev_time: Optional[float] = None


def collect_system_info() -> dict:
    """采集静态系统信息（主机名、OS、CPU 核数、总内存等）。"""
    uname = platform.uname()
    mem = psutil.virtual_memory()
    return {
        "hostname": platform.node(),
        "os": uname.system,
        "os_version": uname.release,
        "arch": uname.machine,
        "cpu_cores": psutil.cpu_count(logical=True),
        "memory_total_mb": int(mem.total / (1024 * 1024)),
    }


def collect_metrics() -> dict:
    """采集当前系统运行指标。

    包括 CPU 使用率、负载、内存、磁盘、网络流量及丢包率。
    网络速率通过与上次采集的差值计算得出。
    """
    cpu_percent = psutil.cpu_percent(interval=1)

    try:
        load1, load5, load15 = psutil.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = 0.0

    mem = psutil.virtual_memory()

    # 磁盘 — 主分区指标（Linux: /, Windows: C:\）
    # Disk — primary partition metrics (Linux: /, Windows: C:\)
    try:
        primary_path = "C:\\" if IS_WINDOWS else "/"
        disk = psutil.disk_usage(primary_path)
        disk_used_mb = int(disk.used / (1024 * 1024))
        disk_total_mb = int(disk.total / (1024 * 1024))
        disk_percent = disk.percent
    except Exception:
        disk_used_mb = disk_total_mb = 0
        disk_percent = 0.0

    # 所有分区使用情况 / All partition usage details
    disk_partitions = _collect_disk_partitions()

    # 网络 — 累计计数器 + 速率计算
    global _prev_net, _prev_time
    net = psutil.net_io_counters()
    now = time.monotonic()

    net_send_rate_kb = 0.0
    net_recv_rate_kb = 0.0
    net_packet_loss_rate = 0.0

    # 与上次采集对比，计算每秒发送/接收速率（KB/s）
    if _prev_net is not None and _prev_time is not None:
        dt = now - _prev_time
        if dt > 0:
            net_send_rate_kb = round(max(0.0, (net.bytes_sent - _prev_net["bytes_sent"]) / 1024 / dt), 2)
            net_recv_rate_kb = round(max(0.0, (net.bytes_recv - _prev_net["bytes_recv"]) / 1024 / dt), 2)

    # 丢包率：丢弃包数 / 总包数（百分比）
    total_in = net.packets_recv + net.dropin
    total_out = net.packets_sent + net.dropout
    total_packets = total_in + total_out
    if total_packets > 0:
        net_packet_loss_rate = round((net.dropin + net.dropout) / total_packets * 100, 4)

    # 保存本次采集数据，供下次计算差值
    _prev_net = {
        "bytes_sent": net.bytes_sent,
        "bytes_recv": net.bytes_recv,
    }
    _prev_time = now

    return {
        "cpu_percent": round(cpu_percent, 1),
        "cpu_load_1": round(load1, 2),
        "cpu_load_5": round(load5, 2),
        "cpu_load_15": round(load15, 2),
        "memory_used_mb": int(mem.used / (1024 * 1024)),
        "memory_percent": round(mem.percent, 1),
        "disk_used_mb": disk_used_mb,
        "disk_total_mb": disk_total_mb,
        "disk_percent": round(disk_percent, 1),
        "disk_partitions": disk_partitions,
        "net_bytes_sent": net.bytes_sent,
        "net_bytes_recv": net.bytes_recv,
        "net_send_rate_kb": net_send_rate_kb,
        "net_recv_rate_kb": net_recv_rate_kb,
        "net_packet_loss_rate": net_packet_loss_rate,
    }


def collect_agent_process_metrics() -> dict:
    """采集当前 Agent 进程自身的资源占用。"""
    try:
        proc = psutil.Process(os.getpid())
        with proc.oneshot():
            mem = proc.memory_info()
            try:
                cpu_percent = proc.cpu_percent(interval=None)
            except Exception:
                cpu_percent = 0.0
            create_time = proc.create_time()
            metrics = {
                "agent_cpu_percent": round(float(cpu_percent), 2),
                "agent_memory_rss_mb": round(mem.rss / (1024 * 1024), 2),
                "agent_thread_count": int(proc.num_threads()),
                "agent_uptime_seconds": max(0, int(time.time() - create_time)),
            }
            try:
                metrics["agent_open_files"] = len(proc.open_files())
            except Exception:
                metrics["agent_open_files"] = None
            return metrics
    except Exception as e:
        logger.warning(f"Failed to collect agent process metrics: {e}")
        return {}


def _collect_disk_partitions() -> List[Dict]:
    """采集所有磁盘分区的使用情况。
    Collect usage details for all mounted disk partitions.

    在 Windows 上遍历 C:\\, D:\\ 等所有盘符；
    在 Linux/macOS 上遍历所有挂载的物理分区。
    On Windows iterates all drive letters (C:\\, D:\\, ...);
    on Linux/macOS iterates all mounted physical partitions.

    Returns:
        分区信息列表，每项包含挂载点、设备、文件系统、已用/总量/百分比。
    """
    partitions = []
    try:
        for part in psutil.disk_partitions(all=False):
            # 跳过只读的虚拟文件系统（如 squashfs snap 挂载）
            # Skip read-only virtual filesystems (e.g. squashfs snap mounts)
            if "squashfs" in part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "mountpoint": part.mountpoint,
                    "device": part.device,
                    "fstype": part.fstype,
                    "total_mb": int(usage.total / (1024 * 1024)),
                    "used_mb": int(usage.used / (1024 * 1024)),
                    "percent": round(usage.percent, 1),
                })
            except (PermissionError, OSError):
                # 某些分区可能无权限访问（如 Windows 恢复分区）
                # Some partitions may be inaccessible (e.g. Windows recovery partitions)
                continue
    except Exception as e:
        logger.warning(f"Failed to collect disk partitions: {e}")
    return partitions
