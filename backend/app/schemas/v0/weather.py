"""和风天气数据模型。

本模块定义了和风天气API相关的数据结构，用于旅游规划智能体。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class LocationInfo(BaseModel):
    """城市位置信息。"""
    name: str = Field(..., description="城市名称")
    id: str = Field(..., description="城市 LocationID")
    lat: str = Field(..., description="纬度")
    lon: str = Field(..., description="经度")
    adm2: str = Field(default="", description="所属城市/地区")
    adm1: str = Field(default="", description="所属省份/州")
    country: str = Field(..., description="所属国家")


class WeatherInfo(BaseModel):
    """天气信息。"""
    date: str = Field(..., description="预报日期 YYYY-MM-DD")
    temp_max: str = Field(..., description="最高温度")
    temp_min: str = Field(..., description="最低温度")
    text_day: str = Field(default="", description="白天天气状况")
    text_night: str = Field(default="", description="夜间天气状况")
    wind_dir: str = Field(default="", description="风向")
    wind_scale: str = Field(default="", description="风力等级")
    humidity: str = Field(default="", description="相对湿度")
    precip: str = Field(default="", description="降水量")
    uv_index: str = Field(default="", description="紫外线指数")
    vis: str = Field(default="", description="能见度")
    sunrise: str = Field(default="", description="日出时间")
    sunset: str = Field(default="", description="日落时间")


class AirQualityInfo(BaseModel):
    """空气质量信息。"""
    aqi: int = Field(default=0, description="空气质量指数")
    category: str = Field(default="未知", description="空气质量类别")
    primary_pollutant: str = Field(default="", description="主要污染物")
    pm25: float = Field(default=0.0, description="PM2.5 浓度")
    pm10: float = Field(default=0.0, description="PM10 浓度")
    health_advice: str = Field(default="", description="健康建议")


class TravelWeatherData(BaseModel):
    """旅游天气数据。"""
    location: LocationInfo = Field(..., description="位置信息")
    weather: List[WeatherInfo] = Field(default=[], description="天气预报列表")
    air_quality: Optional[AirQualityInfo] = Field(default=None, description="空气质量信息")
    travel_advice: str = Field(default="", description="旅行建议")