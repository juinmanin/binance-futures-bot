"""SQLAlchemy 데이터베이스 모델"""
from datetime import datetime
from typing import List, Optional
from uuid import uuid4
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, 
    Numeric, String, Text, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """사용자 테이블"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_2fa_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="user")
    strategy_configs = relationship("StrategyConfig", back_populates="user")


class APIKey(Base):
    """API 키 테이블 (암호화 저장)"""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exchange = Column(String(50), nullable=False, default="binance")
    encrypted_api_key = Column(Text, nullable=False)
    encrypted_api_secret = Column(Text, nullable=False)
    is_testnet = Column(Boolean, default=True)
    ip_whitelist = Column(ARRAY(Text))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="api_keys")


class Trade(Base):
    """거래 기록 테이블"""
    __tablename__ = "trades"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # BUY, SELL
    position_side = Column(String(10))  # LONG, SHORT, BOTH
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT, STOP, etc.
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8))
    executed_price = Column(Numeric(20, 8))
    status = Column(String(20), nullable=False)  # NEW, FILLED, CANCELED, etc.
    strategy_name = Column(String(50))
    signal_source = Column(JSONB)
    pnl = Column(Numeric(20, 8))
    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="trades")


class StrategyConfig(Base):
    """전략 설정 테이블"""
    __tablename__ = "strategy_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    symbols = Column(ARRAY(Text), nullable=False)
    timeframe = Column(String(10), default="1h")
    k_value = Column(Numeric(3, 2), default=0.5)
    rsi_overbought = Column(Integer, default=80)
    rsi_oversold = Column(Integer, default=20)
    fund_flow_threshold = Column(Integer, default=10)
    max_position_pct = Column(Numeric(5, 2), default=1.0)
    stop_loss_pct = Column(Numeric(5, 2), default=2.0)
    take_profit_ratio = Column(Numeric(3, 1), default=2.0)
    is_active = Column(Boolean, default=False)
    mode = Column(String(20), default="paper")  # paper, live
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="strategy_configs")
    signals = relationship("Signal", back_populates="strategy_config", cascade="all, delete-orphan")
    backtest_results = relationship("BacktestResult", back_populates="strategy_config", cascade="all, delete-orphan")


class Signal(Base):
    """전략 신호 기록"""
    __tablename__ = "signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategy_configs.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)  # BUY/SELL/HOLD
    confidence = Column(Numeric(3, 2), nullable=False)
    entry_price = Column(Numeric(20, 8))
    stop_loss = Column(Numeric(20, 8))
    take_profit_1 = Column(Numeric(20, 8))
    take_profit_2 = Column(Numeric(20, 8))
    position_size = Column(Numeric(20, 8))
    reason = Column(Text)
    indicators = Column(JSONB)  # 신호 발생 시점의 지표 값들
    created_at = Column(DateTime, default=datetime.utcnow)
    expired_at = Column(DateTime)  # 신호 만료 시간
    status = Column(String(20), default="PENDING")  # PENDING/EXECUTED/EXPIRED/CANCELLED
    
    # Relationships
    strategy_config = relationship("StrategyConfig", back_populates="signals")


class BacktestResult(Base):
    """백테스팅 결과"""
    __tablename__ = "backtest_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategy_configs.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    initial_capital = Column(Numeric(20, 2), nullable=False)
    final_capital = Column(Numeric(20, 2), nullable=False)
    total_return = Column(Numeric(10, 2))
    win_rate = Column(Numeric(5, 2))
    profit_factor = Column(Numeric(10, 2))
    max_drawdown = Column(Numeric(5, 2))
    sharpe_ratio = Column(Numeric(10, 2))
    total_trades = Column(Integer)
    avg_profit = Column(Numeric(20, 8))
    avg_loss = Column(Numeric(20, 8))
    trades_json = Column(JSONB)  # 개별 거래 기록
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    strategy_config = relationship("StrategyConfig", back_populates="backtest_results")
