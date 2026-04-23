from typing import Annotated, Optional, List, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class CustomAgentState(dict):
    """自定义 Agent 状态 Schema，扩展长期记忆支持。"""

    messages: Annotated[list[BaseMessage], add_messages]
    long_term_memory: str
    user_id: Optional[str]
    session_id: str


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
    structured_data: Optional[Any] = Field(default=None, description="结构化数据，用于写入TripPlan对应字段（可以是dict、list等类型）")

    class Config:
        arbitrary_types_allowed = True
