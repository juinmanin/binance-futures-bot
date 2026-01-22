"""서킷 브레이커 패턴"""
import time
from typing import Callable, Any, TypeVar
from functools import wraps
from loguru import logger


T = TypeVar('T')


class CircuitBreakerOpen(Exception):
    """서킷 브레이커가 열려있을 때 발생하는 예외"""
    pass


class CircuitBreaker:
    """
    서킷 브레이커 패턴 구현
    
    상태:
    - CLOSED: 정상 동작 (에러 카운트)
    - OPEN: 차단 상태 (모든 요청 차단)
    - HALF_OPEN: 복구 시도 (일부 요청 허용)
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        초기화
        
        Args:
            failure_threshold: 실패 임계값 (이 횟수만큼 실패하면 OPEN)
            reset_timeout: 리셋 타임아웃 (초) - OPEN 상태 유지 시간
            expected_exception: 카운트할 예외 타입
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.expected_exception = expected_exception
        
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time = None
        
        logger.info(
            f"CircuitBreaker initialized: "
            f"threshold={failure_threshold}, timeout={reset_timeout}s"
        )
    
    def _on_success(self):
        """성공 시 호출"""
        self.failures = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            logger.info("CircuitBreaker: HALF_OPEN -> CLOSED")
    
    def _on_failure(self):
        """실패 시 호출"""
        self.failures += 1
        self.last_failure_time = time.time()
        
        logger.warning(
            f"CircuitBreaker: failure count = {self.failures}/{self.failure_threshold}"
        )
        
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(
                f"CircuitBreaker: CLOSED -> OPEN (threshold reached)"
            )
    
    def _can_attempt(self) -> bool:
        """요청 시도 가능 여부 확인"""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            # 타임아웃이 지났는지 확인
            if self.last_failure_time and \
               time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
                self.failures = 0
                logger.info("CircuitBreaker: OPEN -> HALF_OPEN (timeout expired)")
                return True
            return False
        
        if self.state == "HALF_OPEN":
            # HALF_OPEN 상태에서는 일부 요청 허용
            return True
        
        return False
    
    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        보호된 함수 호출
        
        Args:
            func: 호출할 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자
            
        Returns:
            함수 실행 결과
            
        Raises:
            CircuitBreakerOpen: 서킷 브레이커가 OPEN 상태일 때
        """
        if not self._can_attempt():
            raise CircuitBreakerOpen(
                f"서비스 일시 중단 (CircuitBreaker OPEN, "
                f"retry after {self.reset_timeout}s)"
            )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def reset(self):
        """서킷 브레이커 리셋"""
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time = None
        logger.info("CircuitBreaker reset to CLOSED")


def circuit_breaker(
    failure_threshold: int = 5,
    reset_timeout: int = 60,
    expected_exception: type = Exception
):
    """
    서킷 브레이커 데코레이터
    
    Args:
        failure_threshold: 실패 임계값
        reset_timeout: 리셋 타임아웃 (초)
        expected_exception: 카운트할 예외 타입
        
    Returns:
        데코레이터 함수
    """
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        reset_timeout=reset_timeout,
        expected_exception=expected_exception
    )
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    
    return decorator
