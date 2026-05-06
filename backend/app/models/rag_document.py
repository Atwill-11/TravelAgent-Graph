"""RAG文档跟踪模型。

用于记录已加载到RAG知识库中的文档信息，
支持增量更新和文档变化检测。
"""

from datetime import datetime, UTC
from typing import Optional
from sqlmodel import Field
from app.models.base import BaseModel


class RAGDocument(BaseModel, table=True):
    """RAG文档跟踪表。

    记录已加载到向量数据库的文档信息，包括：
    - 文件名和路径
    - 文件内容哈希（用于检测变化）
    - 分块数量
    - 加载时间

    使用方式：
        # 检查文档是否已加载
        doc = session.exec(
            select(RAGDocument).where(RAGDocument.filename == "chengdu.md")
        ).first()

        # 添加新文档记录
        new_doc = RAGDocument(
            filename="beijing.md",
            file_path="knowledge_base/beijing.md",
            file_hash="abc123...",
            chunk_count=15
        )
        session.add(new_doc)
    """

    __tablename__ = "rag_documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = Field(index=True, description="文件名（不含路径）")
    file_path: str = Field(description="文件相对路径")
    file_hash: str = Field(description="文件内容哈希值（MD5）")
    chunk_count: int = Field(default=0, description="文档分块数量")
    file_size: int = Field(default=0, description="文件大小（字节）")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="最后更新时间"
    )
