"""리스크 관리 스킬 — 거래 안전성 검증"""
from typing import Any, Dict, Optional
from loguru import logger

from src.services.risk.risk_manager import RiskManager, RiskConfig
from src.core.exceptions import SkillException
from .base_skill import BaseSkill, SkillResult


# 솔라나 DeFi 기본 리스크 설정 (보수적 초기값)
_DEFAULT_SOLANA_RISK_CONFIG = RiskConfig(
    max_position_pct=5.0,      # 계좌 대비 최대 포지션 5%
    max_leverage=1,             # 레버리지 없음 (현물 스왑)
    daily_loss_limit_pct=3.0,  # 일일 손실 한도 3%
    max_positions=3,            # 동시 최대 포지션 3개
    risk_per_trade_pct=1.0,     # 거래당 위험 1%
)


class RiskGuardSkill(BaseSkill):
    """
    리스크 관리 스킬

    거래 전 안전성을 검증하고 포지션 크기를 계산합니다.
    모든 거래는 이 스킬을 통해 검증되어야 합니다.
    """

    def __init__(
        self,
        risk_config: Optional[RiskConfig] = None,
        max_single_trade_usd: float = 100.0,
        daily_loss_limit_usd: float = 50.0,
    ):
        super().__init__(
            name="risk_guard",
            description=(
                "거래 전 안전성을 검증합니다. 포지션 크기, 일일 손실 한도, "
                "슬리피지 허용치를 확인하고 적절한 포지션 크기를 계산합니다."
            ),
        )
        self.risk_manager = RiskManager(risk_config or _DEFAULT_SOLANA_RISK_CONFIG)
        self.max_single_trade_usd = max_single_trade_usd
        self.daily_loss_limit_usd = daily_loss_limit_usd
        self._daily_realized_loss_usd: float = 0.0

    def as_tool_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["validate_trade", "calculate_position_size", "get_limits"],
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
            action: 수행할 작업 (validate_trade/calculate_position_size/get_limits)
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

        # 4. 가격 충격 확인
        if price_impact_pct > 2.0:
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
        }
        return SkillResult(
            success=True,
            data=data,
            message="현재 리스크 한도 조회 완료",
        )

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
