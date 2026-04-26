"""RAG知识库检索子智能体。

本模块实现了RAG子智能体，供规划智能体在任务执行阶段调用。
当规划智能体判断需要检索旅游知识时，会生成类型为"rag"的任务，
由execute_sub_agent_node路由到本子智能体执行。

RAG子智能体与weather/attraction/hotel子智能体并列，
遵循相同的调用规范和返回格式。

调用链路：
  plan_node（生成rag类型任务）
    → execute_sub_agent_node（路由到call_rag_sub_agent）
      → rag_knowledge_search（RAG工具）
        → RAGPipeline.agenerate（检索+生成）
          → 返回结果

返回格式与weather_sub_agent一致：
  {
      "text": "回答文本",
      "structured_data": None,  # RAG暂无结构化数据
  }
"""

from langchain_core.tools import tool

from app.core.logging import logger
from app.core.langgraph.rag.rag_tool import rag_knowledge_search


@tool(
    "rag_sub_agent",
    description="""旅游知识库检索子智能体，基于RAG技术从旅游攻略知识库中检索和生成信息。

适用场景：
- 需要旅游攻略和旅行建议（最佳旅游时间、行程规划建议等）
- 需要景点详细介绍（历史背景、游览建议、门票信息等）
- 需要美食推荐（特色菜品、推荐餐厅、饮食文化等）
- 需要交通住宿指南（交通方式、住宿区域建议等）
- 需要旅行贴士和注意事项

输入格式：
- 自然语言查询，描述需要检索的旅游信息
- 示例："成都美食推荐"、"西安必游景点介绍"、"丽江旅行注意事项"

输出：
- text: 基于知识库检索结果生成的回答
- structured_data: None（RAG暂不提供结构化数据）
""",
)
async def call_rag_sub_agent(query: str) -> dict:
    """调用RAG子智能体，从知识库中检索旅游信息并生成回答。

    Args:
        query: 查询文本，描述需要检索的旅游信息

    Returns:
        包含text和structured_data字段的字典
    """
    logger.info("RAG子智能体开始处理查询", query=query[:100])

    try:
        result = await rag_knowledge_search.ainvoke({"query": query})

        if isinstance(result, dict):
            text = result.get("text", "")
        else:
            text = str(result)

        logger.info(
            "RAG子智能体处理完成",
            query=query[:50],
            answer_length=len(text),
        )

        return {
            "text": text,
            "structured_data": None,
        }

    except Exception as e:
        logger.error("RAG子智能体处理失败", query=query[:50], error=str(e))
        return {
            "text": f"知识库检索失败：{str(e)}",
            "structured_data": None,
        }
