"""실시간 데이터 관리"""
import asyncio
import json
from typing import Dict, List, Callable, Optional, Any
from loguru import logger

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis.asyncio not available, caching will be disabled")

from src.services.binance.websocket import BinanceWebSocket
from src.config import settings


class RealtimeDataManager:
    """실시간 데이터 관리"""
    
    def __init__(
        self,
        binance_ws: Optional[BinanceWebSocket] = None,
        redis_client: Optional[Any] = None
    ):
        """
        초기화
        
        Args:
            binance_ws: 바이낸스 WebSocket 클라이언트
            redis_client: Redis 클라이언트
        """
        self.ws = binance_ws or BinanceWebSocket(ws_url=settings.binance_ws_url)
        self.redis = redis_client
        self.callbacks: Dict[str, List[Callable]] = {}
        self.reconnect_attempts: Dict[str, int] = {}
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # seconds
        
    async def start(self):
        """WebSocket 연결 시작 및 재연결 로직"""
        logger.info("Starting RealtimeDataManager...")
        self.ws.running = True
        
        # Redis 연결 테스트 (사용 가능한 경우)
        if self.redis and REDIS_AVAILABLE:
            try:
                await self.redis.ping()
                logger.info("Redis connection established")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, caching disabled")
                self.redis = None
        else:
            logger.info("Redis not configured, caching disabled")
    
    async def stop(self):
        """WebSocket 연결 종료"""
        logger.info("Stopping RealtimeDataManager...")
        await self.ws.close_all()
        
        if self.redis and REDIS_AVAILABLE:
            try:
                await self.redis.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
    
    async def subscribe_klines(
        self,
        symbols: List[str],
        intervals: List[str],
        callback: Callable
    ):
        """
        다중 심볼/타임프레임 캔들 구독
        
        Args:
            symbols: 심볼 리스트 (예: ['BTCUSDT', 'ETHUSDT'])
            intervals: 타임프레임 리스트 (예: ['1m', '5m', '1h'])
            callback: 데이터 수신 콜백 함수
        """
        for symbol in symbols:
            for interval in intervals:
                stream_key = f"{symbol}:{interval}"
                
                # 콜백 등록
                if stream_key not in self.callbacks:
                    self.callbacks[stream_key] = []
                self.callbacks[stream_key].append(callback)
                
                # WebSocket 구독
                async def kline_handler(data: dict):
                    await self.on_kline_update(data, symbol, interval)
                
                try:
                    await self.ws.subscribe_kline(
                        symbol=symbol.lower(),
                        interval=interval,
                        callback=kline_handler
                    )
                    logger.info(f"Subscribed to kline: {stream_key}")
                except Exception as e:
                    logger.error(f"Failed to subscribe to {stream_key}: {e}")
    
    async def subscribe_user_data(self, listen_key: str, callback: Callable):
        """
        사용자 데이터 스트림 (주문 체결, 포지션 변경 등)
        
        Args:
            listen_key: Binance Listen Key
            callback: 데이터 수신 콜백 함수
        """
        stream_key = f"user_data:{listen_key[:8]}"
        
        # 콜백 등록
        if stream_key not in self.callbacks:
            self.callbacks[stream_key] = []
        self.callbacks[stream_key].append(callback)
        
        # WebSocket 구독
        async def user_data_handler(data: dict):
            await self.on_user_data_update(data)
        
        try:
            await self.ws.subscribe_user_data(
                listen_key=listen_key,
                callback=user_data_handler
            )
            logger.info(f"Subscribed to user data stream")
        except Exception as e:
            logger.error(f"Failed to subscribe to user data: {e}")
    
    async def on_kline_update(self, data: dict, symbol: str, interval: str):
        """
        캔들 업데이트 처리 - Redis 캐싱
        
        Args:
            data: WebSocket 데이터
            symbol: 심볼
            interval: 타임프레임
        """
        try:
            stream_key = f"{symbol}:{interval}"
            
            # Redis에 캐싱 (사용 가능한 경우)
            if self.redis and REDIS_AVAILABLE:
                cache_key = f"kline:{symbol}:{interval}"
                try:
                    await self.redis.set(
                        cache_key,
                        json.dumps(data),
                        ex=60  # 60초 TTL
                    )
                    logger.debug(f"Cached kline data: {cache_key}")
                except Exception as e:
                    logger.warning(f"Failed to cache kline data: {e}")
            
            # 등록된 콜백 실행
            callbacks = self.callbacks.get(stream_key, [])
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"Error in kline callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing kline update: {e}")
    
    async def on_order_update(self, data: dict):
        """
        주문 상태 업데이트 처리
        
        Args:
            data: 주문 업데이트 데이터
        """
        try:
            event_type = data.get("e")
            
            if event_type == "ORDER_TRADE_UPDATE":
                order_data = data.get("o", {})
                symbol = order_data.get("s")
                order_id = order_data.get("i")
                status = order_data.get("X")
                
                logger.info(
                    f"Order update: {symbol} #{order_id} - {status}"
                )
                
                # Redis에 캐싱
                if self.redis and REDIS_AVAILABLE:
                    cache_key = f"order:{symbol}:{order_id}"
                    try:
                        await self.redis.set(
                            cache_key,
                            json.dumps(order_data),
                            ex=3600  # 1시간 TTL
                        )
                    except Exception as e:
                        logger.warning(f"Failed to cache order data: {e}")
                
                # 콜백 실행
                callbacks = self.callbacks.get("order_update", [])
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(order_data)
                        else:
                            callback(order_data)
                    except Exception as e:
                        logger.error(f"Error in order callback: {e}")
                        
        except Exception as e:
            logger.error(f"Error processing order update: {e}")
    
    async def on_position_update(self, data: dict):
        """
        포지션 변경 처리
        
        Args:
            data: 포지션 업데이트 데이터
        """
        try:
            event_type = data.get("e")
            
            if event_type == "ACCOUNT_UPDATE":
                positions = data.get("a", {}).get("P", [])
                
                for position in positions:
                    symbol = position.get("s")
                    position_amount = position.get("pa")
                    entry_price = position.get("ep")
                    unrealized_pnl = position.get("up")
                    
                    logger.info(
                        f"Position update: {symbol} "
                        f"Amount={position_amount}, "
                        f"Entry=${entry_price}, "
                        f"PnL=${unrealized_pnl}"
                    )
                    
                    # Redis에 캐싱
                    if self.redis and REDIS_AVAILABLE:
                        cache_key = f"position:{symbol}"
                        try:
                            await self.redis.set(
                                cache_key,
                                json.dumps(position),
                                ex=60  # 60초 TTL
                            )
                        except Exception as e:
                            logger.warning(f"Failed to cache position data: {e}")
                    
                # 콜백 실행
                callbacks = self.callbacks.get("position_update", [])
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(positions)
                        else:
                            callback(positions)
                    except Exception as e:
                        logger.error(f"Error in position callback: {e}")
                        
        except Exception as e:
            logger.error(f"Error processing position update: {e}")
    
    async def on_user_data_update(self, data: dict):
        """
        사용자 데이터 업데이트 라우팅
        
        Args:
            data: 사용자 데이터
        """
        event_type = data.get("e")
        
        if event_type == "ORDER_TRADE_UPDATE":
            await self.on_order_update(data)
        elif event_type == "ACCOUNT_UPDATE":
            await self.on_position_update(data)
        else:
            logger.debug(f"Unhandled user data event: {event_type}")
    
    async def get_cached_kline(
        self,
        symbol: str,
        interval: str
    ) -> Optional[dict]:
        """
        캐시된 캔들 데이터 조회
        
        Args:
            symbol: 심볼
            interval: 타임프레임
            
        Returns:
            캔들 데이터 (캐시된 경우), None (캐시 없음)
        """
        if not self.redis or not REDIS_AVAILABLE:
            return None
        
        cache_key = f"kline:{symbol}:{interval}"
        try:
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached kline: {e}")
        
        return None
    
    async def handle_reconnection(self, stream_key: str, subscribe_func: Callable):
        """
        재연결 처리
        
        Args:
            stream_key: 스트림 식별자
            subscribe_func: 재구독 함수
        """
        if stream_key not in self.reconnect_attempts:
            self.reconnect_attempts[stream_key] = 0
        
        self.reconnect_attempts[stream_key] += 1
        
        if self.reconnect_attempts[stream_key] > self.max_reconnect_attempts:
            logger.error(
                f"Max reconnection attempts reached for {stream_key}, "
                f"giving up"
            )
            return
        
        logger.info(
            f"Attempting to reconnect {stream_key} "
            f"(attempt {self.reconnect_attempts[stream_key]})"
        )
        
        await asyncio.sleep(self.reconnect_delay)
        
        try:
            await subscribe_func()
            self.reconnect_attempts[stream_key] = 0  # 성공 시 재설정
            logger.info(f"Successfully reconnected to {stream_key}")
        except Exception as e:
            logger.error(f"Reconnection failed for {stream_key}: {e}")
            # 다시 재연결 시도
            await self.handle_reconnection(stream_key, subscribe_func)
