"""该文件包含应用的用户模型。"""

from typing import (
    TYPE_CHECKING,
    List,
)

import bcrypt
from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

# 在运行时 不会被执行，仅在类型检查时会导入 Session 模型，防止循环导入问题
if TYPE_CHECKING:
    from app.models.session import Session


class User(BaseModel, table=True):
    """用户模型，用于存储用户账号信息。
    
    属性：
    id: 主键
    email: 用户邮箱（唯一）
    hashed_password: 密码的bcrypt哈希值
    created_at: 创建时间
    sessions: 用户的聊天会话关系
    """

    id: int = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str

    # 使用字符串前向引用，SQLModel 会在运行时解析
    sessions: List["Session"] = Relationship(back_populates="user")

    def verify_password(self, password: str) -> bool:
        """验证密码是否匹配哈希值。"""
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """使用bcrypt哈希密码。"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# 避免循环导入
# from app.models.session import Session  # noqa: E402
