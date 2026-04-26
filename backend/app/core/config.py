"""应用环境配置。
"""

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


# Define environment types
class Environment(str, Enum):
    """应用环境类型。

    定义了应用可能的环境类型：development, staging, production, and test。
    """

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


# Determine environment
def get_environment() -> Environment:
    """Get the current environment.

    Returns:
        Environment: The current environment (development, staging, production, or test)
    """
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "test":
            return Environment.TEST
        case _:
            return Environment.DEVELOPMENT


# Load appropriate .env file based on environment
def load_env_file():
    """加载当前环境对应的 .env 文件。"""
    import structlog
    logger = structlog.get_logger(__name__)
    
    env = get_environment()
    logger.debug("加载的环境：", environment=env.value)
    # 获取项目根目录
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # 定义环境文件的优先级
    env_files = [
        os.path.join(base_dir, f".env.{env.value}.local"),
        os.path.join(base_dir, f".env.{env.value}"),
        os.path.join(base_dir, ".env.local"),
        os.path.join(base_dir, ".env"),
    ]

    # 按照优先级加载环境文件
    for env_file in env_files:
        if os.path.isfile(env_file):
            load_dotenv(dotenv_path=env_file)
            logger.info("加载的环境文件：", file=env_file)
            return env_file

    # 如果没有找到环境文件，使用默认值
    logger.warning("未找到环境文件", message="使用默认值")
    return None


ENV_FILE = load_env_file()


# Parse list values from environment variables
def parse_list_from_env(env_key, default=None):
    """从环境变量中解析出一个逗号分隔的列表。"""
    value = os.getenv(env_key)
    if not value:
        return default or []

    # 移除字符串首尾的引号
    value = value.strip("\"'")
    # 如果字符串中没有逗号，直接返回单元素列表
    if "," not in value:
        return [value]
    # 划分逗号分隔的字符串
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_dict_of_lists_from_env(prefix, default_dict=None):
    """从环境变量中解析出一个字典，字典的键是环境变量的前缀，值是一个列表。"""
    result = default_dict or {}

    # 遍历所有环境变量，查找指定前缀的变量
    for key, value in os.environ.items():
        if key.startswith(prefix):
            endpoint = key[len(prefix) :].lower()  # 提取环境变量名，转换为小写作为字典键
            if value:
                value = value.strip("\"'")
                if "," in value:
                    result[endpoint] = [item.strip() for item in value.split(",") if item.strip()]
                else:
                    result[endpoint] = [value]

    return result


class Settings:
    """应用配置类。"""

    def __init__(self):
        """初始化应用配置。

        从环境变量中加载所有配置值，每个配置项都有一个默认值。
        同时根据当前环境应用特定的覆盖配置。
        """
        # 设置应用环境类型
        self.ENVIRONMENT = get_environment()

        # 应用设置
        self.PROJECT_NAME = os.getenv("PROJECT_NAME", "Agent 项目")
        self.VERSION = os.getenv("VERSION", "1.0.0")
        self.DESCRIPTION = os.getenv(
            "DESCRIPTION", "一个基于 Langfuse 集成的生产就绪 FastAPI 模板，用于构建智能体应用"
        )
        self.API_V1_STR = os.getenv("API_V1_STR", "/api/v1")
        self.DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "t", "yes")

        # CORS 设置
        self.ALLOWED_ORIGINS = parse_list_from_env("ALLOWED_ORIGINS", ["*"])

        # Langfuse 设置
        self.LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        self.LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
        self.LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        # LangGraph 设置
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-5-mini")
        # qwen的LLM模型配置
        self.DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
        self.DASHSCOPE_API_BASE = os.getenv("DASHSCOPE_API_BASE", "")
        self.DASHSCOPE_DEFAULT_LLM_MODEL = os.getenv("DASHSCOPE_DEFAULT_LLM_MODEL", "")
        self.DASHSCOPE_SUMMARY_LLM_MODEL = os.getenv("DASHSCOPE_SUMMARY_LLM_MODEL") or self.DASHSCOPE_DEFAULT_LLM_MODEL
        self.DASHSCOPE_PLAN_LLM_MODEL = os.getenv("DASHSCOPE_PLAN_LLM_MODEL") or self.DASHSCOPE_DEFAULT_LLM_MODEL
        self.DASHSCOPE_SUBAGENT_LLM_MODEL = os.getenv("DASHSCOPE_SUBAGENT_LLM_MODEL") or self.DASHSCOPE_DEFAULT_LLM_MODEL
        # LLM通用模型配置
        self.DEFAULT_LLM_TEMPERATURE = float(os.getenv("DEFAULT_LLM_TEMPERATURE", "0.2"))
        self.MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
        self.MAX_LLM_CALL_RETRIES = int(os.getenv("MAX_LLM_CALL_RETRIES", "3"))

        # Postgres 设置
        self.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
        self.POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
        self.POSTGRES_DB = os.getenv("POSTGRES_DB", "")
        self.POSTGRES_USER = os.getenv("POSTGRES_USER", "")
        self.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
        self.POSTGRES_POOL_SIZE = int(os.getenv("POSTGRES_POOL_SIZE", "20"))
        self.POSTGRES_MAX_OVERFLOW = int(os.getenv("POSTGRES_MAX_OVERFLOW", "10"))
        self.CHECKPOINT_TABLES = ["checkpoint_blobs", "checkpoint_writes", "checkpoints"]
        
        # 之后会取消mem0的长期记忆，改为更简单的langgraph实现
        # 长期记忆 设置
        self.LONG_TERM_MEMORY_MODEL = os.getenv("LONG_TERM_MEMORY_MODEL", "gpt-5-nano")
        self.LONG_TERM_MEMORY_EMBEDDER_MODEL = os.getenv("LONG_TERM_MEMORY_EMBEDDER_MODEL", "text-embedding-3-small")
        self.LONG_TERM_MEMORY_COLLECTION_NAME = os.getenv("LONG_TERM_MEMORY_COLLECTION_NAME", "longterm_memory")
        
        # JWT 设置
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_DAYS", "30"))

        # Logging 设置
        # 如果LOG_DIR是相对路径，则self.LOG_DIR是相对路径（相对当前工作目录，即允许命令的目录）
        # 一般在项目根目录运行项目，得到的日志根目录也在根目录的下一级
        self.LOG_DIR = Path(os.getenv("LOG_DIR", "../logs"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # "json" or "console"
        # 速率限制
        self.RATE_LIMIT_DEFAULT = parse_list_from_env("RATE_LIMIT_DEFAULT", ["200 per day", "50 per hour"])

        # 速率限制默认值
        default_endpoints = {
            "chat": ["30 per minute"],
            "chat_stream": ["20 per minute"],
            "messages": ["50 per minute"],
            "register": ["10 per hour"],
            "login": ["20 per minute"],
            "root": ["10 per minute"],
            "health": ["20 per minute"],
        }

        # 速率限制端点从环境变量更新为速率限制默认值
        self.RATE_LIMIT_ENDPOINTS = default_endpoints.copy()
        for endpoint in default_endpoints:
            env_key = f"RATE_LIMIT_{endpoint.upper()}"
            value = parse_list_from_env(env_key)
            if value:
                self.RATE_LIMIT_ENDPOINTS[endpoint] = value

        # 和风天气 API 设置
        self.QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY", "")
        self.QWEATHER_API_HOST = os.getenv("QWEATHER_API_HOST", "")

        # 高德地图 API 设置
        self.AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
        self.VITE_AMAP_WEB_JS_KEY = os.getenv("VITE_AMAP_WEB_JS_KEY", "")

        # RAG 知识库检索设置
        self.RAG_COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "travel_knowledge")
        self.RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "500"))
        self.RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
        self.RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
        self.RAG_FORCE_REBUILD = os.getenv("RAG_FORCE_REBUILD", "false").lower() in ("true", "1", "t", "yes")

        # # 评估配置
        # self.EVALUATION_LLM = os.getenv("EVALUATION_LLM", "gpt-5")
        # self.EVALUATION_BASE_URL = os.getenv("EVALUATION_BASE_URL", "https://api.openai.com/v1")
        # self.EVALUATION_API_KEY = os.getenv("EVALUATION_API_KEY", self.OPENAI_API_KEY)
        # self.EVALUATION_SLEEP_TIME = int(os.getenv("EVALUATION_SLEEP_TIME", "10"))

        # 应用环境特定的设置
        self.apply_environment_settings()

    def apply_environment_settings(self):
        """根据当前环境应用环境特定的设置。"""
        env_settings = {
            Environment.DEVELOPMENT: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "200 per hour"],
            },
            Environment.PRODUCTION: {
                "DEBUG": False,
                "LOG_LEVEL": "WARNING",
                "RATE_LIMIT_DEFAULT": ["200 per day", "50 per hour"],
            },
            Environment.TEST: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "1000 per hour"],  # Relaxed for testing
            },
        }

        # 获取当前环境的设置。
        current_env_settings = env_settings.get(self.ENVIRONMENT, {})

        # 如果环境变量中没有设置当前环境的设置，则应用当前环境的设置。
        for key, value in current_env_settings.items():
            env_var_name = key.upper()
            # 如果环境变量中没有设置当前环境的设置，则应用当前环境的设置。
            if env_var_name not in os.environ:
                setattr(self, key, value)


# 创建设置实例
settings = Settings()
