import threading
"""Lazy YOLO loader to avoid importing Ultralytics at app startup.

Ultralytics import can trigger config discovery and disk I/O, which slows
unrelated routes. We defer the import and model load until first use.
"""

# Defer importing Ultralytics until needed
YOLO = None  # type: ignore

_yolo_model = None
_yolo_lock = threading.Lock()


def get_yolo_model():
    """Lazily import Ultralytics and load YOLOv8n. Returns None if unavailable."""
    global _yolo_model, YOLO
    if _yolo_model is not None:
        return _yolo_model
    with _yolo_lock:
        if _yolo_model is not None:
            return _yolo_model
        # Import Ultralytics only when needed
        if YOLO is None:
            try:
                from ultralytics import YOLO as _YOLO  # type: ignore
                YOLO = _YOLO
            except Exception:
                YOLO = None  # type: ignore
        if YOLO is None:
            return None
        # Prefer local weights if present to avoid remote downloads
        import os
        weights = (os.environ.get('OPENSENTRY_YOLO_WEIGHTS') or '').strip()
        if not weights:
            candidate = '/app/yolov8n.pt'
            weights = candidate if os.path.exists(candidate) else 'yolov8n.pt'
        try:
            _yolo_model = YOLO(weights)
        except Exception:
            _yolo_model = None
        return _yolo_model


def get_coco_names():
    """Return the standard COCO class names without importing Ultralytics."""
    return [
        'person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic light',
        'fire hydrant','stop sign','parking meter','bench','bird','cat','dog','horse','sheep','cow',
        'elephant','bear','zebra','giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee',
        'skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard','tennis racket',
        'bottle','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich','orange',
        'broccoli','carrot','hot dog','pizza','donut','cake','chair','couch','potted plant','bed','dining table',
        'toilet','tv','laptop','mouse','remote','keyboard','cell phone','microwave','oven','toaster','sink',
        'refrigerator','book','clock','vase','scissors','teddy bear','hair drier','toothbrush'
    ]
