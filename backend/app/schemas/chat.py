"""本文件定义了应用程序的聊天数据模型。"""

import re
from typing import (
    List,
    Literal,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class Message(BaseModel):
    """聊天接口的消息数据模型。

    属性:
        role: 消息发送者的角色（用户或助手）。
        content: 消息内容。
    """

    model_config = {"extra": "ignore"}

    role: Literal["user", "assistant", "system"] = Field(..., description="消息发送者的角色")
    content: str = Field(..., description="消息内容", min_length=1, max_length=3000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """验证消息内容。

        参数:
            v: 待验证的内容

        返回:
            str: 验证通过的内容

        异常:
            ValueError: 如果内容包含不允许的模式
        """
        # 检查可能包含有害内容的脚本标签
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("Content contains potentially harmful script tags")

        # 检查空字节
        if "\0" in v:
            raise ValueError("Content contains null bytes")

        return v


class ChatRequest(BaseModel):
    """聊天接口的请求数据模型。

    属性:
        messages: 对话中的消息列表。
    """

    messages: List[Message] = Field(
        ...,
        description="对话中的消息列表",
        min_length=1,
    )


class ChatResponse(BaseModel):
    """聊天接口的响应数据模型。

    属性:
        messages: 对话中的消息列表。
    """

    messages: List[Message] = Field(..., description="对话中的消息列表")


class StreamResponse(BaseModel):
    """流式聊天接口的响应数据模型。

    属性:
        content: 当前数据块的内容。
        done: 流式传输是否已完成。
    """

    content: str = Field(default="", description="当前数据块的内容")
    done: bool = Field(default=False, description="流式传输是否已完成")