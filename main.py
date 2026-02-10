#!/usr/bin/env python3
"""TFT 가이드 - 메인 진입점"""
import argparse
import logging
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(__file__))

import config
from capture.screen import ScreenCapture
from recognition.detector import ChampionDetector
from ui.app import create_app


def main():
    parser = argparse.ArgumentParser(description="TFT 게임 가이드")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--llm-url", type=str, default=config.LLM_API_URL)
    parser.add_argument("--capture-interval", type=float, default=config.CAPTURE_INTERVAL)
    parser.add_argument("--threshold", type=float, default=config.DETECTION_THRESHOLD)
    parser.add_argument("--no-capture", action="store_true", help="수동 모드만 (캡처 비활성화)")
    parser.add_argument("--debug", action="store_true", help="디버그 모드 (인식 결과 이미지 저장)")
    args = parser.parse_args()

    # 로깅
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(name)s] %(message)s")
    logger = logging.getLogger("tft-guide")

    # detector 초기화
    detector = ChampionDetector(threshold=args.threshold)
    logger.info(f"🎯 템플릿 {detector.template_count}개 로드")

    # 캡처 설정
    capture = None
    if not args.no_capture:
        capture = ScreenCapture(interval=args.capture_interval, detector=detector)

        if args.debug:
            import cv2
            debug_dir = os.path.join(os.path.dirname(__file__), "debug_output")
            os.makedirs(debug_dir, exist_ok=True)
            frame_idx = [0]

            def save_debug(frame):
                detections = capture.latest_detections
                if detections:
                    img = frame.copy()
                    for d in detections:
                        x, y = d["position"]
                        w, h = d.get("size", (48, 48))
                        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        cv2.putText(img, f"{d['name_kr']} {d['confidence']:.2f}",
                                    (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                    path = os.path.join(debug_dir, f"frame_{frame_idx[0]:04d}.png")
                    cv2.imwrite(path, img)
                    frame_idx[0] += 1

            capture.on_frame(save_debug)

    # Flask 앱
    app = create_app(capture=capture, detector=detector, llm_url=args.llm_url)

    # 종료 처리
    def shutdown(sig, frame):
        print("\n🛑 종료 중...")
        if capture:
            capture.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 시작 메시지
    mode = "수동 모드" if args.no_capture else f"캡처 모드 ({args.capture_interval}초 간격)"
    print(f"\n⚔️  TFT 가이드 v2.0")
    print(f"  🌐 http://localhost:{args.port}")
    print(f"  📸 {mode}")
    print(f"  🤖 LLM: {args.llm_url}")
    print(f"  🎯 템플릿: {detector.template_count}개\n")

    # 캡처는 UI에서 토글 (기본 중지)
    app.run(host=config.HOST, port=args.port, debug=False)


if __name__ == "__main__":
    main()
