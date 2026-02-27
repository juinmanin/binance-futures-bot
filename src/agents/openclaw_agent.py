"""
OpenClaw AI 에이전트 — Claude claude-sonnet-4-5 기반 솔라나 자동 수익화 봇

에이전트 아키텍처:
- Claude AI가 두뇌 역할을 수행하며 시장 상황을 분석하고 거래 결정을 내립니다.
- 각 스킬은 Claude의 tool_use 기능을 통해 호출됩니다.
- 모든 거래는 RiskGuardSkill을 통해 사전 검증됩니다.

안전 원칙:
1. dry_run=True 기본값으로 실제 거래 없이 시뮬레이션
2. 모든 거래는 리스크 검증 통과 후에만 실행
3. 일일 손실 한도 초과 시 자동 거래 중단
4. API 키 및 개인키는 환경 변수로만 관리
"""
import json
from typing import Any, Dict, List, Optional
from loguru import logger

try:
    from anthropic import AsyncAnthropic
    from anthropic.types import (
        Message,
        TextBlock,
        ToolUseBlock,
    )
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    AsyncAnthropic = None  # type: ignore[assignment, misc]

from src.core.exceptions import AgentException
from .base_agent import BaseAgent, AgentResponse
from .skills.base_skill import BaseSkill, SkillResult
from .skills.market_analysis_skill import MarketAnalysisSkill
from .skills.risk_guard_skill import RiskGuardSkill
from .skills.trade_executor_skill import TradeExecutorSkill
from .skills.portfolio_tracker_skill import PortfolioTrackerSkill

_SYSTEM_PROMPT = """\
당신은 솔라나 네트워크에서 운영되는 안전하고 수익성 높은 자동 거래 에이전트입니다.

## 역할
- 솔라나 DEX(Jupiter)를 통해 토큰 스왑 기회를 분석하고 실행합니다.
- 항상 리스크 관리를 최우선으로 고려합니다.

## 의사결정 원칙
1. **안전 우선**: 모든 거래는 risk_guard 스킬로 사전 검증합니다.
2. **데이터 기반**: market_analysis 스킬로 실제 시장 데이터를 확인 후 결정합니다.
3. **포트폴리오 확인**: 거래 전 portfolio_tracker로 현재 잔액을 파악합니다.
4. **손실 제한**: 일일 손실 한도를 절대 초과하지 않습니다.
5. **유동성 확인**: 가격 충격(price impact) 1% 초과 시 거래를 보류합니다.

## 거래 판단 기준
- 시장 품질이 FAIR 이상일 때만 거래를 고려합니다.
- 슬리피지 허용치는 최대 0.5%(50 BPS)입니다.
- 단일 거래 금액은 설정된 한도를 초과하지 않습니다.

## 응답 형식
항상 한국어로 응답하며, 분석 근거와 결정 이유를 명확히 설명합니다.
거래를 실행하지 않는 경우에도 그 이유를 상세히 설명합니다.
"""


class OpenClawAgent(BaseAgent):
    """
    Claude claude-sonnet-4-5 기반 솔라나 자동 수익화 에이전트

    스킬 목록:
    - market_analysis: 시장 가격 및 유동성 분석
    - risk_guard: 거래 안전성 검증
    - trade_executor: DEX 스왑 실행
    - portfolio_tracker: 포트폴리오 잔액 추적
    """

    def __init__(
        self,
        anthropic_api_key: str,
        market_analysis_skill: MarketAnalysisSkill,
        risk_guard_skill: RiskGuardSkill,
        trade_executor_skill: TradeExecutorSkill,
        portfolio_tracker_skill: PortfolioTrackerSkill,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 4096,
        max_tool_rounds: int = 10,
    ):
        """
        초기화

        Args:
            anthropic_api_key: Anthropic API 키 (환경 변수에서 주입)
            market_analysis_skill: 시장 분석 스킬
            risk_guard_skill: 리스크 관리 스킬
            trade_executor_skill: 거래 실행 스킬
            portfolio_tracker_skill: 포트폴리오 추적 스킬
            model: Claude 모델 ID
            max_tokens: 최대 응답 토큰 수
            max_tool_rounds: 최대 도구 호출 라운드 수 (무한루프 방지)
        """
        super().__init__(
            name="openclaw",
            description="Claude claude-sonnet-4-5 기반 솔라나 자동 수익화 에이전트",
        )
        if not _ANTHROPIC_AVAILABLE:
            raise AgentException(
                "anthropic 패키지가 설치되어 있지 않습니다. "
                "`pip install anthropic>=0.39.0`으로 설치하세요."
            )
        if not anthropic_api_key:
            raise AgentException(
                "Anthropic API 키가 설정되어 있지 않습니다. "
                "ANTHROPIC_API_KEY 환경 변수를 설정하세요."
            )

        self._client = AsyncAnthropic(api_key=anthropic_api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds

        # 스킬 등록
        self._skills: Dict[str, BaseSkill] = {
            market_analysis_skill.name: market_analysis_skill,
            risk_guard_skill.name: risk_guard_skill,
            trade_executor_skill.name: trade_executor_skill,
            portfolio_tracker_skill.name: portfolio_tracker_skill,
        }

    @property
    def skills(self) -> Dict[str, BaseSkill]:
        """등록된 스킬 딕셔너리"""
        return self._skills

    def _build_tools(self) -> List[Dict[str, Any]]:
        """Claude tool_use 형식으로 스킬 정의 변환"""
        return [skill.as_tool_definition() for skill in self._skills.values()]

    async def _call_skill(self, name: str, inputs: Dict[str, Any]) -> SkillResult:
        """
        스킬 호출

        Args:
            name: 스킬 이름
            inputs: 스킬 입력 파라미터

        Returns:
            SkillResult
        """
        skill = self._skills.get(name)
        if skill is None:
            return SkillResult(
                success=False,
                message=f"등록되지 않은 스킬: {name}",
                errors=[f"스킬 '{name}'을 찾을 수 없습니다."],
            )
        logger.info(f"스킬 호출: {name}({list(inputs.keys())})")
        try:
            result = await skill.execute(**inputs)
            return result
        except Exception as e:
            logger.error(f"스킬 실행 오류 [{name}]: {e}")
            return SkillResult(
                success=False,
                message=f"스킬 실행 오류: {str(e)}",
                errors=[str(e)],
            )

    async def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """
        에이전트 작업 실행

        Claude가 주어진 task를 분석하고, 필요한 스킬을 순서대로 호출하며
        최종 응답을 생성합니다.

        Args:
            task: 수행할 작업 (예: "SOL 가격 분석 후 $10 매수 여부 결정")
            context: 추가 컨텍스트 (wallet_address 등)

        Returns:
            AgentResponse
        """
        if self._is_running:
            return AgentResponse(
                success=False,
                message="에이전트가 이미 실행 중입니다.",
                errors=["concurrent execution not allowed"],
            )

        self._is_running = True
        actions_taken: List[str] = []
        errors: List[str] = []

        try:
            # 컨텍스트를 task에 포함
            full_task = task
            if context:
                ctx_str = "\n".join(f"- {k}: {v}" for k, v in context.items())
                full_task = f"{task}\n\n[컨텍스트]\n{ctx_str}"

            messages: List[Dict[str, Any]] = [
                {"role": "user", "content": full_task}
            ]
            tools = self._build_tools()
            final_text = ""

            # 도구 호출 루프
            for round_num in range(self.max_tool_rounds):
                logger.info(f"Claude 호출 (라운드 {round_num + 1})")

                response: Message = await self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=_SYSTEM_PROMPT,
                    tools=tools,  # type: ignore[arg-type]
                    messages=messages,
                )

                # 응답 처리
                tool_calls: List[ToolUseBlock] = []
                text_parts: List[str] = []

                for block in response.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append(block)

                if text_parts:
                    final_text = " ".join(text_parts)

                # 도구 호출이 없으면 종료
                if response.stop_reason == "end_turn" or not tool_calls:
                    break

                # 도구 호출 결과 처리
                tool_results: List[Dict[str, Any]] = []
                for tool_call in tool_calls:
                    skill_result = await self._call_skill(
                        name=tool_call.name,
                        inputs=tool_call.input,  # type: ignore[arg-type]
                    )
                    action_desc = (
                        f"{tool_call.name}: "
                        f"{'성공' if skill_result.success else '실패'} — "
                        f"{skill_result.message}"
                    )
                    actions_taken.append(action_desc)
                    if not skill_result.success:
                        errors.extend(skill_result.errors)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": json.dumps(
                            {
                                "success": skill_result.success,
                                "message": skill_result.message,
                                "data": skill_result.data or {},
                                "errors": skill_result.errors,
                            },
                            ensure_ascii=False,
                        ),
                    })

                # 대화 히스토리 업데이트
                messages.append(
                    {"role": "assistant", "content": response.content}  # type: ignore[list-item]
                )
                messages.append(
                    {"role": "user", "content": tool_results}
                )
            else:
                logger.warning(
                    f"최대 도구 호출 라운드({self.max_tool_rounds})에 도달했습니다."
                )

            return AgentResponse(
                success=True,
                message=final_text or "작업이 완료되었습니다.",
                data={"rounds": round_num + 1},
                actions_taken=actions_taken,
                errors=errors,
            )

        except Exception as e:
            logger.error(f"에이전트 실행 오류: {e}")
            return AgentResponse(
                success=False,
                message=f"에이전트 오류: {str(e)}",
                errors=[str(e)],
                actions_taken=actions_taken,
            )
        finally:
            self._is_running = False
