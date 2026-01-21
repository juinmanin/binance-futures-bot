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
