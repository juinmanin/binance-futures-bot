"""전략 설정 기본값"""
from dataclasses import dataclass
from typing import List


@dataclass
class StrategyConfig:
    """전략 설정"""
    # 기본 설정
    symbols: List[str]
    timeframe: str = "1h"
    
    # 래리 윌리엄스 설정
    k_value: float = 0.5
    trend_ma_period: int = 20
    
    # 퓨처차트 RSI 설정
    rsi_length: int = 14
    rsi_overbought: int = 80
    rsi_oversold: int = 20
    
    # 자금 흐름 설정
    fund_flow_threshold: int = 10
    
    # 리스크 관리 설정
    max_position_pct: float = 1.0  # 계좌 대비 최대 포지션 크기 (%)
    stop_loss_pct: float = 2.0      # 최대 손절 비율 (%)
    take_profit_ratio: float = 2.0  # 손절 대비 익절 비율
    
    # 운영 모드
    mode: str = "paper"  # paper/semi-auto/auto
    

# 기본 전략 설정
DEFAULT_STRATEGY_CONFIG = StrategyConfig(
    symbols=["BTCUSDT"],
    timeframe="1h",
    k_value=0.5,
    trend_ma_period=20,
    rsi_length=14,
    rsi_overbought=80,
    rsi_oversold=20,
    fund_flow_threshold=10,
    max_position_pct=1.0,
    stop_loss_pct=2.0,
    take_profit_ratio=2.0,
    mode="paper",
)
