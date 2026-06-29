"""
统一安全层 — 合并 ops_agent_loop + remediation/safety.py 的命令验证

SafetyChecker 是 facade 类，封装：
- 命令黑名单检查（合并两套 pattern）
- 命令白名单检查（来自 remediation/safety.py）
- Redis-backed RateLimiter（持久化、分布式安全）
- Redis-backed CircuitBreaker（持久化、分布式安全）
"""
from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger(__name__)

# ─── 合并后的危险命令黑名单 ──────────────────────────────────────────────────
# 来源 1: ops_agent_loop.py._DANGEROUS_COMMAND_PATTERNS
# 来源 2: remediation/safety.py.FORBIDDEN_PATTERNS
# 取两者并集，去重

FORBIDDEN_PATTERNS: list[str] = [
    # 破坏性文件系统操作
    r"rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+|-[a-zA-Z]*f[a-zA-Z]*\s+)*-[a-zA-Z]*r[a-zA-Z]*\s+/",
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|-[a-zA-Z]*r[a-zA-Z]*\s+)*-[a-zA-Z]*f[a-zA-Z]*\s+/",
    r"rm\s+-rf\s+/\*",
    r"rm\s+-rf\s+~",
    r"mkfs\.",
    r"dd\s+.*of=/dev/[sh]d",
    r"dd\s+if=",
    r">\s*/dev/[sh]d",

    # sudo 包装的破坏性命令
    r"sudo\s+rm\s",
    r"sudo\s+shutdown",
    r"sudo\s+reboot",
    r"sudo\s+mkfs",
    r"sudo\s+dd\s",

    # 权限提升操作
    r"chmod\s+.*777\s+/",
    r"chown\s+.*root\s+/",
    r"passwd\s",
    r"useradd\s",
    r"userdel\s",
    r"visudo",

    # 网络渗透行为
    r"curl\s+.*\|\s*(sh|bash|zsh|python|perl)",
    r"wget\s+.*\|\s*(sh|bash|zsh|python|perl)",
    r"\beval\s*\(",
    r"\$\(curl\s",
    r"\$\(wget\s",

    # 危险系统命令
    r"shutdown\s",
    r"\breboot\b",
    r"init\s+[06]",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r"systemctl\s+(disable|mask)\s",
    r"iptables\s+-F",
    r"iptables\s+-X",

    # 数据销毁操作
    r"DROP\s+DATABASE",
    r"DROP\s+TABLE",
    r"TRUNCATE\s+TABLE",
    r"DELETE\s+FROM\s+\S+\s*;?\s*$",

    # 挖矿和恶意软件
    r"xmrig",
    r"minerd",
    r"cryptonight",

    # 反弹 Shell
    r"bash\s+-i\s+>&\s*/dev/tcp",
    r"nc\s+.*-e\s+(sh|bash)",
    r"python.*socket.*connect",

    # Fork bomb（来自 ops_agent_loop）
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;",
]

_FORBIDDEN_RE = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]

# 安全命令白名单（来自 remediation/safety.py）
ALLOWED_COMMAND_PREFIXES: list[str] = [
    "df", "du", "find", "ls", "cat", "head", "tail", "grep", "wc",
    "stat", "file", "readlink", "basename", "dirname",
    "cp ", "mv ", "mkdir ", "touch ",
    "systemctl restart", "systemctl start", "systemctl stop", "systemctl status",
    "systemctl is-active", "systemctl reload", "systemctl show",
    "systemctl list-units", "systemctl daemon-reload",
    "service ", "journalctl",
    "kill", "pkill", "pgrep",
    "free", "top", "ps", "vmstat", "iostat", "uptime", "w ", "who",
    "uname", "hostname", "date", "timedatectl",
    "sar", "mpstat", "pidstat", "nproc",
    "logrotate", "truncate",
    "ss", "netstat", "lsof", "ping", "traceroute", "tracepath",
    "dig", "nslookup", "host ", "ip ", "ifconfig",
    "curl ", "wget ",
    "sync", "echo", "sleep", "test ", "true", "false",
    "sort", "uniq", "awk", "sed", "cut", "tr ", "xargs",
    "tee ", "which", "whereis", "type ",
    "apt-get update", "apt-get clean", "apt-get install", "apt-get remove",
    "apt clean", "apt list", "apt show", "apt install", "apt remove",
    "yum list", "yum info", "yum check-update", "yum install", "yum remove",
    "dnf list", "dnf info", "dnf check-update", "dnf install", "dnf remove",
    "pip install", "pip list", "pip show",
    "npm ", "npx ",
    "docker restart", "docker stop", "docker start", "docker ps", "docker logs",
    "docker inspect", "docker stats", "docker top",
    "docker exec ", "docker compose", "docker-compose",
    "docker images", "docker pull", "docker info", "docker version",
    "crictl ps", "crictl logs", "crictl inspect",
    "kubectl get ", "kubectl describe ", "kubectl logs ", "kubectl top ",
    "mysql", "mysqladmin", "mysqldump",
    "psql", "pg_dump", "pg_isready",
    "redis-cli", "mongosh", "mongo ",
    "nginx -t", "nginx -s", "nginx -T",
    "apachectl", "httpd -t",
    "sysctl",
    "lscpu", "lsmem", "lsblk", "lspci", "lsusb",
    "dmidecode", "hdparm", "dmesg",
    "tar ", "gzip", "gunzip", "zip", "unzip",
    "crontab -l",
    "last", "lastlog", "faillog",
]


def check_command_safety(cmd: str) -> tuple[bool, str]:
    """统一命令安全性检查（黑名单 + 白名单）。"""
    cmd_stripped = cmd.strip()
    if not cmd_stripped:
        return False, "Empty command"

    for pattern in _FORBIDDEN_RE:
        if pattern.search(cmd_stripped):
            return False, f"Matches forbidden pattern: {pattern.pattern}"

    cmd_lower = cmd_stripped.lower()
    allowed = any(cmd_lower.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES)
    if not allowed:
        first_word = cmd_stripped.split()[0] if cmd_stripped.split() else cmd_stripped
        return False, f"Command not in allowed prefix list: {first_word}"

    return True, "OK"


# ─── Redis-backed RateLimiter ─────────────────────────────────────────────────

class RateLimiter:
    """Redis-backed 频率限制器，持久化 + 分布式安全。"""

    REDIS_PREFIX = "nightmend:ratelimit:"

    def __init__(self, redis=None) -> None:
        self._redis = redis

    async def can_execute(self, host: str, runbook_name: str, cooldown_seconds: int) -> bool:
        if not self._redis:
            return True  # 无 Redis 时不限流
        key = f"{self.REDIS_PREFIX}{host}:{runbook_name}"
        last = await self._redis.get(key)
        if last is not None:
            elapsed = time.time() - float(last)
            if elapsed < cooldown_seconds:
                return False
        return True

    async def record_execution(self, host: str, runbook_name: str) -> None:
        if not self._redis:
            return
        key = f"{self.REDIS_PREFIX}{host}:{runbook_name}"
        await self._redis.set(key, str(time.time()), ex=7200)  # 2h TTL

        # 同时记录到主机维度的 sorted set（用于 recent_count）
        host_key = f"{self.REDIS_PREFIX}host:{host}"
        await self._redis.zadd(host_key, {f"{runbook_name}:{time.time()}": time.time()})
        await self._redis.expire(host_key, 7200)

    async def recent_count(self, host: str, window_seconds: int = 3600) -> int:
        if not self._redis:
            return 0
        host_key = f"{self.REDIS_PREFIX}host:{host}"
        cutoff = time.time() - window_seconds
        # 删除过期记录
        await self._redis.zremrangebyscore(host_key, "-inf", cutoff)
        return await self._redis.zcard(host_key)


# ─── Redis-backed CircuitBreaker ──────────────────────────────────────────────

class CircuitBreaker:
    """Redis-backed 熔断器，持久化 + 分布式安全。"""

    REDIS_PREFIX = "nightmend:circuitbreaker:"
    DEFAULT_MAX_FAILURES = 3
    DEFAULT_WINDOW_SECONDS = 1800  # 30 分钟

    def __init__(
        self,
        redis=None,
        max_failures: int = DEFAULT_MAX_FAILURES,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._redis = redis
        self.max_failures = max_failures
        self.window_seconds = window_seconds

    async def is_open(self, host: str) -> bool:
        if not self._redis:
            return False  # 无 Redis 时不熔断
        key = f"{self.REDIS_PREFIX}{host}"
        cutoff = time.time() - self.window_seconds
        await self._redis.zremrangebyscore(key, "-inf", cutoff)
        count = await self._redis.zcard(key)
        return count >= self.max_failures

    async def record_failure(self, host: str) -> None:
        if not self._redis:
            return
        key = f"{self.REDIS_PREFIX}{host}"
        now = time.time()
        await self._redis.zadd(key, {str(now): now})
        await self._redis.expire(key, self.window_seconds + 60)

    async def record_success(self, host: str) -> None:
        if not self._redis:
            return
        key = f"{self.REDIS_PREFIX}{host}"
        await self._redis.delete(key)


# ─── SafetyChecker Facade ─────────────────────────────────────────────────────

class SafetyChecker:
    """统一安全层 facade，封装命令检查 + 限流 + 熔断。"""

    def __init__(self, redis=None) -> None:
        self.rate_limiter = RateLimiter(redis=redis)
        self.circuit_breaker = CircuitBreaker(redis=redis)

    def is_dangerous(self, command: str) -> bool:
        """快速检查命令是否危险（仅黑名单，不含白名单）。"""
        cmd_stripped = command.strip()
        if not cmd_stripped:
            return True
        for pattern in _FORBIDDEN_RE:
            if pattern.search(cmd_stripped):
                return True
        return False

    def check_command(self, command: str) -> tuple[bool, str]:
        """完整安全检查（黑名单 + 白名单）。"""
        return check_command_safety(command)
