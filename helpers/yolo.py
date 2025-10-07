import threading

try:
    from ultralytics import YOLO  # type: ignore
except Exception:  # pragma: no cover - optional dep
    YOLO = None  # type: ignore

_yolo_model = None
_yolo_lock = threading.Lock()


def get_yolo_model():
    """Lazily load the YOLOv8n model. Returns None if ultralytics is unavailable."""
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model
    with _yolo_lock:
        if _yolo_model is None and YOLO is not None:
            try:
                _yolo_model = YOLO('yolov8n.pt')
            except Exception:
                _yolo_model = None
        return _yolo_model
