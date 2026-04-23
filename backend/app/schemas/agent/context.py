from typing import Optional

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """Agent 运行时上下文 Schema。"""

    user_id: Optional[str] = None
    session_id: str
    environment: str = "development"
    debug: bool = False


class TravelContext(BaseModel):
    """运行时上下文，包含用户会话信息。"""

    user_id: str = Field(default="default_user", description="用户ID")
    session_id: str = Field(default="default", description="会话ID")

    class Config:
        extra = "allow"
