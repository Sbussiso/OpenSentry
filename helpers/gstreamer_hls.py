import os
import threading
import time
from typing import Optional, Callable

try:
    import gi  # type: ignore
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib  # type: ignore
except Exception:  # pragma: no cover - optional dep
    Gst = None  # type: ignore
    GLib = None  # type: ignore

import numpy as np  # type: ignore


class HLSStream:
    """Minimal GStreamer HLS pipeline fed by numpy BGR frames via appsrc.

    - Creates / clears an output directory with index.m3u8 + segments.
    - Tries hardware H.264 encoder (v4l2h264enc) first; falls back to x264enc.
    - Runs a GLib main loop and a producer thread that pushes frames at target FPS.
    - Safe no-op on systems without GStreamer (pipeline won't start).
    """

    def __init__(self, camera_stream, out_dir: str, fps: int = 12, bitrate_kbps: int = 2500, frame_fn: Optional[Callable[[], Optional["np.ndarray"]]] = None):
        self.camera_stream = camera_stream
        self.out_dir = out_dir
        self.fps = max(1, int(fps))
        self.bitrate_kbps = max(200, int(bitrate_kbps))
        self._frame_fn = frame_fn

        self._loop: Optional[GLib.MainLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._producer_thread: Optional[threading.Thread] = None
        self._running = False

        self._pipeline: Optional["Gst.Pipeline"] = None
        self._appsrc: Optional["Gst.Element"] = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._ts_ns = 0

        # init GStreamer if present
        if Gst is not None:
            try:
                Gst.init(None)
            except Exception:
                pass

    def start(self):
        if self._running:
            return
        self._running = True
        # Ensure output directory exists and is empty
        os.makedirs(self.out_dir, exist_ok=True)
        for f in os.listdir(self.out_dir):
            if f.endswith('.m3u8') or f.endswith('.ts'):
                try:
                    os.remove(os.path.join(self.out_dir, f))
                except Exception:
                    pass
        # Start GLib main loop
        if Gst is not None and GLib is not None:
            try:
                self._loop = GLib.MainLoop()
                self._loop_thread = threading.Thread(target=self._loop.run, name='GstMainLoop', daemon=True)
                self._loop_thread.start()
            except Exception:
                self._loop = None
                self._loop_thread = None
        # Start producer
        self._producer_thread = threading.Thread(target=self._producer, name='HLSProducer', daemon=True)
        self._producer_thread.start()

    def stop(self):
        self._running = False
        try:
            if self._pipeline is not None:
                self._pipeline.set_state(Gst.State.NULL)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._pipeline = None
        try:
            if self._loop is not None:
                self._loop.quit()
        except Exception:
            pass
        self._loop = None

    def _ensure_pipeline(self, width: int, height: int):
        if self._pipeline is not None or Gst is None:
            return
        self._width, self._height = int(width), int(height)

        # hlssink paths must be absolute to avoid surprises inside containers
        playlist = os.path.join(self.out_dir, 'index.m3u8')
        segment = os.path.join(self.out_dir, 'segment%05d.ts')

        # First try hardware encoder
        common = (
            f"appsrc name=src is-live=true format=time do-timestamp=true block=true ! "
            f"videoconvert ! video/x-raw,format=NV12 ! "
            f"{self._hw_encoder()} ! h264parse ! mpegtsmux ! "
            f"hlssink target-duration=1 max-files=5 playlist-location={playlist} location={segment}"
        )
        pipeline = None
        try:
            pipeline = Gst.parse_launch(common)
        except Exception:
            # Fallback to software x264enc
            try:
                sw = (
                    "appsrc name=src is-live=true format=time do-timestamp=true block=true ! "
                    "videoconvert ! video/x-raw,format=I420 ! "
                    f"x264enc tune=zerolatency speed-preset=ultrafast bitrate={self.bitrate_kbps} key-int-max={self.fps*2} ! "
                    "h264parse ! mpegtsmux ! "
                    f"hlssink target-duration=1 max-files=5 playlist-location={playlist} location={segment}"
                )
                pipeline = Gst.parse_launch(sw)
            except Exception:
                pipeline = None
        if pipeline is None:
            return
        self._pipeline = pipeline  # type: ignore[assignment]

        # Obtain appsrc and set caps
        appsrc = self._pipeline.get_by_name("src")  # type: ignore[union-attr]
        if appsrc is None:
            self._pipeline = None
            return
        caps = Gst.Caps.from_string(
            f"video/x-raw,format=BGR,width={self._width},height={self._height},framerate={self.fps}/1"
        )
        try:
            appsrc.set_property('caps', caps)
        except Exception:
            pass
        self._appsrc = appsrc

        # Attach bus for error logging
        try:
            bus = self._pipeline.get_bus()  # type: ignore[union-attr]
            bus.add_signal_watch()
            bus.connect('message', self._on_bus_message)
        except Exception:
            pass

        # Start pipeline
        try:
            self._pipeline.set_state(Gst.State.PLAYING)  # type: ignore[attr-defined]
        except Exception:
            self._pipeline = None
            self._appsrc = None

    def _on_bus_message(self, bus, message):  # pragma: no cover - logging only
        t = message.type
        try:
            if t == Gst.MessageType.ERROR:
                err, dbg = message.parse_error()
                print(f"[GStreamer] ERROR: {err} {dbg}")
            elif t == Gst.MessageType.WARNING:
                err, dbg = message.parse_warning()
                print(f"[GStreamer] WARNING: {err} {dbg}")
        except Exception:
            pass

    def _hw_encoder(self) -> str:
        """Return v4l2h264enc with suggested properties for Pi, otherwise generic v4l2h264enc."""
        # key-int-max ~ 2x fps gives 2s GOP; adjust for latency/seekability
        return (
            f"v4l2h264enc extra-controls=encode,frame_level_rate_control_enable=1 ! "
            f"video/x-h264,profile=baseline,level=(string)3.1,stream-format=byte-stream,alignment=au,framerate={self.fps}/1,"
            f"width={self._width},height={self._height},bitrate={self.bitrate_kbps*1000}"
        )

    def _producer(self):
        # push frames at target fps
        period = 1.0 / float(self.fps)
        duration_ns = int(1e9 * period)
        while self._running:
            t0 = time.time()
            try:
                if self._frame_fn is not None:
                    frame = self._frame_fn()
                else:
                    frame = self.camera_stream.get_frame()
            except Exception:
                frame = None
            if frame is None:
                time.sleep(0.01)
                continue
            if not isinstance(frame, np.ndarray) or frame.ndim != 3:
                time.sleep(0.01)
                continue
            h, w = frame.shape[:2]
            if self._pipeline is None and Gst is not None:
                self._ensure_pipeline(w, h)
                # Give the pipeline a moment to preroll
                time.sleep(0.05)
            if self._appsrc is not None and Gst is not None:
                try:
                    data = frame.tobytes()
                    buf = Gst.Buffer.new_allocate(None, len(data), None)
                    buf.fill(0, data)
                    buf.pts = self._ts_ns
                    buf.dts = self._ts_ns
                    buf.duration = duration_ns
                    self._ts_ns += duration_ns
                    self._appsrc.emit('push-buffer', buf)
                except Exception:
                    pass
            # pace
            dt = time.time() - t0
            if dt < period:
                time.sleep(period - dt)

