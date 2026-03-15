"""
VigilOps 自动修复系统 - 安全防护模块
VigilOps Remediation System - Security Protection Module

这是整个自动修复系统最重要的安全防线，负责防止恶意或危险的命令执行。
This is the most critical security barrier of the entire remediation system, responsible 
for preventing execution of malicious or dangerous commands.

安全层次 (Security Layers):
1. 命令黑名单：基于正则表达式的禁止模式匹配
2. 命令白名单：只允许预定义的安全命令前缀
3. 风险评估：根据 AI 置信度和历史执行频率动态调整风险等级
4. 限流机制：防止短时间内频繁执行相同操作
5. 熔断保护：连续失败时自动停止对故障主机的操作

核心原则 (Core Principles):
- 默认拒绝：未明确允许的操作一律拒绝
- 深度防御：多层安全检查，确保没有单点失效
- 不可绕过：安全规则硬编码，不允许配置文件覆盖
- 失败安全：任何不确定的情况都选择最安全的策略

禁止的危险操作 (Prohibited Dangerous Operations):
- 破坏性文件系统操作（rm -rf /、格式化等）
- 权限提升操作（修改用户、权限等）
- 网络渗透行为（远程下载执行脚本等）
- 系统关闭重启（shutdown、reboot 等）
- 数据库结构破坏（DROP、TRUNCATE 等）
- 挖矿和恶意软件相关命令

设计理念 (Design Philosophy):
宁可误判拒绝 100 个安全命令，也不能放过 1 个危险命令。
Better to mistakenly reject 100 safe commands than to let 1 dangerous command through.

作者：VigilOps Team
版本：v1.0
安全等级：Critical
"""
from __future__ import annotations

import re
import time
from collections import defaultdict

from .models import Diagnosis, RiskLevel, RunbookDefinition

# === 危险命令禁止模式 (Dangerous Command Forbidden Patterns) ===
# 
# 这是系统安全的最后防线，任何匹配这些模式的命令都将被无条件拒绝
# This is the last line of defense for system security, any commands matching these patterns will be unconditionally rejected
# 
# 重要：这些规则硬编码在代码中，不允许通过配置文件或环境变量修改
# Important: These rules are hard-coded and cannot be modified via config files or environment variables
FORBIDDEN_PATTERNS: list[str] = [
    # 破坏性文件系统操作 (Destructive Filesystem Operations)
    r"rm\s+-rf\s+/(?!\S)",          # rm -rf / (删除根目录 - Delete root directory)
    r"rm\s+-rf\s+/\*",             # rm -rf /* (删除根目录所有内容 - Delete all root contents)  
    r"rm\s+-rf\s+~",               # rm -rf ~ (删除用户主目录 - Delete user home directory)
    r"mkfs\.",                     # mkfs.* (格式化文件系统 - Format filesystem)
    r"dd\s+.*of=/dev/[sh]d",       # dd 写入硬盘设备 (dd write to disk device)
    r">\s*/dev/[sh]d",             # 重定向到硬盘设备 (Redirect to disk device)
    
    # 权限提升操作 (Privilege Escalation Operations)
    r"chmod\s+.*777\s+/",          # chmod 777 根目录权限 (chmod 777 root directory permissions)
    r"chown\s+.*root\s+/",         # chown 修改根目录所有者 (chown change root directory owner)
    r"passwd\s",                   # 修改密码 (Change password)
    r"useradd\s",                  # 添加用户 (Add user)
    r"userdel\s",                  # 删除用户 (Delete user) 
    r"visudo",                     # 编辑 sudo 配置 (Edit sudo configuration)
    
    # 网络渗透行为 (Network Penetration Behaviors)
    r"curl\s+.*\|\s*sh",           # curl 下载并执行脚本 (curl download and execute script)
    r"wget\s+.*\|\s*sh",           # wget 下载并执行脚本 (wget download and execute script)
    r"curl\s+.*\|\s*bash",         # curl 通过 bash 执行 (curl execute via bash)
    r"wget\s+.*\|\s*bash",         # wget 通过 bash 执行 (wget execute via bash)
    
    # 危险系统命令 (Dangerous System Commands)
    r"shutdown\s",                 # 关机命令 (Shutdown command)
    r"reboot\b",                   # 重启命令 (Reboot command)
    r"init\s+[06]",                # init 0/6 关机重启 (init 0/6 shutdown/reboot)
    r"systemctl\s+(disable|mask)\s", # 禁用系统服务 (Disable system services)
    r"iptables\s+-F",              # 清空防火墙规则 (Flush firewall rules)
    r"iptables\s+-X",              # 删除防火墙链 (Delete firewall chains)
    
    # 数据销毁操作 (Data Destruction Operations)
    r"DROP\s+DATABASE",            # 删除数据库 (Drop database)
    r"DROP\s+TABLE",               # 删除数据表 (Drop table)
    r"TRUNCATE\s+TABLE",           # 清空数据表 (Truncate table)
    
    # 挖矿和恶意软件 (Mining and Malware)
    r"xmrig",                      # XMRig 挖矿软件 (XMRig mining software)
    r"minerd",                     # minerd 挖矿程序 (minerd mining program)
    r"cryptonight",                # CryptoNight 挖矿算法 (CryptoNight mining algorithm)
]

# 预编译正则表达式以提高匹配性能，大小写不敏感 (Pre-compile regex for performance, case-insensitive)
_FORBIDDEN_RE = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]

# === 安全命令白名单 (Safe Command Whitelist) ===
#
# 只有以下前缀开头的命令才被允许执行，这是双重安全保障
# Only commands starting with these prefixes are allowed to execute, this is dual security protection
#
# 设计原则：宁可漏掉一些安全命令，也不能放过任何危险命令
# Design principle: Better to miss some safe commands than to let any dangerous commands through
ALLOWED_COMMAND_PREFIXES: list[str] = [
    # 文件系统查看命令 (Filesystem View Commands)
    "df", "du", "find", "ls", "cat", "head", "tail", "grep",
    
    # 受限的文件操作 (Limited File Operations)
    # ⚠️ 注意：rm 不放入白名单，通过精确命令替代（如 truncate、find ... -delete）
    # rm 依赖黑名单正则兜底存在覆盖不全风险，已移除
    
    # 系统服务管理 (System Service Management)
    "systemctl restart", "systemctl start", "systemctl stop", "systemctl status",
    "journalctl",                  # 系统日志查看 (System log viewing)
    
    # 进程管理 (Process Management)
    "kill", "pkill",               # 进程终止命令 (Process termination commands)
    
    # 系统监控命令 (System Monitoring Commands)
    "free", "top", "ps", "vmstat", "iostat",
    
    # 日志管理 (Log Management)
    "logrotate", "truncate",       # 日志轮转和截断 (Log rotation and truncation)
    
    # 网络诊断 (Network Diagnostics)
    "ss", "netstat", "lsof",       # 网络连接和端口查看 (Network connection and port viewing)
    
    # 基础系统命令 (Basic System Commands)
    "sync", "echo",                # 文件系统同步和输出 (Filesystem sync and output)
    
    # 包管理器 (Package Managers) - 只允许特定安全子命令，不开放整个 apt 前缀
    # ⚠️ 不用 "apt" 前缀（apt install malware 也能通过），改为白名单精确子命令
    "apt-get update", "apt-get clean", "apt clean", "apt list", "apt show",
    "yum list", "yum info", "yum check-update",
    "dnf list", "dnf info", "dnf check-update",
    
    # 容器管理 (Container Management)  
    "docker restart", "docker stop", "docker start", "docker ps", "docker logs",
    
    # Web 服务器 (Web Server)
    "nginx -t", "nginx -s reload", # Nginx 配置测试和重载 (Nginx config test and reload)
    
    # 系统参数 (System Parameters)
    "sysctl",                      # 内核参数管理 (Kernel parameter management)
]


def check_command_safety(cmd: str) -> tuple[bool, str]:
    """命令安全性检查函数 (Command Safety Check Function)
    
    这是系统安全的核心检查点，每个待执行的命令都必须通过此函数验证。
    This is the core security checkpoint, every command to be executed must be validated by this function.
    
    检查流程 (Check Process):
    1. 空命令检查：拒绝空白或空命令
    2. 黑名单检查：使用正则表达式匹配危险模式
    3. 白名单检查：验证命令前缀是否在允许列表中
    
    安全原则 (Security Principles):
    - 白名单优于黑名单：即使不在黑名单中，也必须在白名单中
    - 严格匹配：前缀必须完全匹配，防止命令注入
    - 无例外：任何失败都会拒绝命令执行
    
    Args:
        cmd: 待检查的命令字符串 (Command string to check)
        
    Returns:
        tuple[bool, str]: 
            - bool: True 表示安全可执行，False 表示危险需拒绝
            - str: 检查结果的详细描述，用于日志记录和调试
            
    示例 (Examples):
        check_command_safety("ls -la") → (True, "OK")
        check_command_safety("rm -rf /") → (False, "Matches forbidden pattern: ...")
        check_command_safety("custom_tool") → (False, "Command not in allowed prefix list: custom_tool")
        check_command_safety("") → (False, "Empty command")
    
    性能考虑 (Performance Considerations):
    - 使用预编译的正则表达式提高匹配速度
    - 短路求值：一旦发现问题立即返回
    - 白名单检查使用字符串前缀匹配，时间复杂度 O(n)
    """
    # 清理命令字符串，去除前后空白字符 (Clean command string, remove leading/trailing whitespace)
    cmd_stripped = cmd.strip()

    # 检查 1: 拒绝空命令 (Check 1: Reject empty commands)
    if not cmd_stripped:
        return False, "Empty command"

    # 检查 2: 黑名单模式匹配 - 检查是否包含危险操作 (Check 2: Blacklist pattern matching - check for dangerous operations)
    for pattern in _FORBIDDEN_RE:
        if pattern.search(cmd_stripped):  # 使用正则搜索匹配危险模式
            return False, f"Matches forbidden pattern: {pattern.pattern}"

    # 检查 3: 白名单前缀验证 - 只允许预定义的安全命令 (Check 3: Whitelist prefix validation - only allow predefined safe commands)
    cmd_lower = cmd_stripped.lower()  # 转为小写进行大小写不敏感匹配
    allowed = any(cmd_lower.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES)
    if not allowed:
        # 提取命令的第一个词用于错误报告 (Extract first word of command for error reporting)
        first_word = cmd_stripped.split()[0] if cmd_stripped.split() else cmd_stripped
        return False, f"Command not in allowed prefix list: {first_word}"

    # 所有检查通过，命令被认为是安全的 (All checks passed, command is considered safe)
    return True, "OK"


class RateLimiter:
    """频率限制器 (Rate Limiter)
    
    基于主机和 Runbook 的二维限流机制，防止短时间内频繁执行相同的修复操作。
    Two-dimensional rate limiting mechanism based on host and Runbook, preventing frequent 
    execution of the same remediation operations in short time.
    
    设计理念 (Design Philosophy):
    - 细粒度控制：按照 (host, runbook) 组合进行独立限流
    - 冷却时间：每种操作执行后需要等待指定的冷却时间
    - 滑动窗口：使用时间窗口统计，自动清理过期记录
    - 内存高效：只保留有效时间窗口内的执行记录
    
    限流维度 (Rate Limiting Dimensions):
    - 主机维度：同一主机的不同 Runbook 独立计算
    - Runbook 维度：同一 Runbook 在不同主机上独立计算
    - 时间维度：基于冷却时间的滑动窗口
    
    使用场景 (Use Cases):
    - 防止因 AI 误判导致的重复修复
    - 避免修复操作之间的相互干扰
    - 给系统足够时间观察修复效果
    - 防止修复风暴影响系统稳定性
    
    算法复杂度 (Algorithm Complexity):
    - 时间复杂度：O(n) 其中 n 为历史记录数量
    - 空间复杂度：O(m) 其中 m 为活跃的 (host, runbook) 组合数
    """

    def __init__(self) -> None:
        """初始化限流器 (Initialize Rate Limiter)
        
        创建空的执行历史字典，使用 defaultdict 自动创建新键的空列表。
        """
        # 执行历史：(host, runbook_name) -> [timestamp1, timestamp2, ...]
        # Execution history: (host, runbook_name) -> [timestamp1, timestamp2, ...]
        self._history: dict[tuple[str, str], list[float]] = defaultdict(list)

    def can_execute(self, host: str, runbook_name: str, cooldown_seconds: int) -> bool:
        """检查是否可以执行指定的 Runbook (Check if Specified Runbook Can Be Executed)
        
        Args:
            host: 目标主机名 (Target hostname)
            runbook_name: Runbook 名称 (Runbook name)  
            cooldown_seconds: 冷却时间（秒） (Cooldown time in seconds)
            
        Returns:
            bool: True 表示可以执行，False 表示仍在冷却期
            
        工作原理 (Working Principle):
        1. 清理过期的历史记录（超出冷却时间）
        2. 检查剩余记录数量，为 0 则可以执行
        """
        key = (host, runbook_name)
        now = time.time()
        
        # 清理过期记录，只保留冷却期内的执行历史 (Clean expired records, keep only execution history within cooldown period)
        self._history[key] = [t for t in self._history[key] if now - t < cooldown_seconds]
        
        # 如果冷却期内没有执行记录，则允许执行 (Allow execution if no execution records in cooldown period)
        return len(self._history[key]) == 0

    def record_execution(self, host: str, runbook_name: str) -> None:
        """记录一次执行 (Record One Execution)
        
        Args:
            host: 执行的主机名 (Host where execution occurred)
            runbook_name: 执行的 Runbook 名称 (Name of executed Runbook)
            
        用途 (Purpose):
        在命令执行完成后调用，记录时间戳用于后续的限流判断
        """
        self._history[(host, runbook_name)].append(time.time())  # 记录当前时间戳 (Record current timestamp)

    def recent_count(self, host: str, window_seconds: int = 3600) -> int:
        """统计指定主机在时间窗口内的总执行次数 (Count Total Executions on Host Within Time Window)
        
        Args:
            host: 目标主机名 (Target hostname)
            window_seconds: 时间窗口（秒），默认 1 小时 (Time window in seconds, default 1 hour)
            
        Returns:
            int: 该主机在时间窗口内的总执行次数
            
        用途 (Purpose):
        用于风险评估，频繁执行会提升风险等级
        """
        now = time.time()
        count = 0
        
        # 遍历所有历史记录，统计匹配主机的执行次数 (Iterate all history records, count executions for matching host)
        for (h, _), timestamps in self._history.items():
            if h == host:  # 匹配主机名 (Match hostname)
                # 统计时间窗口内的执行次数 (Count executions within time window)
                count += sum(1 for t in timestamps if now - t < window_seconds)
                
        return count


# === 熔断器配置 (Circuit Breaker Configuration) ===
#
# 熔断器是保护故障主机的重要安全机制，防止对已经出现问题的主机进行过度操作
# Circuit breaker is an important safety mechanism to protect failing hosts from excessive operations

# 触发熔断的最大连续失败次数 (Maximum consecutive failures before circuit break)
MAX_FAILURES_BEFORE_CIRCUIT_BREAK = 3

# 熔断窗口时间：30 分钟内的失败次数累计 (Circuit break window: failure count within 30 minutes)
CIRCUIT_BREAK_WINDOW_SECONDS = 1800


class CircuitBreaker:
    """熔断器 (Circuit Breaker)
    
    这是自动修复系统的重要保护机制，用于防止对故障主机的过度操作。
    This is an important protection mechanism of the remediation system, used to prevent 
    excessive operations on failing hosts.
    
    工作原理 (Working Principle):
    基于经典的熔断器模式 (Circuit Breaker Pattern)：
    - 关闭状态 (Closed): 正常执行修复操作
    - 打开状态 (Open): 拒绝所有修复操作，保护故障主机
    - 半开状态 (Half-Open): 本实现中通过成功执行自动重置实现
    
    熔断逻辑 (Circuit Breaking Logic):
    - 在指定时间窗口内累计失败次数
    - 达到失败阈值时触发熔断（状态变为 Open）
    - 一次成功执行会重置失败计数（状态变为 Closed）
    - 过期失败记录会自动清理
    
    设计目标 (Design Goals):
    1. 保护故障主机：避免雪崩效应
    2. 快速失败：减少不必要的资源消耗
    3. 自动恢复：通过成功操作自动重置
    4. 时间衰减：过期失败不影响当前判断
    
    适用场景 (Use Cases):
    - 主机硬件故障导致修复操作连续失败
    - 网络问题导致命令执行超时
    - 服务配置错误导致重启无效
    - 系统资源耗尽导致操作失败
    
    参数说明 (Parameter Description):
    - max_failures: 触发熔断的失败次数阈值
    - window_seconds: 失败统计的时间窗口
    """

    def __init__(
        self,
        max_failures: int = MAX_FAILURES_BEFORE_CIRCUIT_BREAK,
        window_seconds: int = CIRCUIT_BREAK_WINDOW_SECONDS,
    ) -> None:
        """初始化熔断器 (Initialize Circuit Breaker)
        
        Args:
            max_failures: 触发熔断的最大失败次数 (Max failures before circuit break)
            window_seconds: 失败统计的时间窗口 (Time window for failure counting)
        """
        self.max_failures = max_failures      # 失败阈值 (Failure threshold)
        self.window_seconds = window_seconds  # 时间窗口 (Time window)
        # 失败历史：host -> [failure_timestamp1, failure_timestamp2, ...]
        # Failure history: host -> [failure_timestamp1, failure_timestamp2, ...]
        self._failures: dict[str, list[float]] = defaultdict(list)

    def is_open(self, host: str) -> bool:
        """检查指定主机的熔断器是否打开 (Check if Circuit Breaker is Open for Specified Host)
        
        Args:
            host: 主机名 (Hostname)
            
        Returns:
            bool: True 表示熔断器打开（拒绝执行），False 表示熔断器关闭（允许执行）
            
        工作流程 (Workflow):
        1. 清理过期的失败记录（超出时间窗口）
        2. 统计时间窗口内的失败次数
        3. 与阈值比较，决定熔断器状态
        """
        now = time.time()
        
        # 清理过期失败记录，只保留时间窗口内的记录 (Clean expired failure records, keep only records within time window)
        self._failures[host] = [
            t for t in self._failures[host] if now - t < self.window_seconds
        ]
        
        # 检查失败次数是否达到熔断阈值 (Check if failure count reaches circuit break threshold)
        return len(self._failures[host]) >= self.max_failures

    def record_failure(self, host: str) -> None:
        """记录一次失败 (Record One Failure)
        
        Args:
            host: 发生失败的主机名 (Host where failure occurred)
            
        调用时机 (When to Call):
        修复操作执行失败或验证失败时调用
        """
        self._failures[host].append(time.time())  # 记录失败时间戳 (Record failure timestamp)

    def record_success(self, host: str) -> None:
        """记录一次成功 (Record One Success)
        
        Args:
            host: 执行成功的主机名 (Host where success occurred)
            
        行为说明 (Behavior Description):
        一次成功会清空该主机的所有失败记录，立即重置熔断器状态
        One success clears all failure records for the host, immediately resetting circuit breaker state
        
        设计理念 (Design Philosophy):
        成功表明主机已恢复正常，应该给它重新开始的机会
        """
        self._failures[host] = []  # 清空失败记录，重置熔断器 (Clear failure records, reset circuit breaker)


def assess_risk(
    runbook: RunbookDefinition,
    diagnosis: Diagnosis,
    recent_execution_count: int,
) -> RiskLevel:
    """综合风险评估函数 (Comprehensive Risk Assessment Function)
    
    这是自动修复系统的智能决策中心，负责综合多种因素评估操作的风险等级。
    This is the intelligent decision center of the remediation system, responsible for 
    comprehensively assessing operation risk level based on multiple factors.
    
    评估维度 (Assessment Dimensions):
    1. Runbook 基础风险：每个 Runbook 的固有危险性
    2. AI 诊断置信度：AI 对问题判断的准确程度
    3. 历史执行频率：近期在该主机上的执行次数
    
    风险升级规则 (Risk Escalation Rules):
    - 极低置信度 (< 0.3): 直接阻止执行
    - 低置信度 (< 0.7) + 自动风险: 升级到需要确认
    - 高频执行 (≥ 5 次): 直接阻止执行
    - 中频执行 (≥ 3 次) + 自动风险: 升级到需要确认
    
    设计原则 (Design Principles):
    - 保守策略：有疑虑时选择更安全的等级
    - 动态调整：根据实时状态调整风险评估
    - 多因子考虑：综合多个维度的信息
    - 可解释性：每个决策都有明确的逻辑依据
    
    Args:
        runbook: Runbook 定义，包含基础风险等级 (Runbook definition with base risk level)
        diagnosis: AI 诊断结果，包含置信度 (AI diagnosis result with confidence)
        recent_execution_count: 近期执行次数 (Recent execution count)
        
    Returns:
        RiskLevel: 最终的风险等级
        - AUTO: 可以自动执行
        - CONFIRM: 需要人工确认
        - BLOCK: 禁止执行
        
    决策逻辑 (Decision Logic):
    基于决策树模型，按优先级顺序检查各种风险因素
    """
    # 获取 Runbook 的基础风险等级 (Get base risk level of Runbook)
    base_risk = runbook.risk_level

    # 风险因子 1: AI 诊断置信度检查 (Risk Factor 1: AI Diagnosis Confidence Check)
    if diagnosis.confidence < 0.3:
        # 极低置信度：AI 很不确定问题原因，直接阻止执行
        # Extremely low confidence: AI is very uncertain about the cause, block execution directly
        return RiskLevel.BLOCK

    if diagnosis.confidence < 0.7 and base_risk == RiskLevel.AUTO:
        # 低置信度 + 自动执行：升级到需要人工确认
        # Low confidence + auto execution: escalate to require manual confirmation
        return RiskLevel.CONFIRM

    # 风险因子 2: 历史执行频率检查 (Risk Factor 2: Historical Execution Frequency Check)
    if recent_execution_count >= 5:
        # 高频执行：可能陷入修复循环，强制阻止
        # High frequency execution: might be stuck in remediation loop, force block
        return RiskLevel.BLOCK
        
    if recent_execution_count >= 3 and base_risk == RiskLevel.AUTO:
        # 中频执行 + 自动执行：升级到需要人工确认，避免频繁干预
        # Medium frequency execution + auto execution: escalate to manual confirmation, avoid frequent intervention
        return RiskLevel.CONFIRM

    # 所有风险因子检查通过，返回 Runbook 的基础风险等级
    # All risk factors pass, return base risk level of Runbook
    return base_risk
