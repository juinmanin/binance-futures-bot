"""바이낸스 WebSocket 연결 관리"""
import asyncio
import json
from typing import Callable, Dict, Any, Optional
import websockets
from loguru import logger

from src.core.exceptions import WebSocketException
from .endpoints import WS_STREAMS


class BinanceWebSocket:
    """바이낸스 WebSocket 클라이언트"""
    
    def __init__(self, ws_url: str = "wss://stream.binancefuture.com"):
        """
        초기화
        
        Args:
            ws_url: WebSocket URL
        """
        self.ws_url = ws_url
        self.connections: Dict[str, Any] = {}
        self.running = False
    
    def _get_stream_url(self, stream: str) -> str:
        """
        스트림 URL 생성
        
        Args:
            stream: 스트림 이름
            
        Returns:
            전체 URL
        """
        return f"{self.ws_url}/ws/{stream}"
    
    async def subscribe_kline(
        self,
        symbol: str,
        interval: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """
        캔들 스트림 구독
        
        Args:
            symbol: 심볼 (소문자, 예: btcusdt)
            interval: 간격 (1m, 5m, 15m, 30m, 1h, 4h, 1d, etc.)
            callback: 데이터 수신 콜백 함수 (비동기 함수여야 함)
        """
        stream = WS_STREAMS["kline"].format(
            symbol=symbol.lower(),
            interval=interval,
        )
        await self._subscribe(stream, callback)
    
    async def subscribe_ticker(
        self,
        symbol: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """
        티커 스트림 구독
        
        Args:
            symbol: 심볼 (소문자, 예: btcusdt)
            callback: 데이터 수신 콜백 함수 (비동기 함수여야 함)
        """
        stream = WS_STREAMS["ticker"].format(symbol=symbol.lower())
        await self._subscribe(stream, callback)
    
    async def subscribe_user_data(
        self,
        listen_key: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """
        유저 데이터 스트림 구독
        
        Args:
            listen_key: Listen Key
            callback: 데이터 수신 콜백 함수 (비동기 함수여야 함)
        """
        # 유저 데이터 스트림은 다른 형식
        url = f"{self.ws_url}/ws/{listen_key}"
        stream_id = f"user_data_{listen_key[:8]}"
        
        async def connect():
            try:
                async with websockets.connect(url) as websocket:
                    self.connections[stream_id] = websocket
                    logger.info(f"Connected to user data stream: {stream_id}")
                    
                    while self.running:
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=30.0
                            )
                            data = json.loads(message)
                            # 콜백이 코루틴인지 확인하고 처리
                            if asyncio.iscoroutinefunction(callback):
                                await callback(data)
                            else:
                                callback(data)
                        except asyncio.TimeoutError:
                            # Ping-pong for keeping connection alive
                            await websocket.ping()
                        except Exception as e:
                            logger.error(f"Error receiving message: {e}")
                            break
                    
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                if stream_id in self.connections:
                    del self.connections[stream_id]
        
        if not self.running:
            self.running = True
        asyncio.create_task(connect())
    
    async def _subscribe(
        self,
        stream: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """
        스트림 구독 (내부 메서드)
        
        Args:
            stream: 스트림 이름
            callback: 데이터 수신 콜백 함수 (비동기 함수여야 함)
        """
        url = self._get_stream_url(stream)
        
        async def connect():
            try:
                async with websockets.connect(url) as websocket:
                    self.connections[stream] = websocket
                    logger.info(f"Connected to stream: {stream}")
                    
                    while self.running:
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=30.0
                            )
                            data = json.loads(message)
                            # 콜백이 코루틴인지 확인하고 처리
                            if asyncio.iscoroutinefunction(callback):
                                await callback(data)
                            else:
                                callback(data)
                        except asyncio.TimeoutError:
                            # Ping-pong for keeping connection alive
                            await websocket.ping()
                        except Exception as e:
                            logger.error(f"Error receiving message: {e}")
                            break
                    
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                if stream in self.connections:
                    del self.connections[stream]
        
        if not self.running:
            self.running = True
        asyncio.create_task(connect())
    
    async def unsubscribe(self, stream: str) -> None:
        """
        스트림 구독 취소
        
        Args:
            stream: 스트림 이름
        """
        if stream in self.connections:
            websocket = self.connections[stream]
            await websocket.close()
            del self.connections[stream]
            logger.info(f"Unsubscribed from stream: {stream}")
    
    async def close_all(self) -> None:
        """모든 WebSocket 연결 종료"""
        self.running = False
        for stream, websocket in self.connections.items():
            try:
                await websocket.close()
                logger.info(f"Closed stream: {stream}")
            except Exception as e:
                logger.error(f"Error closing stream {stream}: {e}")
        
        self.connections.clear()
