"""RAG知识库检索系统。

本包实现了基于LangChain的RAG（Retrieval-Augmented Generation）系统，
为旅游规划智能体提供知识库检索能力。

核心组件：
- RAGPipeline: RAG流水线，包含文档加载、分块、嵌入、存储、检索、生成全流程
- rag_tool: 封装为LangChain Tool，供智能体调用

数据流向：
  原始文档 → 文档加载 → 文本分块 → 向量嵌入 → PGVector存储
                                                        ↓
  用户查询 → 向量检索 → 上下文组装 → LLM生成 → 最终回答
"""

from .pipeline import RAGPipeline, get_rag_pipeline
from .rag_tool import rag_knowledge_search

__all__ = [
    "RAGPipeline",
    "get_rag_pipeline",
    "rag_knowledge_search",
]
