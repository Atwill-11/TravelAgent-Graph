"""高德地图MCP服务封装（基于 langchain-mcp-adapters）"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import asyncio
import json
import re

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import settings
from app.schemas.common import Location
from app.schemas.weather import POIInfo, AmapWeatherInfo


# ========== 轻量 Tool 容器（用于按名称查 & 调用） ==========

class MCPToolItem:
    """
    简易工具包装，用于按名字从 client.get_tools() 中查找并调用。
    实际项目中可以直接使用 LangChain Tool 对象；这里做一层薄封装。
    """
    def __init__(self, name: str, tool: Any):
        self.name = name
        self._tool = tool

    @property
    def description(self) -> str:
        return getattr(self._tool, "description", "")

    async def ainvoke(self, arguments: Dict[str, Any]) -> Any:
        """
        统一调用入口，兼容大多数 LangChain Tool 实现。
        """
        return await self._tool.ainvoke(arguments)


class MCPToolSet:
    """从 MultiServerMCPClient.get_tools() 构建的工具集合，支持按名称/前缀查找。"""
    def __init__(self, tools: List[Any]):
        self._tools: List[MCPToolItem] = []
        for t in tools:
            name = getattr(t, "name", None) or getattr(t, "get_name", lambda: None)()
            if not name:
                continue
            self._tools.append(MCPToolItem(name=name, tool=t))

    def get(self, name: str) -> Optional[MCPToolItem]:
        return next((i for i in self._tools if i.name == name), None)

    def list_names(self) -> List[str]:
        return [i.name for i in self._tools]


# ========== 工厂函数：创建 MultiServerMCPClient（单例） ==========

_amap_mcp_client: Optional[MultiServerMCPClient] = None
_amap_tools: Optional[MCPToolSet] = None


async def _init_amap_client_and_tools(
    *,
    server_command: List[str],
    env: Dict[str, str],
    tool_name_prefix: bool = False,
) -> MultiServerMCPClient:
    """
    内部实现：
    - server_command：如 ["uvx", "amap-mcp-server"]，会拆分成 command 与 args。
    - env：传递给子进程的环境变量（如 {"AMAP_MAPS_API_KEY": "xxx"}）。
    - tool_name_prefix：是否给工具名加上“服务名_”前缀，防止同名冲突。
    """
    # 将 server_command 拆解为 command + args（与 StdioConnection 对齐）
    command = server_command[0]
    args = server_command[1:] if len(server_command) > 1 else []

    # 创建客户端（stdio 配置见官方文档示例）<span data-allow-html class='source-item source-aggregated' data-group-key='source-group-1' data-url='https://docs.langchain.com/oss/python/langchain/mcp' data-id='turn0fetch0'><span data-allow-html class='source-item-num' data-group-key='source-group-1' data-id='turn0fetch0' data-url='https://docs.langchain.com/oss/python/langchain/mcp'><span class='source-item-num-name' data-allow-html>langchain.com</span><span data-allow-html class='source-item-num-count'>+1</span></span></span>
    client = MultiServerMCPClient(
        connections={
            "amap": {
                "transport": "stdio",
                "command": command,
                "args": args,
                "env": env,            # 将高德 API Key 注入为子进程环境变量
            }
        },
        tool_name_prefix=tool_name_prefix,  # 可选，避免与其他 MCP 工具同名
    )
    # 预加载工具列表（LangChain Tool 实例列表）
    tools = await client.get_tools()  # 返回 LangChain Tool 列表<span data-allow-html class='source-item source-aggregated' data-group-key='source-group-4' data-url='https://docs.langchain.com/oss/python/langchain/mcp' data-id='turn2find1'><span data-allow-html class='source-item-num' data-group-key='source-group-4' data-id='turn2find1' data-url='https://docs.langchain.com/oss/python/langchain/mcp'><span class='source-item-num-name' data-allow-html>langchain.com</span><span data-allow-html class='source-item-num-count'></span></span></span>
    return client, tools


def _get_client_and_tools() -> tuple[MultiServerMCPClient, MCPToolSet]:
    """
    延迟初始化并缓存 client 与工具集合。
    使用线程池来避免事件循环冲突问题。
    """
    global _amap_mcp_client, _amap_tools
    if _amap_mcp_client is not None and _amap_tools is not None:
        return _amap_mcp_client, _amap_tools

    amap_api_key = settings.AMAP_API_KEY

    if not amap_api_key:
        raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")

    import concurrent.futures

    def run_async_init():
        return asyncio.run(
            _init_amap_client_and_tools(
                server_command=["uvx", "amap-mcp-server"],
                env={"AMAP_MAPS_API_KEY": amap_api_key},
                tool_name_prefix=False,
            )
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_async_init)
        client, tools = future.result()

    _amap_tools = MCPToolSet(tools)

    print("✅ 高德地图MCP客户端初始化成功（基于 MultiServerMCPClient）")
    print(f"  工具数量: {len(_amap_tools.list_names())}")
    if _amap_tools.list_names():
        print("  可用工具:")
        for name in _amap_tools.list_names():
            print(f"  - {name}")

    _amap_mcp_client = client
    return _amap_mcp_client, _amap_tools


# ========== 服务封装类 ==========

def _run_sync(coro):
    """在非异步上下文中同步运行协程的简单封装，使用线程池避免事件循环冲突"""
    import concurrent.futures

    def run_in_thread():
        return asyncio.run(coro)

    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


class AmapService:
    """高德地图服务封装类（适配 langchain-mcp-adapters）"""

    def __init__(self):
        """初始化服务（延迟初始化 client 与 tools）"""
        # 仅缓存，真正初始化在首次调用时触发
        self._client: Optional[MultiServerMCPClient] = None
        self._tools: Optional[MCPToolSet] = None

    def _ensure(self):
        """首次调用时完成初始化"""
        if self._client is None or self._tools is None:
            self._client, self._tools = _get_client_and_tools()

    # ------ POI 搜索 ------

    def search_poi(
        self,
        keywords: str,
        city: str,
        citylimit: bool = True,
    ) -> List["POIInfo"]:
        """
        搜索POI。
        映射关系：调用 MCP 工具 maps_text_search（与你原来保持一致）。
        """
        self._ensure()
        tool_name = "maps_text_search"
        t = self._tools.get(tool_name)
        if t is None:
            print(f"❌ 未找到工具: {tool_name}，可用工具: {self._tools.list_names()}")
            return []

        try:
            result = _run_sync(
                t.ainvoke({
                    "keywords": keywords,
                    "city": city,
                    "citylimit": str(citylimit).lower(),
                })
            )
            # TODO: 按 amap-mcp-server 的实际返回格式做解析
            # 伪代码示意：
            # data = json.loads(result) if isinstance(result, str) else result
            # pois = data.get("pois", [])
            # return [POIInfo(**p) for p in pois]
            print(f"POI搜索结果: {str(result)[:200]}...")
            return []
        except Exception as e:
            print(f"❌ POI搜索失败: {str(e)}")
            return []

    # ------ 天气查询 ------

    def get_weather(self, city: str) -> List["AmapWeatherInfo"]:
        """查询天气。调用 MCP 工具 maps_weather。"""
        self._ensure()
        tool_name = "maps_weather"
        t = self._tools.get(tool_name)
        if t is None:
            print(f"❌ 未找到工具: {tool_name}")
            return []

        try:
            result = _run_sync(t.ainvoke({"city": city}))
            print(f"天气查询结果: {str(result)[:200]}...")
            # TODO: 解析并映射为 AmapWeatherInfo 列表
            return []
        except Exception as e:
            print(f"❌ 天气查询失败: {str(e)}")
            return []

    # ------ 路线规划 ------

    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking",
    ) -> Dict[str, Any]:
        """
        路线规划。
        - walking -> maps_direction_walking_by_address
        - driving -> maps_direction_driving_by_address
        - transit -> maps_direction_transit_integrated_by_address
        """
        self._ensure()
        tool_map = {
            "walking": "maps_direction_walking_by_address",
            "driving": "maps_direction_driving_by_address",
            "transit": "maps_direction_transit_integrated_by_address",
        }
        tool_name = tool_map.get(route_type, "maps_direction_walking_by_address")
        t = self._tools.get(tool_name)
        if t is None:
            print(f"❌ 未找到工具: {tool_name}")
            return {}

        try:
            arguments: Dict[str, Any] = {
                "origin_address": origin_address,
                "destination_address": destination_address,
            }
            if origin_city:
                arguments["origin_city"] = origin_city
            if destination_city:
                arguments["destination_city"] = destination_city

            result = _run_sync(t.ainvoke(arguments))
            print(f"路线规划结果: {str(result)[:200]}...")
            # TODO: 解析为统一结构 { distance, duration, route_type, description }
            return {}
        except Exception as e:
            print(f"❌ 路线规划失败: {str(e)}")
            return {}

    # ------ 地理编码 ------

    def geocode(
        self,
        address: str,
        city: Optional[str] = None,
    ) -> Optional["Location"]:
        """地理编码（地址->坐标）。调用 maps_geo。"""
        self._ensure()
        tool_name = "maps_geo"
        t = self._tools.get(tool_name)
        if t is None:
            print(f"❌ 未找到工具: {tool_name}")
            return None

        try:
            arguments: Dict[str, Any] = {"address": address}
            if city:
                arguments["city"] = city
            result = _run_sync(t.ainvoke(arguments))
            print(f"地理编码结果: {str(result)[:200]}...")
            # TODO: 解析出 Location(longitude=..., latitude=...)
            return None
        except Exception as e:
            print(f"❌ 地理编码失败: {str(e)}")
            return None

    # ------ POI 详情 ------

    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        """获取POI详情。调用 maps_search_detail。"""
        self._ensure()
        tool_name = "maps_search_detail"
        t = self._tools.get(tool_name)
        if t is None:
            print(f"❌ 未找到工具: {tool_name}")
            return {}

        try:
            result = _run_sync(t.ainvoke({"id": poi_id}))
            # 兼容你原来的 JSON 提取逻辑
            if isinstance(result, str):
                json_match = re.search(r"\{.*\}", result, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            return {"raw": result}
        except Exception as e:
            print(f"❌ 获取POI详情失败: {str(e)}")
            return {}


# ========== 全局单例（与原风格一致） ==========

_amap_service: Optional[AmapService] = None


def get_amap_service() -> AmapService:
    """获取高德地图服务实例（单例模式）"""
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service


# ========== 工具列表导出（用于 LangGraph Agent） ==========

async def get_mcp_tools_async() -> List[Any]:
    """
    异步获取 MCP 工具列表（LangChain Tool 对象列表）。
    
    Returns:
        List[BaseTool]: LangChain Tool 实例列表，可直接用于 LangGraph Agent。
    
    使用示例:
        tools = await get_mcp_tools_async()
        agent = create_react_agent(llm, tools)
    """
    global _amap_mcp_client, _amap_tools
    
    if _amap_tools is None:
        amap_api_key = settings.AMAP_API_KEY
        if not amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        
        client, tools = await _init_amap_client_and_tools(
            server_command=["uvx", "amap-mcp-server"],
            env={"AMAP_MAPS_API_KEY": amap_api_key},
            tool_name_prefix=False,
        )
        _amap_mcp_client = client
        _amap_tools = MCPToolSet(tools)
        
        print("✅ 高德地图MCP客户端初始化成功")
        print(f"  工具数量: {len(_amap_tools.list_names())}")
    
    return [t._tool for t in _amap_tools._tools]


def get_mcp_tools() -> List[Any]:
    """
    同步获取 MCP 工具列表（LangChain Tool 对象列表）。
    
    Returns:
        List[BaseTool]: LangChain Tool 实例列表，可直接用于 LangGraph Agent。
    
    使用示例:
        tools = get_mcp_tools()
        agent = create_react_agent(llm, tools)
    """
    _, toolset = _get_client_and_tools()
    return [t._tool for t in toolset._tools]


def get_mcp_tool_names() -> List[str]:
    """
    获取 MCP 工具名称列表。
    
    Returns:
        List[str]: 工具名称列表。
    """
    _, toolset = _get_client_and_tools()
    return toolset.list_names()


def print_mcp_tools_info(verbose: bool = False) -> None:
    """
    打印所有 MCP 工具的详细信息（名称、描述、参数 schema）。
    用于调试和验证工具是否正确加载。
    
    Args:
        verbose: 是否打印完整的 schema 字典（用于调试）
    """
    import json
    
    _, toolset = _get_client_and_tools()
    
    print("\n" + "="*60)
    print("📋 MCP 工具详细信息")
    print("="*60)
    
    for tool_item in toolset._tools:
        tool = tool_item._tool
        name = getattr(tool, "name", "未知")
        description = getattr(tool, "description", "无描述")
        
        print(f"\n🔧 工具名称: {name}")
        print(f"   描述: {description[:100]}..." if len(description) > 100 else f"   描述: {description}")
        
        args_schema = getattr(tool, "args_schema", None)
        if args_schema:
            # 兼容两种情况：args_schema 可能是字典或 Pydantic 模型
            if isinstance(args_schema, dict):
                schema = args_schema
            else:
                schema = args_schema.schema() if hasattr(args_schema, "schema") else {}
            
            if verbose:
                print(f"   完整 Schema:")
                print(f"   {json.dumps(schema, ensure_ascii=False, indent=6)}")
            else:
                properties = schema.get("properties", {})
                required = schema.get("required", [])
                if properties:
                    print(f"   参数:")
                    for param_name, param_info in properties.items():
                        req_mark = "*" if param_name in required else " "
                        param_desc = param_info.get("description", "无描述")
                        param_type = param_info.get("type", "any")
                        print(f"     [{req_mark}] {param_name} ({param_type}): {param_desc[:50]}..." if len(param_desc) > 50 else f"     [{req_mark}] {param_name} ({param_type}): {param_desc}")
                else:
                    print("   参数: 无参数定义")
        else:
            print("   参数: 无参数 schema")
    
    print("\n" + "="*60)


# ========== 工具分类系统（用于不同子智能体） ==========

class MCPToolCategory:
    """MCP 工具分类常量"""
    
    # 景点搜索工具集
    ATTRACTION_TOOLS = [
        "maps_text_search",        # 关键词搜索 POI
        "maps_around_search",      # 周边搜索
        "maps_search_detail",      # POI 详情
        "maps_geo",                # 地理编码（地址→坐标）
        "maps_regeocode",          # 逆地理编码（坐标→地址）
    ]
    
    # 酒店推荐工具集
    HOTEL_TOOLS = [
        "maps_text_search",        # 关键词搜索 POI
        "maps_around_search",      # 周边搜索
        "maps_search_detail",      # POI 详情
        "maps_geo",                # 地理编码
        "maps_regeocode",          # 逆地理编码
    ]
    
    # 路径规划工具集
    ROUTE_PLANNING_TOOLS = [
        "maps_direction_bicycling",                    # 骑行路径规划
        "maps_direction_walking",                      # 步行路径规划
        "maps_direction_driving",                      # 驾车路径规划
        "maps_direction_transit_integrated",           # 公交路径规划
        "maps_direction_walking_by_address",           # 通过地址规划步行路线
        "maps_direction_driving_by_address",           # 通过地址规划驾车路线
        "maps_direction_transit_integrated_by_address", # 通过地址规划公交路线
        "maps_distance",                               # 距离测量
        "maps_geo",                                    # 地理编码
        "maps_regeocode",                              # 逆地理编码
    ]
    
    # 天气查询工具集
    WEATHER_TOOLS = [
        "maps_weather",            # 天气查询
    ]
    
    # 地理编码工具集（通用）
    GEOCODING_TOOLS = [
        "maps_geo",                # 地理编码
        "maps_regeocode",          # 逆地理编码
        "maps_ip_location",        # IP定位
    ]
    
    # 完整工具集（所有工具）
    ALL_TOOLS = None  # None 表示获取所有工具


def get_tools_by_category(category: List[str]) -> List[Any]:
    """
    根据工具名称列表获取对应的 LangChain Tool 对象。
    
    Args:
        category: 工具名称列表，如 MCPToolCategory.ATTRACTION_TOOLS
        
    Returns:
        List[BaseTool]: LangChain Tool 实例列表
        
    使用示例:
        tools = get_tools_by_category(MCPToolCategory.ATTRACTION_TOOLS)
        agent = create_agent(model, tools=tools)
    """
    _, toolset = _get_client_and_tools()
    
    if category is None:
        return [t._tool for t in toolset._tools]
    
    tools = []
    for tool_name in category:
        tool_item = toolset.get(tool_name)
        if tool_item:
            tools.append(tool_item._tool)
        else:
            print(f"⚠️ 工具 '{tool_name}' 不存在，已跳过")
    
    return tools


from langchain_core.tools import tool

@tool
async def search_attractions_with_details(
    keywords: str,
    city: str,
    citylimit: bool = True,
    max_details: int = 10
) -> str:
    """
    搜索景点并自动获取详细信息。这是一个组合工具，会自动：
    1. 使用 maps_text_search 搜索景点
    2. 对每个景点调用 maps_search_detail 获取详情
    3. 返回包含详细信息的景点列表
    
    **关键词选择原则：**
    高德地图POI搜索需要使用具体的地点类型词，不支持抽象概念词。
    
    关键词应该是具体的POI类型，例如：博物馆、公园、景点、寺庙、古镇、美术馆等。
    避免使用抽象概念，例如：历史文化、好玩的地方、适合拍照等。
    
    **示例：**
    - 用户说"想看博物馆" → keywords="博物馆"
    - 用户说"历史文化景点" → keywords="景点" 或 "名胜古迹"
    - 用户说"自然风光" → keywords="公园" 或 "山"
    - 用户说"亲子游" → keywords="游乐园" 或 "公园"
    - 用户说"艺术相关" → keywords="美术馆" 或 "博物馆"
    
    Args:
        keywords: 搜索关键词（具体的POI类型词）
        city: 城市名称，如'北京'、'上海'
        citylimit: 是否限制在城市内搜索，默认为 True
        max_details: 最多获取多少个景点的详情，默认为 10
    
    Returns:
        str: 包含详细信息的景点列表（JSON 格式）
    """
    global _amap_tools
    
    if _amap_tools is None:
        _get_client_and_tools()
    
    text_search_tool = _amap_tools.get("maps_text_search")
    detail_tool = _amap_tools.get("maps_search_detail")
    
    if not text_search_tool or not detail_tool:
        return json.dumps({"error": "工具未初始化"}, ensure_ascii=False)
    
    try:
        search_result = await text_search_tool.ainvoke({
            "keywords": keywords,
            "city": city,
            "citylimit": str(citylimit).lower(),
        })
        
        search_data = {"pois": []}
        
        if isinstance(search_result, list) and len(search_result) > 0:
            first_item = search_result[0]
            if isinstance(first_item, dict) and "text" in first_item:
                text_value = first_item["text"]
                if isinstance(text_value, str):
                    try:
                        search_data = json.loads(text_value)
                    except json.JSONDecodeError:
                        pass
                elif isinstance(text_value, dict):
                    search_data = text_value
        elif isinstance(search_result, str):
            json_match = re.search(r'\{.*\}', search_result, re.DOTALL)
            if json_match:
                search_data = json.loads(json_match.group())
        elif isinstance(search_result, dict):
            search_data = search_result
        
        pois = search_data.get("pois", [])
        
        if not pois:
            return json.dumps({"message": f"未找到匹配'{keywords}'的景点", "pois": []}, ensure_ascii=False)
        
        limited_pois = pois[:max_details]
        
        # 使用信号量限制并发请求数，避免API限流
        semaphore = asyncio.Semaphore(2)
        
        async def fetch_detail_with_limit(poi_id):
            async with semaphore:
                return await detail_tool.ainvoke({"id": poi_id})
        
        tasks = []
        for poi in limited_pois:
            if poi.get("id"):
                tasks.append(fetch_detail_with_limit(poi["id"]))
        
        detailed_pois = []
        if tasks:
            detail_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, (poi, detail_result) in enumerate(zip(limited_pois, detail_results)):
                detailed_poi = dict(poi)
                
                if isinstance(detail_result, Exception):
                    detailed_poi["detail_error"] = str(detail_result)
                else:
                    try:
                        detail_data = {}
                        if isinstance(detail_result, list) and len(detail_result) > 0:
                            first_item = detail_result[0]
                            if isinstance(first_item, dict) and "text" in first_item:
                                text_value = first_item["text"]
                                if isinstance(text_value, str):
                                    try:
                                        detail_data = json.loads(text_value)
                                    except json.JSONDecodeError:
                                        pass
                                elif isinstance(text_value, dict):
                                    detail_data = text_value
                        elif isinstance(detail_result, str):
                            detail_match = re.search(r'\{.*\}', detail_result, re.DOTALL)
                            detail_data = json.loads(detail_match.group()) if detail_match else {}
                        elif isinstance(detail_result, dict):
                            detail_data = detail_result
                        detailed_poi["detail"] = detail_data
                    except Exception as e:
                        detailed_poi["detail_parse_error"] = str(e)
                
                detailed_pois.append(detailed_poi)
        else:
            detailed_pois = limited_pois
        
        return json.dumps({
            "total": len(pois),
            "returned": len(detailed_pois),
            "pois": detailed_pois
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"搜索失败: {str(e)}"}, ensure_ascii=False)


@tool
async def search_hotels_with_details(
    keywords: str,
    city: str,
    citylimit: bool = True,
    max_details: int = 10
) -> str:
    """
    搜索酒店并自动获取详细信息。这是一个组合工具，会自动：
    1. 使用 maps_text_search 搜索酒店
    2. 对每个酒店调用 maps_search_detail 获取详情
    3. 返回包含详细信息的酒店列表
    
    **关键词选择原则：**
    搜索酒店时，关键词通常使用"酒店"、"宾馆"、"住宿"等。
    
    **示例：**
    - 搜索北京酒店 → keywords="酒店", city="北京"
    - 搜索上海宾馆 → keywords="宾馆", city="上海"
    - 搜索经济型酒店 → keywords="经济型酒店", city="广州"
    
    Args:
        keywords: 搜索关键词（如"酒店"、"宾馆"）
        city: 城市名称，如'北京'、'上海'
        citylimit: 是否限制在城市内搜索，默认为 True
        max_details: 最多获取多少个酒店的详情，默认为 10
    
    Returns:
        str: 包含详细信息的酒店列表（JSON 格式）
    """
    global _amap_tools
    
    if _amap_tools is None:
        _get_client_and_tools()
    
    text_search_tool = _amap_tools.get("maps_text_search")
    detail_tool = _amap_tools.get("maps_search_detail")
    
    if not text_search_tool or not detail_tool:
        return json.dumps({"error": "工具未初始化"}, ensure_ascii=False)
    
    try:
        search_result = await text_search_tool.ainvoke({
            "keywords": keywords,
            "city": city,
            "citylimit": str(citylimit).lower(),
        })
        
        search_data = {"pois": []}
        
        if isinstance(search_result, list) and len(search_result) > 0:
            first_item = search_result[0]
            if isinstance(first_item, dict) and "text" in first_item:
                text_value = first_item["text"]
                if isinstance(text_value, str):
                    try:
                        search_data = json.loads(text_value)
                    except json.JSONDecodeError:
                        pass
                elif isinstance(text_value, dict):
                    search_data = text_value
        elif isinstance(search_result, str):
            json_match = re.search(r'\{.*\}', search_result, re.DOTALL)
            if json_match:
                search_data = json.loads(json_match.group())
        elif isinstance(search_result, dict):
            search_data = search_result
        
        pois = search_data.get("pois", [])
        
        if not pois:
            return json.dumps({"message": f"未找到匹配'{keywords}'的酒店", "pois": []}, ensure_ascii=False)
        
        limited_pois = pois[:max_details]
        
        # 使用信号量限制并发请求数，避免API限流
        semaphore = asyncio.Semaphore(1)
        
        async def fetch_detail_with_limit(poi_id):
            async with semaphore:
                return await detail_tool.ainvoke({"id": poi_id})
        
        tasks = []
        for poi in limited_pois:
            if poi.get("id"):
                tasks.append(fetch_detail_with_limit(poi["id"]))
        
        detailed_pois = []
        if tasks:
            detail_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, (poi, detail_result) in enumerate(zip(limited_pois, detail_results)):
                detailed_poi = dict(poi)
                
                if isinstance(detail_result, Exception):
                    detailed_poi["detail_error"] = str(detail_result)
                else:
                    try:
                        detail_data = {}
                        if isinstance(detail_result, list) and len(detail_result) > 0:
                            first_item = detail_result[0]
                            if isinstance(first_item, dict) and "text" in first_item:
                                text_value = first_item["text"]
                                if isinstance(text_value, str):
                                    try:
                                        detail_data = json.loads(text_value)
                                    except json.JSONDecodeError:
                                        pass
                                elif isinstance(text_value, dict):
                                    detail_data = text_value
                        elif isinstance(detail_result, str):
                            detail_match = re.search(r'\{.*\}', detail_result, re.DOTALL)
                            detail_data = json.loads(detail_match.group()) if detail_match else {}
                        elif isinstance(detail_result, dict):
                            detail_data = detail_result
                        detailed_poi["detail"] = detail_data
                    except Exception as e:
                        detailed_poi["detail_parse_error"] = str(e)
                
                detailed_pois.append(detailed_poi)
        else:
            detailed_pois = limited_pois
        
        return json.dumps({
            "total": len(pois),
            "returned": len(detailed_pois),
            "pois": detailed_pois
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"搜索失败: {str(e)}"}, ensure_ascii=False)


def get_attraction_tools() -> List[Any]:
    """
    获取景点搜索子智能体专用工具集。
    
    包含工具:
    - search_attractions_with_details: 搜索景点并自动获取详情（推荐使用）
    - maps_text_search: 关键词搜索 POI
    - maps_around_search: 周边搜索
    - maps_search_detail: POI 详情
    - maps_geo: 地理编码
    - maps_regeocode: 逆地理编码
    
    Returns:
        List[BaseTool]: 景点搜索工具列表
    """
    base_tools = get_tools_by_category(MCPToolCategory.ATTRACTION_TOOLS)
    base_tools.append(search_attractions_with_details)
    return base_tools


def get_hotel_tools() -> List[Any]:
    """
    获取酒店推荐子智能体专用工具集。
    
    包含工具:
    - search_hotels_with_details: 搜索酒店并自动获取详情（推荐使用）
    - maps_text_search: 关键词搜索 POI
    - maps_around_search: 周边搜索
    - maps_search_detail: POI 详情
    - maps_geo: 地理编码
    - maps_regeocode: 逆地理编码
    
    Returns:
        List[BaseTool]: 酒店推荐工具列表
    """
    base_tools = get_tools_by_category(MCPToolCategory.HOTEL_TOOLS)
    base_tools.append(search_hotels_with_details)
    return base_tools


def get_route_planning_tools() -> List[Any]:
    """
    获取路径规划子智能体专用工具集。
    
    包含工具:
    - maps_direction_bicycling: 骑行路径规划
    - maps_direction_walking: 步行路径规划
    - maps_direction_driving: 驾车路径规划
    - maps_direction_transit_integrated: 公交路径规划
    - maps_direction_*_by_address: 通过地址规划路线
    - maps_distance: 距离测量
    - maps_geo: 地理编码
    - maps_regeocode: 逆地理编码
    
    Returns:
        List[BaseTool]: 路径规划工具列表
    """
    return get_tools_by_category(MCPToolCategory.ROUTE_PLANNING_TOOLS)


def get_weather_tools() -> List[Any]:
    """
    获取天气查询子智能体专用工具集。
    
    包含工具:
    - maps_weather: 天气查询
    
    Returns:
        List[BaseTool]: 天气查询工具列表
    """
    return get_tools_by_category(MCPToolCategory.WEATHER_TOOLS)


def get_geocoding_tools() -> List[Any]:
    """
    获取地理编码工具集（通用）。
    
    包含工具:
    - maps_geo: 地理编码
    - maps_regeocode: 逆地理编码
    - maps_ip_location: IP定位
    
    Returns:
        List[BaseTool]: 地理编码工具列表
    """
    return get_tools_by_category(MCPToolCategory.GEOCODING_TOOLS)


def print_tool_categories_info() -> None:
    """
    打印所有工具分类的信息，用于调试和验证。
    """
    print("\n" + "="*60)
    print("📦 MCP 工具分类信息")
    print("="*60)
    
    categories = [
        ("景点搜索工具集", MCPToolCategory.ATTRACTION_TOOLS),
        ("酒店推荐工具集", MCPToolCategory.HOTEL_TOOLS),
        ("路径规划工具集", MCPToolCategory.ROUTE_PLANNING_TOOLS),
        ("天气查询工具集", MCPToolCategory.WEATHER_TOOLS),
        ("地理编码工具集", MCPToolCategory.GEOCODING_TOOLS),
    ]
    
    for name, tools in categories:
        print(f"\n🏷️  {name}:")
        for tool_name in tools:
            print(f"   - {tool_name}")
    
    print("\n" + "="*60)
    print("💡 使用示例:")
    print("   from app.core.langgraph.tools.mcp import get_attraction_tools")
    print("   tools = get_attraction_tools()")
    print("   agent = create_agent(model, tools=tools)")
    print("="*60 + "\n")
