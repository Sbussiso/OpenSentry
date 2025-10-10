import json
import os
from typing import Dict, Any


def load_config(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_config(
    path: str,
    object_detection: Dict[str, Any],
    motion_detection: Dict[str, Any],
    face_detection: Dict[str, Any],
    device_id: str | None = None,
    auth_config: Dict[str, Any] | None = None,
    video_config: Dict[str, Any] | None = None,
    stream_config: Dict[str, Any] | None = None,
) -> None:
    """Save config to JSON, preserving existing top-level keys like device_id.

    - Ensures set -> list conversion for classes.
    - If device_id is provided, it will be set; otherwise preserved when present.
    - If auth_config is provided, it will be merged into the saved config.
    """
    # Start from existing to preserve keys like device_id
    prev: Dict[str, Any] = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            prev = json.load(f) or {}
    except Exception:
        prev = {}

    # Convert non-JSON types (e.g., set -> list)
    obj = {
        **prev,
        'object_detection': {
            **object_detection,
            'classes': sorted(list(object_detection.get('classes', [])))
        },
        'motion_detection': {**motion_detection},
        'face_detection': {**face_detection},
    }
    if device_id is not None:
        obj['device_id'] = device_id
    if auth_config is not None:
        obj['auth'] = auth_config
    # Optional sections
    if video_config is not None:
        obj['video'] = {**video_config}
    if stream_config is not None:
        obj['stream'] = {**stream_config}

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)
