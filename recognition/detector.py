"""OpenCV 기반 챔피언 인식 모듈 - 최적화 버전"""
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

# 템플릿 표준 크기 (매칭 속도 최적화)
TEMPLATE_SIZE = (32, 32)


def _load_champion_map() -> dict:
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


def _nms_boxes(detections: list, iou_threshold: float = 0.3) -> list:
    if not detections:
        return []
    detections.sort(key=lambda d: -d["confidence"])
    kept = []
    for det in detections:
        x1, y1 = det["position"]
        w1, h1 = det.get("size", (32, 32))
        suppress = False
        for k in kept:
            x2, y2 = k["position"]
            w2, h2 = k.get("size", (32, 32))
            ix1, iy1 = max(x1, x2), max(y1, y2)
            ix2, iy2 = min(x1+w1, x2+w2), min(y1+h1, y2+h2)
            if ix2 > ix1 and iy2 > iy1:
                inter = (ix2-ix1) * (iy2-iy1)
                union = w1*h1 + w2*h2 - inter
                if union > 0 and inter/union > iou_threshold:
                    suppress = True
                    break
        if not suppress:
            kept.append(det)
    return kept


class ChampionDetector:
    """챔피언 아이콘 템플릿 매칭 감지기 (최적화 버전)"""

    def __init__(self, threshold: float = 0.7, scales: list = None):
        self.threshold = threshold
        # 그레이스케일 + 고정 크기 템플릿 (사전 처리)
        self._templates: dict[str, np.ndarray] = {}
        self._champion_map: dict = {}
        self._load_templates()

    def _load_templates(self):
        self._champion_map = _load_champion_map()
        if not ICONS_DIR.exists():
            logger.warning(f"아이콘 디렉토리 없음: {ICONS_DIR}")
            return

        count = 0
        for f in ICONS_DIR.glob("TFT16_*.png"):
            api_name = f.stem.replace("TFT16_", "")
            img = cv2.imread(str(f), cv2.IMREAD_COLOR)
            if img is not None:
                # 표준 크기로 리사이즈 + 그레이스케일 (사전 처리)
                resized = cv2.resize(img, TEMPLATE_SIZE)
                gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
                self._templates[api_name] = gray
                count += 1

        logger.info(f"템플릿 {count}개 로드 완료 (매핑: {len(self._champion_map)}개)")

    def set_threshold(self, threshold: float):
        self.threshold = max(0.1, min(1.0, threshold))

    def detect_champions(self, image: np.ndarray,
                         regions: dict = None) -> list:
        """이미지에서 챔피언 감지 (최적화: 그레이스케일 + 고정크기)"""
        if not self._templates:
            return []
        if regions is None:
            regions = REGIONS

        h, w = image.shape[:2]
        # 1920x1080 기준으로 리사이즈
        target_w = 1920
        if w != target_w:
            scale_f = target_w / w
            image = cv2.resize(image, (target_w, int(h * scale_f)))
            h, w = image.shape[:2]

        # 전체 이미지를 그레이스케일로 한번만 변환
        gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        all_detections = []

        for region_name, roi in regions.items():
            x1 = int(w * roi["x"])
            y1 = int(h * roi["y"])
            x2 = int(w * (roi["x"] + roi["w"]))
            y2 = int(h * (roi["y"] + roi["h"]))
            crop = gray_full[y1:y2, x1:x2]

            if crop.size == 0:
                continue

            crop_h, crop_w = crop.shape[:2]
            tw, th = TEMPLATE_SIZE

            if th >= crop_h or tw >= crop_w:
                continue

            for api_name, tmpl in self._templates.items():
                try:
                    result = cv2.matchTemplate(crop, tmpl, cv2.TM_CCOEFF_NORMED)
                except cv2.error:
                    continue

                locations = np.where(result >= self.threshold)
                for pt_y, pt_x in zip(*locations):
                    conf = float(result[pt_y, pt_x])
                    info = self._champion_map.get(api_name, {})
                    all_detections.append({
                        "name": info.get("name", api_name),
                        "name_kr": info.get("name_kr", api_name),
                        "apiName": api_name,
                        "position": (x1 + int(pt_x), y1 + int(pt_y)),
                        "size": TEMPLATE_SIZE,
                        "confidence": round(conf, 4),
                        "area": region_name,
                        "cost": info.get("cost", 1),
                    })

        return _nms_boxes(all_detections)

    def detect_from_region(self, image: np.ndarray, region: str) -> list:
        if region not in REGIONS:
            return []
        return self.detect_champions(image, {region: REGIONS[region]})

    def detect_shop(self, image: np.ndarray) -> list:
        """상점 영역만 인식 (5슬롯 좌→우)"""
        detections = self.detect_from_region(image, "shop")
        detections.sort(key=lambda d: d["position"][0])
        for i, det in enumerate(detections[:5]):
            det["slot"] = i
        return detections[:5]

    @property
    def template_count(self) -> int:
        return len(self._templates)

    @property
    def champion_names(self) -> list:
        return list(self._templates.keys())
