"""통합 전략 테스트"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.strategies.integrated_strategy import IntegratedStrategy
from src.strategies.configs.default_config import StrategyConfig
from src.strategies.types import SignalAction, MarketCondition


@pytest.fixture
def strategy_config():
    """전략 설정 픽스처"""
    return StrategyConfig(
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


@pytest.fixture
def sample_multi_timeframe_data():
    """다중 타임프레임 샘플 데이터"""
    dates_1h = pd.date_range(start='2024-01-01', periods=200, freq='1H')
    
    # 상승 추세 데이터
    base_price = 100.0
    trend = np.linspace(0, 20, 200)
    noise = np.random.randn(200) * 1.5
    
    close_prices_1h = base_price + trend + noise
    
    df_1h = pd.DataFrame({
        'open': close_prices_1h - np.random.rand(200) * 0.5,
        'high': close_prices_1h + np.random.rand(200) * 2,
        'low': close_prices_1h - np.random.rand(200) * 2,
        'close': close_prices_1h,
        'volume': np.random.rand(200) * 1000 + 500,
    }, index=dates_1h)
    
    # 4시간 데이터 (리샘플링)
    df_4h = df_1h.resample('4H').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    
    # 15분 데이터 (리샘플링)
    df_15m = df_1h.resample('15T').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    
    return df_1h, df_4h, df_15m


class TestIntegratedStrategy:
    """통합 전략 테스트"""
    
    def test_strategy_initialization(self, strategy_config):
        """전략 초기화 테스트"""
        strategy = IntegratedStrategy(strategy_config)
        
        assert strategy.config == strategy_config
        assert strategy.river is not None
        assert strategy.cloud is not None
        assert strategy.future_rsi is not None
        assert strategy.fund_flow is not None
        assert strategy.volatility_breakout is not None
        assert strategy.trend_filter is not None
        assert strategy.atr is not None
        assert strategy.vwap is not None
        assert strategy.signal_resolver is not None
    
    def test_analyze_returns_signal(self, strategy_config, sample_multi_timeframe_data):
        """분석이 신호를 반환하는지 테스트"""
        df_1h, df_4h, df_15m = sample_multi_timeframe_data
        strategy = IntegratedStrategy(strategy_config)
        
        signal = strategy.analyze(df_1h, df_4h, df_15m)
        
        assert signal is not None
        assert hasattr(signal, 'action')
        assert hasattr(signal, 'confidence')
        assert hasattr(signal, 'reason')
        assert hasattr(signal, 'indicators')
        
        # 액션은 BUY/SELL/HOLD 중 하나
        assert signal.action in [SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD]
        
        # 신뢰도는 0~1 범위
        assert 0.0 <= signal.confidence <= 1.0
    
    def test_market_condition_check(self, strategy_config, sample_multi_timeframe_data):
        """시장 환경 체크 테스트"""
        df_1h, _, _ = sample_multi_timeframe_data
        strategy = IntegratedStrategy(strategy_config)
        
        market_condition = strategy._check_market_condition(df_1h)
        
        assert market_condition in [
            MarketCondition.BULLISH, 
            MarketCondition.BEARISH, 
            MarketCondition.NEUTRAL
        ]
    
    def test_larry_williams_signal(self, strategy_config, sample_multi_timeframe_data):
        """래리 윌리엄스 신호 생성 테스트"""
        df_1h, _, _ = sample_multi_timeframe_data
        strategy = IntegratedStrategy(strategy_config)
        
        signal = strategy._check_larry_williams_signal(df_1h)
        
        assert signal is not None
        assert signal.action in [SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD]
        assert 0.0 <= signal.confidence <= 1.0
        assert isinstance(signal.reason, str)
        assert isinstance(signal.indicators, dict)
    
    def test_futurechart_confirmation(self, strategy_config, sample_multi_timeframe_data):
        """퓨처차트 확인 테스트"""
        df_1h, df_4h, df_15m = sample_multi_timeframe_data
        strategy = IntegratedStrategy(strategy_config)
        
        confirmation = strategy._check_futurechart_confirmation(df_1h, df_4h, df_15m)
        
        assert confirmation is not None
        assert hasattr(confirmation, 'is_confirmed')
        assert hasattr(confirmation, 'confidence')
        assert hasattr(confirmation, 'layer1_match')
        assert hasattr(confirmation, 'layer2_match')
        assert hasattr(confirmation, 'layer3_match')
        assert hasattr(confirmation, 'details')
        
        assert isinstance(confirmation.is_confirmed, bool)
        assert 0.0 <= confirmation.confidence <= 1.0
    
    def test_vwap_position(self, strategy_config, sample_multi_timeframe_data):
        """VWAP 위치 확인 테스트"""
        df_1h, _, _ = sample_multi_timeframe_data
        strategy = IntegratedStrategy(strategy_config)
        
        vwap_position = strategy._check_vwap_position(df_1h)
        
        assert vwap_position in ['ABOVE', 'BELOW']
    
    def test_position_size_calculation(self, strategy_config):
        """포지션 사이즈 계산 테스트"""
        strategy = IntegratedStrategy(strategy_config)
        
        account_balance = 10000.0
        atr = 2.5
        
        position_size = strategy._calculate_position_size(account_balance, atr)
        
        assert position_size > 0
        # 포지션 사이즈는 계정 잔고보다 작아야 함
        assert position_size < account_balance
    
    def test_stop_loss_calculation(self, strategy_config):
        """손절가 계산 테스트"""
        strategy = IntegratedStrategy(strategy_config)
        
        # 롱 포지션
        entry_price = 100.0
        atr = 2.0
        candle_low = 98.0
        candle_high = 102.0
        
        stop_loss_long = strategy._calculate_stop_loss(
            entry_price=entry_price,
            atr=atr,
            side='BUY',
            candle_low=candle_low,
            candle_high=candle_high
        )
        
        assert stop_loss_long < entry_price  # 롱은 진입가 아래
        
        # 숏 포지션
        stop_loss_short = strategy._calculate_stop_loss(
            entry_price=entry_price,
            atr=atr,
            side='SELL',
            candle_low=candle_low,
            candle_high=candle_high
        )
        
        assert stop_loss_short > entry_price  # 숏은 진입가 위
    
    def test_take_profit_calculation(self, strategy_config):
        """익절가 계산 테스트"""
        strategy = IntegratedStrategy(strategy_config)
        
        # 롱 포지션
        entry_price = 100.0
        stop_loss = 98.0
        
        tp1, tp2 = strategy._calculate_take_profit(
            entry_price=entry_price,
            stop_loss=stop_loss,
            side='BUY'
        )
        
        assert tp1 > entry_price  # 익절은 진입가 위
        assert tp2 > tp1  # 2차 익절은 1차 익절보다 위
        
        # 숏 포지션
        stop_loss = 102.0
        
        tp1, tp2 = strategy._calculate_take_profit(
            entry_price=entry_price,
            stop_loss=stop_loss,
            side='SELL'
        )
        
        assert tp1 < entry_price  # 익절은 진입가 아래
        assert tp2 < tp1  # 2차 익절은 1차 익절보다 아래
    
    def test_signal_with_entry_exit_prices(self, strategy_config, sample_multi_timeframe_data):
        """진입/청산 가격이 포함된 신호 테스트"""
        df_1h, df_4h, df_15m = sample_multi_timeframe_data
        strategy = IntegratedStrategy(strategy_config)
        
        signal = strategy.analyze(df_1h, df_4h, df_15m)
        
        # BUY/SELL 신호가 나온 경우에만 가격이 설정되어야 함
        if signal.action != SignalAction.HOLD:
            assert signal.entry_price is not None
            assert signal.stop_loss is not None
            assert signal.take_profit_1 is not None
            assert signal.take_profit_2 is not None
            
            # 가격 관계 검증
            if signal.action == SignalAction.BUY:
                assert signal.stop_loss < signal.entry_price
                assert signal.take_profit_1 > signal.entry_price
                assert signal.take_profit_2 > signal.take_profit_1
            elif signal.action == SignalAction.SELL:
                assert signal.stop_loss > signal.entry_price
                assert signal.take_profit_1 < signal.entry_price
                assert signal.take_profit_2 < signal.take_profit_1


class TestSignalResolver:
    """신호 해결기 테스트"""
    
    def test_resolver_with_matching_signals(self, strategy_config):
        """일치하는 신호 해결 테스트"""
        from src.strategies.types import Signal, ConfirmationResult
        from src.strategies.signal_resolver import SignalResolver
        
        resolver = SignalResolver()
        
        # 래리 윌리엄스 BUY 신호
        larry_signal = Signal(
            action=SignalAction.BUY,
            confidence=0.7,
            reason="변동성 돌파 상향",
            indicators={'test': 'value'}
        )
        
        # 퓨처차트 확인
        futurechart_confirmation = ConfirmationResult(
            is_confirmed=True,
            confidence=0.8,
            layer1_match=True,
            layer2_match=True,
            layer3_match=True,
            details={}
        )
        
        final_signal = resolver.resolve(larry_signal, futurechart_confirmation)
        
        assert final_signal.action == SignalAction.BUY
        # 일치하는 경우 신뢰도가 높아야 함 (0.7 * 0.8 = 0.56보다 높음)
        assert final_signal.confidence > 0.5
    
    def test_resolver_with_conflicting_signals(self, strategy_config):
        """충돌하는 신호 해결 테스트"""
        from src.strategies.types import Signal, ConfirmationResult
        from src.strategies.signal_resolver import SignalResolver
        
        resolver = SignalResolver()
        
        # 래리 윌리엄스 BUY 신호
        larry_signal = Signal(
            action=SignalAction.BUY,
            confidence=0.7,
            reason="변동성 돌파 상향",
            indicators={'test': 'value'}
        )
        
        # 퓨처차트 미확인
        futurechart_confirmation = ConfirmationResult(
            is_confirmed=False,
            confidence=0.3,
            layer1_match=False,
            layer2_match=False,
            layer3_match=False,
            details={}
        )
        
        final_signal = resolver.resolve(larry_signal, futurechart_confirmation)
        
        # 충돌하는 경우 신뢰도가 낮아야 함
        assert final_signal.confidence < 0.7
