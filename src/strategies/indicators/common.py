"""공통 기술 분석 지표"""
import pandas as pd
import numpy as np
from typing import Optional


class ATRIndicator:
    """Average True Range - 변동성 측정"""
    
    def __init__(self, period: int = 14):
        """
        Args:
            period: ATR 계산 기간
        """
        self.period = period
    
    def calculate(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        """
        ATR 계산
        
        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            
        Returns:
            ATR 값 시리즈
        """
        # True Range 계산
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # ATR = TR의 이동평균
        atr = tr.rolling(window=self.period).mean()
        
        return atr


class VWAPIndicator:
    """Volume Weighted Average Price"""
    
    def calculate(
        self, 
        high: pd.Series, 
        low: pd.Series, 
        close: pd.Series, 
        volume: pd.Series
    ) -> pd.Series:
        """
        VWAP 계산
        
        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            volume: 거래량 시리즈
            
        Returns:
            VWAP 값 시리즈
        """
        # 전형적 가격 (Typical Price)
        typical_price = (high + low + close) / 3
        
        # VWAP 계산
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        
        return vwap


class EMAIndicator:
    """Exponential Moving Average"""
    
    def __init__(self, period: int):
        """
        Args:
            period: EMA 계산 기간
        """
        self.period = period
    
    def calculate(self, prices: pd.Series) -> pd.Series:
        """
        EMA 계산
        
        Args:
            prices: 가격 시리즈
            
        Returns:
            EMA 값 시리즈
        """
        return prices.ewm(span=self.period, adjust=False).mean()


class SMAIndicator:
    """Simple Moving Average"""
    
    def __init__(self, period: int):
        """
        Args:
            period: SMA 계산 기간
        """
        self.period = period
    
    def calculate(self, prices: pd.Series) -> pd.Series:
        """
        SMA 계산
        
        Args:
            prices: 가격 시리즈
            
        Returns:
            SMA 값 시리즈
        """
        return prices.rolling(window=self.period).mean()


class RSIIndicator:
    """Relative Strength Index"""
    
    def __init__(self, period: int = 14):
        """
        Args:
            period: RSI 계산 기간
        """
        self.period = period
    
    def calculate(self, prices: pd.Series) -> pd.Series:
        """
        RSI 계산
        
        Args:
            prices: 가격 시리즈
            
        Returns:
            RSI 값 시리즈 (0-100)
        """
        # 가격 변화
        delta = prices.diff()
        
        # 상승/하락 분리
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # 평균 상승/하락
        avg_gain = gain.rolling(window=self.period).mean()
        avg_loss = loss.rolling(window=self.period).mean()
        
        # RS = 평균 상승 / 평균 하락
        rs = avg_gain / avg_loss
        
        # RSI = 100 - (100 / (1 + RS))
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
