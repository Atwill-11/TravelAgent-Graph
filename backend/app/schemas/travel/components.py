from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Location


class Attraction(BaseModel):
    """景点信息"""

    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="经纬度坐标")
    poi_id: str = Field(default="", description="POI ID")
    city: str = Field(default="", description="所在城市")
    type: str = Field(default="", description="景点类型")
    rating: Optional[float] = Field(default=None, description="评分")
    open_time: str = Field(default="", description="开放时间")
    opentime2: str = Field(default="", description="详细开放时间")
    business_area: str = Field(default="", description="所属商圈")
    level: str = Field(default="", description="景区级别(如5A、4A)")
    ticket_price: int = Field(default=0, description="门票价格(元)")
    visit_duration: int = Field(default=120, description="建议游览时间(分钟)")
    description: Optional[str] = Field(default=None, description="景点描述")
    photos: Optional[List[str]] = Field(default_factory=list, description="景点图片URL列表")
    image_url: Optional[str] = Field(default=None, description="图片URL")

    @classmethod
    def from_poi_detail(cls, poi_data: dict) -> "Attraction":
        """
        从 maps_search_detail 工具返回的POI数据创建Attraction实例。
        
        Args:
            poi_data: 工具返回的POI详情数据，格式如：
                {
                    "id": "B000A83C1S",
                    "name": "天安门广场",
                    "location": "116.397755,39.903182",
                    "address": "东长安街",
                    "business_area": [],
                    "city": "北京市",
                    "type": "风景名胜;风景名胜;红色景区|风景名胜;公园广场;城市广场",
                    "rating": "4.9",
                    "open_time": "05:00-22:00",
                    "opentime2": "周一至周日 05:00-22:00",
                    "level": [],
                    "cost": []
                }
        
        Returns:
            Attraction实例
        """
        location = None
        if "location" in poi_data and poi_data["location"]:
            try:
                lon, lat = poi_data["location"].split(",")
                location = Location(
                    longitude=float(lon),
                    latitude=float(lat)
                )
            except (ValueError, AttributeError):
                pass
        
        rating = None
        if "rating" in poi_data and poi_data["rating"]:
            try:
                rating = float(poi_data["rating"])
            except (ValueError, TypeError):
                pass
        
        business_area_str = ""
        if "business_area" in poi_data:
            if isinstance(poi_data["business_area"], list):
                business_area_str = poi_data["business_area"][0] if poi_data["business_area"] else ""
            else:
                business_area_str = str(poi_data["business_area"])
        
        level_str = ""
        if "level" in poi_data:
            if isinstance(poi_data["level"], list):
                level_str = ", ".join(poi_data["level"]) if poi_data["level"] else ""
            else:
                level_str = str(poi_data["level"])
        
        ticket_price = 0
        if "cost" in poi_data:
            if isinstance(poi_data["cost"], list) and poi_data["cost"]:
                try:
                    ticket_price = int(poi_data["cost"][0])
                except (ValueError, TypeError):
                    pass
            elif isinstance(poi_data["cost"], (int, str)):
                try:
                    ticket_price = int(poi_data["cost"])
                except (ValueError, TypeError):
                    pass
        
        open_time_value = poi_data.get("open_time", "")
        if isinstance(open_time_value, list):
            open_time_value = ""
        
        opentime2_value = poi_data.get("opentime2", "")
        if isinstance(opentime2_value, list):
            opentime2_value = ""
        
        return cls(
            name=poi_data.get("name", ""),
            address=poi_data.get("address", ""),
            location=location,
            poi_id=poi_data.get("id", ""),
            city=poi_data.get("city", ""),
            type=poi_data.get("type", ""),
            rating=rating,
            open_time=open_time_value,
            opentime2=opentime2_value,
            business_area=business_area_str,
            level=level_str,
            ticket_price=ticket_price,
        )


class Meal(BaseModel):
    """餐饮信息"""
    
    type: str = Field(..., description="餐饮类型: breakfast/lunch/dinner/snack")
    name: str = Field(..., description="餐饮名称")
    address: Optional[str] = Field(default=None, description="地址")
    location: Optional[Location] = Field(default=None, description="经纬度坐标")
    description: Optional[str] = Field(default=None, description="描述")
    estimated_cost: int = Field(default=0, description="预估费用(元)")


class Hotel(BaseModel):
    """酒店信息"""

    name: str = Field(..., description="酒店名称")
    poi_id: str = Field(default="", description="POI唯一标识符")
    address: str = Field(default="", description="酒店地址")
    location: Optional[Location] = Field(default=None, description="酒店位置(经纬度)")
    business_area: str = Field(default="", description="所属商圈")
    city: str = Field(default="", description="所在城市")
    rating: Optional[float] = Field(default=None, description="酒店评分")
    hotel_type: str = Field(default="", description="酒店类型")
    hotel_ordering: int = Field(default=0, description="酒店排序优先级")
    lowest_price: Optional[int] = Field(default=None, description="最低价格(元/晚)")
    distance: str = Field(default="", description="距离景点距离")

    @classmethod
    def from_poi_detail(cls, poi_data: dict) -> "Hotel":
        """
        从 maps_search_detail 工具返回的POI数据创建Hotel实例。
        
        Args:
            poi_data: 工具返回的POI详情数据，格式如：
                {
                    "id": "B0L04SXNTP",
                    "name": "北京艺栈青年酒店",
                    "location": "116.458589,39.950448",
                    "address": "新源南路甲3号",
                    "business_area": "燕莎",
                    "city": "北京市",
                    "type": "住宿服务;宾馆酒店;宾馆酒店",
                    "rating": "4.8",
                    "hotel_ordering": "1"
                }
        
        Returns:
            Hotel实例
        """
        # 解析经纬度
        location = None
        if "location" in poi_data and poi_data["location"]:
            try:
                lon, lat = poi_data["location"].split(",")
                location = Location(
                    longitude=float(lon),
                    latitude=float(lat)
                )
            except (ValueError, AttributeError):
                pass
        
        # 解析评分
        rating = None
        if "rating" in poi_data and poi_data["rating"]:
            try:
                rating = float(poi_data["rating"])
            except (ValueError, TypeError):
                pass
        
        # 解析排序
        hotel_ordering = 0
        if "hotel_ordering" in poi_data and poi_data["hotel_ordering"]:
            try:
                hotel_ordering = int(poi_data["hotel_ordering"])
            except (ValueError, TypeError):
                pass
        
        # 解析最低价格
        lowest_price = None
        if "lowest_price" in poi_data and poi_data["lowest_price"]:
            try:
                lowest_price = int(poi_data["lowest_price"])
            except (ValueError, TypeError):
                pass
        
        # 处理可能为空列表的字段
        business_area_value = poi_data.get("business_area", "")
        if isinstance(business_area_value, list):
            business_area_value = business_area_value[0] if business_area_value else ""
        
        return cls(
            name=poi_data.get("name", ""),
            poi_id=poi_data.get("id", ""),
            address=poi_data.get("address", ""),
            location=location,
            business_area=business_area_value,
            city=poi_data.get("city", ""),
            rating=rating,
            hotel_type=poi_data.get("type", ""),
            hotel_ordering=hotel_ordering,
            lowest_price=lowest_price,
        )


class Budget(BaseModel):
    """预算信息"""
    
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: int = Field(default=0, description="酒店总费用")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_transportation: int = Field(default=0, description="交通总费用")
    total: int = Field(default=0, description="总费用")


class DayPlan(BaseModel):
    """单日行程"""
    
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="第几天(从0开始)")
    description: str = Field(..., description="当日行程描述")
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: List[Attraction] = Field(default=[], description="景点列表")
    meals: List[Meal] = Field(default=[], description="餐饮列表")
