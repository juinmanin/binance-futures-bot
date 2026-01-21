"""API 키 암호화 테스트"""
import pytest
from src.core.security import APIKeyEncryption


def test_encryption_initialization():
    """암호화 클래스 초기화 테스트"""
    master_key = "test-master-key-32-bytes!!!!!"
    encryption = APIKeyEncryption(master_key)
    
    assert encryption.master_key is not None
    assert len(encryption.master_key) == 32


def test_encrypt_decrypt():
    """암호화 및 복호화 테스트"""
    master_key = "test-master-key-32-bytes!!!!!"
    encryption = APIKeyEncryption(master_key)
    
    plaintext = "my-secret-api-key"
    
    # 암호화
    ciphertext = encryption.encrypt(plaintext)
    assert ciphertext != plaintext
    assert isinstance(ciphertext, str)
    
    # 복호화
    decrypted = encryption.decrypt(ciphertext)
    assert decrypted == plaintext


def test_encrypt_produces_different_ciphertexts():
    """같은 평문을 암호화해도 다른 암호문이 생성되는지 테스트 (IV 때문에)"""
    master_key = "test-master-key-32-bytes!!!!!"
    encryption = APIKeyEncryption(master_key)
    
    plaintext = "my-secret-api-key"
    
    ciphertext1 = encryption.encrypt(plaintext)
    ciphertext2 = encryption.encrypt(plaintext)
    
    # 같은 평문이라도 IV가 다르기 때문에 암호문은 달라야 함
    assert ciphertext1 != ciphertext2
    
    # 하지만 복호화하면 같은 평문이 나와야 함
    assert encryption.decrypt(ciphertext1) == plaintext
    assert encryption.decrypt(ciphertext2) == plaintext


def test_decrypt_invalid_ciphertext():
    """잘못된 암호문 복호화 시 예외 발생 테스트"""
    master_key = "test-master-key-32-bytes!!!!!"
    encryption = APIKeyEncryption(master_key)
    
    with pytest.raises(Exception):
        encryption.decrypt("invalid-ciphertext")


def test_encryption_with_different_keys():
    """다른 키로 암호화한 데이터는 복호화되지 않는지 테스트"""
    plaintext = "my-secret-api-key"
    
    key1 = "key1-32-bytes-long!!!!!!!!!!!!"
    key2 = "key2-32-bytes-long!!!!!!!!!!!!"
    
    encryption1 = APIKeyEncryption(key1)
    encryption2 = APIKeyEncryption(key2)
    
    ciphertext = encryption1.encrypt(plaintext)
    
    # 다른 키로 복호화하면 예외 발생하거나 잘못된 결과
    with pytest.raises(Exception):
        encryption2.decrypt(ciphertext)
