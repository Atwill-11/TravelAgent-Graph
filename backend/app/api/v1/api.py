"""API路由模块。

该模块定义了根目录下的路由，用于整合其他路由模块。
路由的结构：
api/v1（当前文件）
    - 路由模块1（路由文件1.py）
    - 路由模块2（路由文件2.py）...

模块间通过include_router方法进行集成。
"""
from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.travel import router as travel_router
from app.api.v1.rag import router as rag_router

api_router = APIRouter()
# 挂载auth路由
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
# 挂载travel路由
api_router.include_router(travel_router, prefix="/trip", tags=["旅游计划"])
# 挂载rag路由
api_router.include_router(rag_router, prefix="/rag", tags=["RAG知识库管理"])

