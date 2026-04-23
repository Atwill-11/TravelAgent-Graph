"""本文件包含基于 LangChain create_agent API 的生产级 Agent 实现。

提供以下核心功能：
- 基于 create_agent 的标准化 ReAct Agent 构建
- 状态持久化机制（PostgreSQL + AsyncPostgresSaver）
- 长期记忆功能（mem0 集成）
- 可观测性设计（Langfuse + Prometheus）
- 高可用与降级策略
- 自定义图扩展接口
"""
import os
import asyncio
import time
import hashlib
from typing import (
    Any,
    AsyncGenerator,
    Literal,
    Optional,
    TypedDict,
)
# 导入urllib.parse.quote_plus函数，用于对URL中的特殊字符进行编码
# 避免在数据库连接字符串中直接使用特殊字符，导致解析错误
from urllib.parse import quote_plus

# 导入asgiref.sync.sync_to_async函数，用于将同步函数转换为异步函数
from asgiref.sync import sync_to_async
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ToolCallRequest,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langfuse import get_client, propagate_attributes
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import AsyncPostgresStore
from langchain_community.embeddings import DashScopeEmbeddings
from langgraph.types import RunnableConfig, StateSnapshot
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from app.core.config import Environment, settings
from app.core.langgraph.tools import tools
from app.core.logging import logger
from app.core.prompts import load_system_prompt
from app.schemas import Message, AgentContext, CustomAgentState
from app.services.llm import llm_service
from app.utils import dump_messages, prepare_messages, process_llm_response


class LongTermMemoryMiddleware(AgentMiddleware):
    """长期记忆中间件，在模型调用前注入相关记忆。"""

    state_schema = CustomAgentState

    def __init__(self):
        pass

    def before_model(self, state: CustomAgentState, runtime) -> Optional[dict]:
        """在模型调用前从状态中读取长期记忆并注入到消息列表。"""
        try:
            long_term_memory = state.get("long_term_memory", "")
            
            if not long_term_memory or long_term_memory == "未找到相关记忆":
                return None
            
            messages = state.get("messages", [])
            if not messages:
                return None
            
            from langchain_core.messages import SystemMessage
            
            system_message_index = None
            for i, msg in enumerate(messages):
                if isinstance(msg, SystemMessage):
                    system_message_index = i
                    break
            
            new_messages = None
            if system_message_index is not None:
                existing_system_content = messages[system_message_index].content
                if long_term_memory not in existing_system_content:
                    new_content = f"{existing_system_content}\n\n# 用户长期记忆\n{long_term_memory}"
                    new_messages = messages.copy()
                    new_messages[system_message_index] = SystemMessage(content=new_content)
            else:
                system_content = f"# 用户长期记忆\n{long_term_memory}"
                new_messages = [SystemMessage(content=system_content)] + messages
            
            if new_messages:
                logger.info(
                    "长期记忆注入成功",
                    user_id=state.get("user_id"),
                    memory_length=len(long_term_memory)
                )
                return {"messages": new_messages}
            
        except Exception as e:
            logger.error(
                "长期记忆注入失败",
                error=str(e),
                user_id=state.get("user_id") if state else None
            )
        
        return None


class ToolErrorHandlingMiddleware(AgentMiddleware):
    """工具错误处理中间件，提供优雅降级。"""

    @wrap_tool_call
    async def handle_tool_errors(self, request: ToolCallRequest, handler):
        """处理工具执行错误，返回友好错误消息给模型。"""
        try:
            return await handler(request)
        except Exception as e:
            logger.error(
                "工具执行失败",
                tool_name=request.tool_call["name"],
                error=str(e),
                session_id=request.runtime.context.session_id if request.runtime else "unknown",
            )
            return ToolMessage(
                content=f"工具执行失败：{str(e)}。请尝试其他方法或告知用户暂时无法完成此操作。",
                tool_call_id=request.tool_call["id"],
            )

class MemoryManager:
    """长期记忆管理器，使用 AsyncPostgresStore + 向量搜索实现。"""
    
    def __init__(self):
        self.store: Optional[AsyncPostgresStore] = None
        self._connection_pool: Optional[AsyncConnectionPool] = None
        # 🔴 [新增] 初始化嵌入模型
        self.embeddings = DashScopeEmbeddings(
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"), 
            model="text-embedding-v4"
        )
        logger.info("DashScope Embeddings 初始化成功", model="text-embedding-v4")

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
                logger.info("AsyncPostgresStore 初始化成功 (已启用向量搜索)")
            except Exception as e:
                logger.error("AsyncPostgresStore 初始化失败", error=str(e), exc_info=True)
                raise
            
        return self.store

    async def get_relevant_memory(self, user_id: str, query: str) -> str:
        """获取与用户及查询相关的长期记忆 (语义搜索)。"""
        try:
            if self.store is None:
                return ""
            
            # 🔴 [优化] 使用 asearch 进行向量相似度搜索
            # query: 用户的当前问题，会被自动向量化
            # limit: 返回最相关的 Top 5 条记忆
            results = await self.store.asearch(
                ("memories", str(user_id)),  # Namespace
                query=query,            # 语义查询字符串
                limit=5
            )
            
            if not results:
                return ""
            
            # 提取记忆内容并格式化
            memories = []
            for item in results:
                value = item.value
                if isinstance(value, dict):
                    content = value.get("content", "")
                    if not isinstance(content, str):
                        content = str(content)

                    if content:
                        timestamp = value.get("timestamp")
                        time_str = ""
                        if timestamp and isinstance(timestamp, (int, float)) and timestamp > 0:
                            try:
                                time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp / 1000))
                            except (ValueError, OSError):
                                time_str = ""
                        memories.append(f"[{time_str}] {content}" if time_str else content)
                elif isinstance(value, str):
                    memories.append(value)
            
            if not memories:
                return ""
                
            # ✅ 再次确保所有元素都是字符串 (防御性编程)
            safe_memories = [str(m) for m in memories]
            logger.info("获取相关记忆成功 (向量搜索)", user_id=user_id, query=query, memories=safe_memories)
            return "\n".join(safe_memories)
            
        except Exception as e:
            logger.error("获取相关记忆失败 (向量搜索)", error=str(e), user_id=user_id, query=query)
            return ""

    async def update_memory(self, user_id: str, messages: list[dict], metadata: dict = None) -> None:
        """更新长期记忆 (自动向量化存储)。"""
        try:
            if self.store is None:
                logger.warning("Store 未初始化，无法更新记忆")
                return
            
            # 从消息中提取记忆内容
            for message in messages:
                if message.get("role") == "user":
                    content = message.get("content", "")
                    if not content or len(content.strip()) < 5: 
                        # 过滤掉过短的无意义消息（如"好的", "嗯"）
                        continue
                    
                    # 创建记忆键
                    timestamp = int(time.time() * 1000)
                    content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
                    key = f"{timestamp}_{content_hash}"
                    
                    # 🔴 [关键] 存储结构必须包含 'content' 字段，因为我们在 index 配置中指定了 fields=["content"]
                    memory_data = {
                        "content": content,
                        "timestamp": timestamp,
                        "metadata": metadata or {}
                    }
                    
                    # 写入 Store
                    # 注意：只要 Store 初始化时配置了 index，aput 会自动调用 embed 函数向量化 "content" 字段
                    await self.store.aput(
                        ("memories", str(user_id)), 
                        key,                   
                        memory_data            
                    )
            
            logger.info("长期记忆更新成功 (已向量化)", user_id=user_id)
            
        except Exception as e:
            logger.exception("长期记忆更新失败", user_id=user_id, error=str(e))


class ConnectionPoolManager:
    """数据库连接池管理器，提供高可用连接管理。"""

    def __init__(self):
        self._connection_pool: Optional[AsyncConnectionPool] = None

    async def get_pool(self) -> Optional[AsyncConnectionPool]:
        """获取或创建连接池。"""
        if self._connection_pool is None:
            try:
                max_size = settings.POSTGRES_POOL_SIZE

                connection_url = (
                    "postgresql://"
                    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )

                self._connection_pool = AsyncConnectionPool(
                    connection_url,
                    open=False,
                    max_size=max_size,
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": 5,
                        "prepare_threshold": None,
                    },
                )
                await self._connection_pool.open()
                logger.info("连接池创建成功", max_size=max_size, environment=settings.ENVIRONMENT.value)
            except Exception as e:
                logger.error("连接池创建失败", error=str(e), environment=settings.ENVIRONMENT.value)
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("生产环境：连接池不可用，继续运行", environment=settings.ENVIRONMENT.value)
                    return None
                raise e
        return self._connection_pool

    async def clear_session(self, session_id: str) -> None:
        """清空指定会话的检查点数据。"""
        try:
            conn_pool = await self.get_pool()
            if not conn_pool:
                logger.warning("连接池不可用，无法清空会话", session_id=session_id)
                return

            async with conn_pool.connection() as conn:
                for table in settings.CHECKPOINT_TABLES:
                    try:
                        await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (session_id,))
                        logger.info(f"已清空表 {table} 中会话 {session_id} 的记录")
                    except Exception as e:
                        logger.error(f"清空表 {table} 时发生错误", error=str(e))
        except Exception as e:
            logger.error("清空会话失败", session_id=session_id, error=str(e))
            raise


class GraphBuilderFactory:
    """图构建工厂，提供标准化的图构建接口。"""

    @staticmethod
    async def create_default_react_graph(
        model,
        tools: list,
        system_prompt: Optional[str] = None,
        checkpointer: Optional[AsyncPostgresSaver] = None,
        middleware: Optional[list[AgentMiddleware]] = None,
        state_schema: Optional[type] = None,
        name: Optional[str] = None,
    ) -> CompiledStateGraph:
        """创建默认 ReAct 模式的图。

        参数:
            model: LLM 模型实例
            tools: 工具列表
            system_prompt: 系统提示词
            checkpointer: 状态持久化检查点器
            middleware: 中间件列表
            state_schema: 自定义状态 Schema
            name: 图的名称

        返回:
            CompiledStateGraph: 编译后的状态图实例
        """
        try:
            if checkpointer:
                await checkpointer.setup()

            graph = create_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
                middleware=middleware or [],
                state_schema=state_schema or CustomAgentState,
                checkpointer=checkpointer,
                name=name or "default-agent",
            )

            logger.info(
                "工作流创建成功",
                agent_name=name or "default-agent",
                environment=settings.ENVIRONMENT.value,
                has_checkpointer=checkpointer is not None,
            )

            return graph
        except Exception as e:
            logger.error("工作流创建失败", error=str(e), environment=settings.ENVIRONMENT.value)
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                logger.warning("生产环境：工作流不可用，继续运行")
                return None
            raise e

    @staticmethod
    async def create_custom_graph(
        base_graph: StateGraph,
        checkpointer: Optional[AsyncPostgresSaver] = None,
        name: Optional[str] = None,
    ) -> CompiledStateGraph:
        """创建自定义图，集成生产级特性。

        参数:
            base_graph: 基础 StateGraph 实例
            checkpointer: 状态持久化检查点器
            name: 图的名称

        返回:
            CompiledStateGraph: 编译后的状态图实例
        """
        try:
            if checkpointer:
                await checkpointer.setup()

            compiled_graph = base_graph.compile(
                checkpointer=checkpointer,
                name=name or f"{settings.PROJECT_NAME} Custom Graph ({settings.ENVIRONMENT.value})",
            )

            logger.info(
                "自定义工作流创建成功",
                graph_name=name or "custom-graph",
                environment=settings.ENVIRONMENT.value,
                has_checkpointer=checkpointer is not None,
            )

            return compiled_graph
        except Exception as e:
            logger.error("自定义工作流创建失败", error=str(e), environment=settings.ENVIRONMENT.value)
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                logger.warning("生产环境：自定义工作流不可用，继续运行")
                return None
            raise e


class LangGraphAgent:
    """基于 LangChain create_agent API 的生产级 Agent。

    该类负责：
    - 使用 create_agent 创建标准化 ReAct Agent
    - 管理状态持久化、长期记忆、可观测性等生产级特性
    - 提供统一的图扩展接口
    """

    def __init__(self):
        """初始化 Agent 及所需组件。"""
        self.llm_service = llm_service
        self.tools_by_name = {tool.name: tool for tool in tools}

        self._connection_pool_manager = ConnectionPoolManager()
        self._memory_manager = MemoryManager()
        self._graph: Optional[CompiledStateGraph] = None

        logger.info(
            "LangGraph Agent 初始化成功",
            model=settings.DEFAULT_LLM_MODEL,
            environment=settings.ENVIRONMENT.value,
        )

    async def _get_connection_pool(self) -> Optional[AsyncConnectionPool]:
        """获取数据库连接池。"""
        return await self._connection_pool_manager.get_pool()

    async def _get_relevant_memory(self, user_id: str, query: str) -> str:
        """获取相关长期记忆。"""
        return await self._memory_manager.get_relevant_memory(user_id, query)

    async def _update_long_term_memory(self, user_id: str, messages: list[dict], metadata: dict = None) -> None:
        """更新长期记忆。"""
        await self._memory_manager.update_memory(user_id, messages, metadata)

    async def _create_middleware(self) -> list[AgentMiddleware]:
        """创建 Agent 中间件列表。"""
        # 确保 store 已初始化
        connection_pool = await self._get_connection_pool()
        if connection_pool:
            await self._memory_manager._get_store(connection_pool)
        
        return [
            LongTermMemoryMiddleware(),
            ToolErrorHandlingMiddleware(),
        ]

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """创建并配置 LangGraph 工作流。

        使用 create_agent API 创建默认 ReAct 模式的图，集成：
        - 状态持久化（AsyncPostgresSaver）
        - 长期记忆（AsyncPostgresStore）
        - 可观测性（Langfuse + Prometheus）
        - 错误处理与降级策略

        返回:
            Optional[CompiledStateGraph]: 配置完成的 LangGraph 实例
        """
        if self._graph is None:
            try:
                connection_pool = await self._get_connection_pool()
                checkpointer = AsyncPostgresSaver(connection_pool) if connection_pool else None

                middleware = await self._create_middleware()

                current_llm = self.llm_service.get_llm()
                model_name = (
                    current_llm.model_name
                    if current_llm and hasattr(current_llm, "model_name")
                    else settings.DEFAULT_LLM_MODEL
                )

                self._graph = await GraphBuilderFactory.create_default_react_graph(
                    model=current_llm,
                    tools=tools,
                    system_prompt=load_system_prompt(),
                    checkpointer=checkpointer,
                    middleware=middleware,
                    state_schema=CustomAgentState,
                    name=f"{settings.PROJECT_NAME} Agent",
                )

                return self._graph
            except Exception as e:
                logger.error("工作流创建失败", error=str(e), environment=settings.ENVIRONMENT.value)
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("生产环境：工作流不可用，继续运行")
                    return None
                raise e

        return self._graph

    async def create_custom_graph(
        self,
        base_graph: StateGraph,
        name: Optional[str] = None,
    ) -> Optional[CompiledStateGraph]:
        """创建自定义图，集成生产级特性。

        参数:
            base_graph: 基础 StateGraph 实例
            name: 图的名称

        返回:
            Optional[CompiledStateGraph]: 编译后的状态图实例
        """
        try:
            connection_pool = await self._get_connection_pool()
            checkpointer = AsyncPostgresSaver(connection_pool) if connection_pool else None

            # 🔧 新增：确保 memory store 已初始化
            if connection_pool:
                await self._memory_manager._get_store(connection_pool)

            self._graph = await GraphBuilderFactory.create_custom_graph(
                base_graph=base_graph,
                checkpointer=checkpointer,
                name=name,
            )

            return self._graph
        except Exception as e:
            logger.error("自定义图创建失败", error=str(e))
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                logger.warning("生产环境：自定义图不可用，继续运行")
                return None
            raise e

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """获取 LLM 的响应。

        参数:
            messages: 发送给 LLM 的消息列表
            session_id: 会话 ID
            user_id: 用户 ID

        返回:
            list[dict]: LLM 的响应内容
        """
        # 确保 user_id 是字符串类型，langfuse只接受user_id为字符串
        safe_user_id = str(user_id) if user_id is not None else None

        if self._graph is None:
            self._graph = await self.create_graph()

        # 准备属性字典，过滤掉 None 值
        trace_attributes = {}
        if user_id:
            trace_attributes["user_id"] = safe_user_id
        if session_id:
            trace_attributes["session_id"] = session_id
        
        # 添加环境信息到 Metadata (可选，但推荐)
        trace_attributes["metadata"] = {
            "environment": settings.ENVIRONMENT.value,
            "debug": str(settings.DEBUG).lower(),
        }

        try:
            # 使用上下文管理器包裹整个调用过程
            with propagate_attributes(**trace_attributes):
                
                # CallbackHandler 不再需要传入 user_id/session_id/environment
                # 它会自动从上面的 propagate_attributes 上下文中获取
                config = {
                    "configurable": {"thread_id": session_id},
                    "callbacks": [CallbackHandler()], 
                    # metadata 依然可以保留，用于传递给 LangChain 内部或其他回调
                    "metadata": trace_attributes.get("metadata", {}),
                }

                relevant_memory = await self._get_relevant_memory(user_id, messages[-1].content) if user_id else ""

                response = await self._graph.ainvoke(
                    input={
                        "messages": dump_messages(messages),
                        "long_term_memory": relevant_memory or "未找到相关记忆",
                        "user_id": user_id,
                        "session_id": session_id,
                    },
                    config=config,
                )

                if user_id:
                    asyncio.create_task(
                        self._update_long_term_memory(
                            user_id,
                            convert_to_openai_messages(response["messages"]),
                            config["metadata"],
                        )
                    )

                return self.__process_messages(response["messages"])
                
        except Exception as e:
            logger.error("获取响应时发生错误", error=str(e), session_id=session_id)
            raise

    async def get_stream_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """获取 LLM 的流式响应。

        参数:
            messages: 发送给 LLM 的消息列表
            session_id: 会话 ID
            user_id: 用户 ID

        生成:
            str: LLM 响应的文本片段
        """
        # 确保 user_id 是字符串类型，langfuse只接受user_id为字符串
        safe_user_id = str(user_id) if user_id is not None else None

        if self._graph is None:
            self._graph = await self.create_graph()

        trace_attributes = {}
        if user_id:
            trace_attributes["user_id"] = safe_user_id
        if session_id:
            trace_attributes["session_id"] = session_id
            
        trace_attributes["metadata"] = {
            "environment": settings.ENVIRONMENT.value,
            "debug": str(settings.DEBUG).lower(),
        }

        try:
            # 使用上下文管理器
            with propagate_attributes(**trace_attributes):
                
                # 简化 CallbackHandler 初始化
                config = {
                    "configurable": {"thread_id": session_id},
                    "callbacks": [CallbackHandler()],
                    "metadata": trace_attributes.get("metadata", {}),
                }

                relevant_memory = await self._get_relevant_memory(user_id, messages[-1].content) if user_id else ""

                async for token, _ in self._graph.astream(
                    {
                        "messages": dump_messages(messages),
                        "long_term_memory": relevant_memory or "未找到相关记忆",
                        "user_id": user_id,
                        "session_id": session_id,
                    },
                    config,
                    stream_mode="messages",
                ):
                    try:
                        yield token.content
                    except Exception as token_error:
                        logger.error("处理响应片段时出错", error=str(token_error), session_id=session_id)
                        continue

                state: StateSnapshot = await sync_to_async(self._graph.get_state)(config=config)
                if state.values and "messages" in state.values and user_id:
                    asyncio.create_task(
                        self._update_long_term_memory(
                            user_id,
                            convert_to_openai_messages(state.values["messages"]),
                            config["metadata"],
                        )
                    )
                    
        except Exception as stream_error:
            logger.error("流式处理过程中发生错误", error=str(stream_error), session_id=session_id)
            raise
    async def get_chat_history(self, session_id: str) -> list[Message]:
        """获取指定会话的聊天历史。

        参数:
            session_id: 会话 ID

        返回:
            list[Message]: 聊天历史消息列表
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        state: StateSnapshot = await sync_to_async(self._graph.get_state)(
            config={"configurable": {"thread_id": session_id}}
        )
        return self.__process_messages(state.values["messages"]) if state.values else []

    def __process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        """将原始消息转换为项目标准 Message 列表。

        参数:
            messages: LangGraph 状态中的原始消息列表

        返回:
            清洗后的项目 Message 对象列表
        """
        openai_style_messages = convert_to_openai_messages(messages)
        return [
            Message(role=message["role"], content=str(message["content"]))
            for message in openai_style_messages
            if message["role"] in ["assistant", "user"] and message["content"]
        ]

    async def clear_chat_history(self, session_id: str) -> None:
        """清空指定会话的全部聊天历史。

        参数:
            session_id: 会话 ID
        """
        await self._connection_pool_manager.clear_session(session_id)
