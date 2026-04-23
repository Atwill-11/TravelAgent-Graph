"""MCP 工具模块。

本包封装基于 langchain-mcp-adapters 的 MCP 服务工具，
提供统一的工具导出接口，可直接用于 LangGraph Agent。

使用示例：
    from app.core.langgraph.tools.mcp import get_mcp_tools, get_amap_service
    
    # 获取工具列表（用于 Agent）
    tools = get_mcp_tools()
    
    # 获取服务实例（用于直接调用）
    service = get_amap_service()
    pois = service.search_poi("餐厅", "北京")

┌─────────────────────────────────────────────────────────────┐
│                    MCP 工具分类系统                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐                 │
│  │ 景点搜索工具集   │  │ 酒店推荐工具集   │                 │
│  ├─────────────────┤  ├─────────────────┤                 │
│  │ • maps_text_    │  │ • maps_text_    │                 │
│  │   search        │  │   search        │                 │
│  │ • maps_around_  │  │ • maps_around_  │                 │
│  │   search        │  │   search        │                 │
│  │ • maps_search_  │  │ • maps_search_  │                 │
│  │   detail        │  │   detail        │                 │
│  │ • maps_geo      │  │ • maps_geo      │                 │
│  │ • maps_regeocode│  │ • maps_regeocode│                 │
│  └─────────────────┘  └─────────────────┘                 │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐                 │
│  │ 路径规划工具集   │  │ 天气查询工具集   │                 │
│  ├─────────────────┤  ├─────────────────┤                 │
│  │ • maps_direction│  │ • maps_weather  │                 │
│  │   _bicycling    │  │                 │                 │
│  │ • maps_direction│  └─────────────────┘                 │
│  │   _walking      │                                      │
│  │ • maps_direction│  ┌─────────────────┐                 │
│  │   _driving      │  │ 地理编码工具集   │                 │
│  │ • maps_direction│  ├─────────────────┤                 │
│  │   _transit      │  │ • maps_geo      │                 │
│  │ • maps_distance │  │ • maps_regeocode│                 │
│  │ • maps_geo      │  │ • maps_ip_      │                 │
│  │ • maps_regeocode│  │   location      │                 │
│  └─────────────────┘  └─────────────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
"""

from .amap_server import (
    AmapService,
    MCPToolItem,
    MCPToolSet,
    get_amap_service,
    get_mcp_tools,
    get_mcp_tools_async,
    get_mcp_tool_names,
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

__all__ = [
    # 服务类
    "AmapService",
    "MCPToolItem",
    "MCPToolSet",
    # 基础工具获取
    "get_amap_service",
    "get_mcp_tools",
    "get_mcp_tools_async",
    "get_mcp_tool_names",
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