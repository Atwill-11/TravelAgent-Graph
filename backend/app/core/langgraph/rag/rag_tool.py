"""RAG知识库检索工具封装。

本模块将RAG流水线封装为LangChain Tool，使其可以被智能体直接调用。
工具封装遵循项目中weather_tool.py的规范，使用@tool装饰器定义。

工具调用流程：
  智能体 → rag_knowledge_search(query) → RAGPipeline.agenerate() → 返回结果

工具返回格式：
  {
      "text": "LLM生成的回答文本",
      "sources": [{"city": "chengdu", "source": "/path/to/chengdu.md"}, ...],
  }

此格式与weather_sub_agent等子智能体的返回格式保持一致，
便于execute_sub_agent_node统一处理。
"""

from typing import Any, Dict

from langchain_core.tools import tool

from app.core.logging import logger
from .pipeline import get_rag_pipeline


@tool
async def rag_knowledge_search(query: str) -> Dict[str, Any]:
    """旅游知识库检索工具，基于RAG技术从旅游攻略知识库中检索相关信息。

    当需要以下类型的信息时，应使用此工具：
    - 旅游攻略和旅行建议（如最佳旅游时间、行程规划建议）
    - 景点详细介绍（如历史背景、游览建议、门票信息）
    - 美食推荐（如特色菜品、推荐餐厅、饮食文化）
    - 交通住宿指南（如交通方式、住宿区域建议）
    - 旅行贴士和注意事项

    此工具通过向量相似度搜索从知识库中检索相关文档片段，
    然后使用LLM基于检索结果生成准确、有依据的回答。

    参数:
        query: 查询文本，描述需要检索的旅游信息。
               例如："成都美食推荐"、"西安必游景点"、"丽江旅行注意事项"

    返回:
        包含以下字段的字典：
        - text: LLM基于检索结果生成的回答
        - sources: 信息来源列表，包含city和source字段

    示例:
        >>> result = await rag_knowledge_search.ainvoke({"query": "成都美食推荐"})
        >>> print(result["text"])
        >>> print(result["sources"])
    """
    pipeline = get_rag_pipeline()

    if not pipeline.is_initialized:
        logger.info("RAG流水线未初始化，开始自动初始化...")
        try:
            await pipeline.initialize()
        except Exception as e:
            logger.error("RAG流水线初始化失败", error=str(e))
            return {
                "text": "知识库检索服务暂时不可用，请稍后再试。",
                "sources": [],
            }

    try:
        result = await pipeline.agenerate(query)

        return {
            "text": result["answer"],
            "sources": result.get("sources", []),
        }

    except Exception as e:
        logger.error("RAG知识检索失败", query=query[:50], error=str(e))
        return {
            "text": f"知识库检索过程中出现错误：{str(e)}",
            "sources": [],
        }


rag_tools = [rag_knowledge_search]
