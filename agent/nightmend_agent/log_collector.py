"""
日志采集模块。

实现 tail -f 式的日志文件实时追踪，支持：
- 多行日志合并（如 Java 堆栈跟踪）
- Docker json-log 格式解析
- 文件偏移量持久化（断点续读）
- 日志级别自动检测
- 批量上报与定时刷新
"""
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from nightmend_agent.config import LogSourceConfig

logger = logging.getLogger(__name__)

# 偏移量持久化文件路径
OFFSET_FILE = os.path.expanduser("~/.nightmend/offsets.json")
# 日志级别匹配正则
LEVEL_RE = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\b", re.IGNORECASE)
# 日志级别标准化映射
LEVEL_MAP = {"WARNING": "WARN", "CRITICAL": "FATAL"}


def _detect_level(line: str) -> str:
    """从日志行中检测日志级别，未匹配时默认返回 INFO。"""
    m = LEVEL_RE.search(line)
    if m:
        lvl = m.group(1).upper()
        return LEVEL_MAP.get(lvl, lvl)
    return "INFO"


def load_offsets() -> Dict[str, int]:
    """从磁盘加载日志文件偏移量记录。"""
    try:
        with open(OFFSET_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_offsets(offsets: Dict[str, int]) -> None:
    """将日志文件偏移量记录持久化到磁盘。"""
    p = Path(OFFSET_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(offsets, f)


class LogTailer:
    """单个日志文件的异步 tail -f 实现。

    支持多行合并和 Docker json-log 格式解析。
    """

    def __init__(
        self,
        source: LogSourceConfig,
        host_id: int,
        callback: Callable,
        offsets: Dict[str, int],
    ):
        self.source = source
        self.host_id = host_id
        self.callback = callback        # 日志条目回调函数
        self.offsets = offsets
        self._pending: Optional[Dict] = None  # 多行合并缓冲区
        self._pending_time: float = 0.0

    def _parse_docker_json(self, raw: str) -> Optional[str]:
        """解析 Docker json-log 格式，提取实际日志内容。"""
        try:
            obj = json.loads(raw)
            return obj.get("log", "").rstrip("\n")
        except (json.JSONDecodeError, AttributeError):
            return raw.rstrip("\n")

    def _make_entry(self, message: str) -> Dict:
        """构造标准日志条目字典。"""
        return {
            "host_id": self.host_id,
            "service": self.source.service,
            "source": self.source.path,
            "level": _detect_level(message),
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _flush_pending(self) -> None:
        """刷新多行合并缓冲区，将已缓存的日志条目发送出去。"""
        if self._pending:
            await self.callback(self._pending)
            self._pending = None

    async def _process_line(self, line: str) -> None:
        """处理单行日志，支持 Docker 格式解析和多行合并逻辑。"""
        if self.source.docker:
            line = self._parse_docker_json(line) or ""
            if not line:
                return

        if not self.source.multiline:
            await self.callback(self._make_entry(line))
            return

        # 多行合并：匹配起始模式则刷新上一条并开始新条目
        is_start = bool(re.match(self.source.multiline_pattern, line))
        if is_start:
            await self._flush_pending()
            self._pending = self._make_entry(line)
            self._pending_time = time.monotonic()
        else:
            if self._pending:
                # 追加到当前多行条目
                self._pending["message"] += "\n" + line
            else:
                await self.callback(self._make_entry(line))

    async def run(self) -> None:
        """启动日志追踪主循环。

        从上次偏移量位置（或文件末尾）开始读取，持续追踪新增内容。
        """
        path = self.source.path
        if not os.path.exists(path):
            logger.warning(f"Log file not found: {path}")
            return

        offset = self.offsets.get(path, None)
        try:
            f = open(path, "r", errors="replace")
        except OSError as e:
            logger.warning(f"Cannot open {path}: {e}")
            return

        try:
            if offset is not None:
                f.seek(offset)
            else:
                f.seek(0, 2)  # 无历史偏移时跳到文件末尾

            logger.info(f"Tailing {path} from offset {f.tell()}")
            while True:
                line = f.readline()
                if line:
                    line = line.rstrip("\n")
                    if line:
                        await self._process_line(line)
                    self.offsets[path] = f.tell()
                else:
                    # 无新数据时检查多行超时（2秒未续行则刷新）
                    if self._pending and (time.monotonic() - self._pending_time) > 2.0:
                        await self._flush_pending()
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            await self._flush_pending()
            raise
        finally:
            f.close()


class LogCollector:
    """日志采集管理器。

    管理多个 LogTailer 实例，将日志条目批量缓冲后上报。
    """

    def __init__(self, host_id: int, sources: List[LogSourceConfig], report_fn: Callable):
        self.host_id = host_id
        self.sources = sources
        self.report_fn = report_fn  # 异步上报函数：async fn(logs: list) -> bool
        self.offsets = load_offsets()
        self._buffer: List[Dict] = []
        self._lock = asyncio.Lock()
        self._tasks: List[asyncio.Task] = []

    async def _on_log_entry(self, entry: Dict) -> None:
        """日志条目回调，缓冲满 100 条时自动刷新。"""
        async with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= 100:
                await self._flush()

    async def _flush(self) -> None:
        """刷新缓冲区，批量上报日志（调用方需持有锁）。"""
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        success = await self.report_fn(batch)
        if success:
            save_offsets(self.offsets)

    async def _flush_loop(self) -> None:
        """定时刷新循环，每 5 秒将缓冲区内容上报。"""
        while True:
            await asyncio.sleep(5)
            async with self._lock:
                await self._flush()

    async def start(self) -> List[asyncio.Task]:
        """启动所有日志追踪器和定时刷新任务。"""
        tasks = []
        for src in self.sources:
            tailer = LogTailer(src, self.host_id, self._on_log_entry, self.offsets)
            tasks.append(asyncio.create_task(tailer.run()))
        tasks.append(asyncio.create_task(self._flush_loop()))
        self._tasks = tasks
        logger.info(f"Log collector started: {len(self.sources)} sources")
        return tasks
