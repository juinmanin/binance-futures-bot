"""텔레그램 알림 서비스"""
import asyncio
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from loguru import logger

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available, telegram notifications disabled")


@dataclass
class DailyReport:
    """일일 리포트"""
    date: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: Decimal
    win_rate: float
    largest_win: Decimal
    largest_loss: Decimal


class TelegramNotificationService:
    """텔레그램 알림 서비스"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        초기화
        
        Args:
            bot_token: 텔레그램 봇 토큰
            chat_id: 텔레그램 채팅 ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id and HTTPX_AVAILABLE)
        self._client: Optional[httpx.AsyncClient] = None
        
        if not self.enabled:
            logger.warning(
                "Telegram notifications disabled: "
                f"bot_token={'set' if bot_token else 'not set'}, "
                f"chat_id={'set' if chat_id else 'not set'}, "
                f"httpx={'available' if HTTPX_AVAILABLE else 'not available'}"
            )
        else:
            logger.info("Telegram notifications enabled")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 싱글톤 반환"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def _send_message(
        self,
        message: str,
        parse_mode: str = "Markdown",
        disable_notification: bool = False
    ) -> bool:
        """
        텔레그램 메시지 전송
        
        Args:
            message: 전송할 메시지
            parse_mode: 파싱 모드 (Markdown, HTML)
            disable_notification: 알림 소리 비활성화
            
        Returns:
            전송 성공 여부
        """
        if not self.enabled:
            logger.debug(f"Telegram disabled, skipping message: {message[:50]}...")
            return False
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
        }
        
        try:
            client = await self._get_client()
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info("Telegram message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_signal_alert(
        self,
        signal: Dict[str, Any],
        symbol: str,
        mode: str = "auto"
    ) -> bool:
        """
        전략 신호 발생 알림
        
        Args:
            signal: 전략 신호 정보
            symbol: 심볼
            mode: 거래 모드 (auto, semi-auto, paper)
            
        Returns:
            전송 성공 여부
        """
        action = signal.get("action", "N/A")
        entry_price = signal.get("entry_price", 0)
        stop_loss = signal.get("stop_loss", 0)
        tp1 = signal.get("take_profit_1", 0)
        tp2 = signal.get("take_profit_2", 0)
        position_size = signal.get("position_size", 0)
        confidence = signal.get("confidence", 0)
        reason = signal.get("reason", "N/A")
        
        # 모드 아이콘
        mode_icon = {
            "auto": "🤖",
            "semi-auto": "👤",
            "paper": "📝"
        }.get(mode, "📊")
        
        # 방향 아이콘
        direction_icon = "🟢" if action == "BUY" else "🔴"
        
        message = f"""
{mode_icon} *새로운 거래 신호* {direction_icon}

📊 심볼: `{symbol}`
📈 방향: *{action}*
💰 진입가: `${entry_price:,.2f}`
🛑 손절가: `${stop_loss:,.2f}`
🎯 1차 익절: `${tp1:,.2f}`
🎯 2차 익절: `${tp2:,.2f}`
📏 포지션 크기: `{position_size:.4f}`
🔍 신뢰도: `{confidence:.0%}`

💡 *사유:*
{reason}

⚙️ 모드: {mode.upper()}
        """
        
        return await self._send_message(message.strip())
    
    async def send_order_filled(
        self,
        order: Dict[str, Any],
        symbol: str,
        side: str
    ) -> bool:
        """
        주문 체결 알림
        
        Args:
            order: 주문 정보
            symbol: 심볼
            side: 주문 방향 (BUY/SELL)
            
        Returns:
            전송 성공 여부
        """
        order_id = order.get("order_id", "N/A")
        order_type = order.get("order_type", "N/A")
        quantity = order.get("quantity", 0)
        price = order.get("price", 0)
        
        side_icon = "✅" if side == "BUY" else "❌"
        
        message = f"""
{side_icon} *주문 체결*

📊 심볼: `{symbol}`
🔖 주문 ID: `{order_id}`
📝 주문 유형: `{order_type}`
📈 방향: *{side}*
💰 가격: `${price:,.2f}`
📏 수량: `{quantity:.4f}`
        """
        
        return await self._send_message(message.strip())
    
    async def send_position_closed(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        pnl: Decimal,
        pnl_pct: float
    ) -> bool:
        """
        포지션 청산 알림
        
        Args:
            symbol: 심볼
            side: 포지션 방향
            entry_price: 진입가
            exit_price: 청산가
            quantity: 수량
            pnl: 손익 (달러)
            pnl_pct: 손익률 (%)
            
        Returns:
            전송 성공 여부
        """
        is_profit = pnl > 0
        result_icon = "💰" if is_profit else "💸"
        result_text = "익절" if is_profit else "손절"
        
        message = f"""
{result_icon} *포지션 청산 - {result_text}*

📊 심볼: `{symbol}`
📈 방향: *{side}*
💵 진입가: `${entry_price:,.2f}`
💵 청산가: `${exit_price:,.2f}`
📏 수량: `{quantity:.4f}`

{'🎉' if is_profit else '😢'} **손익: `${pnl:,.2f}` ({pnl_pct:+.2f}%)**
        """
        
        return await self._send_message(message.strip())
    
    async def send_stop_loss_hit(
        self,
        symbol: str,
        loss: Decimal,
        loss_pct: float
    ) -> bool:
        """
        손절 발동 알림
        
        Args:
            symbol: 심볼
            loss: 손실 금액
            loss_pct: 손실률 (%)
            
        Returns:
            전송 성공 여부
        """
        message = f"""
⚠️ *손절 발동*

📊 심볼: `{symbol}`
💸 손실: `${abs(loss):,.2f}` ({loss_pct:.2f}%)

포지션이 자동으로 청산되었습니다.
        """
        
        return await self._send_message(message.strip())
    
    async def send_take_profit_hit(
        self,
        symbol: str,
        profit: Decimal,
        profit_pct: float,
        level: int = 1
    ) -> bool:
        """
        익절 발동 알림
        
        Args:
            symbol: 심볼
            profit: 수익 금액
            profit_pct: 수익률 (%)
            level: 익절 단계 (1 or 2)
            
        Returns:
            전송 성공 여부
        """
        message = f"""
🎯 *{level}차 익절 달성*

📊 심볼: `{symbol}`
💰 수익: `${profit:,.2f}` (+{profit_pct:.2f}%)

{'포지션 50% 청산' if level == 1 else '포지션 전체 청산'}
        """
        
        return await self._send_message(message.strip())
    
    async def send_daily_report(self, report: DailyReport) -> bool:
        """
        일일 리포트 알림
        
        Args:
            report: 일일 리포트 데이터
            
        Returns:
            전송 성공 여부
        """
        win_rate = report.win_rate * 100
        is_profitable = report.total_pnl > 0
        pnl_icon = "📈" if is_profitable else "📉"
        
        message = f"""
📊 *일일 거래 리포트*

📅 날짜: `{report.date.strftime('%Y-%m-%d')}`

📊 **거래 통계**
• 총 거래: `{report.total_trades}건`
• 수익 거래: `{report.winning_trades}건`
• 손실 거래: `{report.losing_trades}건`
• 승률: `{win_rate:.1f}%`

{pnl_icon} **손익**
• 총 손익: `${report.total_pnl:+,.2f}`
• 최대 수익: `${report.largest_win:,.2f}`
• 최대 손실: `${report.largest_loss:,.2f}`

{'🎉 수익 달성!' if is_profitable else '⚠️ 손실 발생'}
        """
        
        return await self._send_message(message.strip())
    
    async def send_error_alert(
        self,
        error_type: str,
        error_message: str,
        symbol: Optional[str] = None
    ) -> bool:
        """
        에러 알림
        
        Args:
            error_type: 에러 유형
            error_message: 에러 메시지
            symbol: 심볼 (선택사항)
            
        Returns:
            전송 성공 여부
        """
        symbol_text = f"\n📊 심볼: `{symbol}`" if symbol else ""
        
        message = f"""
🚨 *시스템 에러 발생*

⚠️ 유형: `{error_type}`{symbol_text}

📝 메시지:
```
{error_message}
```

시스템 관리자에게 문의하세요.
        """
        
        return await self._send_message(message.strip())
    
    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        symbol: Optional[str] = None
    ) -> bool:
        """
        리스크 경고 알림
        
        Args:
            alert_type: 경고 유형
            message: 경고 메시지
            symbol: 심볼 (선택사항)
            
        Returns:
            전송 성공 여부
        """
        symbol_text = f"\n📊 심볼: `{symbol}`" if symbol else ""
        
        alert_message = f"""
⚠️ *리스크 경고*

🔔 유형: `{alert_type}`{symbol_text}

📝 내용:
{message}

즉시 확인이 필요합니다.
        """
        
        return await self._send_message(alert_message.strip())
    
    async def send_account_update(
        self,
        balance: Decimal,
        unrealized_pnl: Decimal,
        open_positions: int
    ) -> bool:
        """
        계좌 상태 업데이트
        
        Args:
            balance: 계좌 잔고
            unrealized_pnl: 미실현 손익
            open_positions: 오픈 포지션 수
            
        Returns:
            전송 성공 여부
        """
        pnl_icon = "📈" if unrealized_pnl >= 0 else "📉"
        
        message = f"""
💼 *계좌 상태 업데이트*

💰 잔고: `${balance:,.2f}`
{pnl_icon} 미실현 손익: `${unrealized_pnl:+,.2f}`
📊 오픈 포지션: `{open_positions}개`
        """
        
        return await self._send_message(
            message.strip(),
            disable_notification=True  # 조용한 알림
        )
