"""LLM 客户端服务测试（mock DeepSeek API）。"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.llm_client import chat_completion, LLMClientError


_MOCK_CONFIG = {
    "base_url": "https://api.example.com",
    "model": "test-model",
    "api_key": "test-key",
}

_MOCK_CONFIG_NO_KEY = {
    "base_url": "https://api.example.com",
    "model": "test-model",
    "api_key": "",
}


class TestLLMClient:
    @patch("app.services.llm_client._load_ai_runtime_config", new_callable=AsyncMock, return_value=_MOCK_CONFIG_NO_KEY)
    @pytest.mark.asyncio
    async def test_chat_completion_missing_key_raises(self, mock_cfg):
        with pytest.raises(LLMClientError, match="AI API Key 未配置"):
            await chat_completion([{"role": "user", "content": "hi"}])

    @patch("httpx.AsyncClient.post")
    @patch("app.services.llm_client._load_ai_runtime_config", new_callable=AsyncMock, return_value=_MOCK_CONFIG)
    @patch("app.services.llm_client.settings")
    @pytest.mark.asyncio
    async def test_chat_completion_success(self, mock_settings, mock_cfg, mock_post):
        mock_settings.environment = "test"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"summary": "All normal"}'}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = await chat_completion([{"role": "user", "content": "test"}])
        assert result == '{"summary": "All normal"}'
        mock_post.assert_called_once()
