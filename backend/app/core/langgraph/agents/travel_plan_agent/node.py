"""智能旅游助手节点函数定义。

该模块定义了旅游规划工作流中的所有节点函数：
- plan_node: 任务规划节点
- execute_sub_agent_node: 子智能体执行节点
- summarize_node: 结果总结节点
- user_review_node: 用户审阅节点（支持多轮对话）
- should_continue: 路由判断函数
- route_after_review: 审阅后路由判断函数
"""

import math
from datetime import datetime, timedelta
from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import interrupt
from langchain_qwq import ChatQwen

from app.core.config import settings
from app.core.logging import logger
from app.core.langgraph.agents.sub_agents import (
    call_attraction_sub_agent,
    call_hotel_sub_agent,
    call_weather_sub_agent,
    call_rag_sub_agent,
    call_selection_sub_agent,
)
from app.schemas import (
    TravelPlannerState,
    TaskItem,
    SubAgentResult,
    TravelWeatherData,
    TripPlan,
    PlanResult,
    DayPlan
)

from app.core.prompts import PLAN_MODEL_PROMPT, SUMMARY_PROMPT

def get_plan_model():
    """获取规划模型"""
    return ChatQwen(
        model_name=settings.DASHSCOPE_PLAN_LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        api_base=settings.DASHSCOPE_API_BASE,
        temperature=0.7,
        max_tokens=1000,
        timeout=180,  # 增加到 3 分钟，支持复杂的旅行计划生成
        max_retries=2,
    )


def get_summary_model():
    """获取总结模型"""
    return ChatQwen(
        model_name=settings.DASHSCOPE_SUMMARY_LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        api_base=settings.DASHSCOPE_API_BASE,
        temperature=0.7,
        max_tokens=1500,
        timeout=180,  # 增加到 3 分钟，支持复杂的总结生成
        max_retries=2,
    )

NODE_DISPLAY_NAMES = {
    "plan": "任务规划",
    "execute": "执行子任务",
    "summarize": "生成旅行计划",
    "user_review": "用户审阅",
}

NODE_DISPLAY_ICONS = {
    "plan": "🧠",
    "execute": "⚙️",
    "summarize": "📋",
    "user_review": "👀",
}

SUB_AGENT_DISPLAY_NAMES = {
    "weather": "天气查询",
    "attraction": "景点搜索",
    "hotel": "酒店推荐",
    "rag": "知识库检索",
    "selection": "景点酒店分配",
}

SUB_AGENT_DISPLAY_ICONS = {
    "weather": "🌤️",
    "attraction": "🏛️",
    "hotel": "🏨",
    "rag": "📚",
    "selection": "🎯",
}

# ========== 子智能体路由映射 ==========

SUB_AGENT_MAP = {
    "weather": call_weather_sub_agent,
    "attraction": call_attraction_sub_agent,
    "hotel": call_hotel_sub_agent,
    "rag": call_rag_sub_agent,
    "selection": call_selection_sub_agent,
}

# ========== 节点函数 ==========

def plan_node(state: TravelPlannerState) -> dict:
    """
    任务规划节点。
    分析用户需求，拆分为具体的子任务。
    支持首次规划和多轮对话修改模式。
    """
    model = get_plan_model()
    
    is_modification = state.notes.get("user_decision") == "modify" and bool(state.user_feedback)
    
    if is_modification:
        user_feedback = state.user_feedback or ""
        plan_summary = state.notes.get("plan_summary", "")
        current_round = state.notes.get("round", 0)
        
        trip_info = ""
        if state.trip_request:
            trip_info = (
                f"当前旅行信息：\n"
                f"- 目的地：{state.trip_request.city}\n"
                f"- 日期：{state.trip_request.start_date} 至 {state.trip_request.end_date}\n"
                f"- 天数：{state.trip_request.travel_days}天\n"
                f"- 交通：{state.trip_request.transportation}\n"
                f"- 住宿偏好：{state.trip_request.accommodation}\n"
                f"- 偏好：{', '.join(state.trip_request.preferences) if state.trip_request.preferences else '无'}\n"
            )
        
        completed_tasks = ""
        if state.sub_agent_results:
            completed_tasks = "已完成的子任务：\n"
            for r in state.sub_agent_results:
                completed_tasks += f"- [{r.type}] {r.task}\n"
        
        plan_prompt = ChatPromptTemplate.from_messages([
            ("system", PLAN_MODEL_PROMPT),
            ("human", """这是对已有旅行计划的修改请求，请根据修改意见生成需要重新执行的完整任务。

{trip_info}

{completed_tasks}

当前旅行计划摘要：
{plan_summary}

用户修改意见：{user_feedback}

请分析用户修改意见，仅生成因修改而需要重新执行的完整任务。"""),
        ])
        
        chain = plan_prompt | model.with_structured_output(PlanResult)
        result = chain.invoke({
            "trip_info": trip_info,
            "completed_tasks": completed_tasks,
            "plan_summary": plan_summary,
            "user_feedback": user_feedback,
        })
        
        task_items = [
            TaskItem(task=task, type=task_type, status="pending", result=None)
            for task, task_type in zip(result.plan.tasks, result.plan.task_types)
        ]
        
        update = {
            "plan": state.plan + task_items,
            "messages": [AIMessage(content=f"根据修改意见，新增 {len(task_items)} 个任务：\n" + "\n".join(f"- {t.task}" for t in task_items))],
            "notes": {**state.notes, "round": current_round + 1},
            "user_feedback": None,
        }
        
        if result.updated_end_date and state.trip_request:
            updated_request = state.trip_request.model_copy(update={
                "end_date": result.updated_end_date,
            })
            if result.updated_travel_days:
                updated_request = updated_request.model_copy(update={
                    "travel_days": result.updated_travel_days,
                })
            update["trip_request"] = updated_request
        elif result.updated_travel_days and state.trip_request:
            updated_request = state.trip_request.model_copy(update={
                "travel_days": result.updated_travel_days,
            })
            update["trip_request"] = updated_request
        
        return update
    else:
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
        
        logger.warning(f"警告：跳过未知任务类型 '{task_type}' - {task_name}")
        
        return {
            "plan": plan,
            "current_task": task_name,
            "messages": [AIMessage(content=f"⚠️ 跳过任务: {task_name} (未知任务类型: {task_type})")],
        }
    
    # 执行子智能体
    try:
        if task_type == "selection":
            query = _build_selection_query(
                state=state,
                task_description=task_name,
            )
        else:
            query = task_name
        
        result = await sub_agent_func.ainvoke({"query": query})

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
                logger.error(f"解析天气结构化数据失败: {e}")

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
                    logger.info(f"已将 {len(attractions)} 个景点添加到景点池")
            except Exception as e:
                logger.error(f"解析景点结构化数据失败: {e}")
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
                    logger.info(f"已将 {len(hotels)} 个酒店添加到酒店池")
            except Exception as e:
                logger.error(f"解析酒店结构化数据失败: {e}")
                import traceback
                traceback.print_exc()

        if task_type == "selection" and structured_data:
            try:
                from app.schemas.travel.selection import DayPlanSelection
                if isinstance(structured_data, DayPlanSelection):
                    selection_result = structured_data
                elif isinstance(structured_data, dict):
                    selection_result = DayPlanSelection(**structured_data)
                else:
                    raise ValueError(f"未知的 structured_data 类型: {type(structured_data)}")
                
                trip_request = state.trip_request
                if trip_request:
                    start_date = datetime.strptime(trip_request.start_date, "%Y-%m-%d")
                    travel_days = trip_request.travel_days
                    weather_info = state.trip_plan.weather_info if state.trip_plan else None
                    
                    trip_plan = _build_trip_plan_from_selection(
                        selection_result=selection_result,
                        attraction_pool=state.attraction_pool,
                        hotel_pool=state.hotel_pool,
                        trip_request=trip_request,
                        start_date=start_date,
                        travel_days=travel_days,
                        weather_info=weather_info,
                    )
                    update["trip_plan"] = trip_plan
                    logger.info("已根据选择结果更新旅行计划")
            except Exception as e:
                logger.error(f"解析选择结果失败: {e}")
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
    生成最终旅游规划的文本描述。
    如果 trip_plan 已经由 selection 任务创建，则只生成文本描述；
    否则，先进行景点和酒店选择，再生成文本描述。
    """
    model = get_summary_model()
    
    sub_agent_results = state.sub_agent_results
    trip_request = state.trip_request
    user_request = state.messages[0].content if state.messages else ""
    
    if not trip_request:
        return {
            "trip_plan": None,
            "messages": [AIMessage(content="缺少旅行请求信息")],
        }
    
    trip_plan = state.trip_plan
    if not trip_plan or not trip_plan.days:
        trip_plan = _create_trip_plan_from_selection(state, model)
    
    if not trip_plan:
        return {
            "trip_plan": None,
            "messages": [AIMessage(content="无法生成旅行计划")],
        }
    
    detailed_description = _generate_detailed_description(
        trip_plan=trip_plan,
        sub_agent_results=sub_agent_results,
        user_request=user_request,
        model=model,
    )
    
    trip_plan.overall_suggestions = detailed_description
    
    return {
        "trip_plan": trip_plan,
        "messages": [AIMessage(content=detailed_description)],
        "notes": {
            **state.notes,
            "plan_summary": detailed_description[:800] if detailed_description else "",
        },
    }


def _create_trip_plan_from_selection(state: TravelPlannerState, model) -> TripPlan:
    """从景点池和酒店池创建旅行计划
    
    Args:
        state: 当前状态
        model: LLM 模型
        
    Returns:
        生成的旅行计划
    """
    trip_request = state.trip_request
    attraction_pool = state.attraction_pool
    hotel_pool = state.hotel_pool
    user_feedback = state.user_feedback
    is_modification = state.notes.get("user_decision") == "modify"
    weather_info = state.trip_plan.weather_info if state.trip_plan else None
    
    start_date = datetime.strptime(trip_request.start_date, "%Y-%m-%d")
    travel_days = trip_request.travel_days
    
    attractions_info = _format_attractions_for_selection(attraction_pool)
    hotels_info = _format_hotels_for_selection(hotel_pool)
    
    current_plan_info = ""
    if is_modification and state.trip_plan:
        current_plan_info = _format_current_plan(state.trip_plan)
    
    selection_prompt = _build_selection_prompt(
        user_request=state.messages[0].content if state.messages else "",
        user_feedback=user_feedback,
        is_modification=is_modification,
        attractions_info=attractions_info,
        hotels_info=hotels_info,
        current_plan_info=current_plan_info,
        travel_days=travel_days,
        start_date=start_date,
        trip_request=trip_request,
    )
    
    from app.schemas.travel.selection import DayPlanSelection
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SELECTION_PROMPT),
        ("human", "{selection_prompt}"),
    ])
    
    chain = prompt | model.with_structured_output(DayPlanSelection)
    selection_result = chain.invoke({"selection_prompt": selection_prompt})
    
    trip_plan = _build_trip_plan_from_selection(
        selection_result=selection_result,
        attraction_pool=attraction_pool,
        hotel_pool=hotel_pool,
        trip_request=trip_request,
        start_date=start_date,
        travel_days=travel_days,
        weather_info=weather_info,
    )
    
    return trip_plan

def should_continue(state: TravelPlannerState) -> Literal["execute", "summarize"]:
    """判断是否还有待执行的任务"""
    for task_item in state.plan:
        if task_item.status == "pending":
            return "execute"
    return "summarize"


def user_review_node(state: TravelPlannerState) -> dict:
    """
    用户审阅节点。
    使用interrupt暂停图执行，等待用户审阅旅行计划并提供反馈。
    当图通过Command(resume=...)恢复时，interrupt返回用户的反馈信息。
    """
    trip_plan_data = None
    if state.trip_plan:
        trip_plan_data = state.trip_plan.model_dump()

    user_response = interrupt({
        "message": "请审阅旅行计划，您可以选择完成规划或提出修改意见",
        "trip_plan": trip_plan_data,
    })

    if user_response.get("action") == "complete":
        return {
            "notes": {**state.notes, "user_decision": "complete"},
            "messages": [AIMessage(content="用户确认完成旅行规划")],
        }
    else:
        feedback = user_response.get("feedback", "")
        return {
            "notes": {**state.notes, "user_decision": "modify"},
            "user_feedback": feedback,
            "messages": [HumanMessage(content=f"用户修改意见：{feedback}")],
        }


def route_after_review(state: TravelPlannerState) -> Literal["plan", "__end__"]:
    """审阅后路由判断：用户选择完成则结束，选择修改则回到规划节点"""
    if state.notes.get("user_decision") == "complete":
        return "__end__"
    return "plan"


def _format_attractions_for_selection(attractions: list) -> str:
    """格式化景点信息供 LLM 选择"""
    if not attractions:
        return "暂无可用景点"
    
    info_lines = ["可选景点列表：\n"]
    for i, attr in enumerate(attractions, 1):
        info_lines.append(
            f"{i}. {attr.name}\n"
            f"   - 评分: {attr.rating or '暂无'}\n"
            f"   - 门票: {attr.ticket_price}元\n"
            f"   - 类型: {attr.type or '未知'}\n"
            f"   - 地址: {attr.address}\n"
            f"   - 开放时间: {attr.open_time or '未知'}\n"
            f"   - 描述: {attr.description or '暂无'}\n"
        )
    
    return "\n".join(info_lines)


def _format_hotels_for_selection(hotels: list) -> str:
    """格式化酒店信息供 LLM 选择"""
    if not hotels:
        return "暂无可用酒店"
    
    info_lines = ["可选酒店列表：\n"]
    for i, hotel in enumerate(hotels, 1):
        info_lines.append(
            f"{i}. {hotel.name}\n"
            f"   - 评分: {hotel.rating or '暂无'}\n"
            f"   - 价格: {hotel.lowest_price or '未知'}元/晚\n"
            f"   - 类型: {hotel.hotel_type or '未知'}\n"
            f"   - 商圈: {hotel.business_area or '未知'}\n"
            f"   - 地址: {hotel.address}\n"
        )
    
    return "\n".join(info_lines)


def _format_current_plan(trip_plan) -> str:
    """格式化当前行程供修改参考"""
    info_lines = ["当前行程安排：\n"]
    
    for day in trip_plan.days:
        info_lines.append(f"第{day.day_index + 1}天 ({day.date})：")
        if day.attractions:
            for attr in day.attractions:
                info_lines.append(f"  - {attr.name}")
        if day.hotel:
            info_lines.append(f"  住宿: {day.hotel.name}")
        info_lines.append("")
    
    return "\n".join(info_lines)


def _build_selection_prompt(
    user_request: str,
    user_feedback: str,
    is_modification: bool,
    attractions_info: str,
    hotels_info: str,
    current_plan_info: str,
    travel_days: int,
    start_date,
    trip_request,
) -> str:
    """构建景点/酒店选择的 prompt"""
    
    prompt_parts = [f"用户原始需求：\n{user_request}\n"]
    
    if is_modification and user_feedback:
        prompt_parts.append(f"\n用户修改意见：\n{user_feedback}\n")
        prompt_parts.append(f"\n{current_plan_info}\n")
        prompt_parts.append("\n请根据用户修改意见，调整景点和酒店的选择。\n")
    
    prompt_parts.append(f"\n行程天数：{travel_days}天")
    prompt_parts.append(f"出发日期：{start_date.strftime('%Y-%m-%d')}")
    prompt_parts.append(f"交通方式：{trip_request.transportation}")
    prompt_parts.append(f"住宿偏好：{trip_request.accommodation}")
    
    if trip_request.preferences:
        prompt_parts.append(f"旅行偏好：{', '.join(trip_request.preferences)}")
    
    prompt_parts.append(f"\n{attractions_info}\n")
    prompt_parts.append(f"\n{hotels_info}\n")
    
    prompt_parts.append("\n请根据以上信息，为每天选择合适的景点和酒店。")
    prompt_parts.append("选择时请考虑：")
    prompt_parts.append("1. 用户的需求和偏好")
    if is_modification:
        prompt_parts.append("2. 用户的修改意见（如果有）")
    prompt_parts.append("3. 景点的评分、类型、门票价格")
    prompt_parts.append("4. 行程的合理性（每天2-3个景点）")
    prompt_parts.append("5. 酒店的位置、价格、评分")
    
    return "\n".join(prompt_parts)


def _build_trip_plan_from_selection(
    selection_result,
    attraction_pool: list,
    hotel_pool: list,
    trip_request,
    start_date,
    travel_days: int,
    weather_info: dict,
):
    """根据 LLM 的选择结果构建 TripPlan"""
    
    days = []
    
    attraction_map = {attr.name: attr for attr in attraction_pool}
    hotel_map = {hotel.name: hotel for hotel in hotel_pool}
    
    for day_selection in selection_result.days:
        selected_attractions = []
        for attr_name in day_selection.selected_attraction_names:
            if attr_name in attraction_map:
                selected_attractions.append(attraction_map[attr_name])
        
        date_str = (start_date + timedelta(days=day_selection.day_index)).strftime("%Y-%m-%d")
        
        description = f"第{day_selection.day_index + 1}天"
        if selected_attractions:
            description += f"：游览{', '.join([a.name for a in selected_attractions])}"
        
        selected_hotel = None
        if selection_result.hotel and selection_result.hotel.selected_hotel_name:
            hotel_name = selection_result.hotel.selected_hotel_name
            if hotel_name in hotel_map:
                selected_hotel = hotel_map[hotel_name]
        
        day_plan = DayPlan(
            date=date_str,
            day_index=day_selection.day_index,
            description=description,
            transportation=trip_request.transportation,
            accommodation=trip_request.accommodation,
            hotel=selected_hotel,
            attractions=selected_attractions,
            meals=[],
        )
        days.append(day_plan)
    
    trip_plan = TripPlan(
        city=trip_request.city,
        start_date=trip_request.start_date,
        end_date=trip_request.end_date,
        days=days,
        weather_info=weather_info,
        overall_suggestions=selection_result.overall_suggestions,
        budget=None,
    )
    
    return trip_plan


SELECTION_PROMPT = """你是一个专业的旅游规划师，负责根据用户需求选择合适的景点和酒店。

你的任务：
1. 分析用户的原始需求和偏好
2. 如果有用户修改意见，理解用户的意图（例如："换一个景点"、"不喜欢这个酒店"）
3. 从可选景点和酒店中，选择最合适的组合
4. 为每天分配2-3个景点，确保行程合理
5. 选择一个合适的酒店（如果需要住宿）

选择原则：
- 优先满足用户的明确需求
- 考虑景点的评分、类型、门票价格
- 考虑酒店的位置、价格、评分
- 确保行程的合理性（避免过于拥挤或松散）
- 如果用户表达不满，避免选择用户不满意的景点/酒店

输出格式：
- days: 每天的景点选择（包含日期、景点名称列表、选择理由）
- hotel: 酒店选择（包含酒店名称、选择理由）
- overall_suggestions: 整体建议和说明

请根据用户需求，做出合理的选择。"""


def _generate_detailed_description(
    trip_plan,
    sub_agent_results: list,
    user_request: str,
    model,
) -> str:
    """使用 SUMMARY_PROMPT 生成详细的旅游规划文本
    
    Args:
        trip_plan: 生成的旅行计划
        sub_agent_results: 子智能体执行结果
        user_request: 用户原始请求
        model: LLM 模型实例
        
    Returns:
        详细的旅游规划文本
    """
    from app.core.prompts import SUMMARY_PROMPT
    
    allocation_text = _format_trip_plan_for_summary(trip_plan)
    
    weather_text = ""
    for result in sub_agent_results:
        if result.type == "weather":
            weather_text = f"\n### 天气查询结果\n{result.result}\n"
            break
    
    results_text = "\n\n".join([
        f"### {r.task}\n{r.result}"
        for r in sub_agent_results
        if r.type != "weather"
    ])
    
    summary_prompt = ChatPromptTemplate.from_messages([
        ("system", SUMMARY_PROMPT),
        ("human", """用户需求：{user_request}

子任务执行结果：
{results}

{weather}

已分配的行程安排：
{allocation}

请根据以上分配结果，生成完整的旅游规划文本描述。"""),
    ])
    
    chain = summary_prompt | model
    result = chain.invoke({
        "user_request": user_request,
        "results": results_text,
        "weather": weather_text,
        "allocation": allocation_text,
    })
    
    return result.content


def _format_trip_plan_for_summary(trip_plan) -> str:
    """格式化 TripPlan 供 SUMMARY_PROMPT 使用
    
    Args:
        trip_plan: 旅行计划
        
    Returns:
        格式化的行程文本
    """
    if not trip_plan or not trip_plan.days:
        return "暂无行程安排"
    
    info_lines = ["**已分配的行程安排：**\n"]
    
    for day in trip_plan.days:
        info_lines.append(f"**第{day.day_index + 1}天 ({day.date})：**")
        if day.attractions:
            for i, attraction in enumerate(day.attractions, 1):
                info_lines.append(f"  {i}. {attraction.name}")
                if attraction.rating:
                    info_lines.append(f"     - 评分: {attraction.rating}")
                if attraction.ticket_price:
                    info_lines.append(f"     - 门票: {attraction.ticket_price}元")
                if attraction.address:
                    info_lines.append(f"     - 地址: {attraction.address}")
                if attraction.open_time:
                    info_lines.append(f"     - 开放时间: {attraction.open_time}")
        else:
            info_lines.append("  暂无景点安排")
        info_lines.append("")
    
    if trip_plan.days and trip_plan.days[0].hotel:
        hotel = trip_plan.days[0].hotel
        info_lines.append(f"**推荐酒店：**{hotel.name}")
        if hotel.rating:
            info_lines.append(f"  - 评分: {hotel.rating}")
        if hotel.lowest_price:
            info_lines.append(f"  - 价格: {hotel.lowest_price}元/晚")
        if hotel.address:
            info_lines.append(f"  - 地址: {hotel.address}")
        info_lines.append("")
    
    return "\n".join(info_lines)


def _build_selection_query(state, task_description: str) -> str:
    """构建 selection 任务的查询文本
    
    Args:
        state: 当前状态
        task_description: 任务描述
        
    Returns:
        完整的查询文本
    """
    trip_request = state.trip_request
    user_request = state.messages[0].content if state.messages else ""
    user_feedback = state.user_feedback
    attraction_pool = state.attraction_pool
    hotel_pool = state.hotel_pool
    is_modification = state.notes.get("user_decision") == "modify"
    
    query_parts = []
    
    query_parts.append(f"**用户原始需求：**{user_request}")
    
    if trip_request:
        query_parts.append(f"**目的地：**{trip_request.city}")
        query_parts.append(f"**旅行日期：**{trip_request.start_date} 至 {trip_request.end_date}")
        query_parts.append(f"**旅行天数：**{trip_request.travel_days}天")
    
    if is_modification and user_feedback:
        query_parts.append(f"**用户修改意见：**{user_feedback}")
    
    if state.trip_plan and is_modification:
        current_plan_info = _format_current_plan(state.trip_plan)
        query_parts.append(f"**当前行程安排：**\n{current_plan_info}")
    
    if attraction_pool:
        attractions_info = _format_attractions_for_selection(attraction_pool)
        query_parts.append(f"**可选景点池：**\n{attractions_info}")
    else:
        query_parts.append("**可选景点池：**暂无景点")
    
    if hotel_pool:
        hotels_info = _format_hotels_for_selection(hotel_pool)
        query_parts.append(f"**可选酒店池：**\n{hotels_info}")
    else:
        query_parts.append("**可选酒店池：**暂无酒店")
    
    query_parts.append(f"**任务描述：**{task_description}")
    
    return "\n\n".join(query_parts)