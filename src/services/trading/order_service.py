"""주문 관리 서비스"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import OrderException, BinanceAPIException
from src.models.database import Trade
from src.models.schemas import OrderRequest, OrderResponse
from src.services.binance.client import BinanceClient


class OrderService:
    """주문 관리 서비스 클래스"""
    
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
    
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        position_side: str = "BOTH",
        reduce_only: bool = False,
        strategy_id: Optional[UUID] = None,
    ) -> OrderResponse:
        """
        시장가 주문 실행
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            side: 주문 방향 (BUY, SELL)
            quantity: 주문 수량
            position_side: 포지션 방향 (LONG, SHORT, BOTH)
            reduce_only: 포지션 감소 전용
            strategy_id: 전략 ID
            
        Returns:
            주문 응답
            
        Raises:
            OrderException: 주문 실패 시
        """
        try:
            order_request = OrderRequest(
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=quantity,
                position_side=position_side,
                reduce_only=reduce_only,
            )
            
            logger.info(
                f"Placing market order: {symbol} {side} {quantity} "
                f"position_side={position_side} reduce_only={reduce_only}"
            )
            
            order_result = await self.client.place_order(order_request)
            
            # 거래 기록 저장
            await self._record_trade(order_result, strategy_id)
            
            logger.info(f"Market order placed successfully: {order_result.order_id}")
            return order_result
            
        except BinanceAPIException as e:
            logger.error(f"Failed to place market order: {e.message}")
            raise OrderException(f"Market order failed: {e.message}", details=e.details)
    
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        time_in_force: str = "GTC",
        position_side: str = "BOTH",
        strategy_id: Optional[UUID] = None,
    ) -> OrderResponse:
        """
        지정가 주문 실행
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            side: 주문 방향 (BUY, SELL)
            quantity: 주문 수량
            price: 지정가
            time_in_force: 주문 유효 시간 (GTC, IOC, FOK)
            position_side: 포지션 방향 (LONG, SHORT, BOTH)
            strategy_id: 전략 ID
            
        Returns:
            주문 응답
            
        Raises:
            OrderException: 주문 실패 시
        """
        try:
            order_request = OrderRequest(
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                quantity=quantity,
                price=price,
                time_in_force=time_in_force,
                position_side=position_side,
            )
            
            logger.info(
                f"Placing limit order: {symbol} {side} {quantity} @ {price} "
                f"position_side={position_side}"
            )
            
            order_result = await self.client.place_order(order_request)
            
            # 거래 기록 저장
            await self._record_trade(order_result, strategy_id)
            
            logger.info(f"Limit order placed successfully: {order_result.order_id}")
            return order_result
            
        except BinanceAPIException as e:
            logger.error(f"Failed to place limit order: {e.message}")
            raise OrderException(f"Limit order failed: {e.message}", details=e.details)
    
    async def place_stop_loss(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        position_side: str = "BOTH",
        strategy_id: Optional[UUID] = None,
    ) -> OrderResponse:
        """
        스톱로스 주문 실행
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            side: 주문 방향 (BUY, SELL)
            quantity: 주문 수량
            stop_price: 스톱 가격
            position_side: 포지션 방향 (LONG, SHORT, BOTH)
            strategy_id: 전략 ID
            
        Returns:
            주문 응답
            
        Raises:
            OrderException: 주문 실패 시
        """
        try:
            order_request = OrderRequest(
                symbol=symbol,
                side=side,
                order_type="STOP_MARKET",
                quantity=quantity,
                price=stop_price,
                position_side=position_side,
            )
            
            logger.info(
                f"Placing stop loss: {symbol} {side} {quantity} @ {stop_price} "
                f"position_side={position_side}"
            )
            
            order_result = await self.client.place_order(order_request)
            
            # 거래 기록 저장
            await self._record_trade(order_result, strategy_id)
            
            logger.info(f"Stop loss placed successfully: {order_result.order_id}")
            return order_result
            
        except BinanceAPIException as e:
            logger.error(f"Failed to place stop loss: {e.message}")
            raise OrderException(f"Stop loss failed: {e.message}", details=e.details)
    
    async def place_take_profit(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        position_side: str = "BOTH",
        strategy_id: Optional[UUID] = None,
    ) -> OrderResponse:
        """
        익절 주문 실행
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            side: 주문 방향 (BUY, SELL)
            quantity: 주문 수량
            stop_price: 익절 가격
            position_side: 포지션 방향 (LONG, SHORT, BOTH)
            strategy_id: 전략 ID
            
        Returns:
            주문 응답
            
        Raises:
            OrderException: 주문 실패 시
        """
        try:
            order_request = OrderRequest(
                symbol=symbol,
                side=side,
                order_type="TAKE_PROFIT_MARKET",
                quantity=quantity,
                price=stop_price,
                position_side=position_side,
            )
            
            logger.info(
                f"Placing take profit: {symbol} {side} {quantity} @ {stop_price} "
                f"position_side={position_side}"
            )
            
            order_result = await self.client.place_order(order_request)
            
            # 거래 기록 저장
            await self._record_trade(order_result, strategy_id)
            
            logger.info(f"Take profit placed successfully: {order_result.order_id}")
            return order_result
            
        except BinanceAPIException as e:
            logger.error(f"Failed to place take profit: {e.message}")
            raise OrderException(f"Take profit failed: {e.message}", details=e.details)
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        주문 취소
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            order_id: 주문 ID
            
        Returns:
            성공 여부
            
        Raises:
            OrderException: 주문 취소 실패 시
        """
        try:
            logger.info(f"Canceling order: {symbol} {order_id}")
            
            success = await self.client.cancel_order(symbol, order_id)
            
            if success:
                logger.info(f"Order canceled successfully: {order_id}")
            else:
                logger.warning(f"Failed to cancel order: {order_id}")
            
            return success
            
        except BinanceAPIException as e:
            logger.error(f"Failed to cancel order: {e.message}")
            raise OrderException(f"Cancel order failed: {e.message}", details=e.details)
    
    async def cancel_all_orders(self, symbol: str) -> bool:
        """
        특정 심볼의 모든 주문 취소
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            
        Returns:
            성공 여부
            
        Raises:
            OrderException: 주문 취소 실패 시
        """
        try:
            logger.info(f"Canceling all orders for: {symbol}")
            
            # 먼저 열린 주문 조회
            open_orders = await self.get_open_orders(symbol)
            
            if not open_orders:
                logger.info(f"No open orders to cancel for: {symbol}")
                return True
            
            # 모든 주문 취소
            success_count = 0
            for order in open_orders:
                try:
                    if await self.client.cancel_order(symbol, order["orderId"]):
                        success_count += 1
                except Exception as e:
                    logger.error(f"Failed to cancel order {order['orderId']}: {str(e)}")
            
            logger.info(
                f"Canceled {success_count}/{len(open_orders)} orders for: {symbol}"
            )
            
            return success_count == len(open_orders)
            
        except BinanceAPIException as e:
            logger.error(f"Failed to cancel all orders: {e.message}")
            raise OrderException(f"Cancel all orders failed: {e.message}", details=e.details)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """
        열린 주문 조회
        
        Args:
            symbol: 심볼 (선택사항, None이면 모든 심볼)
            
        Returns:
            주문 리스트
            
        Raises:
            OrderException: 조회 실패 시
        """
        try:
            from src.services.binance.endpoints import ENDPOINTS
            
            params = {}
            if symbol:
                params["symbol"] = symbol
            
            logger.info(f"Getting open orders for: {symbol or 'all symbols'}")
            
            orders = await self.client._request(
                "GET",
                ENDPOINTS["open_orders"],
                params,
                signed=True
            )
            
            logger.info(f"Found {len(orders)} open orders")
            return orders
            
        except BinanceAPIException as e:
            logger.error(f"Failed to get open orders: {e.message}")
            raise OrderException(f"Get open orders failed: {e.message}", details=e.details)
    
    async def _record_trade(
        self,
        order_result: OrderResponse,
        strategy_id: Optional[UUID] = None,
    ) -> Trade:
        """
        거래 기록을 데이터베이스에 저장
        
        Args:
            order_result: 주문 응답
            strategy_id: 전략 ID
            
        Returns:
            저장된 거래 객체
        """
        try:
            # 전략 이름 조회 (strategy_id가 있는 경우)
            strategy_name = None
            if strategy_id:
                from src.models.database import StrategyConfig
                result = await self.db.execute(
                    select(StrategyConfig).where(StrategyConfig.id == strategy_id)
                )
                strategy = result.scalar_one_or_none()
                if strategy:
                    strategy_name = strategy.name
            
            # 거래 기록 생성
            trade = Trade(
                user_id=self.user_id,
                symbol=order_result.symbol,
                side=order_result.side,
                order_type=order_result.order_type,
                quantity=order_result.quantity,
                price=order_result.price,
                executed_price=order_result.price,
                status=order_result.status,
                strategy_name=strategy_name,
                executed_at=datetime.utcnow() if order_result.status == "FILLED" else None,
            )
            
            self.db.add(trade)
            await self.db.commit()
            await self.db.refresh(trade)
            
            logger.info(f"Trade record saved: {trade.id}")
            return trade
            
        except Exception as e:
            logger.error(f"Failed to record trade: {str(e)}")
            # 거래 기록 실패는 주문 실행에 영향을 주지 않음
            await self.db.rollback()
            raise
