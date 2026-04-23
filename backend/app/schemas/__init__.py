"""API数据传输对象层（DTO）"""

from app.schemas.auth import Token
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Message,
    StreamResponse,
)
from app.schemas.common import Location
from app.schemas.agent import (
    AgentContext,
    TravelContext,
    CustomAgentState,
    TaskItem,
    SubAgentResult,
    TravelPlannerState,
    TravelPlannerOutput,
)
from app.schemas.travel import (
    TripRequest,
    POISearchRequest,
    RouteRequest,
    Attraction,
    Meal,
    Hotel,
    Budget,
    DayPlan,
    TripPlan,
    TripPlanResponse,
)
from app.schemas.weather import (
    LocationInfo,
    QWeatherInfo,
    AirQualityInfo,
    TravelWeatherData,
    AmapWeatherInfo,
    POIInfo,
)

__all__ = [
    "Token",
    "ChatRequest",
    "ChatResponse",
    "Message",
    "StreamResponse",
    "Location",
    "AgentContext",
    "TravelContext",
    "CustomAgentState",
    "TaskItem",
    "SubAgentResult",
    "TravelPlannerState",
    "TravelPlannerOutput",
    "TripRequest",
    "POISearchRequest",
    "RouteRequest",
    "Attraction",
    "Meal",
    "Hotel",
    "Budget",
    "DayPlan",
    "TripPlan",
    "TripPlanResponse",
    "LocationInfo",
    "QWeatherInfo",
    "AirQualityInfo",
    "TravelWeatherData",
    "AmapWeatherInfo",
    "POIInfo",
]
