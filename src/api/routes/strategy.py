"""전략 관련 라우트"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime
import pandas as pd

from src.db import get_db
from src.models.schemas import (
    StrategyConfigCreate, StrategyConfigUpdate, StrategyConfigResponse,
    SignalResponse, BacktestRequest, BacktestResultResponse,
)
from src.models.database import User, StrategyConfig, Signal, BacktestResult as DBBacktestResult
from src.api.dependencies import get_current_user
from src.strategies.configs.default_config import StrategyConfig as StrategyConfigClass
from src.strategies.integrated_strategy import IntegratedStrategy
from src.backtesting.engine import BacktestEngine

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.post("", response_model=StrategyConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    config: StrategyConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigResponse:
    """
    전략 설정 생성
    
    Args:
        config: 전략 설정
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        생성된 전략 설정
    """
    # 전략 설정 생성
    strategy_config = StrategyConfig(
        user_id=current_user.id,
        name=config.name,
        symbols=config.symbols,
        timeframe=config.timeframe,
        k_value=config.k_value,
        rsi_overbought=config.rsi_overbought,
        rsi_oversold=config.rsi_oversold,
        fund_flow_threshold=config.fund_flow_threshold,
        max_position_pct=config.max_position_pct,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_ratio=config.take_profit_ratio,
        mode=config.mode,
    )
    
    db.add(strategy_config)
    await db.commit()
    await db.refresh(strategy_config)
    
    return strategy_config


@router.get("", response_model=List[StrategyConfigResponse])
async def list_strategies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[StrategyConfigResponse]:
    """
    사용자의 전략 목록 조회
    
    Args:
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        전략 설정 리스트
    """
    result = await db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.user_id == current_user.id)
        .order_by(StrategyConfig.created_at.desc())
    )
    strategies = result.scalars().all()
    
    return strategies


@router.get("/{strategy_id}", response_model=StrategyConfigResponse)
async def get_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigResponse:
    """
    특정 전략 설정 조회
    
    Args:
        strategy_id: 전략 ID
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        전략 설정
    """
    result = await db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.id == strategy_id)
        .where(StrategyConfig.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    
    return strategy


@router.put("/{strategy_id}", response_model=StrategyConfigResponse)
async def update_strategy(
    strategy_id: UUID,
    config: StrategyConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigResponse:
    """
    전략 설정 수정
    
    Args:
        strategy_id: 전략 ID
        config: 수정할 설정
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        수정된 전략 설정
    """
    # 전략 조회
    result = await db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.id == strategy_id)
        .where(StrategyConfig.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    
    # 수정할 필드만 업데이트
    update_data = config.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(strategy, field, value)
    
    strategy.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(strategy)
    
    return strategy


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    전략 설정 삭제
    
    Args:
        strategy_id: 전략 ID
        current_user: 현재 사용자
        db: 데이터베이스 세션
    """
    result = await db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.id == strategy_id)
        .where(StrategyConfig.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    
    await db.delete(strategy)
    await db.commit()


@router.post("/{strategy_id}/backtest", response_model=BacktestResultResponse)
async def run_backtest(
    strategy_id: UUID,
    request: BacktestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacktestResultResponse:
    """
    백테스팅 실행
    
    Args:
        strategy_id: 전략 ID
        request: 백테스트 요청
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        백테스트 결과
    """
    # 전략 조회
    result = await db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.id == strategy_id)
        .where(StrategyConfig.user_id == current_user.id)
    )
    strategy_config = result.scalar_one_or_none()
    
    if not strategy_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    
    # 전략 설정 객체 생성
    config = StrategyConfigClass(
        symbols=[request.symbol],
        timeframe=strategy_config.timeframe,
        k_value=float(strategy_config.k_value),
        trend_ma_period=20,
        rsi_length=14,
        rsi_overbought=strategy_config.rsi_overbought,
        rsi_oversold=strategy_config.rsi_oversold,
        fund_flow_threshold=strategy_config.fund_flow_threshold,
        max_position_pct=float(strategy_config.max_position_pct),
        stop_loss_pct=float(strategy_config.stop_loss_pct),
        take_profit_ratio=float(strategy_config.take_profit_ratio),
        mode=strategy_config.mode,
    )
    
    # 전략 생성
    strategy = IntegratedStrategy(config)
    
    # 백테스팅 엔진 생성
    engine = BacktestEngine(strategy, initial_capital=request.initial_capital)
    
    # 샘플 데이터 생성 (실제로는 바이낸스 API에서 가져와야 함)
    # 여기서는 간단한 더미 데이터 사용
    date_range = pd.date_range(
        start=request.start_date,
        end=request.end_date,
        freq='1H'
    )
    
    df_1h = pd.DataFrame({
        'open': [100.0] * len(date_range),
        'high': [105.0] * len(date_range),
        'low': [95.0] * len(date_range),
        'close': [100.0 + i * 0.1 for i in range(len(date_range))],
        'volume': [1000.0] * len(date_range),
    }, index=date_range)
    
    df_4h = df_1h.resample('4H').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    
    df_15m = df_1h.resample('15T').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    
    # 백테스팅 실행
    try:
        backtest_result = await engine.run(
            symbol=request.symbol,
            df_1h=df_1h,
            df_4h=df_4h,
            df_15m=df_15m,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {str(e)}",
        )
    
    # 데이터베이스에 저장
    db_result = DBBacktestResult(
        strategy_id=strategy_id,
        symbol=backtest_result.symbol,
        start_date=backtest_result.start_date,
        end_date=backtest_result.end_date,
        initial_capital=backtest_result.initial_capital,
        final_capital=backtest_result.final_capital,
        total_return=backtest_result.total_return,
        win_rate=backtest_result.win_rate,
        profit_factor=backtest_result.profit_factor,
        max_drawdown=backtest_result.max_drawdown,
        sharpe_ratio=backtest_result.sharpe_ratio,
        total_trades=backtest_result.total_trades,
        avg_profit=backtest_result.avg_profit,
        avg_loss=backtest_result.avg_loss,
        trades_json=backtest_result.trades,
    )
    
    db.add(db_result)
    await db.commit()
    await db.refresh(db_result)
    
    return db_result


@router.get("/{strategy_id}/signals", response_model=List[SignalResponse])
async def get_signals(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[SignalResponse]:
    """
    현재 전략 신호 조회
    
    Args:
        strategy_id: 전략 ID
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        신호 리스트
    """
    # 전략 존재 확인
    result = await db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.id == strategy_id)
        .where(StrategyConfig.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    
    # 신호 조회
    result = await db.execute(
        select(Signal)
        .where(Signal.strategy_id == strategy_id)
        .order_by(Signal.created_at.desc())
        .limit(100)
    )
    signals = result.scalars().all()
    
    return signals


@router.get("/{strategy_id}/backtest-results", response_model=List[BacktestResultResponse])
async def get_backtest_results(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[BacktestResultResponse]:
    """
    백테스트 결과 조회
    
    Args:
        strategy_id: 전략 ID
        current_user: 현재 사용자
        db: 데이터베이스 세션
        
    Returns:
        백테스트 결과 리스트
    """
    # 전략 존재 확인
    result = await db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.id == strategy_id)
        .where(StrategyConfig.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    
    # 백테스트 결과 조회
    result = await db.execute(
        select(DBBacktestResult)
        .where(DBBacktestResult.strategy_id == strategy_id)
        .order_by(DBBacktestResult.created_at.desc())
    )
    results = result.scalars().all()
    
    return results
