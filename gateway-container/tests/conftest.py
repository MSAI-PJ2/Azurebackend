"""pytest 공용 설정 — 컨테이너(/app)와 동일하게 gateway-container 를 sys.path 에 올린다.

실행 방법 (gateway-container 에서): python -m pytest tests/ -q
"""
import sys
from pathlib import Path

_GATEWAY_DIR = Path(__file__).resolve().parents[1]   # gateway-container (app 패키지의 부모)
if str(_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(_GATEWAY_DIR))
