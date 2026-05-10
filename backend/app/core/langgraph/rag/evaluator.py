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

4. NDCG@K（Normalized Discounted Cumulative Gain）：考虑排序位置的增益指标
   - 计算公式：NDCG@K = DCG@K / IDCG@K
   - DCG@K = Σ(rel_i / log2(i+1))，i从1到K
   - 衡量检索系统将相关文档排在靠前位置的能力（比MRR更精细）

评估模式：
  A. 单模式评估（evaluate）：评估单一检索策略的质量
  B. 对比评估（compare）：对比基础检索 vs 扩展检索的质量差异，
     验证MQE+HyDE是否真的提升了召回率

评估流程：
  评估数据集(eval_dataset.json) → 逐条查询RAG流水线 → 判定相关性 → 计算指标 → 汇总报告

相关性判定规则：
  文档被判定为"相关"需同时满足：
  1. 城市匹配：若relevant_cities非空，文档的city元数据必须在其中
  2. 内容匹配：文档的Header 2在relevant_sections中，或内容包含relevant_keywords中的关键词
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        2. 内容过滤（满足任一即可）：
           a) 章节匹配：文档的Header 2在relevant_sections中
           b) 关键词匹配：文档内容包含relevant_keywords中至少2个关键词
              （仅1个关键词匹配过于宽松，容易将仅提及城市名的文档误判为相关）

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
        keyword_hit_count = sum(1 for kw in self.relevant_keywords if kw in content)
        keyword_match = (
            len(self.relevant_keywords) > 0 and keyword_hit_count >= 2
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

    def ndcg_at_k(self, k: int) -> float:
        """计算NDCG@K（Normalized Discounted Cumulative Gain）。

        NDCG@K = DCG@K / IDCG@K

        其中：
        - DCG@K = Σ(rel_i / log2(i+1))，i从1到K
        - IDCG@K是理想排序下的DCG@K（所有相关文档排在最前面）
        - rel_i = 1（相关）或 0（不相关）

        NDCG考虑了文档在排序列表中的位置，排在前面的相关文档贡献更大。
        值域[0, 1]，1表示完美排序。

        Args:
            k: 截断位置

        Returns:
            NDCG@K值
        """
        dcg = 0.0
        for i in range(min(k, len(self.relevance_flags))):
            if self.relevance_flags[i]:
                dcg += 1.0 / (i + 1 if i == 0 else self._log2(i + 1))

        ideal_relevant_count = min(
            self.total_relevant,
            min(k, len(self.relevance_flags)),
        )
        idcg = 0.0
        for i in range(ideal_relevant_count):
            idcg += 1.0 / (i + 1 if i == 0 else self._log2(i + 1))

        return dcg / idcg if idcg > 0 else 0.0

    @staticmethod
    def _log2(x: float) -> float:
        import math
        return math.log2(x)


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
            ndcgs = [r.ndcg_at_k(k) for r in results]
            summary[f"recall@{k}"] = round(sum(recalls) / n, 4)
            summary[f"precision@{k}"] = round(sum(precisions) / n, 4)
            summary[f"ndcg@{k}"] = round(sum(ndcgs) / n, 4)

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
                item[f"ndcg@{k}"] = round(r.ndcg_at_k(k), 4)
            per_query.append(item)

        return {
            "summary": summary,
            "query_count": n,
            "k_values": k_values,
            "per_query": per_query,
        }

    async def compare(
        self,
        k_values: Optional[List[int]] = None,
        multi_query_count: int = 3,
        use_hyde: bool = True,
    ) -> Dict[str, Any]:
        """对比评估：基础检索 vs 扩展检索。

        对同一评估数据集分别执行基础检索和扩展检索，
        生成对比报告，验证MQE+HyDE是否真的提升了召回率。

        对比维度：
        1. 召回率提升：扩展检索是否找到了更多相关文档
        2. 精确率变化：扩展检索是否引入了更多噪声
        3. 排序质量：扩展检索是否将相关文档排在更靠前的位置
        4. 逐查询分析：哪些查询受益最大，哪些查询反而变差

        Args:
            k_values: 需要评估的K值列表，默认[1, 3, 5, 10]
            multi_query_count: MQE生成的扩展查询数量，默认3
            use_hyde: 是否启用HyDE，默认True

        Returns:
            对比评估报告，包含：
            - basic: 基础检索评估结果
            - expanded: 扩展检索评估结果
            - comparison: 对比分析（指标差异、提升/下降查询统计等）
        """
        if k_values is None:
            k_values = [1, 3, 5, 10]

        max_k = max(k_values)

        queries = self.load_eval_dataset()
        all_chunks = self._load_all_chunks()

        basic_results: List[EvalResult] = []
        expanded_results: List[EvalResult] = []

        for q in queries:
            basic_docs = await self._retrieve_basic(q.query, max_k)
            basic_results.append(
                self._build_eval_result(q, basic_docs, all_chunks, k_values)
            )

            expanded_docs = await self._retrieve_expanded(
                q.query, max_k, multi_query_count, use_hyde
            )
            expanded_results.append(
                self._build_eval_result(q, expanded_docs, all_chunks, k_values)
            )

            logger.info(
                "对比评估完成",
                query_id=q.query_id,
                basic_relevant=sum(
                    q.is_relevant(doc) for doc in basic_docs
                ),
                expanded_relevant=sum(
                    q.is_relevant(doc) for doc in expanded_docs
                ),
            )

        basic_report = self._aggregate(basic_results, k_values)
        expanded_report = self._aggregate(expanded_results, k_values)

        comparison = self._build_comparison(
            basic_results, expanded_results, k_values
        )

        return {
            "basic": basic_report,
            "expanded": expanded_report,
            "comparison": comparison,
        }

    async def ab_test(
        self,
        k_values: Optional[List[int]] = None,
        configs: Optional[Dict[str, Dict[str, Any]]] = None,
        langfuse_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """多配置A/B测试：对比不同检索策略组合的效果。

        通过控制aretrieve_enhanced的各开关参数，测试不同策略组合
        对检索质量的影响，证明每个增强策略的独立贡献。

        默认测试5种配置：
        - baseline: 纯向量检索（所有增强策略关闭）
        - mqe_only: 仅启用MQE多查询扩展
        - hyde_only: 仅启用HyDE假设文档嵌入
        - hybrid_only: 仅启用混合检索（向量+关键词）
        - full: 全部策略启用

        测试结果可以回答：
        1. MQE对召回率有多大提升？
        2. HyDE对召回率有多大提升？
        3. 混合检索（关键词+语义）是否优于纯向量检索？
        4. 各策略组合是否有叠加效果？

        Args:
            k_values: 需要评估的K值列表，默认[1, 3, 5, 10]
            configs: 自定义配置字典，格式为 {"配置名": {"参数名": 参数值, ...}}
                     参数名对应aretrieve_enhanced的关键字参数
            langfuse_client: 可选的Langfuse客户端实例，传入后会在Langfuse中
                             创建结构化trace追踪A/B测试过程，可观测MQE/HyDE生成结果

        Returns:
            A/B测试报告，包含：
            - configs: 各配置的参数详情
            - results: 各配置的评估结果
            - comparison: 配置间的对比分析
        """
        if k_values is None:
            k_values = [1, 3, 5, 10]

        if configs is None:
            configs = {
                "baseline": {
                    "use_mqe": False,
                    "use_hyde": False,
                    "use_filter": False,
                    "use_hybrid": False,
                    "use_context_expansion": False,
                    "use_diversity": False,
                    "score_threshold": 2.0,
                },
                "mqe_only": {
                    "use_mqe": True,
                    "use_hyde": False,
                    "use_filter": False,
                    "use_hybrid": False,
                    "use_context_expansion": False,
                    "use_diversity": False,
                    "score_threshold": 2.0,
                },
                "hyde_only": {
                    "use_mqe": False,
                    "use_hyde": True,
                    "use_filter": False,
                    "use_hybrid": False,
                    "use_context_expansion": False,
                    "use_diversity": False,
                    "score_threshold": 2.0,
                },
                "hybrid_only": {
                    "use_mqe": False,
                    "use_hyde": False,
                    "use_filter": False,
                    "use_hybrid": True,
                    "use_context_expansion": False,
                    "use_diversity": False,
                    "score_threshold": 2.0,
                },
                "full": {
                    "use_mqe": True,
                    "use_hyde": True,
                    "use_filter": True,
                    "use_hybrid": True,
                    "use_context_expansion": True,
                    "use_diversity": True,
                    "score_threshold": 2.0,
                },
            }

        max_k = max(k_values)
        queries = self.load_eval_dataset()
        all_chunks = self._load_all_chunks()

        trace_id = None
        if langfuse_client is not None:
            try:
                trace_id = langfuse_client.create_trace_id()
                logger.info("Langfuse A/B测试trace已创建", trace_id=trace_id)
            except Exception as e:
                logger.warning("创建Langfuse trace_id失败，继续无trace执行", error=str(e))
                trace_id = None

        async def _eval_single_query(
            config_name: str,
            config_params: Dict[str, Any],
            q: EvalQuery,
            config_span: Optional[Any],
        ) -> Tuple[EvalResult, float, Optional[Any]]:
            start_time = time.monotonic()

            run_config = None
            query_span = None
            if config_span is not None:
                try:
                    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

                    query_span = config_span.start_observation(
                        name=f"query: {q.query_id}",
                        as_type="span",
                        input={"query": q.query},
                    )
                    run_config = {
                        "callbacks": [
                            LangfuseCallbackHandler(
                                trace_context={
                                    "trace_id": trace_id,
                                    "parent_span_id": query_span.id,
                                },
                            )
                        ],
                        "metadata": {
                            "config_name": config_name,
                            "query_id": q.query_id,
                        },
                    }
                except Exception as e:
                    logger.warning("创建Langfuse query回调失败", error=str(e))
                    run_config = None

            try:
                docs = await self.pipeline.aretrieve_enhanced(
                    query=q.query,
                    k=max_k * 3,
                    **config_params,
                    config=run_config,
                )
            except Exception as e:
                logger.error(
                    "A/B测试检索失败",
                    config=config_name,
                    query_id=q.query_id,
                    error=str(e),
                )
                docs = []

            if query_span is not None:
                try:
                    query_span.update(
                        output={
                            "retrieved_count": len(docs),
                        }
                    )
                    query_span.end()
                except Exception:
                    pass

            elapsed = time.monotonic() - start_time

            eval_result = self._build_eval_result(q, docs, all_chunks, k_values)

            if config_span is not None:
                try:
                    eval_span = config_span.start_observation(
                        name=f"eval: {q.query_id}",
                        as_type="evaluator",
                        input={
                            "query": q.query,
                            "config_name": config_name,
                            "retrieved_count": len(docs),
                        },
                    )

                    query_metrics = {
                        "retrieved_count": len(docs),
                        "relevant_in_retrieved": sum(eval_result.relevance_flags),
                        "total_relevant": eval_result.total_relevant,
                        "elapsed_ms": round(elapsed * 1000, 1),
                        "mrr": round(eval_result.reciprocal_rank(), 4),
                    }
                    for kv in k_values:
                        query_metrics[f"recall@{kv}"] = round(eval_result.recall_at_k(kv), 4)
                        query_metrics[f"precision@{kv}"] = round(eval_result.precision_at_k(kv), 4)
                        query_metrics[f"ndcg@{kv}"] = round(eval_result.ndcg_at_k(kv), 4)

                    eval_span.update(output=query_metrics)

                    for kv in k_values:
                        eval_span.score(
                            name=f"recall@{kv}",
                            value=round(eval_result.recall_at_k(kv), 4),
                        )
                        eval_span.score(
                            name=f"precision@{kv}",
                            value=round(eval_result.precision_at_k(kv), 4),
                        )
                        eval_span.score(
                            name=f"ndcg@{kv}",
                            value=round(eval_result.ndcg_at_k(kv), 4),
                        )
                    eval_span.score(
                        name="mrr",
                        value=round(eval_result.reciprocal_rank(), 4),
                    )

                    eval_span.end()
                except Exception as e:
                    logger.warning("Langfuse eval span记录失败", error=str(e))

            return eval_result, elapsed, query_span

        async def _eval_single_config(
            config_name: str,
            config_params: Dict[str, Any],
        ) -> Tuple[str, List[EvalResult], Dict[str, Any], float, Optional[Any]]:
            config_span = None
            if trace_id is not None:
                try:
                    config_span = langfuse_client.start_observation(
                        name=f"config: {config_name}",
                        as_type="span",
                        trace_context={"trace_id": trace_id},
                        input=config_params,
                    )
                except Exception as e:
                    logger.warning("创建Langfuse config span失败", error=str(e))

            coros = [
                _eval_single_query(config_name, config_params, q, config_span)
                for q in queries
            ]
            gather_results = await asyncio.gather(*coros, return_exceptions=True)

            config_results: List[EvalResult] = []
            config_total_time = 0.0
            for gr in gather_results:
                if isinstance(gr, Exception):
                    logger.error("A/B测试单条查询异常", error=str(gr))
                    continue
                eval_result, elapsed, _ = gr
                config_results.append(eval_result)
                config_total_time += elapsed

            config_report = self._aggregate(config_results, k_values)

            if config_span is not None:
                try:
                    config_span.update(
                        output={
                            "summary": config_report["summary"],
                            "query_count": config_report["query_count"],
                            "total_time": config_total_time,
                        }
                    )

                    for metric_key, metric_value in config_report["summary"].items():
                        config_span.score(
                            name=metric_key,
                            value=metric_value,
                        )

                    config_span.end()
                except Exception as e:
                    logger.warning("Langfuse config span记录失败", error=str(e))

            logger.info(
                "A/B测试配置完成",
                config=config_name,
                avg_recall_at_5=config_report["summary"].get("recall@5", 0),
                total_time=config_total_time,
            )

            return config_name, config_results, config_report, config_total_time, config_span

        config_coros = [
            _eval_single_config(name, params)
            for name, params in configs.items()
        ]
        config_gather_results = await asyncio.gather(*config_coros, return_exceptions=True)

        all_config_results: Dict[str, List[EvalResult]] = {}
        all_config_reports: Dict[str, Dict[str, Any]] = {}
        all_config_times: Dict[str, float] = {}

        for gr in config_gather_results:
            if isinstance(gr, Exception):
                logger.error("A/B测试配置异常", error=str(gr))
                continue
            config_name, config_results, config_report, config_total_time, _ = gr
            all_config_results[config_name] = config_results
            all_config_reports[config_name] = config_report
            all_config_times[config_name] = round(config_total_time, 2)

        comparison = self._build_ab_comparison(
            all_config_results, all_config_reports, k_values
        )

        if langfuse_client is not None:
            try:
                langfuse_client.flush()
                logger.info("Langfuse A/B测试数据已刷新")
            except Exception as e:
                logger.warning("Langfuse flush失败", error=str(e))

        return {
            "configs": configs,
            "k_values": k_values,
            "results": all_config_reports,
            "timing": all_config_times,
            "comparison": comparison,
        }

    def _build_ab_comparison(
        self,
        all_config_results: Dict[str, List[EvalResult]],
        all_config_reports: Dict[str, Dict[str, Any]],
        k_values: List[int],
    ) -> Dict[str, Any]:
        """构建多配置A/B测试的对比分析。

        以baseline为参照，计算各配置相对于baseline的指标增量，
        并统计各配置在逐查询层面的胜/负/平情况。

        Args:
            all_config_results: 各配置的评估结果
            all_config_reports: 各配置的汇总报告
            k_values: K值列表

        Returns:
            多配置对比分析报告
        """
        config_names = list(all_config_results.keys())
        if "baseline" not in config_names:
            baseline_name = config_names[0]
        else:
            baseline_name = "baseline"

        baseline_summary = all_config_reports[baseline_name]["summary"]
        baseline_results = all_config_results[baseline_name]
        n = len(baseline_results)

        config_deltas: Dict[str, Dict[str, float]] = {}
        for name in config_names:
            if name == baseline_name:
                continue
            current_summary = all_config_reports[name]["summary"]
            deltas = {}
            for metric_key, baseline_value in baseline_summary.items():
                current_value = current_summary.get(metric_key, 0.0)
                deltas[f"{metric_key}_delta"] = round(current_value - baseline_value, 4)
            config_deltas[name] = deltas

        max_k = max(k_values)
        per_config_win_stats: Dict[str, Dict[str, int]] = {}
        for name in config_names:
            if name == baseline_name:
                continue
            current_results = all_config_results[name]
            improved = declined = unchanged = 0
            for base_r, cur_r in zip(baseline_results, current_results):
                base_recall = base_r.recall_at_k(max_k)
                cur_recall = cur_r.recall_at_k(max_k)
                if cur_recall > base_recall:
                    improved += 1
                elif cur_recall < base_recall:
                    declined += 1
                else:
                    unchanged += 1
            per_config_win_stats[name] = {
                "improved": improved,
                "declined": declined,
                "unchanged": unchanged,
                "total": n,
                "improved_ratio": round(improved / n, 4) if n > 0 else 0.0,
            }

        summary_table = {}
        for name in config_names:
            summary_table[name] = all_config_reports[name]["summary"]

        return {
            "baseline_config": baseline_name,
            "metric_deltas_vs_baseline": config_deltas,
            "win_stats_vs_baseline": per_config_win_stats,
            "summary_table": summary_table,
        }

    async def _retrieve_basic(
        self, query: str, k: int
    ) -> List[Document]:
        """执行基础检索。

        Args:
            query: 查询文本
            k: 返回文档数量

        Returns:
            检索到的文档列表
        """
        start_time = time.monotonic()
        try:
            results = await self.pipeline.aretrieve_with_scores(
                query=query, k=k
            )
            retrieved_docs = [doc for doc, _score in results]
        except Exception as e:
            logger.error("基础检索失败", query=query[:50], error=str(e))
            retrieved_docs = []
        elapsed = time.monotonic() - start_time
        logger.debug("基础检索耗时", query=query[:50], elapsed_ms=round(elapsed * 1000, 1))
        return retrieved_docs

    async def _retrieve_expanded(
        self,
        query: str,
        k: int,
        multi_query_count: int,
        use_hyde: bool,
    ) -> List[Document]:
        """执行扩展检索。

        Args:
            query: 查询文本
            k: 返回文档数量
            multi_query_count: MQE扩展查询数量
            use_hyde: 是否启用HyDE

        Returns:
            检索到的文档列表
        """
        start_time = time.monotonic()
        try:
            retrieved_docs = await self.pipeline.aretrieve_enhanced(
                query=query,
                k=k,
                use_mqe=multi_query_count > 0,
                use_hyde=use_hyde,
                mqe_count=multi_query_count,
                use_filter=False,
                use_hybrid=False,
                use_context_expansion=False,
                use_diversity=False,
            )
        except Exception as e:
            logger.error("扩展检索失败", query=query[:50], error=str(e))
            retrieved_docs = []
        elapsed = time.monotonic() - start_time
        logger.debug("扩展检索耗时", query=query[:50], elapsed_ms=round(elapsed * 1000, 1))
        return retrieved_docs

    def _build_eval_result(
        self,
        query: EvalQuery,
        retrieved_docs: List[Document],
        all_chunks: List[Document],
        k_values: List[int],
    ) -> EvalResult:
        """构建单条查询的评估结果。

        Args:
            query: 评估查询
            retrieved_docs: 检索到的文档列表
            all_chunks: 全库文档分块
            k_values: K值列表

        Returns:
            EvalResult实例
        """
        relevance_flags = [query.is_relevant(doc) for doc in retrieved_docs]
        total_relevant = self._count_relevant(query, all_chunks)

        return EvalResult(
            query_id=query.query_id,
            query=query.query,
            k_values=k_values,
            relevance_flags=relevance_flags,
            total_relevant=total_relevant,
        )

    def _build_comparison(
        self,
        basic_results: List[EvalResult],
        expanded_results: List[EvalResult],
        k_values: List[int],
    ) -> Dict[str, Any]:
        """构建基础检索 vs 扩展检索的对比分析。

        分析维度：
        1. 指标差异：各指标在两种检索策略下的差值
        2. 提升查询统计：有多少查询的召回率提升了
        3. 下降查询统计：有多少查询的召回率反而下降了
        4. 逐查询对比：每条查询在两种策略下的详细指标对比

        Args:
            basic_results: 基础检索的评估结果列表
            expanded_results: 扩展检索的评估结果列表
            k_values: K值列表

        Returns:
            对比分析报告
        """
        n = len(basic_results)
        if n == 0 or n != len(expanded_results):
            return {"error": "评估结果数量不匹配或为空"}

        metric_deltas: Dict[str, float] = {}
        for k in k_values:
            basic_recall_avg = sum(r.recall_at_k(k) for r in basic_results) / n
            expanded_recall_avg = sum(r.recall_at_k(k) for r in expanded_results) / n
            metric_deltas[f"recall@{k}_delta"] = round(
                expanded_recall_avg - basic_recall_avg, 4
            )

            basic_precision_avg = sum(r.precision_at_k(k) for r in basic_results) / n
            expanded_precision_avg = sum(r.precision_at_k(k) for r in expanded_results) / n
            metric_deltas[f"precision@{k}_delta"] = round(
                expanded_precision_avg - basic_precision_avg, 4
            )

            basic_ndcg_avg = sum(r.ndcg_at_k(k) for r in basic_results) / n
            expanded_ndcg_avg = sum(r.ndcg_at_k(k) for r in expanded_results) / n
            metric_deltas[f"ndcg@{k}_delta"] = round(
                expanded_ndcg_avg - basic_ndcg_avg, 4
            )

        basic_mrr_avg = sum(r.reciprocal_rank() for r in basic_results) / n
        expanded_mrr_avg = sum(r.reciprocal_rank() for r in expanded_results) / n
        metric_deltas["mrr_delta"] = round(expanded_mrr_avg - basic_mrr_avg, 4)

        recall_improved = 0
        recall_declined = 0
        recall_unchanged = 0
        max_k = max(k_values)

        for basic_r, expanded_r in zip(basic_results, expanded_results):
            basic_recall = basic_r.recall_at_k(max_k)
            expanded_recall = expanded_r.recall_at_k(max_k)
            if expanded_recall > basic_recall:
                recall_improved += 1
            elif expanded_recall < basic_recall:
                recall_declined += 1
            else:
                recall_unchanged += 1

        per_query_comparison = []
        for basic_r, expanded_r in zip(basic_results, expanded_results):
            item: Dict[str, Any] = {
                "query_id": basic_r.query_id,
                "query": basic_r.query,
                "basic": {
                    "total_relevant": basic_r.total_relevant,
                    "relevant_in_retrieved": sum(basic_r.relevance_flags),
                    "mrr": round(basic_r.reciprocal_rank(), 4),
                },
                "expanded": {
                    "total_relevant": expanded_r.total_relevant,
                    "relevant_in_retrieved": sum(expanded_r.relevance_flags),
                    "mrr": round(expanded_r.reciprocal_rank(), 4),
                },
            }
            for k in k_values:
                item["basic"][f"recall@{k}"] = round(basic_r.recall_at_k(k), 4)
                item["basic"][f"precision@{k}"] = round(basic_r.precision_at_k(k), 4)
                item["basic"][f"ndcg@{k}"] = round(basic_r.ndcg_at_k(k), 4)
                item["expanded"][f"recall@{k}"] = round(expanded_r.recall_at_k(k), 4)
                item["expanded"][f"precision@{k}"] = round(expanded_r.precision_at_k(k), 4)
                item["expanded"][f"ndcg@{k}"] = round(expanded_r.ndcg_at_k(k), 4)

            basic_max_recall = basic_r.recall_at_k(max_k)
            expanded_max_recall = expanded_r.recall_at_k(max_k)
            if expanded_max_recall > basic_max_recall:
                item["verdict"] = "improved"
            elif expanded_max_recall < basic_max_recall:
                item["verdict"] = "declined"
            else:
                item["verdict"] = "unchanged"

            per_query_comparison.append(item)

        return {
            "metric_deltas": metric_deltas,
            "recall_change_summary": {
                "improved": recall_improved,
                "declined": recall_declined,
                "unchanged": recall_unchanged,
                "total": n,
                "improved_ratio": round(recall_improved / n, 4) if n > 0 else 0.0,
            },
            "per_query": per_query_comparison,
        }
