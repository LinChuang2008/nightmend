"""
运维记忆系统客户端 (Operations Memory System Client)

升级说明 (v2 - 2026-03-02):
    - store() 新增 memory_type、importance、tags、namespace 参数
    - recall() 新增 namespace 参数，支持命名空间隔离
    - 故障模式存储：importance=7, tags=["fault-pattern", service_name]
"""
import httpx
import logging
from typing import List, Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class MemoryClient:
    """运维记忆系统客户端类"""

    @property
    def _base_url(self) -> str:
        return settings.memory_api_url

    @property
    def _enabled(self) -> bool:
        return settings.memory_enabled

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        namespace: str = "nightmend",
    ) -> List[Dict[str, Any]]:
        """
        记忆召回接口 (Memory Recall Interface)

        Args:
            query: 搜索查询文本，支持自然语言（如"CPU使用率过高"）
            top_k: 返回最相关的记忆条数，默认5条
            namespace: 记忆命名空间，默认"nightmend"

        Returns:
            List[Dict[str, Any]]: 相关记忆列表，失败时返回空列表
        """
        if not self._enabled:
            return []

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self._base_url}/recall",
                    json={"query": query, "top_k": top_k, "namespace": namespace},
                )
                resp.raise_for_status()
                data = resp.json()

                if isinstance(data, list):
                    return data
                return data.get("memories", data.get("results", []))

        except Exception as e:
            logger.debug("记忆召回失败（不影响主流程）: %s", str(e))
            return []

    async def store(
        self,
        content: str,
        source: str = "nightmend",
        memory_type: str = "episode",
        importance: int = 5,
        tags: Optional[List[str]] = None,
        namespace: str = "nightmend",
    ) -> bool:
        """
        记忆存储接口 (Memory Storage Interface)

        Args:
            content: 要存储的文本内容
            source: 来源标识（默认"nightmend"）
            memory_type: 记忆类型 episode/fact/lesson（默认"episode"）
            importance: 重要性评分 1-10（默认5）
            tags: 标签列表，如 ["fault-pattern", "nginx"]
            namespace: 记忆命名空间（默认"nightmend"）

        Returns:
            bool: 存储是否成功
        """
        if not self._enabled:
            return False

        try:
            payload: Dict[str, Any] = {
                "content": content,
                "source": source,
                "memory_type": memory_type,
                "importance": importance,
                "namespace": namespace,
            }
            if tags:
                payload["tags"] = tags

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self._base_url}/store",
                    json=payload,
                )
                resp.raise_for_status()
                return True

        except Exception as e:
            logger.debug("记忆存储失败（不影响主流程）: %s", str(e))
            return False


# 模块级单例实例
memory_client = MemoryClient()
