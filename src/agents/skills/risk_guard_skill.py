"""리스크 관리 스킬 — 거래 안전성 검증 (킬스위치 + 공격적 투자 전략)"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from loguru import logger

from src.services.risk.risk_manager import RiskManager, RiskConfig
from src.core.exceptions import KillSwitchException, SkillException
from .base_skill import BaseSkill, SkillResult


# 공격적 투자 전략 리스크 설정 (Pump.fun 스나이핑)
_AGGRESSIVE_RISK_CONFIG = RiskConfig(
    max_position_pct=10.0,     # 계좌 대비 최대 포지션 10%
    max_leverage=1,             # 레버리지 없음 (현물 스왑)
    daily_loss_limit_pct=20.0, # 일일 손실 한도 20% (킬스위치 트리거)
    max_positions=5,            # 동시 최대 포지션 5개
    risk_per_trade_pct=2.0,     # 거래당 위험 2%
)

# 보수적 리스크 설정 (기본/테스트)
_DEFAULT_SOLANA_RISK_CONFIG = RiskConfig(
    max_position_pct=5.0,
    max_leverage=1,
    daily_loss_limit_pct=3.0,
    max_positions=3,
    risk_per_trade_pct=1.0,
)


class RiskGuardSkill(BaseSkill):
    """
    리스크 관리 스킬 (킬스위치 포함)

    거래 전 안전성을 검증하고 포지션 크기를 계산합니다.
    일일 총 자산 손실이 kill_switch_pct에 도달하면 24시간 거래를 중단합니다.

    공격적 전략 파라미터:
    - 손절: -15% (stop_loss_pct)
    - 1차 익절: +30% 시 원금 50% 회수 (take_profit_1_pct)
    - 트레일링 스톱: 5% (trailing_stop_pct)
    - 킬스위치: 총 자산 20% 손실 시 24시간 중단
    """

    def __init__(
        self,
        risk_config: Optional[RiskConfig] = None,
        max_single_trade_usd: float = 100.0,
        daily_loss_limit_usd: float = 50.0,
        kill_switch_pct: float = 20.0,
        stop_loss_pct: float = 15.0,
        take_profit_1_pct: float = 30.0,
        trailing_stop_pct: float = 5.0,
    ):
        super().__init__(
            name="risk_guard",
            description=(
                "거래 전 안전성을 검증합니다. 킬스위치, 손절/익절 레벨, "
                "포지션 크기, 일일 손실 한도를 관리합니다."
            ),
        )
        self.risk_manager = RiskManager(risk_config or _DEFAULT_SOLANA_RISK_CONFIG)
        self.max_single_trade_usd = max_single_trade_usd
        self.daily_loss_limit_usd = daily_loss_limit_usd
        self.kill_switch_pct = kill_switch_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_1_pct = take_profit_1_pct
        self.trailing_stop_pct = trailing_stop_pct

        self._daily_realized_loss_usd: float = 0.0
        self._kill_switch_triggered: bool = False
        self._kill_switch_triggered_at: Optional[datetime] = None
        self._initial_account_balance: float = 0.0  # 킬스위치 기준 잔액

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
                            "validate_trade",
                            "calculate_position_size",
                            "get_limits",
                            "check_kill_switch",
                            "reset_kill_switch",
                        ],
                        "description": "수행할 리스크 점검 작업",
                    },
                    "trade_amount_usd": {
                        "type": "number",
                        "description": "거래 금액 (USD 기준)",
                    },
                    "account_balance_usd": {
                        "type": "number",
                        "description": "현재 계좌 잔액 (USD)",
                    },
                    "entry_price": {
                        "type": "number",
                        "description": "진입 가격",
                    },
                    "stop_loss_price": {
                        "type": "number",
                        "description": "손절 가격",
                    },
                    "price_impact_pct": {
                        "type": "number",
                        "description": "예상 가격 충격 (%)",
                    },
                    "market_quality": {
                        "type": "string",
                        "description": "시장 품질 (EXCELLENT/GOOD/FAIR/POOR)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        action: str,
        trade_amount_usd: float = 0.0,
        account_balance_usd: float = 0.0,
        entry_price: float = 0.0,
        stop_loss_price: float = 0.0,
        price_impact_pct: float = 0.0,
        market_quality: str = "GOOD",
        **_kwargs: Any,
    ) -> SkillResult:
        """
        리스크 관리 작업 실행

        Args:
            action: validate_trade/calculate_position_size/get_limits/
                    check_kill_switch/reset_kill_switch
            trade_amount_usd: 거래 금액 (USD)
            account_balance_usd: 계좌 잔액 (USD)
            entry_price: 진입 가격
            stop_loss_price: 손절 가격
            price_impact_pct: 예상 가격 충격 (%)
            market_quality: 시장 품질

        Returns:
            SkillResult
        """
        if action == "validate_trade":
            return self._validate_trade(
                trade_amount_usd=trade_amount_usd,
                account_balance_usd=account_balance_usd,
                price_impact_pct=price_impact_pct,
                market_quality=market_quality,
            )
        elif action == "calculate_position_size":
            return self._calculate_size(
                account_balance_usd=account_balance_usd,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
            )
        elif action == "get_limits":
            return self._get_current_limits()
        elif action == "check_kill_switch":
            return self._check_kill_switch(account_balance_usd)
        elif action == "reset_kill_switch":
            return self._reset_kill_switch()
        else:
            return SkillResult(
                success=False,
                message=f"알 수 없는 리스크 작업: {action}",
                errors=[f"지원하지 않는 action: {action}"],
            )

    def _validate_trade(
        self,
        trade_amount_usd: float,
        account_balance_usd: float,
        price_impact_pct: float,
        market_quality: str,
    ) -> SkillResult:
        """거래 유효성 검증"""
        errors = []

        # 0. 킬스위치 확인 — 가장 먼저 체크
        if self._kill_switch_triggered:
            hours_remaining = self._kill_switch_hours_remaining()
            errors.append(
                f"킬스위치 발동 중 — 잔여 대기: {hours_remaining:.1f}시간. "
                "일일 손실 한도 초과로 인해 거래가 차단되었습니다."
            )
            return SkillResult(
                success=False,
                data={
                    "is_valid": False,
                    "kill_switch_active": True,
                    "hours_remaining": hours_remaining,
                },
                message=errors[0],
                errors=errors,
            )

        # 1. 단일 거래 한도 확인
        if trade_amount_usd > self.max_single_trade_usd:
            errors.append(
                f"거래 금액 ${trade_amount_usd:.2f}이 단일 거래 한도 "
                f"${self.max_single_trade_usd:.2f}를 초과합니다."
            )

        # 2. 일일 손실 한도 확인
        remaining_daily_budget = self.daily_loss_limit_usd - self._daily_realized_loss_usd
        if trade_amount_usd > remaining_daily_budget and remaining_daily_budget <= 0:
            errors.append(
                f"일일 손실 한도 ${self.daily_loss_limit_usd:.2f}에 도달했습니다."
            )

        # 3. 계좌 잔액 확인
        max_position = account_balance_usd * (
            self.risk_manager.config.max_position_pct / 100
        )
        if account_balance_usd > 0 and trade_amount_usd > max_position:
            errors.append(
                f"거래 금액 ${trade_amount_usd:.2f}이 최대 포지션 크기 "
                f"${max_position:.2f} ({self.risk_manager.config.max_position_pct}%)를 초과합니다."
            )

        # 4. 가격 충격 확인 (공격적 전략: 2% → 3% 완화)
        if price_impact_pct > 3.0:
            errors.append(
                f"가격 충격 {price_impact_pct:.2f}%이 너무 높습니다. "
                "유동성이 낮은 시장입니다."
            )

        # 5. 시장 품질 확인
        if market_quality == "POOR":
            errors.append("시장 품질이 낮습니다(POOR). 거래를 권장하지 않습니다.")

        is_valid = len(errors) == 0
        data = {
            "is_valid": is_valid,
            "trade_amount_usd": trade_amount_usd,
            "max_single_trade_usd": self.max_single_trade_usd,
            "daily_loss_remaining_usd": max(
                0.0, self.daily_loss_limit_usd - self._daily_realized_loss_usd
            ),
            "price_impact_pct": price_impact_pct,
            "market_quality": market_quality,
            "kill_switch_active": self._kill_switch_triggered,
            "errors": errors,
        }

        if is_valid:
            logger.info(f"리스크 검증 통과: ${trade_amount_usd:.2f} USD")
        else:
            logger.warning(f"리스크 검증 실패: {'; '.join(errors)}")

        return SkillResult(
            success=is_valid,
            data=data,
            message="거래 가능" if is_valid else f"거래 불가: {errors[0]}",
            errors=errors,
        )

    def _calculate_size(
        self,
        account_balance_usd: float,
        entry_price: float,
        stop_loss_price: float,
    ) -> SkillResult:
        """포지션 크기 계산"""
        if entry_price <= 0 or stop_loss_price <= 0:
            return SkillResult(
                success=False,
                message="진입가와 손절가는 0보다 커야 합니다.",
                errors=["유효하지 않은 가격 입력"],
            )
        if entry_price == stop_loss_price:
            return SkillResult(
                success=False,
                message="진입가와 손절가가 같을 수 없습니다.",
                errors=["진입가 == 손절가"],
            )

        position_size = self.risk_manager.calculate_position_size(
            account_balance=account_balance_usd,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
        )
        position_usd = position_size * entry_price
        # 단일 거래 한도 적용
        if position_usd > self.max_single_trade_usd:
            position_size = self.max_single_trade_usd / entry_price
            position_usd = self.max_single_trade_usd

        data = {
            "position_size": position_size,
            "position_usd": position_usd,
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "risk_amount_usd": account_balance_usd
            * (self.risk_manager.config.risk_per_trade_pct / 100),
        }
        logger.info(f"포지션 크기 계산: {position_size:.6f} (${position_usd:.2f})")
        return SkillResult(
            success=True,
            data=data,
            message=f"권장 포지션: {position_size:.6f} (${position_usd:.2f} USD)",
        )

    def _get_current_limits(self) -> SkillResult:
        """현재 리스크 한도 조회"""
        data = {
            "max_single_trade_usd": self.max_single_trade_usd,
            "daily_loss_limit_usd": self.daily_loss_limit_usd,
            "daily_loss_used_usd": self._daily_realized_loss_usd,
            "daily_loss_remaining_usd": max(
                0.0, self.daily_loss_limit_usd - self._daily_realized_loss_usd
            ),
            "max_position_pct": self.risk_manager.config.max_position_pct,
            "risk_per_trade_pct": self.risk_manager.config.risk_per_trade_pct,
            "max_positions": self.risk_manager.config.max_positions,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_1_pct": self.take_profit_1_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "kill_switch_pct": self.kill_switch_pct,
            "kill_switch_active": self._kill_switch_triggered,
        }
        return SkillResult(
            success=True,
            data=data,
            message="현재 리스크 한도 조회 완료",
        )

    def _check_kill_switch(self, account_balance_usd: float = 0.0) -> SkillResult:
        """
        킬스위치 상태 확인

        총 자산의 kill_switch_pct% 이상 손실 시 킬스위치 발동
        """
        # 이미 발동 중인 경우 잔여 시간 반환
        if self._kill_switch_triggered:
            hours_remaining = self._kill_switch_hours_remaining()
            if hours_remaining <= 0:
                # 24시간 경과 → 자동 해제
                self._kill_switch_triggered = False
                self._kill_switch_triggered_at = None
                logger.info("킬스위치 자동 해제 (24시간 경과)")
                return SkillResult(
                    success=True,
                    data={"kill_switch_active": False},
                    message="킬스위치 해제됨 (24시간 경과)",
                )
            return SkillResult(
                success=False,
                data={
                    "kill_switch_active": True,
                    "hours_remaining": hours_remaining,
                },
                message=f"킬스위치 활성 — 잔여 대기: {hours_remaining:.1f}시간",
            )

        # 잔액 기반 킬스위치 평가
        if account_balance_usd > 0 and self._initial_account_balance > 0:
            loss_pct = (
                (self._initial_account_balance - account_balance_usd)
                / self._initial_account_balance * 100
            )
            if loss_pct >= self.kill_switch_pct:
                self._kill_switch_triggered = True
                self._kill_switch_triggered_at = datetime.now(timezone.utc)
                logger.warning(
                    f"킬스위치 발동! 손실률 {loss_pct:.1f}% ≥ "
                    f"한도 {self.kill_switch_pct}%. 24시간 거래 중단."
                )
                return SkillResult(
                    success=False,
                    data={
                        "kill_switch_active": True,
                        "loss_pct": loss_pct,
                        "hours_remaining": 24.0,
                    },
                    message=(
                        f"킬스위치 발동: 손실 {loss_pct:.1f}% ≥ "
                        f"한도 {self.kill_switch_pct}%. 24시간 거래 중단."
                    ),
                )

        return SkillResult(
            success=True,
            data={"kill_switch_active": False},
            message="킬스위치 비활성 — 거래 정상 가능",
        )

    def _reset_kill_switch(self) -> SkillResult:
        """킬스위치 수동 해제 (인간 승인 후 호출)"""
        was_active = self._kill_switch_triggered
        self._kill_switch_triggered = False
        self._kill_switch_triggered_at = None
        self._daily_realized_loss_usd = 0.0
        logger.info("킬스위치 수동 해제됨")
        return SkillResult(
            success=True,
            data={"was_active": was_active, "kill_switch_active": False},
            message="킬스위치 해제됨. 일일 손실 카운터도 초기화되었습니다.",
        )

    def _kill_switch_hours_remaining(self) -> float:
        """킬스위치 잔여 시간 계산 (시간 단위)"""
        if not self._kill_switch_triggered_at:
            return 0.0
        from datetime import timedelta
        elapsed = datetime.now(timezone.utc) - self._kill_switch_triggered_at
        remaining = timedelta(hours=24) - elapsed
        return max(0.0, remaining.total_seconds() / 3600)

    def record_loss(self, loss_usd: float) -> None:
        """
        실현 손실 기록 (일일 한도 추적용)

        Args:
            loss_usd: 손실 금액 (USD, 양수)
        """
        if loss_usd > 0:
            self._daily_realized_loss_usd += loss_usd
            logger.info(
                f"일일 손실 기록: +${loss_usd:.2f} "
                f"(누적: ${self._daily_realized_loss_usd:.2f})"
            )

    def reset_daily_loss(self) -> None:
        """일일 손실 카운터 초기화 (매일 자정 호출)"""
        self._daily_realized_loss_usd = 0.0
        logger.info("일일 손실 카운터 초기화")
