WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**可用工具:**
- get_travel_weather: 获取指定城市的旅游天气信息
  - city_name: 城市名称（如：北京、上海、广州）
  - forecast_days: 预报天数，可选值：3, 7, 10, 15, 30，默认为3天

- search_city: 搜索城市并返回城市信息
  - city_name: 城市名称（支持模糊搜索）

**职责:**
- 根据用户提供的城市名称，使用search_city工具查询该城市的相关信息
- 根据search_city得到的城市信息，使用get_travel_weather工具查询该城市的旅游天气信息
- 提供get_travel_weather工具的输出，提供温度、天气状况、风力、湿度、空气质量等关键信息

**注意事项:**
- 必须使用工具查询天气，不要编造天气信息
"""

from app.core.config import settings
from app.core.langgraph.tools.local import weather_tools

DASHSCOPE_API_KEY = settings.DASHSCOPE_API_KEY
DASHSCOPE_API_BASE = settings.DASHSCOPE_API_BASE

from langchain_qwq import ChatQwen  
from langchain.agents import create_agent  
from langchain.tools import tool

# 初始化语言模型
model = ChatQwen(
    model_name="qwen3.5-flash-2026-02-23",
    api_key=DASHSCOPE_API_KEY,
    api_base=DASHSCOPE_API_BASE,
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
print("weather子智能体创建完成")
# 将子智能体封装为一个工具，供主智能体调用
from langchain_core.messages import ToolMessage


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
