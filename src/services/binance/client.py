"""바이낸스 API 클라이언트"""
import hashlib
import hmac
import time
from typing import List, Dict, Any, Optional
from decimal import Decimal
import httpx
from loguru import logger

from src.core.exceptions import BinanceAPIException
from src.models.schemas import (
    Kline, AccountBalance, PositionRisk, 
    OrderRequest, OrderResponse
)
from .endpoints import ENDPOINTS


class BinanceClient:
    """바이낸스 선물 API 클라이언트"""
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://testnet.binancefuture.com",
        testnet: bool = True,
    ):
        """
        초기화
        
        Args:
            api_key: API 키
            api_secret: API 시크릿
            base_url: 기본 URL
            testnet: 테스트넷 사용 여부
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.testnet = testnet
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        HMAC SHA256 서명 생성
        
        Args:
            params: 파라미터 딕셔너리
            
        Returns:
            서명 문자열
        """
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature
    
    def _get_headers(self) -> Dict[str, str]:
        """요청 헤더 생성"""
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/json",
        }
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """
        API 요청
        
        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트
            params: 파라미터
            signed: 서명 필요 여부
            
        Returns:
            응답 데이터
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        if params is None:
            params = {}
        
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._generate_signature(params)
        
        try:
            if method == "GET":
                response = await self.client.get(url, params=params, headers=headers)
            elif method == "POST":
                response = await self.client.post(url, params=params, headers=headers)
            elif method == "DELETE":
                response = await self.client.delete(url, params=params, headers=headers)
            else:
                raise BinanceAPIException(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise BinanceAPIException(error_msg, details=e.response.text)
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise BinanceAPIException(f"Request failed: {str(e)}")
    
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Kline]:
        """
        캔들 데이터 조회
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            interval: 간격 (1m, 5m, 15m, 30m, 1h, 4h, 1d, etc.)
            limit: 조회 개수 (기본: 500, 최대: 1500)
            start_time: 시작 시간 (밀리초)
            end_time: 종료 시간 (밀리초)
            
        Returns:
            캔들 데이터 리스트
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        data = await self._request("GET", ENDPOINTS["klines"], params)
        
        return [
            Kline(
                open_time=k[0],
                open_price=Decimal(k[1]),
                high_price=Decimal(k[2]),
                low_price=Decimal(k[3]),
                close_price=Decimal(k[4]),
                volume=Decimal(k[5]),
                close_time=k[6],
                quote_asset_volume=Decimal(k[7]),
                number_of_trades=k[8],
            )
            for k in data
        ]
    
    async def get_account_balance(self) -> List[AccountBalance]:
        """
        계좌 잔고 조회
        
        Returns:
            잔고 리스트
        """
        data = await self._request("GET", ENDPOINTS["balance"], signed=True)
        
        return [
            AccountBalance(
                asset=b["asset"],
                balance=Decimal(b["balance"]),
                available_balance=Decimal(b["availableBalance"]),
                unrealized_pnl=Decimal(b.get("crossUnPnl", "0")),
            )
            for b in data
        ]
    
    async def get_position_risk(self, symbol: Optional[str] = None) -> List[PositionRisk]:
        """
        포지션 리스크 조회
        
        Args:
            symbol: 심볼 (선택사항)
            
        Returns:
            포지션 리스크 리스트
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        data = await self._request("GET", ENDPOINTS["position_risk"], params, signed=True)
        
        return [
            PositionRisk(
                symbol=p["symbol"],
                position_side=p["positionSide"],
                position_amount=Decimal(p["positionAmt"]),
                entry_price=Decimal(p["entryPrice"]),
                mark_price=Decimal(p["markPrice"]),
                unrealized_profit=Decimal(p["unRealizedProfit"]),
                leverage=int(p["leverage"]),
            )
            for p in data
            if Decimal(p["positionAmt"]) != 0  # 포지션이 있는 것만
        ]
    
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """
        주문 실행
        
        Args:
            order: 주문 요청
            
        Returns:
            주문 응답
        """
        params = {
            "symbol": order.symbol,
            "side": order.side,
            "type": order.order_type,
            "quantity": str(order.quantity),
        }
        
        if order.position_side:
            params["positionSide"] = order.position_side
        
        if order.reduce_only:
            params["reduceOnly"] = "true"
        
        if order.order_type == "LIMIT":
            if not order.price:
                raise BinanceAPIException("Price is required for LIMIT order")
            params["price"] = str(order.price)
            params["timeInForce"] = order.time_in_force or "GTC"
        
        data = await self._request("POST", ENDPOINTS["order"], params, signed=True)
        
        return OrderResponse(
            order_id=str(data["orderId"]),
            symbol=data["symbol"],
            side=data["side"],
            order_type=data["type"],
            quantity=Decimal(data["origQty"]),
            price=Decimal(data["price"]) if data.get("price") else None,
            status=data["status"],
            created_at=data["updateTime"],
        )
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        주문 취소
        
        Args:
            symbol: 심볼
            order_id: 주문 ID
            
        Returns:
            성공 여부
        """
        params = {
            "symbol": symbol,
            "orderId": order_id,
        }
        
        try:
            await self._request("DELETE", ENDPOINTS["order"], params, signed=True)
            return True
        except BinanceAPIException:
            return False
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        레버리지 설정
        
        Args:
            symbol: 심볼
            leverage: 레버리지 (1-125)
            
        Returns:
            성공 여부
        """
        params = {
            "symbol": symbol,
            "leverage": leverage,
        }
        
        try:
            await self._request("POST", ENDPOINTS["leverage"], params, signed=True)
            return True
        except BinanceAPIException:
            return False
    
    async def ping(self) -> bool:
        """
        서버 연결 테스트
        
        Returns:
            연결 성공 여부
        """
        try:
            await self._request("GET", ENDPOINTS["ping"])
            return True
        except BinanceAPIException:
            return False
    
    async def get_server_time(self) -> int:
        """
        서버 시간 조회
        
        Returns:
            서버 시간 (밀리초)
        """
        data = await self._request("GET", ENDPOINTS["time"])
        return data["serverTime"]
