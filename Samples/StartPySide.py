"""간단한 PySide6 시작 예제."""

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("StartPySide")
        self.resize(360, 180)

        label = QLabel("PySide6가 정상적으로 실행되었습니다.")
        label.setStyleSheet("font-size: 14px;")

        button = QPushButton("닫기")
        button.clicked.connect(self.close)

        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
