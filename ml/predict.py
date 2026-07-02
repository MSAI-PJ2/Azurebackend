"""
predict.py  -  학습한 멀티라벨 모델로 새 문장 분류하기 (multi_large_v2)

멀티라벨 분류이므로 softmax(top-k) 대신 sigmoid + threshold 방식을 사용
- 각 라벨(12개: 10개 인지왜곡 + 정상 + 불충분)은 독립적으로 0~1 확률을 가짐
- threshold.json에 저장된 값(예: 0.55)을 넘는 라벨만 최종 예측으로 채택
- 하나도 threshold를 못 넘으면 가장 높은 라벨 1개를 fallback으로 반환 (완전히 빈 결과 방지)

실행 예:
  python predict.py --model_dir outputs/multi_large/best \
      --text "이번 시험 한 번 망쳤으니 난 완전히 실패자야"
"""

import argparse
import json
import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification


def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


EXCLUSIVE_LABELS = {"정상", "불충분"}

def load_threshold(model_dir: str, default: float = 0.55) -> float:
    """model_dir 안의 threshold.json에서 threshold 값을 읽어옴. 없으면 default 사용."""
    threshold_path = os.path.join(model_dir, "threshold.json")
    if os.path.exists(threshold_path):
        with open(threshold_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("threshold", default)
    return default


class CogDistClassifier:
    """
    인지왜곡 멀티라벨 분류기 (multi_large_v2 기반).
    한 번 로드해서 여러 문장을 반복 예측할 때 효율적으로 쓰기 위한 클래스.
    """

    def __init__(self, model_dir: str, threshold: float = None, max_length: int = 160):
        self.device = get_device()
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(self.device)
        self.model.eval()
        self.max_length = max_length
        self.threshold = threshold if threshold is not None else load_threshold(model_dir)
        self.id2label = self.model.config.id2label

    def predict(self, text: str) -> dict:
        """
        text -> {
            "labels": [(라벨명, 확률), ...],   # threshold를 넘은 라벨들 (확률 내림차순)
            "all_scores": {라벨명: 확률, ...},  # 전체 12개 라벨 확률 (참고/디버깅용)
        }
        """
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=self.max_length
        ).to(self.device)

        with torch.no_grad():
            logits = self.model(**inputs).logits
        probs = torch.sigmoid(logits)[0]  # 멀티라벨 -> sigmoid (softmax 아님)

        all_scores = {
            self.id2label[i]: probs[i].item() for i in range(len(self.id2label))
        }

        primary = max(all_scores, key=all_scores.get)

        # 정상/불충분은 라우팅 라벨이므로 인지왜곡 다중 라벨과 배타적으로 처리한다.
        # primary가 정상/불충분이면 그 라벨 하나만 채택하고,
        # primary가 인지왜곡이면 정상/불충분은 threshold를 넘더라도 채택하지 않는다.
        if primary in EXCLUSIVE_LABELS:
            passed = [(primary, all_scores[primary])]
        else:
            passed = [
                (label, score)
                for label, score in all_scores.items()
                if label not in EXCLUSIVE_LABELS and score >= self.threshold
            ]
            if primary not in [label for label, _ in passed]:
                passed.append((primary, all_scores[primary]))
            passed.sort(key=lambda x: x[1], reverse=True)

        return {"primary": primary, "labels": passed, "all_scores": all_scores, "threshold": self.threshold}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model_dir", default="outputs/multi_large/best")
    p.add_argument("--text", required=True)
    p.add_argument("--threshold", type=float, default=None, help="지정하지 않으면 threshold.json 값 사용")
    args = p.parse_args()

    classifier = CogDistClassifier(args.model_dir, threshold=args.threshold)
    result = classifier.predict(args.text)

    print(f"\n입력: {args.text}")
    print(f"threshold: {classifier.threshold}\n")
    print("채택된 라벨 (threshold 이상):")
    for label, score in result["labels"]:
        print(f"  {label:<20} {score*100:5.1f}%")

    print("\n전체 라벨 확률:")
    for label, score in sorted(result["all_scores"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {label:<20} {score*100:5.1f}%")


if __name__ == "__main__":
    main()