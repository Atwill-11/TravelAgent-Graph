"""集中式资源生命周期管理器。

统一管理应用中所有需要生命周期管理的资源，包括：
1. 数据库连接池（SQLAlchemy Engine）
2. psycopg异步连接池（AsyncConnectionPool）
3. LangGraph检查点器（AsyncPostgresSaver）
4. 旅游记忆管理器（TravelMemoryManager）
5. RAG流水线（RAGPipeline + PGEngine）
6. MCP客户端（MultiServerMCPClient）
7. Langfuse可观测性平台
8. 共享嵌入模型（DashScopeEmbeddings）

所有资源的初始化和清理都在此处集中管理，
通过FastAPI的lifespan机制确保资源的正确创建和释放。

资源初始化顺序（按依赖关系）：
  DatabaseService → Langfuse → Embeddings → AsyncConnectionPool
  → Checkpointer → MemoryManager → RAGPipeline → MCPClient

资源清理顺序（逆序）：
  MCPClient → RAGPipeline → MemoryManager → Checkpointer
  → AsyncConnectionPool → Langfuse → DatabaseService
"""

from urllib.parse import quote_plus
from typing import Optional

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.logging import logger
from app.services.database import DatabaseService, database_service


_resource_manager: Optional["ResourceManager"] = None


def get_resource_manager() -> "ResourceManager":
    """获取全局资源管理器实例。

    Returns:
        ResourceManager: 资源管理器实例

    Raises:
        RuntimeError: 如果资源管理器未初始化
    """
    if _resource_manager is None:
        raise RuntimeError("ResourceManager未初始化，请确保应用已启动")
    return _resource_manager


class ResourceManager:
    """集中式资源生命周期管理器。

    通过FastAPI的lifespan机制管理所有资源的创建和释放，
    确保资源在使用前已初始化，在应用关闭时正确清理。

    使用方式：
        # 在 lifespan 中
        rm = ResourceManager()
        await rm.startup()
        app.state.resource_manager = rm

        # 在其他模块中
        rm = get_resource_manager()
        db = rm.db_service
    """

    def __init__(self):
        self.db_service: Optional[DatabaseService] = None
        self.connection_pool: Optional[AsyncConnectionPool] = None
        self.checkpointer: Optional[AsyncPostgresSaver] = None
        self.memory_manager: Optional[TravelMemoryManager] = None
        self.rag_pipeline: Optional[RAGPipeline] = None
        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.mcp_toolset = None
        self.langfuse: Optional[Langfuse] = None
        self.langfuse_handler: Optional[CallbackHandler] = None
        self.embeddings: Optional[DashScopeEmbeddings] = None

    async def startup(self):
        """初始化所有资源。

        按依赖关系顺序初始化，某个资源初始化失败不影响其他资源。
        """
        global _resource_manager
        _resource_manager = self

        logger.info("开始初始化应用资源...")

        await self._init_database()
        self._init_langfuse()
        self._init_embeddings()
        await self._init_connection_pool()
        await self._init_checkpointer()
        await self._init_memory_manager()
        await self._init_rag_pipeline()
        await self._init_mcp_client()

        logger.info("应用资源初始化完成")

    async def shutdown(self):
        """清理所有资源（按初始化逆序）。"""
        global _resource_manager

        logger.info("开始清理应用资源...")

        await self._cleanup_mcp_client()
        await self._cleanup_rag_pipeline()
        self._cleanup_memory_manager()
        self._cleanup_checkpointer()
        await self._cleanup_connection_pool()
        self._cleanup_langfuse()
        await self._cleanup_database()

        _resource_manager = None
        logger.info("应用资源清理完成")

    # ========== 初始化方法 ==========

    async def _init_database(self):
        """初始化数据库服务（SQLAlchemy同步连接池）。

        使用已有的database_service单例，避免创建多个连接池。
        """
        try:
            self.db_service = database_service
            logger.info("数据库服务初始化成功")
        except Exception as e:
            logger.error("数据库服务初始化失败", error=str(e), exc_info=True)

    def _init_langfuse(self):
        """初始化Langfuse可观测性平台。"""
        try:
            if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
                self.langfuse = Langfuse(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=settings.LANGFUSE_HOST,
                )
                self.langfuse_handler = CallbackHandler()
                logger.info("Langfuse初始化成功")
            else:
                logger.warning("Langfuse未配置，跳过初始化")
        except Exception as e:
            logger.error("Langfuse初始化失败", error=str(e), exc_info=True)

    def _init_embeddings(self):
        """初始化共享嵌入模型。

        统一创建DashScopeEmbeddings实例，供TravelMemoryManager和RAGPipeline共享，
        避免重复创建相同配置的嵌入模型。
        """
        EMBEDDING_MODEL = settings.EMBEDDING_MODEL
        try:
            if settings.DASHSCOPE_API_KEY:
                self.embeddings = DashScopeEmbeddings(
                    dashscope_api_key=settings.DASHSCOPE_API_KEY,
                    model=EMBEDDING_MODEL,
                )
                logger.info("共享嵌入模型初始化完成", model=EMBEDDING_MODEL)
            else:
                logger.warning("DashScope API Key未配置，跳过嵌入模型初始化")
        except Exception as e:
            logger.error("共享嵌入模型初始化失败", error=str(e), exc_info=True)

    async def _init_connection_pool(self):
        """初始化psycopg异步连接池。

        该连接池供LangGraph检查点器和旅游记忆管理器共享使用。
        """
        try:
            connection_url = (
                "postgresql://"
                f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            )

            self.connection_pool = AsyncConnectionPool(
                connection_url,
                open=False,
                max_size=settings.POSTGRES_POOL_SIZE,
                kwargs={
                    "autocommit": True,
                    "connect_timeout": 5,
                    "prepare_threshold": None,
                },
            )
            await self.connection_pool.open()
            logger.info("psycopg异步连接池初始化成功")
        except Exception as e:
            logger.error("psycopg异步连接池初始化失败", error=str(e), exc_info=True)
            self.connection_pool = None

    async def _init_checkpointer(self):
        """初始化LangGraph检查点器（AsyncPostgresSaver）。"""
        if self.connection_pool is None:
            logger.warning("连接池未初始化，跳过检查点器初始化")
            return

        try:
            serde = JsonPlusSerializer(allowed_msgpack_modules={
                ("app.schemas.agent.state", "TaskItem"),
                ("app.schemas.agent.state", "SubAgentResult"),
                ("app.schemas.travel.components", "Attraction"),
                ("app.schemas.travel.components", "Hotel"),
                ("app.schemas.travel.components", "Meal"),
                ("app.schemas.travel.components", "Budget"),
                ("app.schemas.travel.components", "DayPlan"),
                ("app.schemas.travel.request", "TripRequest"),
                ("app.schemas.travel.request", "POISearchRequest"),
                ("app.schemas.travel.request", "RouteRequest"),
                ("app.schemas.travel.plan", "TaskPlan"),
                ("app.schemas.travel.plan", "PlanResult"),
                ("app.schemas.travel.plan", "TripPlan"),
                ("app.schemas.travel.plan", "TripPlanResponse"),
                ("app.schemas.weather.qweather", "LocationInfo"),
                ("app.schemas.weather.qweather", "QWeatherInfo"),
                ("app.schemas.weather.qweather", "AirQualityInfo"),
                ("app.schemas.weather.qweather", "TravelWeatherData"),
                ("app.schemas.common.location", "Location"),
                ("app.schemas.agent.travel_state", "TravelPlannerState"),
                ("app.schemas.agent.travel_state", "TravelPlannerOutput"),
                ("app.schemas.agent.context", "AgentContext"),
                ("app.schemas.agent.context", "TravelContext"),
                ("langchain_core.messages", "AIMessage"),
                ("langchain_core.messages", "HumanMessage"),
                ("langchain_core.messages", "BaseMessage"),
                ("langchain_core.messages", "ToolMessage"),
                ("langchain_core.messages", "SystemMessage"),
            })

            self.checkpointer = AsyncPostgresSaver(self.connection_pool, serde=serde)
            await self.checkpointer.setup()
            logger.info("AsyncPostgresSaver检查点器初始化成功")
        except Exception as e:
            logger.error("AsyncPostgresSaver检查点器初始化失败", error=str(e), exc_info=True)
            self.checkpointer = None

    async def _init_memory_manager(self):
        """初始化旅游记忆管理器。"""
        from app.core.langgraph.agents.travel_plan_agent.travel_memory import TravelMemoryManager

        if self.connection_pool is None:
            logger.warning("连接池未初始化，跳过记忆管理器初始化")
            return

        try:
            self.memory_manager = TravelMemoryManager(embeddings=self.embeddings)
            await self.memory_manager._get_store(self.connection_pool)
            logger.info("旅游记忆管理器初始化成功")
        except Exception as e:
            logger.error("旅游记忆管理器初始化失败", error=str(e), exc_info=True)
            self.memory_manager = None

    async def _init_rag_pipeline(self):
        """初始化RAG知识库检索流水线。"""
        from app.core.langgraph.rag.pipeline import RAGPipeline

        try:
            self.rag_pipeline = RAGPipeline(embeddings=self.embeddings)
            await self.rag_pipeline.initialize()
            logger.info("RAG流水线初始化成功")
        except Exception as e:
            logger.error("RAG流水线初始化失败", error=str(e), exc_info=True)
            self.rag_pipeline = None

    async def _init_mcp_client(self):
        """初始化高德地图MCP客户端。"""
        try:
            amap_api_key = settings.AMAP_API_KEY
            if not amap_api_key:
                logger.warning("高德地图API Key未配置，跳过MCP客户端初始化")
                return

            from app.core.langgraph.tools.mcp.amap_server import MCPToolSet, _init_amap_client_and_tools

            self.mcp_client, tools = await _init_amap_client_and_tools(
                server_command=["uvx", "amap-mcp-server"],
                env={"AMAP_MAPS_API_KEY": amap_api_key},
                tool_name_prefix=False,
            )
            self.mcp_toolset = MCPToolSet(tools)

            logger.info(
                "高德地图MCP客户端初始化成功",
                tool_count=len(self.mcp_toolset.list_names()),
            )
        except Exception as e:
            logger.error("高德地图MCP客户端初始化失败", error=str(e), exc_info=True)
            self.mcp_client = None
            self.mcp_toolset = None

    # ========== 清理方法 ==========

    async def _cleanup_mcp_client(self):
        """清理MCP客户端资源。

        MultiServerMCPClient 从 0.1.0 版本开始不再需要显式清理。
        它只持有配置信息，会话在每次调用工具时通过 session() 上下文管理器自动管理。
        """
        if self.mcp_client is not None:
            self.mcp_client = None
            self.mcp_toolset = None
            logger.info("MCP客户端引用已清除")

    async def _cleanup_rag_pipeline(self):
        """清理RAG流水线资源（PGEngine连接池）。"""
        if self.rag_pipeline is not None:
            try:
                await self.rag_pipeline.close()
                logger.info("RAG流水线资源已清理")
            except Exception as e:
                logger.error("清理RAG流水线资源失败", error=str(e))
            finally:
                self.rag_pipeline = None

    def _cleanup_memory_manager(self):
        """清理旅游记忆管理器引用。"""
        self.memory_manager = None
        logger.info("旅游记忆管理器引用已清理")

    def _cleanup_checkpointer(self):
        """清理检查点器引用。"""
        self.checkpointer = None
        logger.info("检查点器引用已清理")

    async def _cleanup_connection_pool(self):
        """关闭psycopg异步连接池。"""
        if self.connection_pool is not None:
            try:
                await self.connection_pool.close()
                logger.info("psycopg异步连接池已关闭")
            except Exception as e:
                logger.error("关闭psycopg连接池失败", error=str(e))
            finally:
                self.connection_pool = None

    def _cleanup_langfuse(self):
        """清理Langfuse资源。"""
        if self.langfuse is not None:
            try:
                self.langfuse.shutdown()
                logger.info("Langfuse已关闭")
            except Exception as e:
                logger.error("关闭Langfuse失败", error=str(e))
            finally:
                self.langfuse = None
                self.langfuse_handler = None

    async def _cleanup_database(self):
        """关闭数据库服务（释放SQLAlchemy连接池）。"""
        if self.db_service is not None:
            try:
                self.db_service.close()
                logger.info("数据库服务已关闭")
            except Exception as e:
                logger.error("关闭数据库服务失败", error=str(e))
            finally:
                self.db_service = None
