# 게이트웨이 컨테이너

Azure Container Apps `api-gateway` 배포용 소스. Docker 빌드 컨텍스트는 `gateway-container/`로 제한한다
(리포지토리 루트의 다른 팀 코드가 이미지에 포함되지 않게).

## 사용 기술

```text
FastAPI + Uvicorn / Azure Container Apps + ACR
Auth: x-api-key (Entra External ID 도입 예정 — app/auth.py 가이드)
Classifier: internal cogdist Container App | Safety: Azure Content Safety + keyword fallback
RAG: Azure AI Search | LLM: Azure OpenAI gpt-4.1-mini | Speech: Azure Speech STT/TTS
Session: memory(개발) 또는 Azure Cosmos DB
```

## 폴더 구조

```text
gateway-container/
|-- API_CONTRACT.md            프론트/테스트 API 계약서 (기준 문서)
|-- docker-compose.yml         로컬 실행
|-- scripts/gateway_live_test.py   배포본 회귀 테스트 (text|transcript|tts|audio|session)
`-- services/
    |-- api-gateway/
    |   |-- Dockerfile / requirements.txt
    |   |-- tests/             v1 계약 테스트 13건 (외부 서비스·키 없이 실행)
    |   `-- app/
    |       |-- main.py        앱 생성 + 미들웨어 + 라우터
    |       |-- api.py         v1 엔드포인트 전체
    |       |-- settings.py    환경변수
    |       |-- auth.py        인증 (+ Entra 도입 가이드)
    |       |-- contracts.py   요청 Pydantic 모델
    |       |-- events.py      SSE 이벤트 payload
    |       |-- prompts.py     시스템 프롬프트 (사람 편집용)
    |       |-- ranking.py     RAG 재정렬
    |       |-- orchestrator/  respond_flow(흐름) + context_policy(정책) + crisis
    |       |-- services/      외부 서비스 어댑터 (컴포넌트당 파일 하나)
    |       `-- session/       세션 저장소 (memory/Cosmos) + 턴 빌더
    |-- common/                Azure OpenAI·Speech 클라이언트
    `-- retrieve/              Azure AI Search retriever
```

## 읽는 순서

```text
1. API_CONTRACT.md                        외부 계약(엔드포인트/SSE 이벤트)
2. app/api.py                             엔드포인트 목록
3. app/orchestrator/respond_flow.py       상담 한 턴의 전체 흐름 (핵심, ~110줄)
4. app/orchestrator/context_policy.py     라벨별 응답 정책 (사람 편집)
5. app/prompts.py                         답변 스타일/프롬프트 (사람 편집)
```

## 사람이 편집하는 지점

```text
답변 스타일/프롬프트   app/prompts.py                       PERSONA·STYLE_RULES·LABEL_GUIDANCE
라벨별 응답 정책       app/orchestrator/context_policy.py   POLICIES 테이블
위기 메시지/핫라인     app/orchestrator/crisis.py           + 위치 기반 DB 조회 작업 가이드
로그인(Entra) 도입     app/auth.py                          단계별 작업 가이드 주석
```

## 테스트

```bash
# 로컬 계약 테스트 (키 불필요) — 게이트웨이 수정 후 필수
cd gateway-container/services/api-gateway
pip install -r requirements-dev.txt
python -m pytest tests/ -q

# 배포본 회귀 테스트
python scripts/gateway_live_test.py all   # GW_FQDN, API_KEY_VALUE 필요
```

## 빌드·실행

```bash
# ACR 빌드 (리포지토리 루트에서, 컨텍스트는 반드시 gateway-container)
az acr build -r "$ACR" -t gateway:<TAG> -f services/api-gateway/Dockerfile gateway-container

# 로컬 실행 (.env 는 .env.example 참고)
docker compose -f gateway-container/docker-compose.yml up --build api-gateway
```

## 보안 메모

- 실제 키·비밀값 커밋 금지. 템플릿은 `.env.example`, 운영 키는 ACA SecretRef.
- 프론트엔드 코드에 게이트웨이 API 키 하드코딩 금지.

## 상태

- `/healthz`·`/v1/classify`·`/v1/respond`(text/transcript/audio/TTS)·crisis·Cosmos 세션 검증 PASS
- 프로토타입 경로(로컬 LLM, GPT-5 responses, model router, 로컬 retriever stub, legacy 분류기 정규화)는
  이 브랜치에서 삭제됨 — 필요하면 git 히스토리(070c799 이전)에서 복원
- Document Intelligence OCR 은 별도 브랜치 (`input_type=document` 예정)
