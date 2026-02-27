# 💓 HEARTBEAT.md — 2분 주기 감시 체크리스트

> 에이전트는 2분마다 이 체크리스트를 순서대로 실행합니다.
> `src/agents/heartbeat.py`의 `SniperHeartbeat` 클래스가 이를 구현합니다.

---

## 2분 주기 체크리스트 (The Pulse)

### 1단계: 시장 감시
- [ ] `pump_fun.scan_new_tokens(limit=20)` — Pump.fun 신규 토큰 리스트 스캔

### 2단계: 보안 필터링 (각 토큰에 대해)
- [ ] **RugCheck 점수 ≤ 100** 인가?
  - `pump_fun.security_check(mint_address=...)`
- [ ] **개발자 이전 토큰 졸업 가능성 ≥ 30%** 인가?
- [ ] **번들 지갑 점유율 < 25%** 인가?
- [ ] 모든 조건 통과 시 → `pump_fun.calculate_levels(entry_price_sol=...)`

### 3단계: 포지션 관리
- [ ] 현재 보유 토큰의 PnL 계산
  - `market_analysis.execute(token=..., trade_amount_usdc=...)` 로 현재 가격 조회
- [ ] 손절 조건 확인: 현재가 ≤ `stop_loss_sol` → 즉시 시장가 매도
- [ ] 트레일링 스톱 확인: `peak_price` 대비 -5% 하락 → 전량 청산
- [ ] 킬스위치 확인: `risk_guard.check_kill_switch(account_balance_usd=...)`

### 4단계: 자기 개선 (5회 주기)
- [ ] 최근 5개 거래 로그 분석
  - `self_optimizer.run_optimization()`
- [ ] 슬리피지/Jito 팁 설정 변경 여부 판단 및 적용

### 5단계: 보고
- [ ] 수익 현황 및 설정 변경 사항 요약 출력
  - `portfolio_tracker.execute(wallet_address=...)`
  - `risk_guard.get_limits()`

---

## 하트비트 설정

```python
# HeartbeatScheduler 초기화
scheduler = HeartbeatScheduler(
    interval_seconds=120,        # 2분
    max_consecutive_errors=5,    # 연속 5회 오류 시 루프 중단
)
```

---

## Termux 백그라운드 실행

```bash
# 화면이 꺼져도 하트비트가 계속 실행되게 하려면:
termux-wake-lock

# nohup으로 백그라운드 실행:
nohup python -m src.agents.heartbeat_runner &

# 로그 확인:
tail -f ~/.openclaw/logs/heartbeat.log
```
