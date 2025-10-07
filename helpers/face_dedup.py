import os
import json
import threading
from typing import List, Dict, Any, Optional

import cv2
import numpy as np

try:
    import face_recognition  # type: ignore
    face_recognition_available = True
except Exception:  # pragma: no cover - optional dep
    face_recognition = None  # type: ignore
    face_recognition_available = False

_manifest_lock = threading.Lock()


def compute_phash(img_bgr) -> int:
    """Compute a 64-bit perceptual hash (pHash) using DCT of an 8x8 low-frequency block."""
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    except Exception:
        gray = img_bgr
    gray = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    f = np.float32(gray)
    dct = cv2.dct(f)
    low = dct[:8, :8]
    med = np.median(low)
    bits = (low > med).astype(np.uint8).flatten()
    h = 0
    for b in bits:
        h = (h << 1) | int(b)
    return int(h)


def hamming(a: int, b: int) -> int:
    return int(bin(a ^ b).count('1'))


def load_manifest(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def append_manifest(path: str, entry: Dict[str, Any]) -> None:
    with _manifest_lock:
        data = load_manifest(path)
        data.append(entry)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


def write_embed_manifest(path: str, entries: List[Dict[str, Any]]) -> None:
    with _manifest_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(list(entries), f, indent=2)


def load_known_manifest(path: str) -> List[Dict[str, Any]]:
    # For now, known manifest uses the same schema as embed manifest but entries include a 'name'
    return load_embed_manifest(path)


def append_known_manifest(path: str, entry: Dict[str, Any]) -> None:
    # Ensure 'name' is present for known entries
    if 'name' not in entry:
        raise ValueError("known manifest entry requires 'name'")
    append_embed_manifest(path, entry)


def load_embed_manifest(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def append_embed_manifest(path: str, entry: Dict[str, Any]) -> None:
    with _manifest_lock:
        data = load_embed_manifest(path)
        data.append(entry)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


def compute_embedding(img_bgr) -> Optional[np.ndarray]:
    if face_recognition is None:
        return None
    try:
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        encs = []
        # Try assuming the crop is the face (full crop bbox)
        try:
            encs = face_recognition.face_encodings(
                rgb,
                known_face_locations=[(0, w, h, 0)],  # top, right, bottom, left
                model='small',
                num_jitters=1,
            )
        except Exception:
            encs = []
        # If that fails, let face_recognition detect inside the crop
        if not encs:
            encs = face_recognition.face_encodings(rgb, model='small', num_jitters=1)
        # Last resort: try the larger model for better recall
        if not encs:
            try:
                encs = face_recognition.face_encodings(
                    rgb,
                    known_face_locations=[(0, w, h, 0)],
                    model='large',
                    num_jitters=1,
                )
            except Exception:
                encs = []
        if not encs:
            encs = face_recognition.face_encodings(rgb, model='large', num_jitters=1)
        if not encs:
            return None
        return np.asarray(encs[0], dtype=np.float32)
    except Exception:
        return None
