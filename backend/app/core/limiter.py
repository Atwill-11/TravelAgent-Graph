"""应用程序的速率限制配置。

本模块使用 slowapi 配置速率限制，默认限制由应用程序设置定义。
速率限制基于远程 IP 地址生效。
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# 初始化速率限制器
limiter = Limiter(key_func=get_remote_address, default_limits=settings.RATE_LIMIT_DEFAULT)
