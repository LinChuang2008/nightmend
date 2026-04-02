"""
NightMend 自动修复系统 - AI 智能诊断客户端
NightMend Remediation System - AI Intelligent Diagnosis Client

这个模块负责将告警信息发送给 AI 模型进行智能分析，识别问题根因并推荐修复方案。
This module is responsible for sending alert information to AI models for intelligent analysis,
identifying problem root causes and recommending remediation solutions.

主要功能 (Key Features):
- 复用 NightMend 全局 AI 配置（默认 DeepSeek API）
- 专门针对运维修复场景优化的 Prompt 工程
- 支持多种上下文信息（系统指标、日志片段等）
- Mock 模式支持，便于测试和开发
- 智能解析 AI 响应，容错处理 Markdown 格式

AI 模型要求 (AI Model Requirements):
- 必须支持 OpenAI 兼容的 API 接口
- 推荐使用 DeepSeek、GPT-4 等具备强逻辑推理能力的模型
- 需要支持 JSON 格式化输出

作者：NightMend Team
版本：v1.0
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings
from .models import Diagnosis, RemediationAlert

logger = logging.getLogger(__name__)

# AI 诊断系统提示词 - 针对运维修复场景精心设计的 Prompt 工程
# AI Diagnosis System Prompt - Carefully designed prompt engineering for ops remediation scenarios
DIAGNOSIS_SYSTEM_PROMPT = """You are NightMend, an expert SRE diagnostic AI.
Given a monitoring alert and system context, produce a JSON diagnosis.

Your response MUST be valid JSON with these fields:
{
    "root_cause": "concise description of the root cause",
    "confidence": 0.0 to 1.0,
    "suggested_runbook": "runbook_name or null",
    "reasoning": "step by step reasoning"
}

Only set "suggested_runbook" when the name is explicitly known from context. Otherwise return null.
Be precise. High confidence only when evidence is clear. When uncertain, say so."""


def _build_diagnosis_prompt(alert: RemediationAlert, context: dict[str, Any]) -> str:
    """构建 AI 诊断用的用户提示词 (Build User Prompt for AI Diagnosis)
    
    将告警信息和补充上下文组织成结构化的提示词，便于 AI 模型理解和分析。
    Organize alert information and additional context into structured prompts for AI model 
    understanding and analysis.
    
    Args:
        alert: 告警信息对象 (Alert information object)
        context: 补充上下文，如系统指标、日志片段等 (Additional context like metrics, log snippets)
        
    Returns:
        str: 格式化的用户提示词 (Formatted user prompt)
        
    提示词结构 (Prompt Structure):
    - ALERT: 告警摘要信息
    - Host: 发生告警的主机
    - Type: 告警类型分类  
    - Severity: 告警严重程度
    - Labels: 告警标签键值对
    - Additional context: 补充的上下文信息（可选）
    """
    # 构建结构化的告警信息片段 (Build structured alert information segments)
    parts = [
        f"ALERT: {alert.summary()}",  # 告警摘要 (Alert summary)
        f"Host: {alert.host}",  # 主机标识 (Host identifier)
        f"Type: {alert.alert_type}",  # 告警类型 (Alert type)
        f"Severity: {alert.severity}",  # 严重程度 (Severity level)
        f"Labels: {json.dumps(alert.labels)}",  # 标签信息 JSON 格式 (Label info in JSON format)
    ]
    
    # 如果有补充上下文，添加到提示词中 (Add additional context if available)
    if context:
        parts.append(f"Additional context: {json.dumps(context)}")
        
    return "\n".join(parts)  # 用换行符连接所有部分 (Join all parts with newlines)


def _parse_diagnosis_response(text: str) -> Diagnosis:
    """解析 AI 响应为诊断对象 (Parse AI Response to Diagnosis Object)
    
    AI 模型可能返回包含 Markdown 代码块的 JSON，需要清理后再解析。
    AI models may return JSON wrapped in Markdown code blocks, need cleaning before parsing.
    
    Args:
        text: AI 模型的原始响应文本 (Raw response text from AI model)
        
    Returns:
        Diagnosis: 解析后的诊断结果对象 (Parsed diagnosis result object)
        
    处理逻辑 (Processing Logic):
    1. 去除前后空白字符
    2. 检测并清理 Markdown 代码块标记（```json 或 ```）
    3. 解析 JSON 并映射到 Diagnosis 对象
    4. 为缺失字段提供默认值
    
    异常处理 (Exception Handling):
    JSON 解析错误会向上抛出，由调用方处理
    """
    # 清理响应文本，去除前后空白 (Clean response text, remove leading/trailing whitespace)
    cleaned = text.strip()
    
    # 处理 Markdown 代码块包装的 JSON (Handle JSON wrapped in Markdown code blocks)
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # 移除第一行的 ```json 或 ``` 以及结尾的 ``` (Remove first line ```json or ``` and ending ```)
        lines = [line for line in lines[1:] if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # 解析 JSON 数据 (Parse JSON data)
    data = json.loads(cleaned)
    
    # 映射到 Diagnosis 对象，为缺失字段提供默认值 (Map to Diagnosis object with default values)
    return Diagnosis(
        root_cause=data.get("root_cause", "unknown"),  # 根因描述，默认 "unknown"
        confidence=float(data.get("confidence", 0.5)),  # 置信度，默认 0.5
        suggested_runbook=data.get("suggested_runbook"),  # 推荐 Runbook，可为 None
        reasoning=data.get("reasoning", ""),  # 推理过程，默认空字符串
    )


class RemediationLLMClient:
    """修复诊断 AI 客户端 (Remediation Diagnosis AI Client)
    
    这是 NightMend 自动修复系统与 AI 模型交互的核心组件，负责：
    This is the core component for NightMend remediation system to interact with AI models, responsible for:
    
    核心职责 (Core Responsibilities):
    1. 管理 AI API 连接和认证 (Manage AI API connections and authentication)
    2. 构建针对运维场景优化的诊断提示词 (Build ops-optimized diagnosis prompts)
    3. 调用 AI 模型进行智能根因分析 (Call AI models for intelligent root cause analysis)
    4. 解析和验证 AI 响应结果 (Parse and validate AI response results)
    5. 提供 Mock 模式支持测试 (Provide mock mode for testing)
    
    配置来源 (Configuration Source):
    默认从 NightMend 全局配置读取 AI 参数：
    - API Key: settings.ai_api_key
    - API Base URL: settings.ai_api_base (默认 DeepSeek)
    - Model Name: settings.ai_model
    
    支持的 AI 接口 (Supported AI APIs):
    任何兼容 OpenAI Chat Completions API 的服务：DeepSeek、GPT-4、Claude 等
    
    Mock 模式 (Mock Mode):
    用于测试和开发，可预设响应结果，避免实际 AI API 调用
    """

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        timeout: float = 30.0,
        mock_responses: Optional[list[Diagnosis]] = None,
    ) -> None:
        """初始化 AI 诊断客户端 (Initialize AI Diagnosis Client)
        
        Args:
            api_key: AI API 密钥，空则使用全局配置 (AI API key, use global config if empty)
            api_base: API 基础 URL，空则使用全局配置 (API base URL, use global config if empty)
            model: 模型名称，空则使用全局配置 (Model name, use global config if empty)
            timeout: API 调用超时时间，默认 30 秒 (API call timeout, default 30s)
            mock_responses: Mock 响应列表，用于测试 (Mock response list for testing)
            
        设计理念 (Design Philosophy):
        采用配置优先级：显式参数 > 全局配置 > 合理默认值
        支持依赖注入，便于单元测试和不同环境部署
        """
        # 配置优先级：参数 > 全局设置 (Configuration priority: parameter > global settings)
        self.api_key = api_key or settings.ai_api_key
        self.api_base = (api_base or settings.ai_api_base).rstrip("/")  # 移除末尾斜杠 (Remove trailing slash)
        self.model = model or settings.ai_model
        self.timeout = timeout
        
        # Mock 模式配置 (Mock mode configuration)
        self._mock_responses = list(mock_responses) if mock_responses else None  # 复制列表避免外部修改
        self._mock_index = 0  # Mock 响应索引计数器 (Mock response index counter)

    @property
    def is_mock(self) -> bool:
        """判断是否为 Mock 模式 (Check if in mock mode)
        
        Returns:
            bool: True 表示使用预设响应，False 表示调用真实 AI API
        """
        return self._mock_responses is not None

    async def diagnose(
        self, alert: RemediationAlert, context: Optional[dict[str, Any]] = None
    ) -> Diagnosis:
        """执行告警智能诊断 (Execute Intelligent Alert Diagnosis)
        
        这是客户端的核心方法，负责将告警信息发送给 AI 模型进行分析。
        This is the core method of the client, responsible for sending alert information 
        to AI models for analysis.
        
        处理流程 (Processing Flow):
        1. 检查是否为 Mock 模式，如果是则返回预设响应
        2. 构建针对运维场景优化的诊断提示词
        3. 调用 AI API 获取分析结果
        4. 解析 AI 响应并转换为结构化诊断对象
        5. 处理异常情况，返回降级响应
        
        Args:
            alert: 待诊断的告警信息 (Alert information to diagnose)
            context: 补充上下文信息，如系统指标、日志等 (Additional context like metrics, logs)
            
        Returns:
            Diagnosis: 包含根因、置信度、推荐 Runbook 等的诊断结果
            
        异常处理 (Exception Handling):
        AI 调用失败时返回降级诊断，确保系统稳定运行
        """
        context = context or {}  # 确保 context 不为 None (Ensure context is not None)

        # Mock 模式：返回预设的诊断响应 (Mock mode: return preset diagnosis responses)
        if self._mock_responses is not None:
            if self._mock_index < len(self._mock_responses):  # 还有预设响应可用
                result = self._mock_responses[self._mock_index]
                self._mock_index += 1  # 移动到下一个响应 (Move to next response)
                return result
            # 预设响应用尽，返回默认 Mock 响应 (Preset responses exhausted, return default mock response)
            return Diagnosis(
                root_cause="mock diagnosis",
                confidence=0.8,
                suggested_runbook=None,
                reasoning="mock mode",
            )

        # 构建用户提示词，包含告警信息和上下文 (Build user prompt with alert info and context)
        user_prompt = _build_diagnosis_prompt(alert, context)

        # 调用真实 AI API 进行诊断 (Call real AI API for diagnosis)
        try:
            return await self._call_llm(
                system_prompt=DIAGNOSIS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.1,  # 低温度确保输出稳定性 (Low temperature for output stability)
            )
        except Exception as e:
            # AI 调用失败，返回降级诊断确保系统继续运行 (AI call failed, return fallback diagnosis)
            # 置信度设为 0.5，允许通过类型匹配的 Runbook 走 CONFIRM 流程而非 BLOCK
            # Confidence set to 0.5, allowing type-matched Runbooks to go through CONFIRM flow instead of BLOCK
            logger.error("AI diagnosis failed: %s", e)
            return Diagnosis(
                root_cause="AI diagnosis unavailable",
                confidence=0.5,
                suggested_runbook=None,
                reasoning=f"AI call failed: {e}",
            )

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> Diagnosis:
        """调用 OpenAI 兼容的 LLM API (Call OpenAI-Compatible LLM API)
        
        使用标准的 Chat Completions API 格式调用 AI 模型。
        Call AI models using standard Chat Completions API format.
        
        Args:
            system_prompt: 系统提示词，定义 AI 角色和输出格式 (System prompt defining AI role and output format)
            user_prompt: 用户提示词，包含具体的告警信息 (User prompt with specific alert information)
            temperature: 生成温度，控制输出随机性 (Generation temperature controlling output randomness)
            
        Returns:
            Diagnosis: 解析后的诊断结果 (Parsed diagnosis result)
            
        异常 (Exceptions):
            - httpx.HTTPStatusError: HTTP 状态错误（如 401, 429, 500）
            - httpx.TimeoutException: 请求超时
            - json.JSONDecodeError: 响应 JSON 解析失败
            - KeyError: 响应结构异常
            
        API 兼容性 (API Compatibility):
        支持所有兼容 OpenAI Chat Completions API 的服务
        """
        # 创建带超时的异步 HTTP 客户端 (Create async HTTP client with timeout)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 调用 Chat Completions API (Call Chat Completions API)
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",  # Bearer token 认证
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,  # 指定使用的模型 (Specify model to use)
                    "messages": [
                        {"role": "system", "content": system_prompt},  # 系统角色定义
                        {"role": "user", "content": user_prompt},  # 用户查询内容
                    ],
                    "temperature": temperature,  # 控制输出随机性 (Control output randomness)
                    "max_tokens": 1024,  # 限制响应长度 (Limit response length)
                },
            )
            response.raise_for_status()  # 检查 HTTP 状态码，失败时抛出异常
            
            # 解析 API 响应 (Parse API response)
            data = response.json()
            content = data["choices"][0]["message"]["content"]  # 提取 AI 生成的内容
            
            # 解析 AI 响应为结构化诊断对象 (Parse AI response to structured diagnosis object)
            return _parse_diagnosis_response(content)
