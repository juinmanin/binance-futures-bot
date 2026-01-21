"""거래 관련 라우트"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db import get_db
from src.models.schemas import (
    OrderRequest, OrderResponse,
    AccountBalance, PositionRisk,
)
from src.models.database import User, APIKey
from src.services.binance import BinanceClient
from src.core.security import get_encryption
from src.config import settings
from src.api.dependencies import get_current_user

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
