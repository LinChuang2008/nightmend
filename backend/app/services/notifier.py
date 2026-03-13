"""
通知分发服务 (Notification Distribution Service)

功能描述 (Description):
    VigilOps 统一通知分发引擎，负责将告警和修复结果通知发送到多个渠道。
    实现智能降噪机制，避免告警风暴对运维人员造成干扰。
    
支持的通知渠道 (Supported Channels):
    1. Webhook - 通用HTTP接口，支持自定义headers
    2. Email - SMTP邮件发送，支持HTML模板
    3. DingTalk - 钉钉机器人，支持签名验证
    4. Feishu - 飞书机器人，支持富文本卡片
    5. WeCom - 企业微信机器人，支持Markdown格式
    
智能降噪特性 (Intelligent Noise Reduction):
    1. 静默时间窗口 (Silence Window) - 指定时间段内不发送通知
    2. 冷却时间控制 (Cooldown Control) - 同一规则的告警间隔发送
    3. 失败重试机制 (Retry Mechanism) - 网络异常时自动重试
    4. 通知模板系统 (Template System) - 支持自定义消息格式
    
技术特性 (Technical Features):
    - 异步发送：所有通知渠道支持并发发送
    - 容错设计：单个渠道失败不影响其他渠道
    - 状态跟踪：完整的发送日志和状态记录
    - 配置灵活：每个渠道独立配置和启用控制
"""
import asyncio
import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from app.models.alert import Alert, AlertRule
from app.models.notification import NotificationChannel, NotificationLog
from app.models.notification_template import NotificationTemplate

logger = logging.getLogger(__name__)

# 通知发送配置常量 (从配置文件读取) (Notification Configuration Constants from Settings)
MAX_RETRIES = settings.notification_max_retries  # 发送失败时的最大重试次数
TEMPLATE_CACHE_TTL = settings.notification_template_cache_ttl  # 模板缓存 TTL（秒）
CHANNEL_CACHE_TTL = settings.notification_channel_cache_ttl  # 渠道配置缓存 TTL（秒）
DEFAULT_COOLDOWN = settings.notification_default_cooldown  # 默认冷却时间（秒）


# ---------------------------------------------------------------------------
# URL 安全验证模块 (URL Security Validation Module)
# 防止 SSRF 攻击，验证 Webhook URL 是否在白名单内
# ---------------------------------------------------------------------------

def _validate_webhook_url(url: str) -> tuple[bool, str | None]:
    """
    Webhook URL 安全验证器 (Webhook URL Security Validator)

    功能描述:
        防止服务端请求伪造（SSRF）攻击，验证目标 URL 是否安全。
        检查 URL 格式、协议、域名白名单等安全要素。

    Args:
        url: 待验证的 Webhook URL

    Returns:
        tuple: (is_valid, error_message)
            - is_valid: True 表示 URL 安全，False 表示不安全
            - error_message: 验证失败时的错误信息，成功时为 None

    验证规则 (Validation Rules):
        1. URL 格式必须合法
        2. 协议必须是 http 或 https
        3. 生产环境下域名必须在白名单内（如果配置了白名单）
        4. 禁止访问内网地址（127.0.0.1, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16）
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL 格式无效: {str(e)}"

    # 1. 协议检查
    if parsed.scheme not in ("http", "https"):
        return False, f"不支持的协议: {parsed.scheme}，仅允许 http 和 https"

    # 2. 域名存在性检查
    if not parsed.netloc:
        return False, "URL 缺少域名"

    # 3. 内网地址检查（防止 SSRF 攻击）
    hostname = parsed.hostname
    if not hostname:
        return False, "无法解析主机名"

    # 禁止访问的内网地址列表
    forbidden_patterns = [
        "127.",           # Loopback
        "localhost",      # Loopback
        "0.0.0.0",        # All interfaces
        "10.",            # Private Class A
        "172.16.",        # Private Class B (start)
        "172.17.",        # Private Class B
        "172.18.",        # Private Class B
        "172.19.",        # Private Class B
        "172.20.",        # Private Class B
        "172.21.",        # Private Class B
        "172.22.",        # Private Class B
        "172.23.",        # Private Class B
        "172.24.",        # Private Class B
        "172.25.",        # Private Class B
        "172.26.",        # Private Class B
        "172.27.",        # Private Class B
        "172.28.",        # Private Class B
        "172.29.",        # Private Class B
        "172.30.",        # Private Class B
        "172.31.",        # Private Class B
        "192.168.",       # Private Class C
    ]

    for pattern in forbidden_patterns:
        if hostname.startswith(pattern) or hostname == pattern.replace(".", ""):
            return False, f"禁止访问内网地址: {hostname}"

    # 4. 白名单检查（生产环境）
    if settings.environment.lower() == "production" and settings.webhook_allowed_domains:
        allowed_domains = [d.strip() for d in settings.webhook_allowed_domains.split(",")]
        if hostname not in allowed_domains:
            return False, f"域名 {hostname} 不在白名单中，允许的域名: {', '.join(allowed_domains)}"

    return True, None


# ---------------------------------------------------------------------------
# 自动修复结果通知模块 (Auto-Remediation Result Notification Module)
# 供 remediation agent 调用，通知修复执行结果
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 测试通知发送模块 (Test Notification Module)
# 用于验证通知渠道配置是否正确
# ---------------------------------------------------------------------------

async def send_test_notification_to_channel(channel: NotificationChannel) -> bool:
    """
    测试通知发送函数 (Test Notification Sender)

    功能描述:
        向指定渠道发送测试通知，用于验证渠道配置是否正确。
        发送固定的测试消息，不依赖实际的告警对象。

    Args:
        channel: 待测试的通知渠道配置

    Returns:
        bool: 发送成功返回 True，失败返回 False

    测试消息内容:
        - 标题: "VigilOps 测试通知"
        - 内容: 包含渠道类型、发送时间等信息的测试消息
    """
    from datetime import datetime

    test_title = "VigilOps 测试通知"
    test_message = f"这是一条测试通知，用于验证 {channel.name} ({channel.type}) 渠道配置是否正确。"
    test_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 构建测试模板变量
    test_variables = {
        "title": test_title,
        "severity": "info",
        "message": test_message,
        "metric_value": "N/A",
        "threshold": "N/A",
        "host_id": "0",
        "fired_at": test_time
    }

    try:
        if channel.type == "webhook":
            return await _send_test_webhook(channel, test_variables)
        elif channel.type == "email":
            return await _send_test_email(channel, test_variables)
        elif channel.type == "dingtalk":
            return await _send_test_dingtalk(channel, test_variables)
        elif channel.type == "feishu":
            return await _send_test_feishu(channel, test_variables)
        elif channel.type == "wecom":
            return await _send_test_wecom(channel, test_variables)
        else:
            logger.warning(f"Unsupported channel type for test: {channel.type}")
            return False
    except Exception as e:
        logger.error(f"Test notification failed for channel {channel.name}: {e}")
        return False


async def _send_test_webhook(channel: NotificationChannel, variables: dict) -> bool:
    """发送 Webhook 测试通知。"""
    url = channel.config.get("url")
    if not url:
        logger.warning(f"Webhook test notification failed: url is empty for channel {channel.name}")
        return False

    # SSRF 防护：验证 URL 安全性
    is_valid, error_msg = _validate_webhook_url(url)
    if not is_valid:
        logger.warning(f"Webhook URL validation failed for channel {channel.name}: {error_msg}")
        return False

    headers = channel.config.get("headers", {})
    headers.setdefault("Content-Type", "application/json")

    payload = {
        "test": True,
        "text": f"**{variables['title']}**\n\n{variables['message']}\n\n发送时间: {variables['fired_at']}"
    }

    try:
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            resp = await client.post(url, json=payload, headers=headers)
        logger.info(f"Webhook test notification response for {channel.name}: status={resp.status_code}, body={resp.text[:200]}")
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.error(f"Webhook test notification failed for channel {channel.name}: {e}", exc_info=True)
        return False


async def _send_test_email(channel: NotificationChannel, variables: dict) -> bool:
    """发送邮件测试通知。"""
    import aiosmtplib

    config = channel.config
    smtp_host = config.get("smtp_host", "")
    smtp_port = config.get("smtp_port", 465)
    smtp_user = config.get("smtp_user", "")
    smtp_password = config.get("smtp_password", "")
    use_ssl = config.get("smtp_ssl", True)
    recipients = config.get("recipients", [])

    if not recipients:
        logger.warning(f"Email test notification failed: recipients is empty for channel {channel.name}")
        return False

    subject = f"🧪 {variables['title']}"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
      <div style="background:#4CAF50;color:#fff;padding:16px 24px;">
        <h2 style="margin:0;">🧪 VigilOps 测试通知</h2>
      </div>
      <div style="padding:24px;">
        <p>这是一条<strong>测试通知</strong>，用于验证邮件配置是否正确。</p>
        <p><strong>渠道名称:</strong> {channel.name}</p>
        <p><strong>渠道类型:</strong> {channel.type}</p>
        <p><strong>发送时间:</strong> {variables['fired_at']}</p>
        <p style="color:#888;">如果您收到此邮件，说明邮件通知配置正确！</p>
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html", "utf-8"))

    kwargs = {
        "hostname": smtp_host,
        "port": smtp_port,
        "username": smtp_user,
        "password": smtp_password,
    }
    if use_ssl:
        kwargs["use_tls"] = True
    else:
        kwargs["start_tls"] = True

    try:
        await aiosmtplib.send(msg, **kwargs)
        logger.info(f"Email test notification sent successfully to {recipients} for channel {channel.name}")
        return True
    except Exception as e:
        logger.error(f"Email test notification failed for channel {channel.name}: {e}", exc_info=True)
        return False


async def _send_test_dingtalk(channel: NotificationChannel, variables: dict) -> bool:
    """发送钉钉测试通知。"""
    config = channel.config
    webhook_url = config.get("webhook_url", "")
    secret = config.get("secret")

    if not webhook_url:
        logger.warning(f"DingTalk test notification failed: webhook_url is empty for channel {channel.name}")
        return False

    # 签名
    if secret:
        ts, sign = _dingtalk_sign(secret)
        sep = "&" if "?" in webhook_url else "?"
        webhook_url = f"{webhook_url}{sep}timestamp={ts}&sign={sign}"

    body = (
        f"## 🧪 VigilOps 测试通知\n\n"
        f"这是一条测试通知，用于验证钉钉配置是否正确。\n\n"
        f"**渠道名称**: {channel.name}\n"
        f"**发送时间**: {variables['fired_at']}\n\n"
        f"如果收到此消息，说明钉钉通知配置正确！"
    )

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "VigilOps 测试通知",
            "text": body,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            resp = await client.post(webhook_url, json=payload)
        logger.info(f"DingTalk test notification response for {channel.name}: status={resp.status_code}, body={resp.text[:200]}")
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.error(f"DingTalk test notification failed for channel {channel.name}: {e}", exc_info=True)
        return False


async def _send_test_feishu(channel: NotificationChannel, variables: dict) -> bool:
    """发送飞书测试通知。"""
    config = channel.config
    webhook_url = config.get("webhook_url", "")
    secret = config.get("secret")

    if not webhook_url:
        logger.warning(f"Feishu test notification failed: webhook_url is empty for channel {channel.name}")
        return False

    body = (
        f"**渠道名称**: {channel.name}\n"
        f"**发送时间**: {variables['fired_at']}\n"
        f"这是一条测试通知，用于验证飞书配置是否正确。"
    )

    payload: dict = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🧪 VigilOps 测试通知"},
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": body},
                }
            ],
        },
    }

    # 签名
    if secret:
        ts, sign = _feishu_sign(secret)
        payload["timestamp"] = ts
        payload["sign"] = sign

    try:
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            resp = await client.post(webhook_url, json=payload)
        logger.info(f"Feishu test notification response for {channel.name}: status={resp.status_code}, body={resp.text[:200]}")
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.error(f"Feishu test notification failed for channel {channel.name}: {e}", exc_info=True)
        return False


async def _send_test_wecom(channel: NotificationChannel, variables: dict) -> bool:
    """发送企业微信测试通知。"""
    config = channel.config
    webhook_url = config.get("webhook_url", "")

    if not webhook_url:
        logger.warning(f"WeCom test notification failed: webhook_url is empty for channel {channel.name}")
        return False

    body = (
        f"## <font color='info'>🧪 VigilOps 测试通知</font>\n"
        f"> 这是一条测试通知，用于验证企业微信配置是否正确。\n"
        f"> **渠道名称**: {channel.name}\n"
        f"> **发送时间**: {variables['fired_at']}\n\n"
        f"如果收到此消息，说明企业微信通知配置正确！"
    )

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": body},
    }

    try:
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            resp = await client.post(webhook_url, json=payload)
        logger.info(f"WeCom test notification response: status={resp.status_code}, body={resp.text[:200]}")
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.error(f"WeCom test notification failed for channel {channel.name}: {e}", exc_info=True)
        return False
# 供 remediation agent 调用，通知修复执行结果
# ---------------------------------------------------------------------------

def _remediation_success_message(alert_name: str, host: str, runbook: str, duration: str) -> str:
    """
    修复成功通知正文生成器 (Remediation Success Message Generator)
    
    功能描述:
        生成自动修复成功时的通知消息，包含关键执行信息。
        
    Args:
        alert_name: 原始告警名称
        host: 执行修复的目标主机
        runbook: 执行的修复脚本名称
        duration: 修复执行耗时
        
    Returns:
        格式化的Markdown通知消息
    """
    return (
        f"✅ **自动修复成功**\n\n"
        f"**告警**: {alert_name}\n"
        f"**主机**: {host}\n"
        f"**Runbook**: {runbook}\n"
        f"**执行耗时**: {duration}"
    )


def _remediation_failure_message(alert_name: str, host: str, reason: str) -> str:
    """
    修复失败通知正文生成器 (Remediation Failure Message Generator)
    
    功能描述:
        生成自动修复失败时的告警升级消息，提醒人工介入。
        
    Args:
        alert_name: 原始告警名称
        host: 修复失败的目标主机
        reason: 失败原因描述
        
    Returns:
        格式化的紧急通知消息，提醒运维人员及时处理
    """
    return (
        f"❌ **自动修复失败，需人工介入**\n\n"
        f"**告警**: {alert_name}\n"
        f"**主机**: {host}\n"
        f"**失败原因**: {reason}"
    )


def _remediation_approval_message(alert_name: str, host: str, action: str, approval_url: str) -> str:
    """
    修复审批通知正文生成器 (Remediation Approval Message Generator)
    
    功能描述:
        生成需要人工审批的修复操作通知，提供审批链接。
        用于高风险操作的安全控制。
        
    Args:
        alert_name: 原始告警名称  
        host: 目标主机
        action: 建议执行的修复操作描述
        approval_url: 审批操作的Web界面链接
        
    Returns:
        包含审批链接的通知消息
    """
    return (
        f"🔒 **修复操作待审批**\n\n"
        f"**告警**: {alert_name}\n"
        f"**主机**: {host}\n"
        f"**建议操作**: {action}\n"
        f"**审批链接**: {approval_url}"
    )


async def send_remediation_notification(
    db: AsyncSession,
    *,
    kind: str,
    alert_name: str,
    host: str,
    runbook: str = "",
    duration: str = "",
    reason: str = "",
    action: str = "",
    approval_url: str = "",
) -> None:
    """
    修复结果统一通知接口 (Unified Remediation Notification Interface)
    
    功能描述:
        自动修复系统的通知入口，根据修复结果类型发送不同格式的通知。
        支持修复成功、失败、需审批三种场景的通知。
        
    Args:
        db: 数据库会话
        kind: 通知类型 - "success"(成功) | "failure"(失败) | "approval"(待审批)
        alert_name: 原始告警名称
        host: 目标主机标识
        runbook: 可选，执行的修复脚本名称（成功时使用）
        duration: 可选，修复执行耗时（成功时使用）
        reason: 可选，失败原因（失败时使用）
        action: 可选，建议操作描述（审批时使用）
        approval_url: 可选，审批链接（审批时使用）
        
    流程步骤:
        1. 根据kind类型选择对应的消息模板
        2. 查询所有已启用的通知渠道
        3. 并发向所有渠道发送通知
        4. 失败渠道记录异常，不影响其他渠道
    """
    # 1. 根据修复结果类型生成对应的通知正文
    if kind == "success":
        body = _remediation_success_message(alert_name, host, runbook, duration)
    elif kind == "approval":
        body = _remediation_approval_message(alert_name, host, action, approval_url)
    else:  # "failure" 或其他情况
        body = _remediation_failure_message(alert_name, host, reason)

    # 2. 查询所有已启用的通知渠道（使用缓存）
    channels = await _get_enabled_channels(db)

    # 3. 使用 asyncio.gather 并发向所有渠道发送修复结果通知
    # return_exceptions=True 确保单个渠道失败不影响其他渠道
    if channels:
        tasks = [_send_remediation_to_channel(channel, body) for channel in channels]
        await asyncio.gather(*tasks, return_exceptions=True)
        # 记录发送异常
        for task, channel in zip(tasks, channels):
            if isinstance(task, Exception):
                logger.exception(
                    "Failed to send remediation notification to channel %s", channel.name
                )


async def _send_remediation_to_channel(channel: NotificationChannel, body: str) -> None:
    """复用现有渠道发送纯文本修复通知。"""
    config = channel.config

    if channel.type == "webhook":
        url = config.get("url", "")
        if not url:
            return
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            await client.post(url, json={"text": body}, headers={"Content-Type": "application/json"})

    elif channel.type == "dingtalk":
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            return
        secret = config.get("secret")
        if secret:
            ts, sign = _dingtalk_sign(secret)
            sep = "&" if "?" in webhook_url else "?"
            webhook_url = f"{webhook_url}{sep}timestamp={ts}&sign={sign}"
        payload = {"msgtype": "markdown", "markdown": {"title": "VigilOps 修复通知", "text": body}}
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            await client.post(webhook_url, json=payload)

    elif channel.type == "feishu":
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            return
        payload: dict = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": "VigilOps 修复通知"}, "template": "blue"},
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}}],
            },
        }
        secret = config.get("secret")
        if secret:
            ts, sign = _feishu_sign(secret)
            payload["timestamp"] = ts
            payload["sign"] = sign
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            await client.post(webhook_url, json=payload)

    elif channel.type == "wecom":
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            return
        payload = {"msgtype": "markdown", "markdown": {"content": body}}
        async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
            await client.post(webhook_url, json=payload)

    elif channel.type == "email":
        import aiosmtplib
        smtp_host = config.get("smtp_host", "")
        smtp_port = config.get("smtp_port", 465)
        smtp_user = config.get("smtp_user", "")
        smtp_password = config.get("smtp_password", "")
        use_ssl = config.get("smtp_ssl", True)
        recipients = config.get("recipients", [])
        if not recipients:
            return
        msg = MIMEMultipart("alternative")
        msg["From"] = smtp_user
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = "VigilOps 修复通知"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        kwargs = {"hostname": smtp_host, "port": smtp_port, "username": smtp_user, "password": smtp_password}
        if use_ssl:
            kwargs["use_tls"] = True
        else:
            kwargs["start_tls"] = True
        await aiosmtplib.send(msg, **kwargs)


# ---------------------------------------------------------------------------
# 通知模板处理模块 (Notification Template Processing Module)  
# 负责模板变量提取、模板查找和内容渲染
# ---------------------------------------------------------------------------

async def _build_template_vars(
    db: AsyncSession,
    alert: Alert,
    notification_type: str = "first",
    duration_seconds: int = 0
) -> dict:
    """
    告警模板变量构建器 (Alert Template Variables Builder)

    功能描述:
        从告警对象中提取关键字段，构建模板渲染所需的变量字典。
        处理空值和类型转换，确保模板渲染的稳定性。
        查询关联主机的显示名称和 IP 地址信息（包括内网 IP 和公网 IP）。

    Args:
        db: 数据库异步会话
        alert: 告警对象，包含所有告警相关信息
        notification_type: 通知类型 (first/continuous/recovery)
        duration_seconds: 告警持续时长（秒）

    Returns:
        dict: 模板变量字典，包含格式化后的告警字段

    变量说明:
        - title: 告警标题
        - severity: 严重级别（critical/warning/info）
        - message: 详细告警消息
        - metric_value: 触发告警的指标值
        - threshold: 告警阈值
        - host_id: 告警来源主机ID
        - host_name: 主机名（优先显示自定义名称）
        - host_ip: 主机IP（优先公网IP，否则内网IP）
        - private_ip: 内网IP地址
        - public_ip: 公网IP地址
        - fired_at: 告警触发时间（格式化字符串）
        - notification_type: 通知类型 (first/continuous/recovery)
        - duration_seconds: 持续时长（秒）
        - duration_human: 持续时长（人类可读格式）
        - status_text: 状态文本（告警/已恢复）
    """
    # 计算人类可读的持续时长
    duration_human = _format_duration(duration_seconds)

    # 根据通知类型确定状态文本
    status_text_map = {
        "first": "告警触发",
        "continuous": "持续告警",
        "recovery": "已恢复"
    }
    status_text = status_text_map.get(notification_type, "告警")

    variables = {
        "title": alert.title or "",                              # 告警标题，空值处理
        "severity": alert.severity or "",                        # 严重级别
        "message": alert.message or "",                          # 告警消息
        "metric_value": alert.metric_value if alert.metric_value is not None else "",  # 指标值，处理None
        "threshold": alert.threshold if alert.threshold is not None else "",            # 阈值，处理None
        "host_id": alert.host_id if alert.host_id is not None else "",                  # 主机ID，处理None
        "host_name": "",                                         # 主机名，默认空
        "host_ip": "",                                           # 主机IP，默认空
        "private_ip": "",                                        # 内网IP，默认空
        "public_ip": "",                                         # 公网IP，默认空
        "fired_at": alert.fired_at.strftime("%Y-%m-%d %H:%M:%S") if alert.fired_at else "",  # 时间格式化
        "resolved_at": alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if alert.resolved_at else "",  # 恢复时间
        "notification_type": notification_type,                   # 通知类型
        "duration_seconds": duration_seconds,                    # 持续时长（秒）
        "duration_human": duration_human,                        # 持续时长（可读）
        "status_text": status_text,                              # 状态文本
        "alert_status": alert.status or "",                      # 告警状态
    }

    # 如果有关联主机，查询主机信息
    if alert.host_id:
        from sqlalchemy import select
        from app.models.host import Host
        result = await db.execute(select(Host).where(Host.id == alert.host_id))
        host = result.scalar_one_or_none()
        if host:
            variables["host_name"] = host.display_hostname
            variables["host_ip"] = host.display_ip
            variables["private_ip"] = host.private_ip or host.ip_address or "-"
            variables["public_ip"] = host.public_ip or "-"

    return variables


def _format_duration(seconds: int) -> str:
    """
    将秒数格式化为人类可读的时长字符串

    Args:
        seconds: 秒数

    Returns:
        格式化的时长字符串，如 "2小时30分钟" 或 "45秒"
    """
    if seconds <= 0:
        return "0秒"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if secs > 0 and hours == 0:  # 只有不到1小时时才显示秒
        parts.append(f"{secs}秒")

    return "".join(parts) if parts else "0秒"


async def _get_default_template(db: AsyncSession, channel_type: str):
    """
    默认通知模板查找器（带缓存）(Default Notification Template Finder with Cache)

    功能描述:
        按优先级查找指定渠道类型的默认通知模板，支持Redis缓存。
        实现模板继承机制，支持通用模板作为后备。

    Args:
        db: 数据库会话
        channel_type: 渠道类型（webhook/email/dingtalk/feishu/wecom）

    Returns:
        NotificationTemplate对象或None

    查找策略:
        1. 优先从缓存查找
        2. 缓存未命中时查询数据库
        3. 精确匹配查找：特定渠道类型的默认模板
        4. 回退查找：通用"all"类型的默认模板
        5. 查询结果写入缓存
    """
    redis = await get_redis()
    cache_key = f"notification:template:{channel_type}"

    # 1. 尝试从缓存获取
    cached = await redis.get(cache_key)
    if cached:
        import json
        try:
            template_data = json.loads(cached)
            # 构造模板对象（简化版，仅包含必要字段）
            from types import SimpleNamespace
            return SimpleNamespace(**template_data)
        except Exception:
            pass  # 缓存解析失败，继续查询数据库

    # 2. 缓存未命中，查询数据库
    # 2.1 精确匹配查找：特定渠道类型的默认模板
    result = await db.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.channel_type == channel_type,
            NotificationTemplate.is_default == True,  # noqa: E712
        )
    )
    template = result.scalar_one_or_none()
    if template:
        # 写入缓存
        template_dict = {
            "id": template.id,
            "name": template.name,
            "channel_type": template.channel_type,
            "subject_template": template.subject_template,
            "body_template": template.body_template,
            "is_default": template.is_default,
        }
        await redis.setex(cache_key, TEMPLATE_CACHE_TTL, json.dumps(template_dict))
        return template

    # 2.2 回退查找：通用"all"类型的默认模板
    result = await db.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.channel_type == "all",
            NotificationTemplate.is_default == True,  # noqa: E712
        )
    )
    template = result.scalar_one_or_none()
    if template:
        # 写入缓存（使用 "all" 类型的缓存键）
        cache_key_all = f"notification:template:all"
        template_dict = {
            "id": template.id,
            "name": template.name,
            "channel_type": template.channel_type,
            "subject_template": template.subject_template,
            "body_template": template.body_template,
            "is_default": template.is_default,
        }
        await redis.setex(cache_key_all, TEMPLATE_CACHE_TTL, json.dumps(template_dict))

    return template


def _render_template(template, variables: dict) -> tuple[str | None, str]:
    """
    模板渲染引擎 (Template Rendering Engine)

    功能描述:
        使用Python字符串格式化语法渲染通知模板。
        支持主题和正文模板的独立渲染，容错处理变量缺失。

    Args:
        template: 通知模板对象，包含subject_template和body_template字段
        variables: 模板变量字典，包含{title}、{severity}等占位符对应值

    Returns:
        tuple: (subject, body) 元组
            - subject: 渲染后的主题（可能为None，如邮件以外渠道）
            - body: 渲染后的正文内容

    容错机制:
        - 变量缺失时使用原始模板内容
        - 格式化异常时保持模板不变
        - 确保渲染过程不会因数据问题中断
    """
    subject = None
    # 1. 主题模板渲染（主要用于邮件渠道）
    if template and template.subject_template:
        try:
            subject = template.subject_template.format(**variables)
        except (KeyError, IndexError):
            # 变量缺失或格式错误时，保持原始模板
            subject = template.subject_template

    # 2. 正文模板渲染（所有渠道必需）
    if template:
        try:
            body = template.body_template.format(**variables)
        except (KeyError, IndexError):
            # 变量缺失或格式错误时，保持原始模板
            body = template.body_template
    else:
        # 没有模板时使用默认消息
        body = f"告警: {variables.get('title', 'N/A')}\n严重级别: {variables.get('severity', 'N/A')}"

    return subject, body


async def _get_enabled_channels(db: AsyncSession):
    """
    获取已启用的通知渠道列表（带缓存）(Get Enabled Channels with Cache)

    功能描述:
        从数据库获取所有已启用的通知渠道，支持Redis缓存。
        缓存渠道列表以减少数据库查询频率。

    Args:
        db: 数据库会话

    Returns:
        list[NotificationChannel]: 已启用的通知渠道列表
    """
    redis = await get_redis()
    cache_key = "notification:channels:enabled"

    # 1. 尝试从缓存获取
    cached = await redis.get(cache_key)
    if cached:
        import json
        try:
            channels_data = json.loads(cached)
            # 从缓存数据重建渠道对象列表
            from types import SimpleNamespace
            channels = [SimpleNamespace(**ch) for ch in channels_data]
            return channels
        except Exception:
            pass  # 缓存解析失败，继续查询数据库

    # 2. 缓存未命中，查询数据库
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.is_enabled == True)  # noqa: E712
    )
    channels = result.scalars().all()

    # 3. 写入缓存
    channels_data = [
        {
            "id": ch.id,
            "name": ch.name,
            "type": ch.type,
            "config": ch.config,
            "is_enabled": ch.is_enabled,
        }
        for ch in channels
    ]
    import json
    await redis.setex(cache_key, CHANNEL_CACHE_TTL, json.dumps(channels_data))

    return channels


async def _get_channels_for_rule(db: AsyncSession, channel_ids: list[int] | None):
    """
    根据告警规则配置获取指定的通知渠道列表 (Get Channels for Alert Rule)

    功能描述:
        根据告警规则中配置的 notification_channel_ids 获取对应的通知渠道。
        如果规则未配置渠道（None 或空列表），则返回所有已启用的渠道（兼容旧数据）。
        仅返回已启用的渠道，避免向已禁用的渠道发送通知。

    Args:
        db: 数据库会话
        channel_ids: 告警规则配置的通知渠道ID列表

    Returns:
        list[NotificationChannel]: 符合条件的通知渠道列表

    逻辑说明:
        1. 如果 channel_ids 为 None 或空列表，返回所有已启用渠道（兼容未配置规则的旧数据）
        2. 如果 channel_ids 有值，只返回指定ID且已启用的渠道
        3. 过滤掉已禁用的渠道，即使用户配置了该渠道
    """
    # 1. 如果规则未配置渠道，返回所有已启用渠道（向后兼容）
    if not channel_ids:
        logger.info("Alert rule has no configured channels, using all enabled channels")
        return await _get_enabled_channels(db)

    # 2. 查询指定ID的渠道，且必须是已启用状态
    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.id.in_(channel_ids),
            NotificationChannel.is_enabled == True,  # noqa: E712
        )
    )
    channels = result.scalars().all()

    # 3. 记录日志：如果配置的渠道中有被禁用的
    enabled_ids = {ch.id for ch in channels}
    disabled_ids = set(channel_ids) - enabled_ids
    if disabled_ids:
        logger.warning(
            f"Some configured channels are disabled and will be skipped: {disabled_ids}"
        )

    return list(channels)


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

async def send_alert_notification(
    db: AsyncSession,
    alert: Alert,
    notification_type: str = "first",
    duration_seconds: int = 0
):
    """
    告警通知智能分发引擎 (Intelligent Alert Notification Distribution Engine)

    功能描述:
        VigilOps 核心降噪引擎，实现智能化的告警通知分发。
        通过静默时间窗口控制，有效避免告警风暴。
        支持三种通知类型：首次告警、持续告警、恢复通知。

    Args:
        db: 数据库会话，用于查询告警规则和通知渠道配置
        alert: 待发送通知的告警对象，包含触发信息和关联规则
        notification_type: 通知类型
            - "first": 首次告警（触发时发送）
            - "continuous": 持续告警（每冷却期发送）
            - "recovery": 恢复通知（恢复正常时发送）
        duration_seconds: 告警持续时长（秒），用于持续告警和恢复通知

    智能降噪流程 (Intelligent Noise Reduction Process):
        1. 静默窗口检查 (Silence Window Check) - 检查当前时间是否在静默期
        2. 多渠道并发发送 (Multi-channel Concurrent Send) - 向所有启用渠道发送

    降噪机制说明 (Noise Reduction Mechanisms):
        - 静默期 (Silence Period): 指定时间段内完全禁止发送通知
        - 冷却期控制已移至 alert_engine 层级，由 AlertDeduplicationService 处理
    """
    # 1. 告警规则配置获取 (Alert Rule Configuration Retrieval)
    # 查询关联的告警规则，获取降噪参数配置
    rule_result = await db.execute(select(AlertRule).where(AlertRule.id == alert.rule_id))
    rule = rule_result.scalar_one_or_none()

    # 2. 静默时间窗口检查 (Silence Window Check) - 降噪机制
    # 在指定的静默时间段内，完全禁止发送任何通知
    if rule and rule.silence_start and rule.silence_end:
        now_time = datetime.now().time()  # 获取当前时间（仅时分秒）

        # 2.1 处理同日静默窗口（如 09:00-18:00）
        if rule.silence_start <= rule.silence_end:
            if rule.silence_start <= now_time <= rule.silence_end:
                logger.info(f"Alert {alert.id} silenced (current time in silence window)")
                return  # 静默期内，直接返回不发送通知
        # 2.2 处理跨日静默窗口（如 23:00-07:00）
        else:
            if now_time >= rule.silence_start or now_time <= rule.silence_end:
                logger.info(f"Alert {alert.id} silenced (current time in silence window)")
                return  # 跨日静默期内，直接返回

    # 3. 多渠道并发通知发送 (Multi-channel Concurrent Notification)
    # 通过降噪检查后，向规则配置的通知渠道发送告警
    channel_ids = rule.notification_channel_ids if rule else None
    channels = await _get_channels_for_rule(db, channel_ids)

    # 3.1 使用 asyncio.gather 并发向所有已启用渠道发送通知
    # return_exceptions=True 确保单个渠道失败不影响其他渠道
    if channels:
        tasks = [
            _send_to_channel(db, alert, channel, notification_type, duration_seconds)
            for channel in channels
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        # 记录发送异常（gather 会返回异常对象）
        for task, channel in zip(tasks, channels):
            if isinstance(task, Exception):
                logger.warning(
                    f"Notification send failed for channel {channel.name}: {task}"
                )


async def _send_to_channel(
    db: AsyncSession,
    alert: Alert,
    channel: NotificationChannel,
    notification_type: str = "first",
    duration_seconds: int = 0
):
    """
    单渠道告警发送处理器 (Single Channel Alert Sender)

    功能描述:
        负责向指定的单个通知渠道发送告警，包含模板渲染、重试机制、状态记录。
        采用策略模式根据渠道类型分发到对应的发送函数。

    Args:
        db: 数据库会话
        alert: 告警对象
        channel: 目标通知渠道配置
        notification_type: 通知类型 (first/continuous/recovery)
        duration_seconds: 告警持续时长（秒）

    处理流程:
        1. 渠道类型分发到对应处理函数
        2. 查找并应用通知模板
        3. 执行带重试的发送逻辑
        4. 记录发送状态和日志
    """
    # 1. 渠道类型分发器 (Channel Type Dispatcher) - 策略模式实现
    dispatchers = {
        "webhook": _send_webhook,      # 通用Webhook发送
        "email": _send_email,          # SMTP邮件发送
        "dingtalk": _send_dingtalk,    # 钉钉机器人发送
        "feishu": _send_feishu,        # 飞书机器人发送
        "wecom": _send_wecom,          # 企业微信机器人发送
    }
    handler = dispatchers.get(channel.type)
    if not handler:
        logger.warning(f"不支持的通知渠道类型: {channel.type}")
        return

    # 2. 通知模板处理 (Notification Template Processing)
    template = await _get_default_template(db, channel.type)  # 查找渠道默认模板
    variables = await _build_template_vars(
        db, alert, notification_type, duration_seconds
    )  # 构建模板变量字典（包含主机信息和通知类型）

    # 3. 初始化通知发送日志记录 (Initialize Notification Log)
    log = NotificationLog(
        alert_id=alert.id,
        channel_id=channel.id,
        status="failed",    # 默认失败，成功后更新
        retries=0,
    )

    # 4. 带重试机制的发送循环 (Retry-enabled Send Loop)
    # 网络异常、服务暂时不可用等情况的容错处理
    full_error = None  # 保存完整错误信息用于日志记录
    for attempt in range(MAX_RETRIES):
        try:
            # 4.1 调用对应渠道的发送函数
            resp_code = await handler(alert, channel, template, variables)
            log.response_code = resp_code

            # 4.2 检查HTTP状态码判断是否发送成功
            if resp_code and 200 <= resp_code < 300:
                log.status = "sent"
                break  # 发送成功，跳出重试循环
            log.error = f"HTTP {resp_code}"
        except Exception as e:
            # 4.3 完整记录异常到日志系统
            full_error = str(e)
            logger.error(
                f"Notification send error (attempt {attempt + 1}/{MAX_RETRIES}) "
                f"for alert {alert.id} to channel {channel.name}: {full_error}",
                exc_info=True  # 记录完整的堆栈跟踪
            )
            # 数据库只存储摘要（限制长度）
            log.error = full_error[:500] if full_error else "Unknown error"
        log.retries = attempt + 1  # 记录重试次数

    # 5. 记录发送状态到数据库 (Record Send Status to Database)
    log.sent_at = datetime.now(timezone.utc)
    db.add(log)
    await db.commit()

    # 6. 发送结果日志记录 (Send Result Logging)
    if log.status == "sent":
        logger.info(
            f"Notification sent successfully for alert {alert.id} to channel {channel.name} "
            f"(attempts: {log.retries})"
        )
    else:
        logger.error(
            f"Notification failed for alert {alert.id} to channel {channel.name} "
            f"after {log.retries} attempts. Last error: {full_error or log.error}"
        )


# ---------------------------------------------------------------------------
# Webhook 发送（保持原有逻辑）
# ---------------------------------------------------------------------------

async def _send_webhook(
    alert: Alert, channel: NotificationChannel, template, variables: dict
) -> int | None:
    """发送 Webhook 通知，支持 SSRF 防护和 URL 白名单验证，包含通知类型和持续时长。"""
    url = channel.config.get("url")
    if not url:
        return None

    # SSRF 防护：验证 URL 安全性
    is_valid, error_msg = _validate_webhook_url(url)
    if not is_valid:
        logger.warning(f"Webhook URL 验证失败: {error_msg}")
        raise ValueError(f"不安全的 Webhook URL: {error_msg}")

    headers = channel.config.get("headers", {})
    headers.setdefault("Content-Type", "application/json")

    # 如果有模板，使用模板渲染 body；否则使用原始 JSON
    if template:
        _, body = _render_template(template, variables)
        payload = {"text": body}
    else:
        payload = {
            "alert_id": alert.id,
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity,
            "status": alert.status,
            "metric_value": alert.metric_value,
            "threshold": alert.threshold,
            "host_id": alert.host_id,
            "host_name": variables.get("host_name", ""),
            "host_ip": variables.get("host_ip", ""),
            "private_ip": variables.get("private_ip", ""),
            "public_ip": variables.get("public_ip", ""),
            "service_id": alert.service_id,
            "fired_at": alert.fired_at.isoformat() if alert.fired_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            # 新增字段：通知类型和持续时长
            "notification_type": variables.get("notification_type", "first"),
            "status_text": variables.get("status_text", "告警"),
            "duration_seconds": variables.get("duration_seconds", 0),
            "duration_human": variables.get("duration_human", ""),
        }

    async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
        resp = await client.post(url, json=payload, headers=headers)
    return resp.status_code


# ---------------------------------------------------------------------------
# 邮件发送
# ---------------------------------------------------------------------------

async def _send_email(
    alert: Alert, channel: NotificationChannel, template, variables: dict
) -> int | None:
    """通过 SMTP 发送邮件通知，支持三种通知类型。"""
    import aiosmtplib

    config = channel.config
    smtp_host = config.get("smtp_host", "")
    smtp_port = config.get("smtp_port", 465)
    smtp_user = config.get("smtp_user", "")
    smtp_password = config.get("smtp_password", "")
    use_ssl = config.get("smtp_ssl", True)
    recipients = config.get("recipients", [])

    if not recipients:
        logger.warning("邮件通知渠道未配置收件人")
        return None

    # 渲染内容
    notification_type = variables.get("notification_type", "first")
    if template:
        subject, body = _render_template(template, variables)
        if not subject:
            subject = _get_email_subject(alert, notification_type)
    else:
        subject = _get_email_subject(alert, notification_type)
        body = _default_email_html(variables, notification_type)

    # 构建邮件
    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html", "utf-8"))

    # 发送
    kwargs = {
        "hostname": smtp_host,
        "port": smtp_port,
        "username": smtp_user,
        "password": smtp_password,
    }
    if use_ssl:
        kwargs["use_tls"] = True
    else:
        kwargs["start_tls"] = True

    await aiosmtplib.send(msg, **kwargs)
    return 200  # SMTP 无 HTTP 状态码，成功即返回 200


def _get_email_subject(alert: Alert, notification_type: str) -> str:
    """根据通知类型生成邮件主题。"""
    if notification_type == "recovery":
        return f"[VigilOps 已恢复] {alert.title}"
    elif notification_type == "continuous":
        return f"[VigilOps 持续告警] {alert.severity} - {alert.title}"
    else:  # first
        return f"[VigilOps 告警] {alert.severity} - {alert.title}"


def _default_email_html(variables: dict, notification_type: str = "first") -> str:
    """生成默认的告警邮件 HTML 正文，支持三种通知类型。"""
    # 根据通知类型选择颜色和标题
    if notification_type == "recovery":
        header_color = "#4CAF50"  # 绿色
        header_text = "✅ VigilOps 告警恢复"
        extra_rows = f"""
          <tr><td style="padding:8px 0;font-weight:bold;">状态</td><td>已恢复</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">持续时长</td><td>{variables.get('duration_human', '-')}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">恢复时间</td><td>{variables.get('resolved_at', '-')}</td></tr>
        """
    elif notification_type == "continuous":
        header_color = "#FF9800"  # 橙色
        header_text = "🔁 VigilOps 持续告警"
        extra_rows = f"""
          <tr><td style="padding:8px 0;font-weight:bold;">持续时长</td><td>{variables.get('duration_human', '-')}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">严重级别</td><td>{variables['severity']}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">消息</td><td>{variables['message']}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">指标值</td><td>{variables['metric_value']}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">阈值</td><td>{variables['threshold']}</td></tr>
        """
    else:  # first
        header_color = "#d32f2f"  # 红色
        header_text = "⚠️ VigilOps 告警通知"
        extra_rows = f"""
          <tr><td style="padding:8px 0;font-weight:bold;">严重级别</td><td>{variables['severity']}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">消息</td><td>{variables['message']}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">指标值</td><td>{variables['metric_value']}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">阈值</td><td>{variables['threshold']}</td></tr>
        """

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
      <div style="background:{header_color};color:#fff;padding:16px 24px;">
        <h2 style="margin:0;">{header_text}</h2>
      </div>
      <div style="padding:24px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr><td style="padding:8px 0;font-weight:bold;">标题</td><td>{variables['title']}</td></tr>
          {extra_rows}
          <tr><td style="padding:8px 0;font-weight:bold;">主机名称</td><td>{variables.get('host_name', '-')}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">内网 IP</td><td>{variables.get('private_ip', '-')}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">公网 IP</td><td>{variables.get('public_ip', '-')}</td></tr>
          <tr><td style="padding:8px 0;font-weight:bold;">触发时间</td><td>{variables['fired_at']}</td></tr>
        </table>
      </div>
      <div style="background:#f5f5f5;padding:12px 24px;text-align:center;color:#888;font-size:12px;">
        VigilOps 监控平台
      </div>
    </div>
    """


# ---------------------------------------------------------------------------
# 钉钉机器人通知模块 (DingTalk Bot Notification Module)
# 实现钉钉Webhook签名验证和消息发送
# ---------------------------------------------------------------------------

def _dingtalk_sign(secret: str) -> tuple[str, str]:
    """
    钉钉Webhook签名计算器 (DingTalk Webhook Signature Calculator)
    
    功能描述:
        按照钉钉官方文档实现Webhook签名算法，确保消息安全性。
        使用HMAC-SHA256算法对时间戳和密钥进行签名。
        
    Args:
        secret: 钉钉机器人的加签密钥
        
    Returns:
        tuple: (timestamp, sign) 时间戳和签名字符串
        
    签名算法:
        1. 获取当前毫秒时间戳
        2. 构建待签名字符串：timestamp + "\n" + secret
        3. 使用HMAC-SHA256计算签名
        4. Base64编码后URL转义
        
    安全说明:
        签名机制防止恶意请求，确保只有拥有密钥的应用能发送消息
    """
    # 1. 获取当前毫秒级时间戳（钉钉要求毫秒精度）
    timestamp = str(int(time.time() * 1000))
    
    # 2. 构建待签名字符串（钉钉官方格式）
    string_to_sign = f"{timestamp}\n{secret}"
    
    # 3. HMAC-SHA256签名计算
    hmac_code = hmac.new(
        secret.encode("utf-8"), 
        string_to_sign.encode("utf-8"), 
        digestmod=hashlib.sha256
    ).digest()
    
    # 4. Base64编码并URL转义（符合钉钉API要求）
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode())
    
    return timestamp, sign


async def _send_dingtalk(
    alert: Alert, channel: NotificationChannel, template, variables: dict
) -> int | None:
    """发送钉钉机器人 Webhook 通知（markdown 格式），支持三种通知类型。"""
    config = channel.config
    webhook_url = config.get("webhook_url", "")
    secret = config.get("secret")

    if not webhook_url:
        return None

    # 签名
    if secret:
        ts, sign = _dingtalk_sign(secret)
        sep = "&" if "?" in webhook_url else "?"
        webhook_url = f"{webhook_url}{sep}timestamp={ts}&sign={sign}"

    # 渲染内容
    if template:
        _, body = _render_template(template, variables)
    else:
        notification_type = variables.get("notification_type", "first")
        status_text = variables.get("status_text", "告警")
        duration_human = variables.get("duration_human", "")

        # 根据通知类型构建不同格式的消息
        if notification_type == "recovery":
            body = (
                f"## ✅ VigilOps 告警恢复\n\n"
                f"**标题**: {variables['title']}\n\n"
                f"**状态**: {status_text}\n\n"
                f"**持续时长**: {duration_human}\n\n"
                f"**主机**: {variables.get('host_name', '-')}\n\n"
                f"**内网IP**: {variables.get('private_ip', '-')}\n\n"
                f"**公网IP**: {variables.get('public_ip', '-')}\n\n"
                f"**恢复时间**: {variables.get('resolved_at', variables['fired_at'])}"
            )
            title_prefix = "[已恢复]"
        elif notification_type == "continuous":
            body = (
                f"## 🔁 VigilOps 持续告警\n\n"
                f"**标题**: {variables['title']}\n\n"
                f"**级别**: {variables['severity']}\n\n"
                f"**消息**: {variables['message']}\n\n"
                f"**持续时长**: {duration_human}\n\n"
                f"**主机**: {variables.get('host_name', '-')}\n\n"
                f"**内网IP**: {variables.get('private_ip', '-')}\n\n"
                f"**公网IP**: {variables.get('public_ip', '-')}\n\n"
                f"**触发时间**: {variables['fired_at']}"
            )
            title_prefix = "[持续]"
        else:  # first
            body = (
                f"## ⚠️ VigilOps 告警\n\n"
                f"**标题**: {variables['title']}\n\n"
                f"**级别**: {variables['severity']}\n\n"
                f"**消息**: {variables['message']}\n\n"
                f"**主机**: {variables.get('host_name', '-')}\n\n"
                f"**内网IP**: {variables.get('private_ip', '-')}\n\n"
                f"**公网IP**: {variables.get('public_ip', '-')}\n\n"
                f"**触发时间**: {variables['fired_at']}"
            )
            title_prefix = "[告警]"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{title_prefix} {variables['title']}",
            "text": body,
        },
    }

    async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
        resp = await client.post(webhook_url, json=payload)
    return resp.status_code


# ---------------------------------------------------------------------------
# 飞书机器人通知模块 (Feishu Bot Notification Module)
# 实现飞书Webhook签名验证和富文本卡片消息发送
# ---------------------------------------------------------------------------

def _feishu_sign(secret: str) -> tuple[str, str]:
    """
    飞书Webhook签名计算器 (Feishu Webhook Signature Calculator)

    功能描述:
        实现飞书官方Webhook签名算法，与钉钉略有差异。
        使用秒级时间戳和HMAC-SHA256算法进行签名。

    Args:
        secret: 飞书机器人的加签密钥

    Returns:
        tuple: (timestamp, sign) 时间戳和签名字符串

    签名算法差异:
        - 飞书使用秒级时间戳（与钉钉的毫秒级不同）
        - HMAC签名后直接Base64编码（无需URL转义）
        - 签名字符串格式与钉钉相同：timestamp + "\n" + secret
        - HMAC参数顺序：secret作为key，string_to_sign作为message

    安全说明:
        签名机制防止恶意请求，确保只有拥有密钥的应用能发送消息
    """
    # 1. 获取当前秒级时间戳（飞书使用秒精度，与钉钉不同）
    timestamp = str(int(time.time()))

    # 2. 构建待签名字符串（与钉钉格式相同）
    string_to_sign = f"{timestamp}\n{secret}"

    # 3. HMAC-SHA256签名计算（使用secret作为key）
    hmac_code = hmac.new(
        secret.encode("utf-8"),      # secret作为key
        string_to_sign.encode("utf-8"),  # 待签名字符串作为message
        digestmod=hashlib.sha256
    ).digest()

    # 4. Base64编码（无需URL转义，与钉钉不同）
    sign = base64.b64encode(hmac_code).decode()

    return timestamp, sign


async def _send_feishu(
    alert: Alert, channel: NotificationChannel, template, variables: dict
) -> int | None:
    """发送飞书机器人 Webhook 通知（富文本卡片格式），支持三种通知类型。"""
    config = channel.config
    webhook_url = config.get("webhook_url", "")
    secret = config.get("secret")

    if not webhook_url:
        return None

    # 渲染内容
    if template:
        _, body = _render_template(template, variables)
        header_title = "VigilOps 通知"
        header_color = "blue"
    else:
        notification_type = variables.get("notification_type", "first")
        status_text = variables.get("status_text", "告警")
        duration_human = variables.get("duration_human", "")

        # 根据通知类型构建不同格式的消息
        if notification_type == "recovery":
            body = (
                f"**标题**: {variables['title']}\n"
                f"**状态**: {status_text}\n"
                f"**持续时长**: {duration_human}\n"
                f"**主机**: {variables.get('host_name', '-')}\n"
                f"**内网IP**: {variables.get('private_ip', '-')}\n"
                f"**公网IP**: {variables.get('public_ip', '-')}\n"
                f"**恢复时间**: {variables.get('resolved_at', variables['fired_at'])}"
            )
            header_title = "✅ VigilOps 告警恢复"
            header_color = "green"
        elif notification_type == "continuous":
            body = (
                f"**标题**: {variables['title']}\n"
                f"**级别**: {variables['severity']}\n"
                f"**消息**: {variables['message']}\n"
                f"**持续时长**: {duration_human}\n"
                f"**主机**: {variables.get('host_name', '-')}\n"
                f"**内网IP**: {variables.get('private_ip', '-')}\n"
                f"**公网IP**: {variables.get('public_ip', '-')}\n"
                f"**触发时间**: {variables['fired_at']}"
            )
            header_title = "🔁 VigilOps 持续告警"
            header_color = "orange"
        else:  # first
            body = (
                f"**标题**: {variables['title']}\n"
                f"**级别**: {variables['severity']}\n"
                f"**消息**: {variables['message']}\n"
                f"**主机**: {variables.get('host_name', '-')}\n"
                f"**内网IP**: {variables.get('private_ip', '-')}\n"
                f"**公网IP**: {variables.get('public_ip', '-')}\n"
                f"**触发时间**: {variables['fired_at']}"
            )
            header_title = "⚠️ VigilOps 告警"
            header_color = "red"

    payload: dict = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": header_color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": body},
                }
            ],
        },
    }

    # 签名
    if secret:
        ts, sign = _feishu_sign(secret)
        payload["timestamp"] = ts
        payload["sign"] = sign

    async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
        resp = await client.post(webhook_url, json=payload)
    return resp.status_code


# ---------------------------------------------------------------------------
# 企业微信发送
# ---------------------------------------------------------------------------

async def _send_wecom(
    alert: Alert, channel: NotificationChannel, template, variables: dict
) -> int | None:
    """发送企业微信机器人 Webhook 通知（markdown 格式），支持三种通知类型。"""
    config = channel.config
    webhook_url = config.get("webhook_url", "")

    if not webhook_url:
        return None

    # 渲染内容
    if template:
        _, body = _render_template(template, variables)
    else:
        notification_type = variables.get("notification_type", "first")
        status_text = variables.get("status_text", "告警")
        duration_human = variables.get("duration_human", "")

        # 根据通知类型构建不同格式的消息
        if notification_type == "recovery":
            body = (
                f"## <font color='info'>✅ VigilOps 告警恢复</font>\n"
                f"> **标题**: {variables['title']}\n"
                f"> **状态**: {status_text}\n"
                f"> **持续时长**: {duration_human}\n"
                f"> **主机**: {variables.get('host_name', '-')}\n"
                f"> **内网IP**: {variables.get('private_ip', '-')}\n"
                f"> **公网IP**: {variables.get('public_ip', '-')}\n"
                f"> **恢复时间**: {variables.get('resolved_at', variables['fired_at'])}"
            )
        elif notification_type == "continuous":
            body = (
                f"## <font color='warning'>🔁 VigilOps 持续告警</font>\n"
                f"> **标题**: {variables['title']}\n"
                f"> **级别**: {variables['severity']}\n"
                f"> **消息**: {variables['message']}\n"
                f"> **持续时长**: {duration_human}\n"
                f"> **主机**: {variables.get('host_name', '-')}\n"
                f"> **内网IP**: {variables.get('private_ip', '-')}\n"
                f"> **公网IP**: {variables.get('public_ip', '-')}\n"
                f"> **触发时间**: {variables['fired_at']}"
            )
        else:  # first
            body = (
                f"## <font color='warning'>⚠️ VigilOps 告警</font>\n"
                f"> **标题**: {variables['title']}\n"
                f"> **级别**: {variables['severity']}\n"
                f"> **消息**: {variables['message']}\n"
                f"> **主机**: {variables.get('host_name', '-')}\n"
                f"> **内网IP**: {variables.get('private_ip', '-')}\n"
                f"> **公网IP**: {variables.get('public_ip', '-')}\n"
                f"> **触发时间**: {variables['fired_at']}"
            )

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": body},
    }

    async with httpx.AsyncClient(timeout=10, verify=settings.webhook_enable_ssl_verification) as client:
        resp = await client.post(webhook_url, json=payload)
    return resp.status_code
