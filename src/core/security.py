"""보안 관련 유틸리티"""
import base64
from typing import Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import secrets


class APIKeyEncryption:
    """API 키 암호화/복호화 클래스 (AES-256)"""
    
    def __init__(self, master_key: str):
        """
        초기화
        
        Args:
            master_key: 32바이트 마스터 키 (Base64 인코딩된 문자열)
        """
        # 마스터 키가 32바이트가 되도록 처리
        if len(master_key) < 32:
            master_key = master_key.ljust(32, '0')
        elif len(master_key) > 32:
            master_key = master_key[:32]
        
        self.master_key = master_key.encode('utf-8')
    
    def encrypt(self, plaintext: str) -> str:
        """
        AES-256 암호화
        
        Args:
            plaintext: 암호화할 평문
            
        Returns:
            Base64 인코딩된 암호문 (IV + 암호화된 데이터)
        """
        # 16바이트 IV 생성
        iv = secrets.token_bytes(16)
        
        # PKCS7 패딩 적용
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode('utf-8')) + padder.finalize()
        
        # AES-256-CBC 암호화
        cipher = Cipher(
            algorithms.AES(self.master_key),
            modes.CBC(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        # IV + 암호문을 Base64로 인코딩
        encrypted_data = iv + ciphertext
        return base64.b64encode(encrypted_data).decode('utf-8')
    
    def decrypt(self, ciphertext: str) -> str:
        """
        AES-256 복호화
        
        Args:
            ciphertext: Base64 인코딩된 암호문
            
        Returns:
            복호화된 평문
        """
        # Base64 디코딩
        encrypted_data = base64.b64decode(ciphertext)
        
        # IV와 암호문 분리 (처음 16바이트가 IV)
        iv = encrypted_data[:16]
        actual_ciphertext = encrypted_data[16:]
        
        # AES-256-CBC 복호화
        cipher = Cipher(
            algorithms.AES(self.master_key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(actual_ciphertext) + decryptor.finalize()
        
        # PKCS7 패딩 제거
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        
        return plaintext.decode('utf-8')


# 전역 암호화 인스턴스를 생성하는 함수
_encryption_instance: Optional[APIKeyEncryption] = None


def get_encryption(master_key: str) -> APIKeyEncryption:
    """암호화 인스턴스 반환"""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = APIKeyEncryption(master_key)
    return _encryption_instance
