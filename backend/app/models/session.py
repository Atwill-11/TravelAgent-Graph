"""该文件包含应用的聊天会话模型。"""

from typing import (
    TYPE_CHECKING,
    List,
)

from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Session(BaseModel, table=True):
    """聊天会话模型，用于存储聊天会话信息。

    Attributes:
        id: 主键
        user_id: user的主键
        name: 会话名称（默认为空字符串）
        current_thread_id: 当前轮次的thread_id，用于checkpoint管理
        created_at: 会话创建时间
        messages: 会话消息关系
        user: 会话所有者关系
    """

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    name: str = Field(default="")
    current_thread_id: str | None = Field(default=None, description="当前轮次的thread_id，用于checkpoint管理")
    user: "User" = Relationship(back_populates="sessions")
