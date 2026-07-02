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

## 용어 미니 사전 (비전공자용)

```text
게이트웨이     프론트엔드와 여러 Azure 서비스 사이에서 교통정리를 하는 중간 서버
엔드포인트     서버가 받는 요청 주소 (예: POST /v1/respond). 전체 목록은 app/api.py
SSE/스트리밍   답변을 완성 후 한 번에 주지 않고 생성되는 대로 조각조각 보내는 방식
이벤트         스트리밍으로 보내는 메시지 조각. type 필드로 구분 (meta/token/done 등)
세션 / 턴      대화방 하나 / 그 안의 발화 하나 (사용자 또는 AI)
RAG            답변 전에 관련 자료를 검색해 프롬프트에 넣어주는 기법
시스템 프롬프트 AI 에게 답변 전에 주는 지시문 (말투·역할·금지사항) — app/prompts.py
어댑터         외부 서비스의 복잡한 호출법을 감추는 중간층 — app/services/
async/await    기다리는 동안 다른 요청을 처리할 수 있게 하는 파이썬 문법
yield          함수가 끝나지 않은 채 값을 하나씩 내보내는 문법 (스트리밍의 재료)
환경변수(env)  코드 밖에서 주입하는 설정값 (키·주소 등) — app/settings.py 에서 읽음
```

모든 파일 상단에 `[역할] 설명` docstring 이 있고, 논리 단계마다 한국어 주석이 있다.
코드가 처음이라면 아래 순서로 주석만 따라 읽어도 전체 구조가 잡히도록 작성했다.

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
