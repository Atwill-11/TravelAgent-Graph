from dotenv import load_dotenv
import os

import uvicorn
from datetime import datetime
from typing import (
    Any,
    Dict,
)
from contextlib import asynccontextmanager
from fastapi import (
    FastAPI,
    Request,
    status,
)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from langfuse import Langfuse
from app.core.middleware import logging_context_middleware
from app.core.config import settings
from app.core.logging import logger
from app.core.limiter import limiter
from app.api.v1.api import api_router

from app.services.database import database_service
from app.core.langgraph.agents.travel_plan_agent.graph import (
    _get_memory_manager,
    _get_checkpointer,
    _cleanup_resources,
)

# 从.env文件中加载环境变量
load_dotenv()

# lagfuse初始化
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。
    
    在应用启动时初始化资源，在应用关闭时清理资源。
    """
    # ========== 启动时 ==========
    logger.info("应用启动中...")
    
    # 初始化旅游规划助手的连接池
    try:
        await _get_memory_manager()
        logger.info("旅游规划助手初始化成功")
    except Exception as e:
        logger.error("旅游规划助手初始化失败", error=str(e), exc_info=True)
    
    # 初始化检查点器
    try:
        await _get_checkpointer()
        logger.info("检查点器初始化成功")
    except Exception as e:
        logger.error("检查点器初始化失败", error=str(e), exc_info=True)
    
    logger.info("应用启动完成")
    
    yield  # 应用运行中...
    
    # ========== 关闭时 ==========
    logger.info("应用关闭中...")
    
    # 清理旅游规划助手资源
    try:
        await _cleanup_resources(wait_for_tasks=False)
        logger.info("旅游规划助手资源已清理")
    except Exception as e:
        logger.error("清理旅游规划助手资源失败", error=str(e), exc_info=True)
    
    # 其他清理逻辑...
    # 例如：关闭数据库连接、清理缓存等
    
    logger.info("应用已关闭")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

"""
CORS 跨域资源共享 - 必须在其他中间件之前添加
allow_origins: 设置允许的来源
allow_credentials: 允许携带cookie
"""
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

"""
添加路由到 FastAPI 应用中
prefix用于给路由添加前缀，例如 /api/v1/check_env
"""
app.include_router(api_router, prefix=settings.API_V1_STR)

"""
添加中间件（注意：装饰器必须在定义 app 之后使用）
日志上下文中间件，用于在请求处理过程中添加用户ID到日志上下文
"""
app.middleware("http")(logging_context_middleware)

# 速率限制中间件
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 添加验证异常处理器
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求数据中的校验错误。

    参数:
        request: 触发校验错误的请求对象
        exc: 校验错误异常实例（如 Pydantic ValidationError）

    返回:
        JSONResponse: 标准化格式的错误响应，示例：
        {
            "error": "validation_failed",
            "message": "请求参数校验失败",
            "details": [...],  # 具体字段错误信息
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """
    # 记录校验错误日志
    logger.error(
        "validation_error",
        client_host=request.client.host if request.client else "unknown",
        path=request.url.path,
        errors=str(exc.errors()),
    )

    # 格式化错误信息，移除 body 字段
    formatted_errors = []
    for error in exc.errors():
        loc = " -> ".join([str(loc_part) for loc_part in error["loc"] if loc_part != "body"])
        formatted_errors.append({"field": loc, "message": error["msg"]})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": formatted_errors},
    )

@app.get("/")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["root"][0])
async def root(request: Request):
    """根接口返回基本API信息"""
    logger.info("root_endpoint_called")
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "environment": settings.ENVIRONMENT.value,
        "swagger_url": "/docs",
        "redoc_url": "/redoc",
    }

@app.get("/health")
async def health_check(request: Request) -> Dict[str, Any]:
    """健康检查接口（包含环境变量）
    Returns:
        Dict[str, Any]: 健康检查结果
    """
    logger.info("health_check_called（包含环境变量）")

    # 检查数据库连接
    db_healthy = await database_service.health_check()

    response = {
        "status": "healthy" if db_healthy else "degraded",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT.value,
        "components": {"api": "healthy", "database": "healthy" if db_healthy else "unhealthy"},
        "timestamp": datetime.now().isoformat(),
    }

    # 如果数据库连接失败，设置为503 Service Unavailable
    status_code = status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(content=response, status_code=status_code)

# if __name__ == "__main__":
#     uvicorn.run(
#         "app.main:app",
#         reload=True,
#         reload_excludes=["projectlogs/**/*"],  # 排除日志目录
#         host="0.0.0.0",
#         port=8000,
#     )