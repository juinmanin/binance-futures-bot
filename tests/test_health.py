"""헬스 체크 엔드포인트 테스트"""
import pytest
from httpx import AsyncClient
from src.main import app


@pytest.mark.asyncio
async def test_health_check():
    """헬스 체크 엔드포인트 테스트"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_root_endpoint():
    """루트 엔드포인트 테스트"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["version"] == "1.0.0"
    assert data["docs"] == "/docs"
