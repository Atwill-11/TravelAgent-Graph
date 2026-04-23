"""管理 LLM 调用、重试及降级机制的 LLM 服务模块。"""

import logging
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Type,
)

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from openai import (
    APIError,
    APITimeoutError,
    OpenAIError,
    RateLimitError,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger


class LLMRegistry:
    """可用 LLM 模型的注册中心，维护预初始化的模型实例。

    该类维护所有 LLM 配置列表，并提供按名称检索模型的方法，
    支持多厂商动态路由、独立 API Key 管理及安全参数覆盖。
    """

    # 类级别变量：包含所有可用的 LLM 模型配置
    LLMS: List[Dict[str, Any]] = [
        {
            "name": "qwen3.6-plus",
            "llm": ChatQwen(
                model="qwen3.6-plus",
                api_key=settings.DASHSCOPE_API_KEY,
                max_tokens=settings.MAX_TOKENS,
            ),
        },
        {
            "name": "gpt-5",
            "llm": ChatOpenAI(
                model="gpt-5",
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                reasoning={"effort": "medium"},
            ),
        },
        {
            "name": "gpt-5-nano",
            "llm": ChatOpenAI(
                model="gpt-5-nano",
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                reasoning={"effort": "minimal"},
            ),
        },
        {
            "name": "gpt-4o",
            "llm": ChatOpenAI(
                model="gpt-4o",
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                top_p=0.95 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
                presence_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
                frequency_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
            ),
        },
        {
            "name": "gpt-4o-mini",
            "llm": ChatOpenAI(
                model="gpt-4o-mini",
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                top_p=0.9 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
            ),
        },
    ]

    # 🔴 [新增] 动态模型注册表：存储用户运行时注册的自定义模型
    _dynamic_models: Dict[str, Dict[str, Any]] = {}
    # ===========================================

    # 多厂商配置路由表：集中管理类、密钥、Base URL 等
    PROVIDERS: Dict[str, Dict[str, Any]] = {
        "openai": {
            "cls": ChatOpenAI,
            "api_key": lambda: settings.OPENAI_API_KEY,
            "base_url": lambda: settings.OPENAI_API_BASE,
        },
        "qwen": {
            "cls": ChatQwen,
            "api_key": lambda: settings.DASHSCOPE_API_KEY,
            "base_url": lambda: settings.DASHSCOPE_API_BASE,
        },
        # 🔴 [新增] 通用 OpenAI 兼容模式：未知供应商的兜底方案
        "generic_openai_compat": {
            "cls": ChatOpenAI,  # 复用 ChatOpenAI 兼容 OpenAI 协议的所有厂商
            "api_key": lambda: None,  # 由用户传入，避免类加载时解析
            "base_url": lambda: None,  # 由用户传入，支持自定义端点
        },
        # 后续可无缝扩展: anthropic, deepseek, zhipu 等
    }

    # 🔴 [新增] 动态注册自定义模型的方法
    @classmethod
    def register_model(
        cls,
        name: str,
        provider: str,
        model_cls: Optional[Type[BaseChatModel]] = None,
        **init_kwargs,
    ) -> None:
        """动态注册自定义模型到注册表。
        
        使用示例:
            # 注册一个自定义的 DeepSeek 模型
            LLMRegistry.register_model(
                name="deepseek-chat-v3",
                provider="generic_openai_compat",  # 或显式指定已知 provider
                api_key="sk-xxx",
                base_url="https://api.deepseek.com/v1",
                temperature=0.7,
            )
        
        参数:
            name: 模型唯一标识名称
            provider: 提供商标识，如 "openai", "qwen", 或 "generic_openai_compat"
            model_cls: 可选，显式指定 LangChain 模型类。若为 None 则从 PROVIDERS 查找
            **init_kwargs: 模型初始化参数，如 api_key, base_url, temperature 等
        """
        # 如果未指定 model_cls，尝试从 PROVIDERS 获取
        if model_cls is None:
            if provider not in cls.PROVIDERS:
                # 🔴 未知提供商，自动回退到兼容模式 + 日志提示
                logger.warning(
                    "未知提供商，自动使用 OpenAI 兼容模式",
                    provider=provider,
                    model_name=name,
                )
                provider = "generic_openai_compat"
            model_cls = cls.PROVIDERS[provider]["cls"]
        
        # 解析 api_key 和 base_url（支持 lambda 延迟求值或直传值）
        provider_cfg = cls.PROVIDERS.get(provider, {})
        resolved_kwargs = {}
        
        # 处理 api_key：优先用户传入，其次配置默认
        api_key_val = init_kwargs.get("api_key")
        if api_key_val is None and "api_key" in provider_cfg:
            key_getter = provider_cfg["api_key"]
            api_key_val = key_getter() if callable(key_getter) else key_getter
        if api_key_val is not None:
            resolved_kwargs["api_key"] = api_key_val
            
        # 处理 base_url：优先用户传入，其次配置默认
        base_url_val = init_kwargs.get("base_url")
        if base_url_val is None and "base_url" in provider_cfg:
            url_getter = provider_cfg["base_url"]
            base_url_val = url_getter() if callable(url_getter) else url_getter
        if base_url_val is not None:
            resolved_kwargs["base_url"] = base_url_val
        
        # 合并其他参数（用户传入优先级最高）
        final_kwargs = {
            **resolved_kwargs, 
            **{k: v for k, v in init_kwargs.items() if k not in ("api_key", "base_url")}
        }
        
        # 创建模型实例
        model_instance = model_cls(model=name, **final_kwargs)
        
        # 注册到动态表（覆盖同名模型）
        cls._dynamic_models[name] = {
            "name": name,
            "llm": model_instance,
            "provider": provider,
            "model_cls": model_cls,
            "init_kwargs": final_kwargs,
        }
        
        logger.info("动态模型注册成功", model_name=name, provider=provider)

    # 🔴 [新增] 合并静态+动态模型的辅助方法，供降级逻辑使用
    @classmethod
    def _get_all_model_entries(cls) -> List[Dict[str, Any]]:
        """合并静态 + 动态模型列表，用于降级遍历等场景。
        
        返回:
            合并后的模型配置列表（静态优先，动态追加）
        """
        return cls.LLMS + list(cls._dynamic_models.values())

    @classmethod
    def get(cls, model_name: str, provider: Optional[str] = None, **kwargs) -> BaseChatModel:
        """按名称获取 LLM 实例，支持可选参数覆盖与多厂商动态实例化。
        [修改] 1. 增加 provider 参数支持显式指定厂商
        [修改] 2. 未命中预注册表时，自动走动态工厂逻辑
        [修改] 3. 🔴 支持从动态注册表查找自定义模型

        参数:
            model_name: 待检索的模型名称。
            **kwargs: 可选参数，用于覆盖模型的默认配置。

        返回:
            BaseChatModel 实例。

        异常:
            ValueError: 当 model_name 在注册表中未找到时抛出。
        """
        
        # 1. 优先匹配预初始化实例（静态表）
        model_entry = None
        for entry in cls.LLMS:
            if entry["name"] == model_name:
                model_entry = entry
                break

        # 🔴 [修改] 1.1 如果静态表未命中，查找动态注册表
        if model_entry is None and model_name in cls._dynamic_models:
            model_entry = cls._dynamic_models[model_name]
            # 动态模型且无自定义参数时，直接返回缓存实例（性能优化）
            if not kwargs:
                return model_entry["llm"]

        # 仅当命中缓存 且 无自定义参数时，才返回预初始化实例
        if model_entry and not kwargs:
            return model_entry["llm"]

        # 2. 解析提供商
        resolved_provider = provider or cls._resolve_provider(model_name)
        
        # 🔴 [修改] 2.1 未知提供商自动回退到兼容模式，而非抛出异常
        if resolved_provider not in cls.PROVIDERS:
            logger.warning(
                "未知提供商，自动使用 OpenAI 兼容模式",
                provider=resolved_provider,
                model_name=model_name,
            )
            resolved_provider = "generic_openai_compat"

        provider_cfg = cls.PROVIDERS[resolved_provider]
        model_cls: Type[BaseChatModel] = provider_cfg["cls"]

        # 3. 安全合并默认配置与用户自定义参数
        default_kwargs = {
            "model": model_name,
            "api_key": provider_cfg.get("api_key"),
            "base_url": provider_cfg.get("base_url"),
        }

        # 过滤 None，避免覆盖模型类内部的默认值或引发 Pydantic 校验警告
        default_kwargs = {k: v for k, v in default_kwargs.items() if v is not None}
        # 用户传入的 kwargs 优先级最高，实现安全覆盖
        final_kwargs = {**default_kwargs, **kwargs}

        log_msg = "使用预置参数动态创建 LLM 实例" if not kwargs else "使用自定义参数覆盖创建 LLM 实例"
        logger.debug(log_msg, model=model_name, provider=resolved_provider, custom_args=list(kwargs.keys()))
        return model_cls(**final_kwargs)

    @classmethod
    def _resolve_provider(cls, model_name: str) -> str:
        """根据模型名称前缀自动推断提供商（可配置为外部映射表）"""
        if model_name.startswith(("gpt-", "o1", "o3", "chatgpt-")):
            return "openai"
        if model_name.startswith(("qwen", "qwq", "deepseek")):
            return "qwen"
        
        # 🔴 [修改] 无法识别时返回兼容模式，而非抛出异常，提升容错性
        logger.debug("无法自动识别模型提供商，将使用兼容模式", model_name=model_name)
        return "generic_openai_compat"
    
    @classmethod
    def get_all_names(cls) -> List[str]:
        """按顺序获取所有已注册的 LLM 名称（静态 + 动态）。
        🔴 [修改] 合并动态注册表中的模型名称

        返回:
            LLM 名称列表。
        """
        # 🔴 [修改] 返回合并后的名称列表，确保降级逻辑能遍历所有模型
        return [entry["name"] for entry in cls._get_all_model_entries()]

    @classmethod
    def get_model_at_index(cls, index: int) -> Dict[str, Any]:
        """获取指定索引位置的模型配置（支持动态模型）。
        🔴 [修改] 基于合并后的模型列表获取

        参数:
            index: 模型在合并列表中的索引。

        返回:
            模型配置字典。
        """
        all_entries = cls._get_all_model_entries()
        if 0 <= index < len(all_entries):
            return all_entries[index]
        # 索引越界时回退到第一个模型
        return all_entries[0] if all_entries else cls.LLMS[0]


class LLMService:
    """管理 LLM 调用的服务类，支持自动重试与环形降级机制。

    该服务处理所有 LLM 交互，具备自动重试逻辑、速率限制处理，
    以及在所有可用模型间进行环形降级的能力。
    """

    def __init__(self):
        """初始化 LLM 服务。"""
        self._llm: Optional[BaseChatModel] = None
        self._current_model_index: int = 0

        # 查找默认模型在注册表中的索引
        all_names = LLMRegistry.get_all_names()
        try:
            self._current_model_index = all_names.index(settings.DEFAULT_LLM_MODEL)
            self._llm = LLMRegistry.get(settings.DEFAULT_LLM_MODEL)
            logger.info(
                "LLM 服务初始化成功",
                default_model=settings.DEFAULT_LLM_MODEL,
                model_index=self._current_model_index,
                total_models=len(all_names),
                environment=settings.ENVIRONMENT.value,
            )
        except (ValueError, Exception) as e:
            # 默认模型未找到，使用第一个模型
            self._current_model_index = 0
            # 🔴 [修改] 使用合并后的列表获取首个模型，兼容动态注册场景
            all_entries = LLMRegistry._get_all_model_entries()
            self._llm = all_entries[0]["llm"] if all_entries else LLMRegistry.LLMS[0]["llm"]
            logger.warning(
                "默认模型未找到，使用首个模型降级",
                requested=settings.DEFAULT_LLM_MODEL,
                using=all_names[0] if all_names else "none",
                error=str(e),
            )

    def _get_next_model_index(self) -> int:
        """以环形方式获取下一个模型的索引。
        🔴 [修改] 使用合并后的模型列表计算索引

        返回:
            下一个模型索引（到达末尾时回绕至 0）。
        """
        # 🔴 [修改] 使用合并后的模型列表，确保动态模型参与降级轮询
        total_models = len(LLMRegistry._get_all_model_entries())
        if total_models == 0:
            return 0
        next_index = (self._current_model_index + 1) % total_models
        return next_index

    def _switch_to_next_model(self) -> bool:
        """切换至注册表中的下一个模型（环形切换）。
        🔴 [修改] 基于合并后的模型列表进行切换

        返回:
            切换成功返回 True，否则返回 False。
        """
        try:
            next_index = self._get_next_model_index()
            next_model_entry = LLMRegistry.get_model_at_index(next_index)

            logger.warning(
                "正在切换至下一个模型",
                from_index=self._current_model_index,
                to_index=next_index,
                to_model=next_model_entry["name"],
            )

            self._current_model_index = next_index
            self._llm = next_model_entry["llm"]

            logger.info("模型切换成功", new_model=next_model_entry["name"], new_index=next_index)
            return True
        except Exception as e:
            logger.error("模型切换失败", error=str(e))
            return False

    @retry(
        stop=stop_after_attempt(settings.MAX_LLM_CALL_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _call_llm_with_retry(self, messages: List[BaseMessage]) -> BaseMessage:
        """调用 LLM 并应用自动重试逻辑。

        参数:
            messages: 发送给 LLM 的消息列表。

        返回:
            LLM 返回的 BaseMessage 响应。

        异常:
            OpenAIError: 当所有重试均失败时抛出。
        """
        if not self._llm:
            raise RuntimeError("llm not initialized")

        try:
            response = await self._llm.ainvoke(messages)
            logger.debug("LLM 调用成功", message_count=len(messages))
            return response
        except (RateLimitError, APITimeoutError, APIError) as e:
            logger.warning(
                "LLM 调用失败，正在重试",
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            raise
        except OpenAIError as e:
            logger.error(
                "LLM 调用失败",
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def call(
        self,
        messages: List[BaseMessage],
        model_name: Optional[str] = None,
        **model_kwargs,
    ) -> BaseMessage:
        """调用 LLM 处理消息，支持指定模型及环形降级。

        参数:
            messages: 发送给 LLM 的消息列表。
            model_name: 可选的指定模型名称。若为 None，则使用当前模型。
            **model_kwargs: 可选参数，用于覆盖模型的默认配置。

        返回:
            LLM 返回的 BaseMessage 响应。

        异常:
            RuntimeError: 当所有模型经重试后仍失败时抛出。
        """
        # 如果用户指定了模型，则从注册表获取
        if model_name:
            try:
                self._llm = LLMRegistry.get(model_name, **model_kwargs)
                # 更新索引以匹配请求的模型
                all_names = LLMRegistry.get_all_names()
                try:
                    self._current_model_index = all_names.index(model_name)
                except ValueError:
                    pass  # 若模型名不在列表中，保持当前索引
                logger.info("使用用户指定的模型", model_name=model_name, has_custom_kwargs=bool(model_kwargs))
            except ValueError as e:
                logger.error("指定的模型未找到", model_name=model_name, error=str(e))
                raise

        # 🔴 [修改] 使用合并后的模型总数，确保动态模型参与降级轮询
        total_models = len(LLMRegistry._get_all_model_entries())
        if total_models == 0:
            raise RuntimeError("no models available in registry")
            
        models_tried = 0
        starting_index = self._current_model_index
        last_error = None

        while models_tried < total_models:
            try:
                response = await self._call_llm_with_retry(messages)
                return response
            except OpenAIError as e:
                last_error = e
                models_tried += 1

                # 🔴 [修改] 安全获取当前模型名称（兼容动态模型）
                all_entries = LLMRegistry._get_all_model_entries()
                current_entry = (
                    all_entries[self._current_model_index] 
                    if self._current_model_index < len(all_entries) 
                    else all_entries[0]
                )
                current_model_name = current_entry["name"]
                
                logger.error(
                    "LLM 调用经重试后仍失败",
                    model=current_model_name,
                    models_tried=models_tried,
                    total_models=total_models,
                    error=str(e),
                )

                # 如果已尝试所有模型，则放弃调用
                if models_tried >= total_models:
                    logger.error(
                        "所有模型经重试后仍失败",
                        models_tried=models_tried,
                        starting_model=(
                            LLMRegistry.LLMS[starting_index]["name"] 
                            if starting_index < len(LLMRegistry.LLMS) 
                            else "unknown"
                        ),
                    )
                    break

                # 环形切换至下一个模型
                if not self._switch_to_next_model():
                    logger.error("切换至下一个模型失败")
                    break

                # 继续循环尝试下一个模型

        # 所有模型均失败
        raise RuntimeError(
            f"failed to get response from llm after trying {models_tried} models. last error: {str(last_error)}"
        )

    def get_llm(self) -> Optional[BaseChatModel]:
        """获取当前 LLM 实例。

        返回:
            当前 BaseChatModel 实例，若未初始化则返回 None。
        """
        return self._llm

    def bind_tools(self, tools: List) -> "LLMService":
        """为当前 LLM 绑定工具函数。

        参数:
            tools: 待绑定的工具函数列表。

        返回:
            self，支持方法链式调用。
        """
        if self._llm:
            self._llm = self._llm.bind_tools(tools)
            logger.debug("工具函数已绑定至 LLM", tool_count=len(tools))
        return self


# 创建全局 LLM 服务实例
llm_service = LLMService()