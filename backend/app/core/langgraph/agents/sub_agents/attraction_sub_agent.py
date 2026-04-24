from app.core.config import settings
from app.core.logging import logger
from app.core.langgraph.tools import get_attraction_tools
from app.schemas import Attraction
from app.core.prompts import ATTRACTION_AGENT_PROMPT

from langchain_qwq import ChatQwen  
from langchain.agents import create_agent  
from langchain.tools import tool

# 初始化语言模型
model = ChatQwen(
    model_name="qwen3.5-flash-2026-02-23",
    api_key=settings.DASHSCOPE_API_KEY,
    api_base=settings.DASHSCOPE_API_BASE,
    temperature=0.7,
    max_tokens=1000,
    timeout=180,  # 增加到 3 分钟，支持复杂的景点搜索
    max_retries=2,
)

# 创建子智能体（使用景点搜索专用工具集）
attraction_sub_agent = create_agent(
    model=model, 
    tools=get_attraction_tools(),  # 只包含景点搜索相关的工具
    system_prompt=ATTRACTION_AGENT_PROMPT,
)
logger.info("attraction子智能体创建完成")
# 将子智能体封装为一个工具，供主智能体调用
from langchain_core.messages import ToolMessage


@tool("attraction_sub_agent", description="景点子智能体，专门用于搜索景点信息的任务")
async def call_attraction_sub_agent(query: str) -> dict:
    """调用attraction子智能体处理查询，返回文本结果和结构化景点数据。
    
    从子智能体的返回消息中提取 ToolMessage，获取 search_attractions_with_details 工具的原始结构化输出，
    并将其转换为 Attraction 对象列表。
    """
    result = await attraction_sub_agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]}
    )
    
    messages = result.get("messages", [])
    text_result = messages[-1].content if messages else ""
    
    attractions = []
    for msg in messages:
        
        if isinstance(msg, ToolMessage):
            
            if msg.name == "search_attractions_with_details":
                try:
                    import json
                    content = msg.content
                    if isinstance(content, str):
                        data = json.loads(content)
                    elif isinstance(content, dict):
                        data = content
                    else:
                        logger.error(f"未知的 content 类型: {type(content)}")
                        continue
                    
                    pois = data.get("pois", [])
                    logger.info(f"pois 数量: {len(pois)}")
                    
                    for i, poi in enumerate(pois):
                        detail = poi.get("detail", {})
                        
                        if detail and "error" not in detail:
                            try:
                                attraction = Attraction.from_poi_detail(detail)
                                attractions.append(attraction)
                            except Exception as e:
                                logger.error(f"创建 Attraction 对象失败: {e}")
                        elif "error" in detail:
                            logger.warning(f"跳过包含错误的 POI: {detail.get('error')}")
                    break
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    logger.error(f"解析景点数据失败: {e}")
                    import traceback
                    traceback.print_exc()
                    pass
    
    return {
        "text": text_result,
        "structured_data": attractions,
    }
