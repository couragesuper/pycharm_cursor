"""폴더/드라이브를 재귀 스캔하여 fcmp_*.json 메타데이터를 생성한다."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from Core.FCMP_Dlt import FCMP_Dlt

# progress(count, current_folder)
ProgressCallback = Callable[[int, str], None]

# 동영상만 수집
VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".mpeg",
    ".mpg",
    ".mpe",
    ".m2ts",
    ".mts",
    ".ts",
    ".vob",
    ".3gp",
    ".3g2",
    ".ogv",
    ".f4v",
    ".asf",
    ".rm",
    ".rmvb",
    ".divx",
}

# Windows 숨김/시스템 속성
_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_SYSTEM = 0x4

_SKIP_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "recovery",
    "recycler",
}


class FCMP_CreateMeta:
    """특정 폴더나 드라이브를 전달하면 메타데이터를 생성하는 클래스."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.data_dir = Path(data_dir) if data_dir else root / "Data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.dlt = FCMP_Dlt.instance()
        self.last_elapsed_sec: float = 0.0

    def scan(
        self,
        target: str | Path,
        progress: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """동영상 파일만 재귀 검색하여 메타 목록을 반환한다. 숨김은 제외."""
        target_path = Path(target).resolve()
        if not target_path.exists():
            self.dlt.error("META", f"path not found: {target_path}")
            raise FileNotFoundError(f"경로를 찾을 수 없습니다: {target_path}")

        root = str(target_path)
        self.dlt.info("META", f"scan start (video only, no hidden): {root}")
        if progress:
            progress(0, root)

        files: list[dict[str, Any]] = []
        count = 0
        last_report = 0
        dirs_seen = 0

        for dirpath, dirnames, filenames in os.walk(
            root,
            topdown=True,
            onerror=self._on_walk_error,
            followlinks=False,
        ):
            # 숨김/스킵 폴더는 하위로 들어가지 않음
            dirnames[:] = [
                d
                for d in dirnames
                if not self._should_skip_dir(os.path.join(dirpath, d), d)
            ]

            dirs_seen += 1
            if progress and dirs_seen % 5 == 1:
                progress(count, dirpath)

            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext not in VIDEO_EXTENSIONS:
                    continue

                full = os.path.join(dirpath, name)
                if self._is_hidden(full, name):
                    continue

                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue

                files.append(
                    {
                        "name": name,
                        "path": full,
                        "size": size,
                    }
                )
                count += 1
                if progress and (count - last_report) >= 50:
                    progress(count, dirpath)
                    last_report = count
                    if count % 500 == 0:
                        self.dlt.debug(
                            "META",
                            f"scan progress: {count} videos @ {dirpath}",
                        )

        if progress:
            progress(count, root)
        self.dlt.info("META", f"scan done: {count} video files")
        return files

    def create(
        self,
        target: str | Path,
        nickname: str,
        progress: ProgressCallback | None = None,
    ) -> Path:
        """스캔 결과를 fcmp_{nickname}.json 으로 Data 폴더에 저장한다."""
        started = time.perf_counter()
        nick = self._sanitize_nickname(nickname)
        if not nick:
            self.dlt.error("META", "empty nickname")
            raise ValueError("nickname을 입력하세요.")

        target_path = Path(target).resolve()
        self.dlt.info("META", f"create start nick={nick} root={target_path}")
        files = self.scan(target_path, progress=progress)
        payload = {
            "nickname": nick,
            "root": str(target_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "filter": {
                "video_only": True,
                "skip_hidden": True,
                "extensions": sorted(VIDEO_EXTENSIONS),
            },
            "file_count": len(files),
            "files": files,
        }

        out_path = self.data_dir / f"fcmp_{nick}.json"
        with out_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

        self.last_elapsed_sec = time.perf_counter() - started
        self.dlt.info(
            "META",
            f"create done path={out_path} count={len(files)} "
            f"elapsed={self.last_elapsed_sec:.3f}s",
        )
        return out_path

    def _should_skip_dir(self, full_path: str, name: str) -> bool:
        if name.lower() in _SKIP_DIR_NAMES:
            return True
        if name.startswith("."):
            return True
        return self._is_hidden(full_path, name)

    def _is_hidden(self, full_path: str, name: str) -> bool:
        if name.startswith("."):
            return True
        try:
            attrs = os.stat(full_path).st_file_attributes  # type: ignore[attr-defined]
            if attrs & (_FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM):
                return True
        except (AttributeError, OSError):
            # non-Windows or inaccessible: fall back to name-only rule
            pass
        # Windows 전용 속성 재확인
        if os.name == "nt":
            try:
                import ctypes

                GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
                GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
                GetFileAttributesW.restype = ctypes.c_uint32
                attrs = GetFileAttributesW(full_path)
                if attrs == 0xFFFFFFFF:
                    return False
                if attrs & (_FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM):
                    return True
            except (AttributeError, OSError, ValueError):
                return False
        return False

    def _on_walk_error(self, err: OSError) -> None:
        self.dlt.warn("META", f"walk error: {err}")

    @staticmethod
    def _sanitize_nickname(nickname: str) -> str:
        text = nickname.strip()
        for ch in '\\/:*?"<>|':
            text = text.replace(ch, "_")
        return text

    @staticmethod
    def load(meta_path: str | Path) -> dict[str, Any]:
        path = Path(meta_path)
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    def list_meta_files(self) -> list[Path]:
        """스캔으로 만든 메타만 반환 (compare 결과 제외)."""
        results: list[Path] = []
        for path in sorted(self.data_dir.glob("fcmp_*.json")):
            try:
                data = self.load(path)
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("type") == "compare":
                continue
            if "files" not in data:
                continue
            results.append(path)
        return results
