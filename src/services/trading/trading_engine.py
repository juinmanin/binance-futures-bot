"""거래 실행 엔진"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import OrderException, ValidationException
from src.models.database import Trade
from src.models.schemas import OrderResponse, OrderRequest
from src.services.binance.client import BinanceClient
from src.services.trading.order_service import OrderService
from src.services.trading.position_service import PositionService
from src.services.risk.risk_manager import RiskManager, RiskConfig, Position, ValidationResult


# 상수 정의
DEFAULT_PAPER_POSITION_SIZE = Decimal("0.1")  # 페이퍼 트레이딩 기본 포지션 크기


class TradingMode(str, Enum):
    """거래 모드"""
    PAPER = "paper"
    SEMI_AUTO = "semi-auto"
    AUTO = "auto"


class SignalAction(str, Enum):
    """시그널 액션"""
    BUY = "BUY"
    SELL = "SELL"


class StrategySignal(BaseModel):
    """전략 시그널 스키마"""
    action: SignalAction = Field(..., description="매수/매도 액션")
    entry_price: Decimal = Field(..., description="진입가")
    stop_loss: Decimal = Field(..., description="손절가")
    take_profit_1: Decimal = Field(..., description="1차 익절가")
    take_profit_2: Decimal = Field(..., description="2차 익절가")
    position_size: Optional[Decimal] = Field(None, description="포지션 크기 (None이면 자동 계산)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="시그널 신뢰도")
    reason: Optional[str] = Field(None, description="시그널 발생 이유")
    atr: Optional[Decimal] = Field(None, description="ATR 값 (ATR 기반 계산 시)")
    candle_low: Optional[Decimal] = Field(None, description="진입 캔들 저가")
    candle_high: Optional[Decimal] = Field(None, description="진입 캔들 고가")


class TradeResult(BaseModel):
    """거래 결과 스키마"""
    success: bool = Field(..., description="성공 여부")
    entry_order: Optional[OrderResponse] = Field(None, description="진입 주문")
    sl_order: Optional[OrderResponse] = Field(None, description="손절 주문")
    tp_orders: List[OrderResponse] = Field(default_factory=list, description="익절 주문 리스트")
    reason: Optional[str] = Field(None, description="실패 사유")
    paper_trade_id: Optional[UUID] = Field(None, description="페이퍼 거래 ID")
    pending_signal_id: Optional[UUID] = Field(None, description="대기 시그널 ID")


class PendingSignal(BaseModel):
    """대기 중인 시그널 (DB 저장용)"""
    id: Optional[UUID] = None
    user_id: UUID
    symbol: str
    signal: Dict[str, Any]
    status: str = "pending"  # pending, confirmed, rejected
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TradingEngine:
    """거래 실행 엔진 클래스"""
    
    def __init__(
        self,
        client: BinanceClient,
        db: AsyncSession,
        user_id: UUID,
        mode: TradingMode = TradingMode.PAPER,
        leverage: int = 10,
        risk_config: Optional[RiskConfig] = None
    ):
        """
        초기화
        
        Args:
            client: 바이낸스 클라이언트
            db: 데이터베이스 세션
            user_id: 사용자 ID
            mode: 거래 모드 (paper/semi-auto/auto)
            leverage: 레버리지 (기본값: 10x)
            risk_config: 리스크 설정
        """
        self.client = client
        self.db = db
        self.user_id = user_id
        self.mode = mode
        self.leverage = leverage
        
        # 서비스 초기화
        self.order_service = OrderService(client, db, user_id)
        self.position_service = PositionService(client, db, user_id)
        self.risk_manager = RiskManager(risk_config or RiskConfig())
        
        logger.info(f"TradingEngine initialized: mode={mode}, leverage={leverage}x")
    
    async def process_signal(
        self,
        signal: StrategySignal,
        symbol: str,
        strategy_id: Optional[UUID] = None
    ) -> TradeResult:
        """
        전략 시그널 처리 (메인 진입점)
        
        Args:
            signal: 전략 시그널
            symbol: 심볼 (예: BTCUSDT)
            strategy_id: 전략 ID
            
        Returns:
            거래 결과
        """
        try:
            logger.info(
                f"Processing signal: {symbol} {signal.action} @ {signal.entry_price} "
                f"mode={self.mode} confidence={signal.confidence}"
            )
            
            # 모드에 따라 처리
            if self.mode == TradingMode.PAPER:
                return await self._execute_paper_trade(signal, symbol, strategy_id)
            elif self.mode == TradingMode.SEMI_AUTO:
                return await self._queue_for_confirmation(signal, symbol, strategy_id)
            else:  # AUTO
                return await self._execute_live_trade(signal, symbol, strategy_id)
                
        except Exception as e:
            logger.error(f"Failed to process signal: {str(e)}")
            return TradeResult(
                success=False,
                reason=f"Signal processing failed: {str(e)}"
            )
    
    async def _execute_live_trade(
        self,
        signal: StrategySignal,
        symbol: str,
        strategy_id: Optional[UUID] = None
    ) -> TradeResult:
        """
        실거래 실행
        
        Args:
            signal: 전략 시그널
            symbol: 심볼
            strategy_id: 전략 ID
            
        Returns:
            거래 결과
        """
        try:
            logger.info(f"Executing live trade: {symbol} {signal.action}")
            
            # 1. 레버리지 설정
            await self.position_service.set_leverage(symbol, self.leverage)
            
            # 2. 계좌 잔고 조회
            account_info = await self.client.get_account()
            usdt_balance = Decimal("0")
            for asset in account_info.get("assets", []):
                if asset["asset"] == "USDT":
                    usdt_balance = Decimal(asset["availableBalance"])
                    break
            
            logger.info(f"Available balance: {usdt_balance} USDT")
            
            # 3. 현재 포지션 조회
            positions = await self.position_service.get_positions(symbol)
            current_positions = [
                Position(
                    symbol=pos.symbol,
                    position_side=pos.position_side,
                    quantity=float(pos.position_amount),
                    entry_price=float(pos.entry_price),
                    unrealized_pnl=float(pos.unrealized_profit)
                )
                for pos in positions
                if pos.position_amount != 0
            ]
            
            # 4. 포지션 크기 계산
            if signal.position_size:
                position_size = signal.position_size
            else:
                # ATR 기반 또는 손절가 기반 계산
                if signal.atr:
                    position_size = Decimal(str(self.risk_manager.calculate_atr_based_size(
                        account_balance=float(usdt_balance),
                        atr=float(signal.atr)
                    )))
                else:
                    position_size = Decimal(str(self.risk_manager.calculate_position_size(
                        account_balance=float(usdt_balance),
                        entry_price=float(signal.entry_price),
                        stop_loss_price=float(signal.stop_loss)
                    )))
            
            logger.info(f"Calculated position size: {position_size}")
            
            # 5. 리스크 검증
            validation_result = self.risk_manager.validate_order(
                order=OrderRequest(
                    symbol=symbol,
                    side=signal.action.value,
                    order_type="MARKET",
                    quantity=position_size,
                    price=signal.entry_price
                ),
                account_balance=float(usdt_balance),
                current_positions=current_positions
            )
            
            if not validation_result.is_valid:
                logger.warning(f"Order validation failed: {validation_result.reason}")
                return TradeResult(
                    success=False,
                    reason=f"Validation failed: {validation_result.reason}"
                )
            
            # 6. 진입 주문 실행 (시장가)
            entry_side = signal.action.value
            position_side = "LONG" if signal.action == SignalAction.BUY else "SHORT"
            
            entry_order = await self.order_service.place_market_order(
                symbol=symbol,
                side=entry_side,
                quantity=position_size,
                position_side=position_side,
                strategy_id=strategy_id
            )
            
            logger.info(f"Entry order placed: {entry_order.order_id}")
            
            # 7. 손절 주문 실행
            sl_side = "SELL" if signal.action == SignalAction.BUY else "BUY"
            sl_order = await self.order_service.place_stop_loss(
                symbol=symbol,
                side=sl_side,
                quantity=position_size,
                stop_price=signal.stop_loss,
                position_side=position_side,
                strategy_id=strategy_id
            )
            
            logger.info(f"Stop loss placed: {sl_order.order_id} @ {signal.stop_loss}")
            
            # 8. 익절 주문 실행 (50% at TP1, 50% at TP2)
            tp_orders = []
            tp_side = "SELL" if signal.action == SignalAction.BUY else "BUY"
            
            # TP1: 50%
            tp1_quantity = position_size / Decimal("2")
            tp1_order = await self.order_service.place_take_profit(
                symbol=symbol,
                side=tp_side,
                quantity=tp1_quantity,
                stop_price=signal.take_profit_1,
                position_side=position_side,
                strategy_id=strategy_id
            )
            tp_orders.append(tp1_order)
            logger.info(f"TP1 placed: {tp1_order.order_id} @ {signal.take_profit_1}")
            
            # TP2: 50%
            tp2_quantity = position_size - tp1_quantity
            tp2_order = await self.order_service.place_take_profit(
                symbol=symbol,
                side=tp_side,
                quantity=tp2_quantity,
                stop_price=signal.take_profit_2,
                position_side=position_side,
                strategy_id=strategy_id
            )
            tp_orders.append(tp2_order)
            logger.info(f"TP2 placed: {tp2_order.order_id} @ {signal.take_profit_2}")
            
            logger.info(f"Live trade executed successfully: {symbol} {signal.action}")
            
            return TradeResult(
                success=True,
                entry_order=entry_order,
                sl_order=sl_order,
                tp_orders=tp_orders
            )
            
        except Exception as e:
            logger.error(f"Failed to execute live trade: {str(e)}")
            return TradeResult(
                success=False,
                reason=f"Live trade execution failed: {str(e)}"
            )
    
    async def _execute_paper_trade(
        self,
        signal: StrategySignal,
        symbol: str,
        strategy_id: Optional[UUID] = None
    ) -> TradeResult:
        """
        페이퍼 트레이딩 실행 (시뮬레이션)
        
        Args:
            signal: 전략 시그널
            symbol: 심볼
            strategy_id: 전략 ID
            
        Returns:
            거래 결과
        """
        try:
            logger.info(f"Executing paper trade: {symbol} {signal.action}")
            
            # 가상의 포지션 크기 (시뮬레이션)
            if signal.position_size:
                position_size = signal.position_size
            else:
                position_size = DEFAULT_PAPER_POSITION_SIZE
            
            # 진입 주문 시뮬레이션
            entry_order = OrderResponse(
                order_id=f"PAPER_{datetime.utcnow().timestamp()}",
                symbol=symbol,
                side=signal.action.value,
                order_type="MARKET",
                quantity=position_size,
                price=signal.entry_price,
                status="FILLED",
                created_at=datetime.utcnow()
            )
            
            # 손절 주문 시뮬레이션
            sl_side = "SELL" if signal.action == SignalAction.BUY else "BUY"
            sl_order = OrderResponse(
                order_id=f"PAPER_SL_{datetime.utcnow().timestamp()}",
                symbol=symbol,
                side=sl_side,
                order_type="STOP_MARKET",
                quantity=position_size,
                price=signal.stop_loss,
                status="NEW",
                created_at=datetime.utcnow()
            )
            
            # 익절 주문 시뮬레이션
            tp_orders = []
            tp_side = "SELL" if signal.action == SignalAction.BUY else "BUY"
            
            # TP1: 50%
            tp1_quantity = position_size / Decimal("2")
            tp1_order = OrderResponse(
                order_id=f"PAPER_TP1_{datetime.utcnow().timestamp()}",
                symbol=symbol,
                side=tp_side,
                order_type="TAKE_PROFIT_MARKET",
                quantity=tp1_quantity,
                price=signal.take_profit_1,
                status="NEW",
                created_at=datetime.utcnow()
            )
            tp_orders.append(tp1_order)
            
            # TP2: 50%
            tp2_quantity = position_size - tp1_quantity
            tp2_order = OrderResponse(
                order_id=f"PAPER_TP2_{datetime.utcnow().timestamp()}",
                symbol=symbol,
                side=tp_side,
                order_type="TAKE_PROFIT_MARKET",
                quantity=tp2_quantity,
                price=signal.take_profit_2,
                status="NEW",
                created_at=datetime.utcnow()
            )
            tp_orders.append(tp2_order)
            
            # 거래 기록 저장 (페이퍼 트레이딩 표시)
            trade = Trade(
                user_id=self.user_id,
                symbol=symbol,
                side=signal.action.value,
                position_side="LONG" if signal.action == SignalAction.BUY else "SHORT",
                order_type="MARKET",
                quantity=position_size,
                price=signal.entry_price,
                executed_price=signal.entry_price,
                status="FILLED",
                strategy_name="paper_trading",
                signal_source={
                    "action": signal.action.value,
                    "entry_price": str(signal.entry_price),
                    "stop_loss": str(signal.stop_loss),
                    "take_profit_1": str(signal.take_profit_1),
                    "take_profit_2": str(signal.take_profit_2),
                    "confidence": signal.confidence,
                    "reason": signal.reason
                },
                executed_at=datetime.utcnow()
            )
            
            self.db.add(trade)
            await self.db.commit()
            await self.db.refresh(trade)
            
            logger.info(f"Paper trade recorded: {trade.id}")
            
            return TradeResult(
                success=True,
                entry_order=entry_order,
                sl_order=sl_order,
                tp_orders=tp_orders,
                paper_trade_id=trade.id
            )
            
        except Exception as e:
            logger.error(f"Failed to execute paper trade: {str(e)}")
            await self.db.rollback()
            return TradeResult(
                success=False,
                reason=f"Paper trade execution failed: {str(e)}"
            )
    
    async def _queue_for_confirmation(
        self,
        signal: StrategySignal,
        symbol: str,
        strategy_id: Optional[UUID] = None
    ) -> TradeResult:
        """
        사용자 확인을 위해 시그널 대기열에 추가
        
        Args:
            signal: 전략 시그널
            symbol: 심볼
            strategy_id: 전략 ID
            
        Returns:
            거래 결과
        """
        try:
            logger.info(f"Queueing signal for confirmation: {symbol} {signal.action}")
            
            # 시그널을 데이터베이스에 저장 (signal_source 필드 활용)
            trade = Trade(
                user_id=self.user_id,
                symbol=symbol,
                side=signal.action.value,
                position_side="LONG" if signal.action == SignalAction.BUY else "SHORT",
                order_type="MARKET",
                quantity=signal.position_size or Decimal("0"),
                price=signal.entry_price,
                executed_price=None,
                status="PENDING",  # 대기 상태
                strategy_name="semi_auto",
                signal_source={
                    "action": signal.action.value,
                    "entry_price": str(signal.entry_price),
                    "stop_loss": str(signal.stop_loss),
                    "take_profit_1": str(signal.take_profit_1),
                    "take_profit_2": str(signal.take_profit_2),
                    "position_size": str(signal.position_size) if signal.position_size else None,
                    "confidence": signal.confidence,
                    "reason": signal.reason,
                    "atr": str(signal.atr) if signal.atr else None,
                    "strategy_id": str(strategy_id) if strategy_id else None
                }
            )
            
            self.db.add(trade)
            await self.db.commit()
            await self.db.refresh(trade)
            
            logger.info(f"Signal queued for confirmation: {trade.id}")
            
            return TradeResult(
                success=True,
                pending_signal_id=trade.id,
                reason="Signal queued for user confirmation"
            )
            
        except Exception as e:
            logger.error(f"Failed to queue signal: {str(e)}")
            await self.db.rollback()
            return TradeResult(
                success=False,
                reason=f"Failed to queue signal: {str(e)}"
            )
    
    async def confirm_pending_signal(
        self,
        pending_signal_id: UUID
    ) -> TradeResult:
        """
        대기 중인 시그널 확인 및 실행
        
        Args:
            pending_signal_id: 대기 시그널 ID
            
        Returns:
            거래 결과
        """
        try:
            logger.info(f"Confirming pending signal: {pending_signal_id}")
            
            # 대기 시그널 조회
            result = await self.db.execute(
                select(Trade).where(
                    Trade.id == pending_signal_id,
                    Trade.user_id == self.user_id,
                    Trade.status == "PENDING"
                )
            )
            pending_trade = result.scalar_one_or_none()
            
            if not pending_trade:
                return TradeResult(
                    success=False,
                    reason="Pending signal not found or already processed"
                )
            
            # 시그널 데이터 복원
            signal_data = pending_trade.signal_source
            signal = StrategySignal(
                action=SignalAction(signal_data["action"]),
                entry_price=Decimal(signal_data["entry_price"]),
                stop_loss=Decimal(signal_data["stop_loss"]),
                take_profit_1=Decimal(signal_data["take_profit_1"]),
                take_profit_2=Decimal(signal_data["take_profit_2"]),
                position_size=Decimal(signal_data["position_size"]) if signal_data.get("position_size") else None,
                confidence=signal_data.get("confidence", 1.0),
                reason=signal_data.get("reason"),
                atr=Decimal(signal_data["atr"]) if signal_data.get("atr") else None
            )
            
            strategy_id = UUID(signal_data["strategy_id"]) if signal_data.get("strategy_id") else None
            
            # 실거래 실행
            result = await self._execute_live_trade(
                signal=signal,
                symbol=pending_trade.symbol,
                strategy_id=strategy_id
            )
            
            # 대기 상태 업데이트
            if result.success:
                pending_trade.status = "CONFIRMED"
                pending_trade.executed_at = datetime.utcnow()
            else:
                pending_trade.status = "FAILED"
            
            await self.db.commit()
            
            logger.info(f"Pending signal confirmed: {pending_signal_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to confirm pending signal: {str(e)}")
            await self.db.rollback()
            return TradeResult(
                success=False,
                reason=f"Failed to confirm signal: {str(e)}"
            )
    
    async def reject_pending_signal(
        self,
        pending_signal_id: UUID
    ) -> bool:
        """
        대기 중인 시그널 거부
        
        Args:
            pending_signal_id: 대기 시그널 ID
            
        Returns:
            성공 여부
        """
        try:
            logger.info(f"Rejecting pending signal: {pending_signal_id}")
            
            # 대기 시그널 조회
            result = await self.db.execute(
                select(Trade).where(
                    Trade.id == pending_signal_id,
                    Trade.user_id == self.user_id,
                    Trade.status == "PENDING"
                )
            )
            pending_trade = result.scalar_one_or_none()
            
            if not pending_trade:
                logger.warning(f"Pending signal not found: {pending_signal_id}")
                return False
            
            # 상태 업데이트
            pending_trade.status = "REJECTED"
            await self.db.commit()
            
            logger.info(f"Pending signal rejected: {pending_signal_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reject pending signal: {str(e)}")
            await self.db.rollback()
            return False
    
    async def get_pending_signals(self) -> List[Trade]:
        """
        대기 중인 시그널 목록 조회
        
        Returns:
            대기 시그널 리스트
        """
        try:
            result = await self.db.execute(
                select(Trade).where(
                    Trade.user_id == self.user_id,
                    Trade.status == "PENDING",
                    Trade.strategy_name == "semi_auto"
                ).order_by(Trade.created_at.desc())
            )
            pending_trades = result.scalars().all()
            
            logger.info(f"Found {len(pending_trades)} pending signals")
            return list(pending_trades)
            
        except Exception as e:
            logger.error(f"Failed to get pending signals: {str(e)}")
            return []
    
    async def close_position_with_profit(
        self,
        symbol: str,
        percentage: Decimal,
        position_side: str = "BOTH",
        strategy_id: Optional[UUID] = None
    ) -> bool:
        """
        익절 포지션 부분 청산
        
        Args:
            symbol: 심볼
            percentage: 청산 비율 (0-100)
            position_side: 포지션 방향
            strategy_id: 전략 ID
            
        Returns:
            성공 여부
        """
        try:
            logger.info(f"Closing {percentage}% of position: {symbol} {position_side}")
            
            if self.mode == TradingMode.PAPER:
                logger.info("Paper mode: position close simulated")
                return True
            
            return await self.position_service.close_partial_position(
                symbol=symbol,
                percentage=percentage,
                position_side=position_side,
                strategy_id=strategy_id
            )
            
        except Exception as e:
            logger.error(f"Failed to close position: {str(e)}")
            return False
    
    def set_mode(self, mode: TradingMode):
        """
        거래 모드 변경
        
        Args:
            mode: 새 거래 모드
        """
        self.mode = mode
        logger.info(f"Trading mode changed to: {mode}")
    
    def set_leverage(self, leverage: int):
        """
        레버리지 변경
        
        Args:
            leverage: 새 레버리지
        """
        if leverage < 1 or leverage > 125:
            raise ValidationException("Leverage must be between 1 and 125")
        
        self.leverage = leverage
        logger.info(f"Leverage changed to: {leverage}x")
