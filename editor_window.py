# -*- coding: utf-8 -*-
"""编辑打包窗口：打开 .pmb 文件，修改照片、音乐和标题后保存。"""
import os
import shutil
import tempfile
import zipfile

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
from PySide6.QtWidgets import QDialog

from bundle import Bundle, BundleError, create_bundle, is_bundle, MANIFEST_NAME, ASSET_DIR
from dark_messagebox import (
    DarkMessageBox, DarkInputDialog, show_information, show_warning, show_critical, show_question,
)
from titlebar import APP_ICON, apply_frameless, fit_to_screen

IMAGE_FILTER = "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp *.gif);;所有文件 (*.*)"
MUSIC_FILTER = (
    "音频文件 (*.mp3 *.wav *.m4a *.aac *.flac *.ogg);;所有文件 (*.*)"
)


def show_input_dialog(parent, title: str, prompt: str, default: str = "") -> tuple:
    """深色主题输入对话框，返回 (text, ok)。"""
    dlg = DarkInputDialog(parent, title, prompt, default)
    ret = dlg.exec()
    return (dlg.input_edit.text(), ret == QDialog.DialogCode.Accepted)


class EditorWindow(QMainWindow):
    """编辑音乐相册的主窗口。"""

    saved = Signal(str)  # 保存成功时发出 .pmb 文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑音乐相册")
        self.setMinimumSize(620, 560)
        fit_to_screen(self, 760, 660, 620, 560)
        self.image_paths = []  # 实际文件路径（外部文件或临时目录中的文件）
        self.music_paths = []
        self.current_bundle_path = None
        self.temp_dir = None  # 解压 .pmb 文件的临时目录
        self._build_ui()

    def _build_ui(self):
        _, _, inner = apply_frameless(self, "编辑音乐相册", icon=APP_ICON)
        root = QVBoxLayout()
        root.setContentsMargins(24, 12, 24, 18)
        root.setSpacing(10)
        inner.addLayout(root, 1)

        hint = QLabel("打开 .pmb 文件进行编辑，可以修改标题、添加/删除照片和音乐。")
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
        rename_img = QPushButton("重命名选中照片")
        rename_img.clicked.connect(lambda: self._rename_selected(self.image_list, self.image_paths, "image"))
        img_footer.addWidget(rename_img)
        remove_img = QPushButton("移除选中照片")
        remove_img.clicked.connect(lambda: self._remove_selected(self.image_list, self.image_paths, "image"))
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
        rename_music = QPushButton("重命名选中音乐")
        rename_music.clicked.connect(lambda: self._rename_selected(self.music_list, self.music_paths, "music"))
        music_footer.addWidget(rename_music)
        remove_music = QPushButton("移除选中音乐")
        remove_music.clicked.connect(lambda: self._remove_selected(self.music_list, self.music_paths, "music"))
        music_footer.addWidget(remove_music)
        root.addLayout(music_footer)

        root.addSpacing(4)

        save_btn = QPushButton("保存更改")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

        # 所有可点击按钮显示"链接选择"小手光标
        for _btn in self.findChildren(QPushButton):
            _btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def load_bundle(self, path: str):
        """加载现有的 .pmb 文件。"""
        if not is_bundle(path):
            show_warning(self, "无效文件", "这不是有效的 .pmb 音乐相册文件。")
            return False
        
        try:
            bundle = Bundle(path)
        except BundleError as e:
            show_warning(self, "无法打开", f"打开文件时出错：\n{e}")
            return False
        
        self.current_bundle_path = path
        self.temp_dir = bundle._tmpdir  # 保存临时目录引用
        
        self.title_edit.setText(bundle.title)
        
        # 加载图片
        self.image_list.clear()
        self.image_paths = []
        for img in bundle.images:
            # 图片在解压后的临时目录中
            rel_path = img["path"]  # 例如 "assets/000_xxx.jpg"
            abs_path = os.path.join(self.temp_dir, rel_path)
            self.image_paths.append(abs_path)
            item = QListWidgetItem(img["name"])
            item.setToolTip(abs_path)
            self.image_list.addItem(item)
        
        # 加载音乐
        self.music_list.clear()
        self.music_paths = []
        for music in bundle.musics:
            rel_path = music["path"]
            abs_path = os.path.join(self.temp_dir, rel_path)
            self.music_paths.append(abs_path)
            item = QListWidgetItem(music["name"])
            item.setToolTip(abs_path)
            self.music_list.addItem(item)
        
        # 不要关闭 bundle，因为我们需要临时目录中的文件
        # 但我们需要防止 bundle 在关闭时删除临时目录
        # 我们通过直接引用 temp_dir 来管理
        
        # 设置窗口标题
        self.setWindowTitle(f"编辑音乐相册 - {os.path.basename(path)}")
        return True

    # ---------- 文件选择 ----------
    def _add_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择照片", "", IMAGE_FILTER)
        for f in files:
            self.image_paths.append(f)
            item = QListWidgetItem(os.path.basename(f))
            item.setToolTip(f)
            self.image_list.addItem(item)

    def _add_musics(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择音乐", "", MUSIC_FILTER)
        for f in files:
            self.music_paths.append(f)
            item = QListWidgetItem(os.path.basename(f))
            item.setToolTip(f)
            self.music_list.addItem(item)

    def _remove_selected(self, list_widget: QListWidget, paths: list, file_type: str):
        """移除选中的列表项，并同步删除对应路径。"""
        rows = sorted(
            (list_widget.row(item) for item in list_widget.selectedItems()),
            reverse=True,
        )
        for row in rows:
            list_widget.takeItem(row)
            if row < len(paths):
                removed_path = paths.pop(row)
                # 如果文件在临时目录中，删除它
                if self.temp_dir and removed_path.startswith(self.temp_dir):
                    try:
                        os.remove(removed_path)
                    except OSError:
                        pass

    def _rename_selected(self, list_widget: QListWidget, paths: list, file_type: str):
        """重命名选中的列表项。"""
        items = list_widget.selectedItems()
        if not items:
            show_warning(self, "提示", "请先选择要重命名的项目。")
            return
        
        item = items[0]
        row = list_widget.row(item)
        old_name = item.text()
        
        new_name, ok = show_input_dialog(self, "重命名", "输入新名称：", old_name)
        if ok and new_name and new_name != old_name:
            item.setText(new_name)
            item.setToolTip(new_name)
            # 更新路径列表中的名称
            if row < len(paths):
                old_path = paths[row]
                # 如果文件在临时目录中，重命名文件
                if self.temp_dir and old_path.startswith(self.temp_dir):
                    dir_name = os.path.dirname(old_path)
                    new_path = os.path.join(dir_name, new_name)
                    try:
                        os.rename(old_path, new_path)
                        paths[row] = new_path
                    except OSError as e:
                        show_warning(self, "重命名失败", f"无法重命名文件：\n{e}")
                else:
                    # 外部文件，只更新显示名称（不移动物理文件）
                    pass

    # ---------- 保存 ----------
    def _save(self):
        if not self.image_paths:
            show_warning(self, "提示", "请至少添加一张照片。")
            return
        
        title = self.title_edit.text().strip() or "未命名相册"
        
        # 如果没有当前路径，询问保存位置
        if not self.current_bundle_path:
            default_name = f"{title}.pmb"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存音乐相册", default_name, "音乐相册 (*.pmb)"
            )
            if not path:
                return
            if not path.lower().endswith(".pmb"):
                path += ".pmb"
        else:
            # 覆盖原文件
            path = self.current_bundle_path
            ret = show_question(
                self,
                "确认保存",
                f"确定要覆盖原文件吗？\n{path}",
            )
            if not ret:
                return
        
        # 准备实际的文件路径列表
        actual_image_paths = []
        for img_path in self.image_paths:
            if os.path.exists(img_path):
                actual_image_paths.append(img_path)
            else:
                show_warning(self, "文件缺失", f"找不到文件：{img_path}")
                return
        
        actual_music_paths = []
        for music_path in self.music_paths:
            if os.path.exists(music_path):
                actual_music_paths.append(music_path)
            else:
                show_warning(self, "文件缺失", f"找不到文件：{music_path}")
                return
        
        # 如果正在编辑现有文件，先删除原文件
        if self.current_bundle_path and os.path.exists(self.current_bundle_path):
            try:
                os.remove(self.current_bundle_path)
            except OSError as e:
                show_critical(self, "删除失败", f"无法删除原文件：\n{e}")
                return
        
        try:
            create_bundle(title, actual_image_paths, actual_music_paths, path)
        except OSError as e:
            show_critical(self, "保存失败", f"保存时出错：\n{e}")
            return
        
        # 清理临时目录
        self._cleanup_temp_dir()
        
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
    
    def _cleanup_temp_dir(self):
        """清理临时目录。"""
        if self.temp_dir and os.path.isdir(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
            except Exception:
                pass
    
    def closeEvent(self, event):
        """窗口关闭时清理临时目录。"""
        self._cleanup_temp_dir()
        super().closeEvent(event)