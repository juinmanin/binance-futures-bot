"""바이낸스 API 엔드포인트 상수"""

# Base URLs
BINANCE_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
BINANCE_MAINNET_BASE_URL = "https://fapi.binance.com"
BINANCE_TESTNET_WS_URL = "wss://stream.binancefuture.com"
BINANCE_MAINNET_WS_URL = "wss://fstream.binance.com"

# REST API Endpoints
ENDPOINTS = {
    # 시세 조회
    "klines": "/fapi/v1/klines",
    "ticker_24h": "/fapi/v1/ticker/24hr",
    "ticker_price": "/fapi/v1/ticker/price",
    
    # 주문
    "order": "/fapi/v1/order",
    "all_orders": "/fapi/v1/allOrders",
    "open_orders": "/fapi/v1/openOrders",
    
    # 계좌 정보
    "balance": "/fapi/v2/balance",
    "account": "/fapi/v2/account",
    "position_risk": "/fapi/v2/positionRisk",
    
    # 레버리지
    "leverage": "/fapi/v1/leverage",
    "margin_type": "/fapi/v1/marginType",
    
    # 유저 데이터 스트림
    "listen_key": "/fapi/v1/listenKey",
    
    # 시스템
    "ping": "/fapi/v1/ping",
    "time": "/fapi/v1/time",
    "exchange_info": "/fapi/v1/exchangeInfo",
}

# WebSocket Streams
WS_STREAMS = {
    "kline": "{symbol}@kline_{interval}",
    "ticker": "{symbol}@ticker",
    "depth": "{symbol}@depth",
    "trade": "{symbol}@trade",
    "agg_trade": "{symbol}@aggTrade",
    "book_ticker": "{symbol}@bookTicker",
    "liquidation": "{symbol}@forceOrder",
    "user_data": "{listen_key}",
}
