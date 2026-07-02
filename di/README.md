# DI — KakaoTalk OCR Pipeline

KakaoTalk screenshot → text extraction → structured conversation log, using **Azure AI Document Intelligence**.

Part of the **생각갈피 (MindMark)** CBT chatbot multimodal input pipeline. The output of this pipeline feeds directly into the cognitive distortion classifier in `ml/`.

---

## Directory Structure

```
di/
├── kakao_ocr_pipeline.py   # Main OCR + parsing pipeline
├── .env                    # Local credentials (not committed)
└── di_test_image.jpeg      # Sample KakaoTalk screenshot for testing (not committed)
```

---

## How It Works

```
KakaoTalk screenshot (.jpeg / .png)
        ↓
Azure Document Intelligence (prebuilt-read)
        ↓  text lines + bounding box coordinates (polygon)
Line classifier
        ↓  message / timestamp / sender_name
Speaker assignment (x-coordinate midpoint)
        ↓  "나" (right side) / sender name (left side)
Timestamp matching (y-coordinate proximity)
        ↓
conversation_output.json
```

### Speaker Detection Logic

KakaoTalk places the user's own messages on the **right side** of the screen and the other person's messages on the **left side**. The pipeline uses the x-coordinate of each text line's bounding box to automatically assign the speaker:

- `x_left < page_width / 2` → other person (상대방)
- `x_left ≥ page_width / 2` → me (나)

### Timestamp Matching Logic

Timestamps ("오전 11:15", "오후 3:42") are matched to their nearest message by **y-coordinate proximity**, not reading order. This correctly handles cases where the timestamp appears before the message text in the OCR output (common for right-aligned messages).

---

## Setup

### 1. Install dependencies

```bash
pip install azure-ai-documentintelligence python-dotenv
```

### 2. Configure `.env`

Create a `.env` file in this folder:

```dotenv
DOCINTEL_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
DOCINTEL_KEY=<your-key>
DOCINTEL_API_VERSION=2024-11-30
DOCINTEL_MODEL_ID=prebuilt-read
```

> The Azure Document Intelligence resource used in this project is `team3-doc-intel` (Korea Central, Free F0 tier, resource group `10ai_2nd_team3`).

---

## Usage

### Run with default test image

```bash
python kakao_ocr_pipeline.py
```

Defaults to `di_test_image.jpeg` in the same folder.

### Run with a specific image

```bash
python kakao_ocr_pipeline.py kakao_capture.jpeg
```

### Output

Prints the reconstructed conversation to the terminal and saves `conversation_output.json`:

```
[오전 11:15] 감동받은 어피치: 야 오늘 과제 제출했어?
[오전 11:15] 나: 응 아까 냈어.
[오전 11:15] 감동받은 어피치: 오 다행이다 크크
...
```

`conversation_output.json` format:

```json
[
  {
    "speaker": "감동받은 어피치",
    "content": "야 오늘 과제 제출했어?",
    "time": "오전 11:15"
  },
  {
    "speaker": "나",
    "content": "응 아까 냈어.",
    "time": "오전 11:15"
  }
]
```

---

## Key Functions

| Function | Description |
|---|---|
| `analyze_image(image_path)` | Calls Azure Document Intelligence API, returns page width/height and line list with polygons |
| `is_time_stamp(text)` | Detects Korean time strings (`오전/오후 HH:MM`) via regex |
| `classify_speaker(polygon, page_width)` | Assigns speaker based on x-coordinate midpoint |
| `parse_lines(page_data, known_sender_names)` | Classifies each OCR line as `message`, `timestamp`, or `sender_name` |
| `build_conversation(parsed_lines)` | Reconstructs ordered conversation with speaker + timestamp matched per message |
| `run_pipeline(image_path, known_sender_names)` | End-to-end entry point: image → `conversation_output.json` |

---

## Customizing for Different Chats

By default, the pipeline is configured for a test conversation. To use with a different KakaoTalk screenshot, update the `known_names` set in `__main__` to match the other person's display name as it appears at the top of their chat bubbles:

```python
known_names = {"친구이름"}  # Replace with the actual sender name shown in the screenshot
run_pipeline(image_path, known_sender_names=known_names)
```

---

## Integration with Cognitive Distortion Classifier

The `conversation_output.json` produced by this pipeline is the direct input to `ml/classify_conversation.py`:

```bash
# Step 1: OCR
python di/kakao_ocr_pipeline.py kakao_capture.jpeg

# Step 2: Classification
python ml/classify_conversation.py \
    --conversation di/conversation_output.json \
    --model_dir ml/outputs/multi_large/best \
    --output conversation_classified.json
```

---

## Requirements

```
azure-ai-documentintelligence
python-dotenv
```