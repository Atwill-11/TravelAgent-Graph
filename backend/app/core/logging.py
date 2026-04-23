"""记录应用程序的配置和设置。

该模块使用structlog提供结构化日志配置，
使用特定于环境的格式化程序和处理程序。两者都支持
控制台友好的开发日志和json格式的生产日志。
"""

import io
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

import structlog

from app.core.config import (
    Environment,
    settings,
)

# 确保日志目录存在，如果不存在则创建
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

# 用于存储每个请求的上下文数据，例如用户ID、请求ID等
# ContextVar 是 Python 3.7+ 提供的上下文变量，专为并发环境设计。
# 它提供的是“任务隔离的局部存储”：在多线程/异步协程中，每个任务拥有独立的变量副本，互不干扰，
# 且能自动随协程调度传递。
_request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})


def bind_context(**kwargs: Any) -> None:
    """将上下文变量绑定到当前请求。

    Args:
        **kwargs: 要绑定到日志上下文的键值对，例如用户ID、请求ID等
    """
    current = _request_context.get()
    _request_context.set({**current, **kwargs})


def clear_context() -> None:
    """清除当前请求的所有上下文变量。"""
    _request_context.set({})


def get_context() -> Dict[str, Any]:
    """获取当前请求的日志上下文。

    Returns:
        Dict[str, Any]: 当前上下文字典，包含用户ID、请求ID等
    """
    return _request_context.get()


def add_context_to_event_dict(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """将当前请求的日志上下文添加到事件字典中。

    这个处理器会将任何绑定的上下文变量添加到每个日志事件中。

    Args:
        logger: 日志记录器实例
        method_name: 日志方法的名称
        event_dict: 要修改的事件字典

    Returns:
        Dict[str, Any]: 修改后的事件字典，包含上下文变量
    """
    context = get_context()
    if context:
        event_dict.update(context)
    return event_dict


def get_log_file_path() -> Path:
    """根据当前日期和环境获取日志文件路径。

    Returns:
        Path: 日志文件路径
    """
    # 使用value属性获取环境枚举值
    env_prefix = settings.ENVIRONMENT.value
    # 返回的日志命名格式：日志根路径/环境类型-日期.jsonl
    return settings.LOG_DIR / f"{env_prefix}-{datetime.now().strftime('%Y-%m-%d')}.jsonl"


class JsonlFileHandler(logging.Handler):
    """继承logging.Handler，自定义JSONL文件处理器，用于将日志记录写入JSONL文件。"""

    def __init__(self, file_path: Path):
        """初始化JSONL文件处理器。

        Args:
            file_path: 要写入的日志文件路径
        """
        super().__init__()
        self.file_path = file_path

    def emit(self, record: logging.LogRecord) -> None:
        """将日志记录写入JSONL文件。"""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "filename": record.pathname,
                "line": record.lineno,
                "environment": settings.ENVIRONMENT.value,
            }
            if hasattr(record, "extra"):
                log_entry.update(record.extra)

            with io.open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """关闭处理器。"""
        super().close()


def get_structlog_processors(include_file_info: bool = True) -> List[Any]:
    """根据配置获取structlog处理器。

    Args:
        include_file_info: 是否包含文件信息

    Returns:
        List[Any]: structlog处理器列表
    """
    # 设置共有的处理器
    processors = [
        # 当前日志级别 `< settings` 中配置的级别，直接返回 `None`，后续处理器全部跳过
        structlog.stdlib.filter_by_level,

        # 自动添加 `logger`（如 `"app.api.users"`）和 `level`（如 `"info"`）字段
        # add_logger_name添加的值取决于你调用 structlog.get_logger() 时传入的名称。如果不传参数，默认就是该模块的 __name__。
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,

        # 兼容传统 `logging` 的位置参数写法
        structlog.stdlib.PositionalArgumentsFormatter(),

        # 自动添加 `timestamp` 字段，格式如 `"2026-04-10T15:30:00.123456Z"`
        structlog.processors.TimeStamper(fmt="iso"),

        # 处理 `logger.info("...", stack_info=True)`，把调用栈格式化后存入 `stack` 字段
        structlog.processors.StackInfoRenderer(),

        # 处理 `logger.exception("...")` 或 `exc_info=True`，把完整 Traceback 存入 `exception` 字段
        structlog.processors.format_exc_info,

        # 确保所有字符串字段都是 Unicode 编码
        structlog.processors.UnicodeDecoder(),

        # 添加上下文变量到所有日志事件中
        add_context_to_event_dict,
    ]

    # Add callsite parameters if file info is requested
    # 如果请求包含文件信息，则添加调用站点参数处理器
    if include_file_info:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.PATHNAME,
                }
            )
        )

    # Add environment info
    # 添加环境信息处理器
    processors.append(lambda _, __, event_dict: {**event_dict, "environment": settings.ENVIRONMENT.value})

    return processors


def setup_logging() -> None:
    """配置structlog，根据环境使用不同的格式化器。

    在开发环境中，使用友好的控制台输出；在测试和生产环境中，使用结构化JSON日志。
    """
    # 确定日志级别
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    # 创建文件处理器，用于将日志记录写入JSONL文件
    # 关闭第三方库的调试日志（DashScope, HTTPX, urllib3 等）
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("dashscope").setLevel(logging.WARNING)
    logging.getLogger("aliyunsdkcore").setLevel(logging.WARNING)
    
    # 关闭 OpenAI SDK 和相关库的调试日志
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("openai.http_client").setLevel(logging.WARNING)
    logging.getLogger("httpx._client").setLevel(logging.WARNING)
    logging.getLogger("httpx._content").setLevel(logging.WARNING)
    
    # 关闭 LangChain 相关库的调试日志
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("langchain_core").setLevel(logging.WARNING)
    logging.getLogger("langchain_openai").setLevel(logging.WARNING)
    logging.getLogger("langchain_qwq").setLevel(logging.WARNING)
    logging.getLogger("langfuse").setLevel(logging.WARNING)
    logging.getLogger("langfuse.langchain").setLevel(logging.WARNING)
    
    # 创建文件处理器，用于将日志记录写入 JSONL 文件
    file_handler = JsonlFileHandler(get_log_file_path())
    # setLevel是logging.Handler继承的方法，用于设置文件处理器的日志级别
    file_handler.setLevel(log_level)

    # 创建控制台处理器，用于在开发环境中使用友好的控制台输出
    # StreamHandler是 logging 模块的内置 Handler 类，把日志记录（LogRecord）发送到任意流对象（如 sys.stdout、sys.stderr、文件、网络套接字等）
    # sys.stdout 是 Python 内置的 文件类对象，代表程序的「标准输出」
    # sys.stdout 默认指向 终端/控制台（你运行 python app.py 时看到文字的地方）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # 获取共享处理器
    shared_processors = get_structlog_processors(
        # 如果环境是开发或测试，则包含文件信息
        include_file_info=settings.ENVIRONMENT
        in [Environment.DEVELOPMENT, Environment.TEST]
    )

    # 配置标准日志记录
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[file_handler, console_handler],
    )

    # 根据环境配置structlog记录
    if settings.LOG_FORMAT == "console":
        # 开发环境使用友好的控制台输出
        structlog.configure(
            processors=[
                *shared_processors,
                # 使用控制台渲染器，用于友好的控制台输出
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # 生产环境使用结构化JSON日志
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )


# 初始化日志记录
setup_logging()

# 创建日志记录器
logger = structlog.get_logger()
log_level_name = "DEBUG" if settings.DEBUG else "INFO"
logger.info(
    "logging_initialized",
    environment=settings.ENVIRONMENT.value,
    log_level=log_level_name,
    log_format=settings.LOG_FORMAT,
    debug=settings.DEBUG,
)
