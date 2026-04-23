from fastapi import APIRouter, Depends, HTTPException

from app.schemas.travel import TripRequest, TripPlanResponse
from app.core.langgraph.agents.travel_plan_agent.graph import run_travel_planner
from app.models.session import Session
from app.api.v1.auth import get_current_session

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