# -*- coding: utf-8 -*-
"""播放窗口：类似视频播放器的界面。

上方是图片鉴赏区（大图 + 左右箭头切换），下方是音乐播放区
（歌曲名、进度条、播放/暂停、上一首/下一首、音量条、音乐列表按钮）。

播放模式：
    顺序播放 —— 按列表依次播放，最后一首播完后回到第一首继续；
    单曲循环 —— 当前歌曲循环播放；
    随机播放 —— 在未播放过的歌曲中随机，全部播完后开始新一轮随机。
"""
import os
import random

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QUrl,
    QPropertyAnimation,
    QVariantAnimation,
    Signal,
    QTimer,
)
from PySide6.QtGui import QCursor, QMouseEvent, QPixmap, QPainter, QColor, QIcon, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QScrollBar,
    QApplication,
    QStyle,
)

from bundle import Bundle, BundleError
from titlebar import (
    APP_ICON,
    _screen_geometry,
    apply_frameless,
    center_on_screen,
    fit_to_screen,
)


def _fmt_ms(ms: int) -> str:
    """把毫秒格式化为 mm:ss。"""
    if ms < 0:
        ms = 0
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


PLAY_MODES = ["顺序播放", "单曲循环", "随机播放"]
MODE_ICONS = {"顺序播放": "🔁", "单曲循环": "🔂", "随机播放": "🔀"}
MODE_TIPS = {
    "顺序播放": "顺序播放：按列表依次播放，最后一首播完后回到第一首继续",
    "单曲循环": "单曲循环：当前歌曲循环播放",
    "随机播放": "随机播放：在未播放过的歌曲中随机，全部播完后开始新一轮",
}


class ClickableSlider(QSlider):
    """支持点击任意位置跳转的滑块控件。"""
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            value = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
            self.setValue(int(value))
            self.sliderMoved.emit(int(value))
        super().mousePressEvent(event)


class GalleryImageLabel(QLabel):
    """主界面图片显示控件：使用 QPainter 直接绘制，确保图片清晰。
    
    与 _ViewerImageLabel 类似，但更简单，只负责显示图片，不支持缩放/拖动。
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pixmap = None
    
    def setPixmap(self, pixmap):
        """设置要显示的图片。"""
        self._pixmap = pixmap
        self.update()
    
    def paintEvent(self, event):
        """直接绘制图片，避免 QLabel 内部缩放导致的画质损失。"""
        if self._pixmap is None or self._pixmap.isNull():
            return
        
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 计算居中显示的位置
        widget_rect = self.rect()
        pixmap_rect = self._pixmap.rect()
        
        # 计算缩放比例，保持纵横比
        scale_x = widget_rect.width() / pixmap_rect.width()
        scale_y = widget_rect.height() / pixmap_rect.height()
        scale = min(scale_x, scale_y)
        
        # 计算缩放后的尺寸
        scaled_width = int(pixmap_rect.width() * scale)
        scaled_height = int(pixmap_rect.height() * scale)
        
        # 计算居中位置
        x = (widget_rect.width() - scaled_width) // 2
        y = (widget_rect.height() - scaled_height) // 2
        
        # 绘制图片
        target_rect = QRectF(x, y, scaled_width, scaled_height)
        source_rect = QRectF(pixmap_rect)
        
        p.drawPixmap(target_rect, self._pixmap, source_rect)
        p.end()


class _ViewerImageLabel(QLabel):
    """图片查看器的图片内容区：自绘缩放图片。

    - 滚轮以鼠标位置为锚点缩放（最小回到适配窗口大小，不可再小）
    - 放大后按住左键拖动查看
    - 鼠标移动转发给宿主做边缘检测（显示/隐藏控制条）
    """
    MAX_SCALE = 10.0

    def __init__(self, host):
        super().__init__()
        self._host = host
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self._src = None          # 原始图
        self._scale = 1.0         # 相对适配窗口的缩放
        self._pan_x = 0.0         # 中心偏移
        self._pan_y = 0.0
        self._dragging = False
        self._last_global = None
        self._cursor_hidden = False
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ---------- 几何 ----------
    def set_source(self, pixmap):
        """设置图片并重置缩放/平移。"""
        self._src = pixmap
        self._scale = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.update()

    def set_cursor_hidden(self, hidden):
        """隐藏或显示光标：隐藏时使用 BlankCursor，不污染全局光标栈。"""
        self._cursor_hidden = hidden
        self._update_cursor()

    def _fit_size(self):
        """适配当前视口尺寸的等比宽高。"""
        if self._src is None:
            return 0, 0
        w, h = self.width(), self.height()
        sw, sh = self._src.width(), self._src.height()
        if w <= 0 or h <= 0 or sw <= 0 or sh <= 0:
            return 0, 0
        k = min(w / sw, h / sh)
        return sw * k, sh * k

    def _display_rect(self):
        """图片当前显示矩形（fit 居中 + 平移偏移）。"""
        fw, fh = self._fit_size()
        if fw <= 0:
            return QRectF()
        sw, sh = fw * self._scale, fh * self._scale
        x = (self.width() - sw) / 2.0 + self._pan_x
        y = (self.height() - sh) / 2.0 + self._pan_y
        return QRectF(x, y, sw, sh)

    def _clamp_pan(self):
        """限制平移范围：图片不小于视口时不让边缘露空，小于视口时居中。"""
        fw, fh = self._fit_size()
        sw, sh = fw * self._scale, fh * self._scale
        W, H = self.width(), self.height()
        mx = max(0.0, (sw - W) / 2.0)
        my = max(0.0, (sh - H) / 2.0)
        self._pan_x = max(-mx, min(mx, self._pan_x))
        self._pan_y = max(-my, min(my, self._pan_y))

    def _update_cursor(self):
        if self._cursor_hidden:
            self.setCursor(Qt.CursorShape.BlankCursor)
        elif self._scale > 1.0:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # ---------- 事件 ----------
    def paintEvent(self, event):
        if self._src is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(self._display_rect(), self._src, QRectF(self._src.rect()))
        p.end()

    def wheelEvent(self, event):
        if self._src is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 ** (delta / 120.0)
        old = self._scale
        new = max(1.0, min(old * factor, self.MAX_SCALE))
        if abs(new - old) < 1e-9:
            event.accept()
            return
        # 以鼠标位置为锚点缩放：保持鼠标指向的图片点不动
        mx, my = event.position().x(), event.position().y()
        rect = self._display_rect()
        if rect.width() > 0 and rect.height() > 0:
            px = (mx - rect.x()) / rect.width()
            py = (my - rect.y()) / rect.height()
        else:
            px = py = 0.5
        self._scale = new
        fw, fh = self._fit_size()
        sw, sh = fw * new, fh * new
        nx = mx - px * sw
        ny = my - py * sh
        self._pan_x = nx - (self.width() - sw) / 2.0
        self._pan_y = ny - (self.height() - sh) / 2.0
        self._clamp_pan()
        self._update_cursor()
        self.update()
        self._host._on_zoom_changed(new)
        event.accept()

    def mousePressEvent(self, event):
        self._host._on_pointer_click()
        if event.button() == Qt.MouseButton.LeftButton and self._scale > 1.0:
            self._dragging = True
            self._last_global = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._host._on_image_mouse_move(event)
        if self._dragging and self._last_global is not None:
            gp = event.globalPosition().toPoint()
            dx = gp.x() - self._last_global.x()
            dy = gp.y() - self._last_global.y()
            self._last_global = gp
            self._pan_x += dx
            self._pan_y += dy
            self._clamp_pan()
            self.update()
        else:
            # 非拖动时同步光标：缩回默认比例后恢复箭头
            self._update_cursor()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._last_global = None
            self._update_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # 双击：属于鼠标活动，先重置光标空闲计时
        self._host._on_pointer_click()
        # 双击恢复默认大小
        if event.button() == Qt.MouseButton.LeftButton and self._scale > 1.0:
            self.set_source(self._src)
            self._update_cursor()
            self._host._on_zoom_changed(1.0)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _ClickableLabel(QLabel):
    """可点击的标签：只有点击文字本身才发出 clicked 信号（仿超链接），
    文字两侧的空白区域不触发。光标也只在文字上方显示手指样式，
    空白处显示箭头。弹窗展开期间光标行为不变。"""
    clicked = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._on_text = False
        self._popup_visible = False
        self._update_cursor()

    def _hit_text(self, local_x) -> bool:
        """判断 x 坐标是否落在文字渲染区域内。"""
        text = self.text()
        if not text:
            return False
        cr = self.contentsRect()
        fm = self.fontMetrics()
        text_rect = fm.boundingRect(text)
        align = self.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
        if align == Qt.AlignmentFlag.AlignRight:
            x = cr.right() - text_rect.width()
        elif align == Qt.AlignmentFlag.AlignHCenter:
            x = cr.left() + (cr.width() - text_rect.width()) // 2
        else:
            x = cr.left()
        return x <= local_x <= x + text_rect.width()

    def _update_cursor(self):
        cursor = Qt.CursorShape.PointingHandCursor if self._on_text else Qt.CursorShape.ArrowCursor
        if self.cursor().shape() != cursor:
            self.setCursor(cursor)

    def mouseMoveEvent(self, event):
        on_text = self._hit_text(event.position().x())
        if on_text != self._on_text:
            self._on_text = on_text
            self._update_cursor()
        super().mouseMoveEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)
        pos = self.mapFromGlobal(QCursor.pos())
        self._on_text = self._hit_text(pos.x())
        self._update_cursor()
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def leaveEvent(self, event):
        self._on_text = False
        self._update_cursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._hit_text(event.position().x()):
                self.clicked.emit()
        super().mousePressEvent(event)


class _MarqueeButton(QPushButton):
    """按钮：文本超出可用宽度时，悬停自动滚动走马灯效果。"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._original_text = text
        self._scroll_buf = ""
        self._scroll_pos = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(200)
        self._scroll_timer.timeout.connect(self._on_tick)

    def enterEvent(self, event):
        super().enterEvent(event)
        fm = self.fontMetrics()
        available = self.width() - 14
        if fm.horizontalAdvance(self._original_text) > available:
            self._scroll_buf = self._original_text + "        "
            self._scroll_pos = 0
            self._scroll_timer.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._scroll_timer.stop()
        self.setText(self._original_text)

    def _on_tick(self):
        if not self._scroll_buf:
            return
        self._scroll_pos = (self._scroll_pos + 1) % len(self._scroll_buf)
        t = self._scroll_buf[self._scroll_pos:] + self._scroll_buf[:self._scroll_pos]
        self.setText(t)


class _ImageListPopup(QFrame):
    """可滚动列表弹窗：走马灯效果、高度上限5项、悬停链接光标。
    图片列表和音乐列表共用此弹窗。"""

    def __init__(self, items, current_index, on_select, parent=None):
        # Popup 类型：临时弹出窗口，不占用任务栏、点击外部自动关闭
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("imageListPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 不抢夺焦点
        self._ready = False  # 防止 popup_at 内 setFocus 触发 focusOut 立即隐藏
        self.setStyleSheet("""
            QFrame#imageListPopup {
                background: transparent;
            }
            QFrame#imageListPopup QScrollArea {
                border: none; background: transparent;
            }
            QFrame#imageListPopup QScrollBar:vertical {
                width: 6px; background: transparent; margin: 0;
            }
            QFrame#imageListPopup QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.25); border-radius: 3px; min-height: 20px;
            }
            QFrame#imageListPopup QScrollBar::add-line:vertical,
            QFrame#imageListPopup QScrollBar::sub-line:vertical { height: 0; }
            QFrame#imageListPopup QScrollBar::add-page:vertical,
            QFrame#imageListPopup QScrollBar::sub-page:vertical { background: none; }
            QFrame#imageListPopup QPushButton {
                background: transparent; border: none; text-align: left;
                padding: 8px 14px; border-radius: 4px; color: #e6e8ee; font-size: 13px;
            }
            QFrame#imageListPopup QPushButton:hover { background-color: rgba(91,124,250,0.2); }
            QFrame#imageListPopup QPushButton:checked { color: #8fb0ff; font-weight: 600; background-color: rgba(91,124,250,0.3); }
            QFrame#imageListPopup QPushButton:checked:hover { background-color: rgba(91,124,250,0.4); }
        """)
        self._on_select = on_select
        self._items = []

        fm = self.fontMetrics()
        max_text_w = max(
            (fm.horizontalAdvance(f"{i + 1}. {item.get('name', '')}")
             for i, item in enumerate(items)),
            default=0,
        )
        n = len(items)
        self._max_visible = min(n, 5)
        # 先前上限 400/下限 350，按用户要求缩减到约 70%：上限 280 / 下限 245
        # 当选项>5个时，右侧自定义滚动条占用 6px+2px间距
        scrollbar_extra = 8 if n > 5 else 0
        self._popup_width = max(245, min(max_text_w + 28 + scrollbar_extra, 280))
        self._item_h = 34
        self._item_gap = 2
        self._show_scrollbar = n > 5

        # 容器：按钮列表
        container = QWidget()
        container.setObjectName("imageListContainer")
        container.setStyleSheet("QWidget#imageListContainer { background: transparent; }")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        for i, item in enumerate(items):
            name = item.get("name", f"项目 {i + 1}")
            btn = _MarqueeButton(f"{i + 1}. {name}")
            btn.setFixedHeight(34)
            btn.setCheckable(True)
            btn.setChecked(i == current_index)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=i: self._pick(idx))
            lay.addWidget(btn)
            self._items.append(btn)

        # 滚动区域：隐藏原生滚动条，内容溢出时用滚轮滚动
        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll_area = scroll

        # 自定义滚动条：作为 self（QFrame）的直接子控件，保证在圆角内部
        self._sb = QScrollBar(Qt.Vertical, self)
        self._sb.setFixedWidth(6)
        self._sb.setStyleSheet("""
            QScrollBar { background: transparent; border: none; }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.25); border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)
        self._sb.setVisible(self._show_scrollbar)
        # 连接滚动条与滚动区域：handle 长度随选项数量动态伸缩
        vbar = scroll.verticalScrollBar()
        vbar.rangeChanged.connect(self._sync_scrollbar)
        vbar.valueChanged.connect(self._sb.setValue)
        self._sb.valueChanged.connect(vbar.setValue)

        # 平滑滚轮动画：像拖动滚动条一样顺滑
        self._scroll_anim = QVariantAnimation(self)
        self._scroll_anim.setDuration(180)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim.valueChanged.connect(lambda v: vbar.setValue(int(v)))

        # 布局：左边滚动内容 + 右边自定义滚动条
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(2)
        main_layout.addWidget(scroll, 1)
        main_layout.addWidget(self._sb)

        # 拦截滚轮事件：viewport 和滚动条上的滚轮都走平滑动画
        scroll.viewport().installEventFilter(self)
        self._sb.installEventFilter(self)
        self.installEventFilter(self)

    def wheelEvent(self, event):
        """滚轮滚动列表内容：按比例换算滚动距离，用动画平滑过渡，避免生硬跳变。"""
        vbar = self._scroll_area.verticalScrollBar()
        delta = event.angleDelta().y()
        if delta == 0:
            return
        # 每次滚轮拨动滚动约 1/3 页，兼顾速度与平滑
        step = max(24, int(vbar.pageStep() * abs(delta) / 360.0))
        target = vbar.value() - (step if delta > 0 else -step)
        target = max(vbar.minimum(), min(vbar.maximum(), target))
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(vbar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()
        event.accept()

    def _sync_scrollbar(self, lo, hi):
        """同步自定义滚动条 range/pageStep：handle 长度随选项数量动态伸缩。"""
        vbar = self._scroll_area.verticalScrollBar()
        # pageStep 直接用视口高度（可见像素数），handle 长度 = 可见区/总内容，随项数动态变化
        page = max(1, self._scroll_area.viewport().height())
        self._sb.setRange(lo, hi)
        self._sb.setPageStep(page)
        self._sb.setVisible(hi > lo)

    def hide(self):
        """隐藏时停止滚动动画，避免后台继续动。"""
        if getattr(self, "_scroll_anim", None):
            self._scroll_anim.stop()
        super().hide()

    def paintEvent(self, event):
        """手动绘制圆角深色背景，避免 QSS 圆角与原生渲染冲突产生黑色边角。"""
        from PySide6.QtGui import QPainter, QColor, QPen, QBrush
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        # 填充深色圆角矩形
        p.setPen(QPen(QColor("#3c4252"), 1))
        p.setBrush(QBrush(QColor("#1d2027")))
        p.drawRoundedRect(rect, 8, 8)
        p.end()

    def _pick(self, idx):
        for i, btn in enumerate(self._items):
            btn.setChecked(i == idx)
        if self._on_select:
            self._on_select(idx)
        self.hide()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self._ready:
            self.hide()

    def eventFilter(self, obj, event):
        # 滚轮事件（viewport/滚动条/弹窗本身）统一走平滑动画
        if event.type() == QEvent.Type.Wheel:
            self.wheelEvent(event)
            return True
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            # 点击弹窗外区域关闭（用全局坐标判断，任何 obj 上都正确）
            if not self._frame_rect_contains(event.globalPosition().toPoint()):
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def _frame_rect_contains(self, gpos) -> bool:
        g = self.frameGeometry()
        return g.contains(gpos)

    def popup_at(self, pos):
        """在指定全局坐标位置弹出；空间不足时翻到左侧并保持屏幕内。"""
        screen = QApplication.primaryScreen().availableGeometry()
        w = self._popup_width
        # 高度 = 内容高度 + 外边距（4px × 2）
        n_visible = self._max_visible
        content_h = n_visible * self._item_h + (n_visible - 1) * self._item_gap + 2 * 2
        h = content_h + 8  # 外边距 4px × 2
        x = pos.x() + 6
        y = pos.y()
        if x + w > screen.right():
            x = pos.x() - w - 6
        if y + h > screen.bottom():
            y = max(screen.top(), pos.y() - h)
        self.setFixedSize(w, h)
        self.setGeometry(x, y, w, h)
        self.show()
        self.raise_()
        # 延迟启用 focusOut 隐藏
        from PySide6.QtCore import QTimer
        QTimer.singleShot(150, lambda: setattr(self, '_ready', True))


class _ViewerButton(QToolButton):
    """查看器内的覆盖按钮：必须作为宿主对话框的子控件（不能是顶层窗口），
    鼠标悬停时保持控制条显示，避免点击过程中被自动隐藏。"""
    def __init__(self, host, text="", size=(50, 90)):
        super().__init__(host)  # 关键：设置父窗口，否则会变成独立顶层窗口
        self._host = host
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(*size)
        self.hide()

    def enterEvent(self, event):
        self._host._show_controls()
        super().enterEvent(event)


class ImageViewerDialog(QDialog):
    """图片查看器对话框：最大化显示，支持滚轮缩放，左右切换，底部渐变信息栏。"""
    
    def __init__(self, pixmap: QPixmap, images: list, current_index: int, 
                 bundle, title: str = "图片查看器", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMouseTracking(True)
        
        # 存储图片列表和状态
        self.images = images
        self.current_index = current_index
        self.bundle = bundle
        self.original_pixmap = pixmap
        self.current_pixmap = pixmap
        self.scale_factor = 1.0
        
        # 设置背景为黑色
        self.setStyleSheet("QDialog { background-color: #0a0a0a; }")
        
        # 主布局（仅包含图片）
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 图片显示区域（使用 QLabel，占满整个窗口）
        self.image_label = _ViewerImageLabel(self)
        self.image_label.setMouseTracking(True)
        self.main_layout.addWidget(self.image_label)
        
        # ---- 以下全部是覆盖在图片上的控件（不参与布局） ----
        
        # 底部渐变遮罩（从透明到黑色，宽度占满窗口）
        self.gradient_mask = QWidget(self)
        self.gradient_mask.setFixedHeight(160)
        self.gradient_mask.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0,0,0,0), stop:0.4 rgba(0,0,0,0),
                stop:1 rgba(0,0,0,200));
        """)
        self.gradient_mask.hide()
        
        # 关闭按钮（父窗口为对话框本身，覆盖在右上角）
        self.close_btn = QPushButton(self)
        self.close_btn.setText("✕")
        self.close_btn.setFixedSize(40, 40)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,15);
                color: white; border: none; border-radius: 20px;
                font-size: 20px; font-weight: bold; padding: 0px;
                font-family: "Segoe UI Symbol", "Microsoft YaHei", "Arial";
            }
            QPushButton:hover { background-color: rgba(255,255,255,40); }
        """)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.hide()
        
        self.info_label = QLabel(self)
        self.info_label.setStyleSheet("color: rgba(255,255,255,0.92); font-size: 15px; background: transparent;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.hide()
        
        self.zoom_label = QLabel(self)
        self.zoom_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 13px; background: transparent;")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.zoom_label.hide()
        
        # 左右导航按钮（默认隐藏，作为窗口子控件覆盖在图片上）
        self.prev_btn = _ViewerButton(self, "‹")
        self.prev_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(0,0,0,100); color: white; border: none;
                border-radius: 8px; font-size: 40px; font-weight: bold;
            }
            QToolButton:hover { background-color: rgba(0,0,0,180); }
        """)
        self.prev_btn.clicked.connect(self._prev_image)
        
        self.next_btn = _ViewerButton(self, "›")
        self.next_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(0,0,0,100); color: white; border: none;
                border-radius: 8px; font-size: 40px; font-weight: bold;
            }
            QToolButton:hover { background-color: rgba(0,0,0,180); }
        """)
        self.next_btn.clicked.connect(self._next_image)
        
        # 初始化显示
        self._update_display()
        self._update_nav_buttons()
        self._update_info_label()
        
        # 全屏显示
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            self.setGeometry(screen_rect)
        
        # 先调用一次 resizeEvent 确保控件位置正确
        self.resizeEvent(None)
        
        # 光标空闲计时器：仅负责“2 秒内鼠标停在空处且不操作 → 隐藏系统光标”
        # UI 显隐不依赖计时器，完全由鼠标位置事件驱动
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.timeout.connect(self._on_cursor_idle)
        self._cursor_timer.start(2000)

        # 光标显隐状态（防重入标记）
        self._cursor_hidden = False

        # ---- 控制条透明度过渡动画（150ms）----
        self._controls = [self.gradient_mask, self.close_btn, self.info_label,
                          self.zoom_label, self.prev_btn, self.next_btn]
        self._opacity_effects = {}
        self._fade_anims = {}
        self._fade_finished = {}
        for c in self._controls:
            eff = QGraphicsOpacityEffect(c)
            c.setGraphicsEffect(eff)
            eff.setOpacity(0.0)
            self._opacity_effects[c] = eff
        # 安全清理：确保销毁时恢复光标（防止 closeEvent 未触发的情况）
        self.destroyed.connect(self._on_destroyed)
        # 打开时默认显示 UI（后续由鼠标位置驱动显隐）
        self._controls_visible = False
        self._show_controls()
        
    def _update_display(self):
        """把当前图片交给内容区（重置缩放/平移）。"""
        if self.original_pixmap is None:
            return
        self.image_label.set_source(self.original_pixmap)
        self._on_zoom_changed(1.0)

    def _on_zoom_changed(self, scale: float):
        """缩放变化时更新百分比显示。"""
        self.scale_factor = scale
        self.zoom_label.setText(f"{int(scale * 100)}%")
        
    def _update_nav_buttons(self):
        """更新导航按钮可用状态：循环切换，始终可用（单张图时也保持可点，点击无副作用）。"""
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        
    def _update_info_label(self):
        """更新底部信息标签（去掉文件后缀）。"""
        image = self.images[self.current_index]
        name = os.path.splitext(image.get("name", ""))[0]
        self.info_label.setText(f"{name}  ({self.current_index + 1} / {len(self.images)})")
        
    def _prev_image(self):
        """切换到上一张图片：第一张时循环到最后一张。"""
        if not self.images:
            return
        self.current_index = (self.current_index - 1) % len(self.images)
        self._load_current_image()
            
    def _next_image(self):
        """切换到下一张图片：最后一张时循环到第一张。"""
        if not self.images:
            return
        self.current_index = (self.current_index + 1) % len(self.images)
        self._load_current_image()
            
    def _load_current_image(self):
        """加载当前索引的图片。"""
        image = self.images[self.current_index]
        self.original_pixmap = QPixmap(self.bundle.asset_path(image["path"]))
        if self.original_pixmap.isNull():
            self.original_pixmap = QPixmap(720, 420)
            self.original_pixmap.fill(Qt.GlobalColor.darkGray)
        
        # 重置缩放因子
        self.scale_factor = 1.0
        
        self._update_display()
        self._update_nav_buttons()
        self._update_info_label()
        
    def _show_controls(self):
        """显示控制条：150ms 透明度淡入（不依赖计时器）。"""
        if self._controls_visible:
            return
        self._controls_visible = True
        for c in self._controls:
            c.show()
            c.raise_()
        self._fade_controls(1.0)

    def _hide_controls(self):
        """隐藏控制条：150ms 透明度淡出，动画结束后真正隐藏（不依赖计时器）。"""
        if not self._controls_visible:
            return
        self._controls_visible = False
        self._fade_controls(0.0)

    def _fade_controls(self, target: float):
        """对所有控制条做 150ms 透明度过渡（复用动画对象）。"""
        for c in self._controls:
            eff = self._opacity_effects[c]
            anim = self._fade_anims.get(c)
            if anim is None:
                anim = QPropertyAnimation(eff, b"opacity", self)
                anim.setDuration(150)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._fade_anims[c] = anim
            # 已向同一方向运行则不重复启动
            if anim.state() == QAbstractAnimation.State.Running and \
                    abs(anim.endValue() - target) < 1e-6:
                continue
            anim.stop()
            anim.setStartValue(eff.opacity())
            anim.setEndValue(target)
            slot = self._fade_finished.get(c)
            if slot is not None:
                try:
                    anim.finished.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
                self._fade_finished[c] = None
            if target <= 0.0:
                slot = lambda _=False, w=c: w.hide()
                anim.finished.connect(slot)
                self._fade_finished[c] = slot
            anim.start()

    # ---------- UI 显隐（位置驱动，无计时器） ----------
    EDGE_MARGIN = 60  # 四边缘条带的宽度（像素）

    def _edge_rects(self):
        """四个边缘条带矩形：上 / 下 / 左 / 右。
        鼠标进入任一边缘条带即显示 UI，中间区域则隐藏。"""
        w, h = self.width(), self.height()
        e = self.EDGE_MARGIN
        return [
            QRect(0, 0, w, e),          # 上边缘
            QRect(0, h - e, w, e),      # 下边缘
            QRect(0, 0, e, h),          # 左边缘
            QRect(w - e, 0, e, h),      # 右边缘
        ]

    def _pointer_over_control(self, gpos) -> bool:
        """判断全局坐标是否落在任一 UI 控件（按钮/底部阴影/信息文本）的
        几何区域内。无论控件当前是否可见都参与判断，保证 UI 淡出后
        鼠标移回原位置仍能重新唤起 UI。"""
        local = self.mapFromGlobal(gpos)
        for c in self._controls:
            if c.geometry().contains(local):
                return True
        return False

    def _pointer_in_ui_area(self, gpos) -> bool:
        """鼠标位于上下左右四边缘条带或任一 UI 控件几何区域内 → 显示 UI。"""
        local = self.mapFromGlobal(gpos)
        for r in self._edge_rects():
            if r.contains(local):
                return True
        return self._pointer_over_control(gpos)

    def _sync_ui_by_pointer(self, gpos):
        """按鼠标位置即时决定 UI 显隐（无计时器）：
        - 位于上下左右四边缘条带 / UI 控件上 → 淡入
        - 位于中间空处 → 直接淡出"""
        if self._pointer_in_ui_area(gpos):
            self._show_controls()
        else:
            self._hide_controls()

    # ---------- 光标显隐（独立逻辑：2s 无操作 → 立即隐藏，无动画） ----------
    def _on_cursor_idle(self):
        """光标空闲超时：仅当鼠标在窗口内、停在边缘/UI 外、2 秒无操作时隐藏光标。"""
        gpos = QCursor.pos()
        if not self.frameGeometry().contains(gpos):
            return  # 鼠标不在窗口内，不处理
        if self._pointer_in_ui_area(gpos):
            # 位于四边缘条带或 UI 控件上：光标也不隐藏，继续等待
            self._cursor_timer.start(2000)
            return
        self._hide_cursor_now()

    def _hide_cursor_now(self):
        """立即隐藏光标（仅影响图片区域，不污染全局光标栈）。"""
        if self._cursor_hidden:
            return
        self._cursor_hidden = True
        self.image_label.set_cursor_hidden(True)

    def _show_cursor_now(self):
        """立即恢复光标。"""
        if not self._cursor_hidden:
            return
        self._cursor_hidden = False
        self.image_label.set_cursor_hidden(False)

    def _on_pointer_click(self):
        """点击任意位置：光标立即显现，重置 2s 空闲计时；UI 按位置决定。"""
        self._show_cursor_now()
        self._cursor_timer.start(2000)
        self._sync_ui_by_pointer(QCursor.pos())

    def closeEvent(self, event):
        """关闭时强制恢复光标并清理计时器。"""
        self._cursor_timer.stop()
        # 无论 _cursor_hidden 当前是什么值，都强制重置到已知安全状态，
        # 防止 BlankCursor 残留到父窗口。
        self._cursor_hidden = False
        if self.image_label:
            self.image_label._cursor_hidden = False
            self.image_label.setCursor(Qt.CursorShape.ArrowCursor)
        super().closeEvent(event)

    def _on_destroyed(self):
        """安全清理：对象被 Qt 销毁时确保光标已恢复。"""
        self._cursor_hidden = False
        if hasattr(self, '_cursor_timer') and self._cursor_timer:
            self._cursor_timer.stop()
        if hasattr(self, 'image_label') and self.image_label:
            self.image_label._cursor_hidden = False
            self.image_label.setCursor(Qt.CursorShape.ArrowCursor)

    def resizeEvent(self, event):
        """窗口大小改变时重新定位控件。"""
        if event is not None:
            super().resizeEvent(event)
        
        w, h = self.width(), self.height()
        
        # 渐变遮罩：覆盖底部 160px
        self.gradient_mask.setGeometry(0, h - 160, w, 160)
        
        # 导航按钮：垂直居中
        btn_height = 90
        btn_y = (h - btn_height) // 2
        self.prev_btn.move(16, btn_y)
        self.next_btn.move(w - 66, btn_y)
        
        # 关闭按钮：右上角
        self.close_btn.move(w - 50, 10)
        
        # 底部信息栏：图片名称 + 缩放比例
        self.info_label.setGeometry(0, h - 60, w, 28)
        self.zoom_label.setGeometry(w - 220, h - 60, 200, 28)
        
        # 保持当前缩放/平移，仅重绘（不要重置为 1.0）
        self.image_label.update()
        
    def mouseMoveEvent(self, event):
        """鼠标移动：位置驱动 UI 显隐，重置光标空闲计时。"""
        self._on_image_mouse_move(event)

    def mousePressEvent(self, event):
        """点击任意位置：光标立即显现，重置空闲计时。"""
        self._on_pointer_click()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """鼠标进入窗口：同步 UI 状态。"""
        self._on_image_mouse_move(event)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开窗口：停止光标计时，恢复光标，隐藏 UI。"""
        self._cursor_timer.stop()
        self._show_cursor_now()
        self._hide_controls()
        super().leaveEvent(event)

    def _on_image_mouse_move(self, event):
        """处理鼠标移动：
        - 移动 = 活动 → 光标立即显现（若有隐藏），重置 2s 空闲计时
        - 拖动图片时保持 UI 显示、光标可见
        - 光标位于四边缘条带 / UI 控件上 → UI 淡入
        - 光标在中间空处 → UI 直接淡出（无计时器）"""
        self._show_cursor_now()
        self._cursor_timer.start(2000)
        if getattr(self.image_label, "_dragging", False):
            self._show_controls()
            return
        self._sync_ui_by_pointer(event.globalPosition().toPoint())

    # 滚轮缩放由 _ViewerImageLabel 以鼠标为锚点处理，此处无需重复实现
    def keyPressEvent(self, event):
        """按键事件处理。"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Left:
            self._prev_image()
        elif event.key() == Qt.Key.Key_Right:
            self._next_image()
        super().keyPressEvent(event)


class PlayerWindow(QMainWindow):
    """音乐相册播放器主窗口。"""

    closed = Signal()

    def __init__(self, bundle: Bundle, parent=None):
        super().__init__(parent)
        self.bundle = bundle
        self.images = list(bundle.images)
        self.musics = list(bundle.musics)
        self.image_index = 0
        self.music_index = 0
        self.play_mode = PLAY_MODES[0]  # 默认顺序播放
        self._pending = []  # 随机播放的未播池（歌曲索引）
        self._origin_pixmap = None
        self._seeking = False

        self.setWindowTitle(f"{bundle.title} · 音乐相册")
        self.setMinimumSize(1120, 720)
        self._load_window_state()

        self._build_ui()
        self._init_player()
        self._show_image(0)
        if self.musics:
            self._select_music(0)
        else:
            self._disable_music_controls()

    # ---------- UI ----------
    def _build_ui(self):
        _, _, inner = apply_frameless(self, self.bundle.title, icon=APP_ICON)
        root = QVBoxLayout()
        root.setContentsMargins(24, 6, 24, 16)
        root.setSpacing(10)
        inner.addLayout(root, 1)

        # ---- 图片鉴赏区 ----
        self.image_label = GalleryImageLabel()
        self.image_label.setObjectName("gallery")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(320)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        # 设置图片标签支持点击事件
        self.image_label.mousePressEvent = self._on_image_click

        self.prev_btn = QToolButton()
        self.prev_btn.setObjectName("navBtn")
        self.prev_btn.setText("‹")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setToolTip("上一张")
        # 不抢焦点：启动时不聚焦、点击也不高亮，只有悬停时高亮
        self.prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.clicked.connect(lambda: self._show_image(self.image_index - 1))

        self.next_btn = QToolButton()
        self.next_btn.setObjectName("navBtn")
        self.next_btn.setText("›")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setToolTip("下一张")
        self.next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_btn.clicked.connect(lambda: self._show_image(self.image_index + 1))

        gallery_row = QHBoxLayout()
        gallery_row.setSpacing(4)
        gallery_row.addWidget(self.prev_btn)
        gallery_row.addWidget(self.image_label, 1)
        gallery_row.addWidget(self.next_btn)
        root.addLayout(gallery_row, 1)

        self.index_label = _ClickableLabel()
        self.index_label.setObjectName("indexLabel")
        self.index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.index_label.clicked.connect(self._show_image_menu)
        root.addWidget(self.index_label)

        # ---- 音乐播放区 ----
        panel = QWidget()
        panel.setObjectName("musicPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 12, 16, 14)
        panel_layout.setSpacing(8)

        # 歌曲信息行
        row1 = QHBoxLayout()
        self.song_label = QLabel()
        self.song_label.setObjectName("songTitle")
        self.list_btn = QPushButton("♪ 音乐列表")
        self.list_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_btn.clicked.connect(self._show_music_menu)
        self.list_btn.setVisible(len(self.musics) > 1)
        row1.addWidget(self.song_label, 1)
        row1.addWidget(self.list_btn)
        panel_layout.addLayout(row1)

        # 进度条行
        row2 = QHBoxLayout()
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("timeLabel")
        self.time_label.setFixedWidth(130)
        self.progress = ClickableSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 0)
        self.progress.setCursor(Qt.CursorShape.PointingHandCursor)
        self.progress.sliderPressed.connect(self._on_slider_pressed)
        self.progress.sliderReleased.connect(self._on_slider_released)
        self.progress.sliderMoved.connect(self._on_slider_moved)
        row2.addWidget(self.time_label)
        row2.addWidget(self.progress, 1)
        panel_layout.addLayout(row2)

        # 控制行：上一首 / 播放暂停 / 下一首 / 播放模式 + 音量
        row3 = QHBoxLayout()
        self.prev_music_btn = QPushButton("⏮ 上一首")
        self.prev_music_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_music_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_music_btn.setToolTip("上一首")
        self.prev_music_btn.clicked.connect(self._prev_music)
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("primaryBtn")
        self.play_btn.setFixedWidth(110)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.clicked.connect(self._toggle_play)
        self._play_icon = self._make_media_icon("play")
        self._pause_icon = self._make_media_icon("pause")
        self.play_btn.setIconSize(QSize(18, 18))
        self._update_play_button(False)
        self.next_music_btn = QPushButton("下一首 ⏭")
        self.next_music_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_music_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_music_btn.setToolTip("下一首")
        self.next_music_btn.clicked.connect(self._next_music)
        self.mode_btn = QPushButton()
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode_btn.clicked.connect(self._cycle_mode)
        self._update_mode_button()
        self.vol_icon = QLabel("🔊")
        self.vol_icon.setObjectName("volIcon")
        self.volume = ClickableSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setCursor(Qt.CursorShape.PointingHandCursor)
        # 音量持久化：记住上次的大小（即使本相册无音乐，也保留该值）
        s = self._settings()
        saved_vol = s.value("volume", 80, type=int)
        self.volume.setValue(max(0, min(100, saved_vol)))
        self.volume.setFixedWidth(140)
        self.volume.setToolTip("音量")
        self.volume.valueChanged.connect(self._on_volume)
        row3.addWidget(self.prev_music_btn)
        row3.addWidget(self.play_btn)
        row3.addWidget(self.next_music_btn)
        row3.addWidget(self.mode_btn)
        row3.addStretch()
        row3.addWidget(self.vol_icon)
        row3.addWidget(self.volume)
        panel_layout.addLayout(row3)

        root.addWidget(panel)

    # ---------- 播放器 ----------
    def _disable_music_controls(self):
        """相册未打包音乐时调用：把音乐控制区整体置灰并禁用。"""
        self.song_label.setText("♫ 本相册未包含音乐")
        self.time_label.setText("--:-- / --:--")
        self.list_btn.setVisible(False)
        self.prev_music_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.next_music_btn.setEnabled(False)
        self.mode_btn.setEnabled(False)
        self.vol_icon.setText("🔇")
        self.volume.setEnabled(False)
        self.progress.setEnabled(False)

    def _init_player(self):
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(self.volume.value() / 100.0)
        self.player.setAudioOutput(self.audio)

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)

    def _select_music(self, index: int):
        """切换到第 index 首音乐并自动播放。"""
        if not self.musics:
            return
        index %= len(self.musics)
        old = self.music_index
        self.music_index = index
        self._forget_from_pending(old)
        music = self.musics[index]
        self.song_label.setText(f"♪ {music['name']}")
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(self.bundle.asset_path(music["path"])))
        self.player.play()
        self._update_play_button(True)
        self.list_btn.setText(f"♪ 音乐列表  ({index + 1}/{len(self.musics)})")
        self._update_nav_buttons()

    # ---------- 播放模式 / 切歌 ----------
    def _update_mode_button(self):
        self.mode_btn.setText(f"{MODE_ICONS[self.play_mode]} {self.play_mode}")
        self.mode_btn.setToolTip(MODE_TIPS[self.play_mode])

    def _cycle_mode(self):
        """顺序播放 → 单曲循环 → 随机播放 → 顺序播放 循环切换。"""
        idx = PLAY_MODES.index(self.play_mode)
        self.play_mode = PLAY_MODES[(idx + 1) % len(PLAY_MODES)]
        self._update_mode_button()
        if self.play_mode == "随机播放":
            self._reset_pending()

    def _reset_pending(self):
        """随机播放的未播池：除当前曲外的全部歌曲，乱序。"""
        n = len(self.musics)
        self._pending = [i for i in range(n) if i != self.music_index]
        random.shuffle(self._pending)

    def _forget_from_pending(self, old_index: int):
        """已播放过的歌曲（旧曲与新当前曲）都不再进入随机池。"""
        for idx in (old_index, self.music_index):
            if idx in self._pending:
                self._pending.remove(idx)

    def _pop_next_random(self) -> int:
        """从未播池取下一首；池空则开启新一轮随机。"""
        if not self._pending:
            self._reset_pending()
        if not self._pending:
            return self.music_index  # 只有一首歌
        return self._pending.pop()

    def _next_music(self):
        """手动下一首：随机模式下从未播池取，其余模式按列表顺序。"""
        if len(self.musics) <= 1:
            return
        if self.play_mode == "随机播放":
            nxt = self._pop_next_random()
        else:
            nxt = (self.music_index + 1) % len(self.musics)
        self._select_music(nxt)

    def _prev_music(self):
        """手动上一首：按列表顺序回退一首（单曲时无效果）。"""
        if len(self.musics) <= 1:
            return
        self._select_music((self.music_index - 1) % len(self.musics))

    def _update_nav_buttons(self):
        single = len(self.musics) <= 1
        self.prev_music_btn.setEnabled(not single)
        self.next_music_btn.setEnabled(not single)

    def _update_play_button(self, playing: bool):
        """切换播放/暂停的图标与文字（标准媒体图标，紧凑美观）。"""
        self.play_btn.setIcon(self._pause_icon if playing else self._play_icon)
        self.play_btn.setText(" 暂停" if playing else " 播放")

    def _make_media_icon(self, kind: str) -> QIcon:
        """生成白灰色实心播放/暂停图标。

        源图按 64×64 绘制，显示时由 Qt 缩小到 18×18：
        缩小渲染在任何 DPI（125%/150% 缩放）下都清晰，
        且不会出现 DPR 方案导致的放大截断问题。
        """
        size = 64  # 高清源图，Qt 负责高质量缩小
        color = QColor("#ffffff")  # 与按钮文字色一致
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if kind == "play":
            # 实心播放三角（填充白灰色）
            p.setPen(QPen(color, 2.0))
            p.setBrush(color)
            pts = [
                QPointF(22.0, 13.0),
                QPointF(50.0, 32.0),
                QPointF(22.0, 51.0),
            ]
            p.drawPolygon(pts)
        else:  # pause：两条实心圆角竖线
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            bar_w = 8.0
            gap = 10.0
            top = 13.0
            h = 38.0
            x0 = (size - (bar_w * 2 + gap)) / 2.0
            p.drawRoundedRect(QRectF(x0, top, bar_w, h), 3.0, 3.0)
            p.drawRoundedRect(QRectF(x0 + bar_w + gap, top, bar_w, h), 3.0, 3.0)
        p.end()
        return QIcon(pm)

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self._update_play_button(False)
        else:
            self.player.play()
            self._update_play_button(True)

    def _show_music_menu(self):
        """点击音乐列表按钮：已打开则关闭，未打开则弹出。"""
        if getattr(self, "_popup_ref", None) is not None and self._popup_ref.isVisible():
            self._popup_ref.hide()
            self._popup_ref = None
            return
        popup = _ImageListPopup(
            self.musics, self.music_index, self._select_music, parent=self
        )
        self._popup_ref = popup
        btn_pos = self.list_btn.mapToGlobal(self.list_btn.rect().bottomLeft())
        popup.popup_at(btn_pos)

    # ---------- 图片 ----------
    def _show_image(self, index: int):
        """显示第 index 张图片（越界自动循环）。"""
        if not self.images:
            return
        self.image_index = index % len(self.images)
        image = self.images[self.image_index]
        pixmap = QPixmap(self.bundle.asset_path(image["path"]))
        if pixmap.isNull():
            pixmap = QPixmap(720, 420)
            pixmap.fill(Qt.GlobalColor.darkGray)
        self._origin_pixmap = pixmap
        # 显示图片名（去掉文件后缀，如 .png），并保留张数信息
        name = os.path.splitext(image.get("name", ""))[0]
        self.index_label.setText(f"{name}  ({self.image_index + 1} / {len(self.images)})")
        self._update_image_display()

    def _show_image_menu(self):
        """点击图片名称行：已打开则关闭，未打开则弹出列表。"""
        if len(self.images) <= 1:
            return
        if getattr(self, "_popup_ref", None) is not None and self._popup_ref.isVisible():
            self._popup_ref.hide()
            self._popup_ref = None
            return
        popup = _ImageListPopup(
            self.images, self.image_index, self._show_image, parent=self
        )
        self._popup_ref = popup
        popup._label_ref = self.index_label

        original_hide = popup.hideEvent

        def _on_hide(e):
            self.index_label._popup_visible = False
            original_hide(e)

        popup.hideEvent = _on_hide
        self.index_label._popup_visible = True

        # 用 QFontMetrics.boundingRect 精确计算文字右边缘的全局坐标
        lbl = self.index_label
        cr = lbl.contentsRect()
        fm = lbl.fontMetrics()
        text_rect = fm.boundingRect(lbl.text())
        align = lbl.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
        if align == Qt.AlignmentFlag.AlignRight:
            text_x = cr.right() - text_rect.width()
        elif align == Qt.AlignmentFlag.AlignHCenter:
            text_x = cr.left() + (cr.width() - text_rect.width()) // 2
        else:
            text_x = cr.left()
        text_right_local = QPoint(text_x + text_rect.width(), cr.top() + cr.height() // 2)
        text_right_global = lbl.mapToGlobal(text_right_local)
        popup.popup_at(text_right_global)

    def _update_image_display(self):
        """按当前控件尺寸等比缩放图片（保持纵横比），确保图片清晰。"""
        if self._origin_pixmap is None:
            return
        # 直接设置原始 pixmap，由 GalleryImageLabel 负责高质量绘制
        self.image_label.setPixmap(self._origin_pixmap)

    def _on_image_click(self, event: QMouseEvent):
        """点击图片时，打开图片查看器对话框。"""
        if self._origin_pixmap is None:
            return
        # 创建图片查看器对话框
        dialog = ImageViewerDialog(
            self._origin_pixmap, 
            self.images,
            self.image_index,
            self.bundle,
            title=f"{self.bundle.title} · 图片查看器",
            parent=self
        )
        dialog.exec()
        # 安全措施：对话框关闭后，确保本窗口光标回到正常状态
        self.image_label.setCursor(Qt.CursorShape.ArrowCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_image_display()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_image_display()
        # 启动时不聚焦任何按钮：清除焦点，避免按钮高亮（仅悬停时高亮）
        if QApplication.focusWidget() is not None:
            QApplication.focusWidget().clearFocus()
        self.setFocus()  # 焦点给窗口本身，不落到任何子控件

    # ---------- 播放器回调 ----------
    def _on_position(self, ms: int):
        if not self._seeking:
            self.progress.setValue(ms)
        self.time_label.setText(f"{_fmt_ms(ms)} / {_fmt_ms(self.player.duration())}")

    def _on_duration(self, ms: int):
        self.progress.setRange(0, max(0, ms))

    def _on_status(self, status):
        """歌曲播放完：按当前播放模式决定下一首。"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.play_mode == "单曲循环":
                self.player.setPosition(0)
                self.player.play()
                return
            if len(self.musics) <= 1:
                self._update_play_button(False)
                return
            if self.play_mode == "随机播放":
                nxt = self._pop_next_random()
            else:  # 顺序播放：最后一首播完回到第一首
                nxt = (self.music_index + 1) % len(self.musics)
            self._select_music(nxt)

    def _on_error(self, error, error_string):
        if error != QMediaPlayer.Error.NoError:
            self.song_label.setText(f"♪ 播放出错：{error_string}")

    def _on_slider_pressed(self):
        self._seeking = True

    def _on_slider_moved(self, pos: int):
        self.time_label.setText(f"{_fmt_ms(pos)} / {_fmt_ms(self.player.duration())}")

    def _on_slider_released(self):
        self._seeking = False
        self.player.setPosition(self.progress.value())

    def _on_volume(self, value: int):
        self.audio.setVolume(value / 100.0)
        self.vol_icon.setText("🔊" if value > 0 else "🔇")
        # 记住音量大小（QSettings 析构时自动落盘）
        self._settings().setValue("volume", value)

    # ---------- 窗口状态记忆 ----------
    def _settings(self) -> QSettings:
        """窗口状态存到项目目录下（便携，随文件夹一起拷贝）。"""
        ini = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "player_state.ini"
        )
        return QSettings(ini, QSettings.Format.IniFormat)

    def _load_window_state(self):
        """恢复上次用户调整过的窗口大小；没有记录则按当前屏幕分辨率
        缩放到默认 1280×800，并始终把窗口居中到屏幕中央。"""
        s = self._settings()
        size = s.value("window/size")
        if isinstance(size, QSize) and size.isValid():
            geo = _screen_geometry(self)
            w = max(size.width(), self.minimumWidth())
            h = max(size.height(), self.minimumHeight())
            # 记忆的尺寸如果超出当前屏幕，收进屏幕可用区内
            w = min(w, int(geo.width() * 0.92))
            h = min(h, int(geo.height() * 0.92))
            self.resize(w, h)
        else:
            fit_to_screen(self, 1600, 1000, self.minimumWidth(), self.minimumHeight())
        center_on_screen(self)

    def _save_window_state(self):
        """保存当前窗口大小，供下次打开时恢复。"""
        s = self._settings()
        # 最大化时保存还原后的尺寸，避免下次以最大化状态启动
        size = self.normalGeometry().size() if self.isMaximized() else self.size()
        s.setValue("window/size", size)
        s.sync()

    def closeEvent(self, event):
        self._save_window_state()
        self.player.stop()
        self.bundle.close()
        self.closed.emit()
        super().closeEvent(event)
