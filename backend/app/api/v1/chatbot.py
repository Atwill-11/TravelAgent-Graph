"""聊天机器人 API 端点，用于处理聊天交互。

本模块提供聊天交互相关的端点，包括常规聊天、流式聊天、消息历史管理和聊天历史清除。
"""

import json
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import StreamingResponse

from app.api.v1.auth import get_current_session
from app.core.config import settings
from app.core.langgraph.graph import LangGraphAgent
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Message,
    StreamResponse,
)

router = APIRouter()
agent = LangGraphAgent()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat(
    request: Request,
    chat_request: ChatRequest,
    # 通过Depends，调用get_current_session的返回值作为session
    session: Session = Depends(get_current_session),
):
    """使用 LangGraph 处理聊天请求。

    参数:
        request: 用于速率限制的 FastAPI 请求对象。
        chat_request: 包含消息的聊天请求。
        session: 来自认证令牌的当前会话。

    返回:
        ChatResponse: 处理后的聊天响应。

    异常:
        HTTPException: 如果处理请求时发生错误。
    """
    try:
        logger.info(
            "收到聊天请求",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        result = await agent.get_response(chat_request.messages, session.id, user_id=session.user_id)

        logger.info("聊天请求处理完成", session_id=session.id, user_id=session.user_id)

        return ChatResponse(messages=result)
    except Exception as e:
        logger.error("聊天请求失败", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """使用 LangGraph 处理带有流式响应的聊天请求。

    参数:
        request: 用于速率限制的 FastAPI 请求对象。
        chat_request: 包含消息的聊天请求。
        session: 来自认证令牌的当前会话。

    返回:
        StreamingResponse: 聊天完成的流式响应。

    异常:
        HTTPException: 如果处理请求时发生错误。
    """
    try:
        logger.info(
            "收到流式聊天请求",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        async def event_generator():
            """生成流式事件。

            产出:
                str: JSON 格式的服务器发送事件 (SSE)。

            异常:
                Exception: 如果流式传输过程中发生错误。
            """
            try:
                full_response = ""
                async for chunk in agent.get_stream_response(
                    chat_request.messages, session.id, user_id=session.user_id
                ):
                    # ✅ 优化 1: 过滤掉空字符串，减少前端无效渲染
                    if not chunk or chunk.strip() == "":
                        continue
                    
                    full_response += chunk
                    response = StreamResponse(content=chunk, done=False)

                    # ✅ 优化 2: ensure_ascii=False 让中文直接显示，而不是 \uXXXX
                    # 注意：SSE 协议要求每行以 \n\n 结尾，json.dumps 默认处理字符串
                    yield f"data: {json.dumps(response.model_dump(), ensure_ascii=False)}\n\n"

                # 发送表示完成的最终消息
                final_response = StreamResponse(content="", done=True)
                yield f"data: {json.dumps(final_response.model_dump())}\n\n"

            except Exception as e:
                logger.error(
                    "流式聊天请求失败",
                    session_id=session.id,
                    error=str(e),
                    exc_info=True,
                )
                error_response = StreamResponse(content=str(e), done=True)
                yield f"data: {json.dumps(error_response.model_dump())}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(
            "流式聊天请求失败",
            session_id=session.id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def get_session_messages(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """获取会话的所有消息。

    参数:
        request: 用于速率限制的 FastAPI 请求对象。
        session: 来自认证令牌的当前会话。

    返回:
        ChatResponse: 会话中的所有消息。

    异常:
        HTTPException: 如果检索消息时发生错误。
    """
    try:
        messages = await agent.get_chat_history(session.id)
        return ChatResponse(messages=messages)
    except Exception as e:
        logger.error("获取消息失败", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/messages")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def clear_chat_history(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """清除会话的所有消息。

    参数:
        request: 用于速率限制的 FastAPI 请求对象。
        session: 来自认证令牌的当前会话。

    返回:
        dict: 指示聊天历史已成功清除的消息。
    """
    try:
        await agent.clear_chat_history(session.id)
        return {"message": "聊天历史已成功清除"}
    except Exception as e:
        logger.error("清除聊天历史失败", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
