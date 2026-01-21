"""바이낸스 API 클라이언트 테스트"""
import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal

from src.services.binance import BinanceClient
from src.models.schemas import OrderRequest


@pytest.mark.asyncio
async def test_binance_client_initialization():
    """바이낸스 클라이언트 초기화 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
        testnet=True,
    )
    
    assert client.api_key == "test_api_key"
    assert client.api_secret == "test_api_secret"
    assert client.testnet is True


@pytest.mark.asyncio
async def test_binance_client_signature_generation():
    """바이낸스 클라이언트 서명 생성 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
    )
    
    params = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "1",
    }
    
    signature = client._generate_signature(params)
    
    assert isinstance(signature, str)
    assert len(signature) == 64  # HMAC SHA256 produces 64 character hex string


@pytest.mark.asyncio
async def test_binance_client_ping():
    """바이낸스 클라이언트 ping 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
    )
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {}
        
        async with client:
            result = await client.ping()
        
        assert result is True
        mock_request.assert_called_once()


@pytest.mark.asyncio
async def test_binance_client_get_server_time():
    """바이낸스 클라이언트 서버 시간 조회 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
    )
    
    expected_time = 1704067200000
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"serverTime": expected_time}
        
        async with client:
            result = await client.get_server_time()
        
        assert result == expected_time


@pytest.mark.asyncio
async def test_binance_client_get_klines():
    """바이낸스 클라이언트 캔들 조회 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
    )
    
    mock_klines_data = [
        [
            1704067200000,  # open_time
            "50000.00",     # open
            "51000.00",     # high
            "49500.00",     # low
            "50500.00",     # close
            "100.5",        # volume
            1704070800000,  # close_time
            "5050000.00",   # quote_volume
            1000,           # trades
        ]
    ]
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_klines_data
        
        async with client:
            klines = await client.get_klines("BTCUSDT", "1h", limit=1)
        
        assert len(klines) == 1
        assert klines[0].open_price == Decimal("50000.00")
        assert klines[0].close_price == Decimal("50500.00")


@pytest.mark.asyncio
async def test_binance_client_place_market_order():
    """바이낸스 클라이언트 시장가 주문 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
    )
    
    order_request = OrderRequest(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("1"),
    )
    
    mock_response = {
        "orderId": 123456,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "origQty": "1",
        "price": "0",
        "status": "FILLED",
        "updateTime": 1704067200000,
    }
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_response
        
        async with client:
            response = await client.place_order(order_request)
        
        assert response.order_id == "123456"
        assert response.symbol == "BTCUSDT"
        assert response.side == "BUY"
        assert response.status == "FILLED"


@pytest.mark.asyncio
async def test_binance_client_cancel_order():
    """바이낸스 클라이언트 주문 취소 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
    )
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"status": "CANCELED"}
        
        async with client:
            result = await client.cancel_order("BTCUSDT", "123456")
        
        assert result is True


@pytest.mark.asyncio
async def test_binance_client_set_leverage():
    """바이낸스 클라이언트 레버리지 설정 테스트"""
    client = BinanceClient(
        api_key="test_api_key",
        api_secret="test_api_secret",
    )
    
    with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"leverage": 10}
        
        async with client:
            result = await client.set_leverage("BTCUSDT", 10)
        
        assert result is True
