"""DLT Viewer로 내부 상태를 디버깅하기 위한 로거.

Data/dlt/fcmp_*.dlt 파일에 DLT Storage 포맷으로 기록한다.
DLT Viewer에서 해당 .dlt 파일을 Open 하면 로그를 확인할 수 있다.
"""

from __future__ import annotations

import struct
import sys
import threading
import time
from enum import IntEnum
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class DltLogLevel(IntEnum):
    FATAL = 0x01
    ERROR = 0x02
    WARN = 0x03
    INFO = 0x04
    DEBUG = 0x05
    VERBOSE = 0x06


class FCMP_Dlt:
    """FileCompare 전용 DLT 로거 (APPID=FCMP)."""

    _instance: FCMP_Dlt | None = None
    _lock = threading.Lock()

    def __init__(self, log_dir: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.log_dir = Path(log_dir) if log_dir else root / "Data" / "dlt"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"fcmp_{stamp}.dlt"
        self._ecu = b"FCMP"
        self._msg_count = 0
        self._file_lock = threading.Lock()
        self.info("MAIN", f"DLT session start -> {self.log_path}")

    @classmethod
    def instance(cls, log_dir: str | Path | None = None) -> FCMP_Dlt:
        with cls._lock:
            if cls._instance is None:
                cls._instance = FCMP_Dlt(log_dir=log_dir)
            return cls._instance

    def fatal(self, context: str, message: str) -> None:
        self._write(context, DltLogLevel.FATAL, message)

    def error(self, context: str, message: str) -> None:
        self._write(context, DltLogLevel.ERROR, message)

    def warn(self, context: str, message: str) -> None:
        self._write(context, DltLogLevel.WARN, message)

    def info(self, context: str, message: str) -> None:
        self._write(context, DltLogLevel.INFO, message)

    def debug(self, context: str, message: str) -> None:
        self._write(context, DltLogLevel.DEBUG, message)

    def verbose(self, context: str, message: str) -> None:
        self._write(context, DltLogLevel.VERBOSE, message)

    def _write(self, context: str, level: DltLogLevel, message: str) -> None:
        packet = self._build_packet(context, level, message)
        with self._file_lock:
            with self.log_path.open("ab") as fp:
                fp.write(packet)

    def _build_packet(self, context: str, level: DltLogLevel, message: str) -> bytes:
        now = time.time()
        seconds = int(now)
        microseconds = int((now - seconds) * 1_000_000)

        # Storage header (16 bytes, little-endian timestamps — DLT Viewer 표준)
        storage = (
            b"DLT\x01"
            + struct.pack("<I", seconds)
            + struct.pack("<i", microseconds)
            + self._ecu.ljust(4, b"\x00")[:4]
        )

        apid = b"FCMP"
        ctid = context.encode("ascii", errors="replace")[:4].ljust(4, b"\x00")

        # Extended header: verbose LOG + level, 1 argument
        msin = ((int(level) & 0x0F) << 4) | 0x01
        ext = bytes([msin, 1]) + apid + ctid

        text = message.encode("utf-8", errors="replace") + b"\x00"
        # Type Info: STRG (0x00000200), little-endian payload (MSBF=0)
        type_info = struct.pack("<I", 0x00000200)
        payload = type_info + struct.pack("<H", len(text)) + text

        self._msg_count = (self._msg_count + 1) & 0xFF
        length = 4 + len(ext) + len(payload)
        # Standard header: UEH | VERS=1
        standard = bytes([0x21, self._msg_count]) + struct.pack(">H", length)

        return storage + standard + ext + payload


if __name__ == "__main__":
    # --- 디버깅용 샘플 변수 (여기 값을 바꿔서 직접 실행) ---
    SAMPLE_LOG_DIR = _ROOT / "Data" / "dlt"
    SAMPLE_CONTEXT = "TEST"
    SAMPLE_MESSAGE = "FCMP_Dlt debug main hello"
    # -------------------------------------------------------

    # 단독 실행 시 새 세션 파일 생성
    FCMP_Dlt._instance = None
    dlt = FCMP_Dlt.instance(SAMPLE_LOG_DIR)
    dlt.info(SAMPLE_CONTEXT, SAMPLE_MESSAGE)
    dlt.debug(SAMPLE_CONTEXT, "debug line")
    dlt.warn(SAMPLE_CONTEXT, "warn line")
    print(f"[done] dlt file: {dlt.log_path}")
    print(f"[done] size: {dlt.log_path.stat().st_size} bytes")
