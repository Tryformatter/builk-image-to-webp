from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QSlider, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from converter import (
    SUPPORTED_EXTENSIONS, ConversionOptions, ConversionResult, convert_many,
    discover_images, readable_size,
)


APP_NAME = "WebP Forge"
APP_VERSION = "1.0.0"


class ConversionWorker(QObject):
    result_ready = Signal(int, object)
    finished = Signal()

    def __init__(self, sources: list[Path], options: ConversionOptions, cancel_event: threading.Event) -> None:
        super().__init__()
        self.sources = sources
        self.options = options
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        convert_many(
            self.sources,
            self.options,
            self.cancel_event,
            lambda index, result: self.result_ready.emit(index, result),
        )
        self.finished.emit()


class DropTable(QTableWidget):
    paths_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()


class WebPForge(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.files: list[Path] = []
        self.known_files: set[str] = set()
        self.results: list[ConversionResult] = []
        self.cancel_event = threading.Event()
        self.worker_thread: QThread | None = None
        self.worker: ConversionWorker | None = None

        self.setWindowTitle(f"{APP_NAME} — Bulk Image Converter")
        self.setWindowIcon(self._make_icon())
        self.resize(1080, 730)
        self.setMinimumSize(900, 620)
        self._build_ui()
        self._apply_styles()

    @staticmethod
    def _make_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("#152238"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#34d399"))
        painter.drawRoundedRect(11, 13, 42, 38, 9, 9)
        painter.setBrush(QColor("#152238"))
        painter.drawRoundedRect(18, 20, 28, 24, 5, 5)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(25, 26, 14, 12)
        painter.end()
        return QIcon(pixmap)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(30, 18, 30, 18)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel("Fast, private batch conversion — your images never leave this computer")
        subtitle.setObjectName("appSubtitle")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        header_layout.addLayout(title_stack)
        header_layout.addStretch()
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("appSubtitle")
        header_layout.addWidget(version, alignment=Qt.AlignmentFlag.AlignTop)
        page.addWidget(header)

        body = QWidget()
        body.setObjectName("body")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 14)
        body_layout.setSpacing(14)
        page.addWidget(body, stretch=1)

        files_card = QFrame()
        files_card.setObjectName("card")
        files_layout = QVBoxLayout(files_card)
        files_layout.setContentsMargins(18, 17, 18, 18)
        files_layout.setSpacing(12)
        files_heading = QHBoxLayout()
        heading = QLabel("Images")
        heading.setObjectName("cardTitle")
        self.summary_label = QLabel("No images added yet")
        self.summary_label.setObjectName("muted")
        files_heading.addWidget(heading)
        files_heading.addStretch()
        files_heading.addWidget(self.summary_label)
        files_layout.addLayout(files_heading)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.add_files_button = QPushButton("＋  Add images")
        self.add_files_button.setObjectName("primary")
        self.add_files_button.clicked.connect(self.add_files)
        self.add_folder_button = QPushButton("Add folder")
        self.add_folder_button.clicked.connect(self.add_folder)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("danger")
        self.clear_button.clicked.connect(self.clear_files)
        actions.addWidget(self.add_files_button)
        actions.addWidget(self.add_folder_button)
        actions.addStretch()
        actions.addWidget(self.clear_button)
        actions.addWidget(self.remove_button)
        files_layout.addLayout(actions)

        self.table = DropTable()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["FILE", "TYPE", "DIMENSIONS", "SIZE", "STATUS"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumWidth(540)
        self.table.paths_dropped.connect(self._handle_dropped_paths)
        files_layout.addWidget(self.table, stretch=1)
        self.drop_hint = QLabel("Drop images or folders here  ·  JPG, PNG, BMP, TIFF, GIF")
        self.drop_hint.setObjectName("dropHint")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.drop_hint.setParent(self.table.viewport())
        self.drop_hint.show()
        body_layout.addWidget(files_card, stretch=7)

        options_card = QFrame()
        options_card.setObjectName("card")
        options_card.setMinimumWidth(290)
        options_card.setMaximumWidth(350)
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(20, 17, 20, 18)
        options_layout.setSpacing(9)
        title = QLabel("Conversion settings")
        title.setObjectName("cardTitle")
        options_layout.addWidget(title)
        options_layout.addSpacing(10)

        quality_line = QHBoxLayout()
        quality_line.addWidget(QLabel("Quality"))
        quality_line.addStretch()
        self.quality_value = QLabel("82")
        self.quality_value.setObjectName("qualityValue")
        quality_line.addWidget(self.quality_value)
        options_layout.addLayout(quality_line)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(82)
        self.quality_slider.valueChanged.connect(lambda value: self.quality_value.setText(str(value)))
        options_layout.addWidget(self.quality_slider)
        slider_legend = QHBoxLayout()
        smaller = QLabel("Smaller")
        sharper = QLabel("Sharper")
        smaller.setObjectName("muted")
        sharper.setObjectName("muted")
        slider_legend.addWidget(smaller)
        slider_legend.addStretch()
        slider_legend.addWidget(sharper)
        options_layout.addLayout(slider_legend)
        options_layout.addSpacing(8)

        self.lossless = QCheckBox("Lossless compression")
        self.lossless.toggled.connect(self._toggle_lossless)
        self.keep_metadata = QCheckBox("Keep color profile and metadata")
        self.keep_metadata.setChecked(True)
        self.recursive = QCheckBox("Scan subfolders")
        self.recursive.setChecked(True)
        self.overwrite = QCheckBox("Overwrite existing WebP files")
        options_layout.addWidget(self.lossless)
        options_layout.addWidget(self.keep_metadata)
        options_layout.addWidget(self.recursive)
        options_layout.addWidget(self.overwrite)
        options_layout.addSpacing(10)

        save_title = QLabel("Save converted files")
        save_title.setObjectName("sectionTitle")
        options_layout.addWidget(save_title)
        self.source_output = QRadioButton("Beside each original")
        self.source_output.setChecked(True)
        self.custom_output = QRadioButton("In one output folder")
        self.source_output.toggled.connect(self._output_mode_changed)
        options_layout.addWidget(self.source_output)
        options_layout.addWidget(self.custom_output)
        output_line = QHBoxLayout()
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("Output folder")
        self.output_entry.setEnabled(False)
        self.output_browse = QPushButton("Browse")
        self.output_browse.setEnabled(False)
        self.output_browse.clicked.connect(self.choose_output)
        output_line.addWidget(self.output_entry)
        output_line.addWidget(self.output_browse)
        options_layout.addLayout(output_line)
        note = QLabel("With overwrite off, duplicates receive a numbered filename.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        options_layout.addWidget(note)
        options_layout.addStretch()
        self.start_button = QPushButton("Convert to WebP")
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumHeight(42)
        self.start_button.clicked.connect(self.start_conversion)
        options_layout.addWidget(self.start_button)
        body_layout.addWidget(options_card, stretch=3)

        footer = QWidget()
        footer.setObjectName("body")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 18)
        footer_layout.setSpacing(8)
        status_line = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status")
        self.open_output_button = QPushButton("Open output folder")
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self.open_output)
        status_line.addWidget(self.status_label)
        status_line.addStretch()
        status_line.addWidget(self.open_output_button)
        footer_layout.addLayout(status_line)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7)
        footer_layout.addWidget(self.progress)
        page.addWidget(footer)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#root, QWidget#body { background: #f4f7fb; color: #263348; font: 9pt 'Segoe UI'; }
            QFrame#header { background: #152238; }
            QLabel#appTitle { color: white; font: 700 21pt 'Segoe UI'; }
            QLabel#appSubtitle { color: #aebbd0; font-size: 9pt; }
            QFrame#card { background: white; border: 1px solid #e2e8f0; border-radius: 10px; }
            QLabel#cardTitle { color: #182336; font: 700 11pt 'Segoe UI'; }
            QLabel#sectionTitle, QLabel#qualityValue { color: #182336; font-weight: 700; }
            QLabel#muted { color: #718096; font-size: 8.5pt; }
            QLabel#status { color: #334155; font-weight: 600; }
            QLabel#dropHint { color: #8290a3; background: transparent; font-size: 10pt; }
            QPushButton { background: #edf2f7; color: #263348; border: 0; border-radius: 6px; padding: 8px 13px; font-weight: 600; }
            QPushButton:hover { background: #dfe8f1; }
            QPushButton:pressed { background: #d3dee9; }
            QPushButton:disabled { color: #a4aebb; background: #f1f4f7; }
            QPushButton#primary { color: white; background: #16a678; padding: 9px 17px; }
            QPushButton#primary:hover { background: #128962; }
            QPushButton#primary:pressed { background: #0f7454; }
            QPushButton#primary:disabled { background: #9bcfbe; color: white; }
            QPushButton#danger { color: #b42318; background: #fff0f0; }
            QPushButton#danger:hover { background: #ffe0e0; }
            QTableWidget { background: white; alternate-background-color: #fafcff; border: 1px solid #e5eaf0; border-radius: 6px; selection-background-color: #d9f5eb; selection-color: #17372d; }
            QHeaderView::section { background: #eef3f8; color: #536176; border: 0; border-bottom: 1px solid #dce4ec; padding: 8px; font-weight: 700; }
            QTableWidget::item { border: 0; padding: 6px; }
            QCheckBox, QRadioButton { spacing: 8px; color: #465367; }
            QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
            QLineEdit { border: 1px solid #d5dde7; border-radius: 5px; padding: 7px; background: white; }
            QLineEdit:disabled { background: #f4f6f8; color: #a4aebb; }
            QSlider::groove:horizontal { height: 5px; background: #dbe4ec; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #23b98b; border-radius: 2px; }
            QSlider::handle:horizontal { background: white; border: 2px solid #16a678; width: 16px; margin: -6px 0; border-radius: 9px; }
            QProgressBar { border: 0; background: #dce5ed; border-radius: 3px; }
            QProgressBar::chunk { background: #23b98b; border-radius: 3px; }
            QScrollBar:vertical { background: #f4f6f8; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #c8d2dc; min-height: 24px; border-radius: 5px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "drop_hint"):
            self.drop_hint.setGeometry(0, 45, self.table.viewport().width(), max(40, self.table.viewport().height() - 45))

    def _toggle_lossless(self, checked: bool) -> None:
        self.quality_slider.setEnabled(not checked)
        self.quality_value.setText("Lossless" if checked else str(self.quality_slider.value()))

    def _output_mode_changed(self) -> None:
        enabled = self.custom_output.isChecked()
        self.output_entry.setEnabled(enabled)
        self.output_browse.setEnabled(enabled)

    def add_files(self) -> None:
        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_EXTENSIONS))
        selected, _ = QFileDialog.getOpenFileNames(self, "Choose images", "", f"Supported images ({patterns});;All files (*.*)")
        self._add_paths([Path(item) for item in selected])

    def add_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose a folder of images")
        if not selected:
            return
        paths = discover_images(Path(selected), recursive=self.recursive.isChecked())
        if not paths:
            QMessageBox.information(self, APP_NAME, "No supported images were found in that folder.")
            return
        self._add_paths(paths)

    @Slot(list)
    def _handle_dropped_paths(self, paths: list[Path]) -> None:
        images: list[Path] = []
        for path in paths:
            if path.is_dir():
                images.extend(discover_images(path, recursive=self.recursive.isChecked()))
            else:
                images.append(path)
        self._add_paths(images)

    def _add_paths(self, paths) -> None:
        paths = list(paths)
        added = 0
        for path in paths:
            try:
                resolved = path.resolve()
                key = str(resolved).lower()
                if key in self.known_files or resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                with Image.open(resolved) as image:
                    dimensions = f"{image.width} × {image.height}"
                self.files.append(resolved)
                self.known_files.add(key)
                self._append_row(resolved, dimensions, readable_size(resolved.stat().st_size), "Ready")
                added += 1
            except Exception:
                continue
        self._refresh_summary()
        if paths and added == 0:
            self.status_label.setText("No new supported images were added")

    def _append_row(self, path: Path, dimensions: str, size: str, status: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [path.name, path.suffix[1:].upper(), dimensions, size, status]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in (1, 2, 3, 4):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, column, item)
        self.table.setRowHeight(row, 34)

    def remove_selected(self) -> None:
        if self._is_running():
            return
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.known_files.discard(str(self.files[row]).lower())
            self.files.pop(row)
            self.table.removeRow(row)
        self._refresh_summary()

    def clear_files(self) -> None:
        if self._is_running():
            return
        self.files.clear()
        self.known_files.clear()
        self.results.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.status_label.setText("Ready")
        self.open_output_button.setEnabled(False)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        count = len(self.files)
        total = sum(path.stat().st_size for path in self.files if path.exists())
        self.summary_label.setText("No images added yet" if count == 0 else f"{count} image{'s' if count != 1 else ''} · {readable_size(total)}")
        self.drop_hint.setVisible(count == 0)

    def choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if selected:
            self.output_entry.setText(selected)

    def _is_running(self) -> bool:
        return self.worker_thread is not None and self.worker_thread.isRunning()

    def start_conversion(self) -> None:
        if self._is_running():
            self.cancel_event.set()
            self.status_label.setText("Stopping after the current image…")
            self.start_button.setEnabled(False)
            return
        if not self.files:
            QMessageBox.information(self, APP_NAME, "Add at least one image first.")
            return

        output_folder: Path | None = None
        if self.custom_output.isChecked():
            value = self.output_entry.text().strip()
            if not value:
                QMessageBox.information(self, APP_NAME, "Choose an output folder first.")
                return
            output_folder = Path(value)

        options = ConversionOptions(
            quality=self.quality_slider.value(), lossless=self.lossless.isChecked(),
            keep_metadata=self.keep_metadata.isChecked(), overwrite=self.overwrite.isChecked(),
            output_directory=output_folder,
        )
        self.results.clear()
        self.cancel_event.clear()
        self.progress.setValue(0)
        for row in range(self.table.rowCount()):
            self.table.item(row, 4).setText("Waiting")
        self._set_controls_enabled(False)
        self.start_button.setText("Cancel")
        self.start_button.setEnabled(True)
        self.status_label.setText(f"Converting 0 of {len(self.files)}…")

        self.worker_thread = QThread(self)
        self.worker = ConversionWorker(list(self.files), options, self.cancel_event)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.result_ready.connect(self._on_result)
        self.worker.finished.connect(self._conversion_done)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._thread_finished)
        self.worker_thread.start()

    @Slot(int, object)
    def _on_result(self, index: int, result: ConversionResult) -> None:
        self.results.append(result)
        self.table.item(index, 4).setText("Done" if result.success else "Failed")
        completed = len(self.results)
        self.progress.setValue(round(completed / len(self.files) * 100))
        self.status_label.setText(f"Converting {completed} of {len(self.files)}…")

    @Slot()
    def _conversion_done(self) -> None:
        self._set_controls_enabled(True)
        self.start_button.setText("Convert to WebP")
        self.start_button.setEnabled(True)
        successful = [result for result in self.results if result.success]
        failed = [result for result in self.results if not result.success]
        if self.cancel_event.is_set():
            self.status_label.setText(f"Cancelled · {len(successful)} converted")
        elif failed:
            self.status_label.setText(f"Finished · {len(successful)} converted · {len(failed)} failed")
            details = "\n".join(f"• {item.source.name}: {item.message}" for item in failed[:8])
            QMessageBox.warning(self, APP_NAME, f"Some images could not be converted:\n\n{details}")
        else:
            before = sum(item.input_bytes for item in successful)
            after = sum(item.output_bytes for item in successful)
            change = 0 if before == 0 else round((1 - after / before) * 100)
            saving = f" · {change}% smaller" if change >= 0 else f" · {abs(change)}% larger"
            self.status_label.setText(f"Finished · {len(successful)} converted{saving}")
            self.progress.setValue(100)
        self.open_output_button.setEnabled(bool(successful))

    @Slot()
    def _thread_finished(self) -> None:
        if self.worker_thread:
            self.worker_thread.deleteLater()
        self.worker_thread = None
        self.worker = None

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.add_files_button, self.add_folder_button, self.remove_button,
            self.clear_button, self.quality_slider, self.lossless, self.keep_metadata,
            self.recursive, self.overwrite, self.source_output, self.custom_output,
        ):
            widget.setEnabled(enabled)
        if enabled:
            self.quality_slider.setEnabled(not self.lossless.isChecked())
            self._output_mode_changed()
        else:
            self.output_entry.setEnabled(False)
            self.output_browse.setEnabled(False)

    def open_output(self) -> None:
        successful = next((item for item in reversed(self.results) if item.success and item.destination), None)
        if not successful or not successful.destination:
            return
        try:
            os.startfile(successful.destination.parent)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not open the folder:\n{exc}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_running():
            answer = QMessageBox.question(self, APP_NAME, "A conversion is still running. Stop and exit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_event.set()
            self.worker_thread.quit()
            self.worker_thread.wait(3000)
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("WebP Forge")
    app.setStyle("Fusion")
    window = WebPForge()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
