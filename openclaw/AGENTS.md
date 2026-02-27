# 🤖 AGENTS.md — 에이전트 역할 정의

## 에이전트 설정: Solana Sniper Optimizer

| 필드 | 값 |
|------|----|
| **ID** | `sol-sniper-bot` |
| **모델** | `claude-sonnet-4-5` |
| **역할** | 솔라나 신규 토큰 감지, 보안 검사, 자동 매매 및 성과 분석 기반 설정 최적화 |
| **사용 도구** | `pump_fun`, `jito_bribe`, `cryptowallet`, `self_optimizer`, `market_analysis`, `risk_guard`, `trade_executor`, `portfolio_tracker` |
| **심장박동 주기** | 2분 (`HEARTBEAT.md` 참조) |

---

## 스킬 매핑

### 🔍 pump_fun (Pump.fun 스나이퍼)
- `scan_new_tokens`: 신규 토큰 목록 스캔
- `security_check`: RugCheck API 보안 검사
- `calculate_levels`: 진입/손절/익절 가격 계산

### ⚡ jito_bribe (Jito 팁 관리자)
- `get_tip`: 현재 권장 팁 조회
- `report_success` / `report_failure`: 결과 보고 → 팁 자동 조정
- `send_bundle`: Jito 번들 전송

### 🔐 cryptowallet (암호화 지갑)
- `encrypt_key`: 개인키 AES-256 암호화
- `verify_key`: 암호화 키 유효성 확인
- `get_public_key`: 공개키(지갑 주소) 파생

### 🧠 self_optimizer (자기 개선)
- `record_trade`: 거래 결과 기록
- `run_optimization`: 설정 자동 최적화
- `get_trade_summary`: 성과 요약 보고

### 📊 market_analysis (시장 분석)
- 가격 조회, 유동성 분석, 슬리피지 추정

### 🛡 risk_guard (리스크 관리 + 킬스위치)
- `validate_trade`: 거래 유효성 검증
- `check_kill_switch`: 킬스위치 상태 확인
- `calculate_position_size`: 포지션 크기 계산

### 💱 trade_executor (거래 실행)
- `estimate`: 스왑 예상치 계산
- `execute`: 실제 스왑 실행 (`dry_run=False` 시에만)

### 💼 portfolio_tracker (포트폴리오 추적)
- 지갑 잔액, USD 가치 산정

---

## 자율 최적화 지침 (Self-Optimization Rules)

```
매 5회 매수 시도 → run_optimization 실행:
  if slippage_exceeded_rate > 20%:
    current_slippage += 2%  (최대 25%)
  
  if tx_fail_rate > 20%:
    jito_tip += 0.005 SOL   (최대 0.05 SOL)
  
  if consecutive_success >= 3:
    jito_tip -= 0.002 SOL   (최소 0.0001 SOL)
```

---

## 보안 설정

- **게이트웨이**: `127.0.0.1:18789` (로컬만, 외부 노출 금지)
- **샌드박스**: `non-main` 모드 활성화
- **개인키**: `OPENCLAW_ENCRYPTED_PRIVATE_KEY` 환경 변수에서만 로드
