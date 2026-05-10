"""RAG知识库检索子智能体。

本模块实现了RAG子智能体，供规划智能体在任务执行阶段调用。
当规划智能体判断需要检索旅游知识时，会生成类型为"rag"的任务，
由execute_sub_agent_node路由到本子智能体执行。

RAG子智能体使用create_agent创建，封装LLM和统一检索工具：
- LLM负责推理：决定如何组合查询、综合分析检索结果
- 检索工具负责执行统一增强检索流水线（查询扩展→混合检索→合并去重→后处理）

调用链路：
  plan_node（生成rag类型任务）
    → execute_sub_agent_node（路由到call_rag_sub_agent）
      → rag_sub_agent（LLM + 检索工具）
        → rag_knowledge_retrieve
          → RAGPipeline.aretrieve_enhanced
            → 返回结果

返回格式与weather_sub_agent一致：
  {
      "text": "LLM总结的回答文本",
      "structured_data": {
          "sources": [
              {"city": "xian", "section": "旅行贴士", "subsection": None, "source": "..."},
              ...
          ],
          "total_documents": 4,
          "cities": ["xian"],
      },
  }

折中方案说明：
  text字段：LLM基于检索结果生成的精炼回答，消除了chunk间的冗余
  structured_data字段：从工具调用结果中提取的元数据，保留来源可追溯性
  主智能体既能获得精炼信息，又能知道信息来源城市和章节
"""

import json
from typing import Any, Dict, List

from langchain_core.messages import ToolMessage

from app.core.config import settings
from app.core.logging import logger
from app.core.langgraph.rag.rag_tool import rag_tools
from app.core.prompts import RAG_AGENT_PROMPT

from langchain_qwq import ChatQwen
from langchain.agents import create_agent
from langchain.tools import tool

RAG_TOOL_NAMES = {"rag_knowledge_retrieve"}

model = ChatQwen(
    model_name=settings.DASHSCOPE_SUBAGENT_LLM_MODEL,
    api_key=settings.DASHSCOPE_API_KEY,
    api_base=settings.DASHSCOPE_API_BASE,
    temperature=0.5,
    max_retries=2,
)

rag_sub_agent = create_agent(
    model=model,
    tools=rag_tools,
    system_prompt=RAG_AGENT_PROMPT,
)
logger.info("RAG子智能体创建完成")


def _extract_sources_from_tool_content(
    tool_content: Any,
) -> List[Dict[str, Any]]:
    """从工具返回的JSON内容中提取文档来源元数据。

    工具返回格式为：
      {"documents": [{"content": "...", "metadata": {...}}, ...], "total_count": N}

    提取每条文档的city、section、subsection、source字段，
    构建去重后的来源列表。

    Args:
        tool_content: 工具返回的内容（str或dict）

    Returns:
        去重后的来源列表
    """
    try:
        if isinstance(tool_content, str):
            data = json.loads(tool_content)
        elif isinstance(tool_content, dict):
            data = tool_content
        else:
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    documents = data.get("documents", [])
    seen_keys = set()
    sources = []

    for doc in documents:
        metadata = doc.get("metadata", {})
        city = metadata.get("city", "")
        section = metadata.get("Header 2", "")
        subsection = metadata.get("Header 3", "")
        source = metadata.get("source", "")

        dedup_key = (city, section, subsection)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        sources.append({
            "city": city,
            "section": section,
            "subsection": subsection if subsection else None,
            "source": source,
        })

    return sources


def _extract_structured_data(messages: list) -> Dict[str, Any]:
    """从agent执行结果的messages中提取所有RAG工具调用的结构化数据。

    遍历messages列表，找到所有RAG工具（rag_knowledge_retrieve）
    的ToolMessage，提取文档来源元数据并合并去重。

    Args:
        messages: agent执行结果中的messages列表

    Returns:
        包含sources、total_documents、cities的结构化数据字典
    """
    all_sources: List[Dict[str, Any]] = []
    total_documents = 0
    seen_keys = set()

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        if msg.name not in RAG_TOOL_NAMES:
            continue

        sources = _extract_sources_from_tool_content(msg.content)

        for src in sources:
            dedup_key = (src["city"], src["section"], src["subsection"])
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            all_sources.append(src)

        try:
            if isinstance(msg.content, str):
                data = json.loads(msg.content)
            elif isinstance(msg.content, dict):
                data = msg.content
            else:
                data = {}
            total_documents += data.get("total_count", 0)
        except (json.JSONDecodeError, TypeError):
            pass

    cities = list(dict.fromkeys(
        src["city"] for src in all_sources if src["city"]
    ))

    return {
        "sources": all_sources,
        "total_documents": total_documents,
        "cities": cities,
    }


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
- text: 基于知识库检索结果生成的精炼回答
- structured_data: 检索来源元数据，包含sources（城市/章节/来源）、total_documents、cities
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
        result = await rag_sub_agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]}
        )

        messages = result.get("messages", [])
        text_result = messages[-1].content if messages else ""

        structured_data = _extract_structured_data(messages)

        logger.info(
            "RAG子智能体处理完成",
            query=query[:50],
            answer_length=len(text_result),
            sources_count=len(structured_data["sources"]),
            cities=structured_data["cities"],
        )

        return {
            "text": text_result,
            "structured_data": structured_data,
        }

    except Exception as e:
        logger.error("RAG子智能体处理失败", query=query[:50], error=str(e))
        return {
            "text": f"知识库检索失败：{str(e)}",
            "structured_data": None,
        }
