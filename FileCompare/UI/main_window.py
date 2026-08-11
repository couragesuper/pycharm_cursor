"""FileCompare Main UI."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from Core.FCMP_CompareMeta import FCMP_CompareMeta
from Core.FCMP_CreateMeta import FCMP_CreateMeta
from Core.FCMP_Dlt import FCMP_Dlt


class _CreateMetaWorker(QObject):
    finished = Signal(str, float)
    failed = Signal(str)
    # videos_found, dirs_scanned, current_folder
    progress = Signal(int, int, str)

    def __init__(self, target: str, nickname: str, data_dir: Path) -> None:
        super().__init__()
        self._target = target
        self._nickname = nickname
        self._data_dir = data_dir

    @Slot()
    def run(self) -> None:
        try:
            creator = FCMP_CreateMeta(self._data_dir)
            out = creator.create(
                self._target,
                self._nickname,
                progress=lambda videos, dirs, folder: self.progress.emit(
                    videos, dirs, folder
                ),
            )
            self.finished.emit(str(out), creator.last_elapsed_sec)
        except Exception as exc:  # noqa: BLE001 - UI에 메시지 전달
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FileCompare")
        self.resize(780, 680)

        self._project_root = Path(__file__).resolve().parent.parent
        self._data_dir = self._project_root / "Data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self.dlt = FCMP_Dlt.instance(self._data_dir / "dlt")
        self._creator = FCMP_CreateMeta(self._data_dir)
        self._comparer = FCMP_CompareMeta(self._data_dir)
        self._selected_folder = ""
        self._worker_thread: QThread | None = None
        self._worker: _CreateMetaWorker | None = None
        self._op_started_at: float | None = None
        self._last_compare_result: dict | None = None

        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self._on_tick)

        self._build_ui()
        self.refresh_meta_list()
        self._set_status("대기", elapsed=None, done=False)
        self._set_progress(None, None)
        self.dlt.info("MAIN", "MainWindow ready")

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        # --- Meta 생성 ---
        layout.addWidget(QLabel("메타데이터 생성"))

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("스캔할 폴더/드라이브 경로")
        self.folder_edit.setReadOnly(True)
        browse_btn = QPushButton("폴더 선택")
        browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(self.folder_edit, stretch=1)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        nick_row = QHBoxLayout()
        self.nickname_edit = QLineEdit()
        self.nickname_edit.setPlaceholderText("nickname (결과: fcmp_nickname.json)")
        create_btn = QPushButton("메타 생성")
        create_btn.clicked.connect(self._on_create_meta)
        nick_row.addWidget(QLabel("Nickname"))
        nick_row.addWidget(self.nickname_edit, stretch=1)
        nick_row.addWidget(create_btn)
        layout.addLayout(nick_row)

        # --- Separator ---
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #888;")
        layout.addWidget(sep)

        # --- Meta 목록 / Compare / 삭제 ---
        layout.addWidget(QLabel("생성된 MetaData (fcmp_*.json) — 선택 후 Compare(2개) 또는 삭제"))

        list_row = QHBoxLayout()
        self.meta_list = QListWidget()
        self.meta_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        list_row.addWidget(self.meta_list, stretch=1)

        side = QVBoxLayout()
        refresh_btn = QPushButton("목록 새로고침")
        refresh_btn.clicked.connect(self.refresh_meta_list)
        compare_btn = QPushButton("Compare")
        compare_btn.clicked.connect(self._on_compare)
        delete_btn = QPushButton("삭제")
        delete_btn.clicked.connect(self._on_delete_meta)
        side.addWidget(refresh_btn)
        side.addWidget(compare_btn)
        side.addWidget(delete_btn)
        side.addStretch(1)
        list_row.addLayout(side)
        layout.addLayout(list_row)

        compare_header = QHBoxLayout()
        compare_header.addWidget(QLabel("Compare 결과 (LeftOnly / 파일명 / 위치 / 사이즈)"))
        compare_header.addStretch(1)
        save_csv_btn = QPushButton("CSV 저장")
        save_csv_btn.clicked.connect(self._on_save_compare_csv)
        compare_header.addWidget(save_csv_btn)
        layout.addLayout(compare_header)

        self.compare_list = QListWidget()
        layout.addWidget(self.compare_list, stretch=1)

        # --- Separator (Status 위) ---
        sep_status = QWidget()
        sep_status.setFixedHeight(1)
        sep_status.setStyleSheet("background-color: #888;")
        layout.addWidget(sep_status)

        # --- Status (하단: 폴더/파일수 / 실행 시간 / 완료) ---
        self.status_progress = QLabel("처리: -")
        self.status_progress.setWordWrap(True)
        layout.addWidget(self.status_progress)

        status_row = QHBoxLayout()
        self.status_state = QLabel("Status: 대기")
        self.status_elapsed = QLabel("실행 시간: -")
        self.status_done = QLabel("완료: -")
        status_row.addWidget(self.status_state)
        status_row.addStretch(1)
        status_row.addWidget(self.status_elapsed)
        status_row.addWidget(self.status_done)
        layout.addLayout(status_row)

        self.setCentralWidget(root)
        bar = QStatusBar()
        self.setStatusBar(bar)
        bar.showMessage(f"DLT: {self.dlt.log_path}")

    def _set_status(self, state: str, elapsed: float | None, done: bool | None) -> None:
        self.status_state.setText(f"Status: {state}")
        if elapsed is None:
            self.status_elapsed.setText("실행 시간: -")
        else:
            self.status_elapsed.setText(f"실행 시간: {elapsed:.2f}s")
        if done is None:
            self.status_done.setText("완료: -")
        elif done:
            self.status_done.setText("완료: 완료")
        else:
            self.status_done.setText("완료: 진행 중")

    def _set_progress(
        self,
        videos: int | None,
        folder: str | None,
        dirs: int | None = None,
    ) -> None:
        if videos is None and folder is None:
            self.status_progress.setText("처리: -")
            return
        video_text = "0" if videos is None else f"{videos:,}"
        dirs_text = "-" if dirs is None else f"{dirs:,}"
        folder_text = folder or "-"
        self.status_progress.setText(
            f"동영상: {video_text} | 폴더스캔: {dirs_text} | 현재: {folder_text}"
        )

    def _start_timing(self, state: str) -> None:
        self._op_started_at = time.perf_counter()
        self._set_status(state, 0.0, False)
        self._set_progress(0, None)
        self._tick.start()

    def _on_tick(self) -> None:
        if self._op_started_at is None:
            return
        elapsed = time.perf_counter() - self._op_started_at
        self.status_elapsed.setText(f"실행 시간: {elapsed:.2f}s")

    def _finish_timing(self, state: str, elapsed: float, ok: bool) -> None:
        self._tick.stop()
        self._op_started_at = None
        self._set_status(state, elapsed, ok)

    def refresh_meta_list(self) -> None:
        self.meta_list.clear()
        for path in self._creator.list_meta_files():
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.meta_list.addItem(item)
        self.dlt.debug("MAIN", f"meta list refreshed count={self.meta_list.count()}")

    def _on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "스캔할 폴더 선택")
        if folder:
            self._selected_folder = folder
            self.folder_edit.setText(folder)
            self.dlt.info("MAIN", f"folder selected: {folder}")

    def _on_create_meta(self) -> None:
        folder = self.folder_edit.text().strip()
        nickname = self.nickname_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "입력 오류", "폴더를 선택하세요.")
            return
        if not nickname:
            QMessageBox.warning(self, "입력 오류", "nickname을 입력하세요.")
            return
        if self._worker_thread is not None:
            QMessageBox.information(self, "진행 중", "이미 메타 생성이 진행 중입니다.")
            return

        self.dlt.info("MAIN", f"create requested nick={nickname}")
        self._start_timing("메타데이터 생성")
        self._set_progress(0, folder, 0)
        self.statusBar().showMessage(f"메타 생성 중... | {folder}")

        thread = QThread(self)
        worker = _CreateMetaWorker(folder, nickname, self._data_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_create_progress)
        worker.finished.connect(self._on_create_finished)
        worker.failed.connect(self._on_create_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._clear_worker)
        # QThread 사용 시 worker 참조를 유지해야 GC로 작업이 끊기지 않음
        self._worker = worker
        self._worker_thread = thread
        thread.start()

    def _on_create_progress(self, videos: int, dirs: int, folder: str) -> None:
        self._set_progress(videos, folder, dirs)
        self.statusBar().showMessage(
            f"스캔 중... 동영상 {videos:,} / 폴더 {dirs:,} | {folder}"
        )

    def _clear_worker(self) -> None:
        self._worker_thread = None
        self._worker = None

    def _on_create_finished(self, out_path: str, elapsed: float) -> None:
        self._finish_timing("메타데이터 생성", elapsed, True)
        self.statusBar().showMessage(f"생성 완료: {out_path}")
        self.refresh_meta_list()
        self.dlt.info("MAIN", f"create UI done elapsed={elapsed:.3f}s")
        QMessageBox.information(
            self,
            "완료",
            f"메타데이터 생성 완료\n{out_path}\n실행 시간: {elapsed:.2f}s",
        )

    def _on_create_failed(self, message: str) -> None:
        elapsed = 0.0
        if self._op_started_at is not None:
            elapsed = time.perf_counter() - self._op_started_at
        self._finish_timing("메타데이터 생성 실패", elapsed, False)
        self._set_progress(None, None)
        self.statusBar().showMessage("메타 생성 실패")
        self.dlt.error("MAIN", f"create failed: {message}")
        QMessageBox.critical(self, "오류", message)

    def _on_delete_meta(self) -> None:
        selected = self.meta_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "선택 오류", "삭제할 MetaData를 선택하세요.")
            return

        names = [item.text() for item in selected]
        preview = "\n".join(names[:10])
        if len(names) > 10:
            preview += f"\n... 외 {len(names) - 10}개"

        answer = QMessageBox.question(
            self,
            "메타데이터 삭제",
            f"선택한 {len(names)}개 파일을 삭제할까요?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        errors: list[str] = []
        for item in selected:
            path = Path(item.data(Qt.ItemDataRole.UserRole))
            try:
                path.unlink(missing_ok=False)
                deleted += 1
                self.dlt.info("MAIN", f"meta deleted: {path.name}")
            except OSError as exc:
                errors.append(f"{path.name}: {exc}")
                self.dlt.error("MAIN", f"meta delete failed: {path.name} {exc}")

        self.refresh_meta_list()
        self.statusBar().showMessage(f"메타 삭제: {deleted}개 완료")
        if errors:
            QMessageBox.warning(
                self,
                "일부 삭제 실패",
                f"{deleted}개 삭제됨.\n실패:\n" + "\n".join(errors),
            )

    def _on_compare(self) -> None:
        selected = self.meta_list.selectedItems()
        if len(selected) != 2:
            QMessageBox.warning(self, "선택 오류", "비교할 MetaData를 정확히 2개 선택하세요.")
            return

        left = Path(selected[0].data(Qt.ItemDataRole.UserRole))
        right = Path(selected[1].data(Qt.ItemDataRole.UserRole))
        self.dlt.info("MAIN", f"compare requested {left.name} vs {right.name}")
        self._start_timing("Compare")

        try:
            result = self._comparer.compare(left, right, save=False)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - (self._op_started_at or time.perf_counter())
            self._finish_timing("Compare 실패", elapsed, False)
            self.dlt.error("MAIN", f"compare failed: {exc}")
            QMessageBox.critical(self, "비교 오류", str(exc))
            return

        elapsed = float(result.get("elapsed_sec", self._comparer.last_elapsed_sec))
        self._finish_timing("Compare", elapsed, True)
        self._last_compare_result = result

        self.compare_list.clear()
        for row in self._comparer.to_list_rows(result):
            self.compare_list.addItem(row)

        summary = result.get("summary", {})
        self.statusBar().showMessage(
            f"비교 완료 LeftOnly={summary.get('only_left', 0)} "
            f"RightOnly={summary.get('only_right', 0)} ({elapsed:.2f}s) — CSV는 수동 저장"
        )

    def _on_save_compare_csv(self) -> None:
        if not self._last_compare_result:
            QMessageBox.information(self, "CSV 저장", "먼저 Compare를 실행하세요.")
            return

        left = self._last_compare_result.get("left", "left")
        right = self._last_compare_result.get("right", "right")
        default_name = f"fcmp_cmp_{left}_vs_{right}.csv"
        default_path = str(self._data_dir / default_name)

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Compare 결과 CSV 저장",
            default_path,
            "CSV Files (*.csv)",
        )
        if not out_path:
            return

        try:
            saved = self._comparer.save_csv(self._last_compare_result, out_path)
        except OSError as exc:
            self.dlt.error("MAIN", f"csv save failed: {exc}")
            QMessageBox.critical(self, "저장 실패", str(exc))
            return

        self._last_compare_result["saved_path"] = str(saved)
        self.dlt.info("MAIN", f"compare csv saved: {saved}")
        self.statusBar().showMessage(f"CSV 저장 완료: {saved}")
        QMessageBox.information(self, "CSV 저장", f"저장 완료\n{saved}")
