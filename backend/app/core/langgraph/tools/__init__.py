"""LangGraph 工具集，用于增强语言模型能力。

本包包含可与 LangGraph 配合使用的自定义工具，以扩展
语言模型的功能。提供工具注册和权限控制功能。

核心功能：
- 工具分类管理（基础工具集、专属工具集）
- 智能体权限控制
- 动态工具注册与发现

使用示例：
    from app.core.langgraph.tools import ToolRegistry, AgentType
    
    # 获取智能体可用的工具
    tools = ToolRegistry.get_agent_tools(AgentType.WEATHER)
"""

from typing import Optional
from langchain_core.tools.base import BaseTool

from .local import local_tools
from .mcp import (
    get_mcp_tools,
    get_mcp_tools_async,
    get_mcp_tool_names,
    get_amap_service,
    AmapService,
    print_mcp_tools_info,
    # 工具分类系统
    MCPToolCategory,
    get_tools_by_category,
    get_attraction_tools,
    get_hotel_tools,
    get_route_planning_tools,
    get_weather_tools,
    get_geocoding_tools,
    print_tool_categories_info,
)

tools: list[BaseTool] = local_tools

_mcp_tools_cache: Optional[list[BaseTool]] = None


def get_all_mcp_tools() -> list[BaseTool]:
    """延迟加载 MCP 工具，避免模块导入时的事件循环冲突"""
    global _mcp_tools_cache
    if _mcp_tools_cache is None:
        _mcp_tools_cache = get_mcp_tools()
    return _mcp_tools_cache


mcp_tools: list[BaseTool] = []

all_tools: list[BaseTool] = local_tools

__all__ = [
    # 工具列表
    "tools",
    "local_tools",
    "mcp_tools",
    "all_tools",
    "get_all_mcp_tools",
    # MCP 工具
    "get_mcp_tools",
    "get_mcp_tools_async",
    "get_mcp_tool_names",
    "get_amap_service",
    "AmapService",
    "print_mcp_tools_info",
    # 工具分类系统
    "MCPToolCategory",
    "get_tools_by_category",
    "get_attraction_tools",
    "get_hotel_tools",
    "get_route_planning_tools",
    "get_weather_tools",
    "get_geocoding_tools",
    "print_tool_categories_info",
]
