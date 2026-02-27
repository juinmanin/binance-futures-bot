"""솔라나 JSON-RPC 클라이언트"""
import asyncio
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger

from src.core.exceptions import SolanaRPCException


class SolanaRPCClient:
    """솔라나 JSON-RPC 2.0 클라이언트 (읽기 전용 시장 데이터)"""

    LAMPORTS_PER_SOL = 1_000_000_000

    def __init__(
        self,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        timeout: float = 30.0,
    ):
        """
        초기화

        Args:
            rpc_url: 솔라나 RPC 엔드포인트
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.rpc_url = rpc_url
        self._client = httpx.AsyncClient(timeout=timeout)
        self._request_id = 0

    async def __aenter__(self) -> "SolanaRPCClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        """클라이언트 종료"""
        await self._client.aclose()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _call(
        self, method: str, params: Optional[List[Any]] = None
    ) -> Any:
        """
        JSON-RPC 호출

        Args:
            method: RPC 메서드 이름
            params: 메서드 파라미터

        Returns:
            RPC 응답 결과
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or [],
        }

        try:
            response = await self._client.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise SolanaRPCException(
                f"RPC HTTP 오류: {e.response.status_code}",
                details=e.response.text,
            ) from e
        except Exception as e:
            raise SolanaRPCException(f"RPC 요청 실패: {str(e)}") from e

        if "error" in data:
            err = data["error"]
            raise SolanaRPCException(
                f"RPC 오류 [{err.get('code', '?')}]: {err.get('message', '알 수 없는 오류')}",
                details=err,
            )

        return data.get("result")

    async def get_balance(self, address: str) -> float:
        """
        SOL 잔액 조회

        Args:
            address: 솔라나 지갑 주소

        Returns:
            SOL 잔액 (소수점 포함)
        """
        result = await self._call("getBalance", [address])
        lamports = result.get("value", 0) if isinstance(result, dict) else result
        return lamports / self.LAMPORTS_PER_SOL

    async def get_token_accounts_by_owner(
        self,
        owner: str,
        mint: Optional[str] = None,
        program_id: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    ) -> List[Dict[str, Any]]:
        """
        SPL 토큰 계정 목록 조회

        Args:
            owner: 소유자 주소
            mint: 특정 토큰 민트 주소 (선택)
            program_id: SPL Token 프로그램 ID

        Returns:
            토큰 계정 목록
        """
        filter_param: Dict[str, Any]
        if mint:
            filter_param = {"mint": mint}
        else:
            filter_param = {"programId": program_id}

        result = await self._call(
            "getTokenAccountsByOwner",
            [
                owner,
                filter_param,
                {"encoding": "jsonParsed"},
            ],
        )
        return result.get("value", []) if isinstance(result, dict) else []

    async def get_token_balance(self, token_account: str) -> Dict[str, Any]:
        """
        SPL 토큰 잔액 조회

        Args:
            token_account: 토큰 계정 주소

        Returns:
            잔액 정보 (amount, decimals, uiAmount)
        """
        result = await self._call(
            "getTokenAccountBalance", [token_account]
        )
        return result.get("value", {}) if isinstance(result, dict) else {}

    async def get_recent_blockhash(self) -> str:
        """
        최근 블록해시 조회 (트랜잭션 서명에 필요)

        Returns:
            최근 블록해시 문자열
        """
        result = await self._call(
            "getLatestBlockhash", [{"commitment": "finalized"}]
        )
        if isinstance(result, dict):
            return result.get("value", {}).get("blockhash", "")
        return ""

    async def get_slot(self) -> int:
        """
        현재 슬롯 번호 조회

        Returns:
            현재 슬롯
        """
        result = await self._call("getSlot")
        return int(result) if result is not None else 0

    async def health_check(self) -> bool:
        """
        RPC 노드 헬스 체크

        Returns:
            연결 성공 여부
        """
        try:
            await self.get_slot()
            return True
        except SolanaRPCException:
            return False

    async def get_multiple_accounts(
        self, addresses: List[str]
    ) -> List[Optional[Dict[str, Any]]]:
        """
        여러 계정 정보 일괄 조회

        Args:
            addresses: 주소 목록 (최대 100개)

        Returns:
            계정 정보 목록 (계정 없으면 None)
        """
        if not addresses:
            return []
        if len(addresses) > 100:
            logger.warning("getMultipleAccounts 최대 100개까지 지원. 처음 100개만 조회합니다.")
            addresses = addresses[:100]

        result = await self._call(
            "getMultipleAccounts",
            [addresses, {"encoding": "jsonParsed"}],
        )
        return result.get("value", []) if isinstance(result, dict) else []

    async def send_raw_transaction(self, signed_tx_base64: str) -> str:
        """
        서명된 트랜잭션 전송

        Args:
            signed_tx_base64: Base64 인코딩된 서명 트랜잭션

        Returns:
            트랜잭션 시그니처
        """
        result = await self._call(
            "sendTransaction",
            [
                signed_tx_base64,
                {"encoding": "base64", "preflightCommitment": "processed"},
            ],
        )
        if not result:
            raise SolanaRPCException("빈 트랜잭션 시그니처 수신")
        return str(result)

    async def confirm_transaction(
        self,
        signature: str,
        commitment: str = "confirmed",
        max_retries: int = 30,
        retry_interval: float = 2.0,
    ) -> bool:
        """
        트랜잭션 컨펌 대기

        Args:
            signature: 트랜잭션 시그니처
            commitment: 컨펌 레벨 (processed/confirmed/finalized)
            max_retries: 최대 재시도 횟수
            retry_interval: 재시도 간격 (초)

        Returns:
            컨펌 성공 여부
        """
        for attempt in range(max_retries):
            try:
                result = await self._call(
                    "getSignatureStatuses",
                    [[signature], {"searchTransactionHistory": False}],
                )
                statuses = result.get("value", []) if isinstance(result, dict) else []
                if statuses and statuses[0] is not None:
                    status = statuses[0]
                    if status.get("err") is not None:
                        raise SolanaRPCException(
                            f"트랜잭션 실패: {status['err']}"
                        )
                    conf = status.get("confirmationStatus", "")
                    if conf in ("confirmed", "finalized"):
                        logger.info(f"트랜잭션 컨펌됨: {signature[:16]}...")
                        return True
            except SolanaRPCException as e:
                if "트랜잭션 실패" in str(e):
                    raise
                logger.warning(f"컨펌 확인 오류 (시도 {attempt + 1}): {e}")
            await asyncio.sleep(retry_interval)

        logger.warning(f"트랜잭션 컨펌 타임아웃: {signature[:16]}...")
        return False
