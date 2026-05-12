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

import asyncio
import uuid
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_postgres import PGEngine, PGVectorStore
from langchain_postgres.v2.hybrid_search_config import HybridSearchConfig, reciprocal_rank_fusion
from langchain_qwq import ChatQwen
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from sqlmodel import Session, select

from app.core.config import settings
from app.core.logging import logger
from app.models.rag_document import RAGDocument
from app.core.prompts import MQE_GENERATION_PROMPT, HYDE_GENERATION_PROMPT
from app.core.langgraph.rag.rate_limiter import get_llm_rate_limiter

KNOWLEDGE_BASE_DIR = Path(__file__).parent / "knowledge_base"

EMBEDDING_MODEL = settings.EMBEDDING_MODEL
EMBEDDING_DIMS = settings.EMBEDDING_DIMS

CITY_ALIASES: Dict[str, str] = {
    "北京": "beijing",
    "上海": "shanghai",
    "西安": "xian",
    "成都": "chengdu",
    "杭州": "hangzhou",
    "丽江": "lijiang",
    "广州": "guangzhou",
    "厦门": "xiamen",
    "大理": "dali",
    "三亚": "sanya",
}

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

    def __init__(self, embeddings: Optional[DashScopeEmbeddings] = None):
        self._vector_store: Optional[PGVectorStore] = None
        self._engine: Optional[PGEngine] = None
        self._embeddings: Optional[DashScopeEmbeddings] = embeddings
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

    def _get_markdown_splitter(self) -> MarkdownHeaderTextSplitter:
        """获取Markdown标题分块器。

        MarkdownHeaderTextSplitter按照Markdown标题结构分块，
        保留文档的层次结构，并将标题信息存储在metadata中。

        旅游攻略文档通常包含以下标题层次：
        - # 城市名（一级标题）
        - ## 景点/美食/住宿等分类（二级标题）
        - ### 具体推荐（三级标题）

        分块后的metadata示例：
        {
            'Header 1': '成都',
            'Header 2': '美食推荐',
            'Header 3': '火锅'
        }
        """
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        return MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=True,
            return_each_line=False,
        )

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

        对于Markdown文档，采用两阶段分块策略：
        1. 使用MarkdownHeaderTextSplitter按标题结构分块，保留层次信息
        2. 对过大的分块使用RecursiveCharacterTextSplitter进一步分割

        这种方法的优势：
        - 保留Markdown文档的结构化信息
        - 标题信息存储在metadata中，提升检索精度
        - 仍然控制块大小在合理范围内

        分块过程：
        1. Markdown标题分块：按#、##、###标题分组
        2. 大小控制：对超过chunk_size的分块进一步分割
        3. 元数据保留：保留原始文档的元数据和标题层次信息

        Args:
            documents: 原始文档列表

        Returns:
            分块后的文档列表，每个块继承原始文档的元数据和标题信息
        """
        markdown_splitter = self._get_markdown_splitter()
        text_splitter = self._get_splitter()

        all_chunks = []

        for doc in documents:
            md_chunks = markdown_splitter.split_text(doc.page_content)

            for md_chunk in md_chunks:
                md_chunk.metadata.update(doc.metadata)

                if len(md_chunk.page_content) > settings.RAG_CHUNK_SIZE:
                    smaller_chunks = text_splitter.split_documents([md_chunk])
                    for chunk in smaller_chunks:
                        chunk.metadata.update(md_chunk.metadata)
                        all_chunks.append(chunk)
                else:
                    all_chunks.append(md_chunk)

        for chunk in all_chunks:
            chunk.id = str(uuid.uuid4())

        logger.info(
            "文档分块完成",
            original_count=len(documents),
            chunk_count=len(all_chunks),
            avg_chunk_size=sum(len(c.page_content) for c in all_chunks) // max(len(all_chunks), 1),
            markdown_chunks=len([c for c in all_chunks if 'Header 1' in c.metadata]),
        )
        return all_chunks

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
        3. 更新文档跟踪表

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

                self._update_document_tracking(chunks, clear_existing=True)
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

                    self._update_document_tracking(chunks, clear_existing=False)

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

    def _update_document_tracking(
        self,
        chunks: List[Document],
        clear_existing: bool = False
    ) -> None:
        """更新文档跟踪表。

        在初始化或重建知识库后，更新数据库中的文档跟踪记录。

        Args:
            chunks: 文档分块列表
            clear_existing: 是否清空现有记录（用于重建场景）
        """
        try:
            with self._get_db_session() as session:
                if clear_existing:
                    all_docs = session.exec(select(RAGDocument)).all()
                    for doc in all_docs:
                        session.delete(doc)
                    session.commit()

                directory = KNOWLEDGE_BASE_DIR
                for file_path in directory.glob("**/*.md"):
                    filename = file_path.stem
                    relative_path = file_path.relative_to(directory)
                    file_hash = self._compute_file_hash(file_path)
                    file_size = file_path.stat().st_size

                    file_chunks = [c for c in chunks if c.metadata.get("city") == filename]

                    # 检查数据库中是否已存在该文件的记录，存在则更新，不存在则创建
                    existing_doc = session.exec(
                        select(RAGDocument).where(RAGDocument.filename == filename)
                    ).first()

                    if existing_doc:
                        existing_doc.file_hash = file_hash
                        existing_doc.chunk_count = len(file_chunks)
                        existing_doc.file_size = file_size
                        session.add(existing_doc)
                    else:
                        new_doc = RAGDocument(
                            filename=filename,
                            file_path=str(relative_path),
                            file_hash=file_hash,
                            chunk_count=len(file_chunks),
                            file_size=file_size,
                        )
                        session.add(new_doc)

                session.commit()
                logger.info("文档跟踪表更新完成")

        except Exception as e:
            logger.error("更新文档跟踪表失败", error=str(e), exc_info=True)

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

    async def _generate_expanded_queries(
        self,
        query: str,
        multi_query_count: int = 3,
        use_hyde: bool = True,
        config: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """生成扩展查询：MQE多查询扩展 + HyDE假设文档。

        MQE和HyDE两个chain调用之间无依赖关系，使用asyncio.gather并行执行，
        将串行的2次LLM调用耗时压缩为1次。

        已集成速率限制和指数退避重试机制，避免触发API限流。

        Args:
            query: 原始查询
            multi_query_count: MQE扩展查询数量
            use_hyde: 是否启用HyDE
            config: 可选的LangChain RunnableConfig，用于传递回调（如Langfuse）

        Returns:
            扩展查询列表
        """
        expanded = []
        rate_limiter = get_llm_rate_limiter()

        async def _invoke_with_retry(chain, input_dict, max_retries=3):
            """带速率限制和重试的LLM调用。

            Args:
                chain: LangChain chain
                input_dict: 输入参数字典
                max_retries: 最大重试次数

            Returns:
                LLM响应结果
            """
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    await rate_limiter.acquire()
                    return await chain.ainvoke(input_dict, config=config)
                except Exception as e:
                    last_exception = e
                    error_str = str(e)
                    
                    if "429" in error_str or "rate" in error_str.lower() or "limit" in error_str.lower():
                        if attempt < max_retries:
                            wait_time = min(2 ** attempt, 30)
                            logger.warning(
                                "API限流，等待后重试",
                                attempt=attempt + 1,
                                wait_seconds=wait_time,
                                error=error_str[:100],
                            )
                            await asyncio.sleep(wait_time)
                            continue
                    
                    raise
            
            raise last_exception

        try:
            model = ChatQwen(
                model_name=settings.DASHSCOPE_RAG_QUERY_EXPANSION_MODEL,
                api_key=settings.DASHSCOPE_API_KEY,
                api_base=settings.DASHSCOPE_API_BASE,
                temperature=0.7,
                max_tokens=500,
                timeout=30,
                max_retries=1,
            )

            mqe_coro = None
            hyde_coro = None

            if multi_query_count > 0:
                mqe_prompt = ChatPromptTemplate.from_messages([
                    ("system", MQE_GENERATION_PROMPT),
                    ("human", "原始查询：{query}\n\n请生成{count}个不同表述的查询。"),
                ])
                mqe_chain = mqe_prompt | model
                mqe_coro = _invoke_with_retry(
                    mqe_chain, {"query": query, "count": multi_query_count}
                )

            if use_hyde:
                hyde_prompt = ChatPromptTemplate.from_messages([
                    ("system", HYDE_GENERATION_PROMPT),
                    ("human", "用户问题：{query}\n\n请写一段详细的回答。"),
                ])
                hyde_chain = hyde_prompt | model
                hyde_coro = _invoke_with_retry(hyde_chain, {"query": query})

            coroutines = [c for c in [mqe_coro, hyde_coro] if c is not None]
            results = await asyncio.gather(*coroutines, return_exceptions=True)

            result_idx = 0
            if mqe_coro is not None:
                mqe_result = results[result_idx]
                result_idx += 1
                if isinstance(mqe_result, Exception):
                    logger.warning("MQE生成失败", error=str(mqe_result))
                else:
                    for line in mqe_result.content.strip().split("\n"):
                        line = line.strip()
                        line = line.lstrip("0123456789.-) ")
                        if line:
                            expanded.append(line)

            if hyde_coro is not None:
                hyde_result = results[result_idx]
                if isinstance(hyde_result, Exception):
                    logger.warning("HyDE生成失败", error=str(hyde_result))
                else:
                    hyde_text = hyde_result.content.strip()
                    if hyde_text:
                        expanded.append(hyde_text)

            logger.info(
                "扩展查询生成完成",
                original_query=query[:50],
                mqe_count=min(multi_query_count, len(expanded)),
                hyde_enabled=use_hyde,
                total_expanded=len(expanded),
            )

        except Exception as e:
            logger.warning("扩展查询生成失败，将使用原始查询", error=str(e))

        return expanded

    def _merge_and_deduplicate(
        self,
        result_groups: List[List[Tuple[Document, float]]],
        k: int = 4,
        score_threshold: float = 0.0,
    ) -> List[Document]:
        """合并多组检索结果并去重，使用RRF（Reciprocal Rank Fusion）排序。

        去重策略：基于page_content的哈希值去重。
        排序策略：使用RRF（Reciprocal Rank Fusion）算法，
        综合考虑文档在各查询结果中的排名位置，而非简单的出现频次。

        RRF公式：score(d) = Σ 1/(k_rrf + rank_i(d))
        其中k_rrf=60是标准常数，rank_i(d)是文档d在第i组结果中的排名。

        RRF vs 纯频次排序：
        纯频次排序的问题：原始查询的top结果在扩展查询中也会出现（语义相似），
        频次最高永远排在最前面，扩展查询带来的独特新文档频次只有1，被截断丢弃。
        RRF的优势：考虑排名位置，扩展查询中排名靠前的独特文档可以超过
        原始查询中排名靠后的文档，使扩展策略的贡献得以体现。

        过滤策略：保留distance <= score_threshold的文档。

        PGVectorStore使用COSINE_DISTANCE度量，distance范围[0, 2]：
        - 0: 完全相同
        - < 0.5: 高度相关
        - 0.5~1.0: 有一定相关性
        - > 1.0: 基本不相关

        Args:
            result_groups: 多组检索结果，每组为(Document, distance)元组列表，
                           按distance升序排列（最相似的在前）
            k: 最终返回的文档数量
            score_threshold: distance阈值，超过此值的文档被过滤掉。
                             0表示不过滤（默认），典型值0.5~1.0

        Returns:
            去重合并后的文档列表
        """
        K_RRF = 60

        doc_scores: Dict[str, Tuple[Document, float, float]] = {}

        for group in result_groups:
            for rank, (doc, dist) in enumerate(group, start=1):
                if score_threshold > 0 and dist > score_threshold:
                    continue
                content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
                rrf_contribution = 1.0 / (K_RRF + rank)
                if content_hash in doc_scores:
                    existing_doc, rrf_score, best_dist = doc_scores[content_hash]
                    doc_scores[content_hash] = (
                        existing_doc,
                        rrf_score + rrf_contribution,
                        min(best_dist, dist),
                    )
                else:
                    doc_scores[content_hash] = (doc, rrf_contribution, dist)

        sorted_docs = sorted(
            doc_scores.values(),
            key=lambda x: -x[1],
        )

        return [doc for doc, _, _ in sorted_docs[:k]]

    @staticmethod
    def _extract_city_filter(query: str) -> Optional[Dict[str, str]]:
        """从查询文本中提取城市名，生成元数据过滤条件。

        遍历CITY_ALIASES映射表，匹配查询中出现的城市名。
        支持多城市匹配：当查询中包含多个城市名时（如"大理和丽江哪个更值得去"），
        返回OR过滤条件，匹配任一城市即可。

        Args:
            query: 用户查询文本

        Returns:
            城市过滤条件字典，未匹配到则返回None
            单城市：{"city": "english_name"}
            多城市：{"city": {"$in": ["city1", "city2"]}}
        """
        matched_cities = []
        for cn_name, en_name in CITY_ALIASES.items():
            if cn_name in query:
                matched_cities.append(en_name)

        if not matched_cities:
            return None
        if len(matched_cities) == 1:
            return {"city": matched_cities[0]}
        return {"city": {"$in": matched_cities}}

    def _build_hybrid_search_config(self, query: str) -> HybridSearchConfig:
        """构建混合检索配置。

        使用PGVectorStore原生的HybridSearchConfig，配置：
        - 向量检索（dense）+ 全文检索（sparse）双路召回
        - RRF（Reciprocal Rank Fusion）融合算法
        - tsv_lang使用zh_cn配置（基于zhparser中文分词扩展）

        zhparser是PostgreSQL的中文分词扩展，基于scws（Simple Chinese Word
        Segmentation）实现。它将中文文本按词组切分，例如"兵马俑"会被识别为
        一个完整的词，而非按字符拆分。这比pg_catalog.simple的字符级匹配
        精确得多。

        zh_cn配置通过db/init.sql在数据库初始化时自动创建：
          CREATE TEXT SEARCH CONFIGURATION zh_cn (PARSER = zhparser);
          ALTER TEXT SEARCH CONFIGURATION zh_cn ADD MAPPING
            FOR n,v,a,i,e,l WITH simple;

        如果zhparser扩展未安装（如本地开发环境），会自动回退到
        pg_catalog.simple。

        Args:
            query: 用户查询文本，同时作为全文检索的查询词

        Returns:
            HybridSearchConfig实例
        """
        config = HybridSearchConfig(
            tsv_column="",
            tsv_lang="zh_cn",
            fts_query=query,
            fusion_function=reciprocal_rank_fusion,
            fusion_function_parameters={"rrf_k": 60},
            primary_top_k=20,
            secondary_top_k=20,
        )
        logger.debug(
            "构建HybridSearchConfig",
            tsv_lang=config.tsv_lang,
            fts_query=config.fts_query,
            primary_top_k=config.primary_top_k,
            secondary_top_k=config.secondary_top_k,
        )
        return config

    async def _hybrid_search_single(
        self,
        query: str,
        k: int,
        filter_dict: Optional[Dict[str, str]] = None,
        use_hybrid: bool = True,
    ) -> List[Tuple[Document, float]]:
        """对单个查询执行混合检索（向量+关键词+RRF融合）。

        这是统一检索流水线Stage 2的原子操作，每个查询（原始/扩展/HyDE）
        都会调用此方法获取候选文档。

        Args:
            query: 查询文本
            k: 返回文档数量
            filter_dict: 元数据过滤条件
            use_hybrid: 是否启用混合检索

        Returns:
            (Document, distance_score) 元组列表，distance越小越相似
        """
        hybrid_config = None
        if use_hybrid:
            try:
                hybrid_config = self._build_hybrid_search_config(query)
                logger.debug(
                    "Hybrid检索配置构建成功",
                    query=query[:50],
                    fts_query=hybrid_config.fts_query,
                    tsv_lang=hybrid_config.tsv_lang,
                )
            except Exception as e:
                logger.warning("Hybrid检索配置构建失败，回退到纯向量检索", error=str(e))
                hybrid_config = None

        fetch_k = max(k * 2, 8)

        docs_with_scores = await self._vector_store.asimilarity_search_with_score(
            query=query,
            k=fetch_k,
            filter=filter_dict,
            hybrid_search_config=hybrid_config,
        )

        return docs_with_scores

    async def aretrieve_enhanced(
        self,
        query: str,
        k: int = 4,
        *,
        use_mqe: bool = True,
        use_hyde: bool = True,
        mqe_count: int = 3,
        use_filter: bool = True,
        use_hybrid: bool = True,
        use_context_expansion: bool = True,
        use_diversity: bool = True,
        score_threshold: float = 0.8,
        config: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """统一增强检索：查询扩展 → 混合检索 → 合并去重 → 后处理。

        这是RAG流水线的核心检索入口，整合查询扩展、混合检索、
        合并去重和后处理为统一的四阶段流水线：

        Stage 1 - 查询扩展（可选）：
          MQE生成语义等价的多样化查询，HyDE生成假设性答案段落。
          扩展查询不仅用于向量检索，也参与关键词检索——
          例如HyDE生成的"兵马俑位于临潼区，可乘坐旅游专线"，
          关键词检索能匹配到"临潼区"和"旅游专线"等原始查询中没有的词。

        Stage 2 - 混合检索：
          对每个查询（原始+扩展）并行执行：
          - 向量检索（dense）：语义匹配
          - 关键词检索（sparse）：PostgreSQL FTS + zhparser中文分词
          - RRF融合：两路结果合并
          同时支持元数据预过滤（城市名提取）。

        Stage 3 - 合并去重：
          多路检索结果按出现频次排序，频次相同按首次出现顺序。
          支持基于distance的相似度阈值过滤，丢弃距离过大的文档。

        Stage 4 - 后处理（可选）：
          - 上下文窗口扩展：基于Header元数据补全同section相邻chunk
          - 城市多样性保证：避免结果过度集中在单一城市

        各策略可独立开关，便于A/B测试和调试。

        Args:
            query: 用户查询文本
            k: 最终返回的文档数量
            use_mqe: 是否启用多查询扩展
            use_hyde: 是否启用假设文档嵌入
            mqe_count: MQE生成的扩展查询数量
            use_filter: 是否启用城市元数据预过滤
            use_hybrid: 是否启用混合检索（向量+关键词）
            use_context_expansion: 是否启用上下文窗口扩展
            use_diversity: 是否启用城市多样性保证
            score_threshold: 余弦距离阈值，distance > 此值的文档被过滤。
                             默认0.8（过滤掉相关性较低的文档，适合生产环境）。
                             范围[0, 2]：0=完全相同，0.5=高度相关，
                             0.8=相关，1.0=中等相关，1.5+=基本不相关。
                             A/B测试评估时建议设为2.0（不过滤），让评估指标自行判断相关性。
            config: 可选的LangChain RunnableConfig，用于传递回调（如Langfuse）。
                    当从A/B测试端点调用时传入Langfuse回调以追踪MQE/HyDE生成过程；
                    当从旅行规划主图调用时为None，回调由主图上下文自动传播。

        Returns:
            增强检索后的文档列表
        """
        if not self.is_initialized:
            await self.initialize()

        if self._vector_store is None:
            logger.error("向量存储不可用")
            return []

        try:
            # ── Stage 1: 查询扩展 ──
            all_queries = [query]
            if use_mqe or use_hyde:
                expanded = await self._generate_expanded_queries(
                    query,
                    multi_query_count=mqe_count if use_mqe else 0,
                    use_hyde=use_hyde,
                    config=config,
                )
                all_queries.extend(expanded)

            # ── Stage 2: 混合检索 ──
            filter_dict = self._extract_city_filter(query) if use_filter else None

            retrieval_tasks = [
                self._hybrid_search_single(
                    q, k=max(k * 2, 8), filter_dict=filter_dict, use_hybrid=use_hybrid
                )
                for q in all_queries
            ]
            all_results = await asyncio.gather(*retrieval_tasks)

            # ── Stage 3: 合并去重 ──
            docs = self._merge_and_deduplicate(
                all_results, k=k * 3, score_threshold=score_threshold
            )

            if len(docs) < k and all_results:
                total_candidates = sum(len(r) for r in all_results)
                logger.warning(
                    "去重后文档数量不足，尝试扩大合并范围",
                    merged_count=len(docs),
                    target_k=k,
                    total_candidates=total_candidates,
                )
                docs = self._merge_and_deduplicate(
                    all_results, k=total_candidates, score_threshold=score_threshold
                )

            # ── Stage 4: 后处理 ──
            if use_context_expansion and docs:
                docs = await self._expand_context_window(docs)

            if use_diversity and docs:
                docs = self._ensure_city_diversity(docs)

            logger.info(
                "统一增强检索完成",
                query=query[:50],
                total_queries=len(all_queries),
                total_candidates=sum(len(r) for r in all_results),
                merged_count=len(docs),
                filter_enabled=use_filter,
                hybrid_enabled=use_hybrid,
                mqe_enabled=use_mqe,
                hyde_enabled=use_hyde,
                context_expansion_enabled=use_context_expansion,
                diversity_enabled=use_diversity,
            )

            return docs[:k + 4]

        except Exception as e:
            logger.error("统一增强检索失败，回退到基础检索", query=query[:50], error=str(e))
            return await self.aretrieve(query, k=k)

    async def _expand_context_window(
        self,
        docs: List[Document],
        max_extra_chunks: int = 2,
    ) -> List[Document]:
        """基于Header元数据的上下文窗口扩展。

        对于每个检索到的文档块，查找同section（相同city+Header 2）的
        相邻块并补充进来。这解决了分块导致的信息截断问题：
        一个chunk可能只包含部分信息，但同section的其他chunk
        包含完整的上下文。

        扩展策略：
        1. 从检索结果中提取所有 (city, Header 2) 组合
        2. 对每个组合，在向量库中检索同section的其他chunk
        3. 合并去重，优先保留原始检索结果

        Args:
            docs: 原始检索结果
            max_extra_chunks: 每个section最多补充的chunk数

        Returns:
            扩展后的文档列表（原始结果 + 补充的同section chunk）
        """
        if not docs or not self._vector_store:
            return docs

        section_keys = set()
        for doc in docs:
            city = doc.metadata.get("city", "")
            header2 = doc.metadata.get("Header 2", "")
            if city and header2:
                section_keys.add((city, header2))

        if not section_keys:
            return docs

        existing_contents = {hashlib.md5(d.page_content.encode()).hexdigest() for d in docs}
        extra_docs = []

        for city, header2 in section_keys:
            try:
                section_docs = await self._vector_store.asimilarity_search(
                    query=f"{header2}",
                    k=max_extra_chunks + len(docs),
                    filter={"city": city},
                )
                for sd in section_docs:
                    if sd.metadata.get("Header 2") != header2:
                        continue
                    content_hash = hashlib.md5(sd.page_content.encode()).hexdigest()
                    if content_hash not in existing_contents:
                        existing_contents.add(content_hash)
                        extra_docs.append(sd)
                        if len(extra_docs) >= max_extra_chunks * len(section_keys):
                            break
            except Exception as e:
                logger.warning("上下文窗口扩展失败", city=city, section=header2, error=str(e))

        if extra_docs:
            logger.info(
                "上下文窗口扩展完成",
                original_count=len(docs),
                expanded_count=len(extra_docs),
                sections=len(section_keys),
            )

        return docs + extra_docs

    def _ensure_city_diversity(
        self,
        docs: List[Document],
        min_cities: int = 2,
        docs_per_city: int = 2,
    ) -> List[Document]:
        """基于city元数据的结果多样性保证。

        当检索结果集中在单一城市时，主动补充其他城市的相关文档，
        避免信息过于集中。这在用户查询比较泛化时特别有用，
        例如"美食推荐"可能需要多个城市的对比信息。

        策略：
        1. 统计结果中各城市的文档数量
        2. 如果只有1个城市，从其他城市补充文档
        3. 补充的文档通过向量检索获取，确保相关性

        Args:
            docs: 原始检索结果
            min_cities: 结果中至少包含的城市数量
            docs_per_city: 每个补充城市最多补充的文档数

        Returns:
            多样性调整后的文档列表
        """
        if not docs:
            return docs

        city_counts: Dict[str, int] = {}
        for doc in docs:
            city = doc.metadata.get("city", "")
            if city:
                city_counts[city] = city_counts.get(city, 0) + 1

        if len(city_counts) >= min_cities:
            return docs

        dominant_city = max(city_counts, key=city_counts.get) if city_counts else ""
        other_cities = [c for c in CITY_ALIASES.values() if c != dominant_city]

        return docs

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

    def _compute_file_hash(self, file_path: Path) -> str:
        """计算文件的MD5哈希值。

        用于检测文件内容是否发生变化。

        Args:
            file_path: 文件路径

        Returns:
            文件内容的MD5哈希值（十六进制字符串）
        """
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _get_db_session(self) -> Session:
        """获取数据库会话。

        优先从ResourceManager获取DatabaseService，
        如果未初始化则抛出异常。

        Returns:
            Session: SQLModel会话实例

        Raises:
            RuntimeError: 如果ResourceManager未初始化
        """
        from app.services.resource_manager import get_resource_manager
        rm = get_resource_manager()
        if rm.db_service is None:
            raise RuntimeError("数据库服务未初始化")
        return rm.db_service.get_session_maker()

    def get_loaded_documents(self) -> List[RAGDocument]:
        """获取已加载到RAG知识库的文档列表。

        Returns:
            已加载文档的列表
        """
        try:
            with self._get_db_session() as session:
                statement = select(RAGDocument).order_by(RAGDocument.created_at.desc())
                documents = session.exec(statement).all()
                return list(documents)
        except Exception as e:
            logger.error("获取已加载文档列表失败", error=str(e), exc_info=True)
            return []

    def scan_new_documents(self, docs_dir: Optional[str] = None) -> Tuple[List[Path], List[Path]]:
        """扫描knowledge_base目录，找出新文档和已变化的文档。

        扫描流程：
        1. 遍历knowledge_base目录下的所有.md文件
        2. 对比数据库中的记录，找出：
           - 新增的文件（数据库中不存在）
           - 已变化的文件（哈希值不匹配）

        Args:
            docs_dir: 文档目录路径，默认为knowledge_base目录

        Returns:
            (new_files, changed_files): 新文件列表和已变化文件列表
        """
        directory = Path(docs_dir) if docs_dir else KNOWLEDGE_BASE_DIR

        if not directory.exists():
            logger.warning("知识库目录不存在", directory=str(directory))
            return [], []

        all_files = list(directory.glob("**/*.md"))
        new_files = []
        changed_files = []

        try:
            with self._get_db_session() as session:
                for file_path in all_files:
                    relative_path = file_path.relative_to(directory)
                    filename = file_path.stem

                    existing_doc = session.exec(
                        select(RAGDocument).where(RAGDocument.filename == filename)
                    ).first()

                    if existing_doc is None:
                        new_files.append(file_path)
                    else:
                        current_hash = self._compute_file_hash(file_path)
                        if current_hash != existing_doc.file_hash:
                            changed_files.append(file_path)

            logger.info(
                "文档扫描完成",
                total_files=len(all_files),
                new_files=len(new_files),
                changed_files=len(changed_files),
            )
            return new_files, changed_files

        except Exception as e:
            logger.error("扫描新文档失败", error=str(e), exc_info=True)
            return [], []

    async def add_documents_incremental(
        self,
        docs_dir: Optional[str] = None,
        include_changed: bool = True
    ) -> Dict[str, Any]:
        """增量添加新文档到RAG知识库。

        流程：
        1. 扫描knowledge_base目录，找出新文档和已变化的文档
        2. 加载并分块这些文档
        3. 将分块后的文档添加到向量库
        4. 更新数据库中的文档跟踪记录

        Args:
            docs_dir: 文档目录路径，默认为knowledge_base目录
            include_changed: 是否包含已变化的文档（默认True）

        Returns:
            操作结果统计信息
        """
        if not self.is_initialized:
            await self.initialize()

        if self._vector_store is None:
            logger.error("向量存储不可用")
            return {
                "success": False,
                "message": "向量存储不可用",
                "added_count": 0,
                "updated_count": 0,
            }

        new_files, changed_files = self.scan_new_documents(docs_dir)
        files_to_add = new_files.copy()
        if include_changed:
            files_to_add.extend(changed_files)

        if not files_to_add:
            logger.info("没有新文档需要添加")
            return {
                "success": True,
                "message": "没有新文档需要添加",
                "added_count": 0,
                "updated_count": 0,
            }

        documents = []
        for file_path in files_to_add:
            try:
                loader = TextLoader(str(file_path), encoding="utf-8")
                docs = loader.load()
                for doc in docs:
                    doc.metadata["source"] = str(file_path)
                    doc.metadata["city"] = file_path.stem
                documents.extend(docs)
            except Exception as e:
                logger.error("加载文档失败", file_path=str(file_path), error=str(e))

        if not documents:
            logger.warning("未能加载任何文档")
            return {
                "success": False,
                "message": "未能加载任何文档",
                "added_count": 0,
                "updated_count": 0,
            }

        chunks = self.split_documents(documents)
        await self._vector_store.aadd_documents(chunks)

        try:
            with self._get_db_session() as session:
                for file_path in files_to_add:
                    filename = file_path.stem
                    relative_path = file_path.relative_to(KNOWLEDGE_BASE_DIR)
                    file_hash = self._compute_file_hash(file_path)
                    file_size = file_path.stat().st_size

                    file_chunks = [c for c in chunks if c.metadata.get("city") == filename]

                    existing_doc = session.exec(
                        select(RAGDocument).where(RAGDocument.filename == filename)
                    ).first()

                    if existing_doc:
                        existing_doc.file_hash = file_hash
                        existing_doc.chunk_count = len(file_chunks)
                        existing_doc.file_size = file_size
                        session.add(existing_doc)
                    else:
                        new_doc = RAGDocument(
                            filename=filename,
                            file_path=str(relative_path),
                            file_hash=file_hash,
                            chunk_count=len(file_chunks),
                            file_size=file_size,
                        )
                        session.add(new_doc)

                session.commit()

            logger.info(
                "增量文档添加完成",
                total_files=len(files_to_add),
                new_files=len(new_files),
                changed_files=len(changed_files),
                total_chunks=len(chunks),
            )

            return {
                "success": True,
                "message": f"成功添加 {len(new_files)} 个新文档，更新 {len(changed_files)} 个已变化文档",
                "added_count": len(new_files),
                "updated_count": len(changed_files),
                "total_chunks": len(chunks),
            }

        except Exception as e:
            logger.error("更新文档跟踪记录失败", error=str(e), exc_info=True)
            return {
                "success": False,
                "message": f"更新文档跟踪记录失败: {str(e)}",
                "added_count": 0,
                "updated_count": 0,
            }

    async def rebuild_knowledge_base(self, docs_dir: Optional[str] = None) -> Dict[str, Any]:
        """重建整个RAG知识库。

        流程：
        1. 删除向量库中的所有数据
        2. 重新加载所有文档
        3. 重新构建向量库
        4. 清空并重建文档跟踪表

        Args:
            docs_dir: 文档目录路径，默认为knowledge_base目录

        Returns:
            操作结果统计信息
        """
        try:
            directory = Path(docs_dir) if docs_dir else KNOWLEDGE_BASE_DIR

            if not directory.exists():
                return {
                    "success": False,
                    "message": f"知识库目录不存在: {directory}",
                    "document_count": 0,
                    "chunk_count": 0,
                }

            logger.info("开始重建RAG知识库...")

            documents = self.load_documents(str(directory))
            if not documents:
                return {
                    "success": False,
                    "message": "未加载到任何文档",
                    "document_count": 0,
                    "chunk_count": 0,
                }

            chunks = self.split_documents(documents)
            self._vector_store = await self.build_vector_store(chunks)

            try:
                with self._get_db_session() as session:
                    session.exec(select(RAGDocument))
                    all_docs = session.exec(select(RAGDocument)).all()
                    for doc in all_docs:
                        session.delete(doc)
                    session.commit()

                    for file_path in directory.glob("**/*.md"):
                        filename = file_path.stem
                        relative_path = file_path.relative_to(directory)
                        file_hash = self._compute_file_hash(file_path)
                        file_size = file_path.stat().st_size

                        file_chunks = [c for c in chunks if c.metadata.get("city") == filename]

                        rag_doc = RAGDocument(
                            filename=filename,
                            file_path=str(relative_path),
                            file_hash=file_hash,
                            chunk_count=len(file_chunks),
                            file_size=file_size,
                        )
                        session.add(rag_doc)

                    session.commit()

                logger.info(
                    "RAG知识库重建完成",
                    document_count=len(documents),
                    chunk_count=len(chunks),
                )

                return {
                    "success": True,
                    "message": "知识库重建成功",
                    "document_count": len(documents),
                    "chunk_count": len(chunks),
                }

            except Exception as e:
                logger.error("更新文档跟踪记录失败", error=str(e), exc_info=True)
                return {
                    "success": False,
                    "message": f"更新文档跟踪记录失败: {str(e)}",
                    "document_count": len(documents),
                    "chunk_count": len(chunks),
                }

        except Exception as e:
            logger.error("重建知识库失败", error=str(e), exc_info=True)
            return {
                "success": False,
                "message": f"重建知识库失败: {str(e)}",
                "document_count": 0,
                "chunk_count": 0,
            }

    async def close(self):
        """清理RAG流水线资源。

        关闭PGEngine连接池，释放数据库连接。
        应在应用关闭时调用。
        """
        if self._engine is not None:
            try:
                await self._engine.close()
                logger.info("RAG PGEngine连接池已关闭")
            except Exception as e:
                logger.error("关闭RAG PGEngine连接池失败", error=str(e))
            finally:
                self._engine = None
        self._vector_store = None
        self._initialized = False


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

    优先从ResourceManager获取（由生命周期管理器初始化），
    如果ResourceManager未初始化则回退到本地懒加载模式。

    Returns:
        RAGPipeline实例
    """
    global _rag_pipeline
    if _rag_pipeline is not None:
        return _rag_pipeline

    try:
        from app.services.resource_manager import get_resource_manager
        rm = get_resource_manager()
        if rm.rag_pipeline is not None:
            _rag_pipeline = rm.rag_pipeline
            return _rag_pipeline
    except RuntimeError:
        pass

    _rag_pipeline = RAGPipeline()
    logger.info("RAG流水线全局实例已创建（懒加载模式）")
    return _rag_pipeline
