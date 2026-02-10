"""Flask 웹 UI 서버"""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, render_template, jsonify, request

from config import COST_COLORS
from engine.recommender import DeckRecommender
from llm.client import LLMClient
from data.updater import update_meta, get_last_updated


def create_app(capture=None, detector=None, llm_url=None):
    app = Flask(__name__)
    recommender = DeckRecommender()
    llm = LLMClient(api_url=llm_url) if llm_url else LLMClient()

    # 상태 저장
    state = {
        "my_champions": [],
        "opponents": [],
        "level": 7,
        "capturing": False,
    }

    @app.route("/")
    def index():
        return render_template("index.html",
                               cost_colors=COST_COLORS,
                               champions=recommender.champions)

    @app.route("/api/recommend", methods=["POST"])
    def api_recommend():
        data = request.json or {}
        my_champs = data.get("my_champions", state["my_champions"])
        opponents = data.get("opponents", state["opponents"])
        level = data.get("level", state["level"])

        state["my_champions"] = my_champs
        state["opponents"] = opponents
        state["level"] = level

        results = recommender.recommend(my_champs, opponents, level)
        return jsonify({"recommendations": results})

    @app.route("/api/pool", methods=["POST"])
    def api_pool():
        data = request.json or {}
        opponents = data.get("opponents", state["opponents"])
        pool = recommender.get_pool_status(opponents)
        return jsonify({"pool": pool})

    @app.route("/api/llm/analyze", methods=["POST"])
    def api_llm_analyze():
        data = request.json or {}
        my_champs = data.get("my_champions", state["my_champions"])
        level = data.get("level", state["level"])
        gold = data.get("gold", 0)

        recs = recommender.recommend(my_champs, state["opponents"], level)
        analysis = llm.analyze_game(my_champs, recs, level=level, gold=gold)
        if analysis:
            return jsonify({"analysis": analysis})
        return jsonify({"analysis": None, "error": "LLM 서버에 연결할 수 없습니다."})

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
            return jsonify({
                "active": capture._running,
                "has_frame": capture.latest_frame is not None,
                "interval": capture.interval,
            })
        return jsonify({"active": False, "has_frame": False})

    @app.route("/api/capture/toggle", methods=["POST"])
    def api_capture_toggle():
        if not capture:
            return jsonify({"error": "캡처 모듈 없음"})
        if capture._running:
            capture.stop()
        else:
            capture.start()
        return jsonify({"active": capture._running})

    @app.route("/api/settings", methods=["POST"])
    def api_settings():
        data = request.json or {}
        if "capture_interval" in data and capture:
            capture.interval = float(data["capture_interval"])
        if "llm_url" in data:
            llm.api_url = data["llm_url"].rstrip("/")
        return jsonify({"ok": True})

    @app.route("/api/champions")
    def api_champions():
        return jsonify({"champions": recommender.champions, "cost_colors": COST_COLORS})

    return app
