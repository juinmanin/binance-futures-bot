"""헬스 체크 라우트"""
from datetime import datetime
from fastapi import APIRouter

from src.models.schemas import HealthCheck

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """
    헬스 체크 엔드포인트
    
    Returns:
        헬스 체크 응답
    """
    return HealthCheck(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
    )
