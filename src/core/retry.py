"""재시도 로직"""
import asyncio
from typing import TypeVar, Callable, Any
from functools import wraps
from loguru import logger

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    logger.warning("tenacity not available, using fallback retry implementation")

from src.core.exceptions import BinanceAPIException


T = TypeVar('T')


class RetryHandler:
    """API 호출 재시도 로직"""
    
    @staticmethod
    def with_retry(
        max_attempts: int = 3,
        min_wait: int = 1,
        max_wait: int = 10,
        multiplier: int = 1
    ):
        """
        지수 백오프를 사용한 재시도 데코레이터
        
        Args:
            max_attempts: 최대 시도 횟수
            min_wait: 최소 대기 시간 (초)
            max_wait: 최대 대기 시간 (초)
            multiplier: 대기 시간 배수
            
        Returns:
            데코레이터 함수
        """
        if TENACITY_AVAILABLE:
            return retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
                retry=retry_if_exception_type(BinanceAPIException),
                before_sleep=before_sleep_log(logger, logger.level("WARNING").no),
                reraise=True
            )
        else:
            # Fallback implementation without tenacity
            def decorator(func: Callable[..., T]) -> Callable[..., T]:
                @wraps(func)
                async def wrapper(*args: Any, **kwargs: Any) -> T:
                    last_exception = None
                    for attempt in range(max_attempts):
                        try:
                            return await func(*args, **kwargs)
                        except BinanceAPIException as e:
                            last_exception = e
                            if attempt < max_attempts - 1:
                                wait_time = min(min_wait * (multiplier ** attempt), max_wait)
                                logger.warning(
                                    f"Attempt {attempt + 1}/{max_attempts} failed: {e}, "
                                    f"retrying in {wait_time}s..."
                                )
                                await asyncio.sleep(wait_time)
                            else:
                                logger.error(f"All {max_attempts} attempts failed")
                    
                    if last_exception:
                        raise last_exception
                    
                return wrapper
            return decorator
    
    @staticmethod
    async def execute_with_retry(
        func: Callable[..., T],
        *args: Any,
        max_attempts: int = 3,
        **kwargs: Any
    ) -> T:
        """
        함수를 재시도 로직과 함께 실행
        
        Args:
            func: 실행할 함수
            *args: 함수 인자
            max_attempts: 최대 시도 횟수
            **kwargs: 함수 키워드 인자
            
        Returns:
            함수 실행 결과
            
        Raises:
            BinanceAPIException: 모든 시도 실패 시
        """
        last_exception = None
        
        for attempt in range(max_attempts):
            try:
                return await func(*args, **kwargs)
            except BinanceAPIException as e:
                last_exception = e
                
                # 재시도하지 않을 에러 코드
                if hasattr(e, 'code') and e.code not in [-1001, -1003, -1021]:
                    logger.error(f"Non-retryable error: {e}")
                    raise
                
                if attempt < max_attempts - 1:
                    wait_time = 2 ** attempt  # 지수 백오프
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed: {e}, "
                        f"retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_attempts} attempts failed")
        
        if last_exception:
            raise last_exception


def retry_on_network_error(max_attempts: int = 3):
    """
    네트워크 에러 발생 시 재시도하는 데코레이터
    
    Args:
        max_attempts: 최대 시도 횟수
        
    Returns:
        데코레이터 함수
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await RetryHandler.execute_with_retry(
                func, *args, max_attempts=max_attempts, **kwargs
            )
        return wrapper
    return decorator
