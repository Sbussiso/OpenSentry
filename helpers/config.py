import json
import os
from typing import Dict, Any


def load_config(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_config(path: str, object_detection: Dict[str, Any], motion_detection: Dict[str, Any], face_detection: Dict[str, Any]) -> None:
    # Convert non-JSON types (e.g., set -> list)
    obj = {
        'object_detection': {
            **object_detection,
            'classes': sorted(list(object_detection.get('classes', [])))
        },
        'motion_detection': {**motion_detection},
        'face_detection': {**face_detection},
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)
