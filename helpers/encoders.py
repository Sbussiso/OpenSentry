from typing import Optional
import cv2

_tj: Optional[object] = None
_turbo_enabled = False


def init_jpeg_encoder(logger=None) -> None:
    """No-op initializer. We use OpenCV for JPEG encoding."""
    global _tj, _turbo_enabled
    _tj = None
    _turbo_enabled = False
    if logger:
        logger.info("JPEG encoder: OpenCV")


def turbojpeg_enabled() -> bool:
    """TurboJPEG is not used in this build."""
    return False


def encode_jpeg_bgr(frame, quality: int = 75) -> bytes:
    """Encode a BGR image to JPEG bytes using OpenCV.
    - frame: numpy ndarray in BGR order (as returned by OpenCV)
    - quality: JPEG quality 1-100
    """
    ret, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ret:
        # Return minimal valid JPEG if encoding fails
        return b"\xff\xd8\xff\xd9"
    return buf.tobytes()
