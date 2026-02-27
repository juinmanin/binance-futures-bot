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
