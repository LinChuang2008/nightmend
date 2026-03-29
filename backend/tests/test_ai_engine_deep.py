"""LLM 客户端深度测试 — mock API，覆盖 chat_completion 和 analyze_logs_brief。"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.llm_client import chat_completion, analyze_logs_brief, LLMClientError


def _mock_httpx_response(content: str):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    resp.raise_for_status = MagicMock()
    return resp


class TestChatCompletion:
    @patch("app.services.llm_client.settings")
    @pytest.mark.asyncio
    async def test_no_api_key_raises(self, mock_settings):
        mock_settings.ai_api_key = ""
        with pytest.raises(LLMClientError, match="AI API Key 未配置"):
            await chat_completion([{"role": "user", "content": "hi"}])

    @patch("httpx.AsyncClient.post")
    @patch("app.services.llm_client.settings")
    @pytest.mark.asyncio
    async def test_success(self, mock_settings, mock_post):
        mock_settings.ai_api_key = "test-key"
        mock_settings.ai_api_base = "https://api.example.com"
        mock_settings.ai_model = "test-model"
        mock_settings.environment = "test"

        mock_post.return_value = _mock_httpx_response('{"answer": "hello"}')

        result = await chat_completion([{"role": "user", "content": "hi"}])
        assert result == '{"answer": "hello"}'

    @patch("httpx.AsyncClient.post")
    @patch("app.services.llm_client.settings")
    @pytest.mark.asyncio
    async def test_custom_params(self, mock_settings, mock_post):
        mock_settings.ai_api_key = "test-key"
        mock_settings.ai_api_base = "https://api.example.com"
        mock_settings.ai_model = "test-model"
        mock_settings.environment = "test"

        mock_post.return_value = _mock_httpx_response("ok")

        result = await chat_completion(
            [{"role": "user", "content": "hi"}],
            max_tokens=500,
            temperature=0.1,
        )
        assert result == "ok"
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["max_tokens"] == 500
        assert payload["temperature"] == 0.1

    @patch("httpx.AsyncClient.post")
    @patch("app.services.llm_client.settings")
    @pytest.mark.asyncio
    async def test_http_error_propagates(self, mock_settings, mock_post):
        mock_settings.ai_api_key = "test-key"
        mock_settings.ai_api_base = "https://api.example.com"
        mock_settings.ai_model = "test-model"
        mock_settings.environment = "test"

        import httpx
        mock_post.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock()
        )
        with pytest.raises(httpx.HTTPStatusError):
            await chat_completion([{"role": "user", "content": "hi"}])


class TestAnalyzeLogsBrief:
    @patch("app.services.llm_client.chat_completion", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_success(self, mock_chat):
        mock_chat.return_value = json.dumps({
            "title": "High error rate",
            "summary": "Found OOM errors",
            "severity": "warning",
        })
        result = await analyze_logs_brief([
            {"timestamp": "2026-01-01", "level": "ERROR", "message": "OOM"}
        ])
        assert result["title"] == "High error rate"
        assert result["severity"] == "warning"

    @patch("app.services.llm_client.chat_completion", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_markdown_wrapped_json(self, mock_chat):
        mock_chat.return_value = '```json\n{"title": "test", "summary": "ok", "severity": "info"}\n```'
        result = await analyze_logs_brief([{"timestamp": "t", "level": "INFO", "message": "ok"}])
        assert result["title"] == "test"
        assert result["severity"] == "info"

    @patch("app.services.llm_client.chat_completion", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_api_error_returns_fallback(self, mock_chat):
        mock_chat.side_effect = Exception("API down")
        result = await analyze_logs_brief([{"timestamp": "t", "level": "ERROR", "message": "err"}])
        assert "error" in result
        assert result["severity"] == "warning"

    @patch("app.services.llm_client.chat_completion", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_invalid_json_returns_fallback(self, mock_chat):
        mock_chat.return_value = "not valid json"
        result = await analyze_logs_brief([{"timestamp": "t", "level": "ERROR", "message": "err"}])
        assert "error" in result

    @patch("app.services.llm_client.chat_completion", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_truncates_logs_to_200(self, mock_chat):
        mock_chat.return_value = json.dumps({"title": "ok", "summary": "ok", "severity": "info"})
        logs = [{"timestamp": "t", "level": "ERROR", "message": f"msg{i}"} for i in range(300)]
        await analyze_logs_brief(logs)
        call_args = mock_chat.call_args[0][0]
        user_content = call_args[1]["content"]
        assert "msg199" in user_content
        assert "msg200" not in user_content

    @patch("app.services.llm_client.chat_completion", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_missing_fields_use_defaults(self, mock_chat):
        mock_chat.return_value = json.dumps({})
        result = await analyze_logs_brief([{"timestamp": "t", "level": "INFO", "message": "ok"}])
        assert result["title"] == "日志异常扫描结果"
        assert result["severity"] == "info"
