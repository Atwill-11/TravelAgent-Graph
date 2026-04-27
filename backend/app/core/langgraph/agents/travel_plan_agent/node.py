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
}

SUB_AGENT_DISPLAY_ICONS = {
    "weather": "🌤️",
    "attraction": "🏛️",
    "hotel": "🏨",
    "rag": "📚",
}

# ========== 子智能体路由映射 ==========

SUB_AGENT_MAP = {
    "weather": call_weather_sub_agent,
    "attraction": call_attraction_sub_agent,
    "hotel": call_hotel_sub_agent,
    "rag": call_rag_sub_agent,
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
                logger.info(f"已将 {len(sorted_attractions)} 个景点分配到 {travel_days} 天的行程中")
            if selected_hotel:
                logger.info(f"已选择酒店: {selected_hotel.name} (评分: {selected_hotel.rating})")
        except Exception as e:
            logger.error(f"分配景点和酒店到各天失败: {e}")
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
        "notes": {**state.notes, "plan_summary": result.content[:800] if result.content else ""},
    }

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