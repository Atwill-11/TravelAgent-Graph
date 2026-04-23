"""该文件定义了应用的图状态模型"""
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import (
    BaseModel,
)

class AgentContext(BaseModel):
    """Agent 运行时上下文 Schema。"""

    user_id: Optional[str] = None
    session_id: str
    environment: str = "development"
    debug: bool = False

class CustomAgentState(TypedDict):
    """自定义 Agent 状态 Schema，扩展长期记忆支持。"""

    messages: Annotated[list[BaseMessage], add_messages]
    long_term_memory: str
    user_id: Optional[str]
    session_id: str