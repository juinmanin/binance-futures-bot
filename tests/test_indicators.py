"""지표 테스트"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.strategies.indicators.common import (
    ATRIndicator, VWAPIndicator, EMAIndicator, SMAIndicator, RSIIndicator
)
from src.strategies.indicators.larry_williams import (
    VolatilityBreakout, TrendFilter, VolatilityRatio
)
from src.strategies.indicators.futurechart import (
    RiverIndicator, CloudIndicator, FutureRSI, FundFlowIndicator
)


@pytest.fixture
def sample_ohlcv_data():
    """샘플 OHLCV 데이터 생성"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
    
    # 간단한 추세 데이터 생성
    base_price = 100.0
    trend = np.linspace(0, 10, 100)
    noise = np.random.randn(100) * 2
    
    close_prices = base_price + trend + noise
    
    df = pd.DataFrame({
        'open': close_prices - np.random.rand(100) * 0.5,
        'high': close_prices + np.random.rand(100) * 2,
        'low': close_prices - np.random.rand(100) * 2,
        'close': close_prices,
        'volume': np.random.rand(100) * 1000 + 500,
    }, index=dates)
    
    return df


class TestCommonIndicators:
    """공통 지표 테스트"""
    
    def test_atr_indicator(self, sample_ohlcv_data):
        """ATR 지표 테스트"""
        df = sample_ohlcv_data
        atr = ATRIndicator(period=14)
        
        result = atr.calculate(df['high'], df['low'], df['close'])
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        # ATR은 항상 양수
        assert (result.dropna() >= 0).all()
    
    def test_vwap_indicator(self, sample_ohlcv_data):
        """VWAP 지표 테스트"""
        df = sample_ohlcv_data
        vwap = VWAPIndicator()
        
        result = vwap.calculate(df['high'], df['low'], df['close'], df['volume'])
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        # VWAP은 가격 범위 내에 있어야 함
        assert (result >= df['low']).all()
        assert (result <= df['high']).all()
    
    def test_ema_indicator(self, sample_ohlcv_data):
        """EMA 지표 테스트"""
        df = sample_ohlcv_data
        ema = EMAIndicator(period=20)
        
        result = ema.calculate(df['close'])
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        # EMA는 가격과 비슷한 범위에 있어야 함
        assert result.dropna().min() >= df['close'].min() * 0.8
        assert result.dropna().max() <= df['close'].max() * 1.2
    
    def test_sma_indicator(self, sample_ohlcv_data):
        """SMA 지표 테스트"""
        df = sample_ohlcv_data
        sma = SMAIndicator(period=20)
        
        result = sma.calculate(df['close'])
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        # 처음 19개는 NaN이어야 함
        assert pd.isna(result.iloc[:19]).all()
        # 나머지는 값이 있어야 함
        assert pd.notna(result.iloc[19:]).all()
    
    def test_rsi_indicator(self, sample_ohlcv_data):
        """RSI 지표 테스트"""
        df = sample_ohlcv_data
        rsi = RSIIndicator(period=14)
        
        result = rsi.calculate(df['close'])
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        # RSI는 0~100 범위
        assert (result.dropna() >= 0).all()
        assert (result.dropna() <= 100).all()


class TestLarryWilliamsIndicators:
    """래리 윌리엄스 지표 테스트"""
    
    def test_volatility_breakout(self, sample_ohlcv_data):
        """변동성 돌파 지표 테스트"""
        df = sample_ohlcv_data
        vb = VolatilityBreakout(k_value=0.5)
        
        result = vb.calculate(df)
        
        assert 'range' in result.columns
        assert 'target_long' in result.columns
        assert 'target_short' in result.columns
        assert 'signal' in result.columns
        
        # 신호는 BUY/SELL/HOLD 중 하나
        assert result['signal'].isin(['BUY', 'SELL', 'HOLD']).all()
    
    def test_trend_filter(self, sample_ohlcv_data):
        """추세 필터 테스트"""
        df = sample_ohlcv_data
        tf = TrendFilter(ma_period=20)
        
        result = tf.calculate(df['close'])
        
        assert isinstance(result, pd.Series)
        # 추세는 UP/DOWN/NEUTRAL 중 하나
        assert result.isin(['UP', 'DOWN', 'NEUTRAL']).all()
    
    def test_volatility_ratio(self, sample_ohlcv_data):
        """변동성 비율 테스트"""
        df = sample_ohlcv_data
        vr = VolatilityRatio(short_period=5, long_period=20)
        
        result = vr.calculate(df['high'], df['low'], df['close'])
        
        assert isinstance(result, pd.DataFrame)
        assert 'short_volatility' in result.columns
        assert 'long_volatility' in result.columns
        assert 'volatility_ratio' in result.columns
        assert 'high_volatility' in result.columns
        assert 'low_volatility' in result.columns


class TestFutureChartIndicators:
    """퓨처차트 지표 테스트"""
    
    def test_river_indicator(self, sample_ohlcv_data):
        """강물 지표 테스트"""
        df = sample_ohlcv_data
        river = RiverIndicator(length=14, phase=0)
        
        result = river.calculate(df['close'])
        
        assert isinstance(result, pd.DataFrame)
        assert 'river_fast' in result.columns
        assert 'river_slow' in result.columns
        assert 'river_direction' in result.columns
        
        # 방향은 UP/DOWN/NEUTRAL 중 하나
        assert result['river_direction'].isin(['UP', 'DOWN', 'NEUTRAL']).all()
    
    def test_cloud_indicator(self, sample_ohlcv_data):
        """구름대 지표 테스트"""
        df = sample_ohlcv_data
        cloud = CloudIndicator(length=20)
        
        result = cloud.calculate(df['high'], df['low'], df['close'])
        
        assert isinstance(result, pd.DataFrame)
        assert 'cloud_upper' in result.columns
        assert 'cloud_lower' in result.columns
        assert 'cloud_color' in result.columns
        
        # 색상은 GREEN/RED 중 하나
        assert result['cloud_color'].isin(['GREEN', 'RED']).all()
        # 상단이 하단보다 크거나 같아야 함
        assert (result['cloud_upper'] >= result['cloud_lower']).all()
    
    def test_future_rsi(self, sample_ohlcv_data):
        """퓨처 RSI 테스트"""
        df = sample_ohlcv_data
        future_rsi = FutureRSI(length=14, overbought=80, oversold=20)
        
        result = future_rsi.calculate(df['close'])
        
        assert isinstance(result, pd.DataFrame)
        assert 'rsi' in result.columns
        assert 'signal' in result.columns
        assert 'divergence' in result.columns
        
        # RSI는 0~100 범위
        assert (result['rsi'].dropna() >= 0).all()
        assert (result['rsi'].dropna() <= 100).all()
        
        # 신호는 OVERBOUGHT/OVERSOLD/NEUTRAL 중 하나
        assert result['signal'].isin(['OVERBOUGHT', 'OVERSOLD', 'NEUTRAL']).all()
        
        # 다이버전스는 BULLISH/BEARISH/NONE 중 하나
        assert result['divergence'].isin(['BULLISH', 'BEARISH', 'NONE']).all()
    
    def test_fund_flow_indicator(self, sample_ohlcv_data):
        """자금 흐름 지표 테스트"""
        df = sample_ohlcv_data
        fund_flow = FundFlowIndicator()
        
        result = fund_flow.calculate(df['volume'], df['close'], df['open'])
        
        assert isinstance(result, pd.DataFrame)
        assert 'fund_flow_score' in result.columns
        assert 'fund_flow_direction' in result.columns
        
        # 점수는 -100 ~ +100 범위
        assert (result['fund_flow_score'].dropna() >= -100).all()
        assert (result['fund_flow_score'].dropna() <= 100).all()
        
        # 방향은 INFLOW/OUTFLOW/NEUTRAL 중 하나
        assert result['fund_flow_direction'].isin(['INFLOW', 'OUTFLOW', 'NEUTRAL']).all()


class TestEdgeCases:
    """엣지 케이스 테스트"""
    
    def test_empty_data(self):
        """빈 데이터 처리"""
        empty_series = pd.Series([], dtype=float)
        
        atr = ATRIndicator()
        result = atr.calculate(empty_series, empty_series, empty_series)
        
        assert len(result) == 0
    
    def test_single_value(self):
        """단일 값 처리"""
        single_series = pd.Series([100.0])
        
        sma = SMAIndicator(period=5)
        result = sma.calculate(single_series)
        
        assert len(result) == 1
        assert pd.isna(result.iloc[0])
    
    def test_nan_values(self):
        """NaN 값 처리"""
        data_with_nan = pd.Series([100.0, 101.0, np.nan, 103.0, 104.0])
        
        ema = EMAIndicator(period=3)
        result = ema.calculate(data_with_nan)
        
        assert len(result) == len(data_with_nan)
        # EMA는 NaN을 적절히 처리해야 함
        assert pd.notna(result.iloc[-1])
