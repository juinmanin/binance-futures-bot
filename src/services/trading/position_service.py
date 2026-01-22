"""포지션 관리 서비스"""
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import OrderException, BinanceAPIException
from src.models.schemas import PositionRisk
from src.services.binance.client import BinanceClient
from src.services.trading.order_service import OrderService


class PositionService:
    """포지션 관리 서비스 클래스"""
    
    def __init__(self, client: BinanceClient, db: AsyncSession, user_id: UUID):
        """
        초기화
        
        Args:
            client: 바이낸스 클라이언트
            db: 데이터베이스 세션
            user_id: 사용자 ID
        """
        self.client = client
        self.db = db
        self.user_id = user_id
        self.order_service = OrderService(client, db, user_id)
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionRisk]:
        """
        포지션 조회
        
        Args:
            symbol: 심볼 (선택사항, None이면 모든 포지션)
            
        Returns:
            포지션 리스트
            
        Raises:
            OrderException: 조회 실패 시
        """
        try:
            logger.info(f"Getting positions for: {symbol or 'all symbols'}")
            
            positions = await self.client.get_position_risk(symbol)
            
            logger.info(f"Found {len(positions)} active positions")
            return positions
            
        except BinanceAPIException as e:
            logger.error(f"Failed to get positions: {e.message}")
            raise OrderException(f"Get positions failed: {e.message}", details=e.details)
    
    async def close_position(
        self,
        symbol: str,
        position_side: str = "BOTH",
        strategy_id: Optional[UUID] = None,
    ) -> bool:
        """
        포지션 전체 청산
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            position_side: 포지션 방향 (LONG, SHORT, BOTH)
            strategy_id: 전략 ID
            
        Returns:
            성공 여부
            
        Raises:
            OrderException: 청산 실패 시
        """
        try:
            logger.info(f"Closing position: {symbol} {position_side}")
            
            # 현재 포지션 조회
            positions = await self.get_positions(symbol)
            
            if not positions:
                logger.info(f"No position to close for: {symbol}")
                return True
            
            # 포지션 방향에 맞는 포지션 찾기
            target_position = None
            for pos in positions:
                if position_side == "BOTH" or pos.position_side == position_side:
                    target_position = pos
                    break
            
            if not target_position:
                logger.info(f"No {position_side} position found for: {symbol}")
                return True
            
            # 포지션 수량이 0이면 청산할 필요 없음
            if target_position.position_amount == 0:
                logger.info(f"Position amount is zero for: {symbol}")
                return True
            
            # 청산 주문 방향 결정 (롱 포지션은 매도, 숏 포지션은 매수)
            close_side = "SELL" if target_position.position_amount > 0 else "BUY"
            quantity = abs(target_position.position_amount)
            
            # 시장가 청산 주문
            await self.order_service.place_market_order(
                symbol=symbol,
                side=close_side,
                quantity=quantity,
                position_side=target_position.position_side,
                reduce_only=True,
                strategy_id=strategy_id,
            )
            
            logger.info(f"Position closed successfully: {symbol} {position_side}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to close position: {str(e)}")
            raise OrderException(f"Close position failed: {str(e)}")
    
    async def close_partial_position(
        self,
        symbol: str,
        percentage: Decimal,
        position_side: str = "BOTH",
        strategy_id: Optional[UUID] = None,
    ) -> bool:
        """
        포지션 부분 청산
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            percentage: 청산 비율 (0-100)
            position_side: 포지션 방향 (LONG, SHORT, BOTH)
            strategy_id: 전략 ID
            
        Returns:
            성공 여부
            
        Raises:
            OrderException: 청산 실패 시
        """
        try:
            if percentage <= 0 or percentage > 100:
                raise OrderException("Percentage must be between 0 and 100")
            
            logger.info(
                f"Closing {percentage}% of position: {symbol} {position_side}"
            )
            
            # 현재 포지션 조회
            positions = await self.get_positions(symbol)
            
            if not positions:
                logger.info(f"No position to close for: {symbol}")
                return True
            
            # 포지션 방향에 맞는 포지션 찾기
            target_position = None
            for pos in positions:
                if position_side == "BOTH" or pos.position_side == position_side:
                    target_position = pos
                    break
            
            if not target_position:
                logger.info(f"No {position_side} position found for: {symbol}")
                return True
            
            # 포지션 수량이 0이면 청산할 필요 없음
            if target_position.position_amount == 0:
                logger.info(f"Position amount is zero for: {symbol}")
                return True
            
            # 청산할 수량 계산
            close_quantity = abs(target_position.position_amount) * (percentage / Decimal("100"))
            
            # 청산 주문 방향 결정
            close_side = "SELL" if target_position.position_amount > 0 else "BUY"
            
            # 시장가 청산 주문
            await self.order_service.place_market_order(
                symbol=symbol,
                side=close_side,
                quantity=close_quantity,
                position_side=target_position.position_side,
                reduce_only=True,
                strategy_id=strategy_id,
            )
            
            logger.info(
                f"{percentage}% of position closed successfully: {symbol} {position_side}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to close partial position: {str(e)}")
            raise OrderException(f"Close partial position failed: {str(e)}")
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        레버리지 설정
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            leverage: 레버리지 (1-125)
            
        Returns:
            성공 여부
            
        Raises:
            OrderException: 설정 실패 시
        """
        try:
            if leverage < 1 or leverage > 125:
                raise OrderException("Leverage must be between 1 and 125")
            
            logger.info(f"Setting leverage: {symbol} {leverage}x")
            
            success = await self.client.set_leverage(symbol, leverage)
            
            if success:
                logger.info(f"Leverage set successfully: {symbol} {leverage}x")
            else:
                logger.warning(f"Failed to set leverage: {symbol} {leverage}x")
            
            return success
            
        except BinanceAPIException as e:
            logger.error(f"Failed to set leverage: {e.message}")
            raise OrderException(f"Set leverage failed: {e.message}", details=e.details)
    
    async def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        """
        마진 타입 설정
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            margin_type: 마진 타입 (ISOLATED, CROSSED)
            
        Returns:
            성공 여부
            
        Raises:
            OrderException: 설정 실패 시
        """
        try:
            if margin_type not in ["ISOLATED", "CROSSED"]:
                raise OrderException("Margin type must be ISOLATED or CROSSED")
            
            logger.info(f"Setting margin type: {symbol} {margin_type}")
            
            from src.services.binance.endpoints import ENDPOINTS
            
            params = {
                "symbol": symbol,
                "marginType": margin_type,
            }
            
            await self.client._request(
                "POST",
                ENDPOINTS["margin_type"],
                params,
                signed=True
            )
            
            logger.info(f"Margin type set successfully: {symbol} {margin_type}")
            return True
            
        except BinanceAPIException as e:
            # 이미 설정된 마진 타입인 경우 에러 무시
            if "No need to change margin type" in str(e.details):
                logger.info(f"Margin type already set: {symbol} {margin_type}")
                return True
            
            logger.error(f"Failed to set margin type: {e.message}")
            raise OrderException(f"Set margin type failed: {e.message}", details=e.details)
    
    async def get_position_pnl(self, symbol: str, position_side: str = "BOTH") -> Decimal:
        """
        포지션 손익 조회
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            position_side: 포지션 방향 (LONG, SHORT, BOTH)
            
        Returns:
            미실현 손익
            
        Raises:
            OrderException: 조회 실패 시
        """
        try:
            logger.info(f"Getting position PnL: {symbol} {position_side}")
            
            positions = await self.get_positions(symbol)
            
            total_pnl = Decimal("0")
            for pos in positions:
                if position_side == "BOTH" or pos.position_side == position_side:
                    total_pnl += pos.unrealized_profit
            
            logger.info(f"Position PnL: {symbol} {position_side} = {total_pnl}")
            return total_pnl
            
        except Exception as e:
            logger.error(f"Failed to get position PnL: {str(e)}")
            raise OrderException(f"Get position PnL failed: {str(e)}")
