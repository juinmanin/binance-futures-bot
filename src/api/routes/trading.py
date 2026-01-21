"""거래 관련 라우트"""
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db import get_db
from src.models.schemas import (
    OrderRequest, OrderResponse,
    AccountBalance, PositionRisk,
    PendingSignalResponse,
)
from src.models.database import User, APIKey, PendingSignal as PendingSignalModel
from src.services.binance import BinanceClient
from src.core.security import get_encryption
from src.config import settings
from src.api.dependencies import get_current_user
from loguru import logger

router = APIRouter(prefix="/api/v1/trading", tags=["trading"])


async def get_binance_client(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BinanceClient:
    """
    바이낸스 클라이언트 의존성
    
    Args:
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        바이낸스 클라이언트
    """
    # 사용자의 API 키 조회
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == current_user.id)
        .where(APIKey.exchange == "binance")
        .limit(1)
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Binance API key not found. Please add your API key first.",
        )
    
    # API 키 복호화
    encryption = get_encryption(settings.master_encryption_key)
    decrypted_api_key = encryption.decrypt(api_key.encrypted_api_key)
    decrypted_api_secret = encryption.decrypt(api_key.encrypted_api_secret)
    
    # 클라이언트 생성
    return BinanceClient(
        api_key=decrypted_api_key,
        api_secret=decrypted_api_secret,
        base_url=settings.binance_base_url,
        testnet=api_key.is_testnet,
    )


@router.get("/balance", response_model=List[AccountBalance])
async def get_balance(
    client: BinanceClient = Depends(get_binance_client),
) -> List[AccountBalance]:
    """
    계좌 잔고 조회
    
    Args:
        client: 바이낸스 클라이언트
        
    Returns:
        잔고 리스트
    """
    try:
        async with client:
            balance = await client.get_account_balance()
            return balance
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get balance: {str(e)}",
        )


@router.get("/positions", response_model=List[PositionRisk])
async def get_positions(
    symbol: Optional[str] = None,
    client: BinanceClient = Depends(get_binance_client),
) -> List[PositionRisk]:
    """
    포지션 조회
    
    Args:
        symbol: 심볼 (선택사항)
        client: 바이낸스 클라이언트
        
    Returns:
        포지션 리스트
    """
    try:
        async with client:
            positions = await client.get_position_risk(symbol)
            return positions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get positions: {str(e)}",
        )


@router.post("/order", response_model=OrderResponse)
async def place_order(
    order: OrderRequest,
    client: BinanceClient = Depends(get_binance_client),
) -> OrderResponse:
    """
    주문 실행
    
    Args:
        order: 주문 요청
        client: 바이낸스 클라이언트
        
    Returns:
        주문 응답
    """
    try:
        async with client:
            response = await client.place_order(order)
            return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place order: {str(e)}",
        )


@router.delete("/order/{symbol}/{order_id}")
async def cancel_order(
    symbol: str,
    order_id: str,
    client: BinanceClient = Depends(get_binance_client),
) -> dict:
    """
    주문 취소
    
    Args:
        symbol: 심볼
        order_id: 주문 ID
        client: 바이낸스 클라이언트
        
    Returns:
        취소 결과
    """
    try:
        async with client:
            success = await client.cancel_order(symbol, order_id)
            if success:
                return {"message": "Order cancelled successfully"}
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to cancel order",
                )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order: {str(e)}",
        )


@router.post("/leverage/{symbol}")
async def set_leverage(
    symbol: str,
    leverage: int,
    client: BinanceClient = Depends(get_binance_client),
) -> dict:
    """
    레버리지 설정
    
    Args:
        symbol: 심볼
        leverage: 레버리지 (1-125)
        client: 바이낸스 클라이언트
        
    Returns:
        설정 결과
    """
    if leverage < 1 or leverage > 125:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leverage must be between 1 and 125",
        )
    
    try:
        async with client:
            success = await client.set_leverage(symbol, leverage)
            if success:
                return {"message": f"Leverage set to {leverage}x successfully"}
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to set leverage",
                )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set leverage: {str(e)}",
        )


@router.post("/orders", response_model=OrderResponse)
async def place_manual_order(
    order: OrderRequest,
    client: BinanceClient = Depends(get_binance_client),
) -> OrderResponse:
    """
    수동 주문 실행
    
    Args:
        order: 주문 요청
        client: 바이낸스 클라이언트
        
    Returns:
        주문 응답
    """
    try:
        async with client:
            response = await client.place_order(order)
            return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place order: {str(e)}",
        )


@router.get("/orders", response_model=List[OrderResponse])
async def get_open_orders(
    symbol: Optional[str] = None,
    client: BinanceClient = Depends(get_binance_client),
) -> List[OrderResponse]:
    """
    미체결 주문 조회
    
    Args:
        symbol: 심볼 (선택사항, 없으면 전체 조회)
        client: 바이낸스 클라이언트
        
    Returns:
        미체결 주문 리스트
    """
    try:
        async with client:
            # BinanceClient에 get_open_orders 메서드가 필요함
            # 임시로 빈 리스트 반환
            return []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get open orders: {str(e)}",
        )


@router.delete("/orders/{symbol}/{order_id}")
async def cancel_order_by_id(
    symbol: str,
    order_id: str,
    client: BinanceClient = Depends(get_binance_client),
) -> dict:
    """
    주문 취소
    
    Args:
        symbol: 심볼
        order_id: 주문 ID
        client: 바이낸스 클라이언트
        
    Returns:
        취소 결과
    """
    try:
        async with client:
            success = await client.cancel_order(symbol, order_id)
            if success:
                return {"message": "Order cancelled successfully", "order_id": order_id}
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to cancel order",
                )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order: {str(e)}",
        )


@router.post("/positions/{symbol}/close")
async def close_position_by_symbol(
    symbol: str,
    percentage: float = 100.0,
    current_user: User = Depends(get_current_user),
    client: BinanceClient = Depends(get_binance_client),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    포지션 청산
    
    Args:
        symbol: 심볼
        percentage: 청산 비율 (0-100, 기본값: 100)
        current_user: 현재 사용자
        client: 바이낸스 클라이언트
        db: 데이터베이스 세션
        
    Returns:
        청산 결과
    """
    if percentage <= 0 or percentage > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Percentage must be between 0 and 100",
        )
    
    try:
        from src.services.trading import PositionService
        
        position_service = PositionService(client, db)
        
        async with client:
            if percentage == 100:
                result = await position_service.close_position(symbol)
            else:
                result = await position_service.close_partial_position(
                    symbol,
                    percentage / 100
                )
            
            return {
                "message": f"Position closed successfully ({percentage}%)",
                "symbol": symbol,
                "order_id": result.order_id
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close position: {str(e)}",
        )


@router.get("/pending-signals", response_model=List[PendingSignalResponse])
async def get_pending_signals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[PendingSignalResponse]:
    """
    반자동 모드: 대기 중인 신호 조회
    
    Args:
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        대기 중인 신호 리스트
    """
    try:
        result = await db.execute(
            select(PendingSignalModel)
            .where(PendingSignalModel.user_id == current_user.id)
            .where(PendingSignalModel.status == "pending")
            .order_by(PendingSignalModel.created_at.desc())
        )
        signals = result.scalars().all()
        
        return [
            PendingSignalResponse(
                id=signal.id,
                symbol=signal.symbol,
                action=signal.action,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit_1=signal.take_profit_1,
                take_profit_2=signal.take_profit_2,
                position_size=signal.position_size,
                confidence=signal.confidence,
                reason=signal.reason,
                strategy_name=signal.strategy_name,
                status=signal.status,
                created_at=signal.created_at,
                expires_at=signal.expires_at
            )
            for signal in signals
        ]
    except Exception as e:
        logger.error(f"Failed to get pending signals: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pending signals: {str(e)}",
        )


@router.post("/execute-signal/{signal_id}")
async def execute_pending_signal(
    signal_id: str,
    current_user: User = Depends(get_current_user),
    client: BinanceClient = Depends(get_binance_client),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    반자동 모드: 신호 수동 실행
    
    Args:
        signal_id: 신호 ID
        current_user: 현재 사용자
        client: 바이낸스 클라이언트
        db: 데이터베이스 세션
        
    Returns:
        실행 결과
    """
    try:
        # 신호 조회
        result = await db.execute(
            select(PendingSignalModel)
            .where(PendingSignalModel.id == signal_id)
            .where(PendingSignalModel.user_id == current_user.id)
        )
        signal = result.scalar_one_or_none()
        
        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signal not found"
            )
        
        if signal.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Signal is not pending (status: {signal.status})"
            )
        
        # 만료 확인
        if signal.expires_at and signal.expires_at < datetime.utcnow():
            signal.status = "expired"
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signal has expired"
            )
        
        # TradingEngine을 사용하여 신호 실행
        from src.services.trading.trading_engine import (
            TradingEngine, 
            StrategySignal,
            SignalAction,
            TradingMode
        )
        
        # StrategySignal 객체 생성
        strategy_signal = StrategySignal(
            action=SignalAction(signal.action),
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            position_size=signal.position_size,
            atr=signal.atr,
            confidence=float(signal.confidence) if signal.confidence else None,
            reason=signal.reason
        )
        
        # 거래 엔진 실행
        engine = TradingEngine(
            client=client,
            db=db,
            user_id=str(current_user.id),
            mode=TradingMode.AUTO  # 확인 후에는 자동 실행
        )
        
        async with client:
            trade_result = await engine._execute_live_trade(strategy_signal, signal.symbol)
        
        if trade_result.success:
            # 신호 상태 업데이트
            signal.status = "confirmed"
            signal.executed_at = datetime.utcnow()
            await db.commit()
            
            return {
                "message": "Signal executed successfully",
                "signal_id": str(signal.id),
                "order_id": trade_result.entry_order.order_id if trade_result.entry_order else None
            }
        else:
            return {
                "message": "Signal execution failed",
                "signal_id": str(signal.id),
                "reason": trade_result.reason
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute signal: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute signal: {str(e)}",
        )


@router.delete("/pending-signals/{signal_id}")
async def reject_pending_signal(
    signal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    대기 중인 신호 거부
    
    Args:
        signal_id: 신호 ID
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        거부 결과
    """
    try:
        # 신호 조회
        result = await db.execute(
            select(PendingSignalModel)
            .where(PendingSignalModel.id == signal_id)
            .where(PendingSignalModel.user_id == current_user.id)
        )
        signal = result.scalar_one_or_none()
        
        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signal not found"
            )
        
        if signal.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Signal is not pending (status: {signal.status})"
            )
        
        # 신호 상태 업데이트
        signal.status = "rejected"
        await db.commit()
        
        return {
            "message": "Signal rejected successfully",
            "signal_id": str(signal.id)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject signal: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject signal: {str(e)}",
        )
