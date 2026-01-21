"""인증 서비스"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.exceptions import AuthenticationException
from src.models.database import User
from src.models.schemas import UserCreate, TokenData


# 비밀번호 해싱 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """인증 서비스 클래스"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        비밀번호 검증
        
        Args:
            plain_password: 평문 비밀번호
            hashed_password: 해시된 비밀번호
            
        Returns:
            검증 성공 여부
        """
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        비밀번호 해싱
        
        Args:
            password: 평문 비밀번호
            
        Returns:
            해시된 비밀번호
        """
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        액세스 토큰 생성
        
        Args:
            data: 토큰에 포함할 데이터
            expires_delta: 만료 시간 (기본: 30분)
            
        Returns:
            JWT 토큰
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.access_token_expire_minutes
            )
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """
        리프레시 토큰 생성
        
        Args:
            data: 토큰에 포함할 데이터
            
        Returns:
            JWT 토큰
        """
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        return encoded_jwt
    
    @staticmethod
    async def verify_token(token: str, token_type: str = "access") -> TokenData:
        """
        토큰 검증
        
        Args:
            token: JWT 토큰
            token_type: 토큰 타입 (access 또는 refresh)
            
        Returns:
            토큰 데이터
            
        Raises:
            AuthenticationException: 토큰이 유효하지 않은 경우
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            
            # 토큰 타입 확인
            if payload.get("type") != token_type:
                raise AuthenticationException("Invalid token type")
            
            user_id: str = payload.get("sub")
            email: str = payload.get("email")
            
            if user_id is None:
                raise AuthenticationException("Invalid token")
            
            return TokenData(user_id=UUID(user_id), email=email)
            
        except JWTError as e:
            raise AuthenticationException(f"Token validation failed: {str(e)}")
    
    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """
        이메일로 사용자 조회
        
        Args:
            db: 데이터베이스 세션
            email: 이메일
            
        Returns:
            사용자 객체 또는 None
        """
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
        """
        ID로 사용자 조회
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            
        Returns:
            사용자 객체 또는 None
        """
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        """
        사용자 생성
        
        Args:
            db: 데이터베이스 세션
            user_data: 사용자 생성 데이터
            
        Returns:
            생성된 사용자 객체
        """
        # 이메일 중복 확인
        existing_user = await AuthService.get_user_by_email(db, user_data.email)
        if existing_user:
            raise AuthenticationException("Email already registered")
        
        # 비밀번호 해싱
        hashed_password = AuthService.get_password_hash(user_data.password)
        
        # 사용자 생성
        user = User(
            email=user_data.email,
            hashed_password=hashed_password,
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        return user
    
    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> Optional[User]:
        """
        사용자 인증
        
        Args:
            db: 데이터베이스 세션
            email: 이메일
            password: 비밀번호
            
        Returns:
            인증된 사용자 객체 또는 None
        """
        user = await AuthService.get_user_by_email(db, email)
        
        if not user:
            return None
        
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        
        if not user.is_active:
            return None
        
        return user
