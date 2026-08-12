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

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import file_assoc
from bundle import Bundle, BundleError, extract_bundle
from creator_window import CreatorWindow
from editor_window import EditorWindow
from dark_messagebox import show_information, show_warning, show_critical, show_question
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
QLabel#versionLabel { color: #565b68; font-size: 11px; }
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
QPushButton:focus {
    outline: none; background-color: #343946;
}
QPushButton:disabled {
    background-color: #22252d; color: #565b68; border-color: #2a2e37;
}
QPushButton#primaryBtn {
    background-color: #5b7cfa; color: #ffffff; font-weight: 600; border: none;
}
QPushButton#primaryBtn:hover { background-color: #6d8bfb; }
QPushButton#primaryBtn:focus {
    outline: none; background-color: #6d8bfb;
}
QPushButton#primaryBtn:disabled {
    background-color: #3a4150; color: #6a7180; font-weight: 600; border: none;
}
QPushButton#bigBtn {
    font-size: 15px; padding: 14px; background-color: #5b7cfa;
    color: #ffffff; font-weight: 600; border: none; border-radius: 10px;
}
QPushButton#bigBtn:hover { background-color: #6d8bfb; }
QPushButton#bigBtn:focus {
    outline: none; background-color: #6d8bfb;
}
QPushButton#bigBtnAlt {
    font-size: 15px; padding: 14px; background-color: #2a2e37;
    border: 1px solid #3c4252; border-radius: 10px;
}
QPushButton#bigBtnAlt:hover { background-color: #343946; }
QPushButton#bigBtnAlt:focus {
    outline: none; background-color: #343946;
}
QPushButton#assocBtn {
    background-color: transparent; border: none; color: #8b90a0;
    font-size: 12px; padding: 4px 8px;
}
QPushButton#assocBtn:hover { color: #cdd3e0; }
QPushButton#assocBtn:focus {
    outline: none;
}
QToolButton#navBtn {
    background: rgba(255, 255, 255, 0.08); border: none; border-radius: 8px;
    font-size: 30px; color: #cdd3e0; padding: 4px 5px; min-width: 30px;
}
QToolButton#navBtn:hover { background: rgba(255, 255, 255, 0.16); }
QToolButton#navBtn:pressed { background: rgba(255, 255, 255, 0.06); }
QToolButton#navBtn:focus {
    outline: none; background: rgba(255, 255, 255, 0.16);
}
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
QSlider::groove:horizontal:disabled { background: #262a32; }
QSlider::sub-page:horizontal:disabled { background: #262a32; }
QSlider::add-page:horizontal:disabled { background: #262a32; }
QSlider::handle:horizontal:disabled { background: #4a4f5c; }
QSlider::handle:horizontal:disabled:hover { background: #4a4f5c; }
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


class _AlignedButton(QWidget):
    """固定图标宽度的按钮：图标和文字各自独立控件，图标固定宽度保证对齐。"""
    clicked = Signal()

    def __init__(self, icon_char: str, text: str, variant: str = "alt", parent=None):
        super().__init__(parent)
        self._variant = variant
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self.setObjectName("alignedBtn")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(6)
        layout.addStretch()

        # 图标：固定宽度 28px 居中
        icon_color = "#ffffff" if variant == "primary" else "#cfd3dc"
        self._icon_label = QLabel(icon_char)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setFixedWidth(28)
        self._icon_label.setStyleSheet(f"color: {icon_color}; font-size: 15px; background: transparent;")
        layout.addWidget(self._icon_label)

        # 文字
        self._text_label = QLabel(text)
        self._text_label.setStyleSheet("color: #e6e8ee; font-size: 15px; font-weight: 600; background: transparent;")
        layout.addWidget(self._text_label)

        layout.addStretch()

        self._apply_style(variant)
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _apply_style(self, variant: str):
        self._variant = variant
        if variant == "primary":
            self.setStyleSheet(
                "#alignedBtn { background-color: #5b7cfa; border-radius: 10px; }"
                "#alignedBtn:hover { background-color: #6d8bfb; }"
                "#alignedBtn:pressed { background-color: #4a6ae0; }"
            )
        else:
            self.setStyleSheet(
                "#alignedBtn { background-color: #2a2e37; border: 1px solid #3c4252; border-radius: 10px; }"
                "#alignedBtn:hover { background-color: #343946; }"
                "#alignedBtn:pressed { background-color: #262a32; }"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """主界面：创建 / 打开两个入口，支持拖拽 .pmb 文件。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("音乐相册 · 图片音乐播放器")
        self.setMinimumSize(680, 580)
        fit_to_screen(self, 900, 760, 680, 580)
        self.setAcceptDrops(True)
        self.creator = None
        self.editor = None
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

        create_btn = _AlignedButton("＋", "创建音乐相册", "primary")
        create_btn.clicked.connect(self._open_creator)
        root.addWidget(create_btn)

        edit_btn = _AlignedButton("✎", "编辑音乐相册")
        edit_btn.clicked.connect(self._open_editor)
        root.addWidget(edit_btn)

        open_btn = _AlignedButton("▶", "打开音乐相册")
        open_btn.clicked.connect(self._open_file)
        root.addWidget(open_btn)

        extract_btn = _AlignedButton("✂", "拆解音乐相册")
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
        assoc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        assoc_btn.setToolTip("注册后双击 .pmb 音乐相册文件即可用本软件打开")
        assoc_btn.clicked.connect(self._register_assoc)
        assoc_row.addWidget(assoc_btn)
        assoc_row.addStretch()
        root.addLayout(assoc_row)

        # 右下角版本号小字（不显眼）
        version_label = QLabel("v1.2.2")
        version_label.setObjectName("versionLabel")
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(version_label)

    def _register_assoc(self):
        ok, info = file_assoc.register_association()
        if ok:
            show_information(
                self,
                "文件关联已设置",
                "已注册 .pmb 文件关联。\n\n现在双击任意 .pmb 音乐相册文件，"
                "即可直接用本软件打开播放。",
            )
        else:
            show_warning(self, "设置失败", f"注册文件关联时出错：\n{info}")

    def _open_creator(self):
        if self.creator is None:
            self.creator = CreatorWindow(self)
            self.creator.saved.connect(self._play_bundle_path)
        self.creator.show()
        self.creator.raise_()

    def _open_editor(self):
        # 打开 .pmb 文件进行编辑
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要编辑的 .pmb 文件", "", "音乐相册 (*.pmb)"
        )
        if not path:
            return
        
        if self.editor is None:
            self.editor = EditorWindow(self)
            self.editor.saved.connect(self._play_bundle_path)
        
        if self.editor.load_bundle(path):
            self.editor.show()
            self.editor.raise_()

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
            show_warning(self, "拆解失败", str(e))
            return
        show_information(
            self, "拆解完成", f"已还原到：\n{folder}"
        )

    def _play_bundle_path(self, path: str):
        try:
            bundle = Bundle(path)
        except BundleError as e:
            show_warning(self, "无法打开", str(e))
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
            show_warning(None, "无法打开", str(e))
            return 1
        PlayerWindow(bundle).show()
        return app.exec()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
