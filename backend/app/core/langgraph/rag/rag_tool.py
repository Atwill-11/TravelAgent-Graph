"""RAG知识库检索工具封装。

本模块将RAG流水线封装为LangChain Tool，使其可以被智能体直接调用。
工具封装遵循项目中weather_tool.py的规范，使用@tool装饰器定义。

工具调用流程：
  智能体 → rag_knowledge_retrieve(query) → RAGPipeline.aretrieve() → 返回文档
  智能体 → rag_expanded_retrieve(query) → RAGPipeline.aexpanded_retrieve() → 返回文档

工具返回格式：
  {
      "documents": [{"content": "...", "metadata": {...}}, ...],
      "total_count": 3,
  }

此格式供RAG子智能体中的LLM综合分析后生成最终回答。
"""

from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_core.tools import tool

from app.core.logging import logger
from .pipeline import get_rag_pipeline


def _format_retrieval_result(docs: List[Document]) -> Dict[str, Any]:
    """将检索到的Document列表格式化为工具返回值。"""
    documents = []
    for doc in docs:
        documents.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
        })
    return {
        "documents": documents,
        "total_count": len(documents),
    }


@tool
async def rag_knowledge_retrieve(query: str, k: int = 4) -> Dict[str, Any]:
    """旅游知识库基础检索工具，通过向量相似度搜索从旅游攻略知识库中检索相关文档片段。

    当需要以下类型的信息时，应使用此工具：
    - 旅游攻略和旅行建议（如最佳旅游时间、行程规划建议）
    - 景点详细介绍（如历史背景、游览建议、门票信息）
    - 美食推荐（如特色菜品、推荐餐厅、饮食文化）
    - 交通住宿指南（交通方式、住宿区域建议）
    - 旅行贴士和注意事项

    此工具仅执行检索，不生成回答。请根据检索到的文档内容自行分析和回答用户问题。

    参数:
        query: 查询文本，描述需要检索的旅游信息。
               例如："成都美食推荐"、"西安必游景点"、"丽江旅行注意事项"
        k: 返回的文档数量，默认4

    返回:
        包含以下字段的字典：
        - documents: 检索到的文档列表，每个文档包含content和metadata
        - total_count: 检索到的文档总数
    """
    pipeline = get_rag_pipeline()

    if not pipeline.is_initialized:
        logger.info("RAG流水线未初始化，开始自动初始化...")
        try:
            await pipeline.initialize()
        except Exception as e:
            logger.error("RAG流水线初始化失败", error=str(e))
            return {
                "documents": [],
                "total_count": 0,
            }

    try:
        docs = await pipeline.aretrieve(query, k=k)
        return _format_retrieval_result(docs)

    except Exception as e:
        logger.error("RAG知识检索失败", query=query[:50], error=str(e))
        return {
            "documents": [],
            "total_count": 0,
        }


@tool
async def rag_expanded_retrieve(query: str, k: int = 4) -> Dict[str, Any]:
    """旅游知识库扩展检索工具，整合多查询扩展(MQE)与假设文档嵌入(HyDE)。

    与基础检索工具相比，此工具通过以下方式提高召回率：
    - 多查询扩展(MQE)：生成语义等价的多样化查询，覆盖不同表述方式
    - 假设文档嵌入(HyDE)：生成假设性答案段落，缩小查询与文档的语义鸿沟
    - 合并去重：并行检索后合并结果，按出现频次排序

    适用场景：
    - 基础检索结果不够全面时
    - 需要从多个角度获取信息时
    - 查询表述与文档用语差异较大时

    参数:
        query: 查询文本，描述需要检索的旅游信息
        k: 最终返回的文档数量，默认4

    返回:
        包含以下字段的字典：
        - documents: 检索到的文档列表，每个文档包含content和metadata
        - total_count: 检索到的文档总数
    """
    pipeline = get_rag_pipeline()

    if not pipeline.is_initialized:
        logger.info("RAG流水线未初始化，开始自动初始化...")
        try:
            await pipeline.initialize()
        except Exception as e:
            logger.error("RAG流水线初始化失败", error=str(e))
            return {
                "documents": [],
                "total_count": 0,
            }

    try:
        docs = await pipeline.aexpanded_retrieve(query, k=k)
        return _format_retrieval_result(docs)

    except Exception as e:
        logger.error("RAG扩展检索失败", query=query[:50], error=str(e))
        return {
            "documents": [],
            "total_count": 0,
        }


rag_tools = [rag_knowledge_retrieve, rag_expanded_retrieve]
