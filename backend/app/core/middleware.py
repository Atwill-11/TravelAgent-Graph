from typing import Callable
from jose import (
    JWTError,
    jwt,
)

from fastapi import Request

from app.core.config import settings
from app.core.logging import (
    bind_context,
    clear_context,
)

async def logging_context_middleware(request: Request, call_next: Callable):
    """日志上下文中间件，用于将用户 ID 和会话 ID 添加到日志上下文。
    
    Args:
        request: 输入应用的请求
        call_next: 下一个中间件或路由处理函数
    
    Returns:
        Response: 应用的响应
    """
    try:
        # 清除上一个请求的上下文
        clear_context()
        
        # 从请求头中提取 Authorization 头中提取 JWT 令牌
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
            try:
                # 提取会话 ID（存储在 JWT 中的 "sub" 断言）
                payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
                session_id = payload.get("sub")
                
                if session_id:
                    bind_context(session_id=session_id)
                    
            except JWTError:
                # 令牌无效，但不失败请求，让认证依赖项处理
                pass
        
        # 处理请求
        response = await call_next(request)
        
        # 检查请求状态中是否添加了用户信息
        if hasattr(request.state, "user_id"):
            bind_context(user_id=request.state.user_id)
        
        return response
    
    finally:
        # 无论是否成功，都清除上下文
        clear_context()