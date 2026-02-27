"""거래 실행 스킬 — 솔라나 DEX 스왑 (Jupiter 집계기)"""
import base64
import struct
from decimal import Decimal
from typing import Any, Dict, Optional
from loguru import logger

from src.services.solana.rpc_client import SolanaRPCClient
from src.services.solana.jupiter_client import JupiterClient
from src.core.exceptions import SkillException
from .base_skill import BaseSkill, SkillResult

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


def _decode_base58(s: str) -> bytes:
    """Base58 디코딩 (외부 라이브러리 없이 구현)"""
    alphabet = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    base_count = len(alphabet)
    decoded = 0
    multi = 1
    for char in reversed(s.encode("ascii")):
        index = alphabet.index(char)
        decoded += multi * index
        multi *= base_count
    result = []
    while decoded:
        result.append(decoded & 0xFF)
        decoded >>= 8
    result.reverse()
    return bytes(result)


class TradeExecutorSkill(BaseSkill):
    """
    솔라나 DEX 거래 실행 스킬

    Jupiter 집계기를 통해 토큰 스왑을 실행합니다.
    dry_run=True 인 경우 실제 트랜잭션을 전송하지 않습니다.
    """

    def __init__(
        self,
        solana_client: SolanaRPCClient,
        jupiter_client: JupiterClient,
        wallet_private_key_b58: str = "",
        dry_run: bool = True,
    ):
        """
        초기화

        Args:
            solana_client: 솔라나 RPC 클라이언트
            jupiter_client: Jupiter DEX 클라이언트
            wallet_private_key_b58: Base58 인코딩된 64바이트 지갑 개인키
                                     (dry_run=False 시 필수)
            dry_run: True이면 실제 트랜잭션 전송 없이 시뮬레이션
        """
        super().__init__(
            name="trade_executor",
            description=(
                "솔라나 DEX(Jupiter)를 통해 토큰 스왑을 실행합니다. "
                "dry_run 모드에서는 실제 거래 없이 시뮬레이션합니다."
            ),
        )
        self.solana = solana_client
        self.jupiter = jupiter_client
        self.dry_run = dry_run
        self._private_key_b58 = wallet_private_key_b58

        if not dry_run and not wallet_private_key_b58:
            raise SkillException(
                "dry_run=False 설정 시 wallet_private_key_b58가 필요합니다."
            )

    def as_tool_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["estimate", "execute"],
                        "description": (
                            "estimate: 거래 예상치 계산 (실행 없음), "
                            "execute: 실제 스왑 실행 (dry_run이 False일 때만 적용)"
                        ),
                    },
                    "input_token": {
                        "type": "string",
                        "description": "입력 토큰 심볼 또는 민트 주소 (예: USDC)",
                    },
                    "output_token": {
                        "type": "string",
                        "description": "출력 토큰 심볼 또는 민트 주소 (예: SOL)",
                    },
                    "amount_ui": {
                        "type": "number",
                        "description": "입력 수량 (소수점 포함 UI 금액)",
                    },
                    "input_decimals": {
                        "type": "integer",
                        "description": "입력 토큰 소수점 자릿수 (기본 6 = USDC)",
                    },
                    "output_decimals": {
                        "type": "integer",
                        "description": "출력 토큰 소수점 자릿수 (기본 9 = SOL)",
                    },
                    "slippage_bps": {
                        "type": "integer",
                        "description": "허용 슬리피지 (베이시스 포인트, 기본 50 = 0.5%)",
                    },
                    "wallet_address": {
                        "type": "string",
                        "description": "지갑 공개 주소 (execute 시 필요)",
                    },
                },
                "required": ["action", "input_token", "output_token", "amount_ui"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        action: str,
        input_token: str,
        output_token: str,
        amount_ui: float,
        input_decimals: int = 6,
        output_decimals: int = 9,
        slippage_bps: int = 50,
        wallet_address: str = "",
        **_kwargs: Any,
    ) -> SkillResult:
        """
        거래 실행

        Args:
            action: 'estimate' 또는 'execute'
            input_token: 입력 토큰
            output_token: 출력 토큰
            amount_ui: 입력 수량 (UI 단위)
            input_decimals: 입력 토큰 소수점
            output_decimals: 출력 토큰 소수점
            slippage_bps: 슬리피지 (BPS)
            wallet_address: 지갑 주소 (execute 시)

        Returns:
            SkillResult
        """
        if action == "estimate":
            return await self._estimate_swap(
                input_token=input_token,
                output_token=output_token,
                amount_ui=Decimal(str(amount_ui)),
                input_decimals=input_decimals,
                output_decimals=output_decimals,
                slippage_bps=slippage_bps,
            )
        elif action == "execute":
            return await self._execute_swap(
                input_token=input_token,
                output_token=output_token,
                amount_ui=Decimal(str(amount_ui)),
                input_decimals=input_decimals,
                output_decimals=output_decimals,
                slippage_bps=slippage_bps,
                wallet_address=wallet_address,
            )
        else:
            return SkillResult(
                success=False,
                message=f"알 수 없는 거래 작업: {action}",
                errors=[f"지원하지 않는 action: {action}"],
            )

    async def _estimate_swap(
        self,
        input_token: str,
        output_token: str,
        amount_ui: Decimal,
        input_decimals: int,
        output_decimals: int,
        slippage_bps: int,
    ) -> SkillResult:
        """스왑 예상치 계산"""
        try:
            est = await self.jupiter.estimate_swap_output(
                input_token=input_token,
                output_token=output_token,
                amount_ui=amount_ui,
                input_decimals=input_decimals,
                output_decimals=output_decimals,
                slippage_bps=slippage_bps,
            )
            data = {
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": float(est["input_amount"]),
                "output_amount": float(est["output_amount"]),
                "price_impact_pct": est["price_impact_pct"],
                "slippage_bps": slippage_bps,
                "route_count": len(est.get("route_plan", [])),
                "dry_run": True,
            }
            logger.info(
                f"스왑 예상: {input_token} {amount_ui} → "
                f"{output_token} {est['output_amount']:.6f}"
            )
            return SkillResult(
                success=True,
                data=data,
                message=(
                    f"{input_token} {amount_ui} → {output_token} "
                    f"{float(est['output_amount']):.6f} "
                    f"(가격 충격: {est['price_impact_pct']:.4f}%)"
                ),
            )
        except Exception as e:
            logger.error(f"스왑 예상 실패: {e}")
            return SkillResult(
                success=False,
                message=f"스왑 예상 실패: {str(e)}",
                errors=[str(e)],
            )

    async def _execute_swap(
        self,
        input_token: str,
        output_token: str,
        amount_ui: Decimal,
        input_decimals: int,
        output_decimals: int,
        slippage_bps: int,
        wallet_address: str,
    ) -> SkillResult:
        """실제 스왑 실행"""
        if self.dry_run:
            logger.info("DRY RUN 모드: 실제 스왑을 실행하지 않습니다.")
            est_result = await self._estimate_swap(
                input_token, output_token, amount_ui,
                input_decimals, output_decimals, slippage_bps
            )
            if est_result.data:
                est_result.data["dry_run"] = True
                est_result.data["tx_signature"] = "DRY_RUN_NO_TRANSACTION"
            est_result.message = f"[DRY RUN] {est_result.message}"
            return est_result

        if not wallet_address:
            return SkillResult(
                success=False,
                message="execute 작업에는 wallet_address가 필요합니다.",
                errors=["wallet_address 누락"],
            )
        if not _CRYPTO_AVAILABLE:
            return SkillResult(
                success=False,
                message="cryptography 패키지가 설치되어 있지 않습니다.",
                errors=["cryptography 미설치"],
            )
        if not self._private_key_b58:
            return SkillResult(
                success=False,
                message="지갑 개인키가 설정되어 있지 않습니다.",
                errors=["개인키 미설정"],
            )

        try:
            # 1. 견적 조회
            quote = await self.jupiter.get_quote(
                input_token=input_token,
                output_token=output_token,
                amount_ui=amount_ui,
                input_decimals=input_decimals,
                slippage_bps=slippage_bps,
            )

            # 2. 트랜잭션 빌드
            tx_b64 = await self.jupiter.get_swap_transaction(
                quote_response=quote,
                user_public_key=wallet_address,
            )

            # 3. 트랜잭션 서명
            signed_tx_b64 = self._sign_transaction(tx_b64)

            # 4. 트랜잭션 전송
            signature = await self.solana.send_raw_transaction(signed_tx_b64)

            # 5. 컨펌 대기
            confirmed = await self.solana.confirm_transaction(signature)

            data = {
                "tx_signature": signature,
                "confirmed": confirmed,
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": float(amount_ui),
                "dry_run": False,
            }
            logger.info(f"스왑 실행 완료: {signature[:16]}... (컨펌: {confirmed})")
            return SkillResult(
                success=confirmed,
                data=data,
                message=f"스왑 {'완료' if confirmed else '전송됨'}: {signature[:20]}...",
            )

        except Exception as e:
            logger.error(f"스왑 실행 실패: {e}")
            return SkillResult(
                success=False,
                message=f"스왑 실행 실패: {str(e)}",
                errors=[str(e)],
            )

    def _sign_transaction(self, tx_b64: str) -> str:
        """
        Ed25519로 트랜잭션 서명

        Args:
            tx_b64: Base64 인코딩된 미서명 트랜잭션

        Returns:
            Base64 인코딩된 서명된 트랜잭션

        Note:
            솔라나 트랜잭션 바이너리 포맷을 직접 처리합니다.
            Versioned Transaction (v0) 형식을 지원합니다.
        """
        raw = base64.b64decode(tx_b64)
        key_bytes = _decode_base58(self._private_key_b58)
        # 솔라나 keypair: 처음 32바이트 시드 사용
        seed = key_bytes[:32]
        private_key = Ed25519PrivateKey.from_private_bytes(seed)

        # 솔라나 트랜잭션 서명: 첫 바이트가 버전 접두사 (0x80이면 versioned)
        if raw[0] & 0x80:
            # Versioned transaction: [prefix][num_sigs][sigs...][message]
            num_required_sigs = 1
            sig_offset = 2  # prefix byte + num_sigs byte
            message = raw[sig_offset + (64 * num_required_sigs):]
            sig = private_key.sign(message)
            signed = bytearray(raw)
            signed[sig_offset: sig_offset + 64] = sig
        else:
            # Legacy transaction: [num_sigs][sigs...][message]
            num_required_sigs = raw[0]
            sig_offset = 1
            message_start = sig_offset + (64 * num_required_sigs)
            message = raw[message_start:]
            sig = private_key.sign(message)
            signed = bytearray(raw)
            signed[sig_offset: sig_offset + 64] = sig

        return base64.b64encode(bytes(signed)).decode("ascii")
