"""API路由模块。

该模块定义了根目录下的路由，用于整合其他路由模块。
路由的结构：
api/v1（当前文件）
    - 路由模块1（路由文件1.py）
    - 路由模块2（路由文件2.py）...

模块间通过include_router方法进行集成。
"""
from fastapi import APIRouter
from app.core.config import settings
from app.core.logging import logger
from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.api.v1.travel import router as travel_router

api_router = APIRouter()
# 挂载auth路由
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
# 挂载chatbot路由
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
# 挂载travel路由
api_router.include_router(travel_router, prefix="/trip", tags=["旅游计划"])

"""
测试使用的路由，用于检查环境变量是否加载正确。
"""
@api_router.get("/check_env")
async def check_environment():
    return {
        "environment": settings.ENVIRONMENT.value,
        "project_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "langfuse_host": settings.LANGFUSE_HOST,
        "default_llm_model": settings.DEFAULT_LLM_MODEL,
        "postgres_host": settings.POSTGRES_HOST,
        "postgres_db": settings.POSTGRES_DB,
    }

"""
简单的健康检查路由，用于检查应用是否正常运行。
"""
@api_router.get("/health")
async def health_check():
    """健康检查接口（简单）

    Returns:
        dict: 健康检查结果
    """
    logger.info("health_check_called（简单）")
    return {"status": "healthy", "version": "1.0.0"}