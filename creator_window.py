# -*- coding: utf-8 -*-
"""创建打包窗口：选择照片和音乐，打包保存为 .pmb 文件。"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bundle import create_bundle
from dark_messagebox import show_information, show_warning, show_critical, show_question
from titlebar import APP_ICON, apply_frameless, fit_to_screen

IMAGE_FILTER = "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp *.gif);;所有文件 (*.*)"
MUSIC_FILTER = (
    "音频文件 (*.mp3 *.wav *.m4a *.aac *.flac *.ogg);;所有文件 (*.*)"
)


class CreatorWindow(QMainWindow):
    """创建音乐相册的主窗口。"""

    saved = Signal(str)  # 保存成功时发出 .pmb 文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建音乐相册")
        self.setMinimumSize(620, 560)
        fit_to_screen(self, 760, 660, 620, 560)
        self.image_paths = []
        self.music_paths = []
        self._build_ui()

    def _build_ui(self):
        _, _, inner = apply_frameless(self, "创建音乐相册", icon=APP_ICON)
        root = QVBoxLayout()
        root.setContentsMargins(24, 12, 24, 18)
        root.setSpacing(10)
        inner.addLayout(root, 1)

        hint = QLabel("选择照片和音乐，打包成一个 .pmb 音乐相册文件（至少 1 张照片，音乐可选）。")
        hint.setObjectName("hint")
        root.addWidget(hint)

        # 相册标题
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("相册标题"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("例如：夏天的旅行")
        title_row.addWidget(self.title_edit, 1)
        root.addLayout(title_row)

        # ---- 照片 ----
        img_header = QHBoxLayout()
        img_header.addWidget(QLabel("照片"))
        img_header.addStretch()
        add_img = QPushButton("＋ 添加照片")
        add_img.clicked.connect(self._add_images)
        img_header.addWidget(add_img)
        root.addLayout(img_header)

        self.image_list = QListWidget()
        self.image_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.image_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.image_list.setStyleSheet("""
            QListWidget {
                min-width: 400px;
                max-height: 120px;
                font-size: 13px;
            }
            QListWidget::item {
                height: 24px;
                padding: 2px;
            }
            QListWidget::item:selected {
                background-color: rgba(91, 124, 250, 0.35);
                color: #e6e8ee;
            }
        """)
        self.image_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.image_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(self.image_list, 3)

        img_footer = QHBoxLayout()
        img_footer.addStretch()
        remove_img = QPushButton("移除选中照片")
        remove_img.clicked.connect(lambda: self._remove_selected(self.image_list, self.image_paths))
        img_footer.addWidget(remove_img)
        root.addLayout(img_footer)

        # ---- 音乐 ----
        music_header = QHBoxLayout()
        music_header.addWidget(QLabel("音乐"))
        music_header.addStretch()
        add_music = QPushButton("＋ 添加音乐")
        add_music.clicked.connect(self._add_musics)
        music_header.addWidget(add_music)
        root.addLayout(music_header)

        self.music_list = QListWidget()
        self.music_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.music_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.music_list.setStyleSheet("""
            QListWidget {
                min-width: 400px;
                max-height: 120px;
                font-size: 13px;
            }
            QListWidget::item {
                height: 24px;
                padding: 2px;
            }
            QListWidget::item:selected {
                background-color: rgba(91, 124, 250, 0.35);
                color: #e6e8ee;
            }
        """)
        self.music_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.music_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(self.music_list, 2)

        music_footer = QHBoxLayout()
        music_footer.addStretch()
        remove_music = QPushButton("移除选中音乐")
        remove_music.clicked.connect(lambda: self._remove_selected(self.music_list, self.music_paths))
        music_footer.addWidget(remove_music)
        root.addLayout(music_footer)

        root.addSpacing(4)

        save_btn = QPushButton("保存为 .pmb 文件")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

        # 所有可点击按钮显示"链接选择"小手光标
        for _btn in self.findChildren(QPushButton):
            _btn.setCursor(Qt.CursorShape.PointingHandCursor)

    # ---------- 文件选择 ----------
    def _add_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择照片", "", IMAGE_FILTER)
        for f in files:
            self.image_paths.append(f)
            item = QListWidgetItem(os.path.basename(f))
            item.setToolTip(os.path.basename(f))
            self.image_list.addItem(item)

    def _add_musics(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择音乐", "", MUSIC_FILTER)
        for f in files:
            self.music_paths.append(f)
            item = QListWidgetItem(os.path.basename(f))
            item.setToolTip(os.path.basename(f))
            self.music_list.addItem(item)

    def _remove_selected(self, list_widget: QListWidget, paths: list):
        """移除选中的列表项，并同步删除对应路径。"""
        rows = sorted(
            (list_widget.row(item) for item in list_widget.selectedItems()),
            reverse=True,
        )
        for row in rows:
            list_widget.takeItem(row)
            if row < len(paths):
                paths.pop(row)

    # ---------- 保存 ----------
    def _save(self):
        if not self.image_paths:
            show_warning(self, "提示", "请至少添加一张照片。")
            return
        title = self.title_edit.text().strip() or "未命名相册"
        default_name = f"{title}.pmb"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存音乐相册", default_name, "音乐相册 (*.pmb)"
        )
        if not path:
            return
        if not path.lower().endswith(".pmb"):
            path += ".pmb"
        try:
            create_bundle(title, self.image_paths, self.music_paths, path)
        except OSError as e:
            show_critical(self, "保存失败", f"保存时出错：\n{e}")
            return
        ret = show_question(
            self,
            "保存成功",
            f"音乐相册已保存到：\n{path}\n\n是否立即打开？",
        )
        if ret:
            self.saved.emit(path)
            self.close()
        else:
            self.close()
