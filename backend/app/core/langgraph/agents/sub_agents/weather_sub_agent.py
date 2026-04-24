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

**forecast_days计算规则（必须严格遵守）：**
1. 计算公式：forecast_days = (查询结束日期 - 当前日期) + 1
2. 必须向上取整到可选值：3、7、10、15、30
3. 示例计算：
   - 当前：2026年4月24日，查询：2026年4月26日至27日
   - 计算：(4月27日 - 4月24日) + 1 = 4天
   - 向上取整：forecast_days = 7（因为4 > 3）
   
   - 当前：2026年4月24日，查询：2026年5月1日至2日
   - 计算：(5月2日 - 4月24日) + 1 = 9天
   - 向上取整：forecast_days = 10（因为9 > 7）

**关键提醒：**
- forecast_days必须足够覆盖从当前日期到查询结束日期的所有天数
- 宁可设置更大的值，也不要设置过小导致数据缺失
"""

# 创建子智能体
weather_sub_agent = create_agent(
    model=model, 
    tools=weather_tools,
    system_prompt=_get_weather_prompt_with_date(),
)
logger.info("weather子智能体创建完成")

import re
from datetime import datetime, timedelta


def _extract_date_range(query: str) -> tuple[datetime, datetime] | None:
    """从查询字符串中提取日期范围。
    
    支持的格式：
    - "查询西安从2026-04-29至2026-04-30的天气情况"
    - "查询2026年4月29日至30日西安的天气情况"
    
    返回:
        (start_date, end_date) 或 None
    """
    patterns = [
        r'从(\d{4}-\d{2}-\d{2})至(\d{4}-\d{2}-\d{2})',
        r'(\d{4})年(\d{1,2})月(\d{1,2})日至(\d{1,2})月(\d{1,2})日',
        r'(\d{4})年(\d{1,2})月(\d{1,2})日至(\d{1,2})日',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                start_date = datetime.strptime(groups[0], "%Y-%m-%d")
                end_date = datetime.strptime(groups[1], "%Y-%m-%d")
                return (start_date, end_date)
            elif len(groups) == 5:
                year, start_month, start_day, end_month, end_day = groups
                start_date = datetime(int(year), int(start_month), int(start_day))
                end_date = datetime(int(year), int(end_month), int(end_day))
                return (start_date, end_date)
            elif len(groups) == 4:
                year, month, start_day, end_day = groups
                start_date = datetime(int(year), int(month), int(start_day))
                end_date = datetime(int(year), int(month), int(end_day))
                return (start_date, end_date)
    
    return None


def _filter_weather_data(
    weather_data: dict,
    start_date: datetime,
    end_date: datetime
) -> dict:
    """过滤天气数据，只保留目标日期范围内的数据。"""
    if not weather_data or "weather" not in weather_data:
        return weather_data
    
    filtered_weather = []
    for day_data in weather_data["weather"]:
        try:
            date_str = day_data.get("date", "")
            weather_date = datetime.strptime(date_str, "%Y-%m-%d")
            if start_date <= weather_date <= end_date:
                filtered_weather.append(day_data)
        except (ValueError, TypeError):
            continue
    
    result = weather_data.copy()
    result["weather"] = filtered_weather
    return result


@tool(
    "weather_sub_agent",
    description="""天气子智能体，专门用于查询天气信息的任务。
    
输入格式要求：
- 必须包含城市名称和日期范围
- 推荐格式："查询[城市]从[开始日期]至[结束日期]的天气情况"
- 示例："查询西安从2026-04-29至2026-04-30的天气情况"

输出：
- text: 天气信息的文本描述
- structured_data: 过滤后的结构化天气数据（仅包含目标日期范围）
"""
)
async def call_weather_sub_agent(query: str) -> dict:
    """调用weather子智能体处理查询，返回文本结果和结构化天气数据。
    
    从子智能体的返回消息中提取 ToolMessage，获取 get_travel_weather 工具的原始结构化输出。
    并根据查询中的日期范围过滤天气数据。
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
                
                date_range = _extract_date_range(query)
                if date_range and structured_data:
                    start_date, end_date = date_range
                    structured_data = _filter_weather_data(
                        structured_data, start_date, end_date
                    )
                    logger.info(
                        "已过滤天气数据",
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d"),
                        days_count=len(structured_data.get("weather", []))
                    )
                
                break
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"解析天气数据失败: {e}")
    
    return {
        "text": text_result,
        "structured_data": structured_data,
    }
