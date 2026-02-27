"""Jito 번들 우선순위 수수료 자동 조정 스킬"""
import asyncio
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger

from src.core.exceptions import JitoException
from .base_skill import BaseSkill, SkillResult


# Jito 팁 계정 목록 (공식 문서 기준)
# 팁 전송 시 이 계정 중 하나를 무작위로 선택하여 SOL 팁을 전송합니다.
# 실제 팁 트랜잭션 구성 시 사용합니다.
_JITO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
]


class JitoBribeSkill(BaseSkill):
    """
    Jito 번들 우선순위 수수료(팁) 자동 조정 스킬

    전략:
    - 트랜잭션 미체결 시 팁을 increment_sol만큼 상향 (max_tip_sol 한도)
    - 연속 3회 성공 시 팁을 decrement_sol만큼 하향 (min_tip_sol 한도)
    """

    def __init__(
        self,
        jito_api_url: str = "https://mainnet.block-engine.jito.wtf",
        default_tip_sol: float = 0.001,
        max_tip_sol: float = 0.05,
        min_tip_sol: float = 0.0001,
        increment_sol: float = 0.005,
        decrement_sol: float = 0.002,
        success_streak_threshold: int = 3,
        timeout: float = 20.0,
    ):
        """
        초기화

        Args:
            jito_api_url: Jito Block Engine API URL
            default_tip_sol: 기본 팁 (SOL)
            max_tip_sol: 최대 팁 (SOL)
            min_tip_sol: 최소 팁 (SOL)
            increment_sol: 실패 시 팁 증가분 (SOL)
            decrement_sol: 연속 성공 시 팁 감소분 (SOL)
            success_streak_threshold: 팁 감소를 위한 연속 성공 횟수
            timeout: HTTP 요청 타임아웃 (초)
        """
        super().__init__(
            name="jito_bribe",
            description=(
                "Jito 번들 팁을 관리합니다. 미체결 시 팁을 상향하고 "
                "연속 성공 시 팁을 절감합니다."
            ),
        )
        self.jito_api_url = jito_api_url.rstrip("/")
        self.current_tip_sol = default_tip_sol
        self.default_tip_sol = default_tip_sol
        self.max_tip_sol = max_tip_sol
        self.min_tip_sol = min_tip_sol
        self.increment_sol = increment_sol
        self.decrement_sol = decrement_sol
        self.success_streak_threshold = success_streak_threshold
        self._client = httpx.AsyncClient(timeout=timeout)

        # 통계
        self._success_streak = 0
        self._total_tips_paid_sol = 0.0
        self._tx_sent = 0
        self._tx_success = 0

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
                            "get_tip",
                            "report_success",
                            "report_failure",
                            "get_stats",
                            "send_bundle",
                        ],
                        "description": (
                            "get_tip: 현재 권장 팁 조회, "
                            "report_success: 성공 보고 (자동 팁 감소), "
                            "report_failure: 실패 보고 (자동 팁 증가), "
                            "get_stats: 팁 통계 조회, "
                            "send_bundle: Jito 번들 전송"
                        ),
                    },
                    "transactions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Base64 인코딩된 서명 트랜잭션 목록 (send_bundle 시)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        action: str,
        transactions: Optional[List[str]] = None,
        **_kwargs: Any,
    ) -> SkillResult:
        """
        Jito 팁 관리 작업 실행

        Args:
            action: get_tip / report_success / report_failure / get_stats / send_bundle
            transactions: Base64 서명 트랜잭션 목록 (send_bundle 시)

        Returns:
            SkillResult
        """
        if action == "get_tip":
            return self._get_current_tip()
        elif action == "report_success":
            return self._on_success()
        elif action == "report_failure":
            return self._on_failure()
        elif action == "get_stats":
            return self._get_stats()
        elif action == "send_bundle":
            return await self._send_bundle(transactions or [])
        else:
            return SkillResult(
                success=False,
                message=f"알 수 없는 Jito 작업: {action}",
                errors=[f"지원하지 않는 action: {action}"],
            )

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────────────────────────────────────

    def _get_current_tip(self) -> SkillResult:
        """현재 권장 팁 반환"""
        data = {
            "tip_sol": self.current_tip_sol,
            "tip_lamports": int(self.current_tip_sol * 1_000_000_000),
            "success_streak": self._success_streak,
            "max_tip_sol": self.max_tip_sol,
            "min_tip_sol": self.min_tip_sol,
        }
        return SkillResult(
            success=True,
            data=data,
            message=f"현재 팁: {self.current_tip_sol:.4f} SOL",
        )

    def _on_success(self) -> SkillResult:
        """트랜잭션 성공 처리"""
        self._tx_success += 1
        self._tx_sent += 1
        self._success_streak += 1

        if self._success_streak >= self.success_streak_threshold:
            old_tip = self.current_tip_sol
            self.current_tip_sol = max(
                self.min_tip_sol, self.current_tip_sol - self.decrement_sol
            )
            self._success_streak = 0
            logger.info(
                f"연속 {self.success_streak_threshold}회 성공 → "
                f"팁 감소: {old_tip:.4f} → {self.current_tip_sol:.4f} SOL"
            )

        self._total_tips_paid_sol += self.current_tip_sol
        return SkillResult(
            success=True,
            data={"tip_sol": self.current_tip_sol, "success_streak": self._success_streak},
            message=f"성공 기록됨. 현재 팁: {self.current_tip_sol:.4f} SOL",
        )

    def _on_failure(self) -> SkillResult:
        """트랜잭션 실패 처리 — 팁 상향"""
        self._tx_sent += 1
        self._success_streak = 0
        old_tip = self.current_tip_sol
        self.current_tip_sol = min(
            self.max_tip_sol, self.current_tip_sol + self.increment_sol
        )
        logger.warning(
            f"미체결 발생 → 팁 상향: {old_tip:.4f} → {self.current_tip_sol:.4f} SOL"
        )
        return SkillResult(
            success=True,
            data={"tip_sol": self.current_tip_sol, "previous_tip": old_tip},
            message=f"팁 상향: {old_tip:.4f} → {self.current_tip_sol:.4f} SOL",
        )

    def _get_stats(self) -> SkillResult:
        """팁 통계 조회"""
        success_rate = (
            (self._tx_success / self._tx_sent * 100) if self._tx_sent > 0 else 0.0
        )
        data = {
            "current_tip_sol": self.current_tip_sol,
            "default_tip_sol": self.default_tip_sol,
            "total_tips_paid_sol": round(self._total_tips_paid_sol, 6),
            "tx_sent": self._tx_sent,
            "tx_success": self._tx_success,
            "success_rate_pct": round(success_rate, 2),
            "success_streak": self._success_streak,
        }
        return SkillResult(
            success=True,
            data=data,
            message=(
                f"팁 통계: 현재={self.current_tip_sol:.4f} SOL, "
                f"성공률={success_rate:.1f}%, 총팁={self._total_tips_paid_sol:.4f} SOL"
            ),
        )

    async def _send_bundle(self, transactions: List[str]) -> SkillResult:
        """
        Jito 번들 전송

        Args:
            transactions: Base64 인코딩된 서명 트랜잭션 목록

        Returns:
            SkillResult with bundle ID
        """
        if not transactions:
            return SkillResult(
                success=False,
                message="트랜잭션 목록이 비어 있습니다.",
                errors=["transactions 누락"],
            )

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendBundle",
            "params": [transactions],
        }

        try:
            response = await self._client.post(
                f"{self.jito_api_url}/api/v1/bundles",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise JitoException(
                f"Jito 번들 전송 실패: HTTP {e.response.status_code}",
                details=e.response.text,
            ) from e
        except Exception as e:
            raise JitoException(f"Jito 전송 오류: {str(e)}") from e

        if "error" in data:
            err = data["error"]
            raise JitoException(
                f"Jito RPC 오류 [{err.get('code')}]: {err.get('message')}",
                details=err,
            )

        bundle_id = data.get("result", "")
        logger.info(f"Jito 번들 전송 완료: {str(bundle_id)[:20]}...")
        return SkillResult(
            success=True,
            data={"bundle_id": bundle_id, "tip_sol": self.current_tip_sol},
            message=f"번들 전송 완료 (팁: {self.current_tip_sol:.4f} SOL)",
        )
