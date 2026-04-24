"""本包包含用于生成智能体提示的函数。"""

from .attraction import ATTRACTION_AGENT_PROMPT
from .hotel import HOTEL_AGENT_PROMPT
from .weather import WEATHER_AGENT_PROMPT
from .travel import (
    PLAN_MODEL_PROMPT,
    SUMMARY_PROMPT,
)

__all__ = [
    "ATTRACTION_AGENT_PROMPT",
    "HOTEL_AGENT_PROMPT",
    "WEATHER_AGENT_PROMPT",
    "PLAN_MODEL_PROMPT",
    "SUMMARY_PROMPT",
]
