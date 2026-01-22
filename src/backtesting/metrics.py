"""백테스팅 성과 지표 계산"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class BacktestMetrics:
    """백테스팅 성과 지표"""
    total_return: float         # 총 수익률 (%)
    win_rate: float             # 승률 (%)
    profit_factor: float        # 수익 팩터
    max_drawdown: float         # 최대 낙폭 (%)
    sharpe_ratio: float         # 샤프 비율
    total_trades: int           # 총 거래 수
    avg_profit: float           # 평균 수익 (%)
    avg_loss: float             # 평균 손실 (%)
    avg_win: float              # 평균 승리 (%)
    avg_lose: float             # 평균 패배 (%)
    max_consecutive_wins: int   # 최대 연속 승
    max_consecutive_losses: int # 최대 연속 패


def calculate_total_return(
    initial_capital: float, 
    final_capital: float
) -> float:
    """
    총 수익률 계산
    
    Args:
        initial_capital: 초기 자본
        final_capital: 최종 자본
        
    Returns:
        총 수익률 (%)
    """
    return ((final_capital - initial_capital) / initial_capital) * 100


def calculate_win_rate(wins: int, total_trades: int) -> float:
    """
    승률 계산
    
    Args:
        wins: 승리한 거래 수
        total_trades: 총 거래 수
        
    Returns:
        승률 (%)
    """
    if total_trades == 0:
        return 0.0
    return (wins / total_trades) * 100


def calculate_profit_factor(total_profit: float, total_loss: float) -> float:
    """
    수익 팩터 계산
    
    수익 팩터 = 총 수익 / 총 손실
    
    Args:
        total_profit: 총 수익
        total_loss: 총 손실
        
    Returns:
        수익 팩터
    """
    if total_loss == 0:
        return float('inf') if total_profit > 0 else 0.0
    return total_profit / abs(total_loss)


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    최대 낙폭(MDD) 계산
    
    Args:
        equity_curve: 자본 곡선 시리즈
        
    Returns:
        최대 낙폭 (%)
    """
    # 누적 최대값
    cumulative_max = equity_curve.cummax()
    
    # 낙폭 계산
    drawdown = (equity_curve - cumulative_max) / cumulative_max * 100
    
    # 최대 낙폭
    max_dd = drawdown.min()
    
    return abs(max_dd)


def calculate_sharpe_ratio(
    returns: pd.Series, 
    risk_free_rate: float = 0.0
) -> float:
    """
    샤프 비율 계산
    
    샤프 비율 = (평균 수익률 - 무위험 수익률) / 수익률 표준편차
    
    Args:
        returns: 수익률 시리즈
        risk_free_rate: 무위험 수익률 (연율)
        
    Returns:
        샤프 비율
    """
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    
    # 연간화된 샤프 비율
    excess_returns = returns - (risk_free_rate / 252)  # 일별 무위험 수익률
    sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
    
    return sharpe


def calculate_consecutive_trades(trades_pnl: List[float]) -> tuple:
    """
    최대 연속 승/패 계산
    
    Args:
        trades_pnl: 거래 손익 리스트
        
    Returns:
        (최대 연속 승, 최대 연속 패)
    """
    if not trades_pnl:
        return 0, 0
    
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0
    
    for pnl in trades_pnl:
        if pnl > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif pnl < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
    
    return max_wins, max_losses


def calculate_metrics_from_trades(
    trades: List[Dict[str, Any]], 
    initial_capital: float
) -> BacktestMetrics:
    """
    거래 내역으로부터 성과 지표 계산
    
    Args:
        trades: 거래 내역 리스트
        initial_capital: 초기 자본
        
    Returns:
        BacktestMetrics: 성과 지표
    """
    if not trades:
        return BacktestMetrics(
            total_return=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            total_trades=0,
            avg_profit=0.0,
            avg_loss=0.0,
            avg_win=0.0,
            avg_lose=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
        )
    
    # 거래 정보 추출
    pnl_list = [t.get('pnl', 0) for t in trades if t.get('pnl') is not None]
    
    if not pnl_list:
        return BacktestMetrics(
            total_return=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            total_trades=len(trades),
            avg_profit=0.0,
            avg_loss=0.0,
            avg_win=0.0,
            avg_lose=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
        )
    
    # 승/패 분리
    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]
    
    # 자본 곡선 생성
    capital = initial_capital
    equity_curve_data = [capital]
    
    for pnl in pnl_list:
        capital += pnl
        equity_curve_data.append(capital)
    
    equity_curve = pd.Series(equity_curve_data)
    
    # 수익률 계산
    returns = equity_curve.pct_change().dropna()
    
    # 성과 지표 계산
    total_return = calculate_total_return(initial_capital, capital)
    win_rate = calculate_win_rate(len(wins), len(pnl_list))
    profit_factor = calculate_profit_factor(sum(wins), sum(losses))
    max_dd = calculate_max_drawdown(equity_curve)
    sharpe = calculate_sharpe_ratio(returns)
    
    avg_profit = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    avg_win = (avg_profit / initial_capital * 100) if wins else 0.0
    avg_lose = (avg_loss / initial_capital * 100) if losses else 0.0
    
    max_cons_wins, max_cons_losses = calculate_consecutive_trades(pnl_list)
    
    return BacktestMetrics(
        total_return=total_return,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        total_trades=len(pnl_list),
        avg_profit=avg_profit,
        avg_loss=avg_loss,
        avg_win=avg_win,
        avg_lose=avg_lose,
        max_consecutive_wins=max_cons_wins,
        max_consecutive_losses=max_cons_losses,
    )
