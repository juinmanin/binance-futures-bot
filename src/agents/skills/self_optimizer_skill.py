"""자기 개선 스킬 — 거래 성과 분석 기반 슬리피지·Jito 팁 자동 최적화"""
from collections import deque
from typing import Any, Deque, Dict, List, Optional
from loguru import logger

from .base_skill import BaseSkill, SkillResult
from .jito_bribe_skill import JitoBribeSkill


# 거래 결과 레코드
class _TradeRecord:
    __slots__ = ("success", "slippage_exceeded", "tx_failed", "pnl_pct")

    def __init__(
        self,
        success: bool,
        slippage_exceeded: bool = False,
        tx_failed: bool = False,
        pnl_pct: float = 0.0,
    ):
        self.success = success
        self.slippage_exceeded = slippage_exceeded
        self.tx_failed = tx_failed
        self.pnl_pct = pnl_pct


class SelfOptimizerSkill(BaseSkill):
    """
    자기 개선 스킬

    최근 N회(기본 5회) 거래를 분석하여 설정값을 자동으로 조정합니다.

    최적화 항목:
    - 슬리피지: 'Slippage exceeded' 에러 발생 시 +2% 상향 (최대 25%)
    - Jito 팁: JitoBribeSkill에 성공/실패 보고 위임
    - 통계 요약 → 에이전트 보고용 데이터 제공
    """

    def __init__(
        self,
        jito_skill: JitoBribeSkill,
        window_size: int = 5,
        slippage_increment_bps: int = 200,   # 실패 시 +2%
        initial_slippage_bps: int = 1500,    # 초기 슬리피지 15%
        max_slippage_bps: int = 2500,        # 최대 슬리피지 25%
    ):
        """
        초기화

        Args:
            jito_skill: JitoBribeSkill 인스턴스
            window_size: 분석 창 크기 (기본 5)
            slippage_increment_bps: 슬리피지 에러 발생 시 증가분 (BPS)
            initial_slippage_bps: 초기 슬리피지 (BPS)
            max_slippage_bps: 최대 슬리피지 (BPS)
        """
        super().__init__(
            name="self_optimizer",
            description=(
                "최근 거래 성과를 분석하여 슬리피지와 Jito 팁을 자동 조정합니다."
            ),
        )
        self.jito_skill = jito_skill
        self.window_size = window_size
        self.slippage_increment_bps = slippage_increment_bps
        self.current_slippage_bps = initial_slippage_bps
        self.max_slippage_bps = max_slippage_bps
        self._history: Deque[_TradeRecord] = deque(maxlen=window_size)
        self._total_trades = 0
        self._total_success = 0

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
                            "record_trade",
                            "run_optimization",
                            "get_current_settings",
                            "get_trade_summary",
                        ],
                        "description": (
                            "record_trade: 거래 결과 기록, "
                            "run_optimization: 최근 거래 분석 후 설정 조정, "
                            "get_current_settings: 현재 최적화 설정 조회, "
                            "get_trade_summary: 최근 거래 통계 요약"
                        ),
                    },
                    "success": {
                        "type": "boolean",
                        "description": "거래 성공 여부 (record_trade 시)",
                    },
                    "slippage_exceeded": {
                        "type": "boolean",
                        "description": "슬리피지 초과 에러 발생 여부",
                    },
                    "tx_failed": {
                        "type": "boolean",
                        "description": "트랜잭션 미체결 여부",
                    },
                    "pnl_pct": {
                        "type": "number",
                        "description": "거래 손익 (%, 양수: 수익, 음수: 손실)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        action: str,
        success: bool = False,
        slippage_exceeded: bool = False,
        tx_failed: bool = False,
        pnl_pct: float = 0.0,
        **_kwargs: Any,
    ) -> SkillResult:
        """
        자기 개선 작업 실행

        Args:
            action: record_trade / run_optimization / get_current_settings / get_trade_summary
            success: 거래 성공 여부
            slippage_exceeded: 슬리피지 초과 에러 발생 여부
            tx_failed: 트랜잭션 미체결 여부
            pnl_pct: 손익 (%)

        Returns:
            SkillResult
        """
        if action == "record_trade":
            return self._record_trade(success, slippage_exceeded, tx_failed, pnl_pct)
        elif action == "run_optimization":
            return await self._run_optimization()
        elif action == "get_current_settings":
            return self._get_current_settings()
        elif action == "get_trade_summary":
            return self._get_trade_summary()
        else:
            return SkillResult(
                success=False,
                message=f"알 수 없는 작업: {action}",
                errors=[f"지원하지 않는 action: {action}"],
            )

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────────────────────────────────────

    def _record_trade(
        self,
        success: bool,
        slippage_exceeded: bool,
        tx_failed: bool,
        pnl_pct: float,
    ) -> SkillResult:
        """거래 결과 기록"""
        record = _TradeRecord(
            success=success,
            slippage_exceeded=slippage_exceeded,
            tx_failed=tx_failed,
            pnl_pct=pnl_pct,
        )
        self._history.append(record)
        self._total_trades += 1
        if success:
            self._total_success += 1

        logger.info(
            f"거래 기록: {'성공' if success else '실패'}, "
            f"PnL={pnl_pct:+.1f}%, 슬리피지초과={slippage_exceeded}, "
            f"미체결={tx_failed}"
        )
        return SkillResult(
            success=True,
            data={
                "recorded": True,
                "window_size": len(self._history),
                "total_trades": self._total_trades,
            },
            message=f"거래 결과 기록 완료 ({len(self._history)}/{self.window_size})",
        )

    async def _run_optimization(self) -> SkillResult:
        """
        최근 거래 분석 후 설정 조정

        트리거:
        1. 슬리피지 에러 발생 비율 > 20% → 슬리피지 +2%
        2. 미체결 비율 > 20% → Jito 팁 증가 (jito_skill에 위임)
        3. 연속 성공 3회 → Jito 팁 감소 (jito_skill에 위임)
        """
        if len(self._history) < self.window_size:
            return SkillResult(
                success=True,
                data={"optimized": False, "reason": "insufficient_data"},
                message=f"최적화 데이터 부족: {len(self._history)}/{self.window_size}",
            )

        records = list(self._history)
        slippage_err_count = sum(1 for r in records if r.slippage_exceeded)
        tx_fail_count = sum(1 for r in records if r.tx_failed)
        success_count = sum(1 for r in records if r.success)
        avg_pnl = sum(r.pnl_pct for r in records) / len(records)

        changes: List[str] = []

        # 슬리피지 조정
        if slippage_err_count / self.window_size > 0.2:
            old_slippage = self.current_slippage_bps
            self.current_slippage_bps = min(
                self.max_slippage_bps,
                self.current_slippage_bps + self.slippage_increment_bps,
            )
            if self.current_slippage_bps != old_slippage:
                changes.append(
                    f"슬리피지 상향: {old_slippage/100:.0f}% → "
                    f"{self.current_slippage_bps/100:.0f}%"
                )
                logger.info(changes[-1])

        # Jito 팁 조정
        if tx_fail_count / self.window_size > 0.2:
            await self.jito_skill.execute(action="report_failure")
            changes.append("Jito 팁 상향 (미체결 비율 20% 초과)")
        elif success_count == self.window_size:
            await self.jito_skill.execute(action="report_success")
            changes.append("Jito 팁 하향 (전체 성공)")

        # 슬리피지가 최대치에 도달하고 아직도 실패 → 경고
        if (
            self.current_slippage_bps >= self.max_slippage_bps
            and slippage_err_count > 0
        ):
            changes.append(
                f"경고: 슬리피지가 최대({self.max_slippage_bps/100:.0f}%)에 도달했습니다. "
                "토큰 유동성 재검토 필요."
            )

        data = {
            "optimized": len(changes) > 0,
            "changes": changes,
            "window_analysis": {
                "window_size": self.window_size,
                "success_count": success_count,
                "slippage_err_count": slippage_err_count,
                "tx_fail_count": tx_fail_count,
                "avg_pnl_pct": round(avg_pnl, 2),
            },
            "current_slippage_bps": self.current_slippage_bps,
        }

        return SkillResult(
            success=True,
            data=data,
            message=(
                f"최적화 완료: {'; '.join(changes) if changes else '변경 없음'}"
            ),
        )

    def _get_current_settings(self) -> SkillResult:
        """현재 최적화 설정 조회"""
        jito_result = self.jito_skill._get_current_tip()
        data = {
            "slippage_bps": self.current_slippage_bps,
            "slippage_pct": self.current_slippage_bps / 100,
            "max_slippage_bps": self.max_slippage_bps,
            "jito_tip_sol": jito_result.data.get("tip_sol", 0) if jito_result.data else 0,
            "window_size": self.window_size,
            "history_count": len(self._history),
        }
        return SkillResult(
            success=True,
            data=data,
            message=(
                f"슬리피지: {self.current_slippage_bps/100:.0f}%, "
                f"Jito 팁: {data['jito_tip_sol']:.4f} SOL"
            ),
        )

    def _get_trade_summary(self) -> SkillResult:
        """최근 거래 통계 요약"""
        if not self._history:
            return SkillResult(
                success=True,
                data={"total_trades": 0},
                message="거래 기록 없음",
            )

        records = list(self._history)
        success_rate = (
            self._total_success / self._total_trades * 100 if self._total_trades > 0 else 0
        )
        avg_pnl = sum(r.pnl_pct for r in records) / len(records)
        total_pnl = sum(r.pnl_pct for r in records)

        data = {
            "total_trades": self._total_trades,
            "total_success": self._total_success,
            "success_rate_pct": round(success_rate, 2),
            "window_avg_pnl_pct": round(avg_pnl, 2),
            "window_total_pnl_pct": round(total_pnl, 2),
            "recent_trades": [
                {
                    "success": r.success,
                    "pnl_pct": r.pnl_pct,
                    "slippage_exceeded": r.slippage_exceeded,
                    "tx_failed": r.tx_failed,
                }
                for r in records
            ],
        }
        return SkillResult(
            success=True,
            data=data,
            message=(
                f"총 {self._total_trades}회 거래 | "
                f"성공률 {success_rate:.1f}% | "
                f"최근 평균 PnL {avg_pnl:+.1f}%"
            ),
        )
