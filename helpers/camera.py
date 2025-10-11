import os
import threading
import time
import logging
import glob
import cv2

logger = logging.getLogger('opensentry.camera')


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
        # Allow env override for capture FPS
        try:
            env_fps = int(os.environ.get('OPENSENTRY_CAMERA_FPS', '').strip() or '0')
            if env_fps > 0:
                fps = env_fps
        except Exception:
            pass
        self._sleep = 1.0 / max(1, fps)
        self._requested_index = device_index

    def start(self) -> None:
        if self.running:
            return
        # Start capture thread; camera will be opened asynchronously by the loop
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

        # Optional tuning via env
        mjpeg = (os.environ.get('OPENSENTRY_CAMERA_MJPEG', '0') in ('1', 'true', 'TRUE'))
        try:
            req_w = int(os.environ.get('OPENSENTRY_CAMERA_WIDTH', '0') or '0')
            req_h = int(os.environ.get('OPENSENTRY_CAMERA_HEIGHT', '0') or '0')
            req_fps = int(os.environ.get('OPENSENTRY_CAMERA_FPS', '0') or '0')
        except Exception:
            req_w = 0
            req_h = 0
            req_fps = 0

        # Build candidate list: specific device path -> indexed path -> all paths -> indices
        candidates: list[tuple[str, str | int]] = []
        env_dev = os.environ.get('OPENSENTRY_CAMERA_DEVICE')
        if env_dev and os.path.exists(env_dev):
            candidates.append(('path', env_dev))
        # Index-specific path
        dev_path = f"/dev/video{idx}"
        if os.path.exists(dev_path):
            candidates.append(('path', dev_path))
        # All /dev/video* paths
        for p in sorted(glob.glob('/dev/video*')):
            if ('path', p) not in candidates:
                candidates.append(('path', p))
        # Index probing 0..5
        idx_candidates = [idx] + [i for i in range(0, 6) if i != idx]
        for i in idx_candidates:
            candidates.append(('index', i))

        # Try to open each candidate
        for kind, target in candidates:
            # Prefer V4L2 backend, then fallback
            apis = [getattr(cv2, 'CAP_V4L2', 200), None]
            for api in apis:
                try:
                    if kind == 'path':
                        cap = cv2.VideoCapture(str(target), api) if api is not None else cv2.VideoCapture(str(target))
                    else:
                        cap = cv2.VideoCapture(int(target), api) if api is not None else cv2.VideoCapture(int(target))
                except Exception:
                    continue

                # Optional format/size and latency reduction
                try:
                    if mjpeg:
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                    if req_w > 0:
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(req_w))
                    if req_h > 0:
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(req_h))
                    if req_fps > 0:
                        cap.set(cv2.CAP_PROP_FPS, float(req_fps))
                    # Reduce internal buffering to minimize latency (best-effort)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass

                # Warm-up a few frames
                ok = False
                frame = None
                for _ in range(6):
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        break
                    time.sleep(0.06)
                if ok and frame is not None:
                    # Found working camera
                    try:
                        if self.camera is not None:
                            self.camera.release()
                    except Exception:
                        pass
                    self.camera = cap
                    try:
                        if kind == 'path':
                            logger.info('Opened camera device=%s using api=%s', str(target), str(api))
                        else:
                            logger.info('Opened camera index=%s using api=%s', str(target), str(api))
                    except Exception:
                        pass
                    return
                try:
                    cap.release()
                except Exception:
                    pass
        try:
            logger.error('Failed to open any camera (idx requested=%s). Paths tried: %s', idx, ','.join([str(t) for k,t in candidates if k=='path']))
        except Exception:
            pass

    def _capture_frames(self) -> None:
        failures = 0
        while self.running:
            if self.camera is None:
                time.sleep(0.2)
                # Try to reopen periodically
                self._open_camera()
                continue
            success, frame = False, None
            try:
                success, frame = self.camera.read()
            except Exception:
                success, frame = False, None
            if success and frame is not None:
                failures = 0
                with self.lock:
                    self.frame = frame.copy()
            else:
                failures += 1
                if failures >= 30:
                    # Reopen the camera after sustained failures
                    try:
                        logger.warning('Camera read failures detected; attempting reopen.')
                    except Exception:
                        pass
                    try:
                        if self.camera is not None:
                            self.camera.release()
                    except Exception:
                        pass
                    self.camera = None
                    self._open_camera()
                    failures = 0
                time.sleep(0.05)
                continue
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
