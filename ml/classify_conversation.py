"""
classify_conversation.py - 카톡 OCR 결과(conversation_output.json)에 인지왜곡 라벨을 붙이는 스크립트

kakao_ocr_pipeline.py 실행 후 나온 conversation_output.json을 읽어서,
각 메시지(content)를 CogDistClassifier(predict.py)에 통과시켜 인지왜곡 라벨을 붙입니다.

사용 방침 (권장):
    - '나'의 발화만 분류 (자기 서술적 인지왜곡 탐지가 목적인 경우 보통 이렇게 함)
    - 상대방 발화까지 분류하려면 --classify_all 옵션 사용

실행 예:
    python classify_conversation.py \
        --conversation conversation_output.json \
        --model_dir outputs/multi_large_v2/best \
        --output conversation_classified.json
"""

import argparse
import json

from predict import CogDistClassifier


def classify_conversation(conversation: list, classifier: CogDistClassifier, classify_all: bool = False) -> list:
    results = []
    for turn in conversation:
        entry = dict(turn)  # 원본 필드(speaker, content, time) 유지

        should_classify = classify_all or (turn["speaker"] == "나")

        if should_classify:
            pred = classifier.predict(turn["content"])
            entry["cogdist_labels"] = [
                {"label": label, "score": round(score, 4)} for label, score in pred["labels"]
            ]
        else:
            entry["cogdist_labels"] = None  # 분류 대상 아님 (상대방 발화, classify_all=False인 경우)

        results.append(entry)

    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--conversation", default="conversation_output.json")
    p.add_argument("--model_dir", default="outputs/multi_large_v2/best")
    p.add_argument("--output", default="conversation_classified.json")
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--classify_all", action="store_true", help="상대방 발화까지 전부 분류 (기본: '나'만 분류)")
    args = p.parse_args()

    with open(args.conversation, "r", encoding="utf-8") as f:
        conversation = json.load(f)

    print(f"[1/2] 모델 로딩 중... ({args.model_dir})")
    classifier = CogDistClassifier(args.model_dir, threshold=args.threshold)

    print(f"[2/2] {len(conversation)}개 메시지 분류 중...")
    classified = classify_conversation(conversation, classifier, classify_all=args.classify_all)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(classified, f, ensure_ascii=False, indent=2)

    print(f"\n완료! {args.output} 에 저장됨\n")
    for turn in classified:
        time_str = turn["time"] or "(시간 미확인)"
        label_str = (
            ", ".join(f"{l['label']}({l['score']*100:.0f}%)" for l in turn["cogdist_labels"])
            if turn["cogdist_labels"] else "-"
        )
        print(f"[{time_str}] {turn['speaker']}: {turn['content']}")
        print(f"    -> {label_str}")


if __name__ == "__main__":
    main()