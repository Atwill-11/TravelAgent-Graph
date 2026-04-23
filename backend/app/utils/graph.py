"""本文件包含应用程序的图（Graph）相关工具函数。"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.messages import trim_messages as _trim_messages

from app.core.config import settings
from app.core.logging import logger
from app.schemas import Message


def dump_messages(messages: list[Message]) -> list[dict]:
    """将消息列表转换为字典列表。

    参数:
        messages (list[Message]): 待转换的消息列表。

    返回:
        list[dict]: 转换后的字典列表。

    示例:
        from app.schemas import Message
        msgs = [
            Message(role="user", content="今天天气怎么样？"),
            Message(role="assistant", content="北京晴，25℃，适合外出。")
        ]
        dump_messages(msgs)结果：
        [
            {'role': 'user', 'content': '今天天气怎么样？'}, 
            {'role': 'assistant', 'content': '北京晴，25℃，适合外出。'}
        ]
    """
    return [message.model_dump() for message in messages]


def process_llm_response(response: BaseMessage) -> BaseMessage:
    """处理 LLM 响应，以支持结构化内容块（例如 GPT-5 系列模型的返回格式）。

    GPT-5 系列模型返回的内容为内容块列表，格式如下：
    [
        {'id': '...', 'summary': [], 'type': 'reasoning'},
        {'type': 'text', 'text': '实际回复内容'}
    ]

    本函数从此类结构中提取实际的文本内容。输出示例：
    response = AIMessage(
        content='这是实际的回复内容'  # 只保留文本内容
    )

    参数:
        response: LLM 返回的原始响应。

    返回:
        BaseMessage: 内容已处理的响应对象。
    """
    if isinstance(response.content, list):
        # 从内容块中提取文本
        text_parts = []
        for block in response.content:
            if isinstance(block, dict):
                # 处理文本块
                if block.get("type") == "text" and "text" in block:
                    text_parts.append(block["text"])
                # 记录推理块以便调试
                elif block.get("type") == "reasoning":
                    logger.debug(
                        "收到推理内容块",
                        reasoning_id=block.get("id"),
                        has_summary=bool(block.get("summary")),
                    )
            elif isinstance(block, str):
                text_parts.append(block)

        # 拼接所有文本片段
        response.content = "".join(text_parts)
        logger.debug(
            "结构化内容处理完成",
            block_count=len(response.content) if isinstance(response.content, list) else 1,
            extracted_length=len(response.content) if isinstance(response.content, str) else 0,
        )

    return response


def prepare_messages(messages: list[Message], llm: BaseChatModel, system_prompt: str) -> list[Message]:
    """为 LLM 准备消息列表。

    参数:
        messages (list[Message]): 待处理的消息列表。
        llm (BaseChatModel): 使用的 LLM 实例。
        system_prompt (str): 系统提示词。

    返回:
        list[Message]: 处理完成的消息列表。
    """
    try:
        trimmed_messages = _trim_messages(
            dump_messages(messages),
            strategy="last",
            token_counter=llm,
            max_tokens=settings.MAX_TOKENS,
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
    except ValueError as e:
        # 处理无法识别的内容块类型（例如 GPT-5 的 reasoning 块）
        if "Unrecognized content block type" in str(e):
            logger.warning(
                "Token 计数失败，跳过消息裁剪",
                error=str(e),
                message_count=len(messages),
            )
            # 跳过裁剪，返回全部消息
            trimmed_messages = messages
        else:
            raise

    return [Message(role="system", content=system_prompt)] + trimmed_messages