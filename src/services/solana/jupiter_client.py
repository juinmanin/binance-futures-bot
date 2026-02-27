"""Jupiter DEX 집계기 클라이언트 (V6 API)"""
from decimal import Decimal
from typing import Any, Dict, Optional
import httpx
from loguru import logger

from src.core.exceptions import JupiterAPIException

# 잘 알려진 솔라나 토큰 민트 주소
KNOWN_TOKENS: Dict[str, str] = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}


class JupiterClient:
    """
    Jupiter DEX 집계기 V6 클라이언트

    스왑 견적 조회 및 트랜잭션 빌딩을 제공합니다.
    실제 거래 서명은 외부에서 처리합니다.
    """

    def __init__(
        self,
        api_url: str = "https://quote-api.jup.ag/v6",
        timeout: float = 30.0,
    ):
        """
        초기화

        Args:
            api_url: Jupiter API 기본 URL
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.api_url = api_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "JupiterClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        """클라이언트 종료"""
        await self._client.aclose()

    def resolve_mint(self, token: str) -> str:
        """
        토큰 심볼 또는 민트 주소 해결

        Args:
            token: 토큰 심볼 (예: "SOL", "USDC") 또는 민트 주소

        Returns:
            민트 주소
        """
        return KNOWN_TOKENS.get(token.upper(), token)

    async def get_quote(
        self,
        input_token: str,
        output_token: str,
        amount_ui: Decimal,
        input_decimals: int = 9,
        slippage_bps: int = 50,
        only_direct_routes: bool = False,
    ) -> Dict[str, Any]:
        """
        스왑 견적 조회

        Args:
            input_token: 입력 토큰 심볼 또는 민트 주소
            output_token: 출력 토큰 심볼 또는 민트 주소
            amount_ui: 입력 수량 (소수점 포함 UI 금액)
            input_decimals: 입력 토큰 소수점 자릿수
            slippage_bps: 허용 슬리피지 (베이시스 포인트, 기본 50 = 0.5%)
            only_direct_routes: 직접 경로만 사용 여부

        Returns:
            견적 데이터 딕셔너리
        """
        input_mint = self.resolve_mint(input_token)
        output_mint = self.resolve_mint(output_token)
        amount_raw = int(amount_ui * (10 ** input_decimals))

        if amount_raw <= 0:
            raise JupiterAPIException("스왑 금액은 0보다 커야 합니다.")

        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_raw),
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": str(only_direct_routes).lower(),
        }

        try:
            response = await self._client.get(
                f"{self.api_url}/quote", params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise JupiterAPIException(
                f"견적 조회 실패: HTTP {e.response.status_code}",
                details=e.response.text,
            ) from e
        except Exception as e:
            raise JupiterAPIException(f"견적 요청 오류: {str(e)}") from e

    async def get_swap_transaction(
        self,
        quote_response: Dict[str, Any],
        user_public_key: str,
        wrap_and_unwrap_sol: bool = True,
        compute_unit_price_micro_lamports: Optional[int] = None,
    ) -> str:
        """
        스왑 트랜잭션 빌드 (서명 전 상태)

        Args:
            quote_response: get_quote() 반환값
            user_public_key: 사용자 지갑 공개 키
            wrap_and_unwrap_sol: SOL 자동 래핑/언래핑 여부
            compute_unit_price_micro_lamports: 우선순위 수수료 (선택)

        Returns:
            Base64 인코딩된 미서명 트랜잭션
        """
        payload: Dict[str, Any] = {
            "quoteResponse": quote_response,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": wrap_and_unwrap_sol,
            "dynamicComputeUnitLimit": True,
        }
        if compute_unit_price_micro_lamports is not None:
            payload["prioritizationFeeLamports"] = compute_unit_price_micro_lamports

        try:
            response = await self._client.post(
                f"{self.api_url}/swap",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise JupiterAPIException(
                f"스왑 트랜잭션 빌드 실패: HTTP {e.response.status_code}",
                details=e.response.text,
            ) from e
        except Exception as e:
            raise JupiterAPIException(f"스왑 요청 오류: {str(e)}") from e

        tx = data.get("swapTransaction", "")
        if not tx:
            raise JupiterAPIException("빈 스왑 트랜잭션 수신", details=data)
        return str(tx)

    async def get_token_price_usdc(
        self,
        token: str,
        amount_ui: Decimal = Decimal("1"),
        input_decimals: int = 9,
    ) -> Optional[Decimal]:
        """
        토큰 가격 조회 (USDC 기준)

        Args:
            token: 토큰 심볼 또는 민트 주소
            amount_ui: 조회할 수량
            input_decimals: 입력 토큰 소수점 자릿수

        Returns:
            USDC 가격 (Decimal), 조회 실패 시 None
        """
        try:
            quote = await self.get_quote(
                input_token=token,
                output_token="USDC",
                amount_ui=amount_ui,
                input_decimals=input_decimals,
                slippage_bps=100,
            )
            out_amount_raw = int(quote.get("outAmount", 0))
            in_amount_raw = int(quote.get("inAmount", 1))
            if in_amount_raw == 0:
                return None
            usdc_decimals = 6
            in_ui = Decimal(in_amount_raw) / Decimal(10 ** input_decimals)
            out_ui = Decimal(out_amount_raw) / Decimal(10 ** usdc_decimals)
            price = out_ui / in_ui
            logger.debug(f"{token} 가격: ${price:.6f} USDC")
            return price
        except JupiterAPIException as e:
            logger.warning(f"{token} 가격 조회 실패: {e.message}")
            return None

    async def estimate_swap_output(
        self,
        input_token: str,
        output_token: str,
        amount_ui: Decimal,
        input_decimals: int = 9,
        output_decimals: int = 6,
        slippage_bps: int = 50,
    ) -> Dict[str, Any]:
        """
        스왑 예상 결과 계산 (실제 거래 없이 시뮬레이션)

        Args:
            input_token: 입력 토큰
            output_token: 출력 토큰
            amount_ui: 입력 수량
            input_decimals: 입력 토큰 소수점 자릿수
            output_decimals: 출력 토큰 소수점 자릿수
            slippage_bps: 허용 슬리피지

        Returns:
            예상 결과 (input_amount, output_amount, price_impact_pct 등)
        """
        quote = await self.get_quote(
            input_token=input_token,
            output_token=output_token,
            amount_ui=amount_ui,
            input_decimals=input_decimals,
            slippage_bps=slippage_bps,
        )

        out_amount_raw = int(quote.get("outAmount", 0))
        in_amount_raw = int(quote.get("inAmount", 0))
        price_impact_pct = float(quote.get("priceImpactPct", 0))

        return {
            "input_amount": Decimal(in_amount_raw) / Decimal(10 ** input_decimals),
            "output_amount": Decimal(out_amount_raw) / Decimal(10 ** output_decimals),
            "price_impact_pct": price_impact_pct,
            "slippage_bps": slippage_bps,
            "route_plan": quote.get("routePlan", []),
        }
