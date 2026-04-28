"""API 的身份认证与授权端点模块。

本模块提供用户注册、登录、会话管理及 token 验证等相关端点。
"""

import uuid
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import (
    bind_context,
    logger,
)
from app.core.langgraph.agents.travel_plan_agent.graph import _get_memory_manager
from app.models.session import Session
from app.models.user import User
from app.schemas import (
    SessionResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.database import DatabaseService
from app.utils.auth import (
    create_access_token,
    verify_token,
)
from app.utils.sanitization import (
    sanitize_email,
    sanitize_string,
    validate_password_strength,
)

router = APIRouter()
security = HTTPBearer()
db_service = DatabaseService()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """从 token 中获取当前用户信息。

    参数:
        credentials: 包含 JWT token 的 HTTP 授权凭证。

    返回:
        User: 从 token 中解析出的用户对象。

    异常:
        HTTPException: 当 token 无效或缺失时抛出。
    """
    try:
        # 对 token 进行清洗处理
        token = sanitize_string(credentials.credentials)

        user_id = verify_token(token)
        if user_id is None:
            logger.error("invalid_token（token 无效）", token_part=token[:10] + "...")
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials（token 无效）",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 验证用户在数据库中是否存在
        user_id_int = int(user_id)
        user = await db_service.get_user(user_id_int)
        if user is None:
            logger.error("user_not_found（用户不存在）", user_id=user_id_int)
            raise HTTPException(
                status_code=404,
                detail="User not found（用户不存在）",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 将 user_id 绑定到日志上下文，便于后续日志追踪
        bind_context(user_id=user_id_int)

        return user
    except ValueError as ve:
        logger.error("token_validation_failed（token 验证失败）", error=str(ve), exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="Invalid token format（token 格式无效）",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Session:
    """从 token 中获取当前会话信息。

    参数:
        credentials: 包含 JWT token 的 HTTP 授权凭证。

    返回:
        Session: 从 token 中解析出的会话对象。

    异常:
        HTTPException: 当 token 无效或缺失时抛出。
    """
    try:
        # 对 token 进行清洗处理
        token = sanitize_string(credentials.credentials)

        session_id = verify_token(token)
        if session_id is None:
            logger.error("session_id_not_found（token 中未找到会话 ID）", token_part=token[:10] + "...")
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 对 session_id 进行清洗处理
        session_id = sanitize_string(session_id)

        # 验证会话在数据库中是否存在
        session = await db_service.get_session(session_id)
        if session is None:
            logger.error("session_not_found（会话不存在）", session_id=session_id)
            raise HTTPException(
                status_code=404,
                detail="Session not found（会话不存在）",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 将 user_id 绑定到日志上下文，便于后续日志追踪
        bind_context(user_id=session.user_id)

        return session
    except ValueError as ve:
        logger.error("token_validation_failed（token 验证失败）", error=str(ve), exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/register", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_user(request: Request, user_data: UserCreate):
    """注册新用户。

    参数:
        request: FastAPI 请求对象，用于速率限制。
        user_data: 用户注册数据。

    返回:
        UserResponse: 创建成功的用户信息。
    """
    try:
        # 清洗邮箱地址
        sanitized_email = sanitize_email(user_data.email)

        # 提取并验证密码
        password = user_data.password.get_secret_value()
        validate_password_strength(password)

        # 检查用户是否已存在
        if await db_service.get_user_by_email(sanitized_email):
            raise HTTPException(status_code=400, detail="Email already registered（邮箱已注册）")

        # 创建用户
        user = await db_service.create_user(email=sanitized_email, password=User.hash_password(password))

        # 创建访问 token
        token = create_access_token(str(user.id))

        return UserResponse(id=user.id, email=user.email, token=token)
    except ValueError as ve:
        logger.error("user_registration_validation_failed（用户注册参数校验失败）", error=str(ve), exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login(
    request: Request, username: str = Form(...), password: str = Form(...), grant_type: str = Form(default="password")
):
    """用户登录。

    参数:
        request: FastAPI 请求对象，用于速率限制。
        username: 用户邮箱。
        password: 用户密码。
        grant_type: 必须为 "password"。

    返回:
        TokenResponse: 访问 token 信息。

    异常:
        HTTPException: 当凭证无效时抛出。
    """
    try:
        # 清洗输入参数
        username = sanitize_string(username)
        password = sanitize_string(password)
        grant_type = sanitize_string(grant_type)

        # 验证 grant_type 是否为 password 类型
        if grant_type != "password":
            raise HTTPException(
                status_code=400,
                detail="Unsupported grant type. Must be 'password'",
            )

        user = await db_service.get_user_by_email(username)
        if not user or not user.verify_password(password):
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = create_access_token(str(user.id))
        return TokenResponse(access_token=token.access_token, token_type="bearer", expires_at=token.expires_at)
    except ValueError as ve:
        logger.error("login_validation_failed（登录参数校验失败）", error=str(ve), exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/session", response_model=SessionResponse)
async def create_session(user: User = Depends(get_current_user), name: str = Form(default="")):
    """为已认证用户创建新的聊天会话。

    参数:
        user: 已认证的用户对象。
        name: 会话名称（可选）。

    返回:
        SessionResponse: 会话 ID、名称及访问 token。
    """
    try:
        # 生成唯一的会话 ID
        session_id = str(uuid.uuid4())
        
        # 清洗会话名称
        sanitized_name = sanitize_string(name) if name else ""

        # 在数据库中创建会话记录
        session = await db_service.create_session(session_id, user.id, sanitized_name)

        # 为该会话创建访问 token
        token = create_access_token(session_id)

        logger.info(
            "session_created（会话创建成功）",
            session_id=session_id,
            user_id=user.id,
            name=session.name,
            expires_at=token.expires_at.isoformat(),
        )

        return SessionResponse(session_id=session_id, name=session.name, token=token)
    except ValueError as ve:
        logger.error("session_creation_validation_failed（会话创建参数校验失败）", error=str(ve), user_id=user.id, exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.patch("/session/{session_id}/name", response_model=SessionResponse)
async def update_session_name(
    session_id: str, name: str = Form(...), user: User = Depends(get_current_user)
):
    """更新会话名称。

    参数:
        session_id: 待更新的会话 ID。
        name: 新的会话名称。
        user: 已认证的用户对象。

    返回:
        SessionResponse: 更新后的会话信息。
    """
    try:
        # 清洗输入参数
        sanitized_session_id = sanitize_string(session_id)
        sanitized_name = sanitize_string(name)

        # 验证会话是否属于当前用户
        session = await db_service.get_session(sanitized_session_id)
        if session is None or session.user_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot modify other sessions")

        # 更新会话名称
        updated_session = await db_service.update_session_name(sanitized_session_id, sanitized_name)

        # 创建新 token
        token = create_access_token(sanitized_session_id)

        return SessionResponse(session_id=sanitized_session_id, name=updated_session.name, token=token)
    except ValueError as ve:
        logger.error("session_update_validation_failed（会话更新参数校验失败）", error=str(ve), session_id=session_id, exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, user: User = Depends(get_current_user)):
    """删除已认证用户的会话。

    参数:
        session_id: 待删除的会话 ID。
        user: 已认证的用户对象。

    返回:
        None
    """
    try:
        # 清洗输入参数
        sanitized_session_id = sanitize_string(session_id)

        # 验证会话是否属于当前用户
        session = await db_service.get_session(sanitized_session_id)
        if session is None or session.user_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot delete other sessions")

        # 删除会话相关的历史规划记忆
        try:
            memory_manager = await _get_memory_manager()
            if memory_manager:
                await memory_manager.delete_session_memories(str(user.id), sanitized_session_id)
        except Exception as e:
            logger.warning("删除会话记忆失败，继续删除会话", session_id=sanitized_session_id, error=str(e))

        # 删除会话
        await db_service.delete_session(sanitized_session_id)

        logger.info("session_deleted（会话删除成功）", session_id=session_id, user_id=user.id)
    except ValueError as ve:
        logger.error("session_deletion_validation_failed（会话删除参数校验失败）", session_id=session_id, exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.get("/sessions", response_model=List[SessionResponse])
async def get_user_sessions(user: User = Depends(get_current_user)):
    """获取已认证用户的所有会话列表。

    参数:
        user: 已认证的用户对象。

    返回:
        List[SessionResponse]: 会话信息列表。
    """
    try:
        sessions = await db_service.get_user_sessions(user.id)
        return [
            SessionResponse(
                session_id=sanitize_string(session.id),
                name=sanitize_string(session.name),
                token=create_access_token(session.id),
            )
            for session in sessions
        ]
    except ValueError as ve:
        logger.error("get_sessions_validation_failed（获取会话列表参数校验失败）", user_id=user.id, error=str(ve), exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))
