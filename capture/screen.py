"""TFT 게임 화면 캡처 + 인식 통합 모듈"""
import logging
import platform
import threading
import time
from typing import Callable, Optional

import numpy as np

try:
    import mss
    import mss.tools
except ImportError:
    mss = None

logger = logging.getLogger(__name__)


def _find_tft_window() -> Optional[dict]:
    """TFT 게임 창 영역을 찾아 반환. 못 찾으면 None."""
    system = platform.system()
    try:
        if system == "Darwin":
            import subprocess
            script = '''
            tell application "System Events"
                repeat with proc in (every process whose background only is false)
                    repeat with win in (every window of proc)
                        set winName to name of win
                        if winName contains "TFT" or winName contains "League" or winName contains "Teamfight" then
                            set {xPos, yPos} to position of win
                            set {w, h} to size of win
                            return (xPos as text) & "," & (yPos as text) & "," & (w as text) & "," & (h as text)
                        end if
                    end repeat
                end repeat
            end tell
            return ""
            '''
            result = subprocess.run(["osascript", "-e", script],
                                    capture_output=True, text=True, timeout=5)
            if result.stdout.strip():
                parts = result.stdout.strip().split(",")
                x, y, w, h = [int(p) for p in parts]
                return {"left": x, "top": y, "width": w, "height": h}
        elif system == "Windows":
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            result_box = {}

            def callback(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, buf, 256)
                    title = buf.value
                    for kw in ["TFT", "Teamfight Tactics", "League of Legends"]:
                        if kw.lower() in title.lower():
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            result_box["left"] = rect.left
                            result_box["top"] = rect.top
                            result_box["width"] = rect.right - rect.left
                            result_box["height"] = rect.bottom - rect.top
                            return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
            )
            user32.EnumWindows(WNDENUMPROC(callback), 0)
            return result_box if result_box else None
    except Exception:
        pass
    return None


class ScreenCapture:
    """화면 캡처 + 인식 통합 관리자"""

    def __init__(self, interval: float = 2.0, detector=None):
        self.interval = interval
        self.detector = detector
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_detections: list[dict] = []
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []
        self._window_region: Optional[dict] = None

        # 상태 추적
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._last_capture_time: float = 0.0
        self._fps_timer: float = 0.0

    def capture_once(self) -> Optional[np.ndarray]:
        """한 번 캡처하여 numpy array 반환"""
        if mss is None:
            return None
        try:
            with mss.mss() as sct:
                region = self._window_region or _find_tft_window()
                if region:
                    self._window_region = region
                    shot = sct.grab(region)
                else:
                    monitor = sct.monitors[1]
                    shot = sct.grab(monitor)
                img = np.array(shot)  # BGRA
                return img[:, :, :3]  # BGR
        except Exception as e:
            logger.debug(f"캡처 실패: {e}")
            return None

    def on_frame(self, callback: Callable[[np.ndarray], None]):
        """프레임 콜백 등록"""
        self._callbacks.append(callback)

    @property
    def latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._latest_frame

    @property
    def latest_detections(self) -> list[dict]:
        with self._lock:
            return list(self._latest_detections)

    @property
    def fps(self) -> float:
        with self._lock:
            return self._fps

    @property
    def last_capture_time(self) -> float:
        with self._lock:
            return self._last_capture_time

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict:
        """캡처 상태 반환"""
        with self._lock:
            return {
                "active": self._running,
                "fps": round(self._fps, 1),
                "frame_count": self._frame_count,
                "last_capture_time": self._last_capture_time,
                "has_frame": self._latest_frame is not None,
                "interval": self.interval,
                "detected_count": len(self._latest_detections),
            }

    def start(self):
        """백그라운드 캡처 시작"""
        if self._running:
            return
        self._running = True
        self._fps_timer = time.time()
        self._frame_count = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("캡처 시작")

    def stop(self):
        """캡처 중지"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("캡처 중지")

    def _loop(self):
        fps_frames = 0
        fps_start = time.time()

        while self._running:
            frame = self.capture_once()
            if frame is not None:
                now = time.time()

                # 인식 실행
                detections = []
                if self.detector:
                    try:
                        detections = self.detector.detect_champions(frame)
                    except Exception as e:
                        logger.error(f"인식 오류: {e}")

                with self._lock:
                    self._latest_frame = frame
                    self._latest_detections = detections
                    self._last_capture_time = now
                    self._frame_count += 1

                # FPS 계산 (1초 단위)
                fps_frames += 1
                elapsed = now - fps_start
                if elapsed >= 1.0:
                    with self._lock:
                        self._fps = fps_frames / elapsed
                    fps_frames = 0
                    fps_start = now

                # 콜백 호출
                for cb in self._callbacks:
                    try:
                        cb(frame)
                    except Exception:
                        pass

            time.sleep(self.interval)

    def refresh_window(self):
        """창 위치 다시 탐색"""
        self._window_region = None
