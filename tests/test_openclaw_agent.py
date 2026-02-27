"""OpenClaw 에이전트 및 스킬 테스트"""
import pytest
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base_agent import AgentResponse, BaseAgent
from src.agents.skills.base_skill import BaseSkill, SkillResult
from src.agents.skills.risk_guard_skill import RiskGuardSkill, _DEFAULT_SOLANA_RISK_CONFIG
from src.agents.skills.market_analysis_skill import MarketAnalysisSkill
from src.agents.skills.trade_executor_skill import TradeExecutorSkill
from src.agents.skills.portfolio_tracker_skill import PortfolioTrackerSkill
from src.core.exceptions import (
    SolanaRPCException, JupiterAPIException, AgentException, SkillException
)


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_jupiter_client():
    """Jupiter 클라이언트 모킹"""
    client = AsyncMock()
    client.get_token_price_usdc = AsyncMock(return_value=Decimal("150.0"))
    client.estimate_swap_output = AsyncMock(return_value={
        "input_amount": Decimal("10"),
        "output_amount": Decimal("0.0666"),
        "price_impact_pct": 0.05,
        "slippage_bps": 50,
        "route_plan": [{"label": "Raydium"}],
    })
    client.get_quote = AsyncMock(return_value={
        "inAmount": "10000000",
        "outAmount": "66600000",
        "priceImpactPct": 0.05,
        "routePlan": [{"label": "Raydium"}],
    })
    client.get_swap_transaction = AsyncMock(return_value="dGVzdA==")  # b64 "test"
    client.resolve_mint = MagicMock(
        side_effect=lambda t: t if len(t) > 10 else f"mint_{t}"
    )
    return client


@pytest.fixture
def mock_solana_client():
    """솔라나 RPC 클라이언트 모킹"""
    client = AsyncMock()
    client.get_balance = AsyncMock(return_value=5.0)
    client.get_token_accounts_by_owner = AsyncMock(return_value=[])
    client.health_check = AsyncMock(return_value=True)
    client.send_raw_transaction = AsyncMock(return_value="sig123abc")
    client.confirm_transaction = AsyncMock(return_value=True)
    return client


@pytest.fixture
def risk_guard():
    """기본 RiskGuardSkill 인스턴스"""
    return RiskGuardSkill(
        max_single_trade_usd=100.0,
        daily_loss_limit_usd=50.0,
    )


@pytest.fixture
def market_analysis_skill(mock_jupiter_client):
    """MarketAnalysisSkill 인스턴스"""
    return MarketAnalysisSkill(jupiter_client=mock_jupiter_client)


@pytest.fixture
def trade_executor_skill(mock_solana_client, mock_jupiter_client):
    """TradeExecutorSkill 인스턴스 (dry_run=True)"""
    return TradeExecutorSkill(
        solana_client=mock_solana_client,
        jupiter_client=mock_jupiter_client,
        dry_run=True,
    )


@pytest.fixture
def portfolio_tracker_skill(mock_solana_client, mock_jupiter_client):
    """PortfolioTrackerSkill 인스턴스"""
    return PortfolioTrackerSkill(
        solana_client=mock_solana_client,
        jupiter_client=mock_jupiter_client,
    )


# ---------------------------------------------------------------------------
# 예외 클래스 테스트
# ---------------------------------------------------------------------------

class TestCustomExceptions:
    def test_solana_rpc_exception(self):
        err = SolanaRPCException("RPC 오류", details={"code": -32002})
        assert err.message == "RPC 오류"
        assert err.details == {"code": -32002}

    def test_jupiter_api_exception(self):
        err = JupiterAPIException("Jupiter 오류")
        assert "Jupiter" in err.message

    def test_agent_exception(self):
        err = AgentException("에이전트 오류")
        assert err.message == "에이전트 오류"

    def test_skill_exception(self):
        err = SkillException("스킬 오류")
        assert err.message == "스킬 오류"


# ---------------------------------------------------------------------------
# SkillResult 테스트
# ---------------------------------------------------------------------------

class TestSkillResult:
    def test_success_result(self):
        result = SkillResult(success=True, message="완료", data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.errors == []

    def test_failure_result(self):
        result = SkillResult(
            success=False,
            message="실패",
            errors=["오류1", "오류2"]
        )
        assert result.success is False
        assert len(result.errors) == 2


# ---------------------------------------------------------------------------
# BaseSkill 추상 클래스 테스트
# ---------------------------------------------------------------------------

class ConcreteSkill(BaseSkill):
    def as_tool_definition(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": {}}

    async def execute(self, **kwargs: Any) -> SkillResult:
        return SkillResult(success=True, message="실행 완료")


class TestBaseSkill:
    def test_repr(self):
        skill = ConcreteSkill("test_skill", "테스트 스킬")
        assert "ConcreteSkill" in repr(skill)
        assert "test_skill" in repr(skill)

    def test_tool_definition(self):
        skill = ConcreteSkill("test_skill", "테스트 스킬")
        defn = skill.as_tool_definition()
        assert defn["name"] == "test_skill"


# ---------------------------------------------------------------------------
# RiskGuardSkill 테스트
# ---------------------------------------------------------------------------

class TestRiskGuardSkill:
    def test_tool_definition(self, risk_guard):
        defn = risk_guard.as_tool_definition()
        assert defn["name"] == "risk_guard"
        assert "input_schema" in defn
        actions = defn["input_schema"]["properties"]["action"]["enum"]
        assert "validate_trade" in actions
        assert "calculate_position_size" in actions
        assert "get_limits" in actions

    @pytest.mark.asyncio
    async def test_validate_trade_passes(self, risk_guard):
        result = await risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=50.0,
            account_balance_usd=1000.0,
            price_impact_pct=0.1,
            market_quality="GOOD",
        )
        assert result.success is True
        assert result.data["is_valid"] is True

    @pytest.mark.asyncio
    async def test_validate_trade_exceeds_single_limit(self, risk_guard):
        result = await risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=200.0,  # 한도 100 초과
            account_balance_usd=1000.0,
            price_impact_pct=0.1,
            market_quality="GOOD",
        )
        assert result.success is False
        assert result.data["is_valid"] is False
        assert any("단일 거래 한도" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_trade_high_price_impact(self, risk_guard):
        result = await risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=10.0,
            account_balance_usd=1000.0,
            price_impact_pct=3.0,  # 2% 초과
            market_quality="POOR",
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_calculate_position_size(self, risk_guard):
        result = await risk_guard.execute(
            action="calculate_position_size",
            account_balance_usd=1000.0,
            entry_price=150.0,
            stop_loss_price=140.0,
        )
        assert result.success is True
        assert result.data["position_size"] > 0
        assert result.data["position_usd"] <= 100.0  # 단일 거래 한도 적용

    @pytest.mark.asyncio
    async def test_calculate_position_size_invalid_prices(self, risk_guard):
        result = await risk_guard.execute(
            action="calculate_position_size",
            account_balance_usd=1000.0,
            entry_price=0.0,
            stop_loss_price=140.0,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_get_limits(self, risk_guard):
        result = await risk_guard.execute(action="get_limits")
        assert result.success is True
        assert "max_single_trade_usd" in result.data
        assert result.data["max_single_trade_usd"] == 100.0
        assert result.data["daily_loss_limit_usd"] == 50.0

    @pytest.mark.asyncio
    async def test_unknown_action(self, risk_guard):
        result = await risk_guard.execute(action="unknown_action")
        assert result.success is False

    def test_record_and_reset_loss(self, risk_guard):
        risk_guard.record_loss(20.0)
        assert risk_guard._daily_realized_loss_usd == 20.0
        risk_guard.record_loss(15.0)
        assert risk_guard._daily_realized_loss_usd == 35.0
        risk_guard.reset_daily_loss()
        assert risk_guard._daily_realized_loss_usd == 0.0

    @pytest.mark.asyncio
    async def test_daily_loss_limit_reached(self, risk_guard):
        risk_guard._daily_realized_loss_usd = 50.0  # 한도에 도달
        result = await risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=10.0,
            account_balance_usd=1000.0,
            price_impact_pct=0.1,
            market_quality="GOOD",
        )
        # 일일 한도 초과 시 실패
        assert result.success is False

    @pytest.mark.asyncio
    async def test_poor_market_quality_rejected(self, risk_guard):
        result = await risk_guard.execute(
            action="validate_trade",
            trade_amount_usd=10.0,
            account_balance_usd=1000.0,
            price_impact_pct=0.1,
            market_quality="POOR",
        )
        assert result.success is False
        assert any("POOR" in e for e in result.errors)


# ---------------------------------------------------------------------------
# MarketAnalysisSkill 테스트
# ---------------------------------------------------------------------------

class TestMarketAnalysisSkill:
    def test_tool_definition(self, market_analysis_skill):
        defn = market_analysis_skill.as_tool_definition()
        assert defn["name"] == "market_analysis"
        assert "token" in defn["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_analyze_token_success(self, market_analysis_skill):
        result = await market_analysis_skill.execute(
            token="SOL", trade_amount_usdc=10.0
        )
        assert result.success is True
        assert result.data["price_usdc"] == 150.0
        assert "market_quality" in result.data

    @pytest.mark.asyncio
    async def test_analyze_token_price_failure(self, market_analysis_skill, mock_jupiter_client):
        mock_jupiter_client.get_token_price_usdc = AsyncMock(return_value=None)
        result = await market_analysis_skill.execute(token="UNKNOWN_TOKEN")
        assert result.success is False

    def test_assess_market_quality(self, market_analysis_skill):
        assert market_analysis_skill._assess_market_quality(0.05) == "EXCELLENT"
        assert market_analysis_skill._assess_market_quality(0.3) == "GOOD"
        assert market_analysis_skill._assess_market_quality(0.7) == "FAIR"
        assert market_analysis_skill._assess_market_quality(2.0) == "POOR"

    def test_compute_simple_indicators(self):
        import random
        prices = [100.0 + i + random.uniform(-1, 1) for i in range(60)]
        indicators = MarketAnalysisSkill.compute_simple_indicators(prices)
        assert "sma_20" in indicators
        assert "sma_50" in indicators
        assert "rsi_14" in indicators
        assert 0 <= indicators["rsi_14"] <= 100

    def test_compute_simple_indicators_insufficient_data(self):
        prices = [100.0, 101.0, 102.0]
        indicators = MarketAnalysisSkill.compute_simple_indicators(prices)
        assert "sma_20" not in indicators
        assert "rsi_14" not in indicators


# ---------------------------------------------------------------------------
# TradeExecutorSkill 테스트
# ---------------------------------------------------------------------------

class TestTradeExecutorSkill:
    def test_tool_definition(self, trade_executor_skill):
        defn = trade_executor_skill.as_tool_definition()
        assert defn["name"] == "trade_executor"
        actions = defn["input_schema"]["properties"]["action"]["enum"]
        assert "estimate" in actions
        assert "execute" in actions

    def test_dry_run_mode_is_default(self, trade_executor_skill):
        assert trade_executor_skill.dry_run is True

    def test_create_without_key_in_live_mode_raises(
        self, mock_solana_client, mock_jupiter_client
    ):
        with pytest.raises(SkillException):
            TradeExecutorSkill(
                solana_client=mock_solana_client,
                jupiter_client=mock_jupiter_client,
                wallet_private_key_b58="",
                dry_run=False,  # live mode without key
            )

    @pytest.mark.asyncio
    async def test_estimate_swap(self, trade_executor_skill):
        result = await trade_executor_skill.execute(
            action="estimate",
            input_token="USDC",
            output_token="SOL",
            amount_ui=10.0,
            input_decimals=6,
            output_decimals=9,
        )
        assert result.success is True
        assert "output_amount" in result.data
        assert result.data["dry_run"] is True

    @pytest.mark.asyncio
    async def test_execute_swap_in_dry_run(self, trade_executor_skill):
        """dry_run=True 시 실제 트랜잭션 없이 시뮬레이션"""
        result = await trade_executor_skill.execute(
            action="execute",
            input_token="USDC",
            output_token="SOL",
            amount_ui=10.0,
            wallet_address="some_wallet_address",
        )
        assert result.success is True
        assert result.data["tx_signature"] == "DRY_RUN_NO_TRANSACTION"
        assert result.data["dry_run"] is True

    @pytest.mark.asyncio
    async def test_unknown_action(self, trade_executor_skill):
        result = await trade_executor_skill.execute(
            action="unknown",
            input_token="USDC",
            output_token="SOL",
            amount_ui=10.0,
        )
        assert result.success is False


# ---------------------------------------------------------------------------
# PortfolioTrackerSkill 테스트
# ---------------------------------------------------------------------------

class TestPortfolioTrackerSkill:
    def test_tool_definition(self, portfolio_tracker_skill):
        defn = portfolio_tracker_skill.as_tool_definition()
        assert defn["name"] == "portfolio_tracker"
        assert "wallet_address" in defn["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_get_portfolio_success(self, portfolio_tracker_skill):
        result = await portfolio_tracker_skill.execute(
            wallet_address="11111111111111111111111111111111",
            include_prices=True,
        )
        assert result.success is True
        assert "tokens" in result.data
        assert result.data["wallet_address"] == "11111111111111111111111111111111"
        # SOL은 항상 포함됨
        sol_tokens = [t for t in result.data["tokens"] if t["symbol"] == "SOL"]
        assert len(sol_tokens) == 1
        assert sol_tokens[0]["balance"] == 5.0

    @pytest.mark.asyncio
    async def test_get_portfolio_no_address(self, portfolio_tracker_skill):
        result = await portfolio_tracker_skill.execute(wallet_address="")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_get_portfolio_without_prices(
        self, portfolio_tracker_skill, mock_solana_client
    ):
        result = await portfolio_tracker_skill.execute(
            wallet_address="11111111111111111111111111111111",
            include_prices=False,
        )
        assert result.success is True
        sol_tokens = [t for t in result.data["tokens"] if t["symbol"] == "SOL"]
        assert "price_usdc" not in sol_tokens[0]

    @pytest.mark.asyncio
    async def test_get_portfolio_rpc_error(
        self, portfolio_tracker_skill, mock_solana_client
    ):
        mock_solana_client.get_balance = AsyncMock(
            side_effect=SolanaRPCException("RPC 연결 실패")
        )
        result = await portfolio_tracker_skill.execute(
            wallet_address="11111111111111111111111111111111"
        )
        assert result.success is False


# ---------------------------------------------------------------------------
# AgentResponse 테스트
# ---------------------------------------------------------------------------

class TestAgentResponse:
    def test_success_response(self):
        resp = AgentResponse(
            success=True,
            message="분석 완료",
            actions_taken=["market_analysis: 성공"],
        )
        assert resp.success is True
        assert len(resp.actions_taken) == 1
        assert resp.errors == []

    def test_failure_response(self):
        resp = AgentResponse(
            success=False,
            message="실패",
            errors=["오류 발생"],
        )
        assert resp.success is False


# ---------------------------------------------------------------------------
# OpenClawAgent 테스트 (Claude API 모킹)
# ---------------------------------------------------------------------------

class TestOpenClawAgent:
    """OpenClawAgent는 anthropic SDK를 모킹하여 테스트합니다."""

    def _make_agent(
        self,
        market_analysis_skill,
        risk_guard,
        trade_executor_skill,
        portfolio_tracker_skill,
    ):
        from src.agents.openclaw_agent import OpenClawAgent
        return OpenClawAgent(
            anthropic_api_key="test-key",
            market_analysis_skill=market_analysis_skill,
            risk_guard_skill=risk_guard,
            trade_executor_skill=trade_executor_skill,
            portfolio_tracker_skill=portfolio_tracker_skill,
        )

    def test_skills_registered(
        self,
        market_analysis_skill,
        risk_guard,
        trade_executor_skill,
        portfolio_tracker_skill,
    ):
        agent = self._make_agent(
            market_analysis_skill, risk_guard,
            trade_executor_skill, portfolio_tracker_skill
        )
        assert "market_analysis" in agent.skills
        assert "risk_guard" in agent.skills
        assert "trade_executor" in agent.skills
        assert "portfolio_tracker" in agent.skills

    def test_build_tools_returns_list(
        self,
        market_analysis_skill,
        risk_guard,
        trade_executor_skill,
        portfolio_tracker_skill,
    ):
        agent = self._make_agent(
            market_analysis_skill, risk_guard,
            trade_executor_skill, portfolio_tracker_skill
        )
        tools = agent._build_tools()
        assert len(tools) == 4
        names = [t["name"] for t in tools]
        assert "market_analysis" in names
        assert "risk_guard" in names

    @pytest.mark.asyncio
    async def test_run_with_mocked_claude(
        self,
        market_analysis_skill,
        risk_guard,
        trade_executor_skill,
        portfolio_tracker_skill,
    ):
        """Claude API를 모킹하여 에이전트 실행 흐름 테스트"""
        from src.agents.openclaw_agent import OpenClawAgent

        # Claude 응답 모킹
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(spec=["text"], text="분석 완료: SOL 매수 추천")]

        # TextBlock으로 만들어야 함
        from anthropic.types import TextBlock
        mock_response.content = [TextBlock(type="text", text="분석 완료: SOL 매수 추천")]

        with patch("src.agents.openclaw_agent.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockAnthropic.return_value = mock_client

            agent = OpenClawAgent(
                anthropic_api_key="test-key",
                market_analysis_skill=market_analysis_skill,
                risk_guard_skill=risk_guard,
                trade_executor_skill=trade_executor_skill,
                portfolio_tracker_skill=portfolio_tracker_skill,
            )
            result = await agent.run("SOL 현재 가격을 분석해주세요.")

        assert result.success is True
        assert "분석 완료" in result.message

    @pytest.mark.asyncio
    async def test_no_concurrent_execution(
        self,
        market_analysis_skill,
        risk_guard,
        trade_executor_skill,
        portfolio_tracker_skill,
    ):
        """동시 실행 방지 테스트"""
        from src.agents.openclaw_agent import OpenClawAgent

        with patch("src.agents.openclaw_agent.AsyncAnthropic"):
            agent = OpenClawAgent(
                anthropic_api_key="test-key",
                market_analysis_skill=market_analysis_skill,
                risk_guard_skill=risk_guard,
                trade_executor_skill=trade_executor_skill,
                portfolio_tracker_skill=portfolio_tracker_skill,
            )
            agent._is_running = True  # 이미 실행 중으로 설정
            result = await agent.run("테스트")

        assert result.success is False
        assert "이미 실행 중" in result.message

    def test_missing_api_key_raises(
        self,
        market_analysis_skill,
        risk_guard,
        trade_executor_skill,
        portfolio_tracker_skill,
    ):
        from src.agents.openclaw_agent import OpenClawAgent
        with pytest.raises(AgentException, match="API 키"):
            OpenClawAgent(
                anthropic_api_key="",  # 빈 키
                market_analysis_skill=market_analysis_skill,
                risk_guard_skill=risk_guard,
                trade_executor_skill=trade_executor_skill,
                portfolio_tracker_skill=portfolio_tracker_skill,
            )


# ---------------------------------------------------------------------------
# SolanaRPCClient 테스트
# ---------------------------------------------------------------------------

class TestSolanaRPCClient:
    @pytest.mark.asyncio
    async def test_rpc_error_handling(self):
        from src.services.solana.rpc_client import SolanaRPCClient
        client = SolanaRPCClient(rpc_url="http://invalid-rpc.example.com")

        with patch.object(
            client._client, "post",
            side_effect=Exception("연결 거부")
        ):
            with pytest.raises(SolanaRPCException):
                await client._call("getSlot")

        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self):
        from src.services.solana.rpc_client import SolanaRPCClient
        client = SolanaRPCClient()

        with patch.object(
            client, "get_slot",
            side_effect=SolanaRPCException("연결 실패")
        ):
            result = await client.health_check()
        assert result is False

        await client.close()

    @pytest.mark.asyncio
    async def test_get_balance_returns_sol_amount(self):
        from src.services.solana.rpc_client import SolanaRPCClient
        client = SolanaRPCClient()

        with patch.object(
            client, "_call",
            return_value={"value": 5_000_000_000}  # 5 SOL
        ):
            balance = await client.get_balance("some_address")
        assert balance == 5.0

        await client.close()

    @pytest.mark.asyncio
    async def test_rpc_error_in_response_raises(self):
        from src.services.solana.rpc_client import SolanaRPCClient
        import httpx

        client = SolanaRPCClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32002, "message": "제한 초과"},
        })

        with patch.object(client._client, "post", return_value=mock_resp):
            with pytest.raises(SolanaRPCException, match="제한 초과"):
                await client._call("getBalance", ["address"])

        await client.close()


# ---------------------------------------------------------------------------
# JupiterClient 테스트
# ---------------------------------------------------------------------------

class TestJupiterClient:
    def test_resolve_known_token(self):
        from src.services.solana.jupiter_client import JupiterClient, KNOWN_TOKENS
        client = JupiterClient()
        assert client.resolve_mint("SOL") == KNOWN_TOKENS["SOL"]
        assert client.resolve_mint("USDC") == KNOWN_TOKENS["USDC"]

    def test_resolve_unknown_token_returns_as_is(self):
        from src.services.solana.jupiter_client import JupiterClient
        client = JupiterClient()
        custom_mint = "CustomMint123456789"
        assert client.resolve_mint(custom_mint) == custom_mint

    @pytest.mark.asyncio
    async def test_get_quote_zero_amount_raises(self):
        from src.services.solana.jupiter_client import JupiterClient
        client = JupiterClient()
        with pytest.raises(JupiterAPIException, match="0보다"):
            await client.get_quote("SOL", "USDC", Decimal("0"))
        await client.close()

    @pytest.mark.asyncio
    async def test_get_token_price_returns_none_on_failure(self):
        from src.services.solana.jupiter_client import JupiterClient
        client = JupiterClient()
        with patch.object(
            client, "get_quote",
            side_effect=JupiterAPIException("API 오류")
        ):
            price = await client.get_token_price_usdc("UNKNOWN")
        assert price is None
        await client.close()
