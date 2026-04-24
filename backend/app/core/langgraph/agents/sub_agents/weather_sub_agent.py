from datetime import datetime

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
    model_name=settings.DASHSCOPE_SUBAGENT_LLM_MODEL,
    api_key=settings.DASHSCOPE_API_KEY,
    api_base=settings.DASHSCOPE_API_BASE,
    temperature=0.7,
    max_tokens=1000,
    timeout=180,
    max_retries=2,
)

def _get_weather_prompt_with_date() -> str:
    """获取包含当前日期的天气查询prompt。"""
    current_date = datetime.now().strftime("%Y年%m月%d日")
    return f"""{WEATHER_AGENT_PROMPT}

**重要信息:**
- 当前日期：{current_date}
- 在计算forecast_days参数时，请根据当前日期和用户查询的日期计算正确的天数，你可以参考以下例子的步骤来计算。
- 天数计算的例子：当前是2026年4月24日，用户查询2026年5月1日至2日的天气，那么查询的天气应该包括2026年5月1日至2日的天气。
由于4月有30天，所以查询应该包括4月24日、4月25日、4月26日、4月27日、4月28日、4月29日、4月30日、5月1日、5月2日的天气，一共9天。
所以forecast_days应该大于9。由于工具的forecast_days参数可选值为3、7、10、15、30，所以forecast_days应该设置为10。
"""

# 创建子智能体
weather_sub_agent = create_agent(
    model=model, 
    tools=weather_tools,
    system_prompt=_get_weather_prompt_with_date(),
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
