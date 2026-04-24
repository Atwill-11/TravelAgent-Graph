"""旅游规划长期记忆管理器。

该模块实现了旅游规划的长期记忆功能：
- 使用 AsyncPostgresStore 进行向量化存储
- 从 TripRequest 中提取个性化字段
- 提供语义搜索功能，检索相关历史规划
"""

import time
import hashlib
from typing import Optional

from langchain_community.embeddings import DashScopeEmbeddings
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.logging import logger
from app.schemas.travel.request import TripRequest


class TravelMemoryManager:
    """旅游规划长期记忆管理器，使用 AsyncPostgresStore + 向量搜索实现。"""
    
    def __init__(self):
        self.store: Optional[AsyncPostgresStore] = None
        self._connection_pool: Optional[AsyncConnectionPool] = None
        self.embeddings = DashScopeEmbeddings(
            dashscope_api_key=settings.DASHSCOPE_API_KEY,
            model="text-embedding-v4"
        )
        logger.info("TravelMemoryManager 初始化成功", model="text-embedding-v4")

    async def _get_store(self, connection_pool: AsyncConnectionPool) -> AsyncPostgresStore:
        """获取或创建存储实例（启用向量索引）。"""
        if self.store is None:
            self._connection_pool = connection_pool
            
            index_config = {
                "dims": 1024,
                "embed": self.embeddings,
                "fields": ["content"]
            }
            
            try:
                store = AsyncPostgresStore(
                    connection_pool,
                    index=index_config
                )
                
                await store.setup()
                self.store = store
                logger.info("TravelMemory AsyncPostgresStore 初始化成功 (已启用向量搜索)")
            except Exception as e:
                logger.error("TravelMemory AsyncPostgresStore 初始化失败", error=str(e), exc_info=True)
                raise
            
        return self.store

    async def get_relevant_plans(
        self,
        user_id: str,
        current_request: TripRequest,
        session_id: Optional[str] = None
    ) -> str:
        """获取与用户当前规划相关的历史规划（语义搜索）。
        
        Args:
            user_id: 用户ID
            current_request: 当前的旅行请求
            session_id: 会话ID（可选，如果提供则优先搜索该会话的记忆）
            
        Returns:
            相关历史规划的文本描述
        """
        try:
            if self.store is None:
                return ""
            
            query = self._build_search_query(current_request)
            memories = []
            
            # 如果提供了 session_id，优先搜索该会话的记忆
            if session_id:
                try:
                    results = await self.store.asearch(
                        ("travel_plans", str(user_id), session_id),
                        query=query,
                        limit=3
                    )
                    for item in results:
                        memory_text = self._format_memory_item(item, "当前会话")
                        if memory_text:
                            memories.append(memory_text)
                except Exception as e:
                    logger.warning("搜索会话记忆失败", session_id=session_id, error=str(e))
            
            # 如果会话记忆不足，再搜索用户所有会话的记忆
            if len(memories) < 3:
                try:
                    results = await self.store.asearch(
                        ("travel_plans", str(user_id)),
                        query=query,
                        limit=5
                    )
                    for item in results:
                        memory_text = self._format_memory_item(item, "历史会话")
                        if memory_text and memory_text not in memories:
                            memories.append(memory_text)
                            if len(memories) >= 5:
                                break
                except Exception as e:
                    logger.warning("搜索用户历史记忆失败", user_id=user_id, error=str(e))
            
            if not memories:
                return ""
            
            logger.info(
                "获取相关历史规划成功",
                user_id=user_id,
                session_id=session_id,
                query=query,
                count=len(memories)
            )
            return "\n\n".join(memories)
            
        except Exception as e:
            logger.error(
                "获取相关历史规划失败",
                error=str(e),
                user_id=user_id,
                session_id=session_id,
                query=query if 'query' in locals() else None
            )
            return ""

    def _format_memory_item(self, item: any, source: str = "历史") -> Optional[str]:
        """格式化记忆项为文本。
        
        Args:
            item: 记忆项
            source: 记忆来源标签
            
        Returns:
            格式化后的记忆文本，如果无效则返回 None
        """
        value = item.value if hasattr(item, 'value') else item
        if isinstance(value, dict):
            content = value.get("content", "")
            if not isinstance(content, str):
                content = str(content)

            if not content:
                return None

            timestamp = value.get("timestamp")
            time_str = ""
            if timestamp and isinstance(timestamp, (int, float)) and timestamp > 0:
                try:
                    time_str = time.strftime("%Y-%m-%d", time.localtime(timestamp / 1000))
                except (ValueError, OSError):
                    time_str = ""
            
            city = value.get("city", "")
            preferences = value.get("preferences", [])
            
            memory_text = f"[{source}] 历史规划({time_str}): {content}"
            if city:
                memory_text += f"\n  目的地: {city}"
            if preferences:
                memory_text += f"\n  偏好: {', '.join(preferences)}"
            
            return memory_text
        elif isinstance(value, str):
            return f"[{source}] {value}"
        return None

    async def save_plan_request(
        self,
        user_id: str,
        request: TripRequest,
        plan_summary: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """保存用户的规划请求到长期记忆。
        
        Args:
            user_id: 用户ID
            request: 旅行请求
            plan_summary: 规划结果摘要（可选）
            session_id: 会话ID（可选，如果提供则存储到会话专属命名空间）
        """
        try:
            if self.store is None:
                logger.warning("Store 未初始化，无法保存规划请求")
                return
            
            content = self._extract_memory_content(request, plan_summary)
            
            if not content or len(content.strip()) < 10:
                logger.debug("规划请求内容过短，跳过存储")
                return
            
            timestamp = int(time.time() * 1000)
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            key = f"{timestamp}_{content_hash}"
            
            memory_data = {
                "content": content,
                "timestamp": timestamp,
                "city": request.city,
                "travel_days": request.travel_days,
                "preferences": request.preferences,
                "transportation": request.transportation,
                "accommodation": request.accommodation,
                "session_id": session_id,
            }
            
            # 如果提供了 session_id，存储到会话专属命名空间
            # 同时也存储到用户全局命名空间，便于跨会话搜索
            if session_id:
                await self.store.aput(
                    ("travel_plans", str(user_id), session_id),
                    key,
                    memory_data
                )
                logger.info(
                    "规划请求保存到会话命名空间",
                    user_id=user_id,
                    session_id=session_id,
                    city=request.city,
                    days=request.travel_days
                )
            
            # 同时存储到用户全局命名空间
            await self.store.aput(
                ("travel_plans", str(user_id)),
                key,
                memory_data
            )
            
            logger.info(
                "规划请求保存成功",
                user_id=user_id,
                session_id=session_id,
                city=request.city,
                days=request.travel_days
            )
            
        except Exception as e:
            logger.exception(
                "保存规划请求失败",
                user_id=user_id,
                session_id=session_id,
                error=str(e)
            )

    def _build_search_query(self, request: TripRequest) -> str:
        """构建语义搜索查询字符串。
        
        Args:
            request: 当前旅行请求
            
        Returns:
            查询字符串
        """
        query_parts = [f"{request.city}旅游"]
        
        if request.preferences:
            query_parts.extend(request.preferences)
        
        if request.free_text_input:
            query_parts.append(request.free_text_input)
        
        return " ".join(query_parts)

    def _extract_memory_content(
        self,
        request: TripRequest,
        plan_summary: Optional[str] = None
    ) -> str:
        """从 TripRequest 中提取用于存储的记忆内容。
        
        Args:
            request: 旅行请求
            plan_summary: 规划结果摘要
            
        Returns:
            记忆内容字符串
        """
        parts = []
        
        parts.append(f"目的地: {request.city}")
        parts.append(f"行程: {request.travel_days}天")
        
        if request.preferences:
            parts.append(f"偏好: {', '.join(request.preferences)}")
        
        if request.transportation:
            parts.append(f"交通: {request.transportation}")
        
        if request.accommodation:
            parts.append(f"住宿: {request.accommodation}")
        
        if request.free_text_input:
            parts.append(f"特殊要求: {request.free_text_input}")
        
        if plan_summary:
            parts.append(f"规划结果: {plan_summary[:200]}")
        
        return " | ".join(parts)