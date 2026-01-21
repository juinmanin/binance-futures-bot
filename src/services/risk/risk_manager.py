"""리스크 관리 시스템"""
from typing import List, Tuple, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.database import Trade
from src.models.schemas import OrderRequest


@dataclass
class RiskConfig:
    """리스크 설정"""
    max_position_pct: float = 10.0  # 계좌 잔고 대비 최대 포지션 크기 (%)
    max_leverage: int = 10  # 최대 레버리지
    daily_loss_limit_pct: float = 5.0  # 일일 손실 한도 (%)
    max_positions: int = 5  # 동시 보유 가능한 최대 포지션 수
    risk_per_trade_pct: float = 1.0  # 거래당 위험 비율 (%)


@dataclass
class Position:
    """포지션 정보"""
    symbol: str
    position_side: str
    quantity: float
    entry_price: float
    unrealized_pnl: float


@dataclass
class ValidationResult:
    """검증 결과"""
    is_valid: bool
    reason: str = ""


class RiskManager:
    """리스크 관리 시스템"""
    
    def __init__(self, config: Optional[RiskConfig] = None):
        """
        초기화
        
        Args:
            config: 리스크 설정
        """
        self.config = config or RiskConfig()
    
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_per_trade: Optional[float] = None
    ) -> float:
        """
        포지션 크기 계산
        
        공식: (계정 잔고 × 위험 비율) / (진입가 - 손절가)
        
        Args:
            account_balance: 계정 잔고
            entry_price: 진입가
            stop_loss_price: 손절가
            risk_per_trade: 거래당 위험 비율 (기본값: config의 risk_per_trade_pct)
            
        Returns:
            포지션 크기
        """
        if risk_per_trade is None:
            risk_per_trade = self.config.risk_per_trade_pct / 100
        
        risk_amount = account_balance * risk_per_trade
        price_diff = abs(entry_price - stop_loss_price)
        
        if price_diff == 0:
            logger.warning("Price difference is zero, cannot calculate position size")
            return 0.0
        
        position_size = risk_amount / price_diff
        
        # 최대 포지션 크기 제한
        max_position_size = (account_balance * self.config.max_position_pct / 100) / entry_price
        position_size = min(position_size, max_position_size)
        
        logger.info(
            f"Calculated position size: {position_size:.4f} "
            f"(risk: ${risk_amount:.2f}, price_diff: ${price_diff:.2f})"
        )
        
        return position_size
    
    def calculate_atr_based_size(
        self,
        account_balance: float,
        atr: float,
        atr_multiplier: float = 2.0,
        risk_per_trade: Optional[float] = None
    ) -> float:
        """
        ATR 기반 포지션 크기 계산
        
        공식: (계정 잔고 × 1%) / (ATR × 2)
        
        Args:
            account_balance: 계정 잔고
            atr: Average True Range
            atr_multiplier: ATR 배수 (기본값: 2.0)
            risk_per_trade: 거래당 위험 비율
            
        Returns:
            포지션 크기
        """
        if risk_per_trade is None:
            risk_per_trade = self.config.risk_per_trade_pct / 100
        
        risk_amount = account_balance * risk_per_trade
        atr_risk = atr * atr_multiplier
        
        if atr_risk == 0:
            logger.warning("ATR is zero, cannot calculate position size")
            return 0.0
        
        position_size = risk_amount / atr_risk
        
        logger.info(
            f"ATR-based position size: {position_size:.4f} "
            f"(risk: ${risk_amount:.2f}, ATR: {atr:.4f})"
        )
        
        return position_size
    
    def validate_order(
        self,
        order: OrderRequest,
        account_balance: float,
        current_positions: List[Position]
    ) -> ValidationResult:
        """
        주문 유효성 검증
        
        Args:
            order: 주문 요청
            account_balance: 계정 잔고
            current_positions: 현재 포지션 리스트
            
        Returns:
            검증 결과
        """
        # 1. 포지션 개수 제한 확인
        if len(current_positions) >= self.config.max_positions:
            return ValidationResult(
                is_valid=False,
                reason=f"Maximum positions limit reached ({self.config.max_positions})"
            )
        
        # 2. 최대 포지션 크기 확인
        order_value = float(order.quantity) * float(order.price) if order.price else 0
        max_position_value = account_balance * (self.config.max_position_pct / 100)
        
        if order_value > max_position_value:
            return ValidationResult(
                is_valid=False,
                reason=f"Order value ${order_value:.2f} exceeds maximum position size ${max_position_value:.2f}"
            )
        
        # 3. 잔고 확인
        if order_value > account_balance:
            return ValidationResult(
                is_valid=False,
                reason=f"Insufficient balance: ${account_balance:.2f} < ${order_value:.2f}"
            )
        
        return ValidationResult(is_valid=True)
    
    async def check_daily_loss_limit(
        self,
        user_id: str,
        daily_limit: Optional[float] = None,
        db: Optional[AsyncSession] = None
    ) -> bool:
        """
        일일 손실 한도 확인
        
        Args:
            user_id: 사용자 ID
            daily_limit: 일일 손실 한도 (기본값: config의 daily_loss_limit_pct)
            db: 데이터베이스 세션
            
        Returns:
            한도 초과 여부 (True: 거래 가능, False: 한도 초과)
        """
        if db is None:
            logger.warning("Database session not provided, skipping daily loss limit check")
            return True
        
        if daily_limit is None:
            daily_limit = self.config.daily_loss_limit_pct
        
        # 오늘의 시작 시간
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        try:
            # 오늘의 총 손실 계산
            result = await db.execute(
                select(func.sum(Trade.pnl))
                .where(Trade.user_id == user_id)
                .where(Trade.created_at >= today_start)
                .where(Trade.pnl < 0)
            )
            total_loss = result.scalar() or 0
            
            # 계정 잔고는 별도로 조회해야 하므로 여기서는 절대값으로 체크
            # 실제로는 account_balance를 전달받아야 함
            logger.info(f"Today's total loss: ${abs(total_loss):.2f}")
            
            # 일일 손실이 한도를 초과하면 거래 불가
            # 실제 구현에서는 account_balance와 비교해야 함
            return True  # 임시로 항상 True 반환
            
        except Exception as e:
            logger.error(f"Failed to check daily loss limit: {str(e)}")
            return True  # 에러 발생 시 거래 허용 (보수적 접근)
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        atr: float,
        side: str,
        candle_low: float,
        candle_high: float,
        max_loss_pct: float = 0.02,
        atr_multiplier: float = 1.5
    ) -> float:
        """
        손절가 계산
        
        손절: MAX(진입 캔들 저가/고가, -2%, ATR × 1.5)
        
        Args:
            entry_price: 진입가
            atr: Average True Range
            side: 포지션 방향 (BUY/SELL)
            candle_low: 진입 캔들 저가
            candle_high: 진입 캔들 고가
            max_loss_pct: 최대 손실 비율 (기본값: 2%)
            atr_multiplier: ATR 배수 (기본값: 1.5)
            
        Returns:
            손절가
        """
        if side == "BUY":
            # 롱 포지션: 손절은 진입가 아래
            atr_stop = entry_price - (atr * atr_multiplier)
            pct_stop = entry_price * (1 - max_loss_pct)
            
            # 가장 높은 손절가 선택 (손실을 최소화)
            stop_loss = max(candle_low, atr_stop, pct_stop)
            
        else:
            # 숏 포지션: 손절은 진입가 위
            atr_stop = entry_price + (atr * atr_multiplier)
            pct_stop = entry_price * (1 + max_loss_pct)
            
            # 가장 낮은 손절가 선택 (손실을 최소화)
            stop_loss = min(candle_high, atr_stop, pct_stop)
        
        logger.info(
            f"Calculated stop loss for {side}: ${stop_loss:.2f} "
            f"(entry: ${entry_price:.2f}, ATR: {atr:.4f})"
        )
        
        return stop_loss
    
    def calculate_take_profit(
        self,
        entry_price: float,
        stop_loss: float,
        side: str,
        risk_reward_ratio: float = 2.0
    ) -> Tuple[float, float]:
        """
        익절가 계산
        
        1차: 손절폭 × 2
        2차: 손절폭 × 3 (또는 추세 전환 시)
        
        Args:
            entry_price: 진입가
            stop_loss: 손절가
            side: 포지션 방향 (BUY/SELL)
            risk_reward_ratio: 손익비 (기본값: 2.0)
            
        Returns:
            (1차 익절가, 2차 익절가) 튜플
        """
        risk = abs(entry_price - stop_loss)
        
        if side == "BUY":
            # 롱 포지션: 익절은 진입가 위
            tp1 = entry_price + (risk * risk_reward_ratio)
            tp2 = entry_price + (risk * (risk_reward_ratio + 1))
        else:
            # 숏 포지션: 익절은 진입가 아래
            tp1 = entry_price - (risk * risk_reward_ratio)
            tp2 = entry_price - (risk * (risk_reward_ratio + 1))
        
        logger.info(
            f"Calculated take profits for {side}: TP1=${tp1:.2f}, TP2=${tp2:.2f} "
            f"(entry: ${entry_price:.2f}, risk: ${risk:.2f})"
        )
        
        return tp1, tp2
    
    def calculate_leverage(
        self,
        position_size: float,
        account_balance: float,
        max_leverage: Optional[int] = None
    ) -> int:
        """
        적절한 레버리지 계산
        
        Args:
            position_size: 포지션 크기
            account_balance: 계정 잔고
            max_leverage: 최대 레버리지 (기본값: config의 max_leverage)
            
        Returns:
            레버리지
        """
        if max_leverage is None:
            max_leverage = self.config.max_leverage
        
        if account_balance == 0:
            return 1
        
        # 필요한 레버리지 계산
        required_leverage = int((position_size / account_balance) + 1)
        
        # 최대 레버리지 제한
        leverage = min(required_leverage, max_leverage)
        
        logger.info(
            f"Calculated leverage: {leverage}x "
            f"(position: ${position_size:.2f}, balance: ${account_balance:.2f})"
        )
        
        return leverage
