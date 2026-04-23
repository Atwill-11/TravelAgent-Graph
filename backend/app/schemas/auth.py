"""本文件包含应用程序的身份认证相关数据模型定义。"""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)


class Token(BaseModel):
    """身份认证用的 Token 数据模型。

    属性:
        access_token: JWT 访问令牌。
        token_type: 令牌类型（固定为 "bearer"）。
        expires_at: 令牌过期时间戳。
    """

    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_at: datetime = Field(..., description="令牌过期时间戳")


class TokenResponse(BaseModel):
    """登录端点的响应数据模型。

    属性:
        access_token: JWT 访问令牌。
        token_type: 令牌类型（固定为 "bearer"）。
        expires_at: 令牌过期时间。
    """

    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_at: datetime = Field(..., description="令牌过期时间")


class UserCreate(BaseModel):
    """用户注册请求数据模型。

    属性:
        email: 用户邮箱地址。
        password: 用户密码。
    """

    email: EmailStr = Field(..., description="用户邮箱地址")
    password: SecretStr = Field(..., description="用户密码", min_length=8, max_length=64)

    # 当解析 password 字段时，在类型转换和基础校验完成后，调用下方方法。
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        """验证密码强度。

        参数:
            v: 待验证的密码。

        返回:
            SecretStr: 验证通过的密码。

        异常:
            ValueError: 当密码强度不足时抛出。
        """
        password = v.get_secret_value()

        # 检查常见密码强度要求
        if len(password) < 8:
            raise ValueError("密码长度必须至少为 8 个字符")

        if not re.search(r"[A-Z]", password):
            raise ValueError("密码必须包含至少一个大写字母")

        if not re.search(r"[a-z]", password):
            raise ValueError("密码必须包含至少一个小写字母")

        if not re.search(r"[0-9]", password):
            raise ValueError("密码必须包含至少一个数字")

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValueError("密码必须包含至少一个特殊字符")

        return v


class UserResponse(BaseModel):
    """用户操作响应数据模型。

    属性:
        id: 用户 ID。
        email: 用户邮箱地址。
        token: 身份认证令牌。
    """

    id: int = Field(..., description="用户 ID")
    email: str = Field(..., description="用户邮箱地址")
    token: Token = Field(..., description="身份认证令牌")


class SessionResponse(BaseModel):
    """会话创建响应数据模型。

    属性:
        session_id: 聊天会话的唯一标识符。
        name: 会话名称（默认为空字符串）。
        token: 会话的身份认证令牌。
    """

    session_id: str = Field(..., description="聊天会话的唯一标识符")
    name: str = Field(default="", description="会话名称", max_length=100)
    token: Token = Field(..., description="会话的身份认证令牌")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """清洗会话名称。

        参数:
            v: 待清洗的名称。

        返回:
            str: 清洗后的名称。
        """
        # 移除可能存在安全隐患的字符
        sanitized = re.sub(r'[<>{}[\]()\'"`]', "", v)
        return sanitized
