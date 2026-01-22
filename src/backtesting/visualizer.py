"""백테스팅 결과 시각화"""
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Dict, Any
from io import BytesIO
import base64

from .engine import BacktestResult


class BacktestVisualizer:
    """백테스팅 결과 시각화"""
    
    def __init__(self, result: BacktestResult):
        """
        Args:
            result: 백테스팅 결과
        """
        self.result = result
    
    def plot_equity_curve(self) -> bytes:
        """
        자본 곡선 차트 생성 (matplotlib 사용)
        
        Returns:
            PNG 이미지 바이트
        """
        # 자본 곡선 데이터 생성
        capital = self.result.initial_capital
        equity_data = [capital]
        dates = [self.result.start_date]
        
        for trade in self.result.trades:
            pnl = trade.get('pnl', 0)
            capital += pnl
            equity_data.append(capital)
            
            # 날짜 파싱
            exit_time = trade.get('exit_time')
            if exit_time:
                dates.append(pd.to_datetime(exit_time))
        
        # 차트 생성
        plt.figure(figsize=(12, 6))
        plt.plot(dates, equity_data, linewidth=2, color='#2E86C1')
        plt.fill_between(
            dates, 
            self.result.initial_capital, 
            equity_data, 
            alpha=0.3, 
            color='#2E86C1'
        )
        
        plt.title('자본 곡선 (Equity Curve)', fontsize=16, fontweight='bold')
        plt.xlabel('날짜', fontsize=12)
        plt.ylabel('자본 ($)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # 이미지를 바이트로 변환
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close()
        buf.seek(0)
        
        return buf.getvalue()
    
    def plot_drawdown(self) -> bytes:
        """
        낙폭 차트 생성 (matplotlib 사용)
        
        Returns:
            PNG 이미지 바이트
        """
        # 자본 곡선 데이터 생성
        capital = self.result.initial_capital
        equity_data = [capital]
        dates = [self.result.start_date]
        
        for trade in self.result.trades:
            pnl = trade.get('pnl', 0)
            capital += pnl
            equity_data.append(capital)
            
            exit_time = trade.get('exit_time')
            if exit_time:
                dates.append(pd.to_datetime(exit_time))
        
        # 낙폭 계산
        equity_series = pd.Series(equity_data, index=dates)
        cumulative_max = equity_series.cummax()
        drawdown = ((equity_series - cumulative_max) / cumulative_max) * 100
        
        # 차트 생성
        plt.figure(figsize=(12, 6))
        plt.fill_between(
            dates, 
            0, 
            drawdown, 
            alpha=0.5, 
            color='#E74C3C'
        )
        plt.plot(dates, drawdown, linewidth=2, color='#C0392B')
        
        plt.title('낙폭 (Drawdown)', fontsize=16, fontweight='bold')
        plt.xlabel('날짜', fontsize=12)
        plt.ylabel('낙폭 (%)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # 이미지를 바이트로 변환
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close()
        buf.seek(0)
        
        return buf.getvalue()
    
    def plot_trade_distribution(self) -> bytes:
        """
        거래 분포 차트 생성 (matplotlib 사용)
        
        Returns:
            PNG 이미지 바이트
        """
        # 손익 데이터 추출
        pnl_list = [t.get('pnl', 0) for t in self.result.trades if t.get('pnl') is not None]
        
        if not pnl_list:
            # 데이터가 없으면 빈 차트
            plt.figure(figsize=(12, 6))
            plt.text(0.5, 0.5, 'No trades', ha='center', va='center', fontsize=20)
            plt.axis('off')
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            plt.close()
            buf.seek(0)
            return buf.getvalue()
        
        # 차트 생성
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # 1. 히스토그램
        ax1.hist(pnl_list, bins=30, color='#3498DB', alpha=0.7, edgecolor='black')
        ax1.axvline(x=0, color='red', linestyle='--', linewidth=2)
        ax1.set_title('손익 분포', fontsize=14, fontweight='bold')
        ax1.set_xlabel('손익 ($)', fontsize=12)
        ax1.set_ylabel('빈도', fontsize=12)
        ax1.grid(True, alpha=0.3)
        
        # 2. 승/패 원형 차트
        wins = len([p for p in pnl_list if p > 0])
        losses = len([p for p in pnl_list if p < 0])
        
        if wins + losses > 0:
            ax2.pie(
                [wins, losses],
                labels=['승리', '패배'],
                colors=['#27AE60', '#E74C3C'],
                autopct='%1.1f%%',
                startangle=90
            )
            ax2.set_title('승/패 비율', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # 이미지를 바이트로 변환
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close()
        buf.seek(0)
        
        return buf.getvalue()
    
    def generate_report(self) -> str:
        """
        HTML 리포트 생성
        
        Returns:
            HTML 문자열
        """
        # 이미지를 base64로 인코딩
        equity_img = base64.b64encode(self.plot_equity_curve()).decode()
        drawdown_img = base64.b64encode(self.plot_drawdown()).decode()
        distribution_img = base64.b64encode(self.plot_trade_distribution()).decode()
        
        # HTML 생성
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>백테스팅 리포트 - {self.result.symbol}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #2C3E50;
                    border-bottom: 3px solid #3498DB;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #34495E;
                    margin-top: 30px;
                }}
                .metrics {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                .metric-card {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .metric-card h3 {{
                    margin: 0 0 10px 0;
                    font-size: 14px;
                    opacity: 0.9;
                }}
                .metric-card .value {{
                    font-size: 28px;
                    font-weight: bold;
                }}
                .chart-container {{
                    margin: 30px 0;
                    text-align: center;
                }}
                .chart-container img {{
                    max-width: 100%;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .positive {{
                    color: #27AE60;
                }}
                .negative {{
                    color: #E74C3C;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 백테스팅 리포트</h1>
                
                <h2>기본 정보</h2>
                <p><strong>심볼:</strong> {self.result.symbol}</p>
                <p><strong>기간:</strong> {self.result.start_date} ~ {self.result.end_date}</p>
                <p><strong>초기 자본:</strong> ${self.result.initial_capital:,.2f}</p>
                <p><strong>최종 자본:</strong> ${self.result.final_capital:,.2f}</p>
                
                <h2>성과 지표</h2>
                <div class="metrics">
                    <div class="metric-card">
                        <h3>총 수익률</h3>
                        <div class="value {'positive' if self.result.total_return > 0 else 'negative'}">
                            {self.result.total_return:,.2f}%
                        </div>
                    </div>
                    <div class="metric-card">
                        <h3>승률</h3>
                        <div class="value">{self.result.win_rate:,.2f}%</div>
                    </div>
                    <div class="metric-card">
                        <h3>수익 팩터</h3>
                        <div class="value">{self.result.profit_factor:,.2f}</div>
                    </div>
                    <div class="metric-card">
                        <h3>최대 낙폭</h3>
                        <div class="value negative">{self.result.max_drawdown:,.2f}%</div>
                    </div>
                    <div class="metric-card">
                        <h3>샤프 비율</h3>
                        <div class="value">{self.result.sharpe_ratio:,.2f}</div>
                    </div>
                    <div class="metric-card">
                        <h3>총 거래 수</h3>
                        <div class="value">{self.result.total_trades}</div>
                    </div>
                </div>
                
                <h2>차트</h2>
                
                <div class="chart-container">
                    <h3>자본 곡선</h3>
                    <img src="data:image/png;base64,{equity_img}" alt="Equity Curve">
                </div>
                
                <div class="chart-container">
                    <h3>낙폭</h3>
                    <img src="data:image/png;base64,{drawdown_img}" alt="Drawdown">
                </div>
                
                <div class="chart-container">
                    <h3>거래 분포</h3>
                    <img src="data:image/png;base64,{distribution_img}" alt="Trade Distribution">
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
