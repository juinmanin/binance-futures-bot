"""시장 분석 스킬 — 솔라나 토큰 가격 및 기술적 지표 분석"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
from loguru import logger

from src.services.solana.jupiter_client import JupiterClient
from src.core.exceptions import SkillException
from .base_skill import BaseSkill, SkillResult


class MarketAnalysisSkill(BaseSkill):
    """
    솔라나 토큰 시장 분석 스킬

    Jupiter DEX에서 가격 데이터를 수집하고 기술적 지표를 계산합니다.
    """

    def __init__(self, jupiter_client: JupiterClient):
        super().__init__(
            name="market_analysis",
            description=(
                "솔라나 토큰의 현재 가격과 시장 상황을 분석합니다. "
                "가격 조회, 유동성 확인, 슬리피지 추정을 수행합니다."
            ),
        )
        self.jupiter = jupiter_client

    def as_tool_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "token": {
                        "type": "string",
                        "description": (
                            "분석할 토큰 심볼(예: SOL, BONK) 또는 민트 주소"
                        ),
                    },
                    "trade_amount_usdc": {
                        "type": "number",
                        "description": "시뮬레이션할 거래 금액 (USDC 기준, 기본 10)",
                    },
                },
                "required": ["token"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        token: str,
        trade_amount_usdc: float = 10.0,
        **_kwargs: Any,
    ) -> SkillResult:
        """
        토큰 시장 분석 실행

        Args:
            token: 토큰 심볼 또는 민트 주소
            trade_amount_usdc: 거래 시뮬레이션 금액 (USDC)

        Returns:
            SkillResult with price data and analysis
        """
        try:
            # 1. SOL/USDC 기준가 조회
            price = await self.jupiter.get_token_price_usdc(token)
            if price is None:
                return SkillResult(
                    success=False,
                    message=f"{token} 가격 조회에 실패했습니다.",
                )

            # 2. 소규모 스왑 슬리피지 추정
            swap_est = await self.jupiter.estimate_swap_output(
                input_token="USDC",
                output_token=token,
                amount_ui=Decimal(str(trade_amount_usdc)),
                input_decimals=6,
                output_decimals=9,
                slippage_bps=50,
            )

            price_impact_pct = swap_est.get("price_impact_pct", 0.0)
            market_quality = self._assess_market_quality(price_impact_pct)

            result_data = {
                "token": token,
                "price_usdc": float(price),
                "trade_amount_usdc": trade_amount_usdc,
                "estimated_output": float(swap_est.get("output_amount", 0)),
                "price_impact_pct": price_impact_pct,
                "market_quality": market_quality,
                "slippage_bps": swap_est.get("slippage_bps", 50),
                "route_count": len(swap_est.get("route_plan", [])),
            }

            logger.info(
                f"시장 분석 완료: {token} = ${price:.6f} USDC "
                f"(가격 충격: {price_impact_pct:.4f}%)"
            )
            return SkillResult(
                success=True,
                data=result_data,
                message=f"{token} 가격: ${price:.6f} USDC, 시장 품질: {market_quality}",
            )

        except Exception as e:
            logger.error(f"시장 분석 오류: {e}")
            return SkillResult(
                success=False,
                message=f"시장 분석 실패: {str(e)}",
                errors=[str(e)],
            )

    def _assess_market_quality(self, price_impact_pct: float) -> str:
        """
        가격 충격 기준 시장 품질 평가

        Args:
            price_impact_pct: 가격 충격 비율 (%)

        Returns:
            시장 품질 등급 (EXCELLENT/GOOD/FAIR/POOR)
        """
        if price_impact_pct < 0.1:
            return "EXCELLENT"
        elif price_impact_pct < 0.5:
            return "GOOD"
        elif price_impact_pct < 1.0:
            return "FAIR"
        else:
            return "POOR"

    @staticmethod
    def compute_simple_indicators(prices: List[float]) -> Dict[str, Any]:
        """
        단순 이동평균 및 RSI 계산 (과거 가격 데이터가 있을 때 사용)

        Args:
            prices: 종가 리스트 (오래된 것부터 최신 순)

        Returns:
            sma_20, sma_50, rsi_14 등 지표 딕셔너리
        """
        if len(prices) < 2:
            return {}
        series = pd.Series(prices)
        result: Dict[str, Any] = {}

        if len(prices) >= 20:
            result["sma_20"] = float(series.rolling(20).mean().iloc[-1])
        if len(prices) >= 50:
            result["sma_50"] = float(series.rolling(50).mean().iloc[-1])

        if len(prices) >= 15:
            delta = series.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            result["rsi_14"] = float(rsi.iloc[-1])

        return result
