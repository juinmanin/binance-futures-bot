"""Pydantic 스키마"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


# User 스키마
class UserBase(BaseModel):
    """사용자 기본 스키마"""
    email: EmailStr


class UserCreate(UserBase):
    """사용자 생성 스키마"""
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    """사용자 로그인 스키마"""
    email: EmailStr
    password: str


class UserResponse(UserBase):
    """사용자 응답 스키마"""
    id: UUID
    is_active: bool
    is_2fa_enabled: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}


# Token 스키마
class Token(BaseModel):
    """토큰 스키마"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """토큰 데이터 스키마"""
    user_id: Optional[UUID] = None
    email: Optional[str] = None


# API Key 스키마
class APIKeyCreate(BaseModel):
    """UI에서 입력받은 API 키 데이터"""
    api_key: str = Field(..., min_length=20, max_length=100, description="바이낸스 API Key")
    api_secret: str = Field(..., min_length=20, max_length=100, description="바이낸스 API Secret")
    is_testnet: bool = Field(default=True, description="테스트넷 여부")
    label: str = Field(default="Default", max_length=50, description="API 키 라벨")


class APIKeyResponse(BaseModel):
    """마스킹된 API 키 응답"""
    id: UUID
    label: str
    masked_api_key: str  # 예: "abcd************"
    exchange: str
    is_testnet: bool
    is_default: bool = False
    created_at: datetime
    last_used_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class APIKeyVerifyResponse(BaseModel):
    """API 키 검증 결과"""
    is_valid: bool
    message: str
    account_type: Optional[str] = None  # TESTNET/MAINNET
    can_trade: bool = False
    can_withdraw: bool = False


# Trading 스키마
class OrderRequest(BaseModel):
    """주문 요청 스키마"""
    symbol: str
    side: str  # BUY, SELL
    position_side: Optional[str] = "BOTH"  # LONG, SHORT, BOTH
    order_type: str = "MARKET"  # MARKET, LIMIT, STOP, etc.
    quantity: Decimal
    price: Optional[Decimal] = None
    time_in_force: Optional[str] = "GTC"
    reduce_only: Optional[bool] = False


class OrderResponse(BaseModel):
    """주문 응답 스키마"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Optional[Decimal]
    status: str
    created_at: datetime


class AccountBalance(BaseModel):
    """계좌 잔고 스키마"""
    asset: str
    balance: Decimal
    available_balance: Decimal
    unrealized_pnl: Decimal


class PositionRisk(BaseModel):
    """포지션 리스크 스키마"""
    symbol: str
    position_side: str
    position_amount: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_profit: Decimal
    leverage: int


class Kline(BaseModel):
    """캔들 데이터 스키마"""
    open_time: int
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    close_time: int
    quote_asset_volume: Decimal
    number_of_trades: int


# Strategy 스키마
class StrategyConfigCreate(BaseModel):
    """전략 설정 생성 스키마"""
    name: str
    symbols: List[str]
    timeframe: str = "1h"
    k_value: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    rsi_overbought: int = Field(default=80, ge=50, le=100)
    rsi_oversold: int = Field(default=20, ge=0, le=50)
    fund_flow_threshold: int = Field(default=10, ge=0)
    max_position_pct: Decimal = Field(default=Decimal("1.0"), ge=0, le=100)
    stop_loss_pct: Decimal = Field(default=Decimal("2.0"), ge=0, le=100)
    take_profit_ratio: Decimal = Field(default=Decimal("2.0"), ge=0)
    mode: str = "paper"


class StrategyConfigUpdate(BaseModel):
    """전략 설정 수정 스키마"""
    name: Optional[str] = None
    symbols: Optional[List[str]] = None
    timeframe: Optional[str] = None
    k_value: Optional[Decimal] = None
    rsi_overbought: Optional[int] = None
    rsi_oversold: Optional[int] = None
    fund_flow_threshold: Optional[int] = None
    max_position_pct: Optional[Decimal] = None
    stop_loss_pct: Optional[Decimal] = None
    take_profit_ratio: Optional[Decimal] = None
    is_active: Optional[bool] = None
    mode: Optional[str] = None


class StrategyConfigResponse(StrategyConfigCreate):
    """전략 설정 응답 스키마"""
    id: UUID
    user_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


# Pending Signal 스키마
class PendingSignalCreate(BaseModel):
    """대기 중인 신호 생성 스키마"""
    symbol: str
    action: str  # BUY, SELL
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal
    take_profit_2: Decimal
    position_size: Optional[Decimal] = None
    atr: Optional[Decimal] = None
    confidence: Optional[Decimal] = None
    reason: Optional[str] = None
    strategy_name: Optional[str] = None


class PendingSignalResponse(BaseModel):
    """대기 중인 신호 응답 스키마"""
    id: UUID
    symbol: str
    action: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal
    take_profit_2: Decimal
    position_size: Optional[Decimal] = None
    confidence: Optional[Decimal] = None
    reason: Optional[str] = None
    strategy_name: Optional[str] = None
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None
class StrategySignal(BaseModel):
    """전략 신호 스키마"""
    action: str  # BUY/SELL/HOLD
    confidence: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit_1: Optional[float]
    take_profit_2: Optional[float]
    position_size: Optional[float]
    reason: str
    indicators: Dict[str, Any]


class SignalResponse(BaseModel):
    """신호 응답 스키마"""
    id: UUID
    strategy_id: UUID
    symbol: str
    timeframe: str
    action: str
    confidence: Decimal
    entry_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    take_profit_1: Optional[Decimal]
    take_profit_2: Optional[Decimal]
    position_size: Optional[Decimal]
    reason: Optional[str]
    indicators: Optional[Dict[str, Any]]
    created_at: datetime
    status: str
    
    model_config = {"from_attributes": True}


class BacktestRequest(BaseModel):
    """백테스트 요청 스키마"""
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10000.0


class BacktestResultResponse(BaseModel):
    """백테스트 결과 응답 스키마"""
    id: UUID
    strategy_id: UUID
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    final_capital: Decimal
    total_return: Optional[Decimal]
    win_rate: Optional[Decimal]
    profit_factor: Optional[Decimal]
    max_drawdown: Optional[Decimal]
    sharpe_ratio: Optional[Decimal]
    total_trades: Optional[int]
    avg_profit: Optional[Decimal]
    avg_loss: Optional[Decimal]
    created_at: datetime
    
    model_config = {"from_attributes": True}


# Health Check
class HealthCheck(BaseModel):
    """헬스 체크 스키마"""
    status: str
    timestamp: datetime
    version: str = "1.0.0"
