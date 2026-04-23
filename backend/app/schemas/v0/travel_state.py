"""旅游规划智能体状态模式定义。"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

from app.schemas.travel import TripRequest, TripPlan


# ========== Context Schema (运行时上下文) ==========

class TravelContext(BaseModel):
    """运行时上下文，包含用户会话信息。"""
    user_id: str = Field(default="default_user", description="用户ID")
    session_id: str = Field(default="default", description="会话ID")
    
    class Config:
        extra = "allow"


# ========== 子智能体相关 Schema ==========

class TaskItem(BaseModel):
    """单个任务项。"""
    task: str = Field(description="任务描述")
    type: str = Field(description="任务类型: weather/attraction/hotel")
    status: str = Field(default="pending", description="状态: pending/completed/failed")
    result: Optional[str] = Field(default=None, description="执行结果")


class SubAgentResult(BaseModel):
    """子智能体执行结果。"""
    task: str = Field(description="任务描述")
    type: str = Field(description="子智能体类型")
    result: str = Field(description="执行结果")
    structured_data: Optional[dict] = Field(default=None, description="结构化数据，用于写入TripPlan对应字段")

    class Config:
        arbitrary_types_allowed = True


# ========== State Schema (内部状态) ==========

class TravelPlannerState(BaseModel):
    """旅游规划主智能体状态。"""
    
    trip_request: Optional[TripRequest] = Field(default=None, description="原始旅行请求")
    messages: List[BaseMessage] = Field(default_factory=list, description="消息列表")
    plan: List[TaskItem] = Field(default_factory=list, description="任务计划列表")
    current_task: Optional[str] = Field(default=None, description="当前执行的任务")
    sub_agent_results: List[SubAgentResult] = Field(default_factory=list, description="子智能体执行结果")
    trip_plan: Optional[TripPlan] = Field(default=None, description="生成的旅行计划")
    notes: dict = Field(default_factory=dict, description="备注信息")
    
    class Config:
        arbitrary_types_allowed = True


# ========== Output Schema (输出) ==========

class TravelPlannerOutput(BaseModel):
    """旅游规划输出。"""
    trip_plan: Optional[TripPlan] = Field(default=None, description="生成的旅行计划")
    messages: List[BaseMessage] = Field(default_factory=list, description="最终消息")
    
    class Config:
        arbitrary_types_allowed = True