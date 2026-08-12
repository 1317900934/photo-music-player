# -*- coding: utf-8 -*-
"""自定义深色主题消息框，替代系统默认 QMessageBox。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QPainter, QPen, QColor, QRadialGradient
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _CloseButton(QPushButton):
    """自绘关闭按钮：用 QPainter 画叉号。"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlat(True)
        self._hovered = False
        self.setMouseTracking(True)
    
    def enterEvent(self, event):
        self._hovered = True
        self.update()
    
    def leaveEvent(self, event):
        self._hovered = False
        self.update()
    
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self._hovered:
            p.setBrush(QColor("#e5484d"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect(), 6, 6)
            pen = QPen(QColor("#ffffff"))
        else:
            pen = QPen(QColor("#9aa0b0"))
        
        pen.setWidthF(1.6)
        p.setPen(pen)
        m = 11
        w, h = self.width(), self.height()
        p.drawLine(m, m, w - m, h - m)
        p.drawLine(w - m, m, m, h - m)
        p.end()


class _ShadowWidget(QWidget):
    """带白色外发光效果的容器。"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # 1px 白色微光
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 25))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 11, 11)
        
        # 深色背景
        p.setBrush(QColor("#1d2027"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 10, 10)
        
        p.end()


class DarkMessageBox(QDialog):
    """深色主题消息框，支持圆角、自定义标题栏、无焦点虚线。"""
    
    def __init__(self, parent=None, title="", message="", icon="info", buttons=None):
        super().__init__(parent)
        
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(440, 210)
        
        # 阴影容器
        shadow = _ShadowWidget(self)
        shadow.setGeometry(0, 0, self.width(), self.height())
        
        # 内容容器
        container = QWidget(shadow)
        container.setObjectName("msgBoxContainer")
        container.setGeometry(4, 4, self.width() - 8, self.height() - 8)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏
        title_bar = QWidget()
        title_bar.setObjectName("msgTitleBar")
        title_bar.setFixedHeight(36)
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 8, 0)
        
        title_label = QLabel(title)
        title_label.setObjectName("msgTitleLabel")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        close_btn = _CloseButton()
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        
        layout.addWidget(title_bar)
        
        # 内容区域
        content_widget = QWidget()
        content_widget.setObjectName("msgContent")
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 16, 24, 16)
        content_layout.setSpacing(16)
        
        icon_map = {
            "info": "i",
            "warning": "!",
            "critical": "x",
            "question": "?",
        }
        icon_label = QLabel(icon_map.get(icon, "i"))
        icon_label.setObjectName("msgIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(40, 40)
        content_layout.addWidget(icon_label)
        
        msg_label = QLabel(message)
        msg_label.setObjectName("msgText")
        msg_label.setWordWrap(True)
        content_layout.addWidget(msg_label, 1)
        
        layout.addWidget(content_widget, 1)
        
        # 按钮栏
        btn_bar = QWidget()
        btn_bar.setObjectName("msgBtnBar")
        btn_bar.setFixedHeight(56)
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(24, 10, 24, 10)
        btn_layout.addStretch()
        
        self.result = None
        
        if buttons is None:
            buttons = [("OK", "accept")]
        
        for text, role in buttons:
            btn = QPushButton(text)
            btn.setObjectName("msgBtn")
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFlat(True)
            btn.setMinimumWidth(80)
            btn.clicked.connect(lambda checked, r=role: self._on_button(r))
            btn_layout.addWidget(btn)
        
        layout.addWidget(btn_bar)
        
        self.setStyleSheet("""
            #msgBoxContainer {
                background-color: #1d2027;
                border-radius: 10px;
            }
            #msgTitleBar {
                background: transparent;
            }
            #msgTitleLabel {
                color: #e6e8ee;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
            #msgContent {
                background: transparent;
            }
            #msgIcon {
                font-size: 28px;
                font-weight: bold;
                color: #5b7cfa;
                background: transparent;
                border: none;
            }
            #msgText {
                color: #e6e8ee;
                font-size: 13px;
                background: transparent;
                border: none;
            }
            #msgBtnBar {
                background: transparent;
            }
            #msgBtn {
                background-color: #2a2e37;
                border: 1px solid #343946;
                border-radius: 8px;
                padding: 8px 24px;
                color: #e6e8ee;
                font-size: 13px;
                min-width: 80px;
            }
            #msgBtn:hover {
                background-color: #343946;
            }
            #msgBtn:pressed {
                background-color: #22252d;
            }
            #msgBtn:focus {
                background-color: #5b7cfa;
                border-color: #5b7cfa;
                outline: none;
            }
        """)
    
    def _on_button(self, role):
        if role == "accept":
            self.result = True
            self.accept()
        else:
            self.result = False
            self.reject()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 40:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            self._dragging = True
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if getattr(self, '_dragging', False):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)


class DarkInputDialog(QDialog):
    """深色主题输入对话框，与 DarkMessageBox 风格一致。"""

    def __init__(self, parent=None, title="", prompt="", default=""):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(440, 240)

        shadow = _ShadowWidget(self)
        shadow.setGeometry(0, 0, self.width(), self.height())

        container = QWidget(shadow)
        container.setObjectName("inputContainer")
        container.setGeometry(4, 4, self.width() - 8, self.height() - 8)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setObjectName("inputTitleBar")
        title_bar.setFixedHeight(36)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 8, 0)
        title_label = QLabel(title)
        title_label.setObjectName("inputTitleLabel")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        close_btn = _CloseButton()
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        layout.addWidget(title_bar)

        # 内容区域
        content = QWidget()
        content.setObjectName("inputContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 16, 24, 16)
        cl.setSpacing(8)

        prompt_label = QLabel(prompt)
        prompt_label.setObjectName("inputPrompt")
        cl.addWidget(prompt_label)

        self.input_edit = QLineEdit(default)
        self.input_edit.selectAll()
        self.input_edit.setMinimumHeight(36)
        cl.addWidget(self.input_edit)

        layout.addWidget(content, 1)

        # 按钮栏
        btn_bar = QWidget()
        btn_bar.setObjectName("inputBtnBar")
        btn_bar.setFixedHeight(56)
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(24, 10, 24, 10)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("inputBtn")
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setFlat(True)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("保存")
        ok_btn.setObjectName("inputBtn")
        ok_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ok_btn.setFlat(True)
        ok_btn.setMinimumWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        ok_btn.setDefault(True)

        layout.addWidget(btn_bar)

        self.setStyleSheet("""
            #inputContainer {
                background-color: #1d2027;
                border-radius: 10px;
            }
            #inputTitleBar { background: transparent; }
            #inputTitleLabel {
                color: #e6e8ee; font-size: 13px; font-weight: 600;
                background: transparent;
            }
            #inputContent { background: transparent; }
            #inputPrompt {
                color: #9aa0b0; font-size: 13px;
                background: transparent; border: none;
            }
            #inputBtnBar { background: transparent; }
            #inputBtn {
                background-color: #2a2e37;
                border: 1px solid #343946;
                border-radius: 8px;
                padding: 8px 24px;
                color: #e6e8ee;
                font-size: 13px;
                min-width: 80px;
            }
            #inputBtn:hover { background-color: #343946; }
            #inputBtn:pressed { background-color: #22252d; }
            #inputBtn:focus {
                background-color: #5b7cfa; border-color: #5b7cfa;
                outline: none;
            }
            QLineEdit {
                background-color: #2a2e37;
                border: 1px solid #343946;
                border-radius: 6px;
                padding: 6px 10px;
                color: #e6e8ee;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #5b7cfa;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 40:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            self._dragging = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, '_dragging', False):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)


def show_information(parent, title, message):
    dlg = DarkMessageBox(parent, title, message, "info", [("OK", "accept")])
    dlg.exec()
    return dlg.result


def show_warning(parent, title, message):
    dlg = DarkMessageBox(parent, title, message, "warning", [("OK", "accept")])
    dlg.exec()
    return dlg.result


def show_critical(parent, title, message):
    dlg = DarkMessageBox(parent, title, message, "critical", [("OK", "accept")])
    dlg.exec()
    return dlg.result


def show_question(parent, title, message):
    dlg = DarkMessageBox(parent, title, message, "question", [("Yes", "accept"), ("No", "reject")])
    dlg.exec()
    return dlg.result
