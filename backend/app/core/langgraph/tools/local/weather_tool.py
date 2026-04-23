"""和风天气工具，为智能旅行助手提供天气数据。

本模块整合了和风天气的三个API：
1. 城市搜索：获取城市的LocationID
2. 每日天气预报：获取未来几天的天气数据
3. 空气质量每日预报：获取空气质量信息

对于旅游助手，重点关注以下信息：
- 温度（最高/最低）
- 天气状况（晴、雨、云等）
- 风力、风速
- 湿度
- 降水概率
- 空气质量
- 紫外线指数
- 能见度
"""

from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from app.core.config import settings
from app.core.logging import logger
from app.schemas.weather import (
    LocationInfo,
    QWeatherInfo,
    AirQualityInfo,
    TravelWeatherData,
)


QWEATHER_API_HOST = settings.QWEATHER_API_HOST


async def _make_qweather_request(
    url: str,
    params: dict,
    api_key: str,
) -> Optional[dict]:
    """发送和风天气API请求。

    参数:
        url: 请求URL
        params: 请求参数
        api_key: API密钥

    返回:
        dict: 响应数据
    """
    headers = {
        "X-QW-Api-Key": api_key,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            logger.debug(
                "发送和风天气API请求",
                url=url,
                params=params,
            )
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.debug(
                "和风天气API响应",
                status_code=response.status_code,
                code=data.get("code"),
            )
            return data
        except httpx.HTTPStatusError as e:
            logger.error(
                "和风天气API请求失败",
                url=url,
                status_code=e.response.status_code,
                error=str(e),
            )
            return None
        except Exception as e:
            logger.error(
                "和风天气API请求异常",
                url=url,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None


async def _get_location_id(city_name: str, api_key: str) -> Optional[LocationInfo]:
    """获取城市的LocationID和基本信息。

    参数:
        city_name: 城市名称
        api_key: 和风天气API密钥

    返回:
        LocationInfo: 城市信息，包含LocationID、经纬度等
    """
    if not QWEATHER_API_HOST:
        logger.error("未配置和风天气API Host")
        return None

    url = f"https://{QWEATHER_API_HOST}/geo/v2/city/lookup"
    params = {
        "location": city_name,
        "number": 1,
        "lang": "zh",
    }

    data = await _make_qweather_request(url, params, api_key)
    if not data:
        logger.error("获取城市信息失败", city_name=city_name)
        return None

    if data.get("code") != "200":
        logger.error(
            "和风天气API返回错误",
            city_name=city_name,
            code=data.get("code"),
            message=data,
        )
        return None

    if not data.get("location"):
        logger.warning("未找到城市", city_name=city_name)
        return None

    location = data["location"][0]
    logger.info(
        "成功获取城市信息",
        city_name=location["name"],
        city_id=location["id"],
    )
    return LocationInfo(
        name=location["name"],
        id=location["id"],
        lat=location["lat"],
        lon=location["lon"],
        adm2=location["adm2"],
        adm1=location["adm1"],
        country=location["country"],
    )


async def _get_weather_forecast(
    location_id: str,
    api_key: str,
    days: int = 3,
) -> Optional[List[QWeatherInfo]]:
    """获取天气预报数据。

    参数:
        location_id: 城市LocationID
        api_key: 和风天气API密钥
        days: 预报天数（3, 7, 10, 15, 30）

    返回:
        List[QWeatherInfo]: 天气预报列表
    """
    if not QWEATHER_API_HOST:
        return None

    days_map = {3: "3d", 7: "7d", 10: "10d", 15: "15d", 30: "30d"}
    days_param = days_map.get(days, "3d")

    url = f"https://{QWEATHER_API_HOST}/v7/weather/{days_param}"
    params = {
        "location": location_id,
        "lang": "zh",
        "unit": "m",
    }

    data = await _make_qweather_request(url, params, api_key)
    if not data:
        return None

    if data.get("code") != "200" or not data.get("daily"):
        return None

    weather_list = []
    for day in data["daily"]:
        weather_list.append(
            QWeatherInfo(
                date=day["fxDate"],
                temp_max=day["tempMax"],
                temp_min=day["tempMin"],
                text_day=day["textDay"],
                text_night=day["textNight"],
                wind_dir=day["windDirDay"],
                wind_scale=day["windScaleDay"],
                humidity=day["humidity"],
                precip=day["precip"],
                uv_index=day["uvIndex"],
                vis=day["vis"],
                sunrise=day.get("sunrise", ""),
                sunset=day.get("sunset", ""),
            )
        )

    return weather_list


async def _get_air_quality(
    latitude: str,
    longitude: str,
    api_key: str,
) -> Optional[AirQualityInfo]:
    """获取空气质量数据。

    参数:
        latitude: 纬度
        longitude: 经度
        api_key: 和风天气API密钥

    返回:
        AirQualityInfo: 空气质量信息
    """
    if not QWEATHER_API_HOST:
        return None

    url = f"https://{QWEATHER_API_HOST}/airquality/v1/daily/{latitude}/{longitude}"
    params = {
        "lang": "zh",
        "localTime": "true",
    }

    data = await _make_qweather_request(url, params, api_key)
    if not data:
        return None

    if not data.get("days") or not data["days"][0].get("indexes"):
        return None

    day_data = data["days"][0]
    aqi_index = day_data["indexes"][0]

    pollutants = {p["code"]: p for p in day_data.get("pollutants", [])}
    pm25 = pollutants.get("pm2p5", {}).get("concentration", {}).get("value", 0)
    pm10 = pollutants.get("pm10", {}).get("concentration", {}).get("value", 0)

    primary_pollutant = ""
    if aqi_index.get("primaryPollutant"):
        primary_pollutant = aqi_index["primaryPollutant"].get("name", "")

    health_advice = ""
    if aqi_index.get("health", {}).get("advice"):
        advice = aqi_index["health"]["advice"]
        health_advice = advice.get("generalPopulation", "")

    return AirQualityInfo(
        aqi=int(aqi_index.get("aqi", 0)),
        category=aqi_index.get("category", "未知"),
        primary_pollutant=primary_pollutant,
        pm25=pm25,
        pm10=pm10,
        health_advice=health_advice,
    )


def _generate_travel_advice(weather: List[QWeatherInfo], air_quality: Optional[AirQualityInfo]) -> str:
    """生成旅游建议。

    参数:
        weather: 天气预报数据
        air_quality: 空气质量数据

    返回:
        str: 旅游建议文本
    """
    advice_parts = []

    if weather:
        today = weather[0]
        advice_parts.append(f"今日天气：{today.text_day}，气温 {today.temp_min}°C 至 {today.temp_max}°C")

        if int(today.uv_index) >= 5:
            advice_parts.append("紫外线较强，建议做好防晒措施")

        if float(today.precip) > 0:
            advice_parts.append("有降水，建议携带雨具")

        if int(today.vis) < 10:
            advice_parts.append("能见度较低，出行注意安全")

        if int(today.humidity) > 80:
            advice_parts.append("湿度较高，体感可能较闷热")

    if air_quality:
        if air_quality.aqi > 100:
            advice_parts.append(f"空气质量{air_quality.category}，AQI {air_quality.aqi}，建议减少户外活动")
        elif air_quality.aqi > 50:
            advice_parts.append(f"空气质量{air_quality.category}，AQI {air_quality.aqi}，敏感人群需注意")
        else:
            advice_parts.append(f"空气质量{air_quality.category}，AQI {air_quality.aqi}，适合户外活动")

    if not advice_parts:
        return "暂无特别建议"

    return "；".join(advice_parts) + "。"


@tool
async def get_travel_weather(
    city_name: str,
    forecast_days: int = 3,
) -> Dict[str, Any]:
    """获取指定城市的旅游天气信息。

    此工具整合了天气预报和空气质量数据，为旅行规划提供全面的天气参考。

    参数:
        city_name: 城市名称（如：北京、上海、广州）
        forecast_days: 预报天数，可选值：3, 7, 10, 15, 30，默认为3天

    返回:
        包含天气、空气质量和旅游建议的字典

    示例:
        >>> result = await get_travel_weather.ainvoke({"city_name": "北京", "forecast_days": 3})
        >>> print(result["travel_advice"])
    """
    api_key = settings.QWEATHER_API_KEY
    if not api_key:
        return {"error": "未配置和风天气API密钥，请设置环境变量 QWEATHER_API_KEY"}

    if not QWEATHER_API_HOST:
        return {"error": "未配置和风天气API Host，请在控制台-设置中查看你的API Host，并设置环境变量 QWEATHER_API_HOST"}

    location_info = await _get_location_id(city_name, api_key)
    if not location_info:
        return {"error": f"未找到城市 '{city_name}'，请检查城市名称是否正确"}

    weather_data = await _get_weather_forecast(location_info.id, api_key, forecast_days)
    if not weather_data:
        return {"error": f"获取天气数据失败，请稍后重试"}

    air_quality_data = await _get_air_quality(location_info.lat, location_info.lon, api_key)

    travel_advice = _generate_travel_advice(weather_data, air_quality_data)

    return TravelWeatherData(
        location=location_info,
        weather=weather_data,
        air_quality=air_quality_data,
        travel_advice=travel_advice,
    ).model_dump()


@tool
async def search_city(city_name: str) -> Dict[str, Any]:
    """搜索城市并返回城市信息。

    此工具用于获取城市的LocationID和基本信息，可用于后续的天气查询。

    参数:
        city_name: 城市名称（支持模糊搜索）

    返回:
        包含城市信息的字典

    示例:
        >>> result = await search_city.ainvoke({"city_name": "北京"})
        >>> print(result["name"], result["id"])
    """
    api_key = settings.QWEATHER_API_KEY
    if not api_key:
        return {"error": "未配置和风天气API密钥，请设置环境变量 QWEATHER_API_KEY"}

    if not QWEATHER_API_HOST:
        return {"error": "未配置和风天气API Host，请在控制台-设置中查看你的API Host，并设置环境变量 QWEATHER_API_HOST"}

    location_info = await _get_location_id(city_name, api_key)
    if not location_info:
        return {"error": f"未找到城市 '{city_name}'，请检查城市名称是否正确"}

    return location_info.model_dump()


weather_tools = [
    get_travel_weather,
    search_city,
]