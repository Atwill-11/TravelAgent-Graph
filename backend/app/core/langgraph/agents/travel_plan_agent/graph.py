"""智能旅游助手主规划智能体。

该模块实现了一个基于 LangGraph 的旅游规划工作流，包括：
1. 任务规划：分析用户需求，拆分为子任务
2. 子智能体调用：委派任务给专门的子智能体执行
3. 结果总结：汇总所有子任务结果，生成最终旅游规划
4. 用户审阅：支持多轮对话，用户可修改旅行计划
5. 长期记忆：存储和检索历史规划请求

资源管理：
  所有资源（连接池、检查点器、记忆管理器等）由 ResourceManager 统一管理，
  通过 get_resource_manager() 获取。不再使用模块级全局变量管理资源生命周期。
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.types import Command

from app.schemas import (
    TravelPlannerState,
    TravelContext,
    TravelPlannerOutput,
    TripRequest, 
    TripPlan
)

from .node import (
    plan_node,
    execute_sub_agent_node,
    summarize_node,
    user_review_node,
    should_continue,
    route_after_review,
    NODE_DISPLAY_NAMES,
)

from langfuse.langchain import CallbackHandler
from langfuse import propagate_attributes
from app.core.config import settings
from app.core.logging import logger
from app.services.resource_manager import get_resource_manager

_compiled_graph = None


def _get_langfuse_handler() -> CallbackHandler:
    """获取Langfuse回调处理器。

    优先从ResourceManager获取共享实例，如果不可用则创建新实例。
    """
    try:
        rm = get_resource_manager()
        if rm.langfuse_handler:
            return rm.langfuse_handler
    except RuntimeError:
        pass
    return CallbackHandler()


def _get_memory_manager():
    """获取旅游记忆管理器实例（从ResourceManager获取）。"""
    try:
        rm = get_resource_manager()
        return rm.memory_manager
    except RuntimeError:
        logger.warning("ResourceManager未初始化，无法获取记忆管理器")
        return None


def _get_checkpointer():
    """获取检查点器实例（从ResourceManager获取）。"""
    try:
        rm = get_resource_manager()
        return rm.checkpointer
    except RuntimeError:
        logger.warning("ResourceManager未初始化，无法获取检查点器")
        return None


async def _get_compiled_graph():
    """获取或创建带检查点器的编译图实例。"""
    global _compiled_graph
    
    if _compiled_graph is None:
        checkpointer = _get_checkpointer()
        _compiled_graph = build_travel_planner_graph(checkpointer=checkpointer)
        logger.info("旅游规划编译图初始化成功（带检查点器）")
    
    return _compiled_graph


def _invalidate_compiled_graph():
    """使编译图缓存失效（在资源清理时调用）。"""
    global _compiled_graph
    _compiled_graph = None

def build_travel_planner_graph(checkpointer=None):
    """构建旅游规划工作流图。
    
    Args:
        checkpointer: 可选的检查点器实例，用于持久化对话状态
    """
    graph = StateGraph(
        state_schema=TravelPlannerState,
        context_schema=TravelContext,
        output_schema=TravelPlannerOutput,
    )
    
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_sub_agent_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("user_review", user_review_node)
    
    graph.set_entry_point("plan")
    
    graph.add_edge("plan", "execute")
    graph.add_conditional_edges(
        "execute",
        should_continue,
        {
            "execute": "execute",
            "summarize": "summarize",
        },
    )
    graph.add_edge("summarize", "user_review")
    graph.add_conditional_edges(
        "user_review",
        route_after_review,
        {
            "plan": "plan",
            "__end__": END,
        },
    )
    
    compile_kwargs = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer
    
    return graph.compile(**compile_kwargs)


async def run_travel_planner(
    request: TripRequest,
    session_id: str = "default",
    user_id: str = "default_user"
) -> TripPlan:
    """
    运行旅游规划智能体。
    
    Args:
        request: 旅行请求
        session_id: 会话ID
        user_id: 用户ID
    
    Returns:
        生成的旅行计划
    """
    graph = build_travel_planner_graph()
    
    # 获取历史规划记忆
    historical_context = ""
    try:
        memory_manager = _get_memory_manager()
        if memory_manager:
            historical_context = await memory_manager.get_relevant_plans(user_id, request, session_id)
            if historical_context:
                logger.info(
                    "成功获取历史规划上下文",
                    user_id=user_id,
                    session_id=session_id,
                    context_length=len(historical_context)
                )
            else:
                historical_context = "该会话没有相关的历史规划记忆"
                logger.info(
                    "该会话没有历史规划记忆",
                    user_id=user_id,
                    session_id=session_id
                )
    except Exception as e:
        logger.warning("获取历史规划失败，继续执行", error=str(e))
        historical_context = "该会话没有相关的历史规划记忆"
    
    # 构建初始状态
    initial_state = {
        "trip_request": request,
        "messages": [HumanMessage(content=_build_user_message(request, historical_context))],
        "plan": [],
        "sub_agent_results": [],
        "current_task": None,
        "trip_plan": None,
        "notes": {},
        "attraction_pool": [],
        "hotel_pool": [],
    }
    
    # 构建上下文
    context = TravelContext(
        user_id=user_id,
        session_id=session_id,
    )
    
    # 确保 user_id 是字符串类型，langfuse只接受user_id为字符串
    safe_user_id = str(user_id) if user_id is not None else None
    trace_attributes = {}
    if user_id:
        trace_attributes["user_id"] = safe_user_id
    if session_id:
        trace_attributes["session_id"] = session_id
    
    # 添加环境信息到 Metadata (可选，但推荐)
    trace_attributes["metadata"] = {
        "environment": settings.ENVIRONMENT.value,
        "debug": str(settings.DEBUG).lower(),
    }

    # 使用上下文管理器包裹整个调用过程
    with propagate_attributes(**trace_attributes):
        # 执行图
        # InpuT默认为state_schema
        result = await graph.ainvoke(initial_state, context=context.model_dump(), config={"callbacks": [_get_langfuse_handler()]})
    
    trip_plan = result.get("trip_plan")
    
    # 保存规划请求到长期记忆
    if trip_plan:
        try:
            memory_manager = _get_memory_manager()
            if memory_manager:
                plan_summary = trip_plan.overall_suggestions[:500] if trip_plan.overall_suggestions else None
                await memory_manager.save_plan_request(user_id, request, plan_summary, session_id)
                logger.info("规划请求已保存到长期记忆", user_id=user_id, session_id=session_id)
        except Exception as e:
            logger.warning("保存规划请求失败", error=str(e))
    
    return trip_plan


def _build_user_message(request: TripRequest, historical_context: str = "") -> str:
    """构建用户消息。
    
    Args:
        request: 旅行请求
        historical_context: 历史规划上下文
        
    Returns:
        构建的用户消息
    """
    msg = f"请帮我规划一个{request.city}的{request.travel_days}日游行程。\n"
    msg += f"日期: {request.start_date} 至 {request.end_date}\n"
    msg += f"交通方式: {request.transportation}\n"
    msg += f"住宿偏好: {request.accommodation}\n"
    if request.preferences:
        msg += f"旅行偏好: {', '.join(request.preferences)}\n"
    if request.free_text_input:
        msg += f"额外要求: {request.free_text_input}\n"
    
    if historical_context:
        msg += f"\n---\n**历史规划参考：**\n{historical_context}\n"
        msg += "\n注意：请在规划时优先考虑用户的本次规划的请求，再参考历史偏好和需求。\n"
    
    return msg


async def stream_travel_planner(
    request: TripRequest,
    session_id: str = "default",
    user_id: str = "default_user",
    thread_id: str = None,
):
    """
    流式运行旅游规划智能体，逐步yield各节点的状态更新。
    使用AsyncPostgresSaver检查点器持久化对话状态，支持多轮对话。
    
    Args:
        request: 旅行请求
        session_id: 会话ID
        user_id: 用户ID
        thread_id: 检查点线程ID，用于区分不同的规划轮次。如果不提供，则使用session_id。
    
    Yields:
        dict: 每个节点执行后的状态更新事件
    """
    graph = await _get_compiled_graph()
    
    if thread_id is None:
        thread_id = session_id
    
    logger.info(
        "开始流式规划",
        session_id=session_id,
        thread_id=thread_id,
        user_id=user_id,
    )
    
    historical_context = ""
    try:
        memory_manager = _get_memory_manager()
        if memory_manager:
            historical_context = await memory_manager.get_relevant_plans(user_id, request, session_id)
            if historical_context:
                logger.info(
                    "成功获取历史规划上下文",
                    user_id=user_id,
                    session_id=session_id,
                    context_length=len(historical_context),
                )
            else:
                historical_context = "该会话没有相关的历史规划记忆"
                logger.info(
                    "该会话没有历史规划记忆",
                    user_id=user_id,
                    session_id=session_id
                )
    except Exception as e:
        logger.warning("获取历史规划失败，继续执行", error=str(e))
        historical_context = "该会话没有相关的历史规划记忆"
    
    initial_state = {
        "trip_request": request,
        "messages": [HumanMessage(content=_build_user_message(request, historical_context))],
        "plan": [],
        "sub_agent_results": [],
        "current_task": None,
        "trip_plan": None,
        "notes": {},
        "user_feedback": None,
        "attraction_pool": [],
        "hotel_pool": [],
    }
    
    context = TravelContext(
        user_id=user_id,
        session_id=session_id,
    )
    
    safe_user_id = str(user_id) if user_id is not None else None
    trace_attributes = {}
    if user_id:
        trace_attributes["user_id"] = safe_user_id
    if session_id:
        trace_attributes["session_id"] = session_id
    trace_attributes["metadata"] = {
        "environment": settings.ENVIRONMENT.value,
        "debug": str(settings.DEBUG).lower(),
    }

    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [_get_langfuse_handler()],
    }

    with propagate_attributes(**trace_attributes):
        async for event in graph.astream(
            initial_state,
            context=context.model_dump(),
            config=config,
            stream_mode="updates",
        ):
            yield event
    
    try:
        memory_manager = _get_memory_manager()
        if memory_manager:
            plan_summary = None
            await memory_manager.save_plan_request(user_id, request, plan_summary, session_id)
            logger.info("规划请求已保存到长期记忆", user_id=user_id, session_id=session_id)
    except Exception as e:
        logger.warning("保存规划请求失败", error=str(e))


async def resume_travel_planner(
    session_id: str,
    user_id: str = "default_user",
    resume_value: dict = None,
    thread_id: str = None,
):
    """
    恢复被interrupt暂停的旅游规划图，继续执行。
    
    Args:
        session_id: 会话ID
        user_id: 用户ID
        resume_value: 传递给interrupt的恢复值，格式: {"action": "complete"/"modify", "feedback": "..."}
        thread_id: 检查点线程ID，用于恢复正确的checkpoint。如果不提供，则使用session_id。
    
    Yields:
        dict: 每个节点执行后的状态更新事件
    """
    graph = await _get_compiled_graph()
    
    if thread_id is None:
        thread_id = session_id
    
    logger.info(
        "恢复规划",
        session_id=session_id,
        thread_id=thread_id,
        user_id=user_id,
        resume_action=resume_value.get("action") if resume_value else None,
    )
    
    context = TravelContext(
        user_id=user_id,
        session_id=session_id,
    )
    
    safe_user_id = str(user_id) if user_id is not None else None
    trace_attributes = {}
    if user_id:
        trace_attributes["user_id"] = safe_user_id
    if session_id:
        trace_attributes["session_id"] = session_id
    trace_attributes["metadata"] = {
        "environment": settings.ENVIRONMENT.value,
        "debug": str(settings.DEBUG).lower(),
    }

    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [_get_langfuse_handler()],
    }

    with propagate_attributes(**trace_attributes):
        async for event in graph.astream(
            Command(resume=resume_value),
            context=context.model_dump(),
            config=config,
            stream_mode="updates",
        ):
            yield event


async def get_graph_interrupt_state(session_id: str, thread_id: str = None) -> dict | None:
    """
    获取图的当前中断状态，用于判断图是否在user_review节点被中断。
    
    Args:
        session_id: 会话ID
        thread_id: 检查点线程ID，如果不提供，则使用session_id
    
    Returns:
        中断信息字典，如果没有中断则返回None
    """
    if thread_id is None:
        thread_id = session_id
    
    graph = await _get_compiled_graph()
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = await graph.aget_state(config)
        if state.tasks:
            for task in state.tasks:
                if task.interrupts:
                    interrupt_value = task.interrupts[0].value
                    return interrupt_value
        return None
    except Exception as e:
        logger.error("获取图中断状态失败", error=str(e), session_id=session_id, thread_id=thread_id)
        return None


def run_travel_planner_sync(
    request: TripRequest,
    session_id: str = "default",
    user_id: str = "default_user",
    cleanup: bool = True
) -> TripPlan:
    """同步运行旅游规划智能体。
    
    Args:
        request: 旅行请求
        session_id: 会话ID
        user_id: 用户ID
        cleanup: 是否在运行后清理资源（一次性脚本建议 True，Web 应用建议 False）
    
    Returns:
        生成的旅行计划
    """
    import asyncio
    import sys
    
    # Windows 系统需要使用 SelectorEventLoop 以支持 psycopg
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(
            run_travel_planner(request, session_id, user_id)
        )
        return result
    finally:
        if cleanup:
            try:
                rm = get_resource_manager()
                loop.run_until_complete(rm.shutdown())
            except RuntimeError:
                pass