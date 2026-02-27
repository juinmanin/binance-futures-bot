"""포트폴리오 추적 스킬 — 솔라나 지갑 잔액 및 성과 추적"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from loguru import logger

from src.services.solana.rpc_client import SolanaRPCClient
from src.services.solana.jupiter_client import JupiterClient
from .base_skill import BaseSkill, SkillResult


class PortfolioTrackerSkill(BaseSkill):
    """
    포트폴리오 추적 스킬

    솔라나 지갑의 SOL 및 SPL 토큰 잔액을 조회하고
    USD 기준 포트폴리오 가치를 계산합니다.
    """

    # 조회를 지원하는 주요 토큰 민트 주소
    TRACKED_TOKENS: Dict[str, Dict[str, Any]] = {
        "USDC": {
            "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "decimals": 6,
            "is_stablecoin": True,
        },
        "USDT": {
            "mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            "decimals": 6,
            "is_stablecoin": True,
        },
        "BONK": {
            "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "decimals": 5,
            "is_stablecoin": False,
        },
        "JUP": {
            "mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            "decimals": 6,
            "is_stablecoin": False,
        },
    }

    def __init__(
        self,
        solana_client: SolanaRPCClient,
        jupiter_client: JupiterClient,
    ):
        super().__init__(
            name="portfolio_tracker",
            description=(
                "솔라나 지갑의 SOL 및 SPL 토큰 잔액을 조회하고 "
                "USD 기준 포트폴리오 가치를 계산합니다."
            ),
        )
        self.solana = solana_client
        self.jupiter = jupiter_client

    def as_tool_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "wallet_address": {
                        "type": "string",
                        "description": "조회할 솔라나 지갑 주소",
                    },
                    "include_prices": {
                        "type": "boolean",
                        "description": "USD 가격 포함 여부 (기본 True)",
                    },
                },
                "required": ["wallet_address"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        wallet_address: str,
        include_prices: bool = True,
        **_kwargs: Any,
    ) -> SkillResult:
        """
        포트폴리오 조회

        Args:
            wallet_address: 솔라나 지갑 주소
            include_prices: USD 가격 포함 여부

        Returns:
            SkillResult with portfolio breakdown
        """
        if not wallet_address:
            return SkillResult(
                success=False,
                message="wallet_address가 필요합니다.",
                errors=["wallet_address 누락"],
            )

        try:
            # 1. SOL 잔액 조회
            sol_balance = await self.solana.get_balance(wallet_address)

            portfolio: Dict[str, Any] = {
                "wallet_address": wallet_address,
                "tokens": [],
                "total_usd": 0.0,
            }

            token_entries: List[Dict[str, Any]] = []

            # 2. SOL 가격 조회
            sol_price_usdc: Optional[Decimal] = None
            if include_prices:
                sol_price_usdc = await self.jupiter.get_token_price_usdc(
                    "SOL", amount_ui=Decimal("1"), input_decimals=9
                )

            sol_entry: Dict[str, Any] = {
                "symbol": "SOL",
                "mint": "So11111111111111111111111111111111111111112",
                "balance": sol_balance,
                "decimals": 9,
            }
            if sol_price_usdc is not None:
                sol_entry["price_usdc"] = float(sol_price_usdc)
                sol_entry["value_usdc"] = float(Decimal(str(sol_balance)) * sol_price_usdc)
                portfolio["total_usd"] += sol_entry["value_usdc"]
            token_entries.append(sol_entry)

            # 3. 주요 SPL 토큰 잔액 조회
            for symbol, info in self.TRACKED_TOKENS.items():
                try:
                    accounts = await self.solana.get_token_accounts_by_owner(
                        wallet_address, mint=info["mint"]
                    )
                    if not accounts:
                        continue

                    # 첫 번째 계정 잔액 합산
                    total_raw = 0
                    for acc in accounts:
                        acc_info = acc.get("account", {}).get("data", {})
                        parsed = acc_info.get("parsed", {}) if isinstance(acc_info, dict) else {}
                        amount_info = parsed.get("info", {}).get("tokenAmount", {})
                        raw = int(amount_info.get("amount", 0))
                        total_raw += raw

                    ui_amount = total_raw / (10 ** info["decimals"])
                    if ui_amount <= 0:
                        continue

                    token_entry: Dict[str, Any] = {
                        "symbol": symbol,
                        "mint": info["mint"],
                        "balance": ui_amount,
                        "decimals": info["decimals"],
                    }

                    if include_prices:
                        if info["is_stablecoin"]:
                            token_entry["price_usdc"] = 1.0
                            token_entry["value_usdc"] = ui_amount
                        else:
                            price = await self.jupiter.get_token_price_usdc(
                                symbol,
                                amount_ui=Decimal("1"),
                                input_decimals=info["decimals"],
                            )
                            if price is not None:
                                token_entry["price_usdc"] = float(price)
                                token_entry["value_usdc"] = float(
                                    Decimal(str(ui_amount)) * price
                                )
                        if "value_usdc" in token_entry:
                            portfolio["total_usd"] += token_entry["value_usdc"]

                    token_entries.append(token_entry)

                except Exception as token_err:
                    logger.warning(f"{symbol} 잔액 조회 실패: {token_err}")

            portfolio["tokens"] = token_entries
            logger.info(
                f"포트폴리오 조회 완료: {wallet_address[:8]}... "
                f"총 가치 ${portfolio['total_usd']:.2f}"
            )
            return SkillResult(
                success=True,
                data=portfolio,
                message=f"포트폴리오 총 가치: ${portfolio['total_usd']:.2f} USD",
            )

        except Exception as e:
            logger.error(f"포트폴리오 조회 오류: {e}")
            return SkillResult(
                success=False,
                message=f"포트폴리오 조회 실패: {str(e)}",
                errors=[str(e)],
            )
