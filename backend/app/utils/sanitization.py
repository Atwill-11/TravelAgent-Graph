"""本文件包含应用程序的数据清洗工具函数。"""

import html
import re
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
)


def sanitize_string(value: str) -> str:
    """清洗字符串以防止 XSS 及其他注入攻击。

    参数:
        value: 待清洗的字符串。

    返回:
        str: 清洗后的字符串。
    """
    # 如果不是字符串类型则转换为字符串
    if not isinstance(value, str):
        value = str(value)

    # HTML 转义以防止 XSS 攻击
    value = html.escape(value)

    # 移除可能已被转义的 script 标签
    value = re.sub(r"&lt;script.*?&gt;.*?&lt;/script&gt;", "", value, flags=re.DOTALL)

    # 移除空字节
    value = value.replace("\0", "")

    return value


def sanitize_email(email: str) -> str:
    """清洗邮箱地址。

    参数:
        email: 待清洗的邮箱地址。

    返回:
        str: 清洗后的邮箱地址。
    """
    # 基础清洗
    email = sanitize_string(email)

    # 验证邮箱格式（基础校验）
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValueError("Invalid email format")

    return email.lower()


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """递归清洗字典中的所有字符串值。

    参数:
        data: 待清洗的字典。

    返回:
        Dict[str, Any]: 清洗后的字典。
    """
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = sanitize_list(value)
        else:
            sanitized[key] = value
    return sanitized


def sanitize_list(data: List[Any]) -> List[Any]:
    """递归清洗列表中的所有字符串值。

    参数:
        data: 待清洗的列表。

    返回:
        List[Any]: 清洗后的列表。
    """
    sanitized = []
    for item in data:
        if isinstance(item, str):
            sanitized.append(sanitize_string(item))
        elif isinstance(item, dict):
            sanitized.append(sanitize_dict(item))
        elif isinstance(item, list):
            sanitized.append(sanitize_list(item))
        else:
            sanitized.append(item)
    return sanitized


def validate_password_strength(password: str) -> bool:
    """验证密码强度。

    参数:
        password: 待验证的密码。

    返回:
        bool: 密码强度是否达标。

    异常:
        ValueError: 当密码强度不足时抛出，并附带具体原因。
    """
    if len(password) < 8:
        raise ValueError("密码长度必须至少8个字符")

    if not re.search(r"[A-Z]", password):
        raise ValueError("密码必须包含至少一个大写字母")

    if not re.search(r"[a-z]", password):
        raise ValueError("密码必须包含至少一个小写字母")

    if not re.search(r"[0-9]", password):
        raise ValueError("密码必须包含至少一个数字")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError("密码必须包含至少一个特殊字符")

    return True
