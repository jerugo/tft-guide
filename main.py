#!/usr/bin/env python3
"""TFT 가이드 - 메인 진입점"""
import argparse
import signal
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from capture.screen import ScreenCapture
from recognition.detector import ChampionDetector
from ui.app import create_app
import config


def main():
    parser = argparse.ArgumentParser(description="TFT 게임 가이드")
    parser.add_argument("--port", type=int, default=config.PORT, help="웹 서버 포트 (기본: 5000)")
    parser.add_argument("--llm-url", type=str, default=config.LLM_API_URL, help="LLM API URL")
    parser.add_argument("--capture-interval", type=float, default=config.CAPTURE_INTERVAL, help="캡처 주기(초)")
    parser.add_argument("--no-capture", action="store_true", help="화면 캡처 비활성화")
    args = parser.parse_args()

    # 화면 캡처 설정
    capture = None
    detector = None
    if not args.no_capture:
        capture = ScreenCapture(interval=args.capture_interval)
        detector = ChampionDetector()

        if detector.template_count > 0:
            def on_frame(frame):
                results = detector.detect_champions(frame)
                if results:
                    names = [r["name"] for r in results]
                    # TODO: UI에 실시간 반영
            capture.on_frame(on_frame)

    # Flask 앱
    app = create_app(capture=capture, detector=detector, llm_url=args.llm_url)

    # 종료 처리
    def shutdown(sig, frame):
        print("\n종료 중...")
        if capture:
            capture.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"🎮 TFT 가이드 시작: http://localhost:{args.port}")
    if capture:
        print(f"📸 화면 캡처: {args.capture_interval}초 간격")
    print(f"🤖 LLM: {args.llm_url}")

    # 캡처 시작 (수동 모드 — UI에서 토글)
    app.run(host=config.HOST, port=args.port, debug=False)


if __name__ == "__main__":
    main()
