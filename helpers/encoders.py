import os
import ctypes.util
from typing import Optional

try:
    from turbojpeg import TurboJPEG, TJPF_BGR  # type: ignore
except Exception:  # pragma: no cover - optional dep
    TurboJPEG = None  # type: ignore
    TJPF_BGR = None  # type: ignore

import cv2

_tj: Optional["TurboJPEG"] = None
_turbo_enabled = False


def init_jpeg_encoder(logger=None) -> None:
    """Initialize TurboJPEG if available and not disabled by env.

    Env:
      - OPENSENTRY_TURBOJPEG: '1' to enable (default), '0' to force disable
    """
    global _tj, _turbo_enabled
    want = os.environ.get("OPENSENTRY_TURBOJPEG", "1") in ("1", "true", "TRUE")
    if not want:
        _tj = None
        _turbo_enabled = False
        if logger:
            logger.info("TurboJPEG disabled via env; falling back to OpenCV encoder")
        return
    if TurboJPEG is None:
        _tj = None
        _turbo_enabled = False
        if logger:
            logger.info("TurboJPEG not available; falling back to OpenCV encoder")
        return
    # Attempt default init first
    try:
        _tj = TurboJPEG()
        _turbo_enabled = True
        if logger:
            logger.info("TurboJPEG enabled for JPEG encoding")
        return
    except Exception as e:  # pragma: no cover - rare init errors
        if logger:
            logger.warning(f"TurboJPEG default init failed ({e}); trying env and common paths")
    # Try explicit env-provided paths
    for key in ("TURBOJPEG", "OPENSENTRY_TURBOJPEG_PATH"):
        p = os.environ.get(key, "").strip()
        if not p:
            continue
        try:
            _tj = TurboJPEG(lib_path=p)
            _turbo_enabled = True
            if logger:
                logger.info(f"TurboJPEG enabled via {key}={p}")
            return
        except Exception as ee:
            if logger:
                logger.warning(f"TurboJPEG init with {key} failed: {ee}")
    # Try ctypes to locate library
    try:
        lib = ctypes.util.find_library("turbojpeg") or ctypes.util.find_library("jpeg-turbo") or ctypes.util.find_library("jpeg")
    except Exception:
        lib = None
    if lib:
        try:
            _tj = TurboJPEG(lib_path=lib)
            _turbo_enabled = True
            if logger:
                logger.info(f"TurboJPEG enabled via find_library: {lib}")
            return
        except Exception as ee:
            if logger:
                logger.warning(f"TurboJPEG init with find_library path {lib} failed: {ee}")
    # Try common Linux/macOS locations and LD_LIBRARY_PATH candidates
    candidates = [
        # Common Ubuntu/Debian paths
        "/usr/lib/x86_64-linux-gnu/libturbojpeg.so",
        "/usr/lib/x86_64-linux-gnu/libturbojpeg.so.0",
        "/lib/x86_64-linux-gnu/libturbojpeg.so",
        "/lib/x86_64-linux-gnu/libturbojpeg.so.0",
        "/usr/lib/aarch64-linux-gnu/libturbojpeg.so",
        "/usr/lib/aarch64-linux-gnu/libturbojpeg.so.0",
        "/lib/aarch64-linux-gnu/libturbojpeg.so.0",
        "/usr/lib/arm-linux-gnueabihf/libturbojpeg.so",
        "/usr/lib/arm-linux-gnueabihf/libturbojpeg.so.0",
        "/lib/arm-linux-gnueabihf/libturbojpeg.so.0",
        "/usr/lib64/libturbojpeg.so",
        "/usr/local/lib/libturbojpeg.so",
        # macOS Homebrew
        "/opt/homebrew/lib/libturbojpeg.dylib",
        "/usr/local/opt/jpeg-turbo/lib/libturbojpeg.dylib",
    ]
    ld_paths = os.environ.get("LD_LIBRARY_PATH", "")
    if ld_paths:
        for d in ld_paths.split(":"):
            if not d:
                continue
            candidates.append(os.path.join(d, "libturbojpeg.so"))
            candidates.append(os.path.join(d, "libturbojpeg.dylib"))
    for p in candidates:
        try:
            if not p or not os.path.exists(p):
                continue
            _tj = TurboJPEG(lib_path=p)
            _turbo_enabled = True
            if logger:
                logger.info(f"TurboJPEG enabled via path: {p}")
            return
        except Exception:
            continue
    # Give up; stick to OpenCV
    _tj = None
    _turbo_enabled = False
    if logger:
        logger.warning("TurboJPEG init failed; falling back to OpenCV encoder")


def turbojpeg_enabled() -> bool:
    return bool(_turbo_enabled and _tj is not None)


def encode_jpeg_bgr(frame, quality: int = 75) -> bytes:
    """Encode a BGR image to JPEG bytes using TurboJPEG if available, else OpenCV.
    - frame: numpy ndarray in BGR order (as returned by OpenCV)
    - quality: JPEG quality 1-100
    """
    if turbojpeg_enabled():
        # TurboJPEG expects pixel_format to be specified for BGR input
        return _tj.encode(frame, quality=int(quality), pixel_format=TJPF_BGR)  # type: ignore[arg-type]
    # Fallback: OpenCV
    ret, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ret:
        # Return minimal valid JPEG if encoding fails
        return b"\xff\xd8\xff\xd9"
    return buf.tobytes()
