"""FastAPI 애플리케이션 엔트리포인트"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.config import settings
from src.db import init_db, close_db
from src.api.routes import health, auth, trading


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # Startup
    logger.info("Starting up application...")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    try:
        await close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Failed to close database: {e}")


# FastAPI 앱 생성
app = FastAPI(
    title=settings.app_name,
    description="바이낸스 선물 반자동 매매봇 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(trading.router)


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "바이낸스 선물 반자동 매매봇 API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
