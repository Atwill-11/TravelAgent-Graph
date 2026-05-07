"""RAG检索质量评估模块。

本模块实现了RAG检索质量的离线评估，支持以下指标：

1. Recall@K：在所有相关文档中，top-K检索结果覆盖了多少比例
   - 计算公式：Recall@K = |{relevant docs} ∩ {top-K docs}| / |{relevant docs}|
   - 衡量检索系统的查全能力，值越高表示遗漏的相关文档越少

2. Precision@K：top-K检索结果中，有多少比例是相关文档
   - 计算公式：Precision@K = |{relevant docs} ∩ {top-K docs}| / K
   - 衡量检索系统的查准能力，值越高表示返回的噪声越少

3. MRR（Mean Reciprocal Rank）：第一个相关文档排名倒数的均值
   - 计算公式：MRR = (1/|Q|) * Σ(1/rank_i)，rank_i为第i个查询的首个相关文档排名
   - 衡量检索系统将相关文档排在靠前位置的能力

评估流程：
  评估数据集(eval_dataset.json) → 逐条查询RAG流水线 → 判定相关性 → 计算指标 → 汇总报告

相关性判定规则：
  文档被判定为"相关"需同时满足：
  1. 城市匹配：若relevant_cities非空，文档的city元数据必须在其中
  2. 内容匹配：文档的Header 2在relevant_sections中，或内容包含relevant_keywords中的关键词
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document

from app.core.logging import logger
from .pipeline import RAGPipeline


EVAL_DATASET_PATH = Path(__file__).parent / "eval_dataset.json"


class EvalQuery:
    """评估查询单条数据。

    封装eval_dataset.json中单条查询的标注信息，
    并提供相关性判定方法。

    Attributes:
        query_id: 查询唯一标识
        query: 查询文本
        relevant_cities: 相关城市列表（为空表示不限城市）
        relevant_sections: 相关章节列表
        relevant_keywords: 相关关键词列表
    """

    def __init__(self, data: Dict[str, Any]):
        self.query_id: str = data["query_id"]
        self.query: str = data["query"]
        self.relevant_cities: List[str] = data.get("relevant_cities", [])
        self.relevant_sections: List[str] = data.get("relevant_sections", [])
        self.relevant_keywords: List[str] = data.get("relevant_keywords", [])

    def is_relevant(self, doc: Document) -> bool:
        """判断文档是否与当前查询相关。

        相关性判定采用两阶段过滤：
        1. 城市过滤：若relevant_cities非空，文档的city元数据必须在其中；
           若relevant_cities为空（跨城市查询），则跳过城市过滤
        2. 内容过滤：文档的Header 2在relevant_sections中，
           或文档内容包含relevant_keywords中的至少一个关键词

        两阶段为AND关系，需同时满足。

        Args:
            doc: 待判定的文档

        Returns:
            True表示文档相关，False表示不相关
        """
        city_match = (
            not self.relevant_cities
            or doc.metadata.get("city", "") in self.relevant_cities
        )

        section_match = (
            self.relevant_sections
            and doc.metadata.get("Header 2", "") in self.relevant_sections
        )

        content = doc.page_content
        keyword_match = (
            self.relevant_keywords
            and any(kw in content for kw in self.relevant_keywords)
        )

        content_match = section_match or keyword_match

        return city_match and content_match


class EvalResult:
    """单条查询的评估结果。

    存储单条查询的检索结果和相关性标注，
    并提供各指标的逐条计算方法。

    Attributes:
        query_id: 查询唯一标识
        query: 查询文本
        k_values: 需要计算的K值列表
        relevance_flags: 检索结果的相关性标记列表（按排名顺序）
        total_relevant: 全库中相关文档的总数
    """

    def __init__(
        self,
        query_id: str,
        query: str,
        k_values: List[int],
        relevance_flags: List[bool],
        total_relevant: int,
    ):
        self.query_id = query_id
        self.query = query
        self.k_values = k_values
        self.relevance_flags = relevance_flags
        self.total_relevant = total_relevant

    def recall_at_k(self, k: int) -> float:
        """计算Recall@K。

        Recall@K = top-K中相关文档数 / 全库相关文档总数

        当全库相关文档数为0时返回0.0，避免除零错误。
        """
        relevant_in_k = sum(self.relevance_flags[:k])
        if self.total_relevant == 0:
            return 0.0
        return relevant_in_k / self.total_relevant

    def precision_at_k(self, k: int) -> float:
        """计算Precision@K。

        Precision@K = top-K中相关文档数 / K
        """
        relevant_in_k = sum(self.relevance_flags[:k])
        return relevant_in_k / k if k > 0 else 0.0

    def reciprocal_rank(self) -> float:
        """计算Reciprocal Rank。

        RR = 1 / (第一个相关文档的排名)

        若检索结果中无相关文档，返回0.0。
        """
        for i, is_rel in enumerate(self.relevance_flags):
            if is_rel:
                return 1.0 / (i + 1)
        return 0.0


class RAGEvaluator:
    """RAG检索质量评估器。

    对RAG流水线的检索质量进行系统性评估，
    输出Recall@K、Precision@K、MRR等指标。

    使用方式：
        evaluator = RAGEvaluator(pipeline)
        report = await evaluator.evaluate(k_values=[1, 3, 5, 10])

    评估报告结构：
        {
            "summary": {
                "recall@1": 0.12, "precision@1": 0.48,
                "recall@3": 0.35, "precision@3": 0.44,
                "recall@5": 0.52, "precision@5": 0.40,
                "recall@10": 0.78, "precision@10": 0.32,
                "mrr": 0.56
            },
            "query_count": 25,
            "k_values": [1, 3, 5, 10],
            "per_query": [...]
        }
    """

    def __init__(
        self,
        pipeline: RAGPipeline,
        eval_dataset_path: Optional[str] = None,
    ):
        self.pipeline = pipeline
        self.eval_dataset_path = (
            Path(eval_dataset_path) if eval_dataset_path else EVAL_DATASET_PATH
        )
        self._queries: Optional[List[EvalQuery]] = None
        self._all_chunks: Optional[List[Document]] = None

    def load_eval_dataset(self) -> List[EvalQuery]:
        """加载评估数据集。

        从eval_dataset.json加载查询及标注信息，
        结果会被缓存，重复调用直接返回缓存。

        Returns:
            EvalQuery列表
        """
        if self._queries is not None:
            return self._queries

        with open(self.eval_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._queries = [EvalQuery(item) for item in data]
        logger.info("评估数据集加载完成", query_count=len(self._queries))
        return self._queries

    def _load_all_chunks(self) -> List[Document]:
        """加载全库文档分块，用于计算全库相关文档总数。

        通过pipeline的load_documents和split_documents方法
        重新生成全库文档分块，结果会被缓存。

        Returns:
            全库文档分块列表
        """
        if self._all_chunks is not None:
            return self._all_chunks

        documents = self.pipeline.load_documents()
        if not documents:
            logger.warning("未加载到任何文档，无法计算全库相关文档数")
            self._all_chunks = []
            return self._all_chunks

        self._all_chunks = self.pipeline.split_documents(documents)
        logger.info("全库文档分块完成", chunk_count=len(self._all_chunks))
        return self._all_chunks

    def _count_relevant(self, query: EvalQuery, chunks: List[Document]) -> int:
        """统计全库中与查询相关的文档数量。

        Args:
            query: 评估查询
            chunks: 全库文档分块列表

        Returns:
            相关文档数量
        """
        return sum(1 for chunk in chunks if query.is_relevant(chunk))

    async def evaluate(
        self,
        k_values: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """执行完整的RAG检索质量评估。

        评估流程：
        1. 加载评估数据集和全库文档分块
        2. 对每条查询，从向量库检索top-K文档
        3. 判定每个检索结果的相关性
        4. 统计全库相关文档数量（用于Recall@K的分母）
        5. 计算各指标并汇总

        Args:
            k_values: 需要评估的K值列表，默认[1, 3, 5, 10]

        Returns:
            评估报告字典，包含summary（汇总指标）和per_query（逐条详情）
        """
        if k_values is None:
            k_values = [1, 3, 5, 10]

        max_k = max(k_values)

        queries = self.load_eval_dataset()
        all_chunks = self._load_all_chunks()

        eval_results: List[EvalResult] = []

        for q in queries:
            try:
                results = await self.pipeline.aretrieve_with_scores(
                    query=q.query, k=max_k
                )
                retrieved_docs = [doc for doc, _score in results]
            except Exception as e:
                logger.error("检索失败", query_id=q.query_id, error=str(e))
                retrieved_docs = []

            relevance_flags = [q.is_relevant(doc) for doc in retrieved_docs]
            total_relevant = self._count_relevant(q, all_chunks)

            eval_results.append(
                EvalResult(
                    query_id=q.query_id,
                    query=q.query,
                    k_values=k_values,
                    relevance_flags=relevance_flags,
                    total_relevant=total_relevant,
                )
            )

            logger.info(
                "查询评估完成",
                query_id=q.query_id,
                retrieved=len(retrieved_docs),
                relevant_in_retrieved=sum(relevance_flags),
                total_relevant=total_relevant,
            )

        return self._aggregate(eval_results, k_values)

    def _aggregate(
        self,
        results: List[EvalResult],
        k_values: List[int],
    ) -> Dict[str, Any]:
        """汇总所有查询的评估结果。

        对所有查询的指标取算术平均，生成汇总报告。

        Args:
            results: 逐条评估结果列表
            k_values: K值列表

        Returns:
            汇总评估报告
        """
        n = len(results)
        if n == 0:
            return {"error": "无评估结果"}

        summary: Dict[str, float] = {}
        for k in k_values:
            recalls = [r.recall_at_k(k) for r in results]
            precisions = [r.precision_at_k(k) for r in results]
            summary[f"recall@{k}"] = round(sum(recalls) / n, 4)
            summary[f"precision@{k}"] = round(sum(precisions) / n, 4)

        mrr_values = [r.reciprocal_rank() for r in results]
        summary["mrr"] = round(sum(mrr_values) / n, 4)

        per_query = []
        for r in results:
            item: Dict[str, Any] = {
                "query_id": r.query_id,
                "query": r.query,
                "total_relevant": r.total_relevant,
                "retrieved_count": len(r.relevance_flags),
                "relevant_in_retrieved": sum(r.relevance_flags),
                "mrr": round(r.reciprocal_rank(), 4),
            }
            for k in k_values:
                item[f"recall@{k}"] = round(r.recall_at_k(k), 4)
                item[f"precision@{k}"] = round(r.precision_at_k(k), 4)
            per_query.append(item)

        return {
            "summary": summary,
            "query_count": n,
            "k_values": k_values,
            "per_query": per_query,
        }
