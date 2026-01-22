"""백테스팅 엔진"""
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from src.strategies.integrated_strategy import IntegratedStrategy
from src.strategies.types import StrategySignal, SignalAction, Trade
from .metrics import BacktestMetrics, calculate_metrics_from_trades


@dataclass
class BacktestResult:
    """백테스팅 결과"""
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    avg_profit: float
    avg_loss: float
    trades: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        result = asdict(self)
        # datetime을 문자열로 변환
        result['start_date'] = self.start_date.isoformat() if self.start_date else None
        result['end_date'] = self.end_date.isoformat() if self.end_date else None
        return result


class BacktestEngine:
    """벡터라이즈드 백테스팅 엔진"""
    
    def __init__(
        self, 
        strategy: IntegratedStrategy, 
        initial_capital: float = 10000
    ):
        """
        Args:
            strategy: 통합 전략
            initial_capital: 초기 자본
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
    
    async def run(
        self, 
        symbol: str,
        df_1h: pd.DataFrame,
        df_4h: pd.DataFrame,
        df_15m: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """
        백테스팅 실행
        
        Args:
            symbol: 심볼
            df_1h: 1시간 OHLCV 데이터
            df_4h: 4시간 OHLCV 데이터
            df_15m: 15분 OHLCV 데이터
            start_date: 시작 날짜 (선택)
            end_date: 종료 날짜 (선택)
        
        Returns:
            BacktestResult: 백테스팅 결과
        """
        # 날짜 필터링
        if start_date:
            df_1h = df_1h[df_1h.index >= start_date]
            df_4h = df_4h[df_4h.index >= start_date]
            df_15m = df_15m[df_15m.index >= start_date]
        
        if end_date:
            df_1h = df_1h[df_1h.index <= end_date]
            df_4h = df_4h[df_4h.index <= end_date]
            df_15m = df_15m[df_15m.index <= end_date]
        
        # 신호 생성
        signals = self._generate_signals(df_1h, df_4h, df_15m)
        
        # 거래 시뮬레이션
        trades = self._simulate_trades(signals, df_1h)
        
        # 성과 지표 계산
        metrics = calculate_metrics_from_trades(trades, self.initial_capital)
        
        # 최종 자본 계산
        final_capital = self.initial_capital + sum(
            t.get('pnl', 0) for t in trades if t.get('pnl') is not None
        )
        
        # 결과 생성
        result = BacktestResult(
            symbol=symbol,
            start_date=df_1h.index[0].to_pydatetime() if len(df_1h) > 0 else start_date,
            end_date=df_1h.index[-1].to_pydatetime() if len(df_1h) > 0 else end_date,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=metrics.total_return,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            max_drawdown=metrics.max_drawdown,
            sharpe_ratio=metrics.sharpe_ratio,
            total_trades=metrics.total_trades,
            avg_profit=metrics.avg_profit,
            avg_loss=metrics.avg_loss,
            trades=trades,
        )
        
        return result
    
    def _generate_signals(
        self,
        df_1h: pd.DataFrame,
        df_4h: pd.DataFrame,
        df_15m: pd.DataFrame,
    ) -> List[StrategySignal]:
        """
        전략 신호 생성
        
        Args:
            df_1h: 1시간 데이터
            df_4h: 4시간 데이터
            df_15m: 15분 데이터
            
        Returns:
            신호 리스트
        """
        signals = []
        
        # 각 1시간 캔들마다 신호 생성
        # 충분한 데이터가 있어야 함 (최소 100개)
        min_periods = 100
        
        if len(df_1h) < min_periods:
            return signals
        
        # 백테스팅을 위해 각 시점에서 과거 데이터만 사용
        for i in range(min_periods, len(df_1h)):
            # 현재 시점까지의 데이터
            current_1h = df_1h.iloc[:i+1].copy()
            
            # 4시간, 15분 데이터도 같은 시점까지만 사용
            current_timestamp = df_1h.index[i]
            current_4h = df_4h[df_4h.index <= current_timestamp].copy()
            current_15m = df_15m[df_15m.index <= current_timestamp].copy()
            
            # 신호 생성
            try:
                signal = self.strategy.analyze(current_1h, current_4h, current_15m)
                
                # 신호가 있으면 저장 (타임스탬프 포함)
                if signal.action != SignalAction.HOLD:
                    signal.indicators['timestamp'] = current_timestamp
                    signals.append(signal)
            except Exception as e:
                # 에러 발생 시 무시하고 계속
                continue
        
        return signals
    
    def _simulate_trades(
        self,
        signals: List[StrategySignal],
        df_1h: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """
        거래 시뮬레이션
        
        Args:
            signals: 신호 리스트
            df_1h: 1시간 가격 데이터
            
        Returns:
            거래 리스트
        """
        trades = []
        current_position = None  # 현재 포지션
        
        for signal in signals:
            # 현재 포지션이 없을 때만 신규 진입
            if current_position is None:
                # 진입
                entry_time = signal.indicators.get('timestamp')
                
                current_position = {
                    'action': signal.action.value,
                    'entry_price': signal.entry_price,
                    'entry_time': entry_time,
                    'stop_loss': signal.stop_loss,
                    'take_profit_1': signal.take_profit_1,
                    'take_profit_2': signal.take_profit_2,
                    'quantity': 1.0,  # 간단화를 위해 1단위
                    'reason': signal.reason,
                }
            
            # 현재 포지션이 있으면 청산 조건 확인
            else:
                # 진입 이후 가격 데이터 조회
                entry_time = current_position['entry_time']
                
                # 진입 이후 데이터 필터링
                future_prices = df_1h[df_1h.index > entry_time]
                
                if len(future_prices) == 0:
                    continue
                
                # 청산 가격 및 시간 찾기
                exit_price, exit_time, exit_reason = self._find_exit(
                    current_position, 
                    future_prices
                )
                
                if exit_price is not None:
                    # 손익 계산
                    if current_position['action'] == 'BUY':
                        pnl = (exit_price - current_position['entry_price']) * current_position['quantity']
                    else:  # SELL
                        pnl = (current_position['entry_price'] - exit_price) * current_position['quantity']
                    
                    # 거래 기록
                    trade = {
                        'symbol': self.strategy.config.symbols[0] if self.strategy.config.symbols else 'UNKNOWN',
                        'side': current_position['action'],
                        'entry_price': current_position['entry_price'],
                        'exit_price': exit_price,
                        'quantity': current_position['quantity'],
                        'pnl': pnl,
                        'entry_time': str(current_position['entry_time']),
                        'exit_time': str(exit_time),
                        'strategy': 'IntegratedStrategy',
                        'reason': exit_reason,
                    }
                    
                    trades.append(trade)
                    
                    # 포지션 청산
                    current_position = None
        
        # 마지막 포지션이 남아있으면 마지막 가격으로 청산
        if current_position is not None:
            last_price = df_1h['close'].iloc[-1]
            last_time = df_1h.index[-1]
            
            if current_position['action'] == 'BUY':
                pnl = (last_price - current_position['entry_price']) * current_position['quantity']
            else:
                pnl = (current_position['entry_price'] - last_price) * current_position['quantity']
            
            trade = {
                'symbol': self.strategy.config.symbols[0] if self.strategy.config.symbols else 'UNKNOWN',
                'side': current_position['action'],
                'entry_price': current_position['entry_price'],
                'exit_price': float(last_price),
                'quantity': current_position['quantity'],
                'pnl': pnl,
                'entry_time': str(current_position['entry_time']),
                'exit_time': str(last_time),
                'strategy': 'IntegratedStrategy',
                'reason': '백테스트 종료',
            }
            
            trades.append(trade)
        
        return trades
    
    def _find_exit(
        self,
        position: Dict[str, Any],
        future_prices: pd.DataFrame,
    ) -> tuple:
        """
        청산 지점 찾기
        
        Args:
            position: 포지션 정보
            future_prices: 진입 이후 가격 데이터
            
        Returns:
            (청산 가격, 청산 시간, 청산 이유)
        """
        for timestamp, row in future_prices.iterrows():
            if position['action'] == 'BUY':
                # 롱 포지션
                # 손절
                if row['low'] <= position['stop_loss']:
                    return position['stop_loss'], timestamp, '손절'
                # 익절1
                if row['high'] >= position['take_profit_1']:
                    return position['take_profit_1'], timestamp, '1차 익절'
            else:
                # 숏 포지션
                # 손절
                if row['high'] >= position['stop_loss']:
                    return position['stop_loss'], timestamp, '손절'
                # 익절1
                if row['low'] <= position['take_profit_1']:
                    return position['take_profit_1'], timestamp, '1차 익절'
        
        return None, None, None
