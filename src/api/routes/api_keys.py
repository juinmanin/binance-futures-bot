"""API 키 관리 라우트"""
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from loguru import logger

from src.db import get_db
from src.models.schemas import APIKeyCreate, APIKeyResponse, APIKeyVerifyResponse
from src.models.database import User, APIKey
from src.core.security import get_encryption
from src.config import settings
from src.api.dependencies import get_current_user
from src.services.binance import BinanceClient

router = APIRouter(prefix="/api/v1/api-keys", tags=["API Keys"])


@router.post("/", response_model=APIKeyResponse)
async def register_api_key(
    api_key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    사용자가 UI에서 입력한 API Key/Secret을 암호화하여 저장
    
    Flow:
    1. 프론트엔드에서 HTTPS로 API Key/Secret 전송
    2. 백엔드에서 AES-256으로 암호화
    3. 암호화된 데이터를 PostgreSQL에 저장
    4. 마스킹된 키 정보 반환 (앞 4자리만 표시)
    """
    try:
        encryption = get_encryption(settings.master_encryption_key)
        
        # 암호화
        encrypted_api_key = encryption.encrypt(api_key_data.api_key)
        encrypted_api_secret = encryption.encrypt(api_key_data.api_secret)
        
        # 기존 default API 키 확인
        if not api_key_data.label or api_key_data.label == "Default":
            # 기존 API 키가 있는지 확인
            result = await db.execute(
                select(APIKey)
                .where(APIKey.user_id == current_user.id)
                .limit(1)
            )
            existing_key = result.scalar_one_or_none()
            is_default = existing_key is None  # 첫 번째 키면 기본값으로 설정
        else:
            is_default = False
        
        # DB 저장
        db_api_key = APIKey(
            user_id=current_user.id,
            exchange="binance",
            encrypted_api_key=encrypted_api_key,
            encrypted_api_secret=encrypted_api_secret,
            is_testnet=api_key_data.is_testnet,
            label=api_key_data.label,
            is_default=is_default
        )
        db.add(db_api_key)
        await db.commit()
        await db.refresh(db_api_key)
        
        # 마스킹된 응답 반환
        masked_key = f"{api_key_data.api_key[:4]}{'*' * 12}"
        
        return APIKeyResponse(
            id=db_api_key.id,
            label=db_api_key.label,
            masked_api_key=masked_key,
            exchange=db_api_key.exchange,
            is_testnet=db_api_key.is_testnet,
            is_default=db_api_key.is_default,
            created_at=db_api_key.created_at,
            last_used_at=db_api_key.last_used_at
        )
    except Exception as e:
        logger.error(f"Failed to register API key: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register API key: {str(e)}"
        )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """사용자의 API 키 목록 조회 (마스킹된 상태)"""
    try:
        result = await db.execute(
            select(APIKey)
            .where(APIKey.user_id == current_user.id)
            .order_by(APIKey.is_default.desc(), APIKey.created_at.desc())
        )
        api_keys = result.scalars().all()
        
        encryption = get_encryption(settings.master_encryption_key)
        
        responses = []
        for api_key in api_keys:
            # 복호화하여 마스킹
            decrypted_key = encryption.decrypt(api_key.encrypted_api_key)
            masked_key = f"{decrypted_key[:4]}{'*' * 12}" if len(decrypted_key) >= 4 else "****"
            
            responses.append(APIKeyResponse(
                id=api_key.id,
                label=api_key.label,
                masked_api_key=masked_key,
                exchange=api_key.exchange,
                is_testnet=api_key.is_testnet,
                is_default=api_key.is_default,
                created_at=api_key.created_at,
                last_used_at=api_key.last_used_at
            ))
        
        return responses
    except Exception as e:
        logger.error(f"Failed to list API keys: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list API keys: {str(e)}"
        )


@router.delete("/{api_key_id}")
async def delete_api_key(
    api_key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """API 키 삭제"""
    try:
        result = await db.execute(
            select(APIKey)
            .where(APIKey.id == api_key_id)
            .where(APIKey.user_id == current_user.id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        await db.delete(api_key)
        await db.commit()
        
        return {"message": "API key deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete API key: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )


@router.post("/verify", response_model=APIKeyVerifyResponse)
async def verify_api_key(
    api_key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    바이낸스 API 연결 테스트
    - 복호화하여 바이낸스에 연결 테스트
    - 잔고 조회 성공 여부 확인
    """
    try:
        # API 키 조회
        result = await db.execute(
            select(APIKey)
            .where(APIKey.id == api_key_id)
            .where(APIKey.user_id == current_user.id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        # 복호화
        encryption = get_encryption(settings.master_encryption_key)
        decrypted_api_key = encryption.decrypt(api_key.encrypted_api_key)
        decrypted_api_secret = encryption.decrypt(api_key.encrypted_api_secret)
        
        # 바이낸스 연결 테스트
        async with BinanceClient(
            api_key=decrypted_api_key,
            api_secret=decrypted_api_secret,
            base_url=settings.binance_base_url,
            testnet=api_key.is_testnet
        ) as client:
            # 연결 테스트
            ping_ok = await client.ping()
            if not ping_ok:
                return APIKeyVerifyResponse(
                    is_valid=False,
                    message="Failed to connect to Binance API"
                )
            
            # 잔고 조회 테스트
            try:
                balance = await client.get_account_balance()
                
                # 계정 타입 확인
                account_type = "TESTNET" if api_key.is_testnet else "MAINNET"
                
                # last_used_at 업데이트
                await db.execute(
                    update(APIKey)
                    .where(APIKey.id == api_key_id)
                    .values(last_used_at=datetime.utcnow())
                )
                await db.commit()
                
                return APIKeyVerifyResponse(
                    is_valid=True,
                    message="API key is valid and working",
                    account_type=account_type,
                    can_trade=True,
                    can_withdraw=False  # 일반적으로 withdraw는 별도 권한
                )
            except Exception as e:
                logger.error(f"Failed to get account balance: {str(e)}")
                return APIKeyVerifyResponse(
                    is_valid=False,
                    message=f"API key is valid but failed to get account data: {str(e)}"
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify API key: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify API key: {str(e)}"
        )


@router.put("/{api_key_id}/set-default")
async def set_default_api_key(
    api_key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """기본 API 키로 설정"""
    try:
        # API 키 확인
        result = await db.execute(
            select(APIKey)
            .where(APIKey.id == api_key_id)
            .where(APIKey.user_id == current_user.id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        # 기존 default 키를 모두 해제
        await db.execute(
            update(APIKey)
            .where(APIKey.user_id == current_user.id)
            .values(is_default=False)
        )
        
        # 선택한 키를 default로 설정
        await db.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(is_default=True)
        )
        
        await db.commit()
        
        return {"message": "Default API key updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set default API key: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set default API key: {str(e)}"
        )
