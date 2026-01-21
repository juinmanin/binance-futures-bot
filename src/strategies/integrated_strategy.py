"""퓨처차트 + 래리 윌리엄스 통합 전략"""
import pandas as pd
from typing import Optional, Tuple, Dict, Any

from .indicators import (
    RiverIndicator, CloudIndicator, FutureRSI, FundFlowIndicator,
    VolatilityBreakout, TrendFilter, ATRIndicator, VWAPIndicator
)
from .types import (
    StrategySignal, Signal, ConfirmationResult, 
    SignalAction, MarketCondition, TrendDirection
)
from .signal_resolver import SignalResolver
from .configs.default_config import StrategyConfig


class IntegratedStrategy:
    """퓨처차트 + 래리 윌리엄스 통합 전략"""
    
    def __init__(self, config: StrategyConfig):
        """
        Args:
            config: 전략 설정
        """
        self.config = config
        
        # 퓨처차트 지표
        self.river = RiverIndicator()
        self.cloud = CloudIndicator()
        self.future_rsi = FutureRSI(
            length=config.rsi_length,
            overbought=config.rsi_overbought,
            oversold=config.rsi_oversold
        )
        self.fund_flow = FundFlowIndicator()
        
        # 래리 윌리엄스 지표
        self.volatility_breakout = VolatilityBreakout(k_value=config.k_value)
        self.trend_filter = TrendFilter(ma_period=config.trend_ma_period)
        
        # 공통 지표
        self.atr = ATRIndicator()
        self.vwap = VWAPIndicator()
        
        # 신호 해결기
        self.signal_resolver = SignalResolver()
    
    def analyze(
        self, 
        df_1h: pd.DataFrame, 
        df_4h: pd.DataFrame, 
        df_15m: pd.DataFrame
    ) -> StrategySignal:
        """
        다중 타임프레임 분석 수행
        
        Args:
            df_1h: 1시간 OHLCV 데이터
            df_4h: 4시간 OHLCV 데이터
            df_15m: 15분 OHLCV 데이터
        
        Returns:
            StrategySignal: 최종 전략 신호
        """
        # 1. 시장 환경 체크
        market_condition = self._check_market_condition(df_1h)
        
        # 2. 래리 윌리엄스 변동성 돌파 신호
        larry_signal = self._check_larry_williams_signal(df_1h)
        
        # 3. 퓨처차트 다중 레이어 확인
        futurechart_confirmation = self._check_futurechart_confirmation(
            df_1h, df_4h, df_15m
        )
        
        # 4. 신호 충돌 해결
        final_signal = self.signal_resolver.resolve(
            larry_signal, 
            futurechart_confirmation
        )
        
        # 5. 진입가/손절가/익절가 계산 (신호가 있을 경우)
        if final_signal.action != SignalAction.HOLD:
            current_price = df_1h['close'].iloc[-1]
            atr_value = self.atr.calculate(
                df_1h['high'], 
                df_1h['low'], 
                df_1h['close']
            ).iloc[-1]
            
            # VWAP 위치 확인
            vwap_position = self._check_vwap_position(df_1h)
            
            # 진입가 설정
            final_signal.entry_price = float(current_price)
            
            # 손절가 계산
            final_signal.stop_loss = self._calculate_stop_loss(
                entry_price=current_price,
                atr=atr_value,
                side=final_signal.action.value,
                candle_low=df_1h['low'].iloc[-1],
                candle_high=df_1h['high'].iloc[-1]
            )
            
            # 익절가 계산
            tp1, tp2 = self._calculate_take_profit(
                entry_price=current_price,
                stop_loss=final_signal.stop_loss,
                side=final_signal.action.value
            )
            final_signal.take_profit_1 = tp1
            final_signal.take_profit_2 = tp2
            
            # 포지션 사이즈 계산 (계좌 잔고는 외부에서 주입)
            # 여기서는 ATR 기준 사이즈만 계산
            final_signal.position_size = None  # 나중에 계좌 정보로 계산
            
            # 추가 정보 저장
            final_signal.indicators['market_condition'] = market_condition.value
            final_signal.indicators['vwap_position'] = vwap_position
            final_signal.indicators['atr'] = float(atr_value)
        
        return final_signal
    
    def _check_market_condition(self, df: pd.DataFrame) -> MarketCondition:
        """
        시장 환경 체크 - 자금 흐름 총점
        
        Args:
            df: OHLCV 데이터프레임
            
        Returns:
            MarketCondition: 시장 환경
        """
        fund_flow_result = self.fund_flow.calculate(
            df['volume'],
            df['close'],
            df['open']
        )
        
        current_score = fund_flow_result['fund_flow_score'].iloc[-1]
        
        if current_score > self.config.fund_flow_threshold:
            return MarketCondition.BULLISH
        elif current_score < -self.config.fund_flow_threshold:
            return MarketCondition.BEARISH
        else:
            return MarketCondition.NEUTRAL
    
    def _check_larry_williams_signal(self, df: pd.DataFrame) -> Signal:
        """
        1차 신호: 래리 윌리엄스 변동성 돌파
        
        Args:
            df: OHLCV 데이터프레임
            
        Returns:
            Signal: 래리 윌리엄스 신호
        """
        # 변동성 돌파 계산
        vb_result = self.volatility_breakout.calculate(df)
        current_signal = vb_result['signal'].iloc[-1]
        
        # 추세 필터 적용
        trend = self.trend_filter.calculate(df['close']).iloc[-1]
        
        # 신호 생성
        if current_signal == 'BUY' and trend == 'UP':
            return Signal(
                action=SignalAction.BUY,
                confidence=0.7,
                reason="변동성 돌파 상향 + 상승 추세",
                indicators={
                    'target_long': float(vb_result['target_long'].iloc[-1]),
                    'range': float(vb_result['range'].iloc[-1]),
                    'trend': trend,
                }
            )
        elif current_signal == 'SELL' and trend == 'DOWN':
            return Signal(
                action=SignalAction.SELL,
                confidence=0.7,
                reason="변동성 돌파 하향 + 하락 추세",
                indicators={
                    'target_short': float(vb_result['target_short'].iloc[-1]),
                    'range': float(vb_result['range'].iloc[-1]),
                    'trend': trend,
                }
            )
        else:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="변동성 돌파 신호 없음 또는 추세 불일치",
                indicators={
                    'signal': current_signal,
                    'trend': trend,
                }
            )
    
    def _check_futurechart_confirmation(
        self,
        df_1h: pd.DataFrame,
        df_4h: pd.DataFrame,
        df_15m: pd.DataFrame
    ) -> ConfirmationResult:
        """
        2차 확인: 퓨처차트 다중 레이어
        - 레이어1(장기): 4시간 강물 방향 + 구름대 색상 일치
        - 레이어2(중기): 1시간 강물 방향 + 퓨처 RSI 상태
        - 레이어3(단기): 15분 강물 곡률 변화 확인
        
        Args:
            df_1h: 1시간 데이터
            df_4h: 4시간 데이터
            df_15m: 15분 데이터
            
        Returns:
            ConfirmationResult: 확인 결과
        """
        # 레이어1: 4시간 분석
        river_4h = self.river.calculate(df_4h['close'])
        cloud_4h = self.cloud.calculate(df_4h['high'], df_4h['low'], df_4h['close'])
        
        river_direction_4h = river_4h['river_direction'].iloc[-1]
        cloud_color_4h = cloud_4h['cloud_color'].iloc[-1]
        
        layer1_match = (
            (river_direction_4h == 'UP' and cloud_color_4h == 'GREEN') or
            (river_direction_4h == 'DOWN' and cloud_color_4h == 'RED')
        )
        
        # 레이어2: 1시간 분석
        river_1h = self.river.calculate(df_1h['close'])
        rsi_1h = self.future_rsi.calculate(df_1h['close'])
        
        river_direction_1h = river_1h['river_direction'].iloc[-1]
        rsi_signal_1h = rsi_1h['signal'].iloc[-1]
        
        layer2_match = (
            (river_direction_1h == 'UP' and rsi_signal_1h != 'OVERBOUGHT') or
            (river_direction_1h == 'DOWN' and rsi_signal_1h != 'OVERSOLD')
        )
        
        # 레이어3: 15분 분석 (강물 곡률)
        river_15m = self.river.calculate(df_15m['close'])
        river_fast_15m = river_15m['river_fast']
        
        # 곡률 변화: 최근 3개 값의 변화율
        recent_changes = river_fast_15m.iloc[-3:].diff()
        is_accelerating = (recent_changes > 0).sum() >= 2  # 가속 중
        
        layer3_match = is_accelerating
        
        # 전체 확인 결과
        is_confirmed = layer1_match and layer2_match
        confidence = 0.0
        
        if is_confirmed:
            confidence = 0.8
            if layer3_match:
                confidence = 0.9
        elif layer1_match or layer2_match:
            confidence = 0.5
        
        return ConfirmationResult(
            is_confirmed=is_confirmed,
            confidence=confidence,
            layer1_match=layer1_match,
            layer2_match=layer2_match,
            layer3_match=layer3_match,
            details={
                'layer1': {
                    'river_direction': river_direction_4h,
                    'cloud_color': cloud_color_4h,
                },
                'layer2': {
                    'river_direction': river_direction_1h,
                    'rsi_signal': rsi_signal_1h,
                    'rsi_value': float(rsi_1h['rsi'].iloc[-1]),
                },
                'layer3': {
                    'is_accelerating': is_accelerating,
                },
            }
        )
    
    def _check_vwap_position(self, df: pd.DataFrame) -> str:
        """
        VWAP 위치 확인
        
        Args:
            df: OHLCV 데이터프레임
            
        Returns:
            str: ABOVE/BELOW
        """
        vwap = self.vwap.calculate(
            df['high'], 
            df['low'], 
            df['close'], 
            df['volume']
        )
        
        current_price = df['close'].iloc[-1]
        current_vwap = vwap.iloc[-1]
        
        return 'ABOVE' if current_price > current_vwap else 'BELOW'
    
    def _calculate_position_size(
        self, 
        account_balance: float, 
        atr: float
    ) -> float:
        """
        포지션 사이즈 계산
        
        포지션 사이즈 = (계정 잔고 × max_position_pct%) / (ATR × 2)
        
        Args:
            account_balance: 계정 잔고
            atr: ATR 값
            
        Returns:
            포지션 크기
        """
        risk_amount = account_balance * (self.config.max_position_pct / 100)
        position_size = risk_amount / (atr * 2)
        
        return position_size
    
    def _calculate_stop_loss(
        self,
        entry_price: float,
        atr: float,
        side: str,
        candle_low: float,
        candle_high: float
    ) -> float:
        """
        손절가 계산
        
        손절: MAX(진입 캔들 저가/고가, -stop_loss_pct%, ATR × 1.5)
        
        Args:
            entry_price: 진입가
            atr: ATR 값
            side: BUY/SELL
            candle_low: 진입 캔들 저가
            candle_high: 진입 캔들 고가
            
        Returns:
            손절가
        """
        if side == 'BUY':
            # 롱 포지션: 손절은 진입가 아래
            stop1 = candle_low
            stop2 = entry_price * (1 - self.config.stop_loss_pct / 100)
            stop3 = entry_price - (atr * 1.5)
            
            # 가장 가까운 (높은) 손절가 선택
            stop_loss = max(stop1, stop2, stop3)
        else:
            # 숏 포지션: 손절은 진입가 위
            stop1 = candle_high
            stop2 = entry_price * (1 + self.config.stop_loss_pct / 100)
            stop3 = entry_price + (atr * 1.5)
            
            # 가장 가까운 (낮은) 손절가 선택
            stop_loss = min(stop1, stop2, stop3)
        
        return float(stop_loss)
    
    def _calculate_take_profit(
        self,
        entry_price: float,
        stop_loss: float,
        side: str
    ) -> Tuple[float, float]:
        """
        익절가 계산
        
        익절: 1차 (손절폭 × take_profit_ratio)에서 50% 청산, 
              2차 (반대 신호 또는 추세 전환)
        
        Args:
            entry_price: 진입가
            stop_loss: 손절가
            side: BUY/SELL
            
        Returns:
            (1차 익절가, 2차 익절가)
        """
        stop_loss_distance = abs(entry_price - stop_loss)
        
        if side == 'BUY':
            # 롱 포지션: 익절은 진입가 위
            take_profit_1 = entry_price + (
                stop_loss_distance * self.config.take_profit_ratio
            )
            take_profit_2 = entry_price + (
                stop_loss_distance * self.config.take_profit_ratio * 2
            )
        else:
            # 숏 포지션: 익절은 진입가 아래
            take_profit_1 = entry_price - (
                stop_loss_distance * self.config.take_profit_ratio
            )
            take_profit_2 = entry_price - (
                stop_loss_distance * self.config.take_profit_ratio * 2
            )
        
        return float(take_profit_1), float(take_profit_2)
