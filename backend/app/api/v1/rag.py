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


