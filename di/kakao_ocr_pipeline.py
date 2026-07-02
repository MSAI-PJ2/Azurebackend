"""
카카오톡 캡쳐 이미지 -> Azure Document Intelligence OCR -> 대화 로그(JSON) 변환 파이프라인

실행 (이미지 경로를 지정):
    python kakao_ocr_pipeline.py di_test_image.jpeg

또는 이미지 경로 없이 실행하면 같은 폴더의 di_test_image.jpeg를 자동으로 사용:
    python kakao_ocr_pipeline.py
"""

import os
import sys
import json
import re
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

# .env 파일 자동 로드 (같은 폴더에 .env가 있으면 자동으로 읽어서 환경변수로 등록)
load_dotenv()


# ---------------------------------------------------------
# 1. Azure Document Intelligence 호출
# ---------------------------------------------------------
def analyze_image(image_path: str) -> dict:
    endpoint = os.environ["DOCINTEL_ENDPOINT"]
    key = os.environ["DOCINTEL_KEY"]

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

    with open(image_path, "rb") as f:
        poller = client.begin_analyze_document("prebuilt-read", body=f)
    result = poller.result()

    # SDK 객체를 다음 단계에서 다루기 쉬운 dict 형태로 변환
    page = result.pages[0]
    return {
        "width": page.width,
        "height": page.height,
        "lines": [
            {"content": line.content, "polygon": line.polygon}
            for line in page.lines
        ],
    }


# ---------------------------------------------------------
# 2. 라인 분류 (메시지 / 시간 / 발신자 이름)
# ---------------------------------------------------------
def is_time_stamp(text: str) -> bool:
    return bool(re.fullmatch(r"(오전|오후)\s*\d{1,2}:\d{2}", text.strip()))


def classify_speaker(polygon, page_width: int) -> str:
    x_left = polygon[0]
    midpoint = page_width / 2
    return "상대방" if x_left < midpoint else "나"


def parse_lines(page_data: dict, known_sender_names: set) -> list:
    """
    known_sender_names: 미리 알고 있는 상대방 이름 목록.
    카톡 캡쳐 상단에 뜨는 이름(예: '감동받은 어피치')을 지정해두면
    이름 라벨과 실제 메시지를 더 정확히 구분할 수 있음.
    """
    page_width = page_data["width"]
    parsed = []

    for line in page_data["lines"]:
        content = line["content"]
        polygon = line["polygon"]

        if is_time_stamp(content):
            parsed.append({"type": "timestamp", "speaker": None,
                            "content": content, "polygon": polygon})
        elif content.strip() in known_sender_names:
            parsed.append({"type": "sender_name", "speaker": "상대방",
                            "content": content, "polygon": polygon})
        else:
            speaker = classify_speaker(polygon, page_width)
            parsed.append({"type": "message", "speaker": speaker,
                            "content": content, "polygon": polygon})

    return parsed


# ---------------------------------------------------------
# 3. 대화 로그로 재구성 (시간 매칭 포함)
# ---------------------------------------------------------
def polygon_center_y(polygon):
    ys = polygon[1::2]
    return sum(ys) / len(ys)


def build_conversation(parsed_lines: list) -> list:
    messages = []
    current_name = None

    for item in parsed_lines:
        if item["type"] == "sender_name":
            current_name = item["content"]
        elif item["type"] == "message":
            speaker_name = "나" if item["speaker"] == "나" else (current_name or "상대방")
            messages.append({
                "speaker": speaker_name,
                "content": item["content"],
                "time": None,
                "_y": polygon_center_y(item["polygon"]),
            })

    timestamps = [
        {"content": item["content"], "_y": polygon_center_y(item["polygon"])}
        for item in parsed_lines if item["type"] == "timestamp"
    ]

    for ts in timestamps:
        candidates = [m for m in messages if m["time"] is None]
        if not candidates:
            break
        closest = min(candidates, key=lambda m: abs(m["_y"] - ts["_y"]))
        closest["time"] = ts["content"]

    for m in messages:
        m.pop("_y", None)

    return messages


# ---------------------------------------------------------
# 4. 메인 실행
# ---------------------------------------------------------
def run_pipeline(image_path: str, known_sender_names: set = None):
    known_sender_names = known_sender_names or set()

    print(f"[1/3] '{image_path}' 분석 중...")
    page_data = analyze_image(image_path)

    print("[2/3] 라인 분류 중...")
    parsed = parse_lines(page_data, known_sender_names)

    print("[3/3] 대화 로그 재구성 중...")
    conversation = build_conversation(parsed)

    output_path = "conversation_output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(conversation, f, ensure_ascii=False, indent=2)

    print(f"\n완료! {output_path} 에 저장됨\n")
    for turn in conversation:
        time_str = turn["time"] or "(시간 미확인)"
        print(f"[{time_str}] {turn['speaker']}: {turn['content']}")

    return conversation


if __name__ == "__main__":
    # 인자 없이 실행하면 같은 폴더의 di_test_image.jpeg를 기본값으로 사용
    if len(sys.argv) < 2:
        image_path = "di_test_image.jpeg"
        print(f"이미지 경로 미지정 -> 기본값 사용: {image_path}")
    else:
        image_path = sys.argv[1]

    # 카톡 캡쳐 상단에 뜨는 상대방 이름을 여기 미리 등록해두면 인식 정확도가 올라감
    known_names = {"감동받은 어피치"}

    run_pipeline(image_path, known_sender_names=known_names)