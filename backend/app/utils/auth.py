"""该文件包含了应用的认证工具函数"""

import re
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import Optional

from jose import (
    JWTError,
    jwt,
)

from app.core.config import settings
from app.core.logging import logger
from app.schemas.auth import Token
from app.utils.sanitization import sanitize_string


def create_access_token(thread_id: str, expires_delta: Optional[timedelta] = None) -> Token:
    """给线程创建一个新的访问令牌，用于会话认证。
    
    Args:
        thread_id:会话的唯一线程ID
        expires_delta:可选的过期时间时间差

    Returns:
        Token: 生成的访问令牌对象
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.JWT_ACCESS_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "sub": thread_id,
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": sanitize_string(f"{thread_id}-{datetime.now(UTC).timestamp()}"),  # 添加token唯一标识符
    }

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    logger.info("token_created（token 创建成功）", thread_id=thread_id, expires_at=expire.isoformat())

    return Token(access_token=encoded_jwt, expires_at=expire)


def verify_token(token: str) -> Optional[str]:
    """验证 JWT token 并返回session ID（thread ID）。

    参数:
        token: 待验证的 JWT token 字符串。

    返回:
        Optional[str]:  若 token 有效则返回对应的session ID（thread ID）；
                        若 token 无效或解析失败则返回 None。

    异常:
        ValueError: 当 token 格式不符合 JWT 规范（如结构错误、编码非法）时抛出。
    """
    if not token or not isinstance(token, str):
        logger.warning("token_invalid_format（token 格式无效：必须是非空字符串）")
        raise ValueError("Token must be a non-empty string（Token必须是非空字符串）")

    # 基础格式校验：在尝试解码前先验证 token 格式
    # JWT token 由 3 个经过 base64url 编码的片段组成，以点号分隔
    if not re.match(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$", token):
        logger.warning("token_suspicious_format（token 格式可疑：不符合 JWT 标准格式）")
        raise ValueError("Token format is invalid - expected JWT format")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        thread_id: str = payload.get("sub")
        if thread_id is None:
            logger.warning("token_missing_thread_id（token 验证通过但缺少话题 ID）")
            return None

        logger.info("token_verified（token 验证成功）", thread_id=thread_id)
        return thread_id

    except JWTError as e:
        logger.error("token_verification_failed（token 验证失败）", error=str(e))
        return None
