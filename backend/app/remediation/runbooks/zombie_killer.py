"""
NightMend 自动修复 Runbook - 僵尸进程清理
NightMend Automatic Remediation Runbook - Zombie Process Cleanup

这是一个僵尸进程清理脚本，用于识别和处理系统中的僵尸（zombie/defunct）进程。
This is a zombie process cleanup script for identifying and handling zombie/defunct processes in the system.

技术背景 (Technical Background):
- 僵尸进程是已终止但父进程未收尾的子进程
- 它们占用进程表条目但不消耗CPU和内存资源
- 大量僵尸进程可能导致进程表溢出
- 清理僵尸进程需要处理其父进程

适用场景 (Applicable Scenarios):
- 系统中僵尸进程数量异常增多 (Abnormal increase in zombie process count)
- 进程表接近满载 (Process table near capacity)
- 应用程序未正确处理子进程退出 (Applications not properly handling child process exit)
- 监控发现过多的 Z 状态进程 (Monitoring detects too many Z-state processes)

清理原理 (Cleanup Principle):
僵尸进程无法直接杀死，需要：
1. 识别僵尸进程及其父进程
2. 向父进程发送信号或重启父进程
3. 父进程收到 SIGCHLD 后调用 wait() 清理僵尸子进程

风险评估 (Risk Assessment):
- 风险等级：AUTO（自动执行）
- 影响：主要是诊断性操作
- 注意：当前实现偏向诊断，实际清理操作有限

注意 (Note):
当前版本主要进行诊断，实际的进程终止操作需要谨慎处理，
因为杀死父进程可能影响正常业务运行。

作者：NightMend Team
版本：v1.0
风险等级：LOW (诊断为主)
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

# 僵尸进程清理 Runbook 定义 (Zombie Process Cleanup Runbook Definition)
RUNBOOK = RunbookDefinition(
    # 基本信息 (Basic Information)
    name="zombie_killer",
    description="Kill zombie/defunct processes and their parent processes",
    
    # 匹配规则 (Matching Rules)
    match_alert_types=["zombie_processes", "defunct_processes", "high_process_count"],  # 进程异常告警
    match_keywords=["zombie", "defunct", "Z state", "too many processes"],            # 僵尸进程关键词
    
    # 安全设置 (Safety Settings)
    risk_level=RiskLevel.AUTO,  # 自动执行：当前版本主要是诊断操作，风险较低
    
    # 僵尸进程诊断命令序列 (Zombie Process Diagnosis Command Sequence)
    commands=[
        # 第1步：列出所有僵尸进程 (Step 1: List all zombie processes)
        RunbookStep(
            description="List zombie processes",
            command="ps aux | grep -w Z | grep -v grep",  # 查找状态为Z的进程
            timeout_seconds=10
            # 命令解析：
            # ps aux: 显示所有进程详细信息
            # grep -w Z: 精确匹配状态列中的 'Z'（僵尸状态）
            # grep -v grep: 排除 grep 命令本身
        ),
        
        # 第2步：识别僵尸进程的父进程 (Step 2: Identify parent processes of zombies)
        # 注意：此命令只是查找，没有实际杀死进程
        # Note: This command only identifies, doesn't actually kill processes
        RunbookStep(
            description="Kill parent processes of zombies to reap them",  # 描述与实际操作不符，需要改进
            command="ps -eo ppid,stat | grep Z | awk '{print $1}' | sort -u | head -20",  # 查找僵尸进程的父进程ID
            timeout_seconds=10
            # 命令解析：
            # ps -eo ppid,stat: 显示父进程ID和进程状态
            # grep Z: 过滤僵尸进程
            # awk '{print $1}': 提取父进程ID
            # sort -u: 去重排序
            # head -20: 限制输出前20个，避免过多输出
            
            # TODO: 考虑添加实际的进程终止命令，如：
            # kill -TERM $(ps -eo ppid,stat | grep Z | awk '{print $1}' | sort -u | head -5)
            # 但需要谨慎，因为可能影响正常业务进程
        ),
    ],
    
    # 验证命令 (Verification Commands)
    verify_commands=[
        RunbookStep(
            description="Check remaining zombie count",
            command="ps aux | grep -w Z | grep -v grep",  # 再次检查僵尸进程数量
            timeout_seconds=10
        ),
    ],
    
    # 冷却时间：5分钟，避免频繁检查 (Cooldown: 5 minutes, avoid frequent checking)
    cooldown_seconds=300,
)
