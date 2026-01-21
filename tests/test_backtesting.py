"""백테스팅 테스트"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.metrics import (
    calculate_total_return, calculate_win_rate, calculate_profit_factor,
    calculate_max_drawdown, calculate_sharpe_ratio, calculate_metrics_from_trades
)
from src.strategies.integrated_strategy import IntegratedStrategy
from src.strategies.configs.default_config import StrategyConfig


@pytest.fixture
def strategy():
    """전략 픽스처"""
    config = StrategyConfig(
        symbols=["BTCUSDT"],
        timeframe="1h",
        k_value=0.5,
        trend_ma_period=20,
        rsi_length=14,
        rsi_overbought=80,
        rsi_oversold=20,
        fund_flow_threshold=10,
        max_position_pct=1.0,
        stop_loss_pct=2.0,
        take_profit_ratio=2.0,
        mode="paper",
    )
    return IntegratedStrategy(config)


@pytest.fixture
def sample_backtest_data():
    """백테스팅용 샘플 데이터"""
    dates = pd.date_range(start='2024-01-01', periods=300, freq='1H')
    
    # 상승 추세 데이터
    base_price = 100.0
    trend = np.linspace(0, 30, 300)
    noise = np.random.randn(300) * 2
    
    close_prices = base_price + trend + noise
    
    df_1h = pd.DataFrame({
        'open': close_prices - np.random.rand(300) * 0.5,
        'high': close_prices + np.random.rand(300) * 3,
        'low': close_prices - np.random.rand(300) * 3,
        'close': close_prices,
        'volume': np.random.rand(300) * 1000 + 500,
    }, index=dates)
    
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
    
    return df_1h, df_4h, df_15m


class TestBacktestMetrics:
    """백테스팅 성과 지표 테스트"""
    
    def test_total_return(self):
        """총 수익률 계산 테스트"""
        initial = 10000.0
        final = 12000.0
        
        total_return = calculate_total_return(initial, final)
        
        assert total_return == 20.0  # 20% 수익
    
    def test_win_rate(self):
        """승률 계산 테스트"""
        wins = 7
        total = 10
        
        win_rate = calculate_win_rate(wins, total)
        
        assert win_rate == 70.0  # 70% 승률
    
    def test_win_rate_zero_trades(self):
        """거래 없을 때 승률 테스트"""
        win_rate = calculate_win_rate(0, 0)
        
        assert win_rate == 0.0
    
    def test_profit_factor(self):
        """수익 팩터 계산 테스트"""
        total_profit = 5000.0
        total_loss = -2000.0
        
        profit_factor = calculate_profit_factor(total_profit, total_loss)
        
        assert profit_factor == 2.5
    
    def test_profit_factor_no_loss(self):
        """손실 없을 때 수익 팩터 테스트"""
        profit_factor = calculate_profit_factor(5000.0, 0.0)
        
        assert profit_factor == float('inf')
    
    def test_max_drawdown(self):
        """최대 낙폭 계산 테스트"""
        equity_curve = pd.Series([10000, 11000, 10500, 9500, 10000, 11500])
        
        max_dd = calculate_max_drawdown(equity_curve)
        
        # 최대 낙폭은 11000 -> 9500 = -13.6%
        assert max_dd > 0  # 항상 양수로 반환
        assert 13 < max_dd < 14
    
    def test_sharpe_ratio(self):
        """샤프 비율 계산 테스트"""
        # 일별 수익률 시뮬레이션
        returns = pd.Series(np.random.randn(252) * 0.01 + 0.001)  # 평균 0.1% 일별 수익
        
        sharpe = calculate_sharpe_ratio(returns)
        
        assert isinstance(sharpe, float)
        # 샤프 비율은 일반적으로 -3 ~ 3 범위
        assert -5 < sharpe < 5
    
    def test_metrics_from_trades(self):
        """거래 내역으로부터 성과 지표 계산 테스트"""
        trades = [
            {'pnl': 100.0},
            {'pnl': 50.0},
            {'pnl': -30.0},
            {'pnl': 80.0},
            {'pnl': -20.0},
        ]
        
        metrics = calculate_metrics_from_trades(trades, initial_capital=10000.0)
        
        assert metrics.total_trades == 5
        assert metrics.total_return > 0  # 순익이 나왔으므로
        assert 0 < metrics.win_rate <= 100
        assert metrics.profit_factor > 0
    
    def test_metrics_from_empty_trades(self):
        """빈 거래 내역 테스트"""
        metrics = calculate_metrics_from_trades([], initial_capital=10000.0)
        
        assert metrics.total_trades == 0
        assert metrics.total_return == 0.0
        assert metrics.win_rate == 0.0


class TestBacktestEngine:
    """백테스팅 엔진 테스트"""
    
    def test_engine_initialization(self, strategy):
        """엔진 초기화 테스트"""
        engine = BacktestEngine(strategy, initial_capital=10000.0)
        
        assert engine.strategy == strategy
        assert engine.initial_capital == 10000.0
    
    @pytest.mark.asyncio
    async def test_run_backtest(self, strategy, sample_backtest_data):
        """백테스팅 실행 테스트"""
        df_1h, df_4h, df_15m = sample_backtest_data
        engine = BacktestEngine(strategy, initial_capital=10000.0)
        
        result = await engine.run(
            symbol="BTCUSDT",
            df_1h=df_1h,
            df_4h=df_4h,
            df_15m=df_15m,
            start_date=df_1h.index[0].to_pydatetime(),
            end_date=df_1h.index[-1].to_pydatetime(),
        )
        
        assert isinstance(result, BacktestResult)
        assert result.symbol == "BTCUSDT"
        assert result.initial_capital == 10000.0
        assert result.final_capital > 0
        assert isinstance(result.trades, list)
    
    @pytest.mark.asyncio
    async def test_backtest_result_attributes(self, strategy, sample_backtest_data):
        """백테스팅 결과 속성 테스트"""
        df_1h, df_4h, df_15m = sample_backtest_data
        engine = BacktestEngine(strategy, initial_capital=10000.0)
        
        result = await engine.run(
            symbol="BTCUSDT",
            df_1h=df_1h,
            df_4h=df_4h,
            df_15m=df_15m,
        )
        
        # 필수 속성 확인
        assert hasattr(result, 'symbol')
        assert hasattr(result, 'start_date')
        assert hasattr(result, 'end_date')
        assert hasattr(result, 'initial_capital')
        assert hasattr(result, 'final_capital')
        assert hasattr(result, 'total_return')
        assert hasattr(result, 'win_rate')
        assert hasattr(result, 'profit_factor')
        assert hasattr(result, 'max_drawdown')
        assert hasattr(result, 'sharpe_ratio')
        assert hasattr(result, 'total_trades')
        assert hasattr(result, 'trades')
        
        # 값 범위 확인
        assert 0 <= result.win_rate <= 100
        assert result.profit_factor >= 0
        assert result.max_drawdown >= 0
        assert result.total_trades >= 0
    
    def test_generate_signals(self, strategy, sample_backtest_data):
        """신호 생성 테스트"""
        df_1h, df_4h, df_15m = sample_backtest_data
        engine = BacktestEngine(strategy, initial_capital=10000.0)
        
        signals = engine._generate_signals(df_1h, df_4h, df_15m)
        
        assert isinstance(signals, list)
        # 신호가 있을 수도, 없을 수도 있음
        for signal in signals:
            assert hasattr(signal, 'action')
            assert hasattr(signal, 'confidence')
            assert hasattr(signal, 'indicators')
    
    def test_simulate_trades(self, strategy, sample_backtest_data):
        """거래 시뮬레이션 테스트"""
        df_1h, df_4h, df_15m = sample_backtest_data
        engine = BacktestEngine(strategy, initial_capital=10000.0)
        
        # 신호 생성
        signals = engine._generate_signals(df_1h, df_4h, df_15m)
        
        # 거래 시뮬레이션
        trades = engine._simulate_trades(signals, df_1h)
        
        assert isinstance(trades, list)
        for trade in trades:
            assert 'symbol' in trade
            assert 'side' in trade
            assert 'entry_price' in trade
            assert 'exit_price' in trade
            assert 'pnl' in trade
            assert trade['side'] in ['BUY', 'SELL']
    
    def test_find_exit(self, strategy, sample_backtest_data):
        """청산 지점 찾기 테스트"""
        df_1h, _, _ = sample_backtest_data
        engine = BacktestEngine(strategy, initial_capital=10000.0)
        
        # 롱 포지션
        position = {
            'action': 'BUY',
            'entry_price': 100.0,
            'stop_loss': 98.0,
            'take_profit_1': 104.0,
            'take_profit_2': 108.0,
        }
        
        future_prices = df_1h.iloc[10:50]
        
        exit_price, exit_time, exit_reason = engine._find_exit(position, future_prices)
        
        # 청산이 발생했는지 확인 (없을 수도 있음)
        if exit_price is not None:
            assert isinstance(exit_price, (int, float))
            assert exit_time is not None
            assert isinstance(exit_reason, str)


class TestBacktestResultConversion:
    """백테스팅 결과 변환 테스트"""
    
    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        result = BacktestResult(
            symbol="BTCUSDT",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 2, 1),
            initial_capital=10000.0,
            final_capital=11000.0,
            total_return=10.0,
            win_rate=60.0,
            profit_factor=1.5,
            max_drawdown=5.0,
            sharpe_ratio=1.2,
            total_trades=10,
            avg_profit=150.0,
            avg_loss=-50.0,
            trades=[],
        )
        
        result_dict = result.to_dict()
        
        assert isinstance(result_dict, dict)
        assert result_dict['symbol'] == "BTCUSDT"
        assert isinstance(result_dict['start_date'], str)  # datetime이 문자열로 변환되어야 함
        assert isinstance(result_dict['end_date'], str)
        assert result_dict['total_return'] == 10.0
