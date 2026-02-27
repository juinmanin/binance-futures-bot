# 📱 TERMUX_SETUP.md — Samsung S22 Ultra Android Termux 설치 가이드

## 개요

이 가이드는 Samsung S22 Ultra (Android)의 Termux 환경에서
OpenClaw 솔라나 스나이퍼 봇을 실행하는 완전한 단계별 설명입니다.

> ⚠️ **경고**: 이 봇은 실제 자산을 사용합니다. 반드시 소액으로 테스트 후 운용하세요.
> `OPENCLAW_DRY_RUN=true`로 시뮬레이션을 먼저 충분히 진행하세요.

---

## 1단계: Termux 설치 및 기본 설정

### 1.1 Termux 설치
```bash
# F-Droid에서 Termux를 설치하세요 (Play Store 버전은 구버전입니다)
# https://f-droid.org/packages/com.termux/
```

### 1.2 배터리 최적화 해제 (핵심!)
```
설정 → 앱 → Termux → 배터리 → "제한 없음" 선택
설정 → 배터리 및 디바이스 케어 → 배터리 → 백그라운드 사용 제한 → Termux 제외
```

### 1.3 Wake Lock 설정
```bash
# Termux에서 실행:
termux-wake-lock

# 또는 자동으로 설정:
echo "termux-wake-lock" >> ~/.bashrc
```

### 1.4 Termux 기본 패키지 업데이트
```bash
pkg update -y && pkg upgrade -y
pkg install -y python git openssl libffi libjpeg-turbo
```

---

## 2단계: Python 환경 설정

```bash
# Python 및 pip 설치
pkg install -y python

# 가상환경 생성 (선택)
pip install virtualenv
virtualenv ~/openclaw-env
source ~/openclaw-env/bin/activate

# 의존성 설치
cd ~/binance-futures-bot
pip install -r requirements.txt
```

> **참고**: Termux에서 `numpy`가 느리게 설치될 수 있습니다. 약 5-10분 소요됩니다.

---

## 3단계: 저장소 클론 및 설정

```bash
# 저장소 클론
git clone https://github.com/juinmanin/binance-futures-bot.git ~/binance-futures-bot
cd ~/binance-futures-bot

# OpenClaw 설정 디렉터리 생성
mkdir -p ~/.openclaw/logs

# OpenClaw 설정 파일 복사
cp openclaw/openclaw.json ~/.openclaw/
cp openclaw/SOUL.md ~/.openclaw/
cp openclaw/AGENTS.md ~/.openclaw/
cp openclaw/HEARTBEAT.md ~/.openclaw/
```

---

## 4단계: 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env
nano .env  # 또는 vi .env
```

`.env`에 다음 값들을 설정하세요:

```env
# ── 필수 설정 ──────────────────────────────────────────

# Anthropic Claude API 키
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 마스터 암호화 키 (32자 이상, 랜덤 문자열)
# 생성: python3 -c "import secrets; print(secrets.token_hex(32))"
MASTER_ENCRYPTION_KEY=your-32-byte-random-key-here

# Solana RPC
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_TESTNET=false

# ── 보안 설정 ──────────────────────────────────────────

# 처음에는 반드시 true (시뮬레이션 모드)
OPENCLAW_DRY_RUN=true

# 단일 거래 최대 금액 (USD) — 처음에는 소액으로 설정
OPENCLAW_MAX_TRADE_USD=10.0

# 일일 손실 한도 (USD)
OPENCLAW_DAILY_LOSS_LIMIT_USD=20.0

# 킬스위치 — 총 자산 20% 손실 시 24시간 중단
PUMP_KILL_SWITCH_PCT=20.0

# ── RugCheck 설정 ──────────────────────────────────────
RUGCHECK_API_KEY=your-rugcheck-api-key

# ── 암호화된 개인키 (4단계 완료 후 설정) ───────────────
# OPENCLAW_ENCRYPTED_PRIVATE_KEY=  (아직 비워둡니다)

# ── 기타 필수 설정 ─────────────────────────────────────
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DATABASE_URL=sqlite+aiosqlite:///./data/trading.db
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

---

## 5단계: 개인키 안전하게 암호화 (핵심 보안 단계)

> ⚠️ **이 단계는 절대 중요합니다.** 개인키를 절대 .env나 텍스트 파일에 평문으로 저장하지 마세요.

### 5.1 Python으로 개인키 암호화
```bash
cd ~/binance-futures-bot
python3 - <<'EOF'
import os
os.environ["MASTER_ENCRYPTION_KEY"] = "your-32-byte-random-key-here"  # .env의 값과 동일하게

from src.core.security import APIKeyEncryption

master_key = os.environ["MASTER_ENCRYPTION_KEY"]
enc = APIKeyEncryption(master_key)

# 개인키 입력 (Phantom 지갑 등에서 export한 Base58 키)
import getpass
private_key = getpass.getpass("솔라나 개인키 (Base58, 표시 안됨): ")
encrypted = enc.encrypt(private_key)
print(f"\n암호화된 키 (이것을 .env에 저장):\nOPENCLAW_ENCRYPTED_PRIVATE_KEY={encrypted}")

# 원본 변수 삭제
private_key = ""
print("\n✅ 암호화 완료. 원본 개인키를 안전하게 삭제하세요.")
EOF
```

### 5.2 .env에 암호화된 키 추가
```bash
# 출력된 OPENCLAW_ENCRYPTED_PRIVATE_KEY 값을 .env에 추가
echo "OPENCLAW_ENCRYPTED_PRIVATE_KEY=<위에서 출력된 암호화 키>" >> .env
```

---

## 6단계: 첫 실행 (시뮬레이션 모드)

```bash
cd ~/binance-futures-bot
set -a && source .env && set +a

# 시뮬레이션 모드로 테스트
python3 - <<'EOF'
import asyncio
import os

async def test():
    from src.services.solana.rpc_client import SolanaRPCClient
    from src.services.solana.jupiter_client import JupiterClient
    from src.agents.skills.pump_fun_skill import PumpFunSkill
    from src.agents.skills.risk_guard_skill import RiskGuardSkill
    from src.agents.skills.market_analysis_skill import MarketAnalysisSkill
    from src.agents.skills.trade_executor_skill import TradeExecutorSkill
    from src.agents.skills.portfolio_tracker_skill import PortfolioTrackerSkill
    from src.agents.skills.jito_bribe_skill import JitoBribeSkill
    from src.agents.skills.cryptowallet_skill import CryptoWalletSkill
    from src.agents.skills.self_optimizer_skill import SelfOptimizerSkill
    from src.agents.openclaw_agent import OpenClawAgent

    solana = SolanaRPCClient(os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com"))
    jupiter = JupiterClient(os.getenv("JUPITER_API_URL", "https://quote-api.jup.ag/v6"))

    jito = JitoBribeSkill()
    agent = OpenClawAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        market_analysis_skill=MarketAnalysisSkill(jupiter),
        risk_guard_skill=RiskGuardSkill(
            kill_switch_pct=float(os.getenv("PUMP_KILL_SWITCH_PCT", "20")),
            stop_loss_pct=15.0,
            take_profit_1_pct=30.0,
        ),
        trade_executor_skill=TradeExecutorSkill(solana, jupiter, dry_run=True),
        portfolio_tracker_skill=PortfolioTrackerSkill(solana, jupiter),
        pump_fun_skill=PumpFunSkill(
            rugcheck_api_key=os.getenv("RUGCHECK_API_KEY", "")
        ),
        jito_bribe_skill=jito,
        self_optimizer_skill=SelfOptimizerSkill(jito),
    )

    result = await agent.run("현재 SOL 가격을 조회하고 시장 상황을 간략히 분석해줘.")
    print(f"\n✅ 에이전트 응답:\n{result.message}")
    await solana.close()
    await jupiter.close()

asyncio.run(test())
EOF
```

---

## 7단계: 하트비트 백그라운드 실행

```bash
# heartbeat_runner.py 직접 실행 (백그라운드)
nohup python3 -c "
import asyncio, os, sys
sys.path.insert(0, '.')

async def main():
    # (6단계의 agent 초기화 코드를 여기에 붙여넣기)
    from src.agents.heartbeat import SniperHeartbeat
    from src.agents.openclaw_agent import OpenClawAgent
    # ... agent 초기화 ...
    heartbeat = SniperHeartbeat(agent=agent, interval_seconds=120)
    await heartbeat.start()
    # 무한 대기
    while True:
        await asyncio.sleep(3600)

asyncio.run(main())
" >> ~/.openclaw/logs/heartbeat.log 2>&1 &

echo "하트비트 PID: $!"
echo $! > ~/.openclaw/heartbeat.pid

# 로그 실시간 확인
tail -f ~/.openclaw/logs/heartbeat.log
```

---

## 8단계: 프로세스 관리

```bash
# 하트비트 상태 확인
cat ~/.openclaw/heartbeat.pid | xargs ps -p

# 하트비트 중지
cat ~/.openclaw/heartbeat.pid | xargs kill

# Termux 재시작 후 자동 실행 (선택)
# ~/.bashrc에 추가:
echo 'termux-wake-lock && cd ~/binance-futures-bot && source ~/.openclaw-env/bin/activate' >> ~/.bashrc
```

---

## 9단계: 실거래 활성화 (충분한 테스트 후)

> ⚠️ **최소 2주 이상 시뮬레이션 후에만 활성화하세요.**

```bash
# .env 수정
sed -i 's/OPENCLAW_DRY_RUN=true/OPENCLAW_DRY_RUN=false/' .env

# 처음에는 소액으로 시작 ($10 이하)
sed -i 's/OPENCLAW_MAX_TRADE_USD=.*/OPENCLAW_MAX_TRADE_USD=10.0/' .env
```

---

## 🔒 보안 체크리스트

- [ ] `OPENCLAW_DRY_RUN=true`로 시뮬레이션 충분히 진행
- [ ] 개인키를 AES-256으로 암호화 후 `.env`의 원본 삭제
- [ ] `.env` 파일 권한 제한: `chmod 600 .env`
- [ ] `OPENCLAW_MAX_TRADE_USD` 소액 설정 확인
- [ ] `PUMP_KILL_SWITCH_PCT=20` (총 자산 20% 이상 손실 시 자동 중단) 설정
- [ ] `termux-wake-lock` 실행 확인
- [ ] 배터리 최적화 해제 확인
- [ ] 로그 모니터링 설정

---

## 🆘 문제 해결

| 문제 | 해결 방법 |
|------|-----------|
| 화면 꺼지면 봇 중단 | `termux-wake-lock` 실행, 배터리 최적화 해제 |
| `ImportError: numpy` | `pip install numpy --upgrade` |
| RPC 연결 실패 | `SOLANA_RPC_URL`을 Helius/QuickNode로 변경 |
| 슬리피지 초과 반복 | 자동 조정 대기 또는 `PUMP_DEFAULT_SLIPPAGE_BPS` 수동 증가 |
| 킬스위치 발동 | 24시간 대기 후 `reset_kill_switch` 실행 (인간 승인 필요) |
| `anthropic` 패키지 없음 | `pip install anthropic>=0.39.0` |

---

## 📞 에이전트에게 명령하는 방법

에이전트를 Python에서 직접 호출:

```python
result = await agent.run(
    "내 솔라나 개인키를 암호화해서 cryptowallet 스킬에 저장해줘"
)

result = await agent.run(
    "Pump.fun 신규 토큰 스캔 후 보안 필터 통과한 토큰 3개 추천해줘"
)

result = await agent.run(
    "오늘 수익 현황과 킬스위치 상태 보고해줘",
    context={"wallet_address": "YOUR_WALLET_ADDRESS"}
)
```
