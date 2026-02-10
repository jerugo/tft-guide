"""OpenCV 기반 챔피언 인식 모듈"""
import json
import pathlib
from typing import Optional

import cv2
import numpy as np

from config import TEMPLATES_DIR, CHAMPIONS_JSON


# TFT 보드 영역 비율 (전체 화면 대비, 1920x1080 기준)
REGIONS = {
    "board": {"x": 0.23, "y": 0.25, "w": 0.54, "h": 0.45},
    "bench": {"x": 0.23, "y": 0.73, "w": 0.54, "h": 0.08},
    "shop":  {"x": 0.31, "y": 0.92, "w": 0.38, "h": 0.07},
}


class ChampionDetector:
    """챔피언 아이콘 템플릿 매칭 감지기"""

    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold
        self._templates: dict[str, np.ndarray] = {}
        self._load_templates()

    def _load_templates(self):
        """템플릿 이미지 로드"""
        tmpl_dir = pathlib.Path(TEMPLATES_DIR)
        if not tmpl_dir.exists():
            tmpl_dir.mkdir(parents=True, exist_ok=True)
            return
        for f in tmpl_dir.glob("*.png"):
            name = f.stem  # 파일명 = 챔피언 영문명
            img = cv2.imread(str(f), cv2.IMREAD_COLOR)
            if img is not None:
                self._templates[name] = img

    def detect_champions(self, image: np.ndarray) -> list[dict]:
        """
        이미지에서 챔피언 감지.
        Returns: [{name, region, position: (x, y), confidence}]
        """
        if not self._templates:
            return []

        results = []
        h, w = image.shape[:2]

        for region_name, roi in REGIONS.items():
            x1 = int(w * roi["x"])
            y1 = int(h * roi["y"])
            x2 = int(w * (roi["x"] + roi["w"]))
            y2 = int(h * (roi["y"] + roi["h"]))
            crop = image[y1:y2, x1:x2]

            if crop.size == 0:
                continue

            for champ_name, tmpl in self._templates.items():
                # 템플릿 크기 조정
                th, tw = tmpl.shape[:2]
                ch, cw = crop.shape[:2]
                if th > ch or tw > cw:
                    scale = min(ch / th, cw / tw) * 0.8
                    tmpl_resized = cv2.resize(tmpl, (int(tw * scale), int(th * scale)))
                else:
                    tmpl_resized = tmpl

                try:
                    match = cv2.matchTemplate(crop, tmpl_resized, cv2.TM_CCOEFF_NORMED)
                    locations = np.where(match >= self.threshold)
                    for pt in zip(*locations[::-1]):
                        results.append({
                            "name": champ_name,
                            "region": region_name,
                            "position": (x1 + pt[0], y1 + pt[1]),
                            "confidence": float(match[pt[1], pt[0]]),
                        })
                except cv2.error:
                    continue

        # NMS: 같은 챔피언 중복 제거
        return self._nms(results)

    def _nms(self, detections: list[dict], dist_threshold: int = 40) -> list[dict]:
        """간단한 거리 기반 중복 제거"""
        if not detections:
            return []
        detections.sort(key=lambda d: -d["confidence"])
        kept = []
        for det in detections:
            too_close = False
            for k in kept:
                dx = det["position"][0] - k["position"][0]
                dy = det["position"][1] - k["position"][1]
                if (dx * dx + dy * dy) < dist_threshold * dist_threshold and det["name"] == k["name"]:
                    too_close = True
                    break
            if not too_close:
                kept.append(det)
        return kept

    @property
    def template_count(self) -> int:
        return len(self._templates)

    def detect_from_region(self, image: np.ndarray, region: str) -> list[dict]:
        """특정 영역만 감지"""
        results = self.detect_champions(image)
        return [r for r in results if r["region"] == region]
