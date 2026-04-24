from app.core.config import settings
from app.core.logging import logger
from app.core.langgraph.tools.local import weather_tools
from app.core.prompts import WEATHER_AGENT_PROMPT

from langchain_qwq import ChatQwen  
from langchain.agents import create_agent  
from langchain.tools import tool
from langchain_core.messages import ToolMessage

# 初始化语言模型
model = ChatQwen(
    model_name="qwen3.5-flash-2026-02-23",
    api_key=settings.DASHSCOPE_API_KEY,
    api_base=settings.DASHSCOPE_API_BASE,
    temperature=0.7,
    max_tokens=1000,
    timeout=180,  # 增加到 3 分钟，支持复杂的天气查询
    max_retries=2,
)

# 创建子智能体（无工具，仅作为一个功能模块）
weather_sub_agent = create_agent(
    model=model, 
    tools=weather_tools,
    system_prompt=WEATHER_AGENT_PROMPT,
)
logger.info("weather子智能体创建完成")

# 将子智能体封装为一个工具，供主智能体调用
@tool("weather_sub_agent", description="天气子智能体，专门用于查询天气信息的任务")
async def call_weather_sub_agent(query: str) -> dict:
    """调用weather子智能体处理查询，返回文本结果和结构化天气数据。
    
    从子智能体的返回消息中提取 ToolMessage，获取 get_travel_weather 工具的原始结构化输出。
    """
    result = await weather_sub_agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]}
    )
    
    messages = result.get("messages", [])
    text_result = messages[-1].content if messages else ""
    
    structured_data = None
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "get_travel_weather":
            try:
                import json
                if isinstance(msg.content, str):
                    structured_data = json.loads(msg.content)
                elif isinstance(msg.content, dict):
                    structured_data = msg.content
                break
            except (json.JSONDecodeError, TypeError):
                pass
    
    return {
        "text": text_result,
        "structured_data": structured_data,
    }
