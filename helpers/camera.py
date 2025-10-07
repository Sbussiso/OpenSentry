import threading
import time
import cv2


class CameraStream:
    """Threaded camera capture with a simple frame buffer."""
    def __init__(self, device_index: int = 0, fps: int = 30):
        self.frame = None
        self.lock = threading.Lock()
        self.camera = cv2.VideoCapture(device_index)
        self.running = False
        self._sleep = 1.0 / max(1, fps)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._capture_frames, daemon=True).start()

    def _capture_frames(self) -> None:
        while self.running:
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
            self.camera.release()
        except Exception:
            pass
