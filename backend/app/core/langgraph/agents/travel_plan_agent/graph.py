"""智能旅游助手主规划智能体。

该模块实现了一个基于 LangGraph 的旅游规划工作流，包括：
1. 任务规划：分析用户需求，拆分为子任务
2. 子智能体调用：委派任务给专门的子智能体执行
3. 结果总结：汇总所有子任务结果，生成最终旅游规划
4. 长期记忆：存储和检索历史规划请求
"""

from urllib.parse import quote_plus

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from psycopg_pool import AsyncConnectionPool

from app.schemas.travel import TripRequest, TripPlan
from app.schemas.agent import (
    TravelPlannerState,
    TravelContext,
    TravelPlannerOutput,
)
from .node import (
    plan_node,
    execute_sub_agent_node,
    summarize_node,
    should_continue,
)
from .travel_memory import TravelMemoryManager

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse import propagate_attributes
from app.core.config import settings
from app.core.logging import logger

# lagfuse初始化
langfuse = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST,
)

# 旅游记忆管理器（全局单例）
_travel_memory_manager: TravelMemoryManager = None
_connection_pool: AsyncConnectionPool = None


async def _get_memory_manager() -> TravelMemoryManager:
    """获取或创建旅游记忆管理器实例。"""
    global _travel_memory_manager, _connection_pool
    
    if _travel_memory_manager is None:
        try:
            if _connection_pool is None:
                connection_url = (
                    "postgresql://"
                    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )
                
                _connection_pool = AsyncConnectionPool(
                    connection_url,
                    open=False,
                    max_size=settings.POSTGRES_POOL_SIZE,
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": 5,
                        "prepare_threshold": None,
                    },
                )
                await _connection_pool.open()
                logger.info("旅游规划连接池创建成功")
            
            _travel_memory_manager = TravelMemoryManager()
            await _travel_memory_manager._get_store(_connection_pool)
            logger.info("旅游记忆管理器初始化成功")
            
        except Exception as e:
            logger.error("旅游记忆管理器初始化失败", error=str(e), exc_info=True)
            _travel_memory_manager = None
    
    return _travel_memory_manager


async def _cleanup_resources(wait_for_tasks: bool = True, timeout: float = 3.0) -> None:
    """清理全局资源，关闭连接池并等待后台任务完成。
    
    Args:
        wait_for_tasks: 是否等待后台任务完成（一次性脚本建议 True，Web 应用建议 False）
        timeout: 等待后台任务的超时时间（秒）
    """
    global _connection_pool, _travel_memory_manager
    
    # 1. 先关闭连接池（这会优雅地停止所有 worker 任务）
    if _connection_pool is not None:
        try:
            await _connection_pool.close()
            logger.info("旅游规划连接池已关闭")
        except Exception as e:
            logger.error("关闭连接池失败", error=str(e))
        finally:
            _connection_pool = None
    
    # 2. 清理记忆管理器引用
    if _travel_memory_manager is not None:
        _travel_memory_manager = None
    
    # 3. 等待其他后台任务完成（可选）
    if wait_for_tasks:
        await _wait_for_background_tasks(timeout=timeout)


async def _wait_for_background_tasks(timeout: float = 5.0) -> None:
    """等待所有后台任务完成。
    
    Args:
        timeout: 最大等待时间（秒）
    """
    import asyncio
    
    # 获取当前事件循环中的所有任务
    all_tasks = asyncio.all_tasks()
    
    # 排除当前任务（清理任务本身）
    current_task = asyncio.current_task()
    pending_tasks = [task for task in all_tasks if task is not current_task]
    
    if not pending_tasks:
        return
    
    logger.info(f"等待 {len(pending_tasks)} 个后台任务完成...")
    
    try:
        # 等待所有任务完成，带超时
        await asyncio.wait_for(
            asyncio.gather(*pending_tasks, return_exceptions=True),
            timeout=timeout
        )
        logger.info("所有后台任务已完成")
    except asyncio.TimeoutError:
        logger.warning(f"等待后台任务超时（{timeout}秒），取消剩余任务")
        # 取消所有未完成的任务
        for task in pending_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    except Exception as e:
        logger.error("等待后台任务时发生错误", error=str(e))

def build_travel_planner_graph():
    """构建旅游规划工作流图。"""
    graph = StateGraph(
        state_schema=TravelPlannerState,
        context_schema=TravelContext,
        # input_schema默认为state_schema
        output_schema=TravelPlannerOutput,
    )
    
    # 添加节点
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_sub_agent_node)
    graph.add_node("summarize", summarize_node)
    
    # 设置入口
    graph.set_entry_point("plan")
    
    # 添加边
    graph.add_edge("plan", "execute")
    graph.add_conditional_edges(
        "execute",
        should_continue,
        {
            "execute": "execute",
            "summarize": "summarize",
        },
    )
    graph.add_edge("summarize", END)
    
    return graph.compile()


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
        memory_manager = await _get_memory_manager()
        if memory_manager:
            historical_context = await memory_manager.get_relevant_plans(user_id, request, session_id)
            if historical_context:
                logger.info(
                    "成功获取历史规划上下文",
                    user_id=user_id,
                    session_id=session_id,
                    context_length=len(historical_context)
                )
    except Exception as e:
        logger.warning("获取历史规划失败，继续执行", error=str(e))
    
    # 构建初始状态
    initial_state = {
        "trip_request": request,
        "messages": [HumanMessage(content=_build_user_message(request, historical_context))],
        "plan": [],
        "sub_agent_results": [],
        "current_task": None,
        "trip_plan": None,
        "notes": {},
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
        result = await graph.ainvoke(initial_state, context=context.model_dump(), config={"callbacks": [CallbackHandler()]})
    
    trip_plan = result.get("trip_plan")
    
    # 保存规划请求到长期记忆
    if trip_plan:
        try:
            memory_manager = await _get_memory_manager()
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
        # 只在一次性脚本中清理资源
        if cleanup:
            loop.run_until_complete(_cleanup_resources(wait_for_tasks=True, timeout=5.0))


# ========== 测试入口 ==========

# if __name__ == "__main__":
#     import asyncio
#     import sys
    
#     # Windows 系统需要使用 SelectorEventLoop 以支持 psycopg
#     if sys.platform == "win32":
#         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
#     test_request = TripRequest(
#         city="西安",
#         start_date="2026-04-25",
#         end_date="2026-04-28",
#         travel_days=3,
#         transportation="公共交通",
#         accommodation="",
#         preferences=[""],
#         free_text_input="",
#     )
#     print(f"用户需求: {test_request.model_dump()}")
#     print("="*60)
    
#     result = run_travel_planner_sync(test_request)
#     print("\n规划完成！")
#     if result:
#         print(f"城市: {result.city}")
#         print(f"天数: {len(result.days)}")
