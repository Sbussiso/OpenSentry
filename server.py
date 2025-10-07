import cv2
import threading
import time
import os
import numpy as np
try:
    import face_recognition  # type: ignore
except Exception:
    face_recognition = None  # type: ignore
from flask import Flask, Response, request, redirect, url_for, send_file, abort
from helpers.camera import CameraStream
from helpers.yolo import get_yolo_model
from helpers.faces import get_face_cascade
from helpers.motion import create_motion_generator
from helpers.settings_page import render_settings_page
from helpers.index_page import render_index_page
from helpers.all_feeds_page import render_all_feeds_page
from helpers.face_dedup import (
    compute_phash as _compute_phash,
    hamming as _hamming,
    load_manifest as _load_manifest,
    append_manifest as _append_manifest,
    load_embed_manifest as _load_embed_manifest,
    append_embed_manifest as _append_embed_manifest,
    write_embed_manifest as _write_embed_manifest,
    load_known_manifest as _load_known_manifest,
    append_known_manifest as _append_known_manifest,
    compute_embedding as _compute_embedding,
    face_recognition_available,
)
from helpers.config import load_config as _load_config, save_config as _save_config

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Stream output tuning
OUTPUT_MAX_WIDTH = 960
JPEG_QUALITY = 75
RAW_TARGET_FPS = 15

# (YOLO is now handled in helpers.yolo; face_recognition is used via helpers.face_dedup)

# Object detection settings (thread-safe)
settings_lock = threading.Lock()
object_detection_config = {
    'select_all': True,   # when True, detect all classes
    'classes': set(),     # when select_all is False, detect only these class names
}

# Motion detection defaults and settings (thread-safe, in-memory)
MOTION_DEFAULTS = {
    'threshold': 25,   # pixel diff threshold; lower = more sensitive
    'min_area': 500,   # minimum contour area (pixels)
    'kernel': 15,      # dilation kernel (px)
    'iterations': 2,   # dilation iterations
    'pad': 10,         # box padding (px)
}
motion_detection_config = MOTION_DEFAULTS.copy()

# Face detection defaults and settings (in-memory)
FACE_DEFAULTS = {
    'archive_unknown': False,      # when True, archive snapshot of unknown faces
    'min_duration_sec': 15,        # how long a face must persist before archiving
    'archive_dir': os.path.join(BASE_DIR, 'archives', 'unknown_faces'),
    # Dedup config
    'dedup_enabled': True,
    'dedup_threshold': 10,         # Hamming distance threshold (0-64)
    'manifest_path': os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest.json'),
    'dedup_method': 'embedding',   # 'embedding' or 'phash'
    'embedding_threshold': 0.7,    # L2 distance threshold for embeddings
    'manifest_embed_path': os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json'),
    'cooldown_minutes': 0,
}
face_detection_config = FACE_DEFAULTS.copy()
# Face dedup utilities moved to helpers.face_dedup

# Known faces manifest path
KNOWN_EMBED_PATH = os.path.join(BASE_DIR, 'archives', 'known_faces', 'manifest_embeddings.json')

# Persisted config path
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

# Load persisted config if present
_cfg = _load_config(CONFIG_PATH)
if _cfg:
    try:
        with settings_lock:
            if 'object_detection' in _cfg:
                object_detection_config.update(_cfg['object_detection'])
                # classes back to set
                if isinstance(object_detection_config.get('classes', set()), list):
                    object_detection_config['classes'] = set(object_detection_config['classes'])
            if 'motion_detection' in _cfg:
                motion_detection_config.update(_cfg['motion_detection'])
            if 'face_detection' in _cfg:
                face_detection_config.update(_cfg['face_detection'])
    except Exception:
        pass

# Global camera stream (class imported from helpers.camera)
camera_stream = CameraStream()

@app.before_request
def _ensure_camera_started():
    if not camera_stream.running:
        camera_stream.start()

def generate_frames():
    """Generator function that yields raw frames in MJPEG format"""
    last_send = 0.0
    while True:
        frame = camera_stream.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        # FPS limit
        now_ts = time.time()
        min_interval = 1.0 / max(1, RAW_TARGET_FPS)
        dt = now_ts - last_send
        if dt < min_interval:
            time.sleep(max(0.0, min_interval - dt))
        last_send = time.time()

        # Downscale for output if needed
        H, W = frame.shape[:2]
        if W > OUTPUT_MAX_WIDTH:
            scale = OUTPUT_MAX_WIDTH / float(W)
            frame = cv2.resize(frame, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)

        # Encode frame as JPEG (lower quality to reduce CPU)
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)])
        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        # Yield frame in multipart format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' + frame_bytes + b'\r\n')


def generate_frames_with_objects():
    """Generator function that yields frames with YOLOv8n object detection overlays."""
    model = get_yolo_model()
    while True:
        frame = camera_stream.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        # Snapshot settings to avoid holding the lock during inference
        with settings_lock:
            select_all = object_detection_config['select_all']
            allowed = set(object_detection_config['classes'])

        if model is None:
            # Informative overlay if ultralytics isn't installed or model failed
            msg = 'YOLOv8n unavailable. Install: uv add ultralytics'
            cv2.putText(frame, msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            try:
                results = model(frame, verbose=False)[0]
                names = getattr(results, 'names', {}) or getattr(model, 'names', {}) or {}
                if hasattr(results, 'boxes') and results.boxes is not None:
                    for b in results.boxes:
                        # xyxy tensor -> ints
                        xyxy = b.xyxy[0].cpu().numpy().tolist()
                        x1, y1, x2, y2 = [int(v) for v in xyxy]
                        conf = float(b.conf[0]) if getattr(b, 'conf', None) is not None else 0.0
                        cls_id = int(b.cls[0]) if getattr(b, 'cls', None) is not None else -1
                        label = names.get(cls_id, str(cls_id if cls_id >= 0 else 'obj'))
                        if not select_all and label not in allowed:
                            continue
                        color = (0, 255, 255)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        text = f"{label} {conf:.2f}"
                        cv2.putText(frame, text, (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            except Exception as e:
                cv2.putText(frame, f'YOLO error: {e}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Encode and yield
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' + frame_bytes + b'\r\n')


def generate_frames_with_faces():
    """Generator function that yields frames with face detection (Haar cascade)."""
    cascade = get_face_cascade()
    # Simple track state for persisting detections over time
    tracks = {}  # id -> {bbox:(x,y,w,h), start:float, last:float, archived:bool}
    next_id = 1

    def _iou(b1, b2):
        x1, y1, w1, h1 = b1
        x2, y2, w2, h2 = b2
        ax1, ay1, ax2, ay2 = x1, y1, x1 + w1, y1 + h1
        bx1, by1, bx2, by2 = x2, y2, x2 + w2, y2 + h2
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        iw = max(0, inter_x2 - inter_x1)
        ih = max(0, inter_y2 - inter_y1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        area_a = w1 * h1
        area_b = w2 * h2
        union = area_a + area_b - inter
        if union <= 0:
            return 0.0
        return inter / float(union)

    def _make_uid(ts_val: float) -> str:
        # Short, readable UID derived from timestamp ms; sufficient for unknown users
        ms = int((ts_val - int(ts_val)) * 1000)
        return f"U{int(ts_val)%100000:05d}{ms:03d}"

    while True:
        frame = camera_stream.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        # Prefer face_recognition detection (HOG) when available; fallback to Haar cascade
        H, W = frame.shape[:2]
        valid = []
        used_detector = 'haar'
        if face_recognition_available and face_recognition is not None:
            try:
                target_w = 800
                scale = 1.0
                if W > target_w:
                    scale = target_w / float(W)
                    small = cv2.resize(frame, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_LINEAR)
                else:
                    small = frame
                small_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                boxes = face_recognition.face_locations(small_rgb, model='hog')  # (top, right, bottom, left)
                # Landmark-based validation: require eyes and nose to reduce false positives
                lmarks = []
                try:
                    lmarks = face_recognition.face_landmarks(small_rgb, boxes, model='small')
                except Exception:
                    lmarks = []
                inv = 1.0 / scale
                for i, (top, right, bottom, left) in enumerate(boxes):
                    lm = lmarks[i] if i < len(lmarks) else {}
                    # Relax gating: accept if eyes OR nose when landmarks are present; if no landmarks, allow box
                    landmarks_ok = True
                    if isinstance(lm, dict) and lm:
                        has_eyes = ('left_eye' in lm and 'right_eye' in lm and lm['left_eye'] and lm['right_eye'])
                        has_nose = ('nose_bridge' in lm and lm['nose_bridge'])
                        if not (has_eyes or has_nose):
                            landmarks_ok = False
                    if not landmarks_ok:
                        continue
                    x = int(left * inv)
                    y = int(top * inv)
                    w = int((right - left) * inv)
                    h = int((bottom - top) * inv)
                    # Aspect and min area filters
                    ar = w / float(h) if h > 0 else 0
                    area = w * h
                    if h <= 0 or w <= 0:
                        continue
                    if ar < 0.70 or ar > 1.40:
                        continue
                    if area < 0.008 * (W * H):  # at least 0.8% of the frame area
                        continue
                    x = max(0, min(W - 1, x))
                    y = max(0, min(H - 1, y))
                    w = max(1, min(W - x, w))
                    h = max(1, min(H - y, h))
                    valid.append((x, y, w, h))
                if valid:
                    used_detector = 'fr'
            except Exception:
                valid = []

        if not valid:
            if cascade is None:
                cv2.putText(frame, 'Face detector unavailable', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)
                # Slightly relaxed detector params and dynamic minimum size
                min_w = max(30, int(W * 0.09))
                min_h = max(30, int(H * 0.09))
                faces = cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.22,
                    minNeighbors=8,
                    minSize=(min_w, min_h)
                )
                # Filter by plausible face aspect ratio and minimum area
                min_area_ratio = 0.012  # 1.2% of frame area
                frame_area = float(W * H)
                for (x, y, w, h) in faces:
                    ar = w / float(h) if h > 0 else 0
                    area = w * h
                    if h <= 0 or w <= 0:
                        continue
                    if ar < 0.70 or ar > 1.40:
                        continue
                    if area < (min_area_ratio * frame_area):
                        continue
                    valid.append((x, y, w, h))
        # Snapshot face archiving settings
        with settings_lock:
            archive_enabled = bool(face_detection_config.get('archive_unknown', False))
            min_dur = float(face_detection_config.get('min_duration_sec', 10))
            archive_dir = str(face_detection_config.get('archive_dir', 'archives/unknown_faces'))
            embed_th_view = float(face_detection_config.get('embedding_threshold', 0.6))

        now = time.time()
        # Match detections to existing tracks by IoU
        used_tracks = set()
        for (x, y, w, h) in valid:
            best_id = None
            best_iou = 0.0
            for tid, t in tracks.items():
                if tid in used_tracks:
                    continue
                i = _iou((x, y, w, h), t['bbox'])
                if i > best_iou:
                    best_iou = i
                    best_id = tid
            if best_id is not None and best_iou >= 0.2:
                t = tracks[best_id]
                t['bbox'] = (x, y, w, h)
                t['last'] = now
                used_tracks.add(best_id)
            else:
                tid = next_id
                next_id += 1
                tracks[tid] = {'bbox': (x, y, w, h), 'start': now, 'last': now, 'archived': False, 'uid': None}
                used_tracks.add(tid)

        # Prune stale tracks
        stale_cutoff = now - 3.0
        for tid in list(tracks.keys()):
            if tracks[tid]['last'] < stale_cutoff:
                del tracks[tid]

        # Pre-pass: identify known faces so recognized tracks are not archived
        if face_recognition_available:
            try:
                k_entries = _load_known_manifest(KNOWN_EMBED_PATH)
            except Exception:
                k_entries = []
            if k_entries:
                for tid, t in tracks.items():
                    if t.get('name'):
                        continue
                    x, y, w, h = t['bbox']
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(W, x + w)
                    y2 = min(H, y + h)
                    if (x2 - x1) <= 1 or (y2 - y1) <= 1:
                        continue
                    # small padding for more stable embeddings
                    pad = int(max(w, h) * 0.1)
                    xx1 = max(0, x1 - pad)
                    yy1 = max(0, y1 - pad)
                    xx2 = min(W, x2 + pad)
                    yy2 = min(H, y2 + pad)
                    crop = frame[yy1:yy2, xx1:xx2]
                    emb_vec = _compute_embedding(crop)
                    if emb_vec is None:
                        continue
                    best_name = None
                    best_dist = 1e9
                    for e in k_entries:
                        try:
                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                            if evec.size != emb_vec.size:
                                continue
                            dist = float(np.linalg.norm(emb_vec - evec))
                            if dist < best_dist:
                                best_dist = dist
                                best_name = e.get('name')
                        except Exception:
                            continue
                    if best_name is not None and best_dist <= embed_th_view:
                        t['name'] = best_name

        # Archive faces that persisted long enough
        if archive_enabled:
            os.makedirs(archive_dir, exist_ok=True)
            for tid, t in tracks.items():
                if t['archived']:
                    continue
                # Skip archiving if already recognized as known
                if t.get('name'):
                    continue
                if (now - t['start']) >= min_dur:
                    x, y, w, h = t['bbox']
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(W, x + w)
                    y2 = min(H, y + h)
                    if (x2 - x1) > 0 and (y2 - y1) > 0:
                        crop = frame[y1:y2, x1:x2]

                        # Dedup check: prefer embeddings if available and selected; fallback to pHash
                        with settings_lock:
                            dedup_enabled = bool(face_detection_config.get('dedup_enabled', True))
                            method = str(face_detection_config.get('dedup_method', 'embedding'))
                            embed_th = float(face_detection_config.get('embedding_threshold', 0.6))
                            dd_th = int(face_detection_config.get('dedup_threshold', 10))
                            manifest_path = str(face_detection_config.get('manifest_path', os.path.join(archive_dir, 'manifest.json')))
                            manifest_embed_path = str(face_detection_config.get('manifest_embed_path', os.path.join(archive_dir, 'manifest_embeddings.json')))
                            cooldown_min = int(face_detection_config.get('cooldown_minutes', 60))
                        is_dup = False
                        used_method = None
                        skip_save = False
                        emb_vec = None
                        matched_uid = None
                        matched_name = None

                        if dedup_enabled and method == 'embedding':
                            used_method = 'embedding'
                            if not face_recognition_available:
                                # Embedding pipeline not available; skip saves for embedding method
                                skip_save = True
                            else:
                                emb_vec = _compute_embedding(crop)
                                if emb_vec is not None:
                                    # Known-first matching
                                    try:
                                        k_entries = _load_known_manifest(KNOWN_EMBED_PATH)
                                    except Exception:
                                        k_entries = []
                                    best_name = None
                                    best_dist = 1e9
                                    for e in k_entries:
                                        try:
                                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                                            if evec.size != emb_vec.size:
                                                continue
                                            dist = float(np.linalg.norm(emb_vec - evec))
                                            if dist < best_dist:
                                                best_dist = dist
                                                best_name = e.get('name')
                                        except Exception:
                                            continue
                                    if best_name is not None and best_dist <= embed_th:
                                        is_dup = True
                                        matched_name = best_name
                                    # Unknown-manifest matching
                                    entries = _load_embed_manifest(manifest_embed_path)
                                    cooldown_sec = max(0, cooldown_min) * 60
                                    # Use a slightly more lenient threshold for unknown dedup to avoid duplicate UIDs for the same person
                                    th_unknown = min(max(embed_th, 0.0) + 0.12, 1.0)
                                    best_uid = None
                                    best_uid_dist = 1e9
                                    for e in entries:
                                        try:
                                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                                            if evec.size != emb_vec.size:
                                                continue
                                            dist = float(np.linalg.norm(emb_vec - evec))
                                            recent = (now - float(e.get('ts', 0))) <= cooldown_sec if cooldown_sec > 0 else True
                                            if recent and dist < best_uid_dist:
                                                best_uid_dist = dist
                                                best_uid = e.get('uid') or (f"U{int(float(e.get('ts', 0)))%100000:05d}")
                                        except Exception:
                                            continue
                                    if matched_name is None and best_uid is not None and best_uid_dist <= th_unknown:
                                        is_dup = True
                                        matched_uid = best_uid
                                else:
                                    # Embedding could not be computed; skip saving to avoid non-embedding fallback
                                    skip_save = True

                        if dedup_enabled and not is_dup and method == 'phash':
                            p = _compute_phash(crop)
                            entries = _load_manifest(manifest_path)
                            cooldown_sec = max(0, cooldown_min) * 60
                            for e in entries:
                                try:
                                    dist = _hamming(int(e.get('hash', 0)), p)
                                    recent = (now - float(e.get('ts', 0))) <= cooldown_sec if cooldown_sec > 0 else True
                                    if dist <= dd_th and recent:
                                        is_dup = True
                                        break
                                except Exception:
                                    continue
                            used_method = 'phash'

                        if is_dup:
                            # Assign matched UID to track for live overlay
                            # Determine which track this crop matched: pick the track whose bbox equals current crop
                            for tid2, t2 in tracks.items():
                                if t2['bbox'] == (x, y, w, h):
                                    if matched_name is not None:
                                        t2['name'] = matched_name
                                    elif matched_uid is not None:
                                        t2['uid'] = matched_uid
                                    break
                            continue
                        if skip_save:
                            continue

                        # Save snapshot and append manifest
                        ts = time.strftime('%Y%m%d_%H%M%S')
                        ms = int((now - int(now)) * 1000)
                        fname = f"unknown_{ts}_{ms}_{x1}_{y1}_{x2-x1}_{y2-y1}.jpg"
                        out_path = os.path.join(archive_dir, fname)
                        saved_ok = False
                        if not cv2.imwrite(out_path, crop):
                            # Failed to write image; abort archiving
                            continue
                        try:
                            if method == 'embedding':
                                if not face_recognition_available:
                                    raise Exception('Embedding not available')
                                if emb_vec is None:
                                    emb_vec = _compute_embedding(crop)
                                if emb_vec is None:
                                    raise Exception('Embedding compute failed')
                                # Assign/generate uid and persist with embedding
                                uid = _make_uid(now)
                                _append_embed_manifest(manifest_embed_path, {"uid": uid, "embedding": emb_vec.tolist(), "ts": float(now), "path": out_path})
                                # Attach uid to the matched track for overlay
                                for tid2, t2 in tracks.items():
                                    if t2['bbox'] == (x, y, w, h):
                                        t2['uid'] = uid
                                        break
                            else:
                                p = _compute_phash(crop)
                                _append_manifest(manifest_path, {"hash": int(p), "ts": float(now), "path": out_path})
                            saved_ok = True
                        except Exception:
                            saved_ok = False
                        if saved_ok:
                            print(f"Archived face snapshot: {out_path}")
                            t['archived'] = True

        # Live known-face identification (per frame): match tracks to known manifest
        if face_recognition_available:
            try:
                k_entries = _load_known_manifest(KNOWN_EMBED_PATH)
            except Exception:
                k_entries = []
            if k_entries:
                for tid, t in tracks.items():
                    if t.get('name'):
                        continue
                    x, y, w, h = t['bbox']
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(W, x + w)
                    y2 = min(H, y + h)
                    if (x2 - x1) <= 1 or (y2 - y1) <= 1:
                        continue
                    crop = frame[y1:y2, x1:x2]
                    emb_vec = _compute_embedding(crop)
                    if emb_vec is None:
                        continue
                    best_name = None
                    best_dist = 1e9
                    for e in k_entries:
                        try:
                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                            if evec.size != emb_vec.size:
                                continue
                            dist = float(np.linalg.norm(emb_vec - evec))
                            if dist < best_dist:
                                best_dist = dist
                                best_name = e.get('name')
                        except Exception:
                            continue
                    if best_name is not None and best_dist <= embed_th_view:
                        t['name'] = best_name

        color = (0, 200, 0) if used_detector == 'fr' else (255, 200, 0)
        # Draw using tracked boxes so we can label with UID or track id
        for tid, t in tracks.items():
            (x, y, w, h) = t['bbox']
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            name = t.get('name')
            if name:
                label_text = str(name)
            else:
                uid = t.get('uid')
                label_text = uid if uid else "Unknown"
            cv2.putText(frame, label_text, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.putText(frame, f'Faces: {len(valid)}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
        # Overlay archiving status
        arch_text = 'Archiving: ON' if archive_enabled else 'Archiving: OFF'
        arch_color = (0, 200, 0) if archive_enabled else (180, 180, 180)
        cv2.putText(frame, arch_text, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, arch_color, 2)

        # Encode and yield
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' + frame_bytes + b'\r\n')


def _get_motion_settings_snapshot():
    with settings_lock:
        return {
            'threshold': int(motion_detection_config.get('threshold', 25)),
            'kernel': int(motion_detection_config.get('kernel', 15)),
            'iterations': int(motion_detection_config.get('iterations', 2)),
            'min_area': int(motion_detection_config.get('min_area', 500)),
            'pad': int(motion_detection_config.get('pad', 10)),
        }


def generate_frames_with_detection():
    """Generator function that yields frames with motion detection overlay (via helpers.motion)."""
    gen = create_motion_generator(camera_stream, _get_motion_settings_snapshot)
    return gen()

@app.route('/archives/image')
def archives_image():
    path = request.args.get('path', '')
    if not path:
        abort(400)
    ap = os.path.abspath(path)
    archives_root = os.path.join(BASE_DIR, 'archives')
    if not ap.startswith(archives_root):
        abort(403)
    try:
        return send_file(ap)
    except Exception:
        abort(404)

@app.route('/archives/unknown_faces', methods=['GET', 'POST'])
def archives_unknown_faces():
    with settings_lock:
        unknown_manifest_path = str(face_detection_config.get('manifest_embed_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')))
    if request.method == 'POST':
        action = request.form.get('action', '')
        uid = request.form.get('uid', '').strip()
        if action == 'delete' and uid:
            entries = _load_embed_manifest(unknown_manifest_path)
            new_entries = []
            img_path = None
            for e in entries:
                if str(e.get('uid', '')) == uid:
                    img_path = e.get('path')
                    continue
                new_entries.append(e)
            try:
                _write_embed_manifest(unknown_manifest_path, new_entries)
            except Exception:
                pass
            if img_path:
                try:
                    os.remove(img_path)
                except Exception:
                    pass
            return redirect(url_for('archives_unknown_faces'))
        if action == 'promote' and uid:
            name = request.form.get('name', '').strip()
            if name:
                entries = _load_embed_manifest(unknown_manifest_path)
                pick = None
                for e in entries:
                    if str(e.get('uid', '')) == uid:
                        pick = e
                        break
                if pick is not None:
                    try:
                        _append_known_manifest(KNOWN_EMBED_PATH, {"name": name, "embedding": pick.get('embedding', []), "ts": pick.get('ts', 0), "path": pick.get('path', '')})
                    except Exception:
                        pass
                    # remove from unknown
                    new_entries = [e for e in entries if str(e.get('uid', '')) != uid]
                    try:
                        _write_embed_manifest(unknown_manifest_path, new_entries)
                    except Exception:
                        pass
            return redirect(url_for('archives_unknown_faces'))
    # GET: render page
    entries = _load_embed_manifest(unknown_manifest_path)
    # Simple inline HTML to list entries
    rows = []
    for e in entries:
        uid = str(e.get('uid', ''))
        ts = float(e.get('ts', 0.0))
        path = e.get('path', '')
        img_url = url_for('archives_image') + f"?path={path}"
        row = f"""
        <div class='card'>
          <div class='img'><img src='{img_url}' alt='{uid}'/></div>
          <div class='meta'><div><strong>{uid}</strong></div><div>{ts}</div></div>
          <form method='post' class='actions'>
            <input type='hidden' name='uid' value='{uid}'>
            <input type='text' name='name' placeholder='Name' />
            <button type='submit' name='action' value='promote'>Promote to Known</button>
            <button type='submit' name='action' value='delete' onclick="return confirm('Delete this snapshot and entry?');">Delete</button>
          </form>
        </div>
        """
        rows.append(row)
    html = f"""
    <!DOCTYPE html>
    <html lang='en'>
    <head>
      <meta charset='utf-8'>
      <meta name='viewport' content='width=device-width, initial-scale=1'>
      <title>Unknown Faces</title>
      <style>
        body {{ font-family: system-ui, Arial, sans-serif; margin:0; padding:10px; }}
        header {{ display:flex; gap:10px; align-items:center; margin-bottom: 10px; }}
        .grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap:12px; }}
        .card {{ border:1px solid #ddd; border-radius:6px; overflow:hidden; display:flex; flex-direction:column; }}
        .img img {{ width:100%; display:block; }}
        .meta {{ padding:8px; display:flex; justify-content:space-between; align-items:center; }}
        .actions {{ display:flex; gap:8px; padding:8px; align-items:center; border-top:1px solid #eee; }}
        .actions input[type=text] {{ flex: 1; min-width:0; padding:6px; }}
        .actions button {{ padding:6px 10px; }}
      </style>
    </head>
    <body>
      <header>
        <strong>Unknown Faces</strong>
        <a href='/'>Home</a>
        <a href='/settings'>Settings</a>
      </header>
      <div class='grid'>
        {''.join(rows)}
      </div>
    </body>
    </html>
    """
    return html

@app.route('/')
def index():
    """Root endpoint - renders the index page via helper."""
    return render_index_page()

@app.route('/all_feeds')
def all_feeds():
    return render_all_feeds_page()

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Simple settings page to select YOLO classes (or All)."""
    # Resolve available class names without running inference if possible
    names = []
    model = get_yolo_model()
    try:
        if model is not None:
            raw_names = getattr(model, 'names', None)
            if isinstance(raw_names, dict):
                names = [raw_names[i] for i in sorted(raw_names.keys())]
            elif isinstance(raw_names, (list, tuple)):
                names = list(raw_names)
    except Exception:
        names = []

    if request.method == 'POST':
        # If reset button pressed, reset motion settings and redirect
        action = request.form.get('action')
        if action == 'reset_motion':
            with settings_lock:
                motion_detection_config.clear()
                motion_detection_config.update(MOTION_DEFAULTS)
            try:
                _save_config(CONFIG_PATH, object_detection_config, motion_detection_config, face_detection_config)
            except Exception:
                pass
            return redirect(url_for('settings'))
        if action == 'reset_face_manifest':
            # Clear the unknown face manifests (hash and embeddings)
            with settings_lock:
                mp = str(face_detection_config.get('manifest_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest.json')))
                mp_e = str(face_detection_config.get('manifest_embed_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')))
            try:
                os.makedirs(os.path.dirname(mp), exist_ok=True)
                with open(mp, 'w', encoding='utf-8') as f:
                    f.write('[]')
            except Exception:
                pass
            try:
                os.makedirs(os.path.dirname(mp_e), exist_ok=True)
                with open(mp_e, 'w', encoding='utf-8') as f:
                    f.write('[]')
            except Exception:
                pass
            return redirect(url_for('settings'))

        # Manage unknowns directly from Settings: promote to known or delete
        if action in ('promote_unknown', 'delete_unknown'):
            with settings_lock:
                unknown_manifest_path = str(
                    face_detection_config.get(
                        'manifest_embed_path',
                        os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')
                    )
                )
            uid = (request.form.get('uid') or '').strip()
            if uid:
                entries = _load_embed_manifest(unknown_manifest_path)
                if action == 'promote_unknown':
                    name = (request.form.get('name') or '').strip()
                    if name:
                        pick = None
                        for e in entries:
                            if str(e.get('uid', '')) == uid:
                                pick = e
                                break
                        if pick is not None:
                            try:
                                _append_known_manifest(
                                    KNOWN_EMBED_PATH,
                                    {"name": name, "embedding": pick.get('embedding', []), "ts": pick.get('ts', 0), "path": pick.get('path', '')}
                                )
                            except Exception:
                                pass
                            # Remove from unknown manifest
                            new_entries = [e for e in entries if str(e.get('uid', '')) != uid]
                            try:
                                _write_embed_manifest(unknown_manifest_path, new_entries)
                            except Exception:
                                pass
                elif action == 'delete_unknown':
                    new_entries = []
                    img_path = None
                    for e in entries:
                        if str(e.get('uid', '')) == uid:
                            img_path = e.get('path')
                            continue
                        new_entries.append(e)
                    try:
                        _write_embed_manifest(unknown_manifest_path, new_entries)
                    except Exception:
                        pass
                    if img_path:
                        try:
                            os.remove(img_path)
                        except Exception:
                            pass
            return redirect(url_for('settings'))

        select_all_flag = ('select_all' in request.form)
        selected = set(request.form.getlist('classes'))
        face_archive_flag = ('face_archive_unknown' in request.form)
        face_dedup_flag = ('face_dedup_enabled' in request.form)
        dedup_method_in = request.form.get('face_dedup_method', '').strip().lower()
        embed_thr_in = request.form.get('face_embedding_threshold', '')
        min_dur_in = request.form.get('face_min_duration_sec', '')

        # Read motion detection sensitivity values with fallbacks
        def _to_int(val, default):
            try:
                return int(val)
            except Exception:
                return default

        th_in = _to_int(request.form.get('md_threshold', ''), motion_detection_config['threshold'])
        ma_in = _to_int(request.form.get('md_min_area', ''), motion_detection_config['min_area'])
        ke_in = _to_int(request.form.get('md_kernel', ''), motion_detection_config['kernel'])
        it_in = _to_int(request.form.get('md_iterations', ''), motion_detection_config['iterations'])
        pd_in = _to_int(request.form.get('md_pad', ''), motion_detection_config['pad'])

        # Clamp to sane ranges
        th_in = max(0, min(255, th_in))
        ma_in = max(0, ma_in)
        ke_in = max(1, ke_in)
        it_in = max(0, it_in)
        pd_in = max(0, pd_in)

        with settings_lock:
            # YOLO class selection
            object_detection_config['select_all'] = select_all_flag
            object_detection_config['classes'] = selected
            # Motion sensitivity
            motion_detection_config['threshold'] = th_in
            motion_detection_config['min_area'] = ma_in
            motion_detection_config['kernel'] = ke_in
            motion_detection_config['iterations'] = it_in
            motion_detection_config['pad'] = pd_in
            # Face detection
            face_detection_config['archive_unknown'] = bool(face_archive_flag)
            face_detection_config['dedup_enabled'] = bool(face_dedup_flag)
            # Optional controls (we'll provide sliders in UI; keep defaults if absent)
            dd_th = request.form.get('face_dedup_threshold')
            cd_min = request.form.get('face_cooldown_minutes')
            try:
                if dd_th is not None and dd_th != '':
                    face_detection_config['dedup_threshold'] = max(0, min(64, int(dd_th)))
            except Exception:
                pass
            try:
                if cd_min is not None and cd_min != '':
                    face_detection_config['cooldown_minutes'] = max(0, int(cd_min))
            except Exception:
                pass
            try:
                if min_dur_in is not None and min_dur_in != '':
                    face_detection_config['min_duration_sec'] = max(1, int(min_dur_in))
            except Exception:
                pass
            # Dedup method and embedding threshold
            if dedup_method_in in ('embedding', 'phash'):
                face_detection_config['dedup_method'] = dedup_method_in
            try:
                if embed_thr_in is not None and embed_thr_in != '':
                    face_detection_config['embedding_threshold'] = max(0.0, min(2.0, float(embed_thr_in)))
            except Exception:
                pass
            # Ensure archive directory exists if enabling
            if face_detection_config['archive_unknown']:
                try:
                    os.makedirs(face_detection_config['archive_dir'], exist_ok=True)
                except Exception:
                    pass
        # Persist config to disk after general update
        try:
            _save_config(CONFIG_PATH, object_detection_config, motion_detection_config, face_detection_config)
        except Exception:
            pass
        return redirect(url_for('settings'))

    with settings_lock:
        select_all_flag = object_detection_config['select_all']
        selected = set(object_detection_config['classes'])
        m_thresh = motion_detection_config['threshold']
        m_min_area = motion_detection_config['min_area']
        m_kernel = motion_detection_config['kernel']
        m_iters = motion_detection_config['iterations']
        m_pad = motion_detection_config['pad']
        f_archive = bool(face_detection_config['archive_unknown'])
        f_min_dur = int(face_detection_config['min_duration_sec'])
        f_dir = face_detection_config['archive_dir']
        f_dedup = bool(face_detection_config.get('dedup_enabled', True))
        f_dd_th = int(face_detection_config.get('dedup_threshold', 10))
        f_cool = int(face_detection_config.get('cooldown_minutes', 60))
        f_method = str(face_detection_config.get('dedup_method', 'embedding'))
        f_embed_th = float(face_detection_config.get('embedding_threshold', 0.6))

    # Build unknowns list for settings management
    with settings_lock:
        unknown_manifest_path = str(face_detection_config.get('manifest_embed_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')))
    try:
        unk_entries = _load_embed_manifest(unknown_manifest_path)
    except Exception:
        unk_entries = []
    unknowns_for_ui = []
    for e in unk_entries[:50]:
        p = e.get('path', '')
        unknowns_for_ui.append({
            'uid': e.get('uid', ''),
            'ts': e.get('ts', ''),
            'img_url': url_for('archives_image') + f"?path={p}" if p else ''
        })

    # Snapshot simple route health/status
    has_frame = (camera_stream.get_frame() is not None)
    raw_ok = camera_stream.running and has_frame
    motion_ok = raw_ok  # motion depends on camera frames
    objects_ok = (model is not None) and raw_ok
    faces_ok = (get_face_cascade() is not None) and raw_ok

    return render_settings_page(
        names=names,
        select_all_flag=select_all_flag,
        selected=selected,
        m_thresh=m_thresh,
        m_min_area=m_min_area,
        m_kernel=m_kernel,
        m_iters=m_iters,
        m_pad=m_pad,
        f_archive=f_archive,
        f_min_dur=f_min_dur,
        f_dir=f_dir,
        f_dedup=f_dedup,
        f_dd_th=f_dd_th,
        f_cool=f_cool,
        f_method=f_method,
        f_embed_th=f_embed_th,
        raw_ok=raw_ok,
        motion_ok=motion_ok,
        objects_ok=objects_ok,
        faces_ok=faces_ok,
        face_recognition_available=face_recognition_available,
        unknowns=unknowns_for_ui,
    )

@app.route('/video_feed')
def video_feed():
    """Video streaming route - raw feed with no processing"""
    resp = Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp


@app.route('/video_feed_objects')
def video_feed_objects():
    """Video streaming route - YOLOv8n object detection overlay"""
    resp = Response(generate_frames_with_objects(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp

@app.route('/video_feed_faces')
def video_feed_faces():
    """Video streaming route - face detection overlay (Haar)."""
    resp = Response(generate_frames_with_faces(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp



@app.route('/video_feed_motion')
def video_feed_motion():
    """Video streaming route - motion detection overlay (alias)"""
    resp = Response(generate_frames_with_detection(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp


def main():
    print("Starting OpenSentry camera server...")
    print("Starting camera stream...")
    camera_stream.start()
    print("Access the feed at http://0.0.0.0:5000/video_feed")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
