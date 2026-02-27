"""암호화 지갑 스킬 — AES-256 개인키 암호화 저장/복호화"""
import os
from typing import Any, Dict
from loguru import logger

from src.core.security import APIKeyEncryption
from src.core.exceptions import EncryptionException, SkillException
from .base_skill import BaseSkill, SkillResult


# 최소 개인키 길이 검증 상수 (Base58 인코딩 기준)
_MIN_PRIVATE_KEY_LENGTH = 32


class CryptoWalletSkill(BaseSkill):
    """
    암호화 지갑 스킬

    AES-256-CBC를 사용하여 솔라나 개인키를 안전하게 암호화/복호화합니다.
    개인키는 절대 평문으로 반환하거나 로그에 출력되지 않습니다.

    보안 원칙:
    - 개인키는 메모리에서 사용 후 즉시 폐기
    - 암호화된 키만 저장 (환경 변수 또는 파일)
    - 복호화된 키는 서명 작업 직전에만 메모리에 로드
    - 어떤 경우에도 개인키를 외부로 반환하지 않음
    """

    def __init__(self, master_encryption_key: str):
        """
        초기화

        Args:
            master_encryption_key: AES-256 마스터 암호화 키 (32바이트 이상)
        """
        super().__init__(
            name="cryptowallet",
            description=(
                "솔라나 개인키를 AES-256으로 암호화하여 안전하게 관리합니다. "
                "개인키는 절대 외부로 노출되지 않습니다."
            ),
        )
        if not master_encryption_key:
            raise SkillException("마스터 암호화 키가 설정되어 있지 않습니다.")
        self._encryption = APIKeyEncryption(master_encryption_key)

    def as_tool_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["encrypt_key", "verify_key", "get_public_key"],
                        "description": (
                            "encrypt_key: 개인키를 AES-256으로 암호화, "
                            "verify_key: 암호화된 키의 유효성 확인, "
                            "get_public_key: 암호화된 키에서 공개키 파생 (Ed25519)"
                        ),
                    },
                    "private_key_b58": {
                        "type": "string",
                        "description": "Base58 인코딩된 솔라나 개인키 (encrypt_key 시만 사용)",
                    },
                    "encrypted_key": {
                        "type": "string",
                        "description": "AES-256 암호화된 키 문자열 (verify_key/get_public_key 시)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(  # type: ignore[override]
        self,
        action: str,
        private_key_b58: str = "",
        encrypted_key: str = "",
        **_kwargs: Any,
    ) -> SkillResult:
        """
        암호화 지갑 작업 실행

        Args:
            action: encrypt_key / verify_key / get_public_key
            private_key_b58: Base58 솔라나 개인키 (encrypt_key 전용)
            encrypted_key: AES-256 암호화 키

        Returns:
            SkillResult — 개인키 평문은 절대 포함하지 않음
        """
        if action == "encrypt_key":
            return self._encrypt_key(private_key_b58)
        elif action == "verify_key":
            return self._verify_key(encrypted_key)
        elif action == "get_public_key":
            return self._get_public_key(encrypted_key)
        else:
            return SkillResult(
                success=False,
                message=f"알 수 없는 작업: {action}",
                errors=[f"지원하지 않는 action: {action}"],
            )

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 메서드 — 개인키는 이 경계를 넘지 않습니다
    # ──────────────────────────────────────────────────────────────────────────

    def _encrypt_key(self, private_key_b58: str) -> SkillResult:
        """
        개인키 암호화

        Args:
            private_key_b58: Base58 개인키 (입력 후 메모리에서 즉시 사용)

        Returns:
            SkillResult with encrypted_key (평문 키는 포함하지 않음)
        """
        if not private_key_b58:
            return SkillResult(
                success=False,
                message="private_key_b58가 필요합니다.",
                errors=["private_key_b58 누락"],
            )

        # 기본 길이 검증 (_MIN_PRIVATE_KEY_LENGTH 자 이상)
        if len(private_key_b58) < _MIN_PRIVATE_KEY_LENGTH:
            return SkillResult(
                success=False,
                message="유효하지 않은 개인키 형식입니다.",
                errors=["개인키가 너무 짧습니다."],
            )

        try:
            encrypted = self._encryption.encrypt(private_key_b58)
        except Exception as e:
            logger.error(f"개인키 암호화 실패 (상세 오류 숨김)")
            return SkillResult(
                success=False,
                message="개인키 암호화에 실패했습니다.",
                errors=["암호화 오류"],
            )
        finally:
            # 평문 키 참조를 명시적으로 제거
            private_key_b58 = ""

        logger.info("개인키 암호화 완료 (키 길이 비공개)")
        return SkillResult(
            success=True,
            data={
                "encrypted_key": encrypted,
                "key_length": len(encrypted),
                "note": "이 암호화된 키를 OPENCLAW_ENCRYPTED_PRIVATE_KEY 환경 변수에 저장하세요.",
            },
            message="개인키가 AES-256으로 암호화되었습니다. 원본 키는 안전하게 폐기하세요.",
        )

    def _verify_key(self, encrypted_key: str) -> SkillResult:
        """
        암호화된 키의 유효성 확인

        Args:
            encrypted_key: AES-256 암호화 키

        Returns:
            SkillResult with validation result (평문 없음)
        """
        if not encrypted_key:
            return SkillResult(
                success=False,
                message="encrypted_key가 필요합니다.",
                errors=["encrypted_key 누락"],
            )

        try:
            decrypted = self._encryption.decrypt(encrypted_key)
            is_valid = len(decrypted) >= 32
        except Exception:
            is_valid = False
        finally:
            # 복호화된 값을 즉시 제거
            decrypted = ""

        return SkillResult(
            success=is_valid,
            data={"is_valid": is_valid},
            message="키 유효성 확인됨" if is_valid else "키 유효성 검사 실패 (잘못된 마스터키 또는 손상된 데이터)",
        )

    def _get_public_key(self, encrypted_key: str) -> SkillResult:
        """
        암호화된 개인키에서 솔라나 공개키(지갑 주소) 파생

        Args:
            encrypted_key: AES-256 암호화 키

        Returns:
            SkillResult with public key (Base58)
        """
        if not encrypted_key:
            return SkillResult(
                success=False,
                message="encrypted_key가 필요합니다.",
                errors=["encrypted_key 누락"],
            )

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            private_key_b58 = self._encryption.decrypt(encrypted_key)
            key_bytes = _decode_base58(private_key_b58)
            seed = key_bytes[:32]
            private_key_obj = Ed25519PrivateKey.from_private_bytes(seed)
            public_key_bytes = private_key_obj.public_key().public_bytes_raw()
            public_key_b58 = _encode_base58(public_key_bytes)

        except Exception as e:
            logger.error("공개키 파생 실패 (상세 오류 숨김)")
            return SkillResult(
                success=False,
                message="공개키 파생에 실패했습니다. 마스터키를 확인하세요.",
                errors=["공개키 파생 오류"],
            )
        finally:
            # 개인키 평문 즉시 제거
            try:
                private_key_b58 = ""
                seed = b""
            except Exception:
                pass

        return SkillResult(
            success=True,
            data={"public_key": public_key_b58},
            message=f"지갑 주소: {public_key_b58}",
        )

    def decrypt_for_signing(self, encrypted_key: str) -> str:
        """
        서명 목적으로만 사용하는 내부 복호화 메서드

        이 메서드는 TradeExecutorSkill 내부에서만 호출해야 합니다.
        반환된 평문 키는 서명 후 즉시 삭제하세요.

        Args:
            encrypted_key: AES-256 암호화 키

        Returns:
            Base58 개인키 (서명 후 즉시 폐기 필수)
        """
        try:
            return self._encryption.decrypt(encrypted_key)
        except Exception as e:
            raise EncryptionException(f"복호화 실패: {str(e)}") from e


# ──────────────────────────────────────────────────────────────────────────────
# Base58 유틸리티 (cryptography 외부 dep 없이)
# ──────────────────────────────────────────────────────────────────────────────

_BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _decode_base58(s: str) -> bytes:
    """Base58 → bytes"""
    base = len(_BASE58_ALPHABET)
    decoded = 0
    multi = 1
    for char in reversed(s.encode("ascii")):
        decoded += multi * _BASE58_ALPHABET.index(char)
        multi *= base
    result = []
    while decoded:
        result.append(decoded & 0xFF)
        decoded >>= 8
    result.reverse()
    return bytes(result)


def _encode_base58(data: bytes) -> str:
    """bytes → Base58"""
    base = len(_BASE58_ALPHABET)
    n = int.from_bytes(data, "big")
    chars = []
    while n:
        n, remainder = divmod(n, base)
        chars.append(chr(_BASE58_ALPHABET[remainder]))
    return "".join(reversed(chars))
