# Trading Engine Documentation

## 개요

TradingEngine은 바이낸스 선물 거래 봇의 핵심 실행 엔진입니다. 전략 시그널을 받아 실제 거래를 실행하며, 3가지 모드를 지원합니다.

## 주요 기능

### 1. 3가지 거래 모드

#### Paper Trading (페이퍼 트레이딩)
- 실제 거래 없이 시뮬레이션만 수행
- 모든 거래는 `strategy_name='paper_trading'`으로 DB에 저장
- 전략 테스트 및 백테스팅에 적합

#### Semi-Auto (세미 오토)
- 시그널을 대기열에 추가하고 사용자 확인 후 실행
- 상태가 `PENDING`인 거래로 저장
- 사용자가 `confirm_pending_signal()` 또는 `reject_pending_signal()` 호출

#### Auto (자동)
- 시그널 수신 즉시 자동으로 실거래 실행
- 완전 자동화된 트레이딩

### 2. 포지션 관리

- **진입 주문**: 시장가 주문으로 즉시 진입
- **손절 주문**: 스톱 마켓 주문 자동 배치
- **익절 주문**: 
  - TP1: 포지션의 50% (take_profit_1 가격)
  - TP2: 포지션의 50% (take_profit_2 가격)
- **부분 청산**: `close_position_with_profit()` 메서드

### 3. 리스크 관리

- RiskManager 통합으로 자동 검증
- 포지션 크기 자동 계산 (ATR 기반 또는 손절가 기반)
- 계좌 잔고 확인
- 일일 손실 한도 체크
- 최대 포지션 개수 제한

## 클래스 및 스키마

### TradingEngine

```python
class TradingEngine:
    def __init__(
        self,
        client: BinanceClient,
        db: AsyncSession,
        user_id: UUID,
        mode: TradingMode = TradingMode.PAPER,
        leverage: int = 10,
        risk_config: Optional[RiskConfig] = None
    )
```

**주요 메서드:**

- `process_signal(signal, symbol, strategy_id)` - 시그널 처리 (메인 진입점)
- `confirm_pending_signal(pending_signal_id)` - 대기 시그널 확인 및 실행
- `reject_pending_signal(pending_signal_id)` - 대기 시그널 거부
- `get_pending_signals()` - 대기 중인 시그널 목록 조회
- `close_position_with_profit(symbol, percentage, position_side)` - 부분 청산
- `set_mode(mode)` - 거래 모드 변경
- `set_leverage(leverage)` - 레버리지 변경

### StrategySignal

전략에서 생성하는 시그널 데이터:

```python
class StrategySignal(BaseModel):
    action: SignalAction  # BUY or SELL
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal
    take_profit_2: Decimal
    position_size: Optional[Decimal] = None  # None이면 자동 계산
    confidence: float = 1.0  # 0.0 ~ 1.0
    reason: Optional[str] = None
    atr: Optional[Decimal] = None  # ATR 기반 계산 시
    candle_low: Optional[Decimal] = None
    candle_high: Optional[Decimal] = None
```

### TradeResult

거래 실행 결과:

```python
class TradeResult(BaseModel):
    success: bool
    entry_order: Optional[OrderResponse] = None
    sl_order: Optional[OrderResponse] = None
    tp_orders: List[OrderResponse] = []
    reason: Optional[str] = None  # 실패 시
    paper_trade_id: Optional[UUID] = None  # 페이퍼 모드
    pending_signal_id: Optional[UUID] = None  # 세미오토 모드
```

## 사용 예제

### 1. 페이퍼 트레이딩

```python
from src.services.trading import TradingEngine, TradingMode, StrategySignal, SignalAction
from decimal import Decimal

# 엔진 초기화
engine = TradingEngine(
    client=binance_client,
    db=db_session,
    user_id=user_id,
    mode=TradingMode.PAPER,
    leverage=10
)

# 시그널 생성
signal = StrategySignal(
    action=SignalAction.BUY,
    entry_price=Decimal("50000"),
    stop_loss=Decimal("49000"),
    take_profit_1=Decimal("52000"),
    take_profit_2=Decimal("53000"),
    confidence=0.85,
    reason="RSI oversold + bullish divergence"
)

# 시그널 처리
result = await engine.process_signal(signal, "BTCUSDT")

if result.success:
    print(f"Paper trade recorded: {result.paper_trade_id}")
```

### 2. 세미 오토 모드

```python
# 엔진 초기화
engine = TradingEngine(
    client=binance_client,
    db=db_session,
    user_id=user_id,
    mode=TradingMode.SEMI_AUTO
)

# 시그널 처리 (대기열에 추가됨)
result = await engine.process_signal(signal, "BTCUSDT")

if result.success:
    print(f"Signal queued: {result.pending_signal_id}")
    
# 대기 시그널 조회
pending_signals = await engine.get_pending_signals()

# 사용자 확인 후 실행
confirmed = await engine.confirm_pending_signal(pending_signal_id)

# 또는 거부
rejected = await engine.reject_pending_signal(pending_signal_id)
```

### 3. 자동 트레이딩

```python
# 엔진 초기화
engine = TradingEngine(
    client=binance_client,
    db=db_session,
    user_id=user_id,
    mode=TradingMode.AUTO,
    leverage=15
)

# ATR 기반 포지션 크기 자동 계산
signal = StrategySignal(
    action=SignalAction.BUY,
    entry_price=Decimal("50500"),
    stop_loss=Decimal("49800"),
    take_profit_1=Decimal("51900"),
    take_profit_2=Decimal("52600"),
    atr=Decimal("350"),  # ATR 값 제공
    confidence=0.9
)

# 자동 실행
result = await engine.process_signal(signal, "BTCUSDT")

if result.success:
    print(f"Entry: {result.entry_order.order_id}")
    print(f"Stop Loss: {result.sl_order.order_id}")
    print(f"Take Profit 1: {result.tp_orders[0].order_id}")
    print(f"Take Profit 2: {result.tp_orders[1].order_id}")
```

### 4. 리스크 관리 커스터마이징

```python
from src.services.risk import RiskConfig

# 커스텀 리스크 설정
risk_config = RiskConfig(
    max_position_pct=5.0,      # 계좌의 5%까지
    max_leverage=10,            # 최대 10배
    daily_loss_limit_pct=3.0,  # 일일 손실 3% 제한
    max_positions=3,            # 동시 3개 포지션
    risk_per_trade_pct=1.0     # 거래당 1% 위험
)

engine = TradingEngine(
    client=binance_client,
    db=db_session,
    user_id=user_id,
    mode=TradingMode.AUTO,
    leverage=10,
    risk_config=risk_config
)
```

### 5. 부분 청산

```python
# TP1 도달 시 50% 청산
success = await engine.close_position_with_profit(
    symbol="BTCUSDT",
    percentage=Decimal("50"),
    position_side="LONG"
)
```

## 데이터베이스 스키마

### Trade 테이블에 저장되는 정보

- **Paper Trading**: `strategy_name = 'paper_trading'`, `status = 'FILLED'`
- **Semi-Auto Pending**: `strategy_name = 'semi_auto'`, `status = 'PENDING'`
- **Semi-Auto Confirmed**: `status = 'CONFIRMED'`, `executed_at` 업데이트
- **Semi-Auto Rejected**: `status = 'REJECTED'`
- **Auto Trading**: 실제 전략 이름, `status = 'FILLED'`

### signal_source 필드

시그널 정보는 JSONB 형태로 `signal_source` 필드에 저장:

```json
{
  "action": "BUY",
  "entry_price": "50000.00",
  "stop_loss": "49000.00",
  "take_profit_1": "52000.00",
  "take_profit_2": "53000.00",
  "confidence": 0.85,
  "reason": "RSI oversold + bullish divergence",
  "atr": "350.00",
  "strategy_id": "uuid-here"
}
```

## 실행 흐름

### Auto 모드 실행 흐름

1. **레버리지 설정** - `position_service.set_leverage()`
2. **계좌 잔고 조회** - USDT 잔고 확인
3. **현재 포지션 조회** - 리스크 검증용
4. **포지션 크기 계산** - ATR 기반 또는 손절가 기반
5. **리스크 검증** - RiskManager로 주문 유효성 확인
6. **진입 주문 실행** - 시장가 주문
7. **손절 주문 실행** - 스톱 마켓 주문
8. **익절 주문 실행** - TP1, TP2 각각 50%씩

### Paper 모드 실행 흐름

1. **포지션 크기 결정** - 고정값 또는 제공된 값
2. **주문 시뮬레이션** - OrderResponse 객체 생성
3. **DB 기록** - Trade 테이블에 저장 (strategy_name='paper_trading')

### Semi-Auto 모드 실행 흐름

1. **시그널 저장** - Trade 테이블에 PENDING 상태로 저장
2. **사용자 확인 대기** - `get_pending_signals()` 로 조회 가능
3. **확인 시** - `confirm_pending_signal()` → Auto 모드와 동일하게 실행
4. **거부 시** - `reject_pending_signal()` → 상태를 REJECTED로 변경

## 에러 처리

모든 메서드는 try-except로 예외를 처리하며, 실패 시 `TradeResult(success=False, reason="...")` 반환:

```python
result = await engine.process_signal(signal, "BTCUSDT")

if not result.success:
    print(f"Trade failed: {result.reason}")
    # 로그 확인 또는 알림 전송
```

## 로깅

모든 주요 작업은 loguru를 통해 로깅됩니다:

```
INFO: Processing signal: BTCUSDT BUY @ 50000 mode=auto confidence=0.85
INFO: Executing live trade: BTCUSDT BUY
INFO: Available balance: 10000.00 USDT
INFO: Calculated position size: 0.1
INFO: Entry order placed: 123456789
INFO: Stop loss placed: 123456790 @ 49000
INFO: TP1 placed: 123456791 @ 52000
INFO: TP2 placed: 123456792 @ 53000
INFO: Live trade executed successfully: BTCUSDT BUY
```

## 통합 예제

실제 사용 시나리오:

```python
from src.services.trading import TradingEngine, TradingMode, StrategySignal, SignalAction
from src.services.risk import RiskConfig
from decimal import Decimal

async def run_strategy():
    # 1. 엔진 초기화
    risk_config = RiskConfig(
        max_position_pct=2.0,
        max_leverage=10,
        daily_loss_limit_pct=5.0,
        max_positions=5,
        risk_per_trade_pct=1.0
    )
    
    engine = TradingEngine(
        client=binance_client,
        db=db_session,
        user_id=user_id,
        mode=TradingMode.AUTO,
        leverage=10,
        risk_config=risk_config
    )
    
    # 2. 전략에서 시그널 생성 (예: RSI + 볼린저 밴드)
    signal = StrategySignal(
        action=SignalAction.BUY,
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit_1=Decimal("52000"),
        take_profit_2=Decimal("53000"),
        atr=Decimal("350"),
        confidence=0.85,
        reason="RSI oversold + BB lower band bounce"
    )
    
    # 3. 시그널 처리
    result = await engine.process_signal(
        signal=signal,
        symbol="BTCUSDT",
        strategy_id=strategy_id
    )
    
    # 4. 결과 처리
    if result.success:
        print("✓ Trade executed successfully")
        # 거래 모니터링 시작
    else:
        print(f"✗ Trade failed: {result.reason}")
        # 알림 전송 또는 로그 기록
```

## 주의사항

1. **레버리지**: 실거래 시 레버리지는 1-125 사이여야 합니다
2. **포지션 크기**: 바이낸스의 최소/최대 주문 수량 제한을 확인하세요
3. **API 권한**: API 키에 거래 권한이 있어야 합니다
4. **테스트**: 항상 Paper 모드로 먼저 테스트하세요
5. **리스크 관리**: 적절한 RiskConfig 설정이 중요합니다

## 향후 개선 사항

- [ ] Trailing Stop Loss 지원
- [ ] 다중 TP 레벨 (3개 이상)
- [ ] 부분 진입 (Scale-in) 지원
- [ ] 동적 레버리지 조정
- [ ] 거래 성과 분석 및 리포팅
