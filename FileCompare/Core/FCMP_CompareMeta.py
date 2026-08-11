"""두 개의 fcmp 메타데이터를 비교하여 차이를 메타데이터화한다."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Core.FCMP_Dlt import FCMP_Dlt


class FCMP_CompareMeta:
    """두 메타데이터 JSON을 비교해 only_left / only_right / size_diff 를 만든다."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.data_dir = Path(data_dir) if data_dir else root / "Data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.dlt = FCMP_Dlt.instance()
        self.last_elapsed_sec: float = 0.0

    def compare(
        self,
        left_meta: str | Path | dict[str, Any],
        right_meta: str | Path | dict[str, Any],
        *,
        save: bool = True,
        result_name: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        left = self._load(left_meta)
        right = self._load(right_meta)

        left_label = left.get("nickname") or Path(str(left_meta)).stem
        right_label = right.get("nickname") or Path(str(right_meta)).stem
        self.dlt.info("CMP", f"compare start left={left_label} right={right_label}")

        left_map = self._index_by_path(left.get("files", []))
        right_map = self._index_by_path(right.get("files", []))

        only_left: list[dict[str, Any]] = []
        only_right: list[dict[str, Any]] = []
        size_diff: list[dict[str, Any]] = []

        for path, info in left_map.items():
            if path not in right_map:
                only_left.append(info)
            elif info.get("size") != right_map[path].get("size"):
                size_diff.append(
                    {
                        "name": info.get("name"),
                        "path": path,
                        "left_size": info.get("size"),
                        "right_size": right_map[path].get("size"),
                    }
                )

        for path, info in right_map.items():
            if path not in left_map:
                only_right.append(info)

        result = {
            "type": "compare",
            "left": left_label,
            "right": right_label,
            "left_root": left.get("root"),
            "right_root": right.get("root"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "only_left": len(only_left),
                "only_right": len(only_right),
                "size_diff": len(size_diff),
            },
            "only_left": only_left,
            "only_right": only_right,
            "size_diff": size_diff,
        }

        if save:
            name = result_name or f"cmp_{left_label}_vs_{right_label}"
            name = self._sanitize(name)
            out_path = self.data_dir / f"fcmp_{name}.json"
            with out_path.open("w", encoding="utf-8") as fp:
                json.dump(result, fp, ensure_ascii=False, indent=2)
            result["saved_path"] = str(out_path)

        self.last_elapsed_sec = time.perf_counter() - started
        result["elapsed_sec"] = self.last_elapsed_sec
        self.dlt.info(
            "CMP",
            f"compare done only_left={len(only_left)} only_right={len(only_right)} "
            f"size_diff={len(size_diff)} elapsed={self.last_elapsed_sec:.3f}s",
        )
        return result

    def to_list_rows(self, result: dict[str, Any]) -> list[str]:
        """UI ListView용 한 줄 요약 문자열 목록."""
        rows: list[str] = []
        summary = result.get("summary", {})
        rows.append(
            f"[요약] only_left={summary.get('only_left', 0)}, "
            f"only_right={summary.get('only_right', 0)}, "
            f"size_diff={summary.get('size_diff', 0)}"
        )

        for item in result.get("only_left", []):
            rows.append(f"[LEFT ONLY] {item.get('path')} ({item.get('size')} bytes)")
        for item in result.get("only_right", []):
            rows.append(f"[RIGHT ONLY] {item.get('path')} ({item.get('size')} bytes)")
        for item in result.get("size_diff", []):
            rows.append(
                f"[SIZE DIFF] {item.get('path')} "
                f"L={item.get('left_size')} R={item.get('right_size')}"
            )
        return rows

    @staticmethod
    def _index_by_path(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for item in files:
            path = item.get("path")
            if path:
                indexed[str(path)] = item
        return indexed

    @staticmethod
    def _load(source: str | Path | dict[str, Any]) -> dict[str, Any]:
        if isinstance(source, dict):
            return source
        path = Path(source)
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    @staticmethod
    def _sanitize(name: str) -> str:
        text = name.strip()
        for ch in '\\/:*?"<>|':
            text = text.replace(ch, "_")
        return text
