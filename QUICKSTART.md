# 빠른 시작 가이드

## 1. 환경 준비

### 필요한 것
- Docker Desktop 설치
- 바이낸스 Testnet 계정 및 API 키
  - 가입: https://testnet.binancefuture.com/

## 2. 프로젝트 설정

### 저장소 클론
```bash
git clone https://github.com/juinmanin/binance-futures-bot.git
cd binance-futures-bot
```

### 환경 변수 설정
```bash
cp .env.example .env
```

`.env` 파일을 열어 다음을 수정하세요:
```env
# 바이낸스 API 키 (필수!)
BINANCE_API_KEY=당신의-testnet-api-key
BINANCE_API_SECRET=당신의-testnet-api-secret

# 보안 키 생성 (필수!)
SECRET_KEY=$(openssl rand -hex 32)
MASTER_ENCRYPTION_KEY=$(openssl rand -hex 16)
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

## 3. Docker로 실행

```bash
cd docker
docker-compose up -d
```

서비스가 시작되면:
- API: http://localhost:8000
- API 문서: http://localhost:8000/docs
- RabbitMQ 관리: http://localhost:15672 (guest/guest)

## 4. 데이터베이스 마이그레이션

```bash
docker exec -it binance-bot-app alembic upgrade head
```

## 5. API 테스트

### 헬스 체크
```bash
curl http://localhost:8000/health
```

예상 응답:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-21T16:50:00.000Z",
  "version": "1.0.0"
}
```

### 회원가입
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "securepassword123"
  }'
```

### 로그인
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "securepassword123"
  }'
```

응답에서 `access_token`을 저장하세요:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

### 잔고 조회
```bash
# ACCESS_TOKEN을 위에서 받은 토큰으로 교체
curl http://localhost:8000/api/v1/trading/balance \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

## 6. API 문서 확인

브라우저에서 http://localhost:8000/docs 를 열어 전체 API를 확인하고 테스트할 수 있습니다.

## 7. 개발 모드

로컬에서 개발하려면:

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements-dev.txt

# 개발 서버 실행
uvicorn src.main:app --reload
```

## 8. 테스트 실행

```bash
# 모든 테스트 실행
pytest

# 커버리지 포함
pytest --cov=src --cov-report=html

# Docker에서 테스트
docker exec -it binance-bot-app pytest
```

## 9. 서비스 중지

```bash
cd docker
docker-compose down
```

데이터까지 삭제하려면:
```bash
docker-compose down -v
```

## 10. 문제 해결

### 포트 충돌
다른 서비스가 이미 포트를 사용 중이면 `docker-compose.yml`에서 포트를 변경하세요.

### 데이터베이스 연결 오류
PostgreSQL 컨테이너가 완전히 시작될 때까지 잠시 기다리세요 (약 10초).

### API 키 오류
바이낸스 Testnet API 키가 올바른지 확인하세요.

## 11. 다음 단계

1. API 문서를 읽고 사용 가능한 엔드포인트를 확인하세요
2. 전략 설정을 구성하세요 (2단계에서 구현 예정)
3. 백테스팅을 실행하세요 (2단계에서 구현 예정)

## 도움말

- 전체 문서: `README.md`
- 이슈 보고: GitHub Issues
- API 문서: http://localhost:8000/docs
