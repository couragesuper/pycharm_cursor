"""두 개의 fcmp 메타데이터를 비교하여 차이를 메타데이터화한다.

비교 키: (파일명, 사이즈) — 절대경로는 수집/출력용이며 매칭에는 사용하지 않는다.
결과: left_only / right_only 만 산출하고 CSV로 저장한다.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from Core.FCMP_Dlt import FCMP_Dlt


class FCMP_CompareMeta:
    """키=(name, size)로 비교해 LeftOnly / RightOnly 를 만들고 CSV로 저장한다."""

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
        save: bool = False,
        result_name: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        left = self._load(left_meta)
        right = self._load(right_meta)

        left_label = left.get("nickname") or Path(str(left_meta)).stem
        right_label = right.get("nickname") or Path(str(right_meta)).stem
        self.dlt.info(
            "CMP",
            f"compare start key=(name,size) left={left_label} right={right_label}",
        )

        left_groups = self._group_by_name_size(left.get("files", []))
        right_groups = self._group_by_name_size(right.get("files", []))

        only_left: list[dict[str, Any]] = []
        only_right: list[dict[str, Any]] = []

        all_keys = set(left_groups) | set(right_groups)
        for key in sorted(all_keys, key=lambda k: (k[0].lower(), k[1])):
            left_items = left_groups.get(key, [])
            right_items = right_groups.get(key, [])
            matched = min(len(left_items), len(right_items))
            # 동일 (name, size) 개수만큼 매칭, 남은 쪽만 only_*
            for item in left_items[matched:]:
                only_left.append(self._row("LeftOnly", item))
            for item in right_items[matched:]:
                only_right.append(self._row("RightOnly", item))

        result = {
            "type": "compare",
            "compare_key": "name+size",
            "left": left_label,
            "right": right_label,
            "left_root": left.get("root"),
            "right_root": right.get("root"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "only_left": len(only_left),
                "only_right": len(only_right),
            },
            "only_left": only_left,
            "only_right": only_right,
        }

        if save:
            name = result_name or f"cmp_{left_label}_vs_{right_label}"
            name = self._sanitize(name)
            csv_path = self.data_dir / f"fcmp_{name}.csv"
            self.save_csv(result, csv_path)
            result["saved_path"] = str(csv_path)
            self.dlt.info("CMP", f"compare csv saved: {csv_path}")

        self.last_elapsed_sec = time.perf_counter() - started
        result["elapsed_sec"] = self.last_elapsed_sec
        self.dlt.info(
            "CMP",
            f"compare done only_left={len(only_left)} only_right={len(only_right)} "
            f"elapsed={self.last_elapsed_sec:.3f}s",
        )
        return result

    def save_csv(self, result: dict[str, Any], out_path: str | Path) -> Path:
        """LeftOnly/RightOnly 결과를 CSV로 저장. 컬럼: side, name, path, size."""
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = list(result.get("only_left", [])) + list(result.get("only_right", []))
        with path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=["side", "name", "path", "size"])
            writer.writeheader()
            for item in rows:
                writer.writerow(
                    {
                        "side": item.get("side", ""),
                        "name": item.get("name", ""),
                        "path": item.get("path", ""),
                        "size": item.get("size", ""),
                    }
                )
        return path

    def to_list_rows(self, result: dict[str, Any]) -> list[str]:
        """UI ListView용: LeftOnly|RightOnly / 파일명 / 위치 / 사이즈."""
        rows: list[str] = []
        summary = result.get("summary", {})
        rows.append(
            f"[요약] LeftOnly={summary.get('only_left', 0)}, "
            f"RightOnly={summary.get('only_right', 0)} "
            f"(key=name+size)"
        )
        saved = result.get("saved_path")
        if saved:
            rows.append(f"[CSV] {saved}")

        for item in result.get("only_left", []):
            rows.append(self._format_row(item))
        for item in result.get("only_right", []):
            rows.append(self._format_row(item))
        return rows

    @staticmethod
    def _format_row(item: dict[str, Any]) -> str:
        return (
            f"{item.get('side', '')} / {item.get('name', '')} / "
            f"{item.get('path', '')} / {item.get('size', '')}"
        )

    @staticmethod
    def _row(side: str, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "side": side,
            "name": item.get("name", ""),
            "path": item.get("path", ""),
            "size": item.get("size", 0),
        }

    @staticmethod
    def _group_by_name_size(
        files: list[dict[str, Any]],
    ) -> dict[tuple[str, int], list[dict[str, Any]]]:
        groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for item in files:
            name = str(item.get("name") or "")
            try:
                size = int(item.get("size", 0))
            except (TypeError, ValueError):
                size = 0
            if not name:
                continue
            groups[(name, size)].append(item)
        return groups

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


if __name__ == "__main__":
    # --- 디버깅용 샘플 변수 (여기 값을 바꿔서 직접 실행) ---
    SAMPLE_LEFT = _ROOT / "Data" / "fcmp_oldblue.json"
    SAMPLE_RIGHT = _ROOT / "Data" / "fcmp_newred.json"
    SAMPLE_DATA_DIR = _ROOT / "Data"
    SAMPLE_SAVE = True
    SAMPLE_RESULT_NAME = None  # None 이면 cmp_{left}_vs_{right}
    # -------------------------------------------------------

    comparer = FCMP_CompareMeta(SAMPLE_DATA_DIR)
    result = comparer.compare(
        SAMPLE_LEFT,
        SAMPLE_RIGHT,
        save=SAMPLE_SAVE,
        result_name=SAMPLE_RESULT_NAME,
    )
    print("[summary]", result.get("summary"))
    print("[elapsed]", f"{comparer.last_elapsed_sec:.3f}s")
    print("[saved]", result.get("saved_path"))
    for row in comparer.to_list_rows(result)[:30]:
        print(row)
