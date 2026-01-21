"""커스텀 예외 클래스"""
from typing import Any, Optional


class TradingBotException(Exception):
    """기본 예외 클래스"""
    
    def __init__(self, message: str, details: Optional[Any] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


class BinanceAPIException(TradingBotException):
    """바이낸스 API 관련 예외"""
    pass


class AuthenticationException(TradingBotException):
    """인증 관련 예외"""
    pass


class DatabaseException(TradingBotException):
    """데이터베이스 관련 예외"""
    pass


class EncryptionException(TradingBotException):
    """암호화 관련 예외"""
    pass


class ValidationException(TradingBotException):
    """검증 관련 예외"""
    pass


class OrderException(TradingBotException):
    """주문 관련 예외"""
    pass


class WebSocketException(TradingBotException):
    """WebSocket 관련 예외"""
    pass
