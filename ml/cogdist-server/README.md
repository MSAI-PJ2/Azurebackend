# CogDist v2 Container

`ml/outputs/multi_large/best`의 RoBERTa-large multi-label 모델을 서비스하기 위한 cogdist API 컨테이너입니다.

## 핵심 변경

multi-label 모드에서도 `정상` / `불충분`을 배타 라벨로 처리합니다.

규칙:

1. `primary` 라벨은 항상 `selected=true`
2. `primary`가 `정상` 또는 `불충분`이면 해당 라벨 하나만 `selected=true`
3. `primary`가 인지왜곡 라벨이면 `정상` / `불충분`은 `selected=false`

## API 계약

기존 게이트웨이가 호출하던 계약을 유지합니다.

```text
GET  /healthz
GET  /readyz
POST /v1/predict
POST /v1/batch-predict
```

`POST /v1/predict` 요청:

```json
{"text":"사람들 앞에 서면 다 망칠 것 같아요", "threshold":0.55}
```

응답은 기존 게이트웨이 호환을 위해 전체 라벨 배열을 유지합니다.
`selected` 값만 정책에 맞게 정리됩니다.

```json
{
  "text": "...",
  "mode": "multi_label",
  "model": "klue/roberta-large",
  "model_version": "multi_large_v2",
  "threshold": 0.55,
  "primary": "불충분",
  "labels": [
    {"label":"'해야 한다' 진술", "score":0.0015, "selected":false},
    {"label":"감정적 추론", "score":0.0046, "selected":false},
    {"label":"불충분", "score":0.5244, "selected":true},
    {"label":"흑백 사고", "score":0.0155, "selected":false}
  ]
}
```

## Azure Container Apps 배포 방식

현재 운영 구조처럼 Azure Files를 `/models/cogdist`에 mount하는 nobake 방식을 기본으로 합니다.
컨테이너 이미지에는 모델 파일을 굽지 않습니다. 따라서 빌드 컨텍스트는 `ml/cogdist-server/`만 사용합니다.

필수 환경변수:

```text
MODEL_PATH=/models/cogdist
MODEL_ID=klue/roberta-large
MODEL_VERSION=multi_large_v2
CLASSIFY_MODE=multi_label
DEFAULT_THRESHOLD=0.55
MAX_LENGTH=160
```

## ACR 빌드 예시

repo root에서 실행:

```bash
TAG=cogdist-v2-exclusive-20260702
az acr build \
  -r "$ACR" \
  -t cogdist:$TAG \
  ml/cogdist-server
```

또는 `ml/cogdist-server/`로 이동 후:

```bash
cd ml/cogdist-server
az acr build -r "$ACR" -t cogdist:$TAG .
```

## ACA 업데이트 예시

```bash
az containerapp update \
  -g "$RG" \
  -n cogdistmodel \
  --image "$ACR.azurecr.io/cogdist:$TAG" \
  --set-env-vars \
    MODEL_PATH=/models/cogdist \
    MODEL_ID=klue/roberta-large \
    MODEL_VERSION=multi_large_v2 \
    CLASSIFY_MODE=multi_label \
    DEFAULT_THRESHOLD=0.55 \
    MAX_LENGTH=160
```

모델 파일은 기존처럼 Azure Files 볼륨 `modelstore`, subPath `v2`, mountPath `/models/cogdist`를 유지합니다.


