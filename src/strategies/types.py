"""전략 데이터 타입"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class SignalAction(str, Enum):
    """신호 액션"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class MarketCondition(str, Enum):
    """시장 환경"""
    BULLISH = "BULLISH"      # 강세장 (자금 유입)
    BEARISH = "BEARISH"      # 약세장 (자금 유출)
    NEUTRAL = "NEUTRAL"      # 중립


class TrendDirection(str, Enum):
    """추세 방향"""
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


@dataclass
class Signal:
    """기본 신호"""
    action: SignalAction
    confidence: float  # 0.0 ~ 1.0
    reason: str
    indicators: Dict[str, Any]


@dataclass
class ConfirmationResult:
    """퓨처차트 확인 결과"""
    is_confirmed: bool
    confidence: float
    layer1_match: bool  # 4시간 강물 + 구름대
    layer2_match: bool  # 1시간 강물 + RSI
    layer3_match: bool  # 15분 강물 곡률
    details: Dict[str, Any]


@dataclass
class StrategySignal:
    """최종 전략 신호"""
    action: SignalAction
    confidence: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit_1: Optional[float]  # 1차 익절 (50% 청산)
    take_profit_2: Optional[float]  # 2차 익절 (추세 전환)
    position_size: Optional[float]
    reason: str
    indicators: Dict[str, Any]


@dataclass
class Trade:
    """거래 기록"""
    symbol: str
    side: str  # BUY/SELL
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    pnl: Optional[float]
    entry_time: str
    exit_time: Optional[str]
    strategy: str
    reason: str
