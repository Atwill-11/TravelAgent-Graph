"""LangGraph 本地配置工具集，用于增强语言模型能力。

本包包含可与 LangGraph 配合使用的自定义工具，以扩展
语言模型的功能。目前包含网络搜索、天气查询等工具。
"""

from langchain_core.tools.base import BaseTool

from .weather_tool import weather_tools

local_tools: list[BaseTool] = [*weather_tools]

__all__ = [
    "weather_tools",
    "local_tools",
]