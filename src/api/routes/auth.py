"""인증 관련 라우트"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.schemas import UserCreate, UserLogin, UserResponse, Token
from src.services.auth import AuthService
from src.api.dependencies import get_current_user
from src.models.database import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    회원가입
    
    Args:
        user_data: 사용자 생성 데이터
        db: 데이터베이스 세션
        
    Returns:
        생성된 사용자 정보
    """
    try:
        user = await AuthService.create_user(db, user_data)
        return UserResponse.model_validate(user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=Token)
async def login(
    user_data: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    로그인
    
    Args:
        user_data: 로그인 데이터
        db: 데이터베이스 세션
        
    Returns:
        액세스 토큰 및 리프레시 토큰
    """
    user = await AuthService.authenticate_user(
        db,
        user_data.email,
        user_data.password,
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 토큰 생성
    token_data = {
        "sub": str(user.id),
        "email": user.email,
    }
    
    access_token = AuthService.create_access_token(token_data)
    refresh_token = AuthService.create_refresh_token(token_data)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    토큰 갱신
    
    Args:
        refresh_token: 리프레시 토큰
        db: 데이터베이스 세션
        
    Returns:
        새로운 액세스 토큰 및 리프레시 토큰
    """
    try:
        token_data = await AuthService.verify_token(refresh_token, token_type="refresh")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    # 새 토큰 생성
    new_token_data = {
        "sub": str(user.id),
        "email": user.email,
    }
    
    new_access_token = AuthService.create_access_token(new_token_data)
    new_refresh_token = AuthService.create_refresh_token(new_token_data)
    
    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    현재 사용자 정보 조회
    
    Args:
        current_user: 현재 사용자
        
    Returns:
        사용자 정보
    """
    return UserResponse.model_validate(current_user)
