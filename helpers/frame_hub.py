import threading
import time
from typing import Callable, Optional


class Broadcaster:
    """Shared MJPEG broadcaster that centralizes encoding per route.

    - produce_fn: returns JPEG bytes for current frame or None to skip.
    - fps_getter: returns target FPS (int), read each loop for live updates.
    """

    def __init__(self, name: str, produce_fn: Callable[[], Optional[bytes]], fps_getter: Callable[[], int]):
        self.name = name
        self._produce = produce_fn
        self._get_fps = fps_getter
        self._latest: Optional[bytes] = None
        self._seq: int = 0
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._th: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._th = threading.Thread(target=self._run, name=f"Broadcaster-{self.name}", daemon=True)
        self._th.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._cv.notify_all()

    def _run(self) -> None:
        next_time = time.time()
        while True:
            fps = max(1, int(self._get_fps() or 1))
            period = 1.0 / float(fps)
            now = time.time()
            if now < next_time:
                time.sleep(min(period, next_time - now))
            next_time = time.time() + period

            # Produce current frame bytes
            try:
                data = self._produce()
            except Exception:
                data = None
            if data is None:
                continue

            with self._lock:
                if not self._running:
                    break
                self._latest = data
                self._seq += 1
                self._cv.notify_all()

            # Avoid spinning in case of extremely fast producers
            time.sleep(0)

    def multipart_stream(self):
        """Flask generator for multipart/x-mixed-replace route."""
        boundary = b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
        last = -1
        while True:
            with self._lock:
                while self._running and (self._seq == last or self._latest is None):
                    self._cv.wait(timeout=1.0)
                if not self._running:
                    break
                last = self._seq
                data = self._latest
            if not data:
                continue
            yield boundary + str(len(data)).encode() + b'\r\n\r\n' + data + b'\r\n'
