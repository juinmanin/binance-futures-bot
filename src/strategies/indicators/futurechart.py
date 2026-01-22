"""퓨처차트 지표 - JMA 기반 추세 및 자금 흐름 분석"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple


class RiverIndicator:
    """강물(River) 지표 - JMA(Jurik Moving Average) 기반 추세 판단"""
    
    def __init__(self, length: int = 14, phase: int = 0):
        """
        Args:
            length: JMA 길이
            phase: 위상 조정 (-100 ~ +100)
        """
        self.length = length
        self.phase = phase
    
    def _jma(self, prices: pd.Series, length: int, phase: int) -> pd.Series:
        """
        Jurik Moving Average 근사 계산
        (실제 JMA는 proprietary이므로, EMA 기반 근사값 사용)
        
        Args:
            prices: 가격 시리즈
            length: JMA 길이
            phase: 위상
            
        Returns:
            JMA 값 시리즈
        """
        # EMA 기반 근사
        # phase를 사용하여 반응 속도 조정
        adjusted_length = length * (1 + phase / 100)
        adjusted_length = max(2, int(adjusted_length))
        
        jma = prices.ewm(span=adjusted_length, adjust=False).mean()
        return jma
    
    def calculate(self, prices: pd.Series) -> pd.DataFrame:
        """
        River 지표 계산
        
        Args:
            prices: 가격 시리즈
        
        Returns:
            데이터프레임:
            - river_fast: 빠른 JMA
            - river_slow: 느린 JMA
            - river_direction: UP/DOWN/NEUTRAL
        """
        # 빠른/느린 JMA 계산
        river_fast = self._jma(prices, self.length, self.phase)
        river_slow = self._jma(prices, self.length * 2, self.phase)
        
        # 방향 판단
        direction = pd.Series('NEUTRAL', index=prices.index)
        direction[river_fast > river_slow] = 'UP'
        direction[river_fast < river_slow] = 'DOWN'
        
        result = pd.DataFrame({
            'river_fast': river_fast,
            'river_slow': river_slow,
            'river_direction': direction,
        })
        
        return result


class CloudIndicator:
    """구름대(Cloud) 지표 - 지지/저항 영역"""
    
    def __init__(self, length: int = 20):
        """
        Args:
            length: 구름대 계산 기간
        """
        self.length = length
    
    def calculate(
        self, 
        high: pd.Series, 
        low: pd.Series, 
        close: pd.Series
    ) -> pd.DataFrame:
        """
        Cloud 지표 계산
        
        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
        
        Returns:
            데이터프레임:
            - cloud_upper: 구름대 상단
            - cloud_lower: 구름대 하단
            - cloud_color: GREEN/RED (지지/저항)
        """
        # 전환선 (Conversion Line): (9일 고가 + 9일 저가) / 2
        conversion_period = max(9, self.length // 2)
        conversion_high = high.rolling(window=conversion_period).max()
        conversion_low = low.rolling(window=conversion_period).min()
        conversion_line = (conversion_high + conversion_low) / 2
        
        # 기준선 (Base Line): (26일 고가 + 26일 저가) / 2
        base_period = self.length
        base_high = high.rolling(window=base_period).max()
        base_low = low.rolling(window=base_period).min()
        base_line = (base_high + base_low) / 2
        
        # 구름대 (Cloud)
        cloud_upper = pd.concat([conversion_line, base_line], axis=1).max(axis=1)
        cloud_lower = pd.concat([conversion_line, base_line], axis=1).min(axis=1)
        
        # 구름대 색상 (가격이 구름대 위: GREEN, 아래: RED)
        cloud_color = pd.Series('RED', index=close.index)
        cloud_color[close > cloud_upper] = 'GREEN'
        
        result = pd.DataFrame({
            'cloud_upper': cloud_upper,
            'cloud_lower': cloud_lower,
            'cloud_color': cloud_color,
        })
        
        return result


class FutureRSI:
    """퓨처 RSI - 과매수/과매도 및 다이버전스 감지"""
    
    def __init__(self, length: int = 14, overbought: int = 80, oversold: int = 20):
        """
        Args:
            length: RSI 계산 기간
            overbought: 과매수 기준
            oversold: 과매도 기준
        """
        self.length = length
        self.overbought = overbought
        self.oversold = oversold
    
    def _calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """RSI 계산"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=self.length).mean()
        avg_loss = loss.rolling(window=self.length).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _detect_divergence(
        self, 
        prices: pd.Series, 
        rsi: pd.Series, 
        window: int = 14
    ) -> pd.Series:
        """
        다이버전스 감지
        
        Args:
            prices: 가격 시리즈
            rsi: RSI 시리즈
            window: 감지 윈도우
            
        Returns:
            다이버전스 시리즈 (BULLISH/BEARISH/NONE)
        """
        divergence = pd.Series('NONE', index=prices.index)
        
        for i in range(window, len(prices)):
            # 최근 윈도우 구간
            price_window = prices.iloc[i-window:i+1]
            rsi_window = rsi.iloc[i-window:i+1]
            
            # 가격 고점/저점
            price_high_idx = price_window.idxmax()
            price_low_idx = price_window.idxmin()
            
            # RSI 고점/저점
            rsi_high_idx = rsi_window.idxmax()
            rsi_low_idx = rsi_window.idxmin()
            
            # Bullish Divergence: 가격은 저점 낮아지는데 RSI는 저점 높아짐
            if (price_window.iloc[-1] < price_window.loc[price_low_idx] and 
                rsi_window.iloc[-1] > rsi_window.loc[rsi_low_idx]):
                divergence.iloc[i] = 'BULLISH'
            
            # Bearish Divergence: 가격은 고점 높아지는데 RSI는 고점 낮아짐
            elif (price_window.iloc[-1] > price_window.loc[price_high_idx] and 
                  rsi_window.iloc[-1] < rsi_window.loc[rsi_high_idx]):
                divergence.iloc[i] = 'BEARISH'
        
        return divergence
    
    def calculate(self, prices: pd.Series) -> pd.DataFrame:
        """
        Future RSI 계산
        
        Args:
            prices: 가격 시리즈
        
        Returns:
            데이터프레임:
            - rsi: RSI 값
            - signal: OVERBOUGHT/OVERSOLD/NEUTRAL
            - divergence: BULLISH/BEARISH/NONE
        """
        rsi = self._calculate_rsi(prices)
        
        # 신호 생성
        signal = pd.Series('NEUTRAL', index=prices.index)
        signal[rsi >= self.overbought] = 'OVERBOUGHT'
        signal[rsi <= self.oversold] = 'OVERSOLD'
        
        # 다이버전스 감지
        divergence = self._detect_divergence(prices, rsi)
        
        result = pd.DataFrame({
            'rsi': rsi,
            'signal': signal,
            'divergence': divergence,
        })
        
        return result


class FundFlowIndicator:
    """7대 자금 흐름 점수 계산"""
    
    def calculate(
        self, 
        volume: pd.Series, 
        close: pd.Series, 
        open_price: pd.Series
    ) -> pd.DataFrame:
        """
        자금 흐름 점수 계산
        
        Args:
            volume: 거래량 시리즈
            close: 종가 시리즈
            open_price: 시가 시리즈
        
        Returns:
            데이터프레임:
            - fund_flow_score: -100 ~ +100
            - fund_flow_direction: INFLOW/OUTFLOW/NEUTRAL
        """
        # 가격 변화
        price_change = close - open_price
        price_change_pct = (price_change / open_price) * 100
        
        # 거래량 변화
        volume_change = volume.diff()
        volume_change_pct = (volume_change / volume.shift()) * 100
        
        # 기본 자금 흐름
        mfi = pd.Series(0.0, index=close.index)
        
        # 상승 + 거래량 증가 = 강한 매수
        strong_buy = (price_change > 0) & (volume_change > 0)
        mfi[strong_buy] = price_change_pct[strong_buy] * (1 + volume_change_pct[strong_buy] / 100)
        
        # 하락 + 거래량 증가 = 강한 매도
        strong_sell = (price_change < 0) & (volume_change > 0)
        mfi[strong_sell] = price_change_pct[strong_sell] * (1 + volume_change_pct[strong_sell] / 100)
        
        # 상승 + 거래량 감소 = 약한 매수
        weak_buy = (price_change > 0) & (volume_change <= 0)
        mfi[weak_buy] = price_change_pct[weak_buy] * 0.5
        
        # 하락 + 거래량 감소 = 약한 매도
        weak_sell = (price_change < 0) & (volume_change <= 0)
        mfi[weak_sell] = price_change_pct[weak_sell] * 0.5
        
        # 정규화 (-100 ~ +100)
        fund_flow_score = mfi.rolling(window=7).sum()
        fund_flow_score = fund_flow_score.clip(-100, 100)
        
        # 방향 판단
        direction = pd.Series('NEUTRAL', index=close.index)
        direction[fund_flow_score > 10] = 'INFLOW'
        direction[fund_flow_score < -10] = 'OUTFLOW'
        
        result = pd.DataFrame({
            'fund_flow_score': fund_flow_score,
            'fund_flow_direction': direction,
        })
        
        return result
