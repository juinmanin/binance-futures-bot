"""
Trading Engine 사용 예제

이 파일은 TradingEngine의 기본 사용법을 보여줍니다.
실제 운영 환경에서는 적절한 설정과 에러 핸들링이 필요합니다.
"""
import asyncio
from decimal import Decimal
from uuid import uuid4

from src.services.trading import (
    TradingEngine,
    TradingMode,
    StrategySignal,
    SignalAction
)


async def example_paper_trading():
    """페이퍼 트레이딩 예제"""
    print("=== Paper Trading Example ===\n")
    
    # 1. TradingEngine 초기화 (페이퍼 모드)
    # 실제 사용 시에는 client, db, user_id를 적절히 설정해야 합니다
    # engine = TradingEngine(
    #     client=binance_client,
    #     db=db_session,
    #     user_id=user_id,
    #     mode=TradingMode.PAPER,
    #     leverage=10
    # )
    
    # 2. 전략 시그널 생성
    signal = StrategySignal(
        action=SignalAction.BUY,
        entry_price=Decimal("50000.00"),
        stop_loss=Decimal("49000.00"),
        take_profit_1=Decimal("52000.00"),
        take_profit_2=Decimal("53000.00"),
        position_size=Decimal("0.1"),  # BTC 0.1개
        confidence=0.85,
        reason="RSI oversold + bullish divergence"
    )
    
    print(f"Signal: {signal.action} @ ${signal.entry_price}")
    print(f"Stop Loss: ${signal.stop_loss}")
    print(f"Take Profit 1: ${signal.take_profit_1} (50%)")
    print(f"Take Profit 2: ${signal.take_profit_2} (50%)")
    print(f"Position Size: {signal.position_size} BTC")
    print(f"Confidence: {signal.confidence}")
    print(f"Reason: {signal.reason}\n")
    
    # 3. 시그널 처리
    # result = await engine.process_signal(
    #     signal=signal,
    #     symbol="BTCUSDT",
    #     strategy_id=strategy_id
    # )
    
    # 4. 결과 확인
    # if result.success:
    #     print(f"✓ Trade executed successfully!")
    #     print(f"  Entry Order: {result.entry_order.order_id}")
    #     print(f"  SL Order: {result.sl_order.order_id}")
    #     print(f"  TP Orders: {len(result.tp_orders)}")
    #     print(f"  Paper Trade ID: {result.paper_trade_id}")
    # else:
    #     print(f"✗ Trade failed: {result.reason}")


async def example_semi_auto_trading():
    """세미 오토 트레이딩 예제"""
    print("\n=== Semi-Auto Trading Example ===\n")
    
    # 1. TradingEngine 초기화 (세미 오토 모드)
    # engine = TradingEngine(
    #     client=binance_client,
    #     db=db_session,
    #     user_id=user_id,
    #     mode=TradingMode.SEMI_AUTO,
    #     leverage=10
    # )
    
    # 2. 시그널 생성 및 대기열 추가
    signal = StrategySignal(
        action=SignalAction.SELL,
        entry_price=Decimal("51000.00"),
        stop_loss=Decimal("52000.00"),
        take_profit_1=Decimal("49000.00"),
        take_profit_2=Decimal("48000.00"),
        confidence=0.75,
        reason="Resistance level + bearish pattern"
    )
    
    print(f"Signal: {signal.action} @ ${signal.entry_price}")
    print("Status: Queued for user confirmation\n")
    
    # 3. 시그널 처리 (대기열에 추가됨)
    # result = await engine.process_signal(signal, "BTCUSDT")
    # if result.success:
    #     print(f"✓ Signal queued: {result.pending_signal_id}")
    
    # 4. 대기 중인 시그널 조회
    # pending_signals = await engine.get_pending_signals()
    # print(f"Pending signals: {len(pending_signals)}")
    
    # 5. 사용자가 확인 후 실행
    # confirmed_result = await engine.confirm_pending_signal(
    #     pending_signal_id=result.pending_signal_id
    # )
    
    # 또는 거부
    # rejected = await engine.reject_pending_signal(
    #     pending_signal_id=result.pending_signal_id
    # )


async def example_auto_trading():
    """자동 트레이딩 예제"""
    print("\n=== Auto Trading Example ===\n")
    
    # 1. TradingEngine 초기화 (자동 모드)
    # engine = TradingEngine(
    #     client=binance_client,
    #     db=db_session,
    #     user_id=user_id,
    #     mode=TradingMode.AUTO,
    #     leverage=15
    # )
    
    # 2. ATR 기반 시그널 (포지션 크기 자동 계산)
    signal = StrategySignal(
        action=SignalAction.BUY,
        entry_price=Decimal("50500.00"),
        stop_loss=Decimal("49800.00"),
        take_profit_1=Decimal("51900.00"),
        take_profit_2=Decimal("52600.00"),
        atr=Decimal("350.00"),  # ATR 값 제공
        confidence=0.9,
        reason="Strong trend + volume confirmation"
    )
    
    print(f"Signal: {signal.action} @ ${signal.entry_price}")
    print(f"ATR: ${signal.atr}")
    print("Status: Will be executed automatically\n")
    
    # 3. 자동 실행
    # result = await engine.process_signal(signal, "BTCUSDT")
    # if result.success:
    #     print(f"✓ Trade executed automatically!")
    #     print(f"  Entry: {result.entry_order.order_id}")
    #     print(f"  Stop Loss: {result.sl_order.order_id}")
    #     print(f"  Take Profit 1: {result.tp_orders[0].order_id}")
    #     print(f"  Take Profit 2: {result.tp_orders[1].order_id}")


async def example_position_management():
    """포지션 관리 예제"""
    print("\n=== Position Management Example ===\n")
    
    # 1. 부분 청산 (TP1 도달 시 50% 청산)
    # success = await engine.close_position_with_profit(
    #     symbol="BTCUSDT",
    #     percentage=Decimal("50"),
    #     position_side="LONG"
    # )
    
    print("Closing 50% of position at TP1...")
    # if success:
    #     print("✓ Partial close successful")
    
    # 2. 나머지 포지션에 트레일링 스톱 적용 (추후 구현)
    print("Applying trailing stop to remaining position...")


async def example_risk_management():
    """리스크 관리 예제"""
    print("\n=== Risk Management Example ===\n")
    
    from src.services.risk import RiskConfig
    
    # 1. 커스텀 리스크 설정
    risk_config = RiskConfig(
        max_position_pct=5.0,      # 계좌의 5%까지만 포지션
        max_leverage=10,            # 최대 10배 레버리지
        daily_loss_limit_pct=3.0,  # 일일 손실 3% 제한
        max_positions=3,            # 동시 3개 포지션까지
        risk_per_trade_pct=1.0     # 거래당 1% 위험
    )
    
    print("Risk Configuration:")
    print(f"  Max Position: {risk_config.max_position_pct}%")
    print(f"  Max Leverage: {risk_config.max_leverage}x")
    print(f"  Daily Loss Limit: {risk_config.daily_loss_limit_pct}%")
    print(f"  Max Positions: {risk_config.max_positions}")
    print(f"  Risk per Trade: {risk_config.risk_per_trade_pct}%\n")
    
    # 2. 리스크 설정을 적용한 엔진 초기화
    # engine = TradingEngine(
    #     client=binance_client,
    #     db=db_session,
    #     user_id=user_id,
    #     mode=TradingMode.AUTO,
    #     leverage=10,
    #     risk_config=risk_config
    # )
    
    # 3. 시그널 처리 시 자동으로 리스크 검증
    # - 포지션 개수 제한 확인
    # - 포지션 크기 제한 확인
    # - 일일 손실 한도 확인
    # - 계좌 잔고 확인


async def example_mode_switching():
    """모드 전환 예제"""
    print("\n=== Mode Switching Example ===\n")
    
    # 1. 초기에는 페이퍼 모드로 시작
    # engine = TradingEngine(
    #     client=binance_client,
    #     db=db_session,
    #     user_id=user_id,
    #     mode=TradingMode.PAPER
    # )
    
    print("Initial mode: PAPER")
    
    # 2. 전략 테스트 후 세미 오토로 전환
    # engine.set_mode(TradingMode.SEMI_AUTO)
    print("Switched to: SEMI_AUTO")
    
    # 3. 안정적인 성과 확인 후 완전 자동화
    # engine.set_mode(TradingMode.AUTO)
    print("Switched to: AUTO")
    
    # 4. 레버리지 조정
    # engine.set_leverage(15)
    print("Leverage changed to: 15x")


async def main():
    """메인 함수"""
    print("Trading Engine Examples\n")
    print("=" * 50)
    
    # 각 예제 실행
    await example_paper_trading()
    await example_semi_auto_trading()
    await example_auto_trading()
    await example_position_management()
    await example_risk_management()
    await example_mode_switching()
    
    print("\n" + "=" * 50)
    print("\n참고:")
    print("- 실제 사용 시에는 BinanceClient, DB Session, User ID를 제공해야 합니다")
    print("- 모든 거래는 Trade 테이블에 기록됩니다")
    print("- 페이퍼 모드는 strategy_name='paper_trading'으로 저장됩니다")
    print("- 세미 오토 모드는 status='PENDING'으로 저장됩니다")


if __name__ == "__main__":
    asyncio.run(main())
