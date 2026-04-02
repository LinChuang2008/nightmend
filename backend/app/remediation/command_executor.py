"""
NightMend 自动修复系统 - 远程命令执行器
NightMend Remediation System - Remote Command Executor

这是自动修复系统的执行引擎，负责安全地在目标主机上执行修复命令。
This is the execution engine of the remediation system, responsible for safely 
executing remediation commands on target hosts.

核心特性 (Key Features):
- Dry-run 模式：默认启用，用于测试和验证命令安全性
- 安全检查：所有命令执行前都要通过安全审核
- 超时保护：防止长时间运行的命令阻塞系统
- 执行日志：记录所有命令的执行结果和性能指标
- 异常恢复：命令执行失败时的优雅处理

安全设计 (Security Design):
1. 默认 dry_run=True，需要显式开启真实执行
2. 命令白名单检查，拒绝危险操作
3. 输出长度限制，防止内存溢出
4. 进程隔离，使用 subprocess 避免影响主进程

使用场景 (Use Cases):
- 自动重启故障服务
- 清理磁盘空间
- 杀死异常进程
- 日志轮转和压缩
- 网络连接重置

作者：NightMend Team
版本：v1.0
"""
from __future__ import annotations

import asyncio
import logging
import shlex
import time

from .models import CommandResult, RunbookStep
from .safety import check_command_safety

logger = logging.getLogger(__name__)


class CommandExecutor:
    """远程命令执行器 (Remote Command Executor)
    
    这是 NightMend 自动修复系统的核心执行引擎，负责安全可靠地执行修复命令。
    This is the core execution engine of NightMend remediation system, responsible for 
    safely and reliably executing remediation commands.
    
    设计原则 (Design Principles):
    1. 安全第一：所有命令执行前必须通过安全审核
    2. 默认保守：dry_run 模式默认开启，避免意外执行
    3. 完整日志：记录所有命令的详细执行信息
    4. 故障隔离：单个命令失败不影响其他操作
    5. 性能监控：记录命令执行时间用于性能分析
    
    执行模式 (Execution Modes):
    - Dry-run 模式：只记录不执行，用于测试和验证
    - 真实执行模式：实际运行命令，用于生产环境
    
    安全机制 (Safety Mechanisms):
    - 命令白名单检查：只允许预定义的安全命令
    - 超时保护：防止命令长时间阻塞
    - 输出截断：防止大量输出导致内存问题
    - 异常捕获：确保任何错误都能被妥善处理
    
    日志记录 (Logging):
    维护完整的执行历史，包括命令内容、退出码、输出、耗时等
    """

    def __init__(self, dry_run: bool = True, remote_host: str = "", ssh_user: str = "", ssh_password: str = "") -> None:
        """初始化命令执行器 (Initialize Command Executor)
        
        Args:
            dry_run: 是否启用 Dry-run 模式 (Whether to enable dry-run mode)
                    True: 只记录不执行，用于测试 (Only log, don't execute, for testing)
                    False: 真实执行命令，用于生产 (Actually execute commands, for production)
                    
        安全考虑 (Security Considerations):
        默认值为 True 是为了防止意外执行危险命令，生产环境需要显式设置为 False
        """
        self.dry_run = dry_run  # 执行模式标志 (Execution mode flag)
        self.remote_host = remote_host  # 远程主机 IP
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self._execution_log: list[CommandResult] = []  # 执行历史记录 (Execution history log)

    @property
    def execution_log(self) -> list[CommandResult]:
        """获取执行历史记录 (Get Execution History Log)
        
        返回所有已执行命令的详细记录，包括成功和失败的情况。
        Returns detailed records of all executed commands, including both success and failure cases.
        
        Returns:
            list[CommandResult]: 执行结果列表的副本，防止外部修改 (Copy of execution results list to prevent external modification)
            
        用途 (Usage):
        - 审计和调试：查看命令执行的详细过程
        - 性能分析：统计命令执行时间和成功率
        - 故障排查：定位失败命令的具体原因
        """
        return list(self._execution_log)  # 返回副本确保数据安全 (Return copy to ensure data safety)

    async def execute_step(self, step: RunbookStep) -> CommandResult:
        """执行单条 Runbook 步骤 (Execute Single Runbook Step)
        
        这是命令执行的核心方法，负责安全地执行一条修复命令。
        This is the core method for command execution, responsible for safely executing 
        a single remediation command.
        
        执行流程 (Execution Flow):
        1. 安全检查：验证命令是否在白名单中
        2. 模式判断：根据 dry_run 标志选择执行策略
        3. 真实执行：调用系统命令并监控结果
        4. 日志记录：保存执行结果到历史记录
        
        Args:
            step: Runbook 步骤定义，包含命令、描述、超时等信息
            
        Returns:
            CommandResult: 执行结果，包含退出码、输出、错误信息、执行时间等
            
        安全保障 (Safety Guarantees):
        - 所有命令都要经过安全检查
        - 危险命令会被直接拒绝
        - 执行超时会自动终止进程
        - 异常情况都有适当的错误处理
        
        性能考虑 (Performance Considerations):
        - 异步执行，不阻塞其他操作
        - 输出长度限制，防止内存溢出
        - 精确计时，便于性能分析
        """
        # 第一层防护：命令安全性检查 (First layer protection: command safety check)
        is_safe, reason = check_command_safety(step.command)
        if not is_safe:  # 发现不安全命令，立即阻止 (Found unsafe command, block immediately)
            result = CommandResult(
                command=step.command,
                exit_code=-1,  # -1 表示被系统阻止 (-1 indicates blocked by system)
                stderr=f"BLOCKED by safety check: {reason}",  # 记录阻止原因
                executed=False,  # 标记为未实际执行 (Mark as not actually executed)
            )
            self._execution_log.append(result)  # 记录到执行历史 (Record to execution history)
            logger.warning("Command blocked: %s -- %s", step.command, reason)
            return result

        # Dry-run 模式：只记录不执行，用于测试和验证 (Dry-run mode: only log, don't execute, for testing and validation)
        if self.dry_run:
            result = CommandResult(
                command=step.command,
                exit_code=0,  # 模拟成功执行 (Simulate successful execution)
                stdout=f"[DRY RUN] Would execute: {step.command}",  # 标记为模拟执行
                executed=False,  # 实际未执行 (Not actually executed)
                duration_ms=0,  # 无执行时间 (No execution time)
            )
            self._execution_log.append(result)  # 记录模拟结果 (Record simulation result)
            logger.info("[DRY RUN] %s: %s", step.description, step.command)
            return result

        # 真实执行模式：调用系统命令 (Real execution mode: call system command)
        if self.remote_host and self.ssh_user:
            return await self._execute_ssh(step)
        return await self._execute_real(step)

    async def execute_steps(self, steps: list[RunbookStep]) -> list[CommandResult]:
        """批量顺序执行多条 Runbook 步骤 (Batch Sequential Execution of Multiple Runbook Steps)
        
        按照预定义的顺序执行一系列修复命令，采用快速失败策略。
        Execute a series of remediation commands in predefined order, using fail-fast strategy.
        
        执行策略 (Execution Strategy):
        - 顺序执行：严格按照步骤定义的顺序执行
        - 快速失败：遇到第一个失败的命令立即停止
        - 完整记录：无论成功失败都会记录到执行历史
        
        Args:
            steps: Runbook 步骤列表，每个步骤包含命令、描述、超时等
            
        Returns:
            list[CommandResult]: 所有已执行步骤的结果列表
            
        行为说明 (Behavior Description):
        - 如果所有步骤成功：返回所有步骤的执行结果
        - 如果某步骤失败：返回到失败步骤为止的所有结果，后续步骤不执行
        - Dry-run 模式：所有步骤都会被"执行"，返回模拟结果
        
        适用场景 (Use Cases):
        - 服务重启：停止服务 → 清理缓存 → 启动服务 → 健康检查
        - 磁盘清理：检查空间 → 清理日志 → 清理临时文件 → 验证结果
        """
        results: list[CommandResult] = []  # 收集所有执行结果 (Collect all execution results)
        
        # 顺序执行每个步骤 (Execute each step sequentially)
        for step in steps:
            result = await self.execute_step(step)  # 执行单个步骤
            results.append(result)  # 收集结果
            
            # 快速失败：遇到错误立即停止后续执行 (Fail-fast: stop on first error)
            if result.exit_code != 0:
                logger.warning(
                    "Step failed (exit=%d), stopping: %s",
                    result.exit_code,
                    step.command,
                )
                break  # 不执行剩余步骤 (Don't execute remaining steps)
                
        return results  # 返回已执行步骤的结果 (Return results of executed steps)

    async def _execute_real(self, step: RunbookStep) -> CommandResult:
        """通过 subprocess 真实执行系统命令 (Execute System Command via subprocess)
        
        这是实际命令执行的核心实现，使用异步子进程确保不阻塞主线程。
        This is the core implementation of actual command execution, using async subprocess 
        to ensure non-blocking main thread.
        
        技术实现 (Technical Implementation):
        - 使用 asyncio.create_subprocess_shell 创建异步子进程
        - 支持超时控制，防止长时间运行的命令阻塞系统
        - 分别捕获 stdout 和 stderr 输出
        - 精确测量执行时间用于性能分析
        - 输出长度限制防止内存溢出
        
        Args:
            step: Runbook 步骤，包含要执行的命令和超时设置
            
        Returns:
            CommandResult: 详细的执行结果，包含退出码、输出、错误、耗时等
            
        安全措施 (Safety Measures):
        - 进程隔离：命令在独立子进程中执行
        - 超时终止：超时后强制杀死子进程
        - 输出截断：限制输出长度到 4KB
        - 异常捕获：妥善处理所有可能的执行异常
        
        错误处理 (Error Handling):
        - 超时错误：返回 exit_code=-1 和超时信息
        - 系统异常：返回 exit_code=-1 和异常描述
        - 命令失败：返回实际的非零退出码
        """
        start = time.monotonic()  # 记录开始时间用于计算耗时 (Record start time for duration calculation)
        
        try:
            # 创建异步子进程执行命令（使用 exec 避免 shell 注入）
            # Create async subprocess (using exec to avoid shell injection)
            args = shlex.split(step.command)
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,  # 捕获标准输出 (Capture stdout)
                stderr=asyncio.subprocess.PIPE,  # 捕获标准错误 (Capture stderr)
            )
            try:
                # 等待命令完成，带超时保护 (Wait for command completion with timeout protection)
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=step.timeout_seconds
                )
            except asyncio.TimeoutError:
                # 命令超时：强制终止进程 (Command timeout: force terminate process)
                proc.kill()  # 发送 SIGKILL 信号强制终止 (Send SIGKILL to force terminate)
                await proc.communicate()  # 等待进程清理完成 (Wait for process cleanup)
                elapsed = int((time.monotonic() - start) * 1000)  # 计算实际耗时
                
                result = CommandResult(
                    command=step.command,
                    exit_code=-1,  # -1 表示超时终止 (-1 indicates timeout termination)
                    stderr=f"Command timed out after {step.timeout_seconds}s",
                    executed=True,  # 标记为已执行（虽然被终止） (Mark as executed though terminated)
                    duration_ms=elapsed,
                )
                self._execution_log.append(result)  # 记录超时结果 (Record timeout result)
                return result

            # 命令正常完成：处理执行结果 (Command completed normally: process execution result)
            elapsed = int((time.monotonic() - start) * 1000)  # 计算总耗时毫秒数 (Calculate total duration in ms)
            
            result = CommandResult(
                command=step.command,
                exit_code=proc.returncode or 0,  # 获取进程退出码，None 时默认 0 (Get process exit code, default 0 if None)
                stdout=stdout_bytes.decode(errors="replace")[:4096],  # 解码并截断标准输出 (Decode and truncate stdout)
                stderr=stderr_bytes.decode(errors="replace")[:4096],  # 解码并截断标准错误 (Decode and truncate stderr) 
                executed=True,  # 标记为真实执行 (Mark as actually executed)
                duration_ms=elapsed,  # 记录执行耗时 (Record execution duration)
            )
            self._execution_log.append(result)  # 添加到执行历史 (Add to execution history)
            return result

        except Exception as e:
            # 系统异常：进程创建失败或其他意外错误 (System exception: process creation failed or other unexpected errors)
            elapsed = int((time.monotonic() - start) * 1000)  # 即使失败也要记录耗时
            
            result = CommandResult(
                command=step.command,
                exit_code=-1,  # -1 表示系统级错误 (-1 indicates system-level error)
                stderr=str(e),  # 记录异常信息到错误输出 (Record exception info to stderr)
                executed=True,  # 标记为已尝试执行 (Mark as execution attempted)
                duration_ms=elapsed,  # 记录到异常发生的时间 (Record time until exception occurred)
            )
            self._execution_log.append(result)  # 记录异常结果 (Record exception result)
            return result

    async def _execute_ssh(self, step: RunbookStep) -> CommandResult:
        """通过 SSH 在远程主机上执行命令。"""
        start = time.monotonic()
        try:
            import asyncssh
            # 从配置读取 known_hosts 路径，留空则禁用验证（仅开发/首次部署）
            # Read known_hosts path from config; empty disables verification (dev/initial deploy only)
            from app.core.config import settings
            _known_hosts_path = settings.agent_ssh_known_hosts or None
            if _known_hosts_path is None:
                if settings.environment != "development":
                    raise RuntimeError(
                        "SSH host key verification is required in production. "
                        "Set AGENT_SSH_KNOWN_HOSTS=/etc/ssh/ssh_known_hosts."
                    )
                logger.warning(
                    "SSH host key verification is disabled (development mode). "
                    "Set AGENT_SSH_KNOWN_HOSTS in production."
                )
            async with asyncssh.connect(
                self.remote_host,
                username=self.ssh_user,
                password=self.ssh_password,
                known_hosts=_known_hosts_path,
            ) as conn:
                ssh_result = await asyncio.wait_for(
                    conn.run(step.command),
                    timeout=step.timeout_seconds,
                )
                elapsed = int((time.monotonic() - start) * 1000)
                result = CommandResult(
                    command=step.command,
                    exit_code=ssh_result.exit_status or 0,
                    stdout=(ssh_result.stdout or "")[:4096],
                    stderr=(ssh_result.stderr or "")[:4096],
                    executed=True,
                    duration_ms=elapsed,
                )
                self._execution_log.append(result)
                logger.info("[SSH %s] %s -> exit=%d", self.remote_host, step.command, result.exit_code)
                return result
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - start) * 1000)
            result = CommandResult(
                command=step.command,
                exit_code=-1,
                stderr=f"SSH command timed out after {step.timeout_seconds}s",
                executed=True,
                duration_ms=elapsed,
            )
            self._execution_log.append(result)
            return result
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            result = CommandResult(
                command=step.command,
                exit_code=-1,
                stderr=f"SSH error: {e}",
                executed=True,
                duration_ms=elapsed,
            )
            self._execution_log.append(result)
            return result
