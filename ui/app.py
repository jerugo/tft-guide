"""Flask 웹 UI 서버 - 실시간 대시보드"""
import json
import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, render_template, jsonify, request, send_from_directory

from config import COST_COLORS, ICONS_DIR
from engine.recommender import DeckRecommender
from llm.client import LLMClient
from data.updater import update_meta, get_last_updated


def create_app(capture=None, detector=None, llm_url=None):
    app = Flask(__name__)
    recommender = DeckRecommender()
    llm = LLMClient(api_url=llm_url) if llm_url else LLMClient()

    # 공유 상태 (thread-safe)
    _state_lock = threading.Lock()
    state = {
        "my_champions": [],      # 수동 선택 챔피언 (name 기준)
        "opponents": [],
        "level": 7,
        "gold": 0,
        "capturing": False,
        "detected_champions": [],  # 자동 인식된 챔피언
        "shop_champions": [],      # 상점 챔피언
        "last_update": 0,
    }

    # 아이콘 서빙: /static/icons/ → data/icons/
    @app.route("/static/icons/<path:filename>")
    def serve_icon(filename):
        return send_from_directory(str(ICONS_DIR), filename)

    @app.route("/")
    def index():
        return render_template("index.html",
                               cost_colors=COST_COLORS,
                               champions=recommender.champions)

    @app.route("/api/status")
    def api_status():
        """실시간 상태 폴링 엔드포인트 (2초 간격)"""
        with _state_lock:
            my_champs = list(state["my_champions"])
            detected = list(state["detected_champions"])
            level = state["level"]
            gold = state["gold"]
            opponents = list(state["opponents"])

        # 캡처에서 인식된 챔피언과 수동 선택 병합
        all_champs = list(set(my_champs + [d.get("name", "") for d in detected]))

        # 추천 계산
        recs = recommender.recommend(all_champs, opponents, level) if all_champs else []

        # 캡처 상태
        cap_status = capture.get_status() if capture else {
            "active": False, "fps": 0, "detected_count": 0,
            "has_frame": False, "interval": 2.0
        }

        return jsonify({
            "my_champions": my_champs,
            "detected_champions": detected,
            "all_champions": all_champs,
            "level": level,
            "gold": gold,
            "recommendations": recs[:5],
            "capture": cap_status,
            "timestamp": time.time(),
        })

    @app.route("/api/recommend", methods=["POST"])
    def api_recommend():
        data = request.json or {}
        my_champs = data.get("my_champions", [])
        opponents = data.get("opponents", [])
        level = data.get("level", 7)

        with _state_lock:
            state["my_champions"] = my_champs
            state["opponents"] = opponents
            state["level"] = level

        results = recommender.recommend(my_champs, opponents, level)
        return jsonify({"recommendations": results})

    @app.route("/api/select_champion", methods=["POST"])
    def api_select_champion():
        """수동으로 챔피언 선택/해제"""
        data = request.json or {}
        name = data.get("name", "")
        action = data.get("action", "toggle")  # toggle, add, remove

        with _state_lock:
            champs = state["my_champions"]
            if action == "toggle":
                if name in champs:
                    champs.remove(name)
                else:
                    champs.append(name)
            elif action == "add" and name not in champs:
                champs.append(name)
            elif action == "remove" and name in champs:
                champs.remove(name)
            state["my_champions"] = champs
            result = list(champs)

        return jsonify({"my_champions": result})

    @app.route("/api/set_level", methods=["POST"])
    def api_set_level():
        data = request.json or {}
        with _state_lock:
            state["level"] = int(data.get("level", 7))
            state["gold"] = int(data.get("gold", 0))
        return jsonify({"ok": True})

    @app.route("/api/opponents", methods=["POST"])
    def api_opponents():
        """상대 챔피언 업데이트"""
        data = request.json or {}
        with _state_lock:
            state["opponents"] = data.get("opponents", [])
        return jsonify({"ok": True})

    @app.route("/api/pool", methods=["POST"])
    def api_pool():
        data = request.json or {}
        opponents = data.get("opponents", [])
        with _state_lock:
            state["opponents"] = opponents
        pool = recommender.get_pool_status(opponents)
        return jsonify({"pool": pool})

    @app.route("/api/llm/analyze", methods=["POST"])
    def api_llm_analyze():
        data = request.json or {}
        with _state_lock:
            my_champs = data.get("my_champions", list(state["my_champions"]))
            level = data.get("level", state["level"])
            gold = data.get("gold", state["gold"])
            opponents = state["opponents"]

        recs = recommender.recommend(my_champs, opponents, level)
        result = llm.analyze_game(my_champs, recs, level=level, gold=gold)
        return jsonify(result)

    @app.route("/api/llm/status")
    def api_llm_status():
        return jsonify({"available": llm.is_available(), "url": llm.api_url})

    @app.route("/api/update", methods=["POST"])
    def api_update():
        result = update_meta()
        if result["success"]:
            recommender.reload_data()
        return jsonify(result)

    @app.route("/api/last_updated")
    def api_last_updated():
        return jsonify({"last_updated": get_last_updated()})

    @app.route("/api/capture/status")
    def api_capture_status():
        if capture:
            return jsonify(capture.get_status())
        return jsonify({"active": False, "has_frame": False, "fps": 0, "interval": 2.0})

    @app.route("/api/capture/toggle", methods=["POST"])
    def api_capture_toggle():
        if not capture:
            return jsonify({"error": "캡처 모듈 없음 (--no-capture 모드)"})
        if capture.is_running:
            capture.stop()
        else:
            capture.start()
        return jsonify(capture.get_status())

    @app.route("/api/settings", methods=["POST"])
    def api_settings():
        data = request.json or {}
        if "capture_interval" in data and capture:
            capture.interval = max(0.5, float(data["capture_interval"]))
        if "threshold" in data and detector:
            detector.set_threshold(float(data["threshold"]))
        if "llm_url" in data:
            llm.api_url = data["llm_url"].rstrip("/")
        return jsonify({"ok": True})

    @app.route("/api/shop_advice", methods=["POST"])
    def api_shop_advice():
        """상점 추천 분석"""
        data = request.json or {}
        shop_champs = data.get("shop_champions", [])

        with _state_lock:
            my_champs = data.get("my_champions", list(state["my_champions"]))
            level = data.get("level", state["level"])
            gold = data.get("gold", state["gold"])
            opponents = list(state["opponents"])
            state["shop_champions"] = shop_champs

        # Get recommendations first
        all_champs = list(set(my_champs))
        recs = recommender.recommend(all_champs, opponents, level) if all_champs else []

        # Get shop advice
        advice = recommender.get_shop_advice(
            my_champs, shop_champs, recs, level, gold, opponents
        )

        return jsonify(advice)

    @app.route("/api/champions")
    def api_champions():
        return jsonify({"champions": recommender.champions, "cost_colors": COST_COLORS})

    # 캡처 인식 결과를 state에 반영
    if capture:
        def _on_detection_update():
            """캡처 결과를 주기적으로 state에 반영"""
            while True:
                if capture.is_running:
                    detections = capture.latest_detections
                    with _state_lock:
                        state["detected_champions"] = detections
                        state["last_update"] = time.time()
                time.sleep(1)

        t = threading.Thread(target=_on_detection_update, daemon=True)
        t.start()

    return app
