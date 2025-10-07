import threading
import cv2

_face_cascade = None
_face_lock = threading.Lock()


def get_face_cascade():
    """Lazily load OpenCV's Haar cascade for frontal face detection.
    Returns a cv2.CascadeClassifier or None if unavailable.
    """
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade
    with _face_lock:
        if _face_cascade is None:
            try:
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                clf = cv2.CascadeClassifier(cascade_path)
                _face_cascade = clf if not clf.empty() else None
            except Exception:
                _face_cascade = None
        return _face_cascade
