from __future__ import annotations

import socket
import threading
from typing import Dict, Optional

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
except Exception:  # pragma: no cover
    Zeroconf = None  # type: ignore
    ServiceInfo = None  # type: ignore
    IPVersion = None  # type: ignore


def _get_local_ip() -> str:
    """Best-effort local IP detection (non-loopback).
    Falls back to 127.0.0.1.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Short timeout to avoid blocking request thread if no network
            s.settimeout(1.0)
        except Exception:
            pass
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        try:
            s.close()
        except Exception:
            pass
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class MdnsAdvertiser:
    """mDNS advertiser for OpenSentry using zeroconf.

    Service type: _opensentry._tcp.local.
    """
    
    def __init__(self, name: str, port: int, txt: Dict[str, str]):
        self.name = name
        self.port = port
        self.txt = {k: str(v) for k, v in (txt or {}).items()}
        self._zc: Optional[Zeroconf] = None
        self._info: Optional[ServiceInfo] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if Zeroconf is None:
            return
        with self._lock:
            if self._zc is not None:
                return
            ip = _get_local_ip()
            try:
                addr = socket.inet_aton(ip)
            except OSError:
                addr = socket.inet_aton("127.0.0.1")
            type_ = "_opensentry._tcp.local."
            name_ = f"{self.name}.{type_}"
            info = ServiceInfo(
                type_,
                name_,
                addresses=[addr],
                port=self.port,
                properties=self.txt,
            )
            zc = Zeroconf(ip_version=IPVersion.V4Only)  # type: ignore
            zc.register_service(info)
            self._zc = zc
            self._info = info

    def update(self, txt: Dict[str, str]) -> None:
        if Zeroconf is None:
            return
        with self._lock:
            if self._zc is None or self._info is None:
                return
            self.txt.update({k: str(v) for k, v in (txt or {}).items()})
            # Re-register with updated TXT
            try:
                self._zc.update_service(self._info, properties=self.txt)
            except Exception:
                pass

    def stop(self) -> None:
        if Zeroconf is None:
            return
        with self._lock:
            if self._zc is None or self._info is None:
                return
            try:
                self._zc.unregister_service(self._info)
            except Exception:
                pass
            try:
                self._zc.close()
            except Exception:
                pass
            self._zc = None
            self._info = None
