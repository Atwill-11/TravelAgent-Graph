from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator
import json


class AttractionList(BaseModel):
    """景点子智能体的结构化输出"""
    attractions: List[dict] = Field(
        default_factory=list,
        description="搜索到的景点列表，每个景点包含完整的POI信息"
    )
    search_summary: str = Field(
        default="",
        description="搜索结果摘要，说明找到了多少个景点"
    )


class HotelList(BaseModel):
    """酒店子智能体的结构化输出"""
    hotels: List[dict] = Field(
        default_factory=list,
        description="搜索到的酒店列表，每个酒店包含完整的POI信息"
    )
    search_summary: str = Field(
        default="",
        description="搜索结果摘要，说明找到了多少个酒店"
    )


class DayAttractionSelection(BaseModel):
    """单日景点选择"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="第几天 (从0开始)")
    selected_attraction_names: List[str] = Field(
        default_factory=list,
        description="选择的景点名称列表"
    )
    selection_reason: str = Field(
        default="",
        description="选择理由"
    )


class HotelSelection(BaseModel):
    """酒店选择"""
    selected_hotel_name: str = Field(
        default="",
        description="选择的酒店名称"
    )
    selection_reason: str = Field(
        default="",
        description="选择理由"
    )


class DayPlanSelection(BaseModel):
    """LLM 生成的行程选择结果"""
    days: List[DayAttractionSelection] = Field(
        default_factory=list,
        description="每天的景点选择"
    )
    hotel: Optional[Union[HotelSelection, str, dict]] = Field(
        default=None,
        description="酒店选择（可以是 HotelSelection 对象、字典或 JSON 字符串）"
    )
    overall_suggestions: str = Field(
        default="",
        description="整体建议和说明"
    )
    
    @field_validator('hotel', mode='before')
    @classmethod
    def parse_hotel(cls, v):
        """将字符串或字典转换为 HotelSelection 对象"""
        if v is None:
            return None
        if isinstance(v, HotelSelection):
            return v
        if isinstance(v, str):
            try:
                data = json.loads(v)
                return HotelSelection(**data)
            except (json.JSONDecodeError, TypeError):
                return None
        if isinstance(v, dict):
            return HotelSelection(**v)
        return None
