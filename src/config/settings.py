"""설정 관리 모듈"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # Application
    app_name: str = "binance-futures-bot"
    app_env: str = "development"
    debug: bool = True
    secret_key: str
    
    # Database
    database_url: str
    redis_url: str
    rabbitmq_url: str
    
    # Binance API
    binance_testnet: bool = True
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_base_url: str = "https://testnet.binancefuture.com"
    binance_ws_url: str = "wss://stream.binancefuture.com"
    
    # Security
    master_encryption_key: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # Solana Network
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    solana_testnet: bool = True
    solana_testnet_rpc_url: str = "https://api.devnet.solana.com"
    solana_wallet_private_key: str = ""  # Base58-encoded 64-byte keypair (optional)

    # Jupiter DEX Aggregator
    jupiter_api_url: str = "https://quote-api.jup.ag/v6"

    # Claude AI (OpenClaw 에이전트)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5"
    claude_max_tokens: int = 4096

    # OpenClaw 에이전트 리스크 설정
    openclaw_dry_run: bool = True  # True: 실제 거래 없이 시뮬레이션
    openclaw_max_trade_usd: float = 100.0  # 단일 거래 최대 금액 (USD)
    openclaw_daily_loss_limit_usd: float = 50.0  # 일일 손실 한도 (USD)

    # 공격적 투자 전략 (Pump.fun 스나이핑)
    pump_fun_api_url: str = "https://frontend-api.pump.fun"
    pump_stop_loss_pct: float = 15.0         # 손절 -15%
    pump_take_profit_1_pct: float = 30.0     # 1차 익절 +30% (원금 50% 회수)
    pump_trailing_stop_pct: float = 5.0      # 트레일링 스톱 5%
    pump_kill_switch_pct: float = 20.0       # 일일 총 자산 20% 손실 시 24시간 중단
    pump_default_slippage_bps: int = 1500    # 기본 슬리피지 15%
    pump_max_slippage_bps: int = 2500        # 최대 슬리피지 25%

    # Jito 번들 설정
    jito_api_url: str = "https://mainnet.block-engine.jito.wtf"
    jito_default_tip_sol: float = 0.001      # 기본 팁 0.001 SOL
    jito_max_tip_sol: float = 0.05           # 최대 팁 0.05 SOL
    jito_tip_increment_sol: float = 0.005    # 실패 시 팁 증가분
    jito_tip_decrement_sol: float = 0.002    # 연속 성공 시 팁 감소분

    # RugCheck 보안 필터
    rugcheck_api_url: str = "https://api.rugcheck.xyz/v1"
    rugcheck_api_key: str = ""
    rugcheck_max_score: int = 100            # RugCheck 점수 100 이하만 허용
    rugcheck_min_grad_rate: float = 30.0     # 졸업 가능성 30% 이상
    rugcheck_max_bundle_pct: float = 25.0    # 번들 지갑 점유율 25% 미만

    # 암호화 지갑
    openclaw_encrypted_private_key: str = ""  # AES-256 암호화된 개인키
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """CORS origins를 리스트로 반환"""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# 전역 설정 인스턴스
settings = Settings()
