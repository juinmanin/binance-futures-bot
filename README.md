# 바이낸스 선물 반자동 매매봇

바이낸스 선물 거래를 위한 반자동 매매봇입니다. 퓨처차트와 래리 윌리엄스 변동성 돌파 전략을 통합하여 자동화된 거래를 지원합니다.

## 🚀 주요 기능

- **바이낸스 선물 API 연동**: Testnet 및 Mainnet 지원
- **JWT 기반 인증**: 안전한 사용자 인증 및 세션 관리
- **API 키 암호화**: AES-256 암호화로 안전한 키 저장
- **실시간 데이터**: WebSocket을 통한 실시간 시세 및 계좌 데이터
- **거래 관리**: 주문 실행, 취소, 포지션 관리
- **전략 설정**: 사용자 정의 거래 전략 구성

## 📋 기술 스택

### 백엔드
- **Python 3.10+**
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **SQLAlchemy 2.0**: ORM 및 데이터베이스 관리
- **Alembic**: 데이터베이스 마이그레이션

### 데이터베이스
- **PostgreSQL**: 거래 기록 및 사용자 데이터
- **Redis**: 캐싱 및 실시간 데이터
- **RabbitMQ**: 메시지 큐 및 작업 관리

### 보안
- **JWT**: JSON Web Token 기반 인증
- **bcrypt**: 비밀번호 해싱
- **AES-256**: API 키 암호화

### 분석 라이브러리
- **TA-Lib**: 기술적 분석
- **pandas**: 데이터 처리
- **numpy**: 수치 계산

### 인프라
- **Docker**: 컨테이너화
- **Docker Compose**: 멀티 컨테이너 관리

## 🏗️ 프로젝트 구조

```
binance-futures-bot/
├── docker/                     # Docker 설정
│   ├── Dockerfile
│   └── docker-compose.yml
├── src/                        # 소스 코드
│   ├── main.py                # FastAPI 앱 엔트리포인트
│   ├── config/                # 환경 설정
│   │   └── settings.py
│   ├── api/                   # API 라우트
│   │   ├── routes/
│   │   │   ├── auth.py       # 인증
│   │   │   ├── trading.py    # 거래
│   │   │   └── health.py     # 헬스 체크
│   │   └── dependencies.py   # FastAPI 의존성
│   ├── core/                  # 핵심 기능
│   │   ├── security.py       # 암호화
│   │   └── exceptions.py     # 예외 처리
│   ├── services/              # 비즈니스 로직
│   │   ├── binance/          # 바이낸스 API
│   │   │   ├── client.py
│   │   │   ├── websocket.py
│   │   │   └── endpoints.py
│   │   └── auth/             # 인증 서비스
│   │       └── service.py
│   ├── models/                # 데이터 모델
│   │   ├── database.py       # SQLAlchemy 모델
│   │   └── schemas.py        # Pydantic 스키마
│   └── db/                    # 데이터베이스
│       ├── session.py
│       └── repositories/
├── tests/                     # 테스트
├── alembic/                   # DB 마이그레이션
├── .env.example              # 환경 변수 예제
├── requirements.txt          # Python 의존성
└── README.md
```

## 🚀 시작하기

### 사전 요구사항

- Docker 및 Docker Compose 설치
- 바이낸스 Testnet API 키 ([등록 링크](https://testnet.binancefuture.com/))

### 1. 저장소 클론

```bash
git clone https://github.com/juinmanin/binance-futures-bot.git
cd binance-futures-bot
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 필요한 설정을 입력하세요:

```env
# 바이낸스 API 키 (Testnet)
BINANCE_API_KEY=your-testnet-api-key
BINANCE_API_SECRET=your-testnet-api-secret

# 보안 키 (32바이트 이상)
SECRET_KEY=your-secret-key-here
MASTER_ENCRYPTION_KEY=your-32-byte-encryption-key-here
JWT_SECRET_KEY=your-jwt-secret-key
```

### 3. Docker Compose로 실행

```bash
cd docker
docker-compose up -d
```

서비스가 시작되면 다음 포트에서 접근할 수 있습니다:
- **FastAPI**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **RabbitMQ 관리 UI**: http://localhost:15672 (guest/guest)

### 4. 데이터베이스 마이그레이션

```bash
# 컨테이너 내부에서 실행
docker exec -it binance-bot-app alembic upgrade head
```

## 📚 API 문서

서버가 실행 중일 때 다음 URL에서 자동 생성된 API 문서를 확인할 수 있습니다:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 주요 엔드포인트

#### 인증
- `POST /api/v1/auth/register` - 회원가입
- `POST /api/v1/auth/login` - 로그인
- `POST /api/v1/auth/refresh` - 토큰 갱신
- `GET /api/v1/auth/me` - 현재 사용자 정보

#### 거래
- `GET /api/v1/trading/balance` - 계좌 잔고 조회
- `GET /api/v1/trading/positions` - 포지션 조회
- `POST /api/v1/trading/order` - 주문 실행
- `DELETE /api/v1/trading/order/{symbol}/{order_id}` - 주문 취소
- `POST /api/v1/trading/leverage/{symbol}` - 레버리지 설정

#### 시스템
- `GET /health` - 헬스 체크

## 🔒 보안

### API 키 보안
- API 키는 AES-256 암호화로 데이터베이스에 저장
- 마스터 암호화 키는 환경 변수로만 관리 (코드에 포함하지 않음)

### 인증 보안
- JWT 기반 인증 (액세스 토큰 + 리프레시 토큰)
- 비밀번호는 bcrypt로 해싱
- 2FA 지원 준비 (향후 구현)

### 네트워크 보안
- CORS 설정으로 허용된 오리진만 접근 가능
- HTTPS 사용 권장 (프로덕션)

## 🧪 테스트

### 테스트 실행

```bash
# 로컬 환경
pip install -r requirements-dev.txt
pytest

# 커버리지 포함
pytest --cov=src --cov-report=html

# Docker 환경
docker exec -it binance-bot-app pytest
```

### 테스트 종류
- 단위 테스트: 바이낸스 API 클라이언트, 암호화
- 통합 테스트: API 엔드포인트
- 헬스 체크 테스트

## 📝 개발

### 로컬 개발 환경 설정

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements-dev.txt

# 개발 서버 실행
uvicorn src.main:app --reload
```

### 코드 품질

```bash
# 코드 포매팅
black src tests

# 린팅
flake8 src tests
pylint src

# 타입 체크
mypy src
```

### 데이터베이스 마이그레이션

```bash
# 마이그레이션 생성
alembic revision --autogenerate -m "설명"

# 마이그레이션 적용
alembic upgrade head

# 롤백
alembic downgrade -1
```

## 🗺️ 로드맵

### 1단계: 기본 인프라 구축 ✅
- [x] Docker 환경 구성
- [x] 바이낸스 API 연동
- [x] 사용자 인증 시스템
- [x] 데이터베이스 설계
- [x] 기본 API 엔드포인트

### 2단계: 전략 구현 (예정)
- [ ] 래리 윌리엄스 변동성 돌파 전략
- [ ] 퓨처차트 자금 흐름 분석
- [ ] RSI 필터링
- [ ] 백테스팅 시스템

### 3단계: 자동 거래 (예정)
- [ ] 시그널 생성 및 실행
- [ ] 리스크 관리
- [ ] 포지션 관리
- [ ] 손익 계산

### 4단계: 모니터링 및 알림 (예정)
- [ ] 실시간 대시보드
- [ ] 텔레그램 알림
- [ ] 로그 및 모니터링
- [ ] 성과 분석

## 🤝 기여

기여를 환영합니다! 이슈나 풀 리퀘스트를 자유롭게 제출해주세요.

## ⚠️ 면책 조항

이 소프트웨어는 교육 및 연구 목적으로 제공됩니다. 실제 거래에 사용할 경우 발생하는 손실에 대해 개발자는 책임지지 않습니다. 항상 Testnet에서 충분히 테스트한 후 실제 거래에 사용하시기 바랍니다.

## 📄 라이선스

MIT License

## 📧 문의

이슈 트래커를 통해 질문이나 버그를 보고해주세요.