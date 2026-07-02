# Gateway Container 공유 안내서

이 문서는 `gateway-container/` 폴더를 공유하거나 검토할 때 필요한 요약 안내입니다.
실제 키와 비밀값은 포함하지 않습니다.

## 포함 범위

```text
app/               FastAPI 게이트웨이 애플리케이션 (컨테이너에 이 폴더만 들어감)
tests/             v1 계약 테스트 (외부 서비스·키 없이 로컬 실행)
scripts/           배포본 회귀 테스트 스크립트
API_CONTRACT.md    프론트엔드와 테스트용 API/SSE 계약서
.env.example       안전한 환경변수 템플릿
```

채팅 캡쳐 OCR 파이프라인의 원본은 리포지토리 루트 `di/`(DI 담당 팀원 작업물)이며,
게이트웨이는 복제본 `app/services/document_ocr.py` 를 사용합니다.

## 빌드 경로

리포지토리 루트 기준으로 실행합니다.

```bash
az acr build \
  -r "$ACR" \
  -t gateway:<TAG> \
  -f Dockerfile \
  gateway-container
```

`gateway-container/.dockerignore`는 기본 차단 방식입니다. 컨테이너 빌드에는 `requirements.txt`와 `app/`만 포함됩니다.

## 주요 API

자세한 계약은 `API_CONTRACT.md`를 기준으로 합니다.

```text
GET  /healthz
POST /v1/classify
POST /v1/respond    (text / transcript / audio / image 입력)
GET  /v1/sessions/{session_id}
```

테스트/운영 배포에서는 `/healthz`를 제외한 API에 `x-api-key` 헤더가 필요합니다.

## SSE 이벤트 요약

```text
meta            분류/세션 메타데이터
chunks          검색된 RAG 청크
token           스트리밍 LLM 텍스트 토큰
crisis          자해/위기 안전 배리어 응답
stt             speech-to-text 상태/결과
ocr             채팅 캡쳐 이미지 인식 상태/결과
tts             text-to-speech 상태/결과
input_required  입력은 수락됐지만 transcript/text가 부족한 상태
done            스트림 완료
```

## 테스트

```bash
# 로컬 계약 테스트 (키 불필요)
cd gateway-container && python -m pytest tests/ -q

# 배포본 회귀 테스트 (GW_FQDN, API_KEY_VALUE 필요)
python gateway-container/scripts/gateway_live_test.py all
```
