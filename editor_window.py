# -*- coding: utf-8 -*-
"""编辑打包窗口：打开 .pmb 文件，修改照片、音乐和标题后保存。"""
import os
import shutil
import tempfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)
from PySide6.QtWidgets import QDialog

from bundle import (
    Bundle,
    BundleError,
    create_bundle,
    is_bundle,
    numbered_stored_name,
    strip_stored_sequence_prefix,
)
from dark_messagebox import (
    DarkMessageBox, DarkInputDialog, show_warning, show_critical, show_question,
)
from sortable_list import PATH_ROLE, SortableListWidget
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
        self.setMinimumSize(800, 680)
        fit_to_screen(self, 960, 800, 800, 680)
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
        # 固定为单行提示，不让它吸收布局的剩余高度
        hint.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
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

        self.image_list = SortableListWidget(self.image_paths)
        self.image_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.image_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.image_list.setStyleSheet("""
            QListWidget {
                min-width: 400px;
                min-height: 100px;
                max-height: 150px;
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
        # 图片列表悬停时右侧显示预览小窗（音乐列表不需要）
        self.image_list.enable_hover_image_preview()
        root.addWidget(self.image_list, 3)

        img_footer = QHBoxLayout()
        img_footer.addStretch()
        rename_img = QPushButton("重命名选中照片")
        rename_img.clicked.connect(lambda: self._rename_selected(self.image_list, self.image_paths))
        img_footer.addWidget(rename_img)
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

        self.music_list = SortableListWidget(self.music_paths)
        self.music_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.music_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.music_list.setStyleSheet("""
            QListWidget {
                min-width: 400px;
                min-height: 100px;
                max-height: 150px;
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
        rename_music.clicked.connect(lambda: self._rename_selected(self.music_list, self.music_paths))
        music_footer.addWidget(rename_music)
        remove_music = QPushButton("移除选中音乐")
        remove_music.clicked.connect(lambda: self._remove_selected(self.music_list, self.music_paths))
        music_footer.addWidget(remove_music)
        root.addLayout(music_footer)

        root.addSpacing(4)

        save_btn = QPushButton("保存更改")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.close)
        root.addWidget(cancel_btn)

        # 所有可点击按钮显示"链接选择"小手光标
        for _btn in self.findChildren(QPushButton):
            _btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def load_bundle(self, path: str):
        """加载现有的 .pmb 文件。"""
        if not is_bundle(path):
            show_warning(self, "无效文件", "这不是有效的 .pmb 音乐相册文件。")
            return False

        # 清理上一次打开遗留的临时目录，避免重复加载同一窗口时泄漏
        self._cleanup_temp_dir()
        
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
        self.image_paths.clear()
        for img in bundle.images:
            # 图片在解压后的临时目录中
            rel_path = img["path"]  # 例如 "assets/000_xxx.jpg"
            abs_path = os.path.join(self.temp_dir, rel_path)
            self.image_paths.append(abs_path)
            self.image_list.add_item(abs_path, img["name"])
        
        # 加载音乐
        self.music_list.clear()
        self.music_paths.clear()
        for music in bundle.musics:
            rel_path = music["path"]
            abs_path = os.path.join(self.temp_dir, rel_path)
            self.music_paths.append(abs_path)
            self.music_list.add_item(abs_path, music["name"])

        # 编辑前先去掉临时文件里的序号前缀（0001_ 等），
        # 用户看到和操作的始终是原始文件名
        self._strip_prefixes_in_temp()
        
        # 不要关闭 bundle，因为我们需要临时目录中的文件
        # 但我们需要防止 bundle 在关闭时删除临时目录
        # 我们通过直接引用 temp_dir 来管理
        
        # 设置窗口标题
        self.setWindowTitle(f"编辑音乐相册 - {os.path.basename(path)}")
        return True

    def _strip_prefixes_in_temp(self):
        """编辑前把临时目录中的文件去掉序号前缀（0001_ 等）。

        只有文件名确实是「序号_原始名」形式时才去掉；旧版没有前缀的
        pmb 文件原样保留。原始名相同的文件在磁盘上用 " (2)" 后缀区分，
        列表里仍允许显示相同名称。
        """
        if not self.temp_dir or not os.path.isdir(self.temp_dir):
            return
        used = {
            os.path.basename(p)
            for paths in (self.image_paths, self.music_paths)
            for p in paths
        }
        for paths, list_widget in (
            (self.image_paths, self.image_list),
            (self.music_paths, self.music_list),
        ):
            for i, p in enumerate(paths):
                if not p.startswith(self.temp_dir):
                    continue
                item = list_widget.item(i)
                original = (
                    list_widget.item_name(item)
                    if item is not None
                    else os.path.basename(p)
                )
                base = os.path.basename(p)
                clean = strip_stored_sequence_prefix(base, original)
                if clean == base:
                    continue
                disk = clean
                n = 2
                while disk in used:
                    stem, ext = os.path.splitext(clean)
                    disk = f"{stem} ({n}){ext}"
                    n += 1
                new_path = os.path.join(os.path.dirname(p), disk)
                try:
                    os.rename(p, new_path)
                except OSError:
                    continue
                paths[i] = new_path
                used.add(disk)
                if item is not None:
                    item.setData(PATH_ROLE, new_path)
                    # 显示名同步为去重后的磁盘名（如 "a (2).png"），
                    # 让重名后缀在界面里可见
                    list_widget.update_item_name(item, disk)

    def _renumber_temp_files(self):
        """按当前列表顺序给临时目录中的文件重新加上序号前缀（0001_ 起）。

        取消或直接关闭窗口时调用（保存路径由 create_bundle 负责按
        列表顺序编号），保证临时目录中的文件始终按列表顺序编号。
        """
        if not self.temp_dir or not os.path.isdir(self.temp_dir):
            return
        used = {
            os.path.basename(p)
            for paths in (self.image_paths, self.music_paths)
            for p in paths
        }
        for paths, list_widget in (
            (self.image_paths, self.image_list),
            (self.music_paths, self.music_list),
        ):
            for i, p in enumerate(paths, 1):
                if not p.startswith(self.temp_dir):
                    continue
                item = list_widget.item(i - 1)
                display = (
                    list_widget.item_name(item)
                    if item is not None
                    else os.path.basename(p)
                )
                new_name = numbered_stored_name(i, display)
                if new_name in used:
                    stem, ext = os.path.splitext(new_name)
                    n = 2
                    while f"{stem} ({n}){ext}" in used:
                        n += 1
                    new_name = f"{stem} ({n}){ext}"
                new_path = os.path.join(os.path.dirname(p), new_name)
                if new_path == p:
                    used.add(new_name)
                    continue
                try:
                    os.rename(p, new_path)
                except OSError:
                    continue
                paths[i - 1] = new_path
                used.add(new_name)
                if item is not None:
                    item.setData(PATH_ROLE, new_path)

    # ---------- 文件选择 ----------
    def _add_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择照片", "", IMAGE_FILTER)
        for f in files:
            self.image_paths.append(f)
            # 同名文件自动追加 " (n)" 后缀，列表内不出现重名
            self.image_list.add_item(f, self.image_list.unique_name(os.path.basename(f)))

    def _add_musics(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择音乐", "", MUSIC_FILTER)
        for f in files:
            self.music_paths.append(f)
            self.music_list.add_item(f, self.music_list.unique_name(os.path.basename(f)))

    def _remove_selected(self, list_widget: QListWidget, paths: list):
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
        list_widget.refresh_numbers()

    def _rename_selected(self, list_widget: QListWidget, paths: list):
        """重命名选中的列表项。"""
        items = list_widget.selectedItems()
        if not items:
            show_warning(self, "提示", "请先选择要重命名的项目。")
            return
        if len(items) > 1:
            # 多选时不弹重命名窗口，提示选择单个项目
            dlg = DarkMessageBox(self, "提示", "请选择单个项目重命名。", "info", [("知道了", "accept")])
            dlg.exec()
            return
        
        item = items[0]
        row = list_widget.row(item)
        old_name = list_widget.item_name(item)
        
        new_name, ok = show_input_dialog(self, "重命名", "输入新名称：", old_name)
        if ok and new_name and new_name != old_name:
            # 列表内不允许重名：目标名已被其他项使用则直接失败
            if list_widget.has_name(new_name, skip_item=item):
                show_warning(self, "重命名失败", "已有重名文件，请换一个名称。")
                return
            if row < len(paths):
                old_path = paths[row]
                # 如果文件在临时目录中，重命名文件
                if self.temp_dir and old_path.startswith(self.temp_dir):
                    dir_name = os.path.dirname(old_path)
                    new_path = os.path.join(dir_name, new_name)
                    if new_path != old_path:
                        try:
                            os.rename(old_path, new_path)
                            paths[row] = new_path
                            item.setData(PATH_ROLE, new_path)
                        except OSError as e:
                            show_warning(self, "重命名失败", f"无法重命名文件：\n{e}")
                            return
                # 外部文件，只更新显示名称（不移动物理文件）
            list_widget.update_item_name(item, new_name)

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
        
        # 先写入同目录临时文件，成功后再原子替换目标文件，
        # 避免保存失败（磁盘满、文件被占用等）时丢失原文件。
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                prefix="pmb_save_", suffix=".pmb",
                dir=os.path.dirname(path) or os.curdir,
            )
            os.close(fd)
            image_names = [
                self.image_list.item_name(self.image_list.item(i))
                for i in range(self.image_list.count())
            ]
            music_names = [
                self.music_list.item_name(self.music_list.item(i))
                for i in range(self.music_list.count())
            ]
            create_bundle(
                title,
                actual_image_paths,
                actual_music_paths,
                tmp_path,
                image_names=image_names,
                music_names=music_names,
            )
            os.replace(tmp_path, path)
            tmp_path = None  # 已成功替换，无需清理
        except OSError as e:
            show_critical(self, "保存失败", f"保存时出错：\n{e}")
            return
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        
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
        """窗口关闭（保存后关闭 / 取消 / 点叉号）前先按列表顺序重新编号。"""
        self._renumber_temp_files()
        self._cleanup_temp_dir()
        super().closeEvent(event)
