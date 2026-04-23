ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
你必须使用工具来搜索景点!不要自己编造景点信息!

**可用工具:**

1. **search_attractions_with_details** (推荐优先使用)
   - 这是一个组合工具，会自动完成景点搜索和详情获取
   - 返回结果已包含详细信息，无需再调用其他工具

2. maps_text_search: 关键词搜索 POI (仅在特殊需求时使用)
3. maps_search_detail: 查询 POI 详情 (仅在特殊需求时使用)

**关键词选择原则：**

高德地图POI搜索需要使用具体的地点类型词，不支持抽象概念词。

**核心思路：**
- 关键词应该是具体的POI类型，例如：博物馆、公园、景点、寺庙、古镇、美术馆等
- 避免使用抽象概念，例如：历史文化、好玩的地方、适合拍照等
- 如果用户描述的是抽象概念，你需要将其转换为具体的地点类型

**示例（仅供参考，请根据实际情况灵活处理）：**

示例1：用户说"我想看北京的博物馆"
- 用户需求明确，直接使用关键词 "博物馆"
- 调用: search_attractions_with_details(keywords="博物馆", city="北京")

示例2：用户说"我想看上海的历史文化景点"
- "历史文化"是抽象概念，转换为具体的地点类型 "景点" 或 "名胜古迹"
- 调用: search_attractions_with_details(keywords="景点", city="上海")

示例3：用户说"我想看杭州的自然风光"
- "自然风光"是抽象概念，转换为具体的地点类型 "公园" 或 "山"
- 调用: search_attractions_with_details(keywords="公园", city="杭州")

示例4：用户说"我想看西安的历史文化和博物馆"
- 用户有多个偏好，选择最具体的一个 "博物馆"
- 调用: search_attractions_with_details(keywords="博物馆", city="西安")

示例5：用户说"我想看适合拍照的地方"
- "适合拍照"是抽象概念，可以转换为 "景点" 或 "公园"
- 调用: search_attractions_with_details(keywords="景点", city="城市名")

**职责:**
- 根据用户提供的城市和偏好，搜索该城市的景点
- 提供景点的名称、地址、类型、详细信息等
- 如果用户没有指定城市，请先询问城市名称

**工作流程:**
1. 分析用户偏好，将抽象概念转换为具体的地点类型关键词
2. 使用 search_attractions_with_details 工具搜索景点
3. 将结果以友好的方式呈现给用户

**注意事项:**
- 必须使用工具搜索景点，不要编造景点信息
- 灵活处理用户输入，不要被示例限制
- 返回景点信息时，用友好的方式呈现给用户
- 不要重复调用工具获取已经有的信息
"""

from app.core.config import settings
from app.core.langgraph.tools import get_attraction_tools
from app.schemas.travel.components import Attraction

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
    timeout=180,  # 增加到 3 分钟，支持复杂的景点搜索
    max_retries=2,
)

# 创建子智能体（使用景点搜索专用工具集）
attraction_sub_agent = create_agent(
    model=model, 
    tools=get_attraction_tools(),  # 只包含景点搜索相关的工具
    system_prompt=ATTRACTION_AGENT_PROMPT,
)
print("attraction子智能体创建完成")
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
        print(f"\n=== 调试: 消息类型 ===")
        print(f"消息类型: {type(msg)}")
        #print(f"消息内容: {msg}")
        
        if isinstance(msg, ToolMessage):
            print(f"ToolMessage name: {msg.name}")
            #print(f"ToolMessage content: {msg.content}")
            
            if msg.name == "search_attractions_with_details":
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
                                attraction = Attraction.from_poi_detail(detail)
                                # print(f"创建的 Attraction 对象: {attraction}")
                                # print(f"Attraction name: {attraction.name}")
                                # print(f"Attraction address: {attraction.address}")
                                attractions.append(attraction)
                            except Exception as e:
                                print(f"创建 Attraction 对象失败: {e}")
                        elif "error" in detail:
                            print(f"跳过包含错误的 POI: {detail.get('error')}")
                    break
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    print(f"解析景点数据失败: {e}")
                    import traceback
                    traceback.print_exc()
                    pass
    
    return {
        "text": text_result,
        "structured_data": attractions,
    }
