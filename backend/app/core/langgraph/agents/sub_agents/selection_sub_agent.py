from app.core.config import settings
from app.core.logging import logger
from app.schemas.travel.selection import DayPlanSelection
from app.core.prompts import SELECTION_AGENT_PROMPT

from langchain_qwq import ChatQwen
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate

model = ChatQwen(
    model_name=settings.DASHSCOPE_SUBAGENT_LLM_MODEL,
    api_key=settings.DASHSCOPE_API_KEY,
    api_base=settings.DASHSCOPE_API_BASE,
    temperature=0.7,
    max_tokens=1500,
    timeout=180,
    max_retries=2,
)
logger.info("selection子智能体创建完成")


@tool(
    "selection_sub_agent",
    description="""景点和酒店分配子智能体，负责从景点池和酒店池中智能选择合适的景点和酒店，并分配到各天的行程中。

适用场景：
- 首次规划：根据用户需求从景点池和酒店池中选择合适的景点和酒店
- 修改分配：根据用户修改意见（如"换一个景点"、"增加一个景点"）重新选择
- 调整行程：根据用户反馈调整景点和酒店的分配

输入格式：
- query: 包含用户需求、修改意见、景点池信息、酒店池信息等的自然语言描述
- 示例："用户需求：杭州2日游，偏好自然风光。修改意见：第一天增加两个景点。景点池：[景点列表]。酒店池：[酒店列表]。"

输出：
- text: 选择结果的文本描述
- structured_data: DayPlanSelection 对象，包含每天的景点选择和酒店选择

重要说明：
- 该子智能体从已有的景点池和酒店池中选择，不会重新搜索
- 可以理解用户的修改意见（如"换一个"、"增加"、"删除"）
- 综合考虑用户需求、景点评分、类型、价格等因素
- 确保行程合理性（每天2-3个景点）
"""
)
async def call_selection_sub_agent(query: str) -> dict:
    """调用selection子智能体处理景点和酒店的选择分配。
    
    Args:
        query: 包含用户需求、景点池、酒店池等信息的查询文本
        
    Returns:
        包含text和structured_data字段的字典
    """
    logger.info("selection子智能体开始处理选择任务")
    
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", SELECTION_AGENT_PROMPT),
            ("human", "{query}"),
        ])
        
        chain = prompt | model.with_structured_output(DayPlanSelection)
        selection_result = chain.invoke({"query": query})
        
        logger.info(
            "selection子智能体处理完成",
            days_count=len(selection_result.days),
            has_hotel=selection_result.hotel is not None,
        )
        
        return {
            "text": selection_result.overall_suggestions,
            "structured_data": selection_result,
        }
    
    except Exception as e:
        logger.error("selection子智能体处理失败", error=str(e))
        return {
            "text": f"景点和酒店分配失败：{str(e)}",
            "structured_data": None,
        }
