"""RAG知识库检索工具封装。

本模块将RAG流水线封装为LangChain Tool，使其可以被智能体直接调用。
工具封装遵循项目中weather_tool.py的规范，使用@tool装饰器定义。

统一检索工具提供四阶段流水线：
  Stage 1: 查询扩展（MQE+HyDE）→ 生成多样化查询和假设答案
  Stage 2: 混合检索（向量+关键词+RRF融合）→ 对每个查询并行检索
  Stage 3: 合并去重 → 多路结果按出现频次排序
  Stage 4: 后处理 → 上下文窗口扩展 + 城市多样性保证

工具调用流程：
  智能体 → rag_knowledge_retrieve(query) → RAGPipeline.aretrieve_enhanced() → 返回文档

工具返回格式：
  {
      "documents": [{"content": "...", "metadata": {...}}, ...],
      "total_count": 3,
  }

此格式供RAG子智能体中的LLM综合分析后生成最终回答。
"""

from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_core.tools import tool

from app.core.logging import logger
from .pipeline import get_rag_pipeline


def _format_retrieval_result(docs: List[Document]) -> Dict[str, Any]:
    """将检索到的Document列表格式化为工具返回值。"""
    documents = []
    for doc in docs:
        documents.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
        })
    return {
        "documents": documents,
        "total_count": len(documents),
    }


@tool
async def rag_knowledge_retrieve(
    query: str,
    k: int = 4,
    use_mqe: bool = True,
    use_hyde: bool = True,
    mqe_count: int = 3,
    use_filter: bool = True,
    use_hybrid: bool = True,
    use_context_expansion: bool = True,
    use_diversity: bool = True,
    score_threshold: float = 1.0,
) -> Dict[str, Any]:
    """旅游知识库检索工具，通过统一增强检索流水线从旅游攻略知识库中检索相关文档。

    检索流水线包含四个阶段，各阶段可独立开关：

    Stage 1 - 查询扩展：
      - use_mqe: 启用多查询扩展，生成语义等价的多样化查询，提高召回率
      - use_hyde: 启用假设文档嵌入，生成假设性答案段落，缩小查询与文档的语义鸿沟
      - mqe_count: MQE生成的扩展查询数量（仅当use_mqe=True时生效）
      扩展查询同时用于向量检索和关键词检索，例如HyDE生成的"兵马俑位于临潼区，
      可乘坐旅游专线"，关键词检索能匹配到"临潼区"和"旅游专线"等原始查询中没有的词

    Stage 2 - 混合检索：
      - use_filter: 启用城市元数据预过滤，从查询中自动识别城市名（如"西安美食"→city=xian）
      - use_hybrid: 启用混合检索，向量检索（语义匹配）+ 关键词检索（zhparser中文分词），
        通过RRF算法融合两路结果。关闭则退化为纯向量检索

    Stage 3 - 合并去重：
      多路检索结果按出现频次排序，频次相同按首次出现顺序。
      支持相似度阈值过滤，丢弃与查询距离过大的不相关文档。

    Stage 4 - 后处理：
      - use_context_expansion: 启用上下文窗口扩展，基于Header元数据补全同section相邻chunk，
        解决分块截断问题
      - use_diversity: 启用城市多样性保证，避免结果过度集中在单一城市

    相似度阈值说明（score_threshold）：
      基于余弦距离（cosine distance），范围[0, 2]：
      - 0: 完全相同
      - < 0.5: 高度相关
      - 0.5~1.0: 有一定相关性（默认阈值1.0保留此类文档）
      - > 1.0: 基本不相关
      降低阈值可提高精确率但可能降低召回率，升高阈值则相反。

    适用场景：
    - 旅游攻略和旅行建议（最佳旅游时间、行程规划建议等）
    - 景点详细介绍（历史背景、游览建议、门票信息等）
    - 美食推荐（特色菜品、推荐餐厅、饮食文化等）
    - 交通住宿指南（交通方式、住宿区域建议等）
    - 旅行贴士和注意事项

    此工具仅执行检索，不生成回答。请根据检索到的文档内容自行分析和回答用户问题。

    参数:
        query: 查询文本，描述需要检索的旅游信息。
               例如："成都美食推荐"、"西安必游景点"、"丽江旅行注意事项"
        k: 返回的文档数量，默认4
        use_mqe: 是否启用多查询扩展，默认True
        use_hyde: 是否启用假设文档嵌入，默认True
        mqe_count: MQE生成的扩展查询数量，默认3
        use_filter: 是否启用城市元数据预过滤，默认True
        use_hybrid: 是否启用混合检索（向量+关键词），默认True
        use_context_expansion: 是否启用上下文窗口扩展，默认True
        use_diversity: 是否启用城市多样性保证，默认True
        score_threshold: 余弦距离阈值，distance超过此值的文档被过滤，默认1.0。
                         范围[0, 2]，值越小过滤越严格。设为2.0则不过滤。

    返回:
        包含以下字段的字典：
        - documents: 检索到的文档列表，每个文档包含content和metadata
        - total_count: 检索到的文档总数
    """
    pipeline = get_rag_pipeline()

    if not pipeline.is_initialized:
        logger.info("RAG流水线未初始化，开始自动初始化...")
        try:
            await pipeline.initialize()
        except Exception as e:
            logger.error("RAG流水线初始化失败", error=str(e))
            return {
                "documents": [],
                "total_count": 0,
            }

    try:
        docs = await pipeline.aretrieve_enhanced(
            query,
            k=k,
            use_mqe=use_mqe,
            use_hyde=use_hyde,
            mqe_count=mqe_count,
            use_filter=use_filter,
            use_hybrid=use_hybrid,
            use_context_expansion=use_context_expansion,
            use_diversity=use_diversity,
            score_threshold=score_threshold,
        )
        return _format_retrieval_result(docs)

    except Exception as e:
        logger.error("RAG知识检索失败", query=query[:50], error=str(e))
        return {
            "documents": [],
            "total_count": 0,
        }


rag_tools = [rag_knowledge_retrieve]
