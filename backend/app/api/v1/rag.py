"""RAG知识库管理API接口。

提供RAG知识库的管理功能，包括：
1. 扫描并增量添加新文档
2. 重建整个知识库
3. 查看已加载文档列表
4. 评估RAG检索质量（Recall@K/Precision@K/MRR）
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.resource_manager import get_resource_manager


router = APIRouter()


class ScanAndAddRequest(BaseModel):
    """扫描并添加文档请求模型。"""

    docs_dir: Optional[str] = Field(
        None,
        description="文档目录路径（可选，默认为knowledge_base目录）"
    )
    include_changed: bool = Field(
        True,
        description="是否包含已变化的文档（默认True）"
    )


class ScanAndAddResponse(BaseModel):
    """扫描并添加文档响应模型。"""

    success: bool = Field(description="操作是否成功")
    message: str = Field(description="操作结果消息")
    added_count: int = Field(description="新增文档数量")
    updated_count: int = Field(description="更新文档数量")
    total_chunks: Optional[int] = Field(None, description="总分块数量")


class RebuildRequest(BaseModel):
    """重建知识库请求模型。"""

    docs_dir: Optional[str] = Field(
        None,
        description="文档目录路径（可选，默认为knowledge_base目录）"
    )


class RebuildResponse(BaseModel):
    """重建知识库响应模型。"""

    success: bool = Field(description="操作是否成功")
    message: str = Field(description="操作结果消息")
    document_count: int = Field(description="文档总数")
    chunk_count: int = Field(description="分块总数")


class DocumentInfo(BaseModel):
    """文档信息模型。"""

    id: int = Field(description="文档ID")
    filename: str = Field(description="文件名")
    file_path: str = Field(description="文件路径")
    file_hash: str = Field(description="文件哈希值")
    chunk_count: int = Field(description="分块数量")
    file_size: int = Field(description="文件大小（字节）")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")


class DocumentListResponse(BaseModel):
    """文档列表响应模型。"""

    total: int = Field(description="文档总数")
    documents: List[DocumentInfo] = Field(description="文档列表")


class EvalRequest(BaseModel):
    """RAG评估请求模型。"""

    k_values: Optional[List[int]] = Field(
        None,
        description="评估的K值列表，默认[1, 3, 5, 10]"
    )


class EvalSummary(BaseModel):
    """评估指标汇总。"""

    recall_at_1: Optional[float] = Field(None, alias="recall@1", description="Recall@1")
    precision_at_1: Optional[float] = Field(None, alias="precision@1", description="Precision@1")
    recall_at_3: Optional[float] = Field(None, alias="recall@3", description="Recall@3")
    precision_at_3: Optional[float] = Field(None, alias="precision@3", description="Precision@3")
    recall_at_5: Optional[float] = Field(None, alias="recall@5", description="Recall@5")
    precision_at_5: Optional[float] = Field(None, alias="precision@5", description="Precision@5")
    recall_at_10: Optional[float] = Field(None, alias="recall@10", description="Recall@10")
    precision_at_10: Optional[float] = Field(None, alias="precision@10", description="Precision@10")
    mrr: Optional[float] = Field(None, description="Mean Reciprocal Rank")

    class Config:
        populate_by_name = True


class PerQueryResult(BaseModel):
    """单条查询的评估结果。"""

    query_id: str = Field(description="查询ID")
    query: str = Field(description="查询文本")
    total_relevant: int = Field(description="全库相关文档数")
    retrieved_count: int = Field(description="检索返回文档数")
    relevant_in_retrieved: int = Field(description="检索结果中相关文档数")
    mrr: float = Field(description="Reciprocal Rank")
    extra_metrics: Optional[Dict[str, float]] = Field(
        None, description="各K值下的Recall@K和Precision@K"
    )


class EvalResponse(BaseModel):
    """RAG评估响应模型。"""

    summary: Dict[str, float] = Field(description="汇总指标")
    query_count: int = Field(description="评估查询总数")
    k_values: List[int] = Field(description="评估使用的K值列表")
    per_query: List[Dict[str, Any]] = Field(description="逐条查询评估详情")


@router.post(
    "/scan-and-add",
    response_model=ScanAndAddResponse,
    summary="扫描并添加新文档",
    description="""
扫描knowledge_base目录，自动识别新文档和已变化的文档，
并将它们增量添加到RAG知识库中。

**功能说明：**
1. 扫描knowledge_base目录下的所有.md文件
2. 对比数据库记录，找出新增和已变化的文档
3. 对这些文档进行分块、嵌入和存储
4. 更新文档跟踪记录

**参数说明：**
- `docs_dir`: 可选，指定文档目录路径，默认使用knowledge_base目录
- `include_changed`: 是否包含已变化的文档，默认True

**返回说明：**
- `success`: 操作是否成功
- `message`: 操作结果消息
- `added_count`: 新增文档数量
- `updated_count`: 更新文档数量
- `total_chunks`: 总分块数量
    """,
)
async def scan_and_add_documents(
    request: Request,
    body: ScanAndAddRequest = Depends(),
) -> ScanAndAddResponse:
    """扫描并增量添加新文档到RAG知识库。"""
    try:
        rm = get_resource_manager()
        rag_pipeline = rm.rag_pipeline

        if rag_pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="RAG流水线未初始化，请检查应用启动日志"
            )

        logger.info(
            "开始扫描并添加文档",
            docs_dir=body.docs_dir,
            include_changed=body.include_changed,
        )

        result = await rag_pipeline.add_documents_incremental(
            docs_dir=body.docs_dir,
            include_changed=body.include_changed,
        )

        return ScanAndAddResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("扫描并添加文档失败", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"扫描并添加文档失败: {str(e)}"
        )


@router.post(
    "/rebuild",
    response_model=RebuildResponse,
    summary="重建知识库",
    description="""
重建整个RAG知识库，清空现有数据并重新加载所有文档。

**功能说明：**
1. 删除向量库中的所有数据
2. 重新加载knowledge_base目录下的所有文档
3. 重新构建向量库
4. 清空并重建文档跟踪表

**注意：**
此操作会清空现有知识库，请谨慎使用！

**参数说明：**
- `docs_dir`: 可选，指定文档目录路径，默认使用knowledge_base目录

**返回说明：**
- `success`: 操作是否成功
- `message`: 操作结果消息
- `document_count`: 加载的文档总数
- `chunk_count`: 生成的分块总数
    """,
)
async def rebuild_knowledge_base(
    request: Request,
    body: RebuildRequest = Depends(),
) -> RebuildResponse:
    """重建整个RAG知识库。"""
    try:
        rm = get_resource_manager()
        rag_pipeline = rm.rag_pipeline

        if rag_pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="RAG流水线未初始化，请检查应用启动日志"
            )

        logger.info("开始重建知识库", docs_dir=body.docs_dir)

        result = await rag_pipeline.rebuild_knowledge_base(docs_dir=body.docs_dir)

        return RebuildResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("重建知识库失败", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"重建知识库失败: {str(e)}"
        )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="获取已加载文档列表",
    description="""
获取已加载到RAG知识库的文档列表。

**返回说明：**
- `total`: 文档总数
- `documents`: 文档列表，包含每个文档的详细信息
  - `id`: 文档ID
  - `filename`: 文件名
  - `file_path`: 文件路径
  - `file_hash`: 文件哈希值
  - `chunk_count`: 分块数量
  - `file_size`: 文件大小（字节）
  - `created_at`: 创建时间
  - `updated_at`: 更新时间
    """,
)
async def get_loaded_documents(request: Request) -> DocumentListResponse:
    """获取已加载到RAG知识库的文档列表。"""
    try:
        rm = get_resource_manager()
        rag_pipeline = rm.rag_pipeline

        if rag_pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="RAG流水线未初始化，请检查应用启动日志"
            )

        documents = rag_pipeline.get_loaded_documents()

        doc_infos = [
            DocumentInfo(
                id=doc.id,
                filename=doc.filename,
                file_path=doc.file_path,
                file_hash=doc.file_hash,
                chunk_count=doc.chunk_count,
                file_size=doc.file_size,
                created_at=doc.created_at.isoformat(),
                updated_at=doc.updated_at.isoformat(),
            )
            for doc in documents
        ]

        return DocumentListResponse(
            total=len(doc_infos),
            documents=doc_infos,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取已加载文档列表失败", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取已加载文档列表失败: {str(e)}"
        )


@router.post(
    "/evaluate",
    response_model=EvalResponse,
    summary="评估RAG检索质量",
    description="""
对RAG检索质量进行系统性评估，输出Recall@K、Precision@K、MRR等指标。

**评估指标说明：**
- **Recall@K**：在所有相关文档中，top-K检索结果覆盖的比例
  - 衡量检索系统的查全能力，值越高表示遗漏的相关文档越少
- **Precision@K**：top-K检索结果中，相关文档的比例
  - 衡量检索系统的查准能力，值越高表示返回的噪声越少
- **MRR（Mean Reciprocal Rank）**：第一个相关文档排名倒数的均值
  - 衡量检索系统将相关文档排在靠前位置的能力

**参数说明：**
- `k_values`: 评估的K值列表，默认[1, 3, 5, 10]

**返回说明：**
- `summary`: 各指标的汇总均值
- `query_count`: 评估的查询总数
- `k_values`: 评估使用的K值列表
- `per_query`: 每条查询的详细评估结果
    """,
)
async def evaluate_rag_retrieval(
    request: Request,
    body: EvalRequest,
) -> EvalResponse:
    """评估RAG检索质量。"""
    try:
        rm = get_resource_manager()
        rag_pipeline = rm.rag_pipeline

        if rag_pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="RAG流水线未初始化，请检查应用启动日志"
            )

        from app.core.langgraph.rag.evaluator import RAGEvaluator

        evaluator = RAGEvaluator(rag_pipeline)

        logger.info("开始RAG检索质量评估", k_values=body.k_values)

        report = await evaluator.evaluate(k_values=body.k_values)

        logger.info(
            "RAG检索质量评估完成",
            summary=report.get("summary"),
            query_count=report.get("query_count"),
        )

        return EvalResponse(**report)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("RAG检索质量评估失败", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"RAG检索质量评估失败: {str(e)}"
        )


class ABTestRequest(BaseModel):
    """RAG A/B测试请求模型。"""

    k_values: Optional[List[int]] = Field(
        None,
        description="评估的K值列表，默认[1, 3, 5, 10]"
    )
    configs: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="""自定义配置字典，格式为 {"配置名": {"参数名": 参数值, ...}}。
不传递此参数则使用默认5种配置：
- baseline: 纯向量检索（所有增强策略关闭）
- mqe_only: 仅启用MQE多查询扩展
- hyde_only: 仅启用HyDE假设文档嵌入
- hybrid_only: 仅启用混合检索（向量+关键词）
- full: 全部策略启用"""
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "k_values": [1, 3, 5, 10]
                },
                {
                    "k_values": [5],
                    "configs": {
                        "my_baseline": {
                            "use_mqe": False,
                            "use_hyde": False,
                            "use_filter": False,
                            "use_hybrid": False,
                            "use_context_expansion": False,
                            "use_diversity": False
                        },
                        "my_enhanced": {
                            "use_mqe": True,
                            "use_hyde": True,
                            "use_filter": True,
                            "use_hybrid": True,
                            "use_context_expansion": True,
                            "use_diversity": True
                        }
                    }
                }
            ]
        }
    }


class ABTestResponse(BaseModel):
    """RAG A/B测试响应模型。"""

    configs: Dict[str, Dict[str, Any]] = Field(description="各配置的参数详情")
    k_values: List[int] = Field(description="评估使用的K值列表")
    results: Dict[str, Dict[str, Any]] = Field(description="各配置的评估结果")
    timing: Dict[str, float] = Field(description="各配置的总耗时（秒）")
    comparison: Dict[str, Any] = Field(description="配置间的对比分析")


@router.post(
    "/evaluate/ab_test",
    response_model=ABTestResponse,
    summary="RAG检索策略A/B测试",
    description="""
对不同的RAG检索策略组合进行A/B测试，对比各策略的效果差异。

**默认测试配置：**
- **baseline**: 纯向量检索（所有增强策略关闭）
- **mqe_only**: 仅启用MQE多查询扩展
- **hyde_only**: 仅启用HyDE假设文档嵌入
- **hybrid_only**: 仅启用混合检索（向量+关键词）
- **full**: 全部策略启用

**测试结果可以回答：**
1. MQE对召回率有多大提升？
2. HyDE对召回率有多大提升？
3. 混合检索（关键词+语义）是否优于纯向量检索？
4. 各策略组合是否有叠加效果？

**参数说明：**
- `k_values`: 评估的K值列表，默认[1, 3, 5, 10]
- `configs`: 自定义配置字典，可覆盖默认配置

**返回说明：**
- `configs`: 各配置的参数详情
- `results`: 各配置的评估结果（包含summary、query_count、per_query）
- `comparison`: 配置间的对比分析（指标差异、排名等）
    """,
)
async def evaluate_rag_ab_test(
    request: Request,
    body: ABTestRequest,
) -> ABTestResponse:
    """RAG检索策略A/B测试。"""
    try:
        rm = get_resource_manager()
        rag_pipeline = rm.rag_pipeline

        if rag_pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="RAG流水线未初始化，请检查应用启动日志"
            )

        from app.core.langgraph.rag.evaluator import RAGEvaluator

        evaluator = RAGEvaluator(rag_pipeline)

        langfuse_client = getattr(rm, "langfuse", None)

        logger.info("开始RAG A/B测试", k_values=body.k_values, configs=body.configs)

        report = await evaluator.ab_test(
            k_values=body.k_values,
            configs=body.configs,
            langfuse_client=langfuse_client,
        )

        logger.info(
            "RAG A/B测试完成",
            config_count=len(report.get("results", {})),
        )

        return ABTestResponse(**report)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("RAG A/B测试失败", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"RAG A/B测试失败: {str(e)}"
        )


class AnnotateRequest(BaseModel):
    """LLM标注请求模型。"""

    output_path: Optional[str] = Field(
        None,
        description="输出文件路径（可选，默认覆盖原eval_dataset.json）"
    )
    passage_signature_length: int = Field(
        30,
        description="每个passage特征文本的长度（字符数），默认30"
    )
    candidate_k: int = Field(
        20,
        description="向量检索的候选chunk数量，默认20。增大可提高召回但增加LLM成本"
    )
    max_concurrency: int = Field(
        5,
        description="最大并发数，默认5。根据API限流策略调整，通义千问建议不超过10"
    )


class AnnotateResponse(BaseModel):
    """LLM标注响应模型。"""

    total_queries: int = Field(description="标注的查询总数")
    total_chunks: int = Field(description="全库文档分块总数")
    candidate_k: int = Field(description="向量检索的候选chunk数量")
    max_concurrency: int = Field(description="最大并发数")
    annotations: List[Dict[str, Any]] = Field(description="每条查询的标注统计")
    saved_to: str = Field(description="标注结果保存路径")


@router.post(
    "/evaluate/annotate",
    response_model=AnnotateResponse,
    summary="LLM预标注评估数据集",
    description="""
使用LLM为评估数据集预标注相关段落（relevant_passages）。

**两阶段检索策略（避免上下文爆炸）：**
1. 阶段1：向量检索 → 找到候选chunk（top-k，默认20个）
2. 阶段2：LLM判断 → 只判断候选chunk的相关性

这样可以将上下文从N个chunk降到k个chunk，大幅降低API成本。

**并行优化：**
- 使用asyncio.Semaphore控制并发，避免API限流
- 默认并发数为5，可根据API限制调整
- 并行处理大幅提升标注速度

**预标注的优势：**
- 比关键词/章节匹配更精准
- 能处理需要语义理解的复杂相关性判断
- 标注结果持久化，评估时无需重复调用LLM

**参数说明：**
- `candidate_k`: 候选chunk数量，默认20。增大可提高召回但增加LLM成本
- `passage_signature_length`: 特征文本长度，默认30字符
- `max_concurrency`: 最大并发数，默认5。通义千问建议不超过10

**注意：**
- 标注过程需要调用LLM API，会产生费用
- 标注后需重建知识库（如果文档有变更）
- 建议在文档稳定后执行一次标注即可
    """,
)
async def annotate_eval_dataset(
    request: Request,
    body: AnnotateRequest,
) -> AnnotateResponse:
    """LLM预标注评估数据集。"""
    try:
        rm = get_resource_manager()
        rag_pipeline = rm.rag_pipeline

        if rag_pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="RAG流水线未初始化，请检查应用启动日志"
            )

        from app.core.langgraph.rag.evaluator import RAGEvaluator

        evaluator = RAGEvaluator(rag_pipeline)

        logger.info(
            "开始LLM标注评估数据集",
            candidate_k=body.candidate_k,
            max_concurrency=body.max_concurrency,
        )

        result = await evaluator.annotate_dataset_with_llm(
            output_path=body.output_path,
            passage_signature_length=body.passage_signature_length,
            candidate_k=body.candidate_k,
            max_concurrency=body.max_concurrency,
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        logger.info(
            "LLM标注完成",
            total_queries=result["total_queries"],
            total_chunks=result["total_chunks"],
        )

        return AnnotateResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("LLM标注失败", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"LLM标注失败: {str(e)}"
        )
