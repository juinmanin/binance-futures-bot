"""래리 윌리엄스 변동성 돌파 전략 지표"""
import pandas as pd
import numpy as np
from typing import Optional


class VolatilityBreakout:
    """래리 윌리엄스 변동성 돌파 전략"""
    
    def __init__(self, k_value: float = 0.5):
        """
        Args:
            k_value: 변동성 돌파 계수 (0.3 ~ 0.7)
        """
        self.k_value = k_value
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        변동성 돌파 지표 계산
        
        Args:
            df: OHLCV 데이터프레임 (open, high, low, close, volume 컬럼 필요)
        
        Returns:
            다음 컬럼이 추가된 데이터프레임:
            - range: 전일 고가 - 전일 저가
            - target_long: 금일 시가 + (range * k_value)
            - target_short: 금일 시가 - (range * k_value)
            - signal: BUY/SELL/HOLD
        """
        result = df.copy()
        
        # 전일 변동폭 계산
        result['range'] = (result['high'] - result['low']).shift(1)
        
        # 목표가 계산
        result['target_long'] = result['open'] + (result['range'] * self.k_value)
        result['target_short'] = result['open'] - (result['range'] * self.k_value)
        
        # 신호 생성
        result['signal'] = 'HOLD'
        
        # 롱 신호: 현재가가 목표가(상) 돌파
        long_condition = result['close'] > result['target_long']
        result.loc[long_condition, 'signal'] = 'BUY'
        
        # 숏 신호: 현재가가 목표가(하) 돌파
        short_condition = result['close'] < result['target_short']
        result.loc[short_condition, 'signal'] = 'SELL'
        
        return result


class TrendFilter:
    """추세 필터 - 래리 윌리엄스 전략용"""
    
    def __init__(self, ma_period: int = 20):
        """
        Args:
            ma_period: 이동평균선 기간
        """
        self.ma_period = ma_period
    
    def calculate(self, close: pd.Series) -> pd.Series:
        """
        추세 방향 계산
        
        Args:
            close: 종가 시리즈
        
        Returns:
            추세 방향 시리즈 (UP/DOWN)
        """
        # 이동평균선 계산
        ma = close.rolling(window=self.ma_period).mean()
        
        # 추세 판단
        trend = pd.Series('NEUTRAL', index=close.index)
        trend[close > ma] = 'UP'
        trend[close < ma] = 'DOWN'
        
        return trend


class VolatilityRatio:
    """변동성 비율 계산"""
    
    def __init__(self, short_period: int = 5, long_period: int = 20):
        """
        Args:
            short_period: 단기 변동성 기간
            long_period: 장기 변동성 기간
        """
        self.short_period = short_period
        self.long_period = long_period
    
    def calculate(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.DataFrame:
        """
        변동성 비율 계산
        
        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            
        Returns:
            변동성 비율 데이터프레임
        """
        # True Range 계산
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # 단기/장기 평균 변동성
        short_volatility = tr.rolling(window=self.short_period).mean()
        long_volatility = tr.rolling(window=self.long_period).mean()
        
        # 변동성 비율
        volatility_ratio = short_volatility / long_volatility
        
        result = pd.DataFrame({
            'short_volatility': short_volatility,
            'long_volatility': long_volatility,
            'volatility_ratio': volatility_ratio,
            'high_volatility': volatility_ratio > 1.2,  # 고변동성
            'low_volatility': volatility_ratio < 0.8,   # 저변동성
        })
        
        return result
