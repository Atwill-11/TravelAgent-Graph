from typing import Optional, List

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from app.schemas.travel import TripPlan, TripRequest
from app.schemas.travel.components import Attraction, Hotel
from .state import TaskItem, SubAgentResult


class TravelPlannerState(BaseModel):
    """旅游规划主智能体状态。"""

    trip_request: Optional[TripRequest] = Field(default=None, description="原始旅行请求")
    messages: List[BaseMessage] = Field(default_factory=list, description="消息列表")
    plan: List[TaskItem] = Field(default_factory=list, description="任务计划列表")
    current_task: Optional[str] = Field(default=None, description="当前执行的任务")
    sub_agent_results: List[SubAgentResult] = Field(default_factory=list, description="子智能体执行结果")
    attraction_pool: List[Attraction] = Field(default_factory=list, description="景点池：存储所有搜索到的景点，等待分配到各天")
    hotel_pool: List[Hotel] = Field(default_factory=list, description="酒店池：存储所有搜索到的酒店，等待分配")
    trip_plan: Optional[TripPlan] = Field(default=None, description="生成的旅行计划")
    notes: dict = Field(default_factory=dict, description="备注信息")

    class Config:
        arbitrary_types_allowed = True


class TravelPlannerOutput(BaseModel):
    """旅游规划主智能体输出。"""

    trip_plan: Optional[TripPlan] = Field(default=None, description="生成的旅行计划")
    messages: List[BaseMessage] = Field(default_factory=list, description="最终消息")

    class Config:
        arbitrary_types_allowed = True
