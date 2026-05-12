"""API速率限制器。

提供多种限流策略，防止API调用过快触发限流错误。
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional


class RateLimiter:
    """令牌桶算法实现的速率限制器。

    使用令牌桶算法控制请求速率，支持突发流量和平滑限流。

    Attributes:
        rate: 每秒允许的请求数
        burst_size: 令牌桶容量，允许的突发请求数
        tokens: 当前令牌数
        last_update: 上次更新时间
        lock: 异步锁，保证线程安全
    """

    def __init__(self, rate: float = 2.0, burst_size: int = 5):
        """初始化速率限制器。

        Args:
            rate: 每秒允许的请求数，默认2.0（每秒2个请求）
            burst_size: 令牌桶容量，默认5（允许5个突发请求）
        """
        self.rate = rate
        self.burst_size = burst_size
        self.tokens = float(burst_size)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        """获取令牌，如果没有足够的令牌则等待。

        Args:
            tokens: 需要获取的令牌数，默认1
        """
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst_size, self.tokens + elapsed * self.rate
            )
            self.last_update = now

            if self.tokens < tokens:
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
                self.last_update = time.monotonic()
            else:
                self.tokens -= tokens

    @asynccontextmanager
    async def limit(self, tokens: int = 1):
        """上下文管理器，自动获取和释放令牌。

        Args:
            tokens: 需要获取的令牌数

        Yields:
            None
        """
        await self.acquire(tokens)
        yield


class ExponentialBackoff:
    """指数退避重试策略。

    在遇到错误时，按照指数增长的延迟时间进行重试，
    避免立即重试导致更严重的拥塞。

    Attributes:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exponential_base: 指数基数
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ):
        """初始化指数退避策略。

        Args:
            max_retries: 最大重试次数，默认3
            base_delay: 基础延迟时间（秒），默认1.0
            max_delay: 最大延迟时间（秒），默认60.0
            exponential_base: 指数基数，默认2.0
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def get_delay(self, attempt: int) -> float:
        """计算指定重试次数的延迟时间。

        Args:
            attempt: 当前重试次数（从0开始）

        Returns:
            延迟时间（秒）
        """
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)

    async def sleep(self, attempt: int) -> None:
        """异步等待指定时间。

        Args:
            attempt: 当前重试次数（从0开始）
        """
        delay = self.get_delay(attempt)
        await asyncio.sleep(delay)


class APIRateController:
    """API调用控制器。

    结合速率限制和指数退避，提供完整的API调用保护机制。

    Attributes:
        rate_limiter: 速率限制器
        backoff: 指数退避策略
    """

    def __init__(
        self,
        rate: float = 2.0,
        burst_size: int = 5,
        max_retries: int = 3,
    ):
        """初始化API调用控制器。

        Args:
            rate: 每秒允许的请求数，默认2.0
            burst_size: 令牌桶容量，默认5
            max_retries: 最大重试次数，默认3
        """
        self.rate_limiter = RateLimiter(rate=rate, burst_size=burst_size)
        self.backoff = ExponentialBackoff(max_retries=max_retries)

    async def execute_with_retry(
        self,
        coro,
        retry_on: tuple = (Exception,),
    ):
        """执行协程，支持速率限制和自动重试。

        Args:
            coro: 要执行的协程
            retry_on: 触发重试的异常类型元组

        Returns:
            协程的执行结果

        Raises:
            最后一次重试失败的异常
        """
        last_exception = None

        for attempt in range(self.backoff.max_retries + 1):
            try:
                await self.rate_limiter.acquire()
                return await coro
            except retry_on as e:
                last_exception = e
                if attempt < self.backoff.max_retries:
                    await self.backoff.sleep(attempt)
                    continue
                raise

        raise last_exception


_llm_rate_limiter: Optional[RateLimiter] = None
_embedding_rate_limiter: Optional[RateLimiter] = None


def get_llm_rate_limiter() -> RateLimiter:
    """获取LLM调用的全局速率限制器。

    Returns:
        RateLimiter实例
    """
    global _llm_rate_limiter
    if _llm_rate_limiter is None:
        _llm_rate_limiter = RateLimiter(rate=2.0, burst_size=5)
    return _llm_rate_limiter


def get_embedding_rate_limiter() -> RateLimiter:
    """获取Embedding调用的全局速率限制器。

    Returns:
        RateLimiter实例
    """
    global _embedding_rate_limiter
    if _embedding_rate_limiter is None:
        _embedding_rate_limiter = RateLimiter(rate=5.0, burst_size=10)
    return _embedding_rate_limiter
