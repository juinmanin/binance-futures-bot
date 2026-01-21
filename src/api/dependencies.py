"""FastAPI 의존성"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.database import User
from src.services.auth import AuthService

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    현재 인증된 사용자 조회
    
    Args:
        credentials: HTTP Authorization 헤더
        db: 데이터베이스 세션
        
    Returns:
        현재 사용자
        
    Raises:
        HTTPException: 인증 실패 시
    """
    token = credentials.credentials
    
    try:
        token_data = await AuthService.verify_token(token, token_type="access")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    현재 활성 사용자 조회
    
    Args:
        current_user: 현재 사용자
        
    Returns:
        활성 사용자
        
    Raises:
        HTTPException: 비활성 사용자인 경우
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user
