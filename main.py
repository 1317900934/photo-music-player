# -*- coding: utf-8 -*-
"""图片音乐播放器入口。

运行方式：
    pip install -r requirements.txt
    python main.py

主界面提供「创建音乐相册」「打开音乐相册」「拆解音乐相册」三个入口，
也支持直接把 .pmb 文件拖入窗口打开。
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import file_assoc
from bundle import Bundle, BundleError, extract_bundle
from creator_window import CreatorWindow
from player_window import PlayerWindow
from titlebar import APP_ICON, apply_frameless, fit_to_screen

STYLE = """
* { font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"; }
QWidget { color: #e6e8ee; }
/* 自绘标题栏 */
QWidget#titleBar { background: transparent; }
QLabel#tbIcon { font-size: 16px; }
QLabel#tbTitle { font-size: 13px; font-weight: 600; color: #dfe3ec; }
QPushButton#tbBtn {
    background: transparent; border: none; border-radius: 6px;
    color: #9aa0b0; font-size: 13px; font-family: "Segoe UI Symbol";
}
QPushButton#tbBtn:hover { background: rgba(255, 255, 255, 0.10); color: #f2f4f8; }
QPushButton#tbBtn:pressed { background: rgba(255, 255, 255, 0.05); }
QPushButton#tbClose {
    background: transparent; border: none; border-radius: 6px;
    color: #b6bac4; font-size: 13px; font-family: "Segoe UI Symbol";
}
QPushButton#tbClose:hover { background: #e5484d; color: #ffffff; }
QPushButton#tbClose:pressed { background: #c93a3f; }
QLabel#logo { font-size: 46px; color: #5b7cfa; }
QLabel#h1 { font-size: 26px; font-weight: 600; color: #f2f4f8; }
QLabel#hint { color: #8b90a0; font-size: 12px; }
QLabel#windowTitle { font-size: 16px; font-weight: 600; color: #f2f4f8; }
QLabel#songTitle { font-size: 14px; font-weight: 500; color: #dfe3ec; }
QLabel#indexLabel { color: #8b90a0; font-size: 12px; }
QLabel#timeLabel { color: #9aa0b0; font-size: 12px; }
QLabel#gallery { background-color: #101216; border-radius: 12px; }
QPushButton {
    background-color: #2a2e37; border: 1px solid #343946; border-radius: 8px;
    padding: 8px 16px; color: #e6e8ee; font-size: 13px;
}
QPushButton:hover { background-color: #343946; }
QPushButton:pressed { background-color: #22252d; }
QPushButton:disabled {
    background-color: #22252d; color: #565b68; border-color: #2a2e37;
}
QPushButton#primaryBtn {
    background-color: #5b7cfa; color: #ffffff; font-weight: 600; border: none;
}
QPushButton#primaryBtn:hover { background-color: #6d8bfb; }
QPushButton#bigBtn {
    font-size: 15px; padding: 14px; background-color: #5b7cfa;
    color: #ffffff; font-weight: 600; border: none; border-radius: 10px;
}
QPushButton#bigBtn:hover { background-color: #6d8bfb; }
QPushButton#bigBtnAlt {
    font-size: 15px; padding: 14px; background-color: #2a2e37;
    border: 1px solid #3c4252; border-radius: 10px;
}
QPushButton#bigBtnAlt:hover { background-color: #343946; }
QPushButton#assocBtn {
    background-color: transparent; border: none; color: #8b90a0;
    font-size: 12px; padding: 4px 8px;
}
QPushButton#assocBtn:hover { color: #cdd3e0; text-decoration: underline; }
QToolButton#navBtn {
    background: rgba(255, 255, 255, 0.08); border: none; border-radius: 8px;
    font-size: 30px; color: #cdd3e0; padding: 4px 5px; min-width: 30px;
}
QToolButton#navBtn:hover { background: rgba(255, 255, 255, 0.16); }
QToolButton#navBtn:pressed { background: rgba(255, 255, 255, 0.06); }
QLineEdit {
    background-color: #22252d; border: 1px solid #3c4252; border-radius: 8px;
    padding: 8px 12px; color: #e6e8ee; font-size: 13px;
}
QLineEdit:focus { border-color: #5b7cfa; }
QListWidget {
    background-color: #1d2027; border: 1px solid #2f333e; border-radius: 8px;
    padding: 6px; color: #dde1ea; font-size: 12px;
}
QListWidget::item { padding: 6px 8px; border-radius: 5px; }
QListWidget::item:selected { background-color: #3a4a8f; color: #ffffff; }
QListWidget::item:hover { background-color: #2a2e37; }
QSlider::groove:horizontal { height: 4px; background: #343946; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #5b7cfa; border-radius: 2px; }
QSlider::add-page:horizontal { background: #343946; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0;
    background: #f2f4f8; border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: #ffffff; }
QWidget#musicPanel { background-color: #1d2027; border-radius: 12px; }
QLabel#volIcon { font-size: 15px; }
QMenu {
    background-color: #22252d; color: #e6e8ee;
    border: 1px solid #3c4252; border-radius: 8px; padding: 6px;
}
QMenu::item { padding: 7px 28px; border-radius: 5px; }
QMenu::item:selected { background-color: #3a4a8f; }
QMenu::item:checked { font-weight: 600; color: #8fb0ff; }
"""


class MainWindow(QMainWindow):
    """主界面：创建 / 打开两个入口，支持拖拽 .pmb 文件。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("音乐相册 · 图片音乐播放器")
        self.setMinimumSize(680, 580)
        fit_to_screen(self, 900, 760, 680, 580)
        self.setAcceptDrops(True)
        self.creator = None
        self.player = None

        _, _, inner = apply_frameless(self, "音乐相册", icon=APP_ICON)
        root = QVBoxLayout()
        root.setContentsMargins(40, 16, 40, 36)
        root.setSpacing(14)
        inner.addLayout(root, 1)

        logo = QLabel("🎞️")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(logo)

        title = QLabel("音乐相册")
        title.setObjectName("h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel("把照片和音乐打包成独特格式，在音乐中重温回忆")
        subtitle.setObjectName("hint")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        root.addSpacing(10)

        create_btn = QPushButton("＋ 创建音乐相册")
        create_btn.setObjectName("bigBtn")
        create_btn.clicked.connect(self._open_creator)
        root.addWidget(create_btn)

        open_btn = QPushButton("▶ 打开音乐相册")
        open_btn.setObjectName("bigBtnAlt")
        open_btn.clicked.connect(self._open_file)
        root.addWidget(open_btn)

        extract_btn = QPushButton("✂ 拆解音乐相册")
        extract_btn.setObjectName("bigBtnAlt")
        extract_btn.clicked.connect(self._extract_bundle)
        root.addWidget(extract_btn)

        tip = QLabel("提示：也可以直接把 .pmb 文件拖到窗口上打开")
        tip.setObjectName("hint")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(tip)

        assoc_row = QHBoxLayout()
        assoc_row.addStretch()
        assoc_btn = QPushButton("⚙ 设置 .pmb 文件关联")
        assoc_btn.setObjectName("assocBtn")
        assoc_btn.setToolTip("注册后双击 .pmb 音乐相册文件即可用本软件打开")
        assoc_btn.clicked.connect(self._register_assoc)
        assoc_row.addWidget(assoc_btn)
        assoc_row.addStretch()
        root.addLayout(assoc_row)

    def _register_assoc(self):
        ok, info = file_assoc.register_association()
        if ok:
            QMessageBox.information(
                self,
                "文件关联已设置",
                "已注册 .pmb 文件关联。\n\n现在双击任意 .pmb 音乐相册文件，"
                "即可直接用本软件打开播放。",
            )
        else:
            QMessageBox.warning(self, "设置失败", f"注册文件关联时出错：\n{info}")

    def _open_creator(self):
        if self.creator is None:
            self.creator = CreatorWindow(self)
            self.creator.saved.connect(self._play_bundle_path)
        self.creator.show()
        self.creator.raise_()

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开音乐相册", "", "音乐相册 (*.pmb)"
        )
        if path:
            self._play_bundle_path(path)

    def _extract_bundle(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要拆解的 .pmb 文件", "", "音乐相册 (*.pmb)"
        )
        if not path:
            return
        dest = QFileDialog.getExistingDirectory(self, "选择保存位置")
        if not dest:
            return
        try:
            folder = extract_bundle(path, dest)
        except BundleError as e:
            QMessageBox.warning(self, "拆解失败", str(e))
            return
        QMessageBox.information(
            self, "拆解完成", f"已还原到：\n{folder}"
        )

    def _play_bundle_path(self, path: str):
        try:
            bundle = Bundle(path)
        except BundleError as e:
            QMessageBox.warning(self, "无法打开", str(e))
            return
        self._open_player(bundle)

    def _open_player(self, bundle: Bundle):
        self.player = PlayerWindow(bundle)
        self.player.closed.connect(self.show)
        self.player.show()
        self.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(".pmb"):
                self._play_bundle_path(path)
                return


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("音乐相册")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    # 启动时静默刷新 .pmb 文件关联（保证移动目录后路径仍有效）
    file_assoc.register_association()
    # 通过文件关联/命令行直接打开 .pmb：只显示播放器，不启动主界面
    if len(sys.argv) > 1:
        try:
            bundle = Bundle(sys.argv[1])
        except BundleError as e:
            QMessageBox.warning(None, "无法打开", str(e))
            return 1
        PlayerWindow(bundle).show()
        return app.exec()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
