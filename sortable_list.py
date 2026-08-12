# -*- coding: utf-8 -*-
"""支持拖拽排序的 QListWidget，每项自动显示序号。

列表项通过自定义 role 保存路径和原始名称，显示文本为
「序号. 名称」；拖拽排序、删除、重命名后序号自动刷新，
保证显示顺序与外部数据列表（image_paths / music_paths）一致。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

PATH_ROLE = Qt.ItemDataRole.UserRole
NAME_ROLE = Qt.ItemDataRole.UserRole + 1


class SortableListWidget(QListWidget):
    """按住列表项上下拖动即可调整顺序，并自动维护序号显示。"""

    def __init__(self, data_list: list, parent=None):
        super().__init__(parent)
        self._data = data_list
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
        item.setToolTip(name)
        self.addItem(item)
        self.refresh_numbers()
        return item

    def item_name(self, item: QListWidgetItem) -> str:
        """返回该项的原始名称（不含序号前缀）。"""
        name = item.data(NAME_ROLE)
        return name if name is not None else item.text()

    def update_item_name(self, item: QListWidgetItem, name: str):
        """更新某项的原始名称并刷新显示。"""
        item.setData(NAME_ROLE, name)
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
