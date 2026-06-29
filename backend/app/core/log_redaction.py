"""日志脱敏过滤器 (Log Redaction Filter)

全局 logging Filter，拦截所有日志 record 的 msg/args，
对常见敏感凭证（Bearer token / Authorization 头 / API key 参数）做脱敏。

底层逻辑：
    第三方库（httpx、fastmcp、uvicorn）可能在 DEBUG/WARNING 级别打印
    完整请求头或 URL 查询串，token 一旦进日志文件/ELK 就等于泄漏。
    在根 logger 挂一个 Filter，拦截点尽量靠近 write，覆盖面最大。

只脱敏字符串字段，不改变日志结构；性能损耗 < 5μs/record (regex sub)。
"""
from __future__ import annotations

import logging
import re
from typing import Any


# 不贪婪匹配，避免吃掉后续多余字符
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer xxx
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._\-]+"), r"\1***REDACTED***"),
    # 裸 Bearer 前缀
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1***REDACTED***"),
    # URL query / form 里的 api_key / token / access_token
    (re.compile(r"(?i)((?:api[_-]?key|token|access[_-]?token|secret)=)[^&\s\"']+"),
     r"\1***REDACTED***"),
    # JSON 风格: "api_key": "xxx"
    (re.compile(r"(?i)(\"(?:api[_-]?key|token|access[_-]?token|secret)\"\s*:\s*\")([^\"]+)(\")"),
     r"\1***REDACTED***\3"),
)


def _scrub(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _scrub_any(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub(value)
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub_any(v) for v in value]
        return type(value)(scrubbed)
    if isinstance(value, dict):
        return {k: _scrub_any(v) for k, v in value.items()}
    return value


class RedactionFilter(logging.Filter):
    """对 record.msg 与 record.args 做脱敏；filter 必须返回 True 放行。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args:
            record.args = _scrub_any(record.args)  # type: ignore[assignment]
        return True


def install_global_redaction() -> None:
    """在 root logger 安装脱敏 filter，幂等。"""
    root = logging.getLogger()
    # 避免重复注入
    if any(isinstance(f, RedactionFilter) for f in root.filters):
        return
    redactor = RedactionFilter()
    root.addFilter(redactor)
    # 同步附加到已有 handler —— basicConfig 安装的 handler 只走自身 filter
    for handler in root.handlers:
        if not any(isinstance(f, RedactionFilter) for f in handler.filters):
            handler.addFilter(redactor)
