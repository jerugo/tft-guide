"""TFT Guide 설정"""
import os
import pathlib

# LLM API 설정
LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama3")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))

# 화면 캡처 설정
CAPTURE_INTERVAL = float(os.environ.get("CAPTURE_INTERVAL", "2.0"))
DETECTION_THRESHOLD = float(os.environ.get("DETECTION_THRESHOLD", "0.7"))
TFT_WINDOW_TITLES = ["TFT", "Teamfight Tactics", "League of Legends"]

# 서버 설정
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "5000"))

# 데이터 경로
DATA_DIR = pathlib.Path(__file__).parent / "data"
CHAMPIONS_JSON = DATA_DIR / "champions.json"
META_JSON = DATA_DIR / "meta.json"
TEMPLATES_DIR = DATA_DIR / "templates"
ICONS_DIR = DATA_DIR / "icons"

# TFT 챔피언 풀 (코스트별 총 복사본 수)
CHAMPION_POOL = {1: 29, 2: 22, 3: 18, 4: 12, 5: 10}

# 레벨별 상점 확률 (레벨 2~10, 코스트 1~5)
SHOP_ODDS = {
    2:  [1.00, 0.00, 0.00, 0.00, 0.00],
    3:  [0.75, 0.25, 0.00, 0.00, 0.00],
    4:  [0.55, 0.30, 0.15, 0.00, 0.00],
    5:  [0.45, 0.33, 0.20, 0.02, 0.00],
    6:  [0.30, 0.40, 0.25, 0.05, 0.00],
    7:  [0.19, 0.30, 0.35, 0.15, 0.01],
    8:  [0.18, 0.25, 0.32, 0.22, 0.03],
    9:  [0.15, 0.20, 0.25, 0.30, 0.10],
    10: [0.05, 0.10, 0.20, 0.40, 0.25],
}

# 코스트별 UI 색상
COST_COLORS = {
    1: "#808080",
    2: "#11b288",
    3: "#207ac7",
    4: "#c440da",
    5: "#ffb93b",
}
