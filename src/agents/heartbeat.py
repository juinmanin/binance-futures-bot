"""
하트비트 — 2분 주기 시장 감시 루프

체크리스트 (2분 주기):
1. Pump.fun 신규 토큰 스캔
2. RugCheck 보안 필터링
3. 포지션 PnL 계산 및 손절/트레일링 스톱 실행
4. 자기 개선 (최근 5개 거래 분석)
5. 보고
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional
from loguru import logger

from src.core.exceptions import KillSwitchException


class HeartbeatScheduler:
    """
    주기적 감시 루프 스케줄러

    asyncio 기반으로 지정된 주기마다 콜백을 실행합니다.
    Termux/모바일 환경에서도 안정적으로 동작하도록 예외를 격리합니다.
    """

    Callback = Callable[[], Coroutine[Any, Any, None]]

    def __init__(
        self,
        interval_seconds: int = 120,
        max_consecutive_errors: int = 5,
    ):
        """
        초기화

        Args:
            interval_seconds: 실행 주기 (초, 기본 120 = 2분)
            max_consecutive_errors: 연속 허용 오류 수 (초과 시 루프 중단)
        """
        self.interval_seconds = interval_seconds
        self.max_consecutive_errors = max_consecutive_errors
        self._callbacks: List[HeartbeatScheduler.Callback] = []
        self._running = False
        self._tick_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        self._last_tick_at: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def register(self, callback: "HeartbeatScheduler.Callback") -> None:
        """
        감시 콜백 등록

        Args:
            callback: async 함수
        """
        self._callbacks.append(callback)
        logger.info(f"하트비트 콜백 등록: {callback.__name__}")

    async def start(self) -> None:
        """감시 루프 시작 (백그라운드 태스크)"""
        if self._running:
            logger.warning("하트비트 루프가 이미 실행 중입니다.")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="heartbeat_loop")
        logger.info(
            f"하트비트 시작: {self.interval_seconds}초 주기, "
            f"콜백 {len(self._callbacks)}개"
        )

    async def stop(self) -> None:
        """감시 루프 중단"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("하트비트 중단됨")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> Dict[str, Any]:
        """루프 통계"""
        return {
            "running": self._running,
            "tick_count": self._tick_count,
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "last_tick_at": (
                self._last_tick_at.isoformat() if self._last_tick_at else None
            ),
            "interval_seconds": self.interval_seconds,
            "callbacks_registered": len(self._callbacks),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """메인 감시 루프"""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"하트비트 루프 오류: {e}")
                self._error_count += 1
                self._consecutive_errors += 1
                if self._consecutive_errors >= self.max_consecutive_errors:
                    logger.critical(
                        f"연속 오류 {self._consecutive_errors}회 — 하트비트 중단"
                    )
                    self._running = False
                    break

    async def _tick(self) -> None:
        """단일 틱 실행 — 모든 콜백 순서대로 실행"""
        self._tick_count += 1
        self._last_tick_at = datetime.now(timezone.utc)
        logger.info(
            f"하트비트 틱 #{self._tick_count} "
            f"({self._last_tick_at.strftime('%H:%M:%S')} UTC)"
        )

        for callback in self._callbacks:
            try:
                await callback()
                self._consecutive_errors = 0  # 성공 시 연속 오류 카운터 초기화
            except KillSwitchException as e:
                logger.warning(f"킬스위치 발동으로 틱 중단: {e.message}")
                break
            except Exception as e:
                logger.error(f"하트비트 콜백 [{callback.__name__}] 오류: {e}")
                self._error_count += 1
                self._consecutive_errors += 1
                # 개별 콜백 오류는 계속 진행 (다음 콜백 실행)


class SniperHeartbeat:
    """
    Pump.fun 스나이퍼 하트비트

    2분마다 다음을 수행:
    1. Pump.fun 신규 토큰 스캔
    2. RugCheck 보안 필터링
    3. 포지션 PnL 계산 및 손절/트레일링 스톱 실행
    4. 자기 개선 루프
    5. 보고
    """

    def __init__(
        self,
        agent: Any,          # OpenClawAgent (순환 임포트 방지를 위해 Any)
        scheduler: Optional[HeartbeatScheduler] = None,
        interval_seconds: int = 120,
    ):
        """
        초기화

        Args:
            agent: OpenClawAgent 인스턴스
            scheduler: 기존 스케줄러 (없으면 새로 생성)
            interval_seconds: 실행 주기 (초)
        """
        self.agent = agent
        self.scheduler = scheduler or HeartbeatScheduler(interval_seconds)
        self._positions: Dict[str, Dict[str, Any]] = {}  # mint → position info
        self._cycle_count = 0

        # 체크리스트 콜백 등록
        self.scheduler.register(self._step1_scan_tokens)
        self.scheduler.register(self._step2_manage_positions)
        self.scheduler.register(self._step3_self_optimize)
        self.scheduler.register(self._step4_report)

    async def start(self) -> None:
        """하트비트 시작"""
        await self.scheduler.start()

    async def stop(self) -> None:
        """하트비트 중단"""
        await self.scheduler.stop()

    def register_position(
        self,
        mint: str,
        entry_price_sol: float,
        quantity: float,
        stop_loss_sol: float,
        take_profit_1_sol: float,
        trailing_stop_pct: float = 5.0,
    ) -> None:
        """
        포지션 등록 (매수 후 호출)

        Args:
            mint: 토큰 민트 주소
            entry_price_sol: 진입 가격 (SOL)
            quantity: 보유 수량
            stop_loss_sol: 손절 가격 (SOL)
            take_profit_1_sol: 1차 익절 가격 (SOL)
            trailing_stop_pct: 트레일링 스톱 비율 (%)
        """
        self._positions[mint] = {
            "mint": mint,
            "entry_price_sol": entry_price_sol,
            "quantity": quantity,
            "stop_loss_sol": stop_loss_sol,
            "take_profit_1_sol": take_profit_1_sol,
            "trailing_stop_pct": trailing_stop_pct,
            "peak_price_sol": entry_price_sol,
            "tp1_triggered": False,
            "trailing_active": False,
            "entered_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"포지션 등록: {mint[:8]}... @ {entry_price_sol:.6f} SOL")

    def close_position(self, mint: str) -> None:
        """포지션 제거"""
        if mint in self._positions:
            del self._positions[mint]
            logger.info(f"포지션 종료: {mint[:8]}...")

    # ──────────────────────────────────────────────────────────────────────────
    # 하트비트 단계
    # ──────────────────────────────────────────────────────────────────────────

    async def _step1_scan_tokens(self) -> None:
        """1단계: 신규 토큰 스캔 및 보안 필터"""
        task = (
            "Pump.fun 신규 토큰을 스캔하고 RugCheck 보안 필터를 통과한 "
            "유망 토큰 목록을 분석해줘. 보안 점수와 졸업 가능성을 기준으로 "
            "최대 3개를 선별하고, 각 토큰에 대한 진입/손절/익절 레벨을 계산해줘."
        )
        response = await self.agent.run(task)
        logger.info(f"[하트비트] 1단계 완료: {response.message[:80]}...")

    async def _step2_manage_positions(self) -> None:
        """2단계: 포지션 관리 — PnL 계산 및 손절/트레일링 스톱"""
        if not self._positions:
            logger.debug("[하트비트] 관리할 포지션 없음")
            return

        position_list = list(self._positions.values())
        task = (
            f"현재 보유 중인 포지션들의 상태를 점검해줘. "
            f"포지션 수: {len(position_list)}개. "
            "각 포지션의 현재 가격을 조회하고, "
            "손절 또는 트레일링 스톱 조건이 충족되면 즉시 매도 처리해줘. "
            f"포지션 정보: {position_list}"
        )
        response = await self.agent.run(task)
        logger.info(f"[하트비트] 2단계 완료: {response.message[:80]}...")

    async def _step3_self_optimize(self) -> None:
        """3단계: 자기 개선 — 최근 5개 거래 분석"""
        self._cycle_count += 1
        if self._cycle_count % 5 != 0:  # 5회 주기마다 실행
            return

        task = (
            "최근 거래 결과를 분석하고 self_optimizer 스킬을 사용하여 "
            "슬리피지와 Jito 팁 설정을 최적화해줘. "
            "변경된 설정값과 그 이유를 보고해줘."
        )
        response = await self.agent.run(task)
        logger.info(f"[하트비트] 3단계 완료: {response.message[:80]}...")

    async def _step4_report(self) -> None:
        """4단계: 수익 현황 및 설정 변경 보고"""
        task = (
            "현재 포트폴리오 잔액, 오늘의 수익/손실, "
            "킬스위치 상태를 종합하여 간략한 보고서를 작성해줘. "
            "리스크 한도 잔여량도 포함해줘."
        )
        response = await self.agent.run(task)
        logger.info(f"[하트비트] 4단계 완료 (보고): {response.message[:80]}...")
