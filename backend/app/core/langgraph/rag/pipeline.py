"""RAG知识库检索流水线。

本模块实现了完整的RAG（Retrieval-Augmented Generation）流水线，
包含从文档加载到回答生成的全部环节。

RAG Pipeline 各环节说明：
1. 文档加载（Document Loading）：
   - 使用DirectoryLoader批量加载knowledge_base目录下的旅游攻略文档
   - 支持Markdown格式
   - 自动为每个文档添加元数据（来源城市、文件名等）

2. 文档分块（Text Splitting）：
   - 使用RecursiveCharacterTextSplitter进行递归分块
   - 分块策略：优先按段落（\\n\\n）分割，其次按句子（\\n）分割，最后按字符分割
   - chunk_size=500：每个文本块最大500字符，兼顾语义完整性和检索精度
   - chunk_overlap=50：相邻块之间重叠50字符，避免关键信息被截断

3. 文本嵌入（Text Embedding）：
   - 使用DashScopeEmbeddings将文本块转换为向量表示
   - 模型：text-embedding-v4，向量维度1024
   - 嵌入过程：文本 → DashScope API → 1024维浮点向量

4. 向量存储（Vector Storage）：
   - 使用PGVectorStore将向量存储到PostgreSQL+pgvector数据库
   - 表名：travel_knowledge，与长期记忆表隔离
   - 支持增量添加文档，避免重复嵌入

5. 检索实现（Retrieval）：
   - 基于向量相似度搜索（余弦相似度）
   - 根据用户查询的向量表示，在向量空间中找到最相似的文档片段
   - 默认返回top-k=4个最相关结果
   - 预留扩展接口：支持未来集成混合检索、重排序等策略

6. 回答生成（Answer Generation）：
   - 将检索到的文档片段作为上下文，与用户查询一起输入LLM
   - LLM基于检索到的知识生成准确、有依据的回答
   - 回答中会标注信息来源，确保可追溯性

数据流向图：
  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │  原始文档     │ ──→ │  文档分块     │ ──→ │  文本嵌入     │
  │ (Markdown)   │     │ (Splitter)   │     │ (Embedding)  │
  └──────────────┘     └──────────────┘     └──────┬───────┘
                                                   │
                                                   ▼
  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │  最终回答     │ ←── │  LLM生成     │ ←── │  向量存储     │
  │ (Answer)     │     │ (Generation) │     │ (PGVectorStore)│
  └──────────────┘     └──────────────┘     └──────┬───────┘
                                                   ▲
                                           ┌──────┴───────┐
                                           │  向量检索     │
                                           │ (Similarity) │
                                           └──────────────┘
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_postgres import PGEngine, PGVectorStore
from langchain_qwq import ChatQwen
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import logger


KNOWLEDGE_BASE_DIR = Path(__file__).parent / "knowledge_base"

EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIMS = 1024


class RetrievalStrategy(Protocol):
    """检索策略协议接口，预留扩展。

    当前仅实现基础向量相似度搜索，未来可扩展：
    - HybridRetrieval: 混合检索（向量+关键词）
    - RerankedRetrieval: 带重排序的检索
    - MultiQueryRetrieval: 多查询检索
    - ContextualRetrieval: 上下文感知检索
    """

    def retrieve(self, query: str, k: int = 4) -> List[Document]:
        ...


class RAGPipeline:
    """RAG知识库检索流水线。

    封装了从文档加载到回答生成的完整RAG流程，提供简洁的API接口。

    使用方式：
        # 获取全局实例
        pipeline = get_rag_pipeline()

        # 初始化（加载文档并构建向量库，仅需执行一次）
        await pipeline.initialize()

        # 检索相关文档
        docs = await pipeline.aretrieve("成都有什么美食？")

        # 检索+生成回答
        answer = await pipeline.agenerate("成都有什么美食？")
    """

    def __init__(self):
        self._vector_store: Optional[PGVectorStore] = None
        self._engine: Optional[PGEngine] = None
        self._embeddings: Optional[DashScopeEmbeddings] = None
        self._splitter: Optional[RecursiveCharacterTextSplitter] = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized and self._vector_store is not None

    def _get_async_connection_string(self) -> str:
        """构建异步PostgreSQL连接字符串。

        langchain_postgres PGVectorStore使用asyncpg驱动进行异步操作：
        postgresql+asyncpg://user:password@host:port/dbname
        """
        return (
            f"postgresql+asyncpg://"
            f"{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )

    def _get_engine(self) -> PGEngine:
        """获取PGEngine连接池实例。

        PGEngine配置了共享连接池，是行业最佳实践，
        可以管理连接数量并通过缓存的数据库连接减少延迟。
        """
        if self._engine is None:
            connection_string = self._get_async_connection_string()
            self._engine = PGEngine.from_connection_string(url=connection_string)
            logger.info("PGEngine连接池初始化完成")
        return self._engine

    def _get_embeddings(self) -> DashScopeEmbeddings:
        """获取嵌入模型实例。

        使用DashScope的text-embedding-v4模型，向量维度为1024。
        与travel_memory.py中的嵌入模型保持一致，确保向量空间统一。
        """
        if self._embeddings is None:
            self._embeddings = DashScopeEmbeddings(
                dashscope_api_key=settings.DASHSCOPE_API_KEY,
                model=EMBEDDING_MODEL,
            )
            logger.info("RAG嵌入模型初始化完成", model=EMBEDDING_MODEL, dims=EMBEDDING_DIMS)
        return self._embeddings

    def _get_splitter(self) -> RecursiveCharacterTextSplitter:
        """获取文本分块器。

        RecursiveCharacterTextSplitter的递归分块策略：
        1. 首先尝试按 "\\n\\n"（段落）分割
        2. 如果块仍过大，按 "\\n"（行）分割
        3. 最后按字符分割
        这确保了语义完整性，同时控制块大小在合理范围内。

        参数说明：
        - chunk_size=500: 每个文本块最大500字符
          选择依据：旅游攻略信息密度适中，500字符可以包含完整的景点/美食描述
        - chunk_overlap=50: 相邻块重叠50字符
          选择依据：约10%的重叠率，避免关键信息被截断，同时不引入过多冗余
        - separators: 自定义分割符优先级，确保中文文本的合理分割
        """
        if self._splitter is None:
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.RAG_CHUNK_SIZE,
                chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            )
            logger.info(
                "RAG文本分块器初始化完成",
                chunk_size=settings.RAG_CHUNK_SIZE,
                chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            )
        return self._splitter

    def load_documents(self, docs_dir: Optional[str] = None) -> List[Document]:
        """加载旅游攻略文档。

        使用DirectoryLoader批量加载指定目录下的所有Markdown文档文件。
        当前支持Markdown（.md）格式。

        文档加载后会自动添加元数据：
        - source: 文件路径
        - city: 从文件名中提取的城市名称

        Args:
            docs_dir: 文档目录路径，默认为knowledge_base目录

        Returns:
            加载的文档列表，每个文档包含page_content和metadata
        """
        directory = Path(docs_dir) if docs_dir else KNOWLEDGE_BASE_DIR

        if not directory.exists():
            logger.warning("知识库目录不存在", directory=str(directory))
            return []

        loader = DirectoryLoader(
            str(directory),
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=True,
        )

        documents = loader.load()

        for doc in documents:
            source_path = doc.metadata.get("source", "")
            filename = Path(source_path).stem
            doc.metadata["city"] = filename

        logger.info(
            "文档加载完成",
            directory=str(directory),
            document_count=len(documents),
            cities=list(set(d.metadata.get("city", "unknown") for d in documents)),
        )
        return documents

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """将文档分割为文本块。

        使用RecursiveCharacterTextSplitter进行递归分块，
        确保每个文本块在语义上尽可能完整。

        分块过程：
        1. 按段落分割，保持段落的语义完整性
        2. 过大的段落进一步按句子分割
        3. 仍然过大的句子按字符分割
        4. 相邻块之间保留overlap区域，避免信息截断

        Args:
            documents: 原始文档列表

        Returns:
            分块后的文档列表，每个块继承原始文档的元数据
        """
        splitter = self._get_splitter()
        chunks = splitter.split_documents(documents)

        for chunk in chunks:
            chunk.id = str(uuid.uuid4())

        logger.info(
            "文档分块完成",
            original_count=len(documents),
            chunk_count=len(chunks),
            avg_chunk_size=sum(len(c.page_content) for c in chunks) // max(len(chunks), 1),
        )
        return chunks

    async def _init_vectorstore_table(self, overwrite_existing: bool = False) -> None:
        """初始化向量存储表结构。

        创建具有正确schema的表，用于存储向量和文档。
        当overwrite_existing=True时，会删除旧表并重新创建。

        Args:
            overwrite_existing: 是否覆盖已有表（用于表结构不匹配时重建）
        """
        engine = self._get_engine()
        await engine.ainit_vectorstore_table(
            table_name=settings.RAG_COLLECTION_NAME,
            vector_size=EMBEDDING_DIMS,
            overwrite_existing=overwrite_existing,
        )
        logger.info(
            "向量存储表初始化完成",
            table_name=settings.RAG_COLLECTION_NAME,
            vector_size=EMBEDDING_DIMS,
            overwrite_existing=overwrite_existing,
        )

    async def build_vector_store(self, chunks: List[Document]) -> PGVectorStore:
        """从文档块构建PGVectorStore向量存储。

        此方法执行以下操作：
        1. 初始化向量存储表结构
        2. 创建PGVectorStore实例
        3. 调用DashScope Embedding API将每个文本块转换为1024维向量
        4. 将向量和原始文本存储到PostgreSQL表中

        注意：此操作会调用外部API并写入数据库，耗时取决于文档数量。

        Args:
            chunks: 分块后的文档列表

        Returns:
            PGVectorStore向量存储实例
        """
        engine = self._get_engine()
        embeddings = self._get_embeddings()

        await self._init_vectorstore_table(overwrite_existing=True)

        vector_store = await PGVectorStore.create(
            engine=engine,
            table_name=settings.RAG_COLLECTION_NAME,
            embedding_service=embeddings,
        )

        await vector_store.aadd_documents(chunks)

        logger.info(
            "PGVectorStore向量存储构建完成",
            table_name=settings.RAG_COLLECTION_NAME,
            vector_count=len(chunks),
            embedding_model=EMBEDDING_MODEL,
        )
        return vector_store

    async def connect_vector_store(self) -> PGVectorStore:
        """连接到已有的PGVectorStore向量存储。

        与build_vector_store不同，此方法不会重新加载文档和计算嵌入，
        而是直接连接到数据库中已有的向量表。
        适用于向量库已初始化后的后续连接场景。

        如果表不存在或表结构不匹配（如从旧版PGVector迁移），
        会自动创建或重建表结构。

        Returns:
            PGVectorStore向量存储实例
        """
        engine = self._get_engine()
        embeddings = self._get_embeddings()

        try:
            vector_store = await PGVectorStore.create(
                engine=engine,
                table_name=settings.RAG_COLLECTION_NAME,
                embedding_service=embeddings,
            )
        except Exception as e:
            error_str = str(e)
            if "does not exist" in error_str or "relation" in error_str.lower():
                logger.warning(
                    "向量存储表不存在或结构不匹配，正在创建/重建表...",
                    table_name=settings.RAG_COLLECTION_NAME,
                    error=error_str,
                )
                await self._init_vectorstore_table(overwrite_existing=True)
                vector_store = await PGVectorStore.create(
                    engine=engine,
                    table_name=settings.RAG_COLLECTION_NAME,
                    embedding_service=embeddings,
                )
            else:
                raise

        logger.info(
            "已连接到现有PGVectorStore向量存储",
            table_name=settings.RAG_COLLECTION_NAME,
        )
        return vector_store

    async def _is_table_empty(self) -> bool:
        """检查向量存储表是否为空。

        Returns:
            True如果表为空或不存在，False如果表中有数据
        """
        from sqlalchemy import text

        engine = self._get_engine()

        async def _check() -> bool:
            async with engine._pool.connect() as conn:
                result = await conn.execute(
                    text(f"SELECT EXISTS (SELECT 1 FROM {settings.RAG_COLLECTION_NAME} LIMIT 1)")
                )
                row = result.fetchone()
                return not row[0]

        return await engine._run_as_async(_check())

    async def initialize(self, force_rebuild: bool = False) -> None:
        """初始化RAG流水线。

        初始化流程：
        1. 如果force_rebuild=True：删除旧表，加载文档→分块→嵌入→存储
        2. 否则：连接已有向量库，如果表为空则自动加载数据

        建议在应用启动时调用此方法进行初始化。

        Args:
            force_rebuild: 是否强制重建向量库（重新加载文档和计算嵌入）
        """
        if self._initialized and not force_rebuild:
            logger.info("RAG流水线已初始化，跳过")
            return

        try:
            if force_rebuild:
                logger.info("开始重建RAG向量库...")
                documents = self.load_documents()
                if not documents:
                    logger.warning("未加载到任何文档，RAG初始化中止")
                    return

                chunks = self.split_documents(documents)
                if not chunks:
                    logger.warning("文档分块结果为空，RAG初始化中止")
                    return

                self._vector_store = await self.build_vector_store(chunks)
            else:
                self._vector_store = await self.connect_vector_store()

                try:
                    is_empty = await self._is_table_empty()
                except Exception:
                    is_empty = True

                if is_empty:
                    logger.info("向量存储表为空，开始加载文档...")
                    documents = self.load_documents()
                    if not documents:
                        logger.warning("未加载到任何文档，RAG初始化中止")
                        return

                    chunks = self.split_documents(documents)
                    if not chunks:
                        logger.warning("文档分块结果为空，RAG初始化中止")
                        return

                    await self._vector_store.aadd_documents(chunks)
                    logger.info(
                        "文档加载完成",
                        chunk_count=len(chunks),
                    )

            self._initialized = True
            logger.info("RAG流水线初始化完成")

        except Exception as e:
            logger.error("RAG流水线初始化失败", error=str(e), exc_info=True)
            self._initialized = False
            raise

    async def aretrieve(
        self,
        query: str,
        k: int = 4,
        **kwargs,
    ) -> List[Document]:
        """异步向量相似度检索。

        检索流程：
        1. 将用户查询通过DashScope Embedding转换为向量
        2. 在PGVectorStore中执行余弦相似度搜索
        3. 返回最相似的k个文档片段

        扩展接口说明：
        kwargs参数预留用于未来扩展检索策略：
        - filter: 元数据过滤条件，如 {"city": "chengdu"}
        - score_threshold: 相似度阈值过滤
        - fetch_k: MMR算法中的候选集大小
        - lambda_mult: MMR算法中的多样性参数

        Args:
            query: 用户查询文本
            k: 返回的文档数量（默认4）
            **kwargs: 预留的扩展参数

        Returns:
            检索到的文档列表，按相似度从高到低排序
        """
        if not self.is_initialized:
            logger.warning("RAG流水线未初始化，尝试自动连接...")
            await self.initialize()

        if self._vector_store is None:
            logger.error("向量存储不可用")
            return []

        try:
            docs = await self._vector_store.asimilarity_search(
                query=query,
                k=k,
                **kwargs,
            )
            logger.info(
                "向量检索完成",
                query=query[:50],
                result_count=len(docs),
                k=k,
            )
            return docs
        except Exception as e:
            logger.error("向量检索失败", query=query[:50], error=str(e))
            return []

    async def aretrieve_with_scores(
        self,
        query: str,
        k: int = 4,
    ) -> List[tuple]:
        """带相似度分数的异步检索。

        返回文档及其相似度分数，便于调试和结果过滤。
        分数越小表示越相似（基于距离度量）。

        Args:
            query: 用户查询文本
            k: 返回的文档数量

        Returns:
            (Document, score) 元组列表
        """
        if not self.is_initialized:
            await self.initialize()

        if self._vector_store is None:
            return []

        try:
            results = await self._vector_store.asimilarity_search_with_score(
                query=query,
                k=k,
            )
            logger.info(
                "带分数检索完成",
                query=query[:50],
                result_count=len(results),
            )
            return results
        except Exception as e:
            logger.error("带分数检索失败", query=query[:50], error=str(e))
            return []

    async def agenerate(self, query: str, k: int = 4) -> Dict[str, Any]:
        """检索增强生成（RAG核心方法）。

        完整的RAG流程：
        1. 检索：根据查询从向量库中检索相关文档片段
        2. 上下文组装：将检索到的文档片段拼接为上下文
        3. 生成：将上下文和查询一起输入LLM，生成最终回答

        生成的回答具有以下特点：
        - 基于检索到的知识，减少幻觉
        - 标注信息来源，便于追溯
        - 如果检索不到相关信息，会如实告知

        Args:
            query: 用户查询文本
            k: 检索的文档数量

        Returns:
            包含以下字段的字典：
            - answer: LLM生成的回答
            - sources: 检索到的文档来源信息
            - context: 拼接的上下文文本
        """
        docs = await self.aretrieve(query, k=k)

        if not docs:
            return {
                "answer": "抱歉，知识库中未找到与您的问题相关的旅游信息。建议您尝试更具体的提问，或咨询其他信息来源。",
                "sources": [],
                "context": "",
            }

        context_parts = []
        sources = []
        for i, doc in enumerate(docs, 1):
            city = doc.metadata.get("city", "未知")
            source = doc.metadata.get("source", "未知")
            context_parts.append(f"[文档{i}] (来源: {city}旅游攻略)\n{doc.page_content}")
            sources.append({"city": city, "source": source})

        context = "\n\n---\n\n".join(context_parts)

        model = ChatQwen(
            model_name=settings.DASHSCOPE_SUBAGENT_LLM_MODEL,
            api_key=settings.DASHSCOPE_API_KEY,
            api_base=settings.DASHSCOPE_API_BASE,
            temperature=0.5,
            max_tokens=800,
            timeout=60,
            max_retries=2,
        )

        rag_prompt = ChatPromptTemplate.from_messages([
            ("system", RAG_GENERATION_PROMPT),
            ("human", "用户问题：{query}\n\n参考资料：\n{context}"),
        ])

        chain = rag_prompt | model
        result = await chain.ainvoke({"query": query, "context": context})

        logger.info(
            "RAG回答生成完成",
            query=query[:50],
            answer_length=len(result.content),
            source_count=len(sources),
        )

        return {
            "answer": result.content,
            "sources": sources,
            "context": context,
        }

    async def aadd_documents(self, documents: List[Document]) -> None:
        """向现有向量库中增量添加文档。

        适用于知识库更新场景，无需重建整个向量库。
        添加的文档会自动进行分块、嵌入和存储。

        Args:
            documents: 要添加的文档列表
        """
        if not self.is_initialized:
            await self.initialize()

        if self._vector_store is None:
            logger.error("向量存储不可用，无法添加文档")
            return

        chunks = self.split_documents(documents)
        await self._vector_store.aadd_documents(chunks)

        logger.info(
            "增量文档添加完成",
            original_count=len(documents),
            chunk_count=len(chunks),
        )


RAG_GENERATION_PROMPT = """你是一个专业的旅游知识助手。请根据提供的参考资料回答用户的问题。

回答要求：
1. 严格基于参考资料中的信息回答，不要编造不存在的内容
2. 如果参考资料中没有足够的信息，请如实说明
3. 回答要具体、实用，包含具体的地点、价格、时间等细节
4. 适当引用来源，如"根据成都旅游攻略的介绍..."
5. 回答要简洁明了，重点突出

注意：如果参考资料与用户问题不相关，请说明知识库中暂无相关信息。"""


_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    """获取RAG流水线全局单例。

    使用单例模式确保整个应用共享同一个RAGPipeline实例，
    避免重复初始化嵌入模型和数据库连接。

    Returns:
        RAGPipeline实例
    """
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
        logger.info("RAG流水线全局实例已创建")
    return _rag_pipeline
