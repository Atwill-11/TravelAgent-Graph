import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.travel import TripRequest, TripPlanResponse
from app.core.langgraph.agents.travel_plan_agent.graph import run_travel_planner, stream_travel_planner
from app.core.langgraph.agents.travel_plan_agent.node import (
    NODE_DISPLAY_NAMES,
    NODE_DISPLAY_ICONS,
    SUB_AGENT_DISPLAY_NAMES,
    SUB_AGENT_DISPLAY_ICONS,
)
from app.models.session import Session
from app.api.v1.auth import get_current_session
from app.core.logging import logger

router = APIRouter()


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划",
)
async def plan_trip(
    request: TripRequest,
    session: Session = Depends(get_current_session),
):
    """生成旅行计划。"""
    try:
        trip_plan = await run_travel_planner(
            request=request,
            session_id=session.id,
            user_id=str(session.user_id),
        )
        
        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan,
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}",
        )


async def _stream_event_generator(
    request: TripRequest,
    session_id: str,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """SSE事件生成器，将旅行规划过程拆分为流式事件。"""
    try:
        yield f"event: start\ndata: {json.dumps({'message': '开始规划旅行...', 'session_id': session_id}, ensure_ascii=False)}\n\n"

        async for event in stream_travel_planner(
            request=request,
            session_id=session_id,
            user_id=user_id,
        ):
            for node_name, node_state in event.items():
                display_name = NODE_DISPLAY_NAMES.get(node_name, node_name)
                icon = NODE_DISPLAY_ICONS.get(node_name, "📌")

                if node_name == "plan":
                    plan_items = []
                    node_plan = node_state.get('plan', [])
                    if node_plan:
                        plan_items = [
                            {
                                "task": t.get('task') if isinstance(t, dict) else t.task,
                                "type": t.get('type') if isinstance(t, dict) else t.type,
                                "type_display": SUB_AGENT_DISPLAY_NAMES.get(t.get('type') if isinstance(t, dict) else t.type, t.get('type') if isinstance(t, dict) else t.type),
                                "icon": SUB_AGENT_DISPLAY_ICONS.get(t.get('type') if isinstance(t, dict) else t.type, "📌"),
                            }
                            for t in node_plan
                        ]
                    messages = []
                    node_messages = node_state.get('messages', [])
                    if node_messages:
                        messages = [m.get('content') if isinstance(m, dict) else m.content for m in node_messages]
                    
                    data = {
                        'node': node_name,
                        'display_name': display_name,
                        'icon': icon,
                        'message': f'{icon} {display_name}：已规划 {len(plan_items)} 个子任务',
                        'plan_items': plan_items,
                        'messages': messages,
                    }
                    yield f"event: plan\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                elif node_name == "execute":
                    current_task = node_state.get('current_task')
                    task_type = None
                    task_status = None
                    node_plan = node_state.get('plan', [])
                    if node_plan:
                        for t in node_plan:
                            t_task = t.get('task') if isinstance(t, dict) else t.task
                            if t_task == current_task:
                                task_type = t.get('type') if isinstance(t, dict) else t.type
                                task_status = t.get('status') if isinstance(t, dict) else t.status
                                break
                    sub_display = SUB_AGENT_DISPLAY_NAMES.get(task_type, task_type or "未知") if task_type else ""
                    sub_icon = SUB_AGENT_DISPLAY_ICONS.get(task_type, "⚙️") if task_type else "⚙️"
                    messages = []
                    node_messages = node_state.get('messages', [])
                    if node_messages:
                        messages = [m.get('content') if isinstance(m, dict) else m.content for m in node_messages]
                    
                    data = {
                        'node': node_name,
                        'display_name': display_name,
                        'icon': icon,
                        'current_task': current_task,
                        'task_type': task_type,
                        'task_type_display': sub_display,
                        'task_icon': sub_icon,
                        'task_status': task_status,
                        'message': f'{sub_icon} {sub_display}：{current_task}' if current_task else f'{icon} {display_name}',
                        'messages': messages,
                    }
                    yield f"event: execute\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                elif node_name == "summarize":
                    trip_plan = None
                    suggestions = ""
                    node_trip_plan = node_state.get('trip_plan')
                    if node_trip_plan:
                        if hasattr(node_trip_plan, 'model_dump'):
                            trip_plan = node_trip_plan.model_dump()
                        elif isinstance(node_trip_plan, dict):
                            trip_plan = node_trip_plan
                        if trip_plan:
                            suggestions = trip_plan.get('overall_suggestions', '') or ''
                    messages = []
                    node_messages = node_state.get('messages', [])
                    if node_messages:
                        messages = [m.get('content') if isinstance(m, dict) else m.content for m in node_messages]
                    
                    data = {
                        'node': node_name,
                        'display_name': display_name,
                        'icon': icon,
                        'message': f'{icon} {display_name}：正在汇总生成最终旅行计划...',
                        'trip_plan': trip_plan,
                        'suggestions': suggestions,
                        'messages': messages,
                    }
                    yield f"event: summarize\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                else:
                    data = {
                        'node': node_name,
                        'display_name': display_name,
                        'icon': icon,
                        'message': f'{icon} {display_name}',
                    }
                    yield f"event: step\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield f"event: done\ndata: {json.dumps({'message': '旅行计划生成完成！', 'success': True}, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error("SSE流式响应异常", error=str(e), exc_info=True)
        yield f"event: error\ndata: {json.dumps({'message': f'生成旅行计划失败: {str(e)}', 'success': False}, ensure_ascii=False)}\n\n"


@router.post(
    "/plan/stream",
    summary="流式生成旅行计划",
    description="根据用户输入的旅行需求,以SSE流式方式实时返回智能助手的思考过程和生成结果",
)
async def plan_trip_stream(
    request: TripRequest,
    session: Session = Depends(get_current_session),
):
    """以SSE流式方式生成旅行计划，实时展示Agent思考过程。"""
    return StreamingResponse(
        _stream_event_generator(
            request=request,
            session_id=session.id,
            user_id=str(session.user_id),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )