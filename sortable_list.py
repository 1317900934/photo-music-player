# -*- coding: utf-8 -*-
"""支持拖拽排序的 QListWidget，每项自动显示序号。

列表项通过自定义 role 保存路径和原始名称，显示文本为
「序号. 名称」；拖拽排序、删除、重命名后序号自动刷新，
保证显示顺序与外部数据列表（image_paths / music_paths）一致。
"""
import os

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

PATH_ROLE = Qt.ItemDataRole.UserRole
NAME_ROLE = Qt.ItemDataRole.UserRole + 1


class HoverImagePreview(QFrame):
    """悬停预览小窗：深色圆角容器包裹图片缩略图，不抢焦点。"""

    PREVIEW_W = 168
    PREVIEW_H = 118
    PAD_X = 8
    PAD_Y = 1
    RADIUS = 8
    GAP = 10

    def __init__(self, parent=None, gap=GAP):
        super().__init__(parent)
        self._gap = gap
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(
            self.PAD_X, self.PAD_Y, self.PAD_X, self.PAD_Y
        )
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: transparent;")
        lay.addWidget(self._image_label)
        self.hide()

    def paintEvent(self, event):
        """自绘深色圆角背景，避免 QSS 圆角在透明窗口上产生黑色边角。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor("#3c4252"), 1))
        p.setBrush(QBrush(QColor("#1d2027")))
        p.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
        p.end()

    def show_image(self, image_path: str, anchor_global):
        """显示 image_path 的缩略图，位置放在 anchor_global 的右侧。"""
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.hide()
            return
        pixmap = pixmap.scaled(
            self.PREVIEW_W,
            self.PREVIEW_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(pixmap)
        self.setFixedSize(
            self.PREVIEW_W + 2 * self.PAD_X,
            self.PREVIEW_H + 2 * self.PAD_Y,
        )
        screen = QApplication.screenAt(anchor_global) or QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = anchor_global.x() + self._gap
        if x + self.width() > geo.right():
            x = anchor_global.x() - self.width() - self._gap
        y = anchor_global.y() - self.height() // 2
        y = max(geo.top() + 4, min(y, geo.bottom() - self.height() - 4))
        self.move(x, y)
        self.show()
        self.raise_()

    def hide_preview(self):
        self.hide()


class SortableListWidget(QListWidget):
    """按住列表项上下拖动即可调整顺序，并自动维护序号显示。"""

    def __init__(self, data_list: list, parent=None):
        super().__init__(parent)
        self._data = data_list
        self._tooltips_enabled = True
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        # 与播放界面（QScrollArea）一致的像素级平滑滚动，避免按项跳动的生硬感
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def add_item(self, path: str, name: str) -> QListWidgetItem:
        """添加一项：绑定路径与原始名称，显示为「序号. 名称」。"""
        item = QListWidgetItem()
        item.setData(PATH_ROLE, path)
        item.setData(NAME_ROLE, name)
        if self._tooltips_enabled:
            item.setToolTip(name)
        self.addItem(item)
        self.refresh_numbers()
        return item

    def item_name(self, item: QListWidgetItem) -> str:
        """返回该项的原始名称（不含序号前缀）。"""
        name = item.data(NAME_ROLE)
        return name if name is not None else item.text()

    def unique_name(self, name: str) -> str:
        """返回列表内不重复的显示名：与已有项同名时自动追加 " (n)" 后缀。"""
        existing = {
            self.item_name(self.item(i)).lower()
            for i in range(self.count())
        }
        if name.lower() not in existing:
            return name
        stem, ext = os.path.splitext(name)
        n = 2
        while f"{stem} ({n}){ext}".lower() in existing:
            n += 1
        return f"{stem} ({n}){ext}"

    def has_name(self, name: str, skip_item=None) -> bool:
        """列表中是否已有同名项（大小写不敏感）；skip_item 用于排除某项自身。"""
        target = name.lower()
        for i in range(self.count()):
            item = self.item(i)
            if item is skip_item:
                continue
            if self.item_name(item).lower() == target:
                return True
        return False

    def update_item_name(self, item: QListWidgetItem, name: str):
        """更新某项的原始名称并刷新显示。"""
        item.setData(NAME_ROLE, name)
        if self._tooltips_enabled:
            item.setToolTip(name)
        self.refresh_numbers()

    def refresh_numbers(self):
        """按当前顺序为每一项刷新「序号. 名称」显示。"""
        for i in range(self.count()):
            item = self.item(i)
            item.setText(f"{i + 1}. {self.item_name(item)}")

    def dropEvent(self, event):
        super().dropEvent(event)
        if event.isAccepted():
            self._sync_data()
            self.refresh_numbers()

    def _sync_data(self):
        """按当前列表顺序重建外部数据列表。"""
        ordered = []
        for i in range(self.count()):
            path = self.item(i).data(PATH_ROLE)
            if path is not None:
                ordered.append(path)
        if ordered:
            self._data[:] = ordered

    # ---------- 图片悬停预览 ----------
    def enable_hover_image_preview(self):
        """为图片列表启用悬停预览：鼠标悬停某项时，右侧出现预览小窗。

        预览图已承担名称提示作用，因此同时关闭列表项的悬停名称提示；
        预览窗相对列表右缘的间距为 30px。
        """
        self._tooltips_enabled = False
        for i in range(self.count()):
            self.item(i).setToolTip("")
        self._hover_preview = HoverImagePreview(gap=30)
        self.itemEntered.connect(self._show_hover_preview)
        self.viewport().installEventFilter(self)

    def _show_hover_preview(self, item: QListWidgetItem):
        path = item.data(PATH_ROLE)
        if not path:
            return
        # 锚点取列表右侧边缘，预览窗固定出现在列表右边
        anchor = self.viewport().mapToGlobal(
            self.viewport().rect().topRight()
        )
        anchor.setY(
            self.viewport().mapToGlobal(self.visualItemRect(item).center()).y()
        )
        self._hover_preview.show_image(path, anchor)

    def eventFilter(self, obj, event):
        if (
            obj is self.viewport()
            and event.type() == QEvent.Type.Leave
            and hasattr(self, "_hover_preview")
        ):
            self._hover_preview.hide_preview()
        return super().eventFilter(obj, event)
