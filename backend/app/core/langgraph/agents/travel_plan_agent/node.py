"""智能旅游助手节点函数定义。

该模块定义了旅游规划工作流中的所有节点函数：
- plan_node: 任务规划节点
- execute_sub_agent_node: 子智能体执行节点
- summarize_node: 结果总结节点
- should_continue: 路由判断函数
"""

from typing import Literal
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.langgraph.agents.sub_agents import (
    call_attraction_sub_agent,
    call_hotel_sub_agent,
    call_weather_sub_agent,
)
from app.schemas.agent import (
    TravelPlannerState,
    TaskItem,
    SubAgentResult,
)
from app.schemas.travel import TripPlan
from app.schemas.weather import TravelWeatherData


# ========== Prompt 定义 ==========

PLAN_MODEL_PROMPT = """
你是一个智能旅游规划助手，负责分析用户需求并拆分为具体的子任务。

**可用子智能体:**
- weather: 天气查询专家，可查询指定城市的天气信息
- attraction: 景点搜索专家，可根据城市和偏好搜索景点
- hotel: 酒店推荐专家，可根据城市推荐合适的酒店

**重要说明：**
- 只生成需要调用子智能体的任务（weather、attraction、hotel）
- 不要生成"整合"、"总结"、"制定行程"等类型的任务
- 整合工作由系统自动完成，无需单独规划任务

**任务拆分原则:**
1. 每个任务应该明确、可执行
2. 任务之间应该有合理的依赖顺序
3. 每个任务应该能由对应的子智能体完成
4. 任务数量控制在2-3个（仅包含需要调用子智能体的任务）

**输出格式:**
返回 JSON 格式，包含:
- reasoning: 规划思路
- plan: 任务计划
  - tasks: 任务列表
  - task_types: 每个任务对应的子智能体类型（只能是 weather/attraction/hotel）
"""


SUMMARY_PROMPT = """
你是一个专业的旅游规划总结助手。

**重要说明：**
景点和酒店已经根据评分和距离智能分配完成，你只需要根据分配结果生成友好的文本描述。

**你的核心任务：**
根据已分配的景点和酒店，生成完整、实用的旅游规划文本描述。

**工作流程：**
1. **阅读分配结果**：仔细查看已分配的景点和酒店信息
2. **生成描述**：
   - 为每天生成详细的行程描述
   - 包含景点名称、地址、评分、门票价格等关键信息
   - 提供交通和餐饮建议
   - 添加实用的旅游提示

**注意事项：**
- 必须严格按照分配结果生成描述，不要修改已分配的景点和酒店
- 可以添加行程亮点、注意事项、交通建议等补充信息
- 确保描述生动、实用、易于理解

**输出要求：**
1. 结构清晰，使用标题和列表组织内容
2. 信息完整，包含所有关键信息
3. 实用性强，提供具体建议
4. 语言简洁，避免冗余

**输出格式：**
## 📋 旅游规划概览
[整体概述]

## 🌤️ 天气信息
[天气相关内容，要求从保留子智能体得到的具体数据]

## 🏛️ 景点推荐
[根据分配结果生成详细的景点描述]

## 🏨 住宿建议
[根据分配结果生成酒店描述]

## 💡 温馨提示
[其他建议]
"""


# ========== 模型初始化 ==========

DASHSCOPE_API_KEY = settings.DASHSCOPE_API_KEY
DASHSCOPE_API_BASE = settings.DASHSCOPE_API_BASE

from langchain_qwq import ChatQwen


def get_plan_model():
    """获取规划模型"""
    return ChatQwen(
        model_name="qwen3.5-flash-2026-02-23",
        api_key=DASHSCOPE_API_KEY,
        api_base=DASHSCOPE_API_BASE,
        temperature=0.7,
        max_tokens=1000,
        timeout=180,  # 增加到 3 分钟，支持复杂的旅行计划生成
        max_retries=2,
    )


def get_summary_model():
    """获取总结模型"""
    return ChatQwen(
        model_name="qwen3.5-flash-2026-02-23",
        api_key=DASHSCOPE_API_KEY,
        api_base=DASHSCOPE_API_BASE,
        temperature=0.7,
        max_tokens=1500,
        timeout=180,  # 增加到 3 分钟，支持复杂的总结生成
        max_retries=2,
    )


# ========== Schema 定义 ==========

class TaskPlan(BaseModel):
    """任务规划结构"""
    tasks: list[str] = Field(description="任务列表，按执行顺序排列")
    task_types: list[str] = Field(description="每个任务对应的子智能体类型: weather/attraction/hotel")


class PlanResult(BaseModel):
    """规划结果"""
    reasoning: str = Field(description="规划思路")
    plan: TaskPlan = Field(description="任务计划")


# ========== 子智能体路由映射 ==========

SUB_AGENT_MAP = {
    "weather": call_weather_sub_agent,
    "attraction": call_attraction_sub_agent,
    "hotel": call_hotel_sub_agent,
}


# ========== 节点函数 ==========

def plan_node(state: TravelPlannerState) -> dict:
    """
    任务规划节点。
    分析用户需求，拆分为具体的子任务。
    """
    model = get_plan_model()
    
    trip_request = state.trip_request
    user_message = state.messages[-1].content if state.messages else ""
    
    plan_prompt = ChatPromptTemplate.from_messages([
        ("system", PLAN_MODEL_PROMPT),
        ("human", "用户需求：{user_request}\n\n请分析并拆分为子任务。"),
    ])
    
    chain = plan_prompt | model.with_structured_output(PlanResult)
    result = chain.invoke({"user_request": user_message})
    
    task_items = [
        TaskItem(task=task, type=task_type, status="pending", result=None)
        for task, task_type in zip(result.plan.tasks, result.plan.task_types)
    ]
    
    return {
        "plan": task_items,
        "messages": [AIMessage(content=f"已规划 {len(result.plan.tasks)} 个任务：\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(result.plan.tasks)))],
    }


async def execute_sub_agent_node(state: TravelPlannerState) -> dict:
    """
    执行子智能体节点。
    按顺序执行待处理的子任务。
    """
    plan = state.plan
    sub_agent_results = state.sub_agent_results
    
    # 找到第一个待执行的任务
    current_task_idx = None
    for idx, task_item in enumerate(plan):
        if task_item.status == "pending":
            current_task_idx = idx
            break
    
    if current_task_idx is None:
        return {"current_task": None}
    
    task_item = plan[current_task_idx]
    task_name = task_item.task
    task_type = task_item.type
    
    # 获取对应的子智能体
    sub_agent_func = SUB_AGENT_MAP.get(task_type)
    if not sub_agent_func:
        # 将未知任务类型标记为已完成（跳过）
        plan[current_task_idx].status = "completed"
        plan[current_task_idx].result = f"跳过：'{task_type}' 不是有效的子智能体类型"
        
        print(f"警告：跳过未知任务类型 '{task_type}' - {task_name}")
        
        return {
            "plan": plan,
            "current_task": task_name,
            "messages": [AIMessage(content=f"⚠️ 跳过任务: {task_name} (未知任务类型: {task_type})")],
        }
    
    # 执行子智能体
    try:
        result = await sub_agent_func.ainvoke({"query": task_name})

        if isinstance(result, dict) and "text" in result:
            task_result = result["text"]
            structured_data = result.get("structured_data")
        else:
            task_result = result if isinstance(result, str) else str(result)
            structured_data = None

        # 更新任务状态
        plan[current_task_idx].status = "completed"
        plan[current_task_idx].result = task_result

        sub_agent_results.append(
            SubAgentResult(
                task=task_name,
                type=task_type,
                result=task_result,
                structured_data=structured_data,
            )
        )

        update = {
            "plan": plan,
            "sub_agent_results": sub_agent_results,
            "current_task": task_name,
            "messages": [AIMessage(content=f"✅ 任务完成: {task_name}")],
        }

        if task_type == "weather" and structured_data:
            try:
                weather_data = TravelWeatherData(**structured_data)
                if state.trip_plan:
                    trip_plan = state.trip_plan.model_copy(update={"weather_info": weather_data})
                else:
                    trip_plan = TripPlan(
                        city=state.trip_request.city if state.trip_request else "",
                        start_date=state.trip_request.start_date if state.trip_request else "",
                        end_date=state.trip_request.end_date if state.trip_request else "",
                        days=[],
                        weather_info=weather_data,
                        overall_suggestions="",
                    )
                update["trip_plan"] = trip_plan
            except Exception as e:
                print(f"解析天气结构化数据失败: {e}")

        if task_type == "attraction" and structured_data:
            try:
                from app.schemas.travel.components import Attraction
                if isinstance(structured_data, list):
                    attractions = []
                    for item in structured_data:
                        if isinstance(item, Attraction):
                            attractions.append(item)
                        elif isinstance(item, dict):
                            attractions.append(Attraction(**item))
                    update["attraction_pool"] = state.attraction_pool + attractions
                    print(f"已将 {len(attractions)} 个景点添加到景点池")
            except Exception as e:
                print(f"解析景点结构化数据失败: {e}")
                import traceback
                traceback.print_exc()

        if task_type == "hotel" and structured_data:
            try:
                from app.schemas.travel.components import Hotel
                if isinstance(structured_data, list):
                    hotels = []
                    for item in structured_data:
                        if isinstance(item, Hotel):
                            hotels.append(item)
                        elif isinstance(item, dict):
                            hotels.append(Hotel(**item))
                    update["hotel_pool"] = state.hotel_pool + hotels
                    print(f"已将 {len(hotels)} 个酒店添加到酒店池")
            except Exception as e:
                print(f"解析酒店结构化数据失败: {e}")
                import traceback
                traceback.print_exc()

        return update
    except Exception as e:
        plan[current_task_idx].status = "failed"
        plan[current_task_idx].result = f"执行失败: {str(e)}"

        return {
            "plan": plan,
            "current_task": task_name,
            "messages": [AIMessage(content=f"❌ 任务失败: {task_name} - {str(e)}")],
        }


def summarize_node(state: TravelPlannerState) -> dict:
    """
    总结节点。
    汇总所有子任务结果，生成最终旅游规划。
    """
    from app.schemas.travel import TripPlan, DayPlan, Budget
    from datetime import datetime, timedelta
    import math
    
    model = get_summary_model()
    
    sub_agent_results = state.sub_agent_results
    trip_request = state.trip_request
    user_request = state.messages[0].content if state.messages else ""
    attraction_pool = state.attraction_pool
    hotel_pool = state.hotel_pool
    
    # ========== 步骤1：先完成景点和酒店的分配 ==========
    days = []
    selected_hotel = None
    sorted_attractions = []
    
    if trip_request:
        try:
            start_date = datetime.strptime(trip_request.start_date, "%Y-%m-%d")
            travel_days = trip_request.travel_days
            
            # 按评分排序景点（从高到低）
            sorted_attractions = sorted(
                attraction_pool,
                key=lambda x: x.rating if x.rating else 0,
                reverse=True
            )
            
            # 计算每天的景点数量（2-3个）
            total_attractions = len(sorted_attractions)
            if total_attractions > 0:
                attractions_per_day = min(3, max(2, math.ceil(total_attractions / travel_days)))
            else:
                attractions_per_day = 0
            
            # 选择评分最高的酒店
            if hotel_pool:
                sorted_hotels = sorted(
                    hotel_pool,
                    key=lambda x: x.rating if x.rating else 0,
                    reverse=True
                )
                selected_hotel = sorted_hotels[0] if sorted_hotels else None
            
            # 为每天分配景点
            for day_idx in range(travel_days):
                start_idx = day_idx * attractions_per_day
                end_idx = min(start_idx + attractions_per_day, len(sorted_attractions))
                day_attractions = sorted_attractions[start_idx:end_idx]
                
                date_str = (start_date + timedelta(days=day_idx)).strftime("%Y-%m-%d")
                
                # 生成当天行程描述
                if day_attractions:
                    attraction_names = ", ".join([a.name for a in day_attractions])
                    description = f"第{day_idx + 1}天：游览{attraction_names}"
                else:
                    description = f"第{day_idx + 1}天：自由活动"
                
                day_plan = DayPlan(
                    date=date_str,
                    day_index=day_idx,
                    description=description,
                    transportation=trip_request.transportation,
                    accommodation=trip_request.accommodation,
                    hotel=selected_hotel,
                    attractions=day_attractions,
                    meals=[],
                )
                days.append(day_plan)
            
            if sorted_attractions:
                print(f"已将 {len(sorted_attractions)} 个景点分配到 {travel_days} 天的行程中")
            if selected_hotel:
                print(f"已选择酒店: {selected_hotel.name} (评分: {selected_hotel.rating})")
        except Exception as e:
            print(f"分配景点和酒店到各天失败: {e}")
            import traceback
            traceback.print_exc()
    
    # ========== 步骤2：构建分配结果的文本描述 ==========
    allocation_text = ""
    if days:
        allocation_text = "\n\n**已分配的行程安排：**\n\n"
        for day in days:
            allocation_text += f"**第{day.day_index + 1}天 ({day.date})：**\n"
            if day.attractions:
                for i, attraction in enumerate(day.attractions, 1):
                    allocation_text += f"  {i}. {attraction.name}"
                    if attraction.rating:
                        allocation_text += f" (评分: {attraction.rating})"
                    if attraction.ticket_price:
                        allocation_text += f" - 门票: {attraction.ticket_price}元"
                    allocation_text += "\n"
            else:
                allocation_text += "  暂无景点安排\n"
            allocation_text += "\n"
        
        if selected_hotel:
            allocation_text += f"**推荐酒店：**{selected_hotel.name}"
            if selected_hotel.rating:
                allocation_text += f" (评分: {selected_hotel.rating})"
            if selected_hotel.address:
                allocation_text += f"\n地址：{selected_hotel.address}"
            allocation_text += "\n"
    
    # ========== 步骤3：将分配结果传递给 AI 生成文本 ==========
    results_text = "\n\n".join([
        f"### {r.task}\n{r.result}"
        for r in sub_agent_results
    ])
    
    summary_prompt = ChatPromptTemplate.from_messages([
        ("system", SUMMARY_PROMPT),
        ("human", """用户需求：{user_request}

子任务执行结果：
{results}

{allocation}

请根据以上分配结果，生成完整的旅游规划文本描述。"""),
    ])
    
    chain = summary_prompt | model
    result = chain.invoke({
        "user_request": user_request,
        "results": results_text,
        "allocation": allocation_text,
    })

    # ========== 步骤4：构建最终的 TripPlan ==========
    if state.trip_plan:
        trip_plan = state.trip_plan.model_copy(update={
            "days": days,
            "overall_suggestions": result.content
        })
    else:
        trip_plan = TripPlan(
            city=trip_request.city if trip_request else "",
            start_date=trip_request.start_date if trip_request else "",
            end_date=trip_request.end_date if trip_request else "",
            days=days,
            weather_info=None,
            overall_suggestions=result.content,
            budget=None,
        )

    return {
        "trip_plan": trip_plan,
        "messages": [AIMessage(content=result.content)],
    }


# ========== 路由函数 ==========

def should_continue(state: TravelPlannerState) -> Literal["execute", "summarize"]:
    """判断是否还有待执行的任务"""
    for task_item in state.plan:
        if task_item.status == "pending":
            return "execute"
    return "summarize"