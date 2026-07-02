"""컨테이너와 동일한 import 배치(app/common/retrieve 나란히)를 로컬에서 재현.

실행 (services/api-gateway 에서): python -m pytest tests/ -q
"""
import sys
from pathlib import Path

_API_GATEWAY_DIR = Path(__file__).resolve().parents[1]   # services/api-gateway
for path in (str(_API_GATEWAY_DIR.parent), str(_API_GATEWAY_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)
