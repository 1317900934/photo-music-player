# -*- coding: utf-8 -*-
"""自定义无边框窗口支持：自绘标题栏 + 圆角窗口 + 圆角阴影 + 边缘缩放。

- TitleBar：自绘标题栏，左侧图标 + 标题，右侧最小化 / 最大化还原 / 关闭按钮，
  支持按住拖拽移动窗口、双击最大化 / 还原。
- ShadowShell：窗口外壳，自绘圆角背景 + 圆角柔和阴影。不使用
  QGraphicsDropShadowEffect —— 它的阴影基于矩形边界生成，会在圆角窗口的
  四角留下尖锐的直角黑角；这里改为逐层绘制同心圆角矩形，阴影形状与窗口
  圆角完全一致，四角平滑过渡。阴影绘制在 shell 自身的边距区域，不会被
  子控件裁剪。
- FramelessHelper：窗口边缘区域拖拽缩放（与系统窗口行为一致）。
- apply_frameless：把普通 QMainWindow 改造成圆角无边框窗口，返回
  (title_bar, content, inner_layout)，调用方把内容布局装进 inner_layout。
"""
import os

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CONTENT_OBJECT_NAME = "appContent"


def sync_shadow_margins(window, maximized: bool):
    """根据最大化状态调整外壳：圆角/阴影开关 + 内容边距。"""
    shell = getattr(window, "_tb_shell", None)
    if shell is None:
        return
    shell.set_maximized(maximized)
    if maximized:
        shell.layout().setContentsMargins(0, 0, 0, 0)
    else:
        m = ShadowShell.SHADOW
        off = ShadowShell.OFFSET
        shell.layout().setContentsMargins(m, m, m, m + off)


# 程序主图标（多尺寸 ICO），供窗口/任务栏/标题栏使用
_ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
APP_ICON = os.path.join(_ICONS_DIR, "app_icon.ico")


def _icon_for_label(icon):
    """标题栏图标：图片路径 → QPixmap；否则按文本 emoji 显示。"""
    if isinstance(icon, str) and os.path.isfile(icon):
        qi = QIcon(icon)
        if not qi.isNull():
            # 从 ICO 多尺寸中选取最接近目标尺寸的帧，避免从 256px 硬缩导致模糊
            pm = qi.pixmap(20, 20, QIcon.Mode.Normal, QIcon.State.On)
            if not pm.isNull():
                return pm
    return None


def apply_frameless(window, title, icon="🎞️"):
    """把 QMainWindow 改造成无边框圆角窗口。

    返回 (TitleBar, content, inner_layout)：
      - content 是透明内容容器（objectName=appContent），圆角背景由外壳绘制
      - inner_layout 是 content 内部的纵向布局，调用方把页面内容加进去
    """
    window.setWindowFlags(
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
    )
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    if os.path.isfile(APP_ICON):
        window.setWindowIcon(QIcon(APP_ICON))

    shell = ShadowShell()
    window.setCentralWidget(shell)
    outer = QVBoxLayout(shell)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    content = QWidget()
    content.setObjectName(CONTENT_OBJECT_NAME)
    content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    outer.addWidget(content)

    title_bar = TitleBar(title, window, icon)
    inner = QVBoxLayout(content)
    inner.setContentsMargins(0, 0, 0, 0)
    inner.setSpacing(0)
    inner.addWidget(title_bar)

    helper = FramelessHelper(window)
    helper.install(shell)

    window._tb_content = content
    window._tb_title = title_bar
    window._tb_shell = shell
    window._tb_helper = helper  # 供测试引用
    sync_shadow_margins(window, False)
    return title_bar, content, inner


class ShadowShell(QWidget):
    """窗口外壳：自绘圆角背景 + 圆角柔和阴影（含内容边距）。"""

    RADIUS = 14     # 圆角半径（像素）
    SHADOW = 8      # 阴影扩散半径（像素），收束后几乎看不见
    OFFSET = 2      # 阴影向下偏移（像素）
    MAX_ALPHA = 10  # 阴影最深处不透明度（0-255），几乎不可见
    BG = QColor("#16181d")
    BORDER = QColor("#262b36")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._maximized = False

    def set_maximized(self, on: bool):
        self._maximized = on
        self.setProperty("tbMax", on)
        self.update()

    def _inner_rect(self) -> QRectF:
        """圆角主体区域（内容所在位置，含阴影边距偏移）。"""
        if self._maximized:
            return QRectF(self.rect())
        m = self.SHADOW
        return QRectF(self.rect()).adjusted(m, m, -m, -(m + self.OFFSET))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._maximized:
            p.fillRect(QRectF(self.rect()), self.BG)
            return
        inner = self._inner_rect()
        # 阴影层：同心圆角矩形由外到内逐层加深，四角平滑无直角
        for i in range(self.SHADOW, 0, -1):
            alpha = self.MAX_ALPHA * (self.SHADOW - i + 1) // self.SHADOW
            r = inner.adjusted(-i, -i + self.OFFSET, i, i + self.OFFSET)
            path = QPainterPath()
            path.addRoundedRect(r, self.RADIUS + i, self.RADIUS + i)
            p.fillPath(path, QColor(0, 0, 0, alpha))
        # 主体圆角背景
        path = QPainterPath()
        path.addRoundedRect(inner, self.RADIUS, self.RADIUS)
        p.fillPath(path, self.BG)
        p.setPen(QPen(self.BORDER, 1))
        p.drawPath(path)


class TitleBar(QWidget):
    """自绘标题栏：图标 + 标题 + 最小化 / 最大化还原 / 关闭。"""

    HEIGHT = 44

    def __init__(self, title, window, icon="🎞️", parent=None):
        super().__init__(parent)
        self._window = window
        self._drag = None
        self.setObjectName("titleBar")
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 10, 0)
        layout.setSpacing(8)

        if icon:
            pm = _icon_for_label(icon)
            icon_label = QLabel()
            icon_label.setObjectName("tbIcon")
            if pm is not None:
                icon_label.setPixmap(pm)
            else:
                icon_label.setText(icon)
            layout.addWidget(icon_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("tbTitle")
        layout.addWidget(self.title_label)
        layout.addStretch()

        self.min_btn = self._make_btn("─", "最小化", "tbBtn")
        self.max_btn = self._make_btn("□", "最大化", "tbBtn")
        self.close_btn = self._make_btn("✕", "关闭", "tbClose")
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

        self.min_btn.clicked.connect(self._window.showMinimized)
        self.max_btn.clicked.connect(self._toggle_max)
        self.close_btn.clicked.connect(self._window.close)

    def set_title(self, title: str):
        self.title_label.setText(title)

    def _make_btn(self, text, tip, obj_name):
        btn = QPushButton(text)
        btn.setObjectName(obj_name)
        btn.setToolTip(tip)
        btn.setFixedSize(44, 32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def _toggle_max(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self.sync_max_state()

    def sync_max_state(self):
        """最大化状态变化时更新按钮图标与外壳圆角/阴影。"""
        maximized = self._window.isMaximized()
        self.max_btn.setText("❐" if maximized else "□")
        self.max_btn.setToolTip("还原" if maximized else "最大化")
        sync_shadow_margins(self._window, maximized)

    # ---- 拖拽移动 ----
    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._window.isMaximized()
        ):
            self._drag = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            self._window.move(event.globalPosition().toPoint() - self._drag)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
        else:
            super().mouseDoubleClickEvent(event)


class FramelessHelper(QObject):
    """窗口边缘拖拽缩放。

    命中区域与圆角内容的可视边缘对齐（而非窗口矩形的阴影外圈）：
    以 ShadowShell 的内矩形（圆角主体）四边为中心，向阴影方向外扩
    EDGE_OUT 像素、向内容方向内扩 EDGE_IN 像素，组成拉动触发带。
    四角以圆角弧线为基准的环形窄带判定（半径 = 圆角半径，弧内仅
    CORNER_IN 像素深），保证圆角窗口四角贴近弧线时才能触发对角缩放。
    """

    # 拉动（resize）只允许在内容边缘 2px 内触发——光标变为拉动样式后才能缩放；
    # 其余靠近边缘的区域（阴影过渡带 + 内容边缘内侧浅带）按下拖动 = 移动窗口。
    EDGE_OUT = 2   # 内容边缘向外 2px：resize 触发带
    EDGE_IN = 2    # 内容边缘向内 2px：resize 触发带
    MOVE_OUT = 7   # 内容边缘向外 2~7px：移动窗口带（阴影过渡区，最外圈 1px 不触发）
    MOVE_IN = 6    # 内容边缘向内 2~6px：移动窗口带
    CORNER = 14    # 四角弧线半径（与圆角半径一致）
    MOVE = "move"  # 命中：移动窗口位置

    _CURSORS = {
        "l": Qt.CursorShape.SizeHorCursor,
        "r": Qt.CursorShape.SizeHorCursor,
        "t": Qt.CursorShape.SizeVerCursor,
        "b": Qt.CursorShape.SizeVerCursor,
        "tl": Qt.CursorShape.SizeFDiagCursor,
        "br": Qt.CursorShape.SizeFDiagCursor,
        "tr": Qt.CursorShape.SizeBDiagCursor,
        "bl": Qt.CursorShape.SizeBDiagCursor,
    }

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._shell = None
        self._dir = None
        self._move = None
        self._start_geom = None
        self._start_gp = None
        self._apps = []

    def install(self, widget):
        self._shell = widget
        widget.installEventFilter(self)
        self._enable_tracking_recursive(widget)
        # 应用级过滤器：子控件不产生 MouseMove 时也能更新光标；
        # 同时捕获动态新增控件以启用鼠标跟踪
        app = QApplication.instance()
        if app is not None and app not in self._apps:
            self._apps.append(app)
            app.installEventFilter(self)

    def _enable_tracking_recursive(self, w):
        w.setMouseTracking(True)
        for child in w.findChildren(QWidget):
            child.setMouseTracking(True)

    def _hit(self, p):
        """命中判定（p 为外壳坐标系坐标）。

        返回：
          - 方向字符串 l/r/t/b/tl/tr/bl/br：resize 触发带（内容边缘 2px 内 / 圆角弧线 2px 内）
          - MOVE：移动窗口带（靠近边缘但未到 2px 的区域）
          - None：窗口内部（正常交互）或最外圈阴影
        """
        if self._window.isMaximized():
            return None
        inner = self._shell._inner_rect()
        x, y = p.x(), p.y()
        e, m_out, m_in = self.EDGE_OUT, self.MOVE_OUT, self.MOVE_IN
        c = self.CORNER
        L, R, T, B = inner.left(), inner.right(), inner.top(), inner.bottom()
        # 四角优先：以圆角圆心为基准的环形窄带
        #   resize：弧线 ±2px；move：弧外 2~7px；弧内深处 = 正常内容
        for name, cx, cy in (
            ("tl", L + c, T + c),
            ("tr", R - c, T + c),
            ("bl", L + c, B - c),
            ("br", R - c, B - c),
        ):
            if name == "tl":
                ok = x <= cx and y <= cy
            elif name == "tr":
                ok = x >= cx and y <= cy
            elif name == "bl":
                ok = x <= cx and y >= cy
            else:
                ok = x >= cx and y >= cy
            if not ok:
                continue
            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            if (c - e) ** 2 <= d2 <= (c + e) ** 2:
                return name
            if (c + e) ** 2 < d2 <= (c + m_out) ** 2:
                return self.MOVE
            return None
        # 非角区：左右边缘（纵向中间段，避开四角弧区）
        if y > T + c and y < B - c:
            if L - e <= x <= L + e:
                return "l"
            if R - e <= x <= R + e:
                return "r"
            if (L - m_out < x < L - e) or (R + e < x < R + m_out):
                return self.MOVE
            if (L + e < x <= L + m_in) or (R - m_in <= x < R - e):
                return self.MOVE
        # 非角区：上下边缘（横向中间段，避开四角弧区）
        if x > L + c and x < R - c:
            if T - e <= y <= T + e:
                return "t"
            if B - e <= y <= B + e:
                return "b"
            if (T - m_out < y < T - e) or (B + e < y < B + m_out):
                return self.MOVE
            if (T + e < y <= T + m_in) or (B - m_in <= y < B - e):
                return self.MOVE
        return None

    def _pos_in_shell(self, event):
        """把任意控件上的鼠标事件坐标统一换算到外壳坐标系。"""
        return self._shell.mapFromGlobal(event.globalPosition().toPoint())

    def _do_resize(self, event):
        win = self._window
        gp = event.globalPosition().toPoint()
        g = self._start_geom
        dx = gp.x() - self._start_gp.x()
        dy = gp.y() - self._start_gp.y()
        left, top = g.left(), g.top()
        right, bottom = g.right(), g.bottom()
        if "l" in self._dir:
            left = g.left() + dx
        if "r" in self._dir:
            right = g.right() + dx
        if "t" in self._dir:
            top = g.top() + dy
        if "b" in self._dir:
            bottom = g.bottom() + dy
        min_w, min_h = win.minimumWidth(), win.minimumHeight()
        if right - left < min_w:
            if "l" in self._dir:
                left = right - min_w
            else:
                right = left + min_w
        if bottom - top < min_h:
            if "t" in self._dir:
                top = bottom - min_h
            else:
                bottom = top + min_h
        win.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)))

    def eventFilter(self, obj, event):
        t = event.type()
        # 动态新增子控件时启用鼠标跟踪（保证光标能实时恢复）
        if t in (QEvent.Type.ChildAdded, QEvent.Type.ChildPolished):
            if isinstance(obj, QWidget) and obj.window() is self._window:
                child = event.child()
                if isinstance(child, QWidget):
                    child.setMouseTracking(True)
                    for c in child.findChildren(QWidget):
                        c.setMouseTracking(True)
            return False
        # 只处理本窗口（含其子控件）的事件，避免干扰其他窗口
        if not isinstance(obj, QWidget) or obj.window() is not self._window:
            return False
        if t == QEvent.Type.MouseMove:
            if self._dir and (event.buttons() & Qt.MouseButton.LeftButton):
                self._do_resize(event)
                return True
            if self._move is not None and (
                event.buttons() & Qt.MouseButton.LeftButton
            ):
                self._window.move(event.globalPosition().toPoint() - self._move)
                return True
            # 无论鼠标在哪，实时按命中区更新光标：
            # 只有进入 2px resize 带才变拉动光标，移回内部立即恢复普通光标
            d = self._hit(self._pos_in_shell(event))
            self._window.setCursor(
                self._CURSORS.get(d, Qt.CursorShape.ArrowCursor)
            )
        elif (
            t == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            d = self._hit(self._pos_in_shell(event))
            if d in self._CURSORS:
                # 光标已是拉动样式（2px 带内）→ 才允许调整大小
                self._dir = d
                self._start_geom = self._window.geometry()
                self._start_gp = event.globalPosition().toPoint()
                return True
            if d == self.MOVE and not self._is_interactive(obj):
                # 靠近边缘但未到 2px：拖动 = 移动窗口位置
                self._move = (
                    event.globalPosition().toPoint()
                    - self._window.frameGeometry().topLeft()
                )
                return True
        elif t == QEvent.Type.MouseButtonRelease:
            if self._dir:
                self._dir = None
                self._window.setCursor(Qt.CursorShape.ArrowCursor)
                return True
            if self._move is not None:
                self._move = None
                return True
        elif t == QEvent.Type.Leave:
            if obj is self._shell:
                self._window.setCursor(Qt.CursorShape.ArrowCursor)
        return super().eventFilter(obj, event)

    @staticmethod
    def _is_interactive(obj):
        """交互控件上不劫持为移动窗口，保证按钮/滑块等正常点击。"""
        from PySide6.QtWidgets import (
            QAbstractButton,
            QAbstractScrollArea,
            QAbstractSlider,
            QAbstractSpinBox,
            QComboBox,
        )

        return isinstance(
            obj,
            (QAbstractButton, QAbstractSlider, QAbstractSpinBox,
             QAbstractScrollArea, QComboBox),
        )


# ---------------------------------------------------------------------------
# 屏幕适配：多分辨率下按比例缩放默认窗口大小 + 居中到屏幕中央
# ---------------------------------------------------------------------------

BASE_SCREEN_W = 1920   # 设计基准分辨率（在此分辨率下默认尺寸 = 原始设计值）
BASE_SCREEN_H = 1080
MIN_SCALE = 0.7        # 小屏最小缩放（防止窗口小到不可用）
MAX_SCALE = 2.0        # 大屏（4K 等）最大缩放
MAX_RATIO = 0.92       # 窗口不超过屏幕可用区的 92%，保证边缘可拉动


def scaled_window_size(
    screen_w: int,
    screen_h: int,
    base_w: int,
    base_h: int,
    min_w: int = 0,
    min_h: int = 0,
) -> tuple:
    """按屏幕分辨率等比缩放默认窗口尺寸（纯函数，便于测试）。

    - 以 1920×1080 为基准：同比例屏幕尺寸不变，4K/带鱼屏放大，小屏缩小；
    - 结果不小于 min_w/min_h（窗口最小尺寸），也不超过屏幕可用区的 92%。
    """
    scale = min(screen_w / BASE_SCREEN_W, screen_h / BASE_SCREEN_H)
    scale = max(MIN_SCALE, min(MAX_SCALE, scale))
    w = int(base_w * scale)
    h = int(base_h * scale)
    w = max(w, min_w)
    h = max(h, min_h)
    w = min(w, int(screen_w * MAX_RATIO))
    h = min(h, int(screen_h * MAX_RATIO))
    return w, h


def _screen_geometry(window) -> QRect:
    """窗口所在屏幕的可用区域（去掉任务栏）；找不到时退回主屏。"""
    screen = window.screen()
    if screen is None:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return QRect(0, 0, 1920, 1080)
    return screen.availableGeometry()


def center_on_screen(window):
    """把窗口移动到所在屏幕的中央（不改变窗口大小）。"""
    geo = _screen_geometry(window)
    w, h = window.width(), window.height()
    window.move(
        geo.x() + max(0, (geo.width() - w) // 2),
        geo.y() + max(0, (geo.height() - h) // 2),
    )


def fit_to_screen(window, base_w: int, base_h: int, min_w: int = 0, min_h: int = 0):
    """按当前屏幕分辨率缩放窗口到适配尺寸，并居中显示。

    各窗口在 __init__ 中调用（如 fit_to_screen(self, 1280, 800, 960, 620)）。
    """
    geo = _screen_geometry(window)
    w, h = scaled_window_size(
        geo.width(), geo.height(), base_w, base_h, min_w, min_h
    )
    window.resize(w, h)
    center_on_screen(window)
