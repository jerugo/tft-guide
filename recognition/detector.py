"""OpenCV 기반 챔피언 인식 모듈 - 멀티스케일 템플릿 매칭"""
import json
import logging
import pathlib
from typing import Optional

import cv2
import numpy as np

from config import CHAMPIONS_JSON

logger = logging.getLogger(__name__)

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
ICONS_DIR = DATA_DIR / "icons"

# TFT 보드 영역 비율 (전체 화면 대비, 1920x1080 기준)
REGIONS = {
    "board": {"x": 0.20, "y": 0.20, "w": 0.60, "h": 0.50},
    "bench": {"x": 0.20, "y": 0.73, "w": 0.60, "h": 0.09},
    "shop":  {"x": 0.28, "y": 0.90, "w": 0.44, "h": 0.09},
}

# 멀티스케일 매칭 범위
SCALES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5]


def _load_champion_map() -> dict:
    """apiName → {name_kr, cost} 매핑 로드"""
    mapping = {}
    try:
        with open(CHAMPIONS_JSON, "r", encoding="utf-8") as f:
            champs = json.load(f)
        for c in champs:
            api = c.get("apiName")
            if api:
                mapping[api] = {
                    "name_kr": c.get("name_kr", c["name"]),
                    "name": c["name"],
                    "cost": c.get("cost", 1),
                }
    except Exception as e:
        logger.warning(f"챔피언 데이터 로드 실패: {e}")
    return mapping


def _nms_boxes(detections: list[dict], iou_threshold: float = 0.3) -> list[dict]:
    """Non-Maximum Suppression (IoU 기반)"""
    if not detections:
        return []

    detections.sort(key=lambda d: -d["confidence"])
    kept = []

    for det in detections:
        x1, y1 = det["position"]
        w1, h1 = det.get("size", (48, 48))

        suppress = False
        for k in kept:
            x2, y2 = k["position"]
            w2, h2 = k.get("size", (48, 48))

            # IoU 계산
            ix1 = max(x1, x2)
            iy1 = max(y1, y2)
            ix2 = min(x1 + w1, x2 + w2)
            iy2 = min(y1 + h1, y2 + h2)

            if ix2 > ix1 and iy2 > iy1:
                inter = (ix2 - ix1) * (iy2 - iy1)
                union = w1 * h1 + w2 * h2 - inter
                if union > 0 and inter / union > iou_threshold:
                    suppress = True
                    break

        if not suppress:
            kept.append(det)

    return kept


class ChampionDetector:
    """챔피언 아이콘 템플릿 매칭 감지기 (멀티스케일)"""

    def __init__(self, threshold: float = 0.7, scales: list[float] = None):
        self.threshold = threshold
        self.scales = scales or SCALES
        self._templates: dict[str, np.ndarray] = {}
        self._champion_map: dict = {}
        self._load_templates()

    def _load_templates(self):
        """아이콘 PNG 로드 + 챔피언 매핑"""
        self._champion_map = _load_champion_map()

        if not ICONS_DIR.exists():
            logger.warning(f"아이콘 디렉토리 없음: {ICONS_DIR}")
            return

        count = 0
        for f in ICONS_DIR.glob("TFT16_*.png"):
            api_name = f.stem.replace("TFT16_", "")
            img = cv2.imread(str(f), cv2.IMREAD_COLOR)
            if img is not None:
                self._templates[api_name] = img
                count += 1

        logger.info(f"템플릿 {count}개 로드 완료 (매핑: {len(self._champion_map)}개)")

    def set_threshold(self, threshold: float):
        """매칭 임계값 변경"""
        self.threshold = max(0.1, min(1.0, threshold))

    def detect_champions(self, image: np.ndarray,
                         regions: dict = None) -> list[dict]:
        """
        이미지에서 챔피언 감지 (멀티스케일 + NMS).
        Returns: [{name, name_kr, position, confidence, area, cost, size}]
        """
        if not self._templates:
            return []

        if regions is None:
            regions = REGIONS

        h, w = image.shape[:2]
        all_detections = []

        for region_name, roi in regions.items():
            x1 = int(w * roi["x"])
            y1 = int(h * roi["y"])
            x2 = int(w * (roi["x"] + roi["w"]))
            y2 = int(h * (roi["y"] + roi["h"]))
            crop = image[y1:y2, x1:x2]

            if crop.size == 0:
                continue

            crop_h, crop_w = crop.shape[:2]

            for api_name, tmpl in self._templates.items():
                best_conf = 0.0
                best_loc = None
                best_size = None

                for scale in self.scales:
                    th, tw = tmpl.shape[:2]
                    new_h = int(th * scale)
                    new_w = int(tw * scale)

                    if new_h >= crop_h or new_w >= crop_w or new_h < 10 or new_w < 10:
                        continue

                    resized = cv2.resize(tmpl, (new_w, new_h))

                    try:
                        result = cv2.matchTemplate(
                            crop, resized, cv2.TM_CCOEFF_NORMED
                        )
                    except cv2.error:
                        continue

                    # 모든 매칭 위치 탐색
                    locations = np.where(result >= self.threshold)
                    for pt_y, pt_x in zip(*locations):
                        conf = float(result[pt_y, pt_x])
                        if conf > best_conf:
                            best_conf = conf
                            best_loc = (x1 + pt_x, y1 + pt_y)
                            best_size = (new_w, new_h)

                if best_loc and best_conf >= self.threshold:
                    info = self._champion_map.get(api_name, {})
                    all_detections.append({
                        "name": info.get("name", api_name),
                        "name_kr": info.get("name_kr", api_name),
                        "apiName": api_name,
                        "position": best_loc,
                        "size": best_size,
                        "confidence": round(best_conf, 4),
                        "area": region_name,
                        "cost": info.get("cost", 1),
                    })

        # NMS로 중복 제거
        return _nms_boxes(all_detections)

    def detect_from_region(self, image: np.ndarray, region: str) -> list[dict]:
        """특정 영역만 감지"""
        if region not in REGIONS:
            return []
        return self.detect_champions(image, {region: REGIONS[region]})

    @property
    def template_count(self) -> int:
        return len(self._templates)

    @property
    def champion_names(self) -> list[str]:
        """로드된 챔피언 apiName 목록"""
        return list(self._templates.keys())
