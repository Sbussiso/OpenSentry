import time
import cv2


def create_motion_generator(camera_stream, get_settings):
    """
    Factory that produces a generator yielding MJPEG frames with motion overlay.

    - camera_stream: object exposing get_frame()
    - get_settings: callable returning a dict with keys
        threshold, kernel, iterations, min_area, pad
    """
    # Tuning parameters
    TARGET_FPS = 15
    PROC_SCALE = 0.5  # process at half resolution to reduce CPU
    JPEG_QUALITY = 75

    def generate_frames_with_detection():
        prev_small = None
        last_send = 0.0
        while True:
            frame = camera_stream.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            cfg = get_settings()
            m_thresh = int(cfg.get('threshold', 25))
            m_kernel = int(cfg.get('kernel', 15))
            m_iters = int(cfg.get('iterations', 2))
            min_area = int(cfg.get('min_area', 500))
            pad = int(cfg.get('pad', 10))

            # FPS cap
            now_ts = time.time()
            min_interval = 1.0 / max(1, TARGET_FPS)
            dt = now_ts - last_send
            if dt < min_interval:
                time.sleep(max(0.0, min_interval - dt))
            last_send = time.time()

            # Downscale for processing
            H, W = frame.shape[:2]
            small = cv2.resize(frame, (int(W * PROC_SCALE), int(H * PROC_SCALE)), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_small is None:
                prev_small = gray
                continue

            frame_delta = cv2.absdiff(prev_small, gray)
            thresh = cv2.threshold(frame_delta, m_thresh, 255, cv2.THRESH_BINARY)[1]
            # Cache kernel by size
            ksize = max(1, m_kernel)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ksize, ksize))
            thresh = cv2.dilate(thresh, kernel, iterations=max(0, m_iters))

            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            motion_detected = False
            x_min = y_min = x_max = y_max = None
            for contour in contours:
                if cv2.contourArea(contour) < min_area:
                    continue
                (x, y, w, h) = cv2.boundingRect(contour)
                if x_min is None:
                    x_min, y_min, x_max, y_max = x, y, x + w, y + h
                    motion_detected = True
                else:
                    x_min = min(x_min, x)
                    y_min = min(y_min, y)
                    x_max = max(x_max, x + w)
                    y_max = max(y_max, y + h)

            if motion_detected:
                # Scale bbox back to full-res coords
                inv = 1.0 / PROC_SCALE
                x1 = int(max(0, x_min - pad) * inv)
                y1 = int(max(0, y_min - pad) * inv)
                x2 = int(min(small.shape[1] - 1, x_max + pad) * inv)
                y2 = int(min(small.shape[0] - 1, y_max + pad) * inv)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)

            status = "MOTION DETECTED" if motion_detected else "No Motion"
            color = (0, 0, 255) if motion_detected else (0, 255, 0)
            cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

            prev_small = gray

            # Downscale for output to reduce JPEG cost if very large
            out = frame
            if W > 960:
                scale_out = 960 / float(W)
                out = cv2.resize(frame, (int(W * scale_out), int(H * scale_out)), interpolation=cv2.INTER_AREA)
            ret, buffer = cv2.imencode('.jpg', out, [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)])
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' + frame_bytes + b'\r\n')

    return generate_frames_with_detection
