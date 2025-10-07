import os
import threading
import time
import cv2


class CameraStream:
    """Threaded camera capture with a simple frame buffer.

    Respects OPENSENTRY_CAMERA_INDEX if set, otherwise uses device_index.
    Auto-probes indices 0..5 if initial open fails.
    """
    def __init__(self, device_index: int = 0, fps: int = 30):
        self.frame = None
        self.lock = threading.Lock()
        self.camera = None  # defer open until start()
        self.running = False
        self._sleep = 1.0 / max(1, fps)
        self._requested_index = device_index

    def start(self) -> None:
        if self.running:
            return
        # Ensure camera is opened before starting the capture thread
        self._open_camera()
        self.running = True
        threading.Thread(target=self._capture_frames, daemon=True).start()

    def _open_camera(self) -> None:
        # Decide initial index
        idx = self._requested_index
        env_idx = os.environ.get('OPENSENTRY_CAMERA_INDEX')
        if env_idx is not None:
            try:
                idx = int(env_idx)
            except Exception:
                pass
        # Try initial index then probe 0..5
        candidates = [idx] + [i for i in range(0, 6) if i != idx]
        for i in candidates:
            try:
                cap = cv2.VideoCapture(i)
            except Exception:
                continue
            ok, frame = cap.read()
            if ok and frame is not None:
                # Found working camera
                # Release previous if any
                try:
                    if self.camera is not None:
                        self.camera.release()
                except Exception:
                    pass
                self.camera = cap
                return
            try:
                cap.release()
            except Exception:
                pass

    def _capture_frames(self) -> None:
        while self.running:
            if self.camera is None:
                time.sleep(0.2)
                continue
            success, frame = self.camera.read()
            if success:
                with self.lock:
                    self.frame = frame.copy()
            time.sleep(self._sleep)

    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def stop(self) -> None:
        self.running = False
        try:
            if self.camera is not None:
                self.camera.release()
        except Exception:
            pass
