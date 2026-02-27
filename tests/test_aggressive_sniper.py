"""신규 스킬 및 하트비트 테스트 (공격적 투자 전략 + 보안 업그레이드)"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.skills.pump_fun_skill import PumpFunSkill
from src.agents.skills.jito_bribe_skill import JitoBribeSkill
from src.agents.skills.self_optimizer_skill import SelfOptimizerSkill
from src.agents.skills.cryptowallet_skill import CryptoWalletSkill
from src.agents.skills.risk_guard_skill import (
    RiskGuardSkill, _DEFAULT_SOLANA_RISK_CONFIG, _AGGRESSIVE_RISK_CONFIG
)
from src.agents.skills.base_skill import SkillResult
from src.agents.heartbeat import HeartbeatScheduler, SniperHeartbeat
from src.core.exceptions import (
    PumpFunException, RugCheckException, JitoException, KillSwitchException, SkillException
)


# ──────────────────────────────────────────────────────────────────────────────
# 예외 클래스 테스트
# ──────────────────────────────────────────────────────────────────────────────

class TestNewExceptions:
    def test_pump_fun_exception(self):
        err = PumpFunException("Pump.fun 오류")
        assert err.message == "Pump.fun 오류"

    def test_rugcheck_exception(self):
        err = RugCheckException("RugCheck 오류")
        assert err.message == "RugCheck 오류"

    def test_jito_exception(self):
        err = JitoException("Jito 오류")
        assert err.message == "Jito 오류"

    def test_kill_switch_exception(self):
        err = KillSwitchException("킬스위치 발동", details={"loss_pct": 21.5})
        assert "킬스위치" in err.message
        assert err.details["loss_pct"] == 21.5


# ──────────────────────────────────────────────────────────────────────────────
# PumpFunSkill 테스트
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def pump_fun_skill():
    return PumpFunSkill(
        stop_loss_pct=15.0,
        take_profit_1_pct=30.0,
        trailing_stop_pct=5.0,
    )


class TestPumpFunSkill:
    def test_tool_definition(self, pump_fun_skill):
        defn = pump_fun_skill.as_tool_definition()
        assert defn["name"] == "pump_fun"
        actions = defn["input_schema"]["properties"]["action"]["enum"]
        assert "scan_new_tokens" in actions
        assert "security_check" in actions
        assert "calculate_levels" in actions

    def test_calculate_levels_basic(self, pump_fun_skill):
        """가격 레벨 계산 테스트"""
        result = pump_fun_skill._calculate_levels(entry_price_sol=1.0)
        assert result.success is True
        data = result.data
        # 손절 -15%
        assert abs(data["stop_loss_sol"] - 0.85) < 1e-9
        assert data["stop_loss_pct"] == -15.0
        # 1차 익절 +30%
        assert abs(data["take_profit_1_sol"] - 1.30) < 1e-9
        assert data["take_profit_1_pct"] == 30.0
        # 원금 50% 회수
        assert data["tp1_exit_fraction"] == 0.5
        # 트레일링 스톱 5%
        assert data["trailing_stop_pct"] == 5.0

    def test_calculate_levels_small_price(self, pump_fun_skill):
        """소액 토큰 가격 레벨"""
        result = pump_fun_skill._calculate_levels(entry_price_sol=0.000001)
        assert result.success is True
        assert result.data["stop_loss_sol"] < 0.000001

    @pytest.mark.asyncio
    async def test_calculate_levels_via_execute(self, pump_fun_skill):
        result = await pump_fun_skill.execute(
            action="calculate_levels", entry_price_sol=2.5
        )
        assert result.success is True
        assert result.data["stop_loss_sol"] == pytest.approx(2.5 * 0.85, rel=1e-6)

    @pytest.mark.asyncio
    async def test_security_check_missing_mint(self, pump_fun_skill):
        result = await pump_fun_skill.execute(action="security_check")
        assert result.success is False
        assert "mint_address" in result.message

    @pytest.mark.asyncio
    async def test_calculate_levels_zero_price_fails(self, pump_fun_skill):
        result = await pump_fun_skill.execute(
            action="calculate_levels", entry_price_sol=0.0
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_scan_new_tokens_api_success(self, pump_fun_skill):
        mock_tokens = [
            {"mint": "mint1" + "a" * 38, "name": "TestToken", "symbol": "TST",
             "market_cap": 100, "usd_market_cap": 200, "complete": False,
             "created_timestamp": 1700000000},
        ]
        with patch.object(pump_fun_skill._client, "get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value=mock_tokens)
            mock_get.return_value = mock_resp

            result = await pump_fun_skill.execute(action="scan_new_tokens", limit=5)
        assert result.success is True
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_scan_new_tokens_api_failure(self, pump_fun_skill):
        import httpx
        with patch.object(pump_fun_skill._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("연결 실패")
            with pytest.raises(PumpFunException):
                await pump_fun_skill._scan_new_tokens()

    @pytest.mark.asyncio
    async def test_security_check_404(self, pump_fun_skill):
        """토큰 데이터 없는 경우"""
        import httpx
        with patch.object(pump_fun_skill._client, "get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock(status_code=404, text="Not Found")
            )
            mock_get.return_value = mock_resp
            result = await pump_fun_skill._security_check("mint_address_123")
        assert result.success is False
        assert "데이터 없음" in result.message

    @pytest.mark.asyncio
    async def test_security_check_passes_all_criteria(self, pump_fun_skill):
        """모든 보안 조건 통과"""
        good_report = {
            "score": 50,
            "risks": [],
            "topHolders": [],
            "token": {"marketCapSol": 30.0},  # ~43% 졸업 가능성
        }
        with patch.object(pump_fun_skill._client, "get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value=good_report)
            mock_get.return_value = mock_resp
            result = await pump_fun_skill._security_check("safe_mint_address")
        assert result.success is True
        assert result.data["passed"] is True

    @pytest.mark.asyncio
    async def test_security_check_fails_high_score(self, pump_fun_skill):
        """RugCheck 점수 초과"""
        bad_report = {
            "score": 150,  # 한도 100 초과
            "risks": [{"name": "honeypot"}],
            "topHolders": [],
            "token": {"marketCapSol": 50.0},
        }
        with patch.object(pump_fun_skill._client, "get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value=bad_report)
            mock_get.return_value = mock_resp
            result = await pump_fun_skill._security_check("bad_mint_address")
        assert result.success is False
        assert result.data["passed"] is False

    @pytest.mark.asyncio
    async def test_unknown_action(self, pump_fun_skill):
        result = await pump_fun_skill.execute(action="invalid")
        assert result.success is False


# ──────────────────────────────────────────────────────────────────────────────
# JitoBribeSkill 테스트
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def jito_skill():
    return JitoBribeSkill(
        default_tip_sol=0.001,
        max_tip_sol=0.05,
        min_tip_sol=0.0001,
        increment_sol=0.005,
        decrement_sol=0.002,
        success_streak_threshold=3,
    )


class TestJitoBribeSkill:
    def test_tool_definition(self, jito_skill):
        defn = jito_skill.as_tool_definition()
        assert defn["name"] == "jito_bribe"
        actions = defn["input_schema"]["properties"]["action"]["enum"]
        assert all(a in actions for a in ["get_tip", "report_success", "report_failure", "get_stats"])

    @pytest.mark.asyncio
    async def test_get_tip_initial(self, jito_skill):
        result = await jito_skill.execute(action="get_tip")
        assert result.success is True
        assert result.data["tip_sol"] == 0.001
        assert result.data["tip_lamports"] == 1_000_000

    @pytest.mark.asyncio
    async def test_failure_increases_tip(self, jito_skill):
        result = await jito_skill.execute(action="report_failure")
        assert result.success is True
        assert result.data["tip_sol"] == pytest.approx(0.001 + 0.005)

    @pytest.mark.asyncio
    async def test_failure_capped_at_max(self, jito_skill):
        """최대 팁 한도 확인"""
        jito_skill.current_tip_sol = 0.048
        result = await jito_skill.execute(action="report_failure")
        assert result.data["tip_sol"] == 0.05  # max_tip

    @pytest.mark.asyncio
    async def test_success_streak_decreases_tip(self, jito_skill):
        """연속 3회 성공 시 팁 감소"""
        jito_skill.current_tip_sol = 0.02
        for _ in range(3):
            await jito_skill.execute(action="report_success")
        assert jito_skill.current_tip_sol == pytest.approx(0.02 - 0.002)

    @pytest.mark.asyncio
    async def test_success_streak_reset_after_failure(self, jito_skill):
        """성공 후 실패 시 streak 초기화"""
        await jito_skill.execute(action="report_success")
        await jito_skill.execute(action="report_success")
        assert jito_skill._success_streak == 2
        await jito_skill.execute(action="report_failure")
        assert jito_skill._success_streak == 0

    @pytest.mark.asyncio
    async def test_tip_floor_not_below_min(self, jito_skill):
        """최소 팁 이하로 감소하지 않음"""
        jito_skill.current_tip_sol = 0.0003
        jito_skill._success_streak = 2
        await jito_skill.execute(action="report_success")  # 3번째 성공
        assert jito_skill.current_tip_sol >= jito_skill.min_tip_sol

    @pytest.mark.asyncio
    async def test_get_stats(self, jito_skill):
        await jito_skill.execute(action="report_success")
        await jito_skill.execute(action="report_failure")
        result = await jito_skill.execute(action="get_stats")
        assert result.success is True
        assert result.data["tx_sent"] == 2
        assert result.data["tx_success"] == 1

    @pytest.mark.asyncio
    async def test_send_bundle_empty_fails(self, jito_skill):
        result = await jito_skill.execute(action="send_bundle", transactions=[])
        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_bundle_success(self, jito_skill):
        with patch.object(jito_skill._client, "post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value={"jsonrpc": "2.0", "id": 1, "result": "bundle_id_123"})
            mock_post.return_value = mock_resp

            result = await jito_skill.execute(action="send_bundle", transactions=["dGVzdA=="])
        assert result.success is True
        assert result.data["bundle_id"] == "bundle_id_123"

    @pytest.mark.asyncio
    async def test_unknown_action(self, jito_skill):
        result = await jito_skill.execute(action="unknown")
        assert result.success is False


# ──────────────────────────────────────────────────────────────────────────────
# CryptoWalletSkill 테스트
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def cryptowallet_skill():
    return CryptoWalletSkill(master_encryption_key="test-master-key-for-testing-only")


class TestCryptoWalletSkill:
    def test_init_without_key_raises(self):
        with pytest.raises(SkillException):
            CryptoWalletSkill(master_encryption_key="")

    def test_tool_definition(self, cryptowallet_skill):
        defn = cryptowallet_skill.as_tool_definition()
        assert defn["name"] == "cryptowallet"
        actions = defn["input_schema"]["properties"]["action"]["enum"]
        assert "encrypt_key" in actions
        assert "verify_key" in actions
        assert "get_public_key" in actions

    @pytest.mark.asyncio
    async def test_encrypt_key_success(self, cryptowallet_skill):
        # 유효한 길이의 가짜 키 (최소 32자)
        fake_key = "a" * 88  # Base58 솔라나 키 길이 유사
        result = await cryptowallet_skill.execute(
            action="encrypt_key", private_key_b58=fake_key
        )
        assert result.success is True
        assert "encrypted_key" in result.data
        # 평문 키가 결과에 없어야 함
        assert fake_key not in str(result.data)

    @pytest.mark.asyncio
    async def test_encrypt_key_missing_fails(self, cryptowallet_skill):
        result = await cryptowallet_skill.execute(action="encrypt_key", private_key_b58="")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_encrypt_key_too_short_fails(self, cryptowallet_skill):
        result = await cryptowallet_skill.execute(
            action="encrypt_key", private_key_b58="tooshort"
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_encrypt_then_verify(self, cryptowallet_skill):
        fake_key = "b" * 88
        enc_result = await cryptowallet_skill.execute(
            action="encrypt_key", private_key_b58=fake_key
        )
        encrypted = enc_result.data["encrypted_key"]

        verify_result = await cryptowallet_skill.execute(
            action="verify_key", encrypted_key=encrypted
        )
        assert verify_result.success is True
        assert verify_result.data["is_valid"] is True

    @pytest.mark.asyncio
    async def test_verify_invalid_key(self, cryptowallet_skill):
        result = await cryptowallet_skill.execute(
            action="verify_key", encrypted_key="invalid_base64_data!!!"
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_verify_missing_key(self, cryptowallet_skill):
        result = await cryptowallet_skill.execute(action="verify_key")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_no_plaintext_key_in_output(self, cryptowallet_skill):
        """암호화 결과에 평문 키가 포함되지 않음을 확인"""
        fake_key = "mysecretprivatekey123456789abcdef12345678901234567890"
        result = await cryptowallet_skill.execute(
            action="encrypt_key", private_key_b58=fake_key
        )
        # 메시지나 데이터에 평문 키가 없어야 함
        assert fake_key not in result.message
        assert fake_key not in str(result.data)

    @pytest.mark.asyncio
    async def test_unknown_action(self, cryptowallet_skill):
        result = await cryptowallet_skill.execute(action="unknown")
        assert result.success is False

    def test_decrypt_for_signing(self, cryptowallet_skill):
        """서명용 복호화 테스트"""
        fake_key = "c" * 88
        encrypted = cryptowallet_skill._encryption.encrypt(fake_key)
        decrypted = cryptowallet_skill.decrypt_for_signing(encrypted)
        assert decrypted == fake_key


# ──────────────────────────────────────────────────────────────────────────────
# SelfOptimizerSkill 테스트
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def self_optimizer_skill():
    jito = JitoBribeSkill(default_tip_sol=0.001, max_tip_sol=0.05, increment_sol=0.005)
    return SelfOptimizerSkill(
        jito_skill=jito,
        window_size=5,
        slippage_increment_bps=200,
        initial_slippage_bps=1500,
        max_slippage_bps=2500,
    )


class TestSelfOptimizerSkill:
    def test_tool_definition(self, self_optimizer_skill):
        defn = self_optimizer_skill.as_tool_definition()
        assert defn["name"] == "self_optimizer"

    @pytest.mark.asyncio
    async def test_record_trade(self, self_optimizer_skill):
        result = await self_optimizer_skill.execute(
            action="record_trade", success=True, pnl_pct=25.0
        )
        assert result.success is True
        assert result.data["total_trades"] == 1

    @pytest.mark.asyncio
    async def test_optimization_not_triggered_insufficient_data(self, self_optimizer_skill):
        """데이터 부족 시 최적화 건너뜀"""
        result = await self_optimizer_skill.execute(action="run_optimization")
        assert result.success is True
        assert result.data["optimized"] is False

    @pytest.mark.asyncio
    async def test_optimization_increases_slippage_on_errors(self, self_optimizer_skill):
        """슬리피지 에러 빈발 시 슬리피지 증가"""
        # 5개 거래 중 2개 슬리피지 에러 (40%)
        for i in range(5):
            await self_optimizer_skill.execute(
                action="record_trade",
                success=i >= 2,
                slippage_exceeded=(i < 2),
            )
        old_slippage = self_optimizer_skill.current_slippage_bps
        result = await self_optimizer_skill.execute(action="run_optimization")
        assert result.success is True
        assert self_optimizer_skill.current_slippage_bps > old_slippage

    @pytest.mark.asyncio
    async def test_slippage_capped_at_max(self, self_optimizer_skill):
        """슬리피지 최대치 초과하지 않음"""
        self_optimizer_skill.current_slippage_bps = 2400
        for _ in range(5):
            await self_optimizer_skill.execute(
                action="record_trade", success=False, slippage_exceeded=True
            )
        await self_optimizer_skill.execute(action="run_optimization")
        assert self_optimizer_skill.current_slippage_bps <= self_optimizer_skill.max_slippage_bps

    @pytest.mark.asyncio
    async def test_get_current_settings(self, self_optimizer_skill):
        result = await self_optimizer_skill.execute(action="get_current_settings")
        assert result.success is True
        assert "slippage_bps" in result.data
        assert result.data["slippage_bps"] == 1500

    @pytest.mark.asyncio
    async def test_get_trade_summary_empty(self, self_optimizer_skill):
        result = await self_optimizer_skill.execute(action="get_trade_summary")
        assert result.success is True
        assert result.data["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_get_trade_summary_with_data(self, self_optimizer_skill):
        await self_optimizer_skill.execute(action="record_trade", success=True, pnl_pct=30.0)
        await self_optimizer_skill.execute(action="record_trade", success=False, pnl_pct=-15.0)
        result = await self_optimizer_skill.execute(action="get_trade_summary")
        assert result.data["total_trades"] == 2
        assert result.data["total_success"] == 1
        assert result.data["success_rate_pct"] == 50.0


# ──────────────────────────────────────────────────────────────────────────────
# RiskGuardSkill 업그레이드 테스트 (킬스위치)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def aggressive_risk_guard():
    return RiskGuardSkill(
        risk_config=_AGGRESSIVE_RISK_CONFIG,
        max_single_trade_usd=500.0,
        daily_loss_limit_usd=200.0,
        kill_switch_pct=20.0,
        stop_loss_pct=15.0,
        take_profit_1_pct=30.0,
        trailing_stop_pct=5.0,
    )


class TestRiskGuardUpgrades:
    @pytest.mark.asyncio
    async def test_kill_switch_not_active_initially(self, aggressive_risk_guard):
        result = await aggressive_risk_guard.execute(
            action="check_kill_switch", account_balance_usd=1000.0
        )
        assert result.success is True
        assert result.data["kill_switch_active"] is False

    @pytest.mark.asyncio
    async def test_kill_switch_triggers_on_20pct_loss(self, aggressive_risk_guard):
        aggressive_risk_guard._initial_account_balance = 1000.0
        result = await aggressive_risk_guard.execute(
            action="check_kill_switch", account_balance_usd=795.0  # -20.5%
        )
        assert result.success is False
        assert result.data["kill_switch_active"] is True
        assert result.data["loss_pct"] == pytest.approx(20.5, rel=0.01)

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_trade(self, aggressive_risk_guard):
        """킬스위치 발동 시 거래 차단"""
        aggressive_risk_guard._kill_switch_triggered = True
        aggressive_risk_guard._kill_switch_triggered_at = datetime.now(timezone.utc)

        result = await aggressive_risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=10.0,
            account_balance_usd=800.0,
            price_impact_pct=0.1,
            market_quality="GOOD",
        )
        assert result.success is False
        assert result.data["kill_switch_active"] is True

    @pytest.mark.asyncio
    async def test_kill_switch_auto_releases_after_24h(self, aggressive_risk_guard):
        """24시간 경과 후 킬스위치 자동 해제"""
        aggressive_risk_guard._kill_switch_triggered = True
        # 25시간 전으로 설정
        aggressive_risk_guard._kill_switch_triggered_at = (
            datetime.now(timezone.utc) - timedelta(hours=25)
        )
        result = await aggressive_risk_guard.execute(
            action="check_kill_switch", account_balance_usd=800.0
        )
        assert result.success is True
        assert result.data["kill_switch_active"] is False

    @pytest.mark.asyncio
    async def test_reset_kill_switch(self, aggressive_risk_guard):
        aggressive_risk_guard._kill_switch_triggered = True
        aggressive_risk_guard._kill_switch_triggered_at = datetime.now(timezone.utc)
        aggressive_risk_guard._daily_realized_loss_usd = 150.0

        result = await aggressive_risk_guard.execute(action="reset_kill_switch")
        assert result.success is True
        assert aggressive_risk_guard._kill_switch_triggered is False
        assert aggressive_risk_guard._daily_realized_loss_usd == 0.0

    @pytest.mark.asyncio
    async def test_get_limits_includes_new_fields(self, aggressive_risk_guard):
        result = await aggressive_risk_guard.execute(action="get_limits")
        assert result.success is True
        assert "stop_loss_pct" in result.data
        assert "take_profit_1_pct" in result.data
        assert "trailing_stop_pct" in result.data
        assert "kill_switch_pct" in result.data
        assert result.data["stop_loss_pct"] == 15.0
        assert result.data["take_profit_1_pct"] == 30.0
        assert result.data["kill_switch_pct"] == 20.0

    @pytest.mark.asyncio
    async def test_aggressive_risk_config_allows_higher_impact(self, aggressive_risk_guard):
        """공격적 전략: 가격 충격 3% 이하 허용 (기존 2%)"""
        result = await aggressive_risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=50.0,
            account_balance_usd=1000.0,
            price_impact_pct=2.5,  # 2.5% — 기존 시스템에선 거부, 새 시스템에선 통과
            market_quality="GOOD",
        )
        assert result.success is True  # 3% 미만이므로 통과

    @pytest.mark.asyncio
    async def test_aggressive_risk_config_blocks_above_3pct(self, aggressive_risk_guard):
        """3% 초과 가격 충격 차단"""
        result = await aggressive_risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=50.0,
            account_balance_usd=1000.0,
            price_impact_pct=3.5,
            market_quality="GOOD",
        )
        assert result.success is False


# ──────────────────────────────────────────────────────────────────────────────
# HeartbeatScheduler 테스트
# ──────────────────────────────────────────────────────────────────────────────

class TestHeartbeatScheduler:
    @pytest.mark.asyncio
    async def test_scheduler_starts_and_stops(self):
        scheduler = HeartbeatScheduler(interval_seconds=1000)
        await scheduler.start()
        assert scheduler.is_running is True
        await scheduler.stop()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_scheduler_executes_callback(self):
        """콜백이 정상적으로 호출되는지 확인"""
        call_count = 0

        async def my_callback():
            nonlocal call_count
            call_count += 1

        # interval=0으로 설정하고 _tick을 직접 호출하여 콜백 실행 검증
        scheduler = HeartbeatScheduler(interval_seconds=120)
        scheduler.register(my_callback)
        await scheduler._tick()
        assert call_count == 1

    def test_stats_initial(self):
        scheduler = HeartbeatScheduler(interval_seconds=120)
        stats = scheduler.stats
        assert stats["running"] is False
        assert stats["tick_count"] == 0
        assert stats["interval_seconds"] == 120

    def test_register_callback(self):
        scheduler = HeartbeatScheduler()

        async def cb1():
            pass

        async def cb2():
            pass

        scheduler.register(cb1)
        scheduler.register(cb2)
        assert scheduler.stats["callbacks_registered"] == 2

    @pytest.mark.asyncio
    async def test_kill_switch_exception_stops_tick(self):
        """킬스위치 예외 발생 시 해당 틱의 나머지 콜백 중단"""
        executed = []

        async def cb1():
            raise KillSwitchException("킬스위치!")

        async def cb2():
            executed.append("cb2")  # 실행되면 안 됨

        scheduler = HeartbeatScheduler(interval_seconds=1000)
        scheduler.register(cb1)
        scheduler.register(cb2)
        await scheduler._tick()
        # cb1에서 KillSwitchException 발생 → cb2는 실행되지 않아야 함
        assert "cb2" not in executed

    @pytest.mark.asyncio
    async def test_regular_exception_continues_to_next_callback(self):
        """일반 예외는 다음 콜백을 계속 실행"""
        executed = []

        async def cb1():
            raise ValueError("일반 오류")

        async def cb2():
            executed.append("cb2")

        scheduler = HeartbeatScheduler(interval_seconds=1000)
        scheduler.register(cb1)
        scheduler.register(cb2)
        await scheduler._tick()
        assert "cb2" in executed


# ──────────────────────────────────────────────────────────────────────────────
# SniperHeartbeat 테스트
# ──────────────────────────────────────────────────────────────────────────────

class TestSniperHeartbeat:
    def _make_mock_agent(self):
        agent = AsyncMock()
        agent.run = AsyncMock(return_value=MagicMock(
            success=True, message="테스트 완료", actions_taken=[]
        ))
        return agent

    def test_register_position(self):
        agent = self._make_mock_agent()
        hb = SniperHeartbeat(agent=agent, interval_seconds=120)
        hb.register_position(
            mint="mint123",
            entry_price_sol=1.0,
            quantity=100.0,
            stop_loss_sol=0.85,
            take_profit_1_sol=1.30,
        )
        assert "mint123" in hb._positions
        pos = hb._positions["mint123"]
        assert pos["entry_price_sol"] == 1.0
        assert pos["stop_loss_sol"] == 0.85

    def test_close_position(self):
        agent = self._make_mock_agent()
        hb = SniperHeartbeat(agent=agent)
        hb.register_position("mint_abc", 1.0, 100, 0.85, 1.30)
        assert "mint_abc" in hb._positions
        hb.close_position("mint_abc")
        assert "mint_abc" not in hb._positions

    @pytest.mark.asyncio
    async def test_step1_scan_tokens(self):
        agent = self._make_mock_agent()
        hb = SniperHeartbeat(agent=agent)
        await hb._step1_scan_tokens()
        agent.run.assert_called_once()
        call_args = agent.run.call_args[0][0]
        assert "Pump.fun" in call_args

    @pytest.mark.asyncio
    async def test_step2_skips_if_no_positions(self):
        agent = self._make_mock_agent()
        hb = SniperHeartbeat(agent=agent)
        await hb._step2_manage_positions()
        agent.run.assert_not_called()  # 포지션 없으면 에이전트 호출 안 함

    @pytest.mark.asyncio
    async def test_step2_calls_agent_with_positions(self):
        agent = self._make_mock_agent()
        hb = SniperHeartbeat(agent=agent)
        hb.register_position("mint1", 1.0, 100, 0.85, 1.30)
        await hb._step2_manage_positions()
        agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_step3_only_runs_every_5_cycles(self):
        agent = self._make_mock_agent()
        hb = SniperHeartbeat(agent=agent)
        hb._cycle_count = 0
        # 5번 호출 — 5번째 호출에서만 에이전트 실행 (cycle_count가 5가 될 때)
        for _ in range(5):
            await hb._step3_self_optimize()
        # 딱 1번만 호출되어야 함 (cycle_count=5 일 때)
        assert agent.run.call_count == 1


# ──────────────────────────────────────────────────────────────────────────────
# OpenClawAgent 새 스킬 통합 테스트
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenClawAgentNewSkills:
    @pytest.fixture
    def mock_jupiter_client(self):
        client = AsyncMock()
        client.get_token_price_usdc = AsyncMock(return_value=Decimal("150.0"))
        client.estimate_swap_output = AsyncMock(return_value={
            "input_amount": Decimal("10"),
            "output_amount": Decimal("0.0666"),
            "price_impact_pct": 0.05,
            "slippage_bps": 50,
            "route_plan": [],
        })
        return client

    @pytest.fixture
    def mock_solana_client(self):
        client = AsyncMock()
        client.get_balance = AsyncMock(return_value=5.0)
        client.get_token_accounts_by_owner = AsyncMock(return_value=[])
        return client

    def test_agent_registers_all_new_skills(
        self, mock_jupiter_client, mock_solana_client
    ):
        from src.agents.openclaw_agent import OpenClawAgent
        from src.agents.skills.market_analysis_skill import MarketAnalysisSkill
        from src.agents.skills.trade_executor_skill import TradeExecutorSkill
        from src.agents.skills.portfolio_tracker_skill import PortfolioTrackerSkill

        jito = JitoBribeSkill()
        with patch("src.agents.openclaw_agent.AsyncAnthropic"):
            agent = OpenClawAgent(
                anthropic_api_key="test-key",
                market_analysis_skill=MarketAnalysisSkill(mock_jupiter_client),
                risk_guard_skill=RiskGuardSkill(kill_switch_pct=20.0),
                trade_executor_skill=TradeExecutorSkill(
                    mock_solana_client, mock_jupiter_client, dry_run=True
                ),
                portfolio_tracker_skill=PortfolioTrackerSkill(
                    mock_solana_client, mock_jupiter_client
                ),
                pump_fun_skill=PumpFunSkill(),
                jito_bribe_skill=jito,
                cryptowallet_skill=CryptoWalletSkill("test-master-key-32chars!!"),
                self_optimizer_skill=SelfOptimizerSkill(jito),
            )

        assert "pump_fun" in agent.skills
        assert "jito_bribe" in agent.skills
        assert "cryptowallet" in agent.skills
        assert "self_optimizer" in agent.skills
        assert len(agent.skills) == 8

    def test_agent_max_tool_rounds_increased(
        self, mock_jupiter_client, mock_solana_client
    ):
        from src.agents.openclaw_agent import OpenClawAgent
        from src.agents.skills.market_analysis_skill import MarketAnalysisSkill
        from src.agents.skills.trade_executor_skill import TradeExecutorSkill
        from src.agents.skills.portfolio_tracker_skill import PortfolioTrackerSkill

        with patch("src.agents.openclaw_agent.AsyncAnthropic"):
            agent = OpenClawAgent(
                anthropic_api_key="test-key",
                market_analysis_skill=MarketAnalysisSkill(mock_jupiter_client),
                risk_guard_skill=RiskGuardSkill(),
                trade_executor_skill=TradeExecutorSkill(
                    mock_solana_client, mock_jupiter_client, dry_run=True
                ),
                portfolio_tracker_skill=PortfolioTrackerSkill(
                    mock_solana_client, mock_jupiter_client
                ),
            )
        # 기본값 15로 증가
        assert agent.max_tool_rounds == 15
