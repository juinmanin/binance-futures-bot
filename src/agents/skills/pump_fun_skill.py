"""Pump.fun 신규 토큰 스나이핑 스킬 + RugCheck 보안 필터"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger

from src.core.exceptions import PumpFunException, RugCheckException, SkillException
from .base_skill import BaseSkill, SkillResult


# ──────────────────────────────────────────────────────────────────────────────
# RugCheck 보안 필터 기본값
# ──────────────────────────────────────────────────────────────────────────────
_DEFAULT_RUGCHECK_MAX_SCORE = 100       # 점수 100 이하 (낮을수록 안전)
_DEFAULT_MIN_GRAD_RATE = 30.0           # 개발자 졸업 가능성 30% 이상
_DEFAULT_MAX_BUNDLE_PCT = 25.0          # 번들 지갑 점유율 25% 미만

# Pump.fun 졸업 기준 시가총액 (SOL) — 약 69 SOL 도달 시 Raydium으로 자동 이주
_PUMP_FUN_GRADUATION_THRESHOLD_SOL = 69.0

# 최소 개인키 길이 (Base58 인코딩 기준)
_MIN_PRIVATE_KEY_LENGTH = 32


class PumpFunSkill(BaseSkill):
    """
    Pump.fun 신규 토큰 스나이핑 스킬

    기능:
    - Pump.fun 신규 토큰 목록 스캔
    - RugCheck API를 통한 러그풀·번들 지갑 보안 검사
    - 졸업 가능성 기반 진입 필터
    - 손절(-15%) / 1차 익절(+30%) / 트레일링 스톱(5%) 계산
    """

    def __init__(
        self,
        pump_fun_api_url: str = "https://frontend-api.pump.fun",
        rugcheck_api_url: str = "https://api.rugcheck.xyz/v1",
        rugcheck_api_key: str = "",
        rugcheck_max_score: int = _DEFAULT_RUGCHECK_MAX_SCORE,
        min_grad_rate: float = _DEFAULT_MIN_GRAD_RATE,
        max_bundle_pct: float = _DEFAULT_MAX_BUNDLE_PCT,
        stop_loss_pct: float = 15.0,
        take_profit_1_pct: float = 30.0,
        trailing_stop_pct: float = 5.0,
        timeout: float = 20.0,
    ):
        """
        초기화

        Args:
            pump_fun_api_url: Pump.fun 프런트엔드 API URL
            rugcheck_api_url: RugCheck API URL
            rugcheck_api_key: RugCheck API 키
            rugcheck_max_score: 허용 최대 RugCheck 점수 (낮을수록 안전)
            min_grad_rate: 최소 졸업 가능성 (%)
            max_bundle_pct: 최대 번들 지갑 점유율 (%)
            stop_loss_pct: 손절 비율 (%) — 기본 15%
            take_profit_1_pct: 1차 익절 비율 (%) — 기본 30%
            trailing_stop_pct: 트레일링 스톱 비율 (%) — 기본 5%
            timeout: HTTP 요청 타임아웃 (초)
        """
        super().__init__(
            name="pump_fun",
            description=(
                "Pump.fun 신규 토큰을 스캔하고 RugCheck 보안 필터를 통과한 "
                "토큰의 진입/손절/익절 가격을 계산합니다."
            ),
        )
        self.pump_fun_api_url = pump_fun_api_url.rstrip("/")
        self.rugcheck_api_url = rugcheck_api_url.rstrip("/")
        self.rugcheck_api_key = rugcheck_api_key
        self.rugcheck_max_score = rugcheck_max_score
        self.min_grad_rate = min_grad_rate
        self.max_bundle_pct = max_bundle_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_1_pct = take_profit_1_pct
        self.trailing_stop_pct = trailing_stop_pct
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        await self._client.aclose()

    def as_tool_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "scan_new_tokens",
                            "security_check",
                            "calculate_levels",
                        ],
                        "description": (
                            "scan_new_tokens: 신규 토큰 목록 스캔, "
                            "security_check: 특정 토큰 보안 검사, "
                            "calculate_levels: 진입/손절/익절 가격 계산"
                        ),
                    },
                    "mint_address": {
                        "type": "string",
                        "description": "보안 검사 대상 토큰 민트 주소",
                    },
                    "entry_price_sol": {
                        "type": "number",
                        "description": "진입 가격 (SOL 기준) — calculate_levels 시 필요",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "스캔 시 최대 반환 토큰 수 (기본 20)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        action: str,
        mint_address: str = "",
        entry_price_sol: float = 0.0,
        limit: int = 20,
        **_kwargs: Any,
    ) -> SkillResult:
        """
        스킬 실행

        Args:
            action: scan_new_tokens / security_check / calculate_levels
            mint_address: 토큰 민트 주소
            entry_price_sol: 진입 가격 (SOL)
            limit: 스캔 최대 반환 수

        Returns:
            SkillResult
        """
        if action == "scan_new_tokens":
            return await self._scan_new_tokens(limit=limit)
        elif action == "security_check":
            if not mint_address:
                return SkillResult(
                    success=False,
                    message="security_check 에는 mint_address가 필요합니다.",
                    errors=["mint_address 누락"],
                )
            return await self._security_check(mint_address)
        elif action == "calculate_levels":
            if entry_price_sol <= 0:
                return SkillResult(
                    success=False,
                    message="calculate_levels 에는 양수 entry_price_sol이 필요합니다.",
                    errors=["entry_price_sol 누락 또는 0"],
                )
            return self._calculate_levels(entry_price_sol)
        else:
            return SkillResult(
                success=False,
                message=f"알 수 없는 작업: {action}",
                errors=[f"지원하지 않는 action: {action}"],
            )

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────────────────────────────────────

    async def _scan_new_tokens(self, limit: int = 20) -> SkillResult:
        """
        Pump.fun 신규 토큰 스캔

        Returns:
            SkillResult with list of new tokens
        """
        try:
            response = await self._client.get(
                f"{self.pump_fun_api_url}/coins",
                params={"limit": min(limit, 50), "sort": "created_timestamp", "order": "DESC"},
            )
            response.raise_for_status()
            tokens: List[Dict[str, Any]] = response.json()
        except httpx.HTTPStatusError as e:
            raise PumpFunException(
                f"Pump.fun API 오류: HTTP {e.response.status_code}",
                details=e.response.text,
            ) from e
        except Exception as e:
            raise PumpFunException(f"Pump.fun 스캔 실패: {str(e)}") from e

        simplified = [
            {
                "mint": t.get("mint", ""),
                "name": t.get("name", ""),
                "symbol": t.get("symbol", ""),
                "market_cap_sol": t.get("market_cap", 0),
                "usd_market_cap": t.get("usd_market_cap", 0),
                "complete": t.get("complete", False),  # 졸업 여부
                "created_timestamp": t.get("created_timestamp", 0),
            }
            for t in tokens
            if t.get("mint")
        ]

        logger.info(f"Pump.fun 신규 토큰 {len(simplified)}개 스캔 완료")
        return SkillResult(
            success=True,
            data={"tokens": simplified, "count": len(simplified)},
            message=f"신규 토큰 {len(simplified)}개 발견",
        )

    async def _security_check(self, mint_address: str) -> SkillResult:
        """
        RugCheck API를 통한 토큰 보안 검사

        검사 항목:
        1. RugCheck 점수 ≤ rugcheck_max_score
        2. 개발자 졸업 가능성 ≥ min_grad_rate
        3. 번들 지갑 점유율 < max_bundle_pct

        Args:
            mint_address: 토큰 민트 주소

        Returns:
            SkillResult with security assessment
        """
        try:
            headers = {}
            if self.rugcheck_api_key:
                headers["Authorization"] = f"Bearer {self.rugcheck_api_key}"

            response = await self._client.get(
                f"{self.rugcheck_api_url}/tokens/{mint_address}/report",
                headers=headers,
            )
            response.raise_for_status()
            report: Dict[str, Any] = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return SkillResult(
                    success=False,
                    message=f"토큰 {mint_address[:8]}... RugCheck 데이터 없음",
                    data={"mint": mint_address, "passed": False, "reason": "no_data"},
                )
            raise RugCheckException(
                f"RugCheck API 오류: HTTP {e.response.status_code}",
                details=e.response.text,
            ) from e
        except Exception as e:
            raise RugCheckException(f"RugCheck 검사 실패: {str(e)}") from e

        # 점수 추출
        score = int(report.get("score", 999))
        risks = report.get("risks", [])

        # 번들 지갑 점유율 — topHolders 기반 추정
        top_holders = report.get("topHolders", [])
        bundle_pct = sum(
            float(h.get("pct", 0))
            for h in top_holders
            if h.get("insider", False)
        )

        # 졸업 가능성 — RugCheck는 직접 제공하지 않으므로 market cap 기반 추정
        # 실제 환경에서는 pump.fun API의 complete/raydium_pool 필드 활용
        token_info = report.get("token", {})
        market_cap_sol = float(token_info.get("marketCapSol", 0))
        # Pump.fun 졸업 기준: _PUMP_FUN_GRADUATION_THRESHOLD_SOL SOL 도달 시 Raydium 이주
        grad_rate_est = (
            min(100.0, (market_cap_sol / _PUMP_FUN_GRADUATION_THRESHOLD_SOL) * 100)
            if market_cap_sol > 0 else 0.0
        )

        failures = []
        if score > self.rugcheck_max_score:
            failures.append(
                f"RugCheck 점수 {score} > 한도 {self.rugcheck_max_score}"
            )
        if grad_rate_est < self.min_grad_rate:
            failures.append(
                f"졸업 가능성 {grad_rate_est:.1f}% < 최소 {self.min_grad_rate}%"
            )
        if bundle_pct >= self.max_bundle_pct:
            failures.append(
                f"번들 지갑 {bundle_pct:.1f}% ≥ 최대 {self.max_bundle_pct}%"
            )

        passed = len(failures) == 0
        data = {
            "mint": mint_address,
            "passed": passed,
            "rugcheck_score": score,
            "grad_rate_est_pct": grad_rate_est,
            "bundle_pct": bundle_pct,
            "risks": risks[:5],  # 상위 5개 위험 요소만
            "failures": failures,
        }

        if passed:
            logger.info(f"보안 검사 통과: {mint_address[:8]}... (점수: {score})")
        else:
            logger.warning(f"보안 검사 실패: {mint_address[:8]}... — {failures}")

        return SkillResult(
            success=passed,
            data=data,
            message="보안 검사 통과" if passed else f"보안 검사 실패: {failures[0]}",
            errors=failures if not passed else [],
        )

    def _calculate_levels(self, entry_price_sol: float) -> SkillResult:
        """
        진입/손절/익절 가격 계산

        전략:
        - 손절: 진입가 × (1 - stop_loss_pct/100)          기본 -15%
        - 1차 익절: 진입가 × (1 + take_profit_1_pct/100)  기본 +30%
        - 트레일링 스톱: 고점 × (1 - trailing_stop_pct/100)

        Args:
            entry_price_sol: 진입 가격 (SOL)

        Returns:
            SkillResult with level calculations
        """
        stop_loss = entry_price_sol * (1 - self.stop_loss_pct / 100)
        take_profit_1 = entry_price_sol * (1 + self.take_profit_1_pct / 100)
        trailing_trigger = take_profit_1  # 1차 익절가 도달 후 트레일링 활성화

        data = {
            "entry_price_sol": entry_price_sol,
            "stop_loss_sol": round(stop_loss, 10),
            "stop_loss_pct": -self.stop_loss_pct,
            "take_profit_1_sol": round(take_profit_1, 10),
            "take_profit_1_pct": self.take_profit_1_pct,
            "tp1_exit_fraction": 0.5,   # 1차 익절 시 원금 50% 회수
            "trailing_stop_pct": self.trailing_stop_pct,
            "trailing_trigger_sol": round(trailing_trigger, 10),
        }

        logger.info(
            f"가격 레벨 계산: 진입={entry_price_sol:.6f} SOL, "
            f"손절={stop_loss:.6f} SOL, 익절1={take_profit_1:.6f} SOL"
        )
        return SkillResult(
            success=True,
            data=data,
            message=(
                f"진입 {entry_price_sol:.6f} SOL | "
                f"손절 {stop_loss:.6f} (-{self.stop_loss_pct}%) | "
                f"1차익절 {take_profit_1:.6f} (+{self.take_profit_1_pct}%)"
            ),
        )
