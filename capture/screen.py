"""TFT 게임 화면 캡처 모듈"""
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


def _find_tft_window() -> Optional[dict]:
    """TFT 게임 창 영역을 찾아 반환. 못 찾으면 None."""
    system = platform.system()
    try:
        if system == "Darwin":
            import subprocess, json as _json
            # AppleScript로 창 목록 조회
            script = '''
            tell application "System Events"
                set winList to {}
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
            EnumWindows = user32.EnumWindows
            GetWindowTextW = user32.GetWindowTextW
            GetWindowRect = user32.GetWindowRect
            IsWindowVisible = user32.IsWindowVisible
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))

            result = {}

            def callback(hwnd, _):
                if IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(256)
                    GetWindowTextW(hwnd, buf, 256)
                    title = buf.value
                    for keyword in ["TFT", "Teamfight Tactics", "League of Legends"]:
                        if keyword.lower() in title.lower():
                            rect = wintypes.RECT()
                            GetWindowRect(hwnd, ctypes.byref(rect))
                            result["left"] = rect.left
                            result["top"] = rect.top
                            result["width"] = rect.right - rect.left
                            result["height"] = rect.bottom - rect.top
                            return False
                return True

            EnumWindows(WNDENUMPROC(callback), 0)
            return result if result else None
    except Exception:
        pass
    return None


class ScreenCapture:
    """화면 캡처 관리자"""

    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []
        self._window_region: Optional[dict] = None

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
                    # 전체 화면 캡처 (폴백)
                    monitor = sct.monitors[1]
                    shot = sct.grab(monitor)
                img = np.array(shot)  # BGRA
                return img[:, :, :3]  # BGR
        except Exception:
            return None

    def on_frame(self, callback: Callable[[np.ndarray], None]):
        """프레임 콜백 등록"""
        self._callbacks.append(callback)

    @property
    def latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._latest_frame

    def start(self):
        """백그라운드 캡처 시작"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """캡처 중지"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            frame = self.capture_once()
            if frame is not None:
                with self._lock:
                    self._latest_frame = frame
                for cb in self._callbacks:
                    try:
                        cb(frame)
                    except Exception:
                        pass
            time.sleep(self.interval)

    def refresh_window(self):
        """창 위치 다시 탐색"""
        self._window_region = None
