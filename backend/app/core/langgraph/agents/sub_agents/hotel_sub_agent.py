HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
你必须使用工具来搜索酒店!不要自己编造酒店信息!

**可用工具:**

1. **search_hotels_with_details** (推荐优先使用)
   - 这是一个组合工具，会自动完成酒店搜索和详情获取
   - 返回结果已包含详细信息，无需再调用其他工具

2. maps_text_search: 关键词搜索 POI (仅在特殊需求时使用)
3. maps_around_search: 周边搜索 (仅在特殊需求时使用)
4. maps_search_detail: 查询 POI 详情 (仅在特殊需求时使用)

**关键词选择原则：**
搜索酒店时，关键词通常使用"酒店"、"宾馆"、"住宿"等。

**示例（仅供参考，请根据实际情况灵活处理）：**

示例1：用户说"推荐北京的酒店"
- 用户需求明确，直接使用关键词 "酒店"
- 调用: search_hotels_with_details(keywords="酒店", city="北京")

示例2：用户说"推荐上海的经济型酒店"
- 用户需求明确，使用关键词 "经济型酒店"
- 调用: search_hotels_with_details(keywords="经济型酒店", city="上海")

示例3：用户说"推荐景点附近的酒店"
- 需要结合景点位置，使用 maps_around_search 工具
- 调用: maps_around_search(location="景点坐标", keywords="酒店")

**职责:**
- 根据用户提供的城市名称，搜索该城市的酒店
- 根据景点位置推荐附近合适的酒店
- 提供酒店的名称、地址、价格等关键信息
- 如果用户没有指定城市，请先询问城市名称

**工作流程:**
1. 分析用户需求，确定搜索关键词和城市
2. 使用 search_hotels_with_details 工具搜索酒店
3. 将结果以友好的方式呈现给用户

**注意事项:**
- 必须使用工具搜索酒店，不要编造酒店信息
- 灵活处理用户输入，不要被示例限制
- 返回酒店信息时，用友好的方式呈现给用户
- 不要重复调用工具获取已经有的信息
"""

from app.core.config import settings
from app.core.langgraph.tools import get_hotel_tools
from app.schemas.travel.components import Hotel

DASHSCOPE_API_KEY = settings.DASHSCOPE_API_KEY
DASHSCOPE_API_BASE = settings.DASHSCOPE_API_BASE

from langchain_qwq import ChatQwen  
from langchain.agents import create_agent  
from langchain.tools import tool
from langchain_core.messages import ToolMessage

# 初始化语言模型
model = ChatQwen(
    model_name="qwen3.5-flash-2026-02-23",
    api_key=DASHSCOPE_API_KEY,
    api_base=DASHSCOPE_API_BASE,
    temperature=0.7,
    max_tokens=1000,
    timeout=60,
    max_retries=2,
)

# 创建子智能体（使用酒店推荐专用工具集）
hotel_sub_agent = create_agent(
    model=model, 
    tools=get_hotel_tools(),  # 只包含酒店推荐相关的工具
    system_prompt=HOTEL_AGENT_PROMPT,
)
print("hotel子智能体创建完成")

# 将子智能体封装为一个工具，供主智能体调用
@tool("hotel_sub_agent", description="酒店子智能体，专门用于推荐酒店信息的任务")
async def call_hotel_sub_agent(query: str) -> dict:
    """调用hotel子智能体处理查询，返回文本结果和结构化酒店数据。
    
    从子智能体的返回消息中提取 ToolMessage，获取 search_hotels_with_details 工具的原始结构化输出，
    并将其转换为 Hotel 对象列表。
    """
    result = await hotel_sub_agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]}
    )
    
    messages = result.get("messages", [])
    text_result = messages[-1].content if messages else ""
    
    hotels = []
    for msg in messages:
        print(f"\n=== 调试: 消息类型 ===")
        print(f"消息类型: {type(msg)}")
        #print(f"消息内容: {msg}")
        
        if isinstance(msg, ToolMessage):
            print(f"ToolMessage name: {msg.name}")
            print(f"ToolMessage content 类型: {type(msg.content)}")
            #print(f"ToolMessage content: {msg.content}")
            
            if msg.name == "search_hotels_with_details":
                try:
                    import json
                    content = msg.content
                    if isinstance(content, str):
                        data = json.loads(content)
                    elif isinstance(content, dict):
                        data = content
                    else:
                        print(f"未知的 content 类型: {type(content)}")
                        continue
                    
                    # print(f"\n=== 解析后的数据 ===")
                    # print(f"data keys: {data.keys()}")
                    
                    pois = data.get("pois", [])
                    print(f"pois 数量: {len(pois)}")
                    
                    for i, poi in enumerate(pois):
                        detail = poi.get("detail", {})
                        # print(f"\n--- POI {i+1} ---")
                        # print(f"POI 数据: {poi}")
                        # print(f"detail 数据: {detail}")
                        
                        if detail and "error" not in detail:
                            try:
                                hotel = Hotel.from_poi_detail(detail)
                                # print(f"创建的 Hotel 对象: {hotel}")
                                # print(f"Hotel name: {hotel.name}")
                                # print(f"Hotel address: {hotel.address}")
                                hotels.append(hotel)
                            except Exception as e:
                                print(f"创建 Hotel 对象失败: {e}")
                        elif "error" in detail:
                            print(f"跳过包含错误的 POI: {detail.get('error')}")
                    break
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    print(f"解析酒店数据失败: {e}")
                    import traceback
                    traceback.print_exc()
                    pass
    
    return {
        "text": text_result,
        "structured_data": hotels,
    }
