from pydantic import BaseModel, Field


class Location(BaseModel):
    """位置信息"""
    
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")
