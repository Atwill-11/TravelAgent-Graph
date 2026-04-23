"""基础模型和所有模型的通用导入。"""

from datetime import datetime, UTC
from typing import Annotated
from sqlmodel import Field, SQLModel

class BaseModel(SQLModel):
    """基础模型，包含公共字段。继承自SQLModel。"""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))