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

from PySide6.QtCore import QSettings, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSlider,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
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
        self._select_music(0)

    # ---------- UI ----------
    def _build_ui(self):
        _, _, inner = apply_frameless(self, self.bundle.title, icon=APP_ICON)
        root = QVBoxLayout()
        root.setContentsMargins(24, 6, 24, 16)
        root.setSpacing(10)
        inner.addLayout(root, 1)

        # ---- 图片鉴赏区 ----
        self.image_label = QLabel()
        self.image_label.setObjectName("gallery")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(320)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.prev_btn = QToolButton()
        self.prev_btn.setObjectName("navBtn")
        self.prev_btn.setText("‹")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setToolTip("上一张")
        self.prev_btn.clicked.connect(lambda: self._show_image(self.image_index - 1))

        self.next_btn = QToolButton()
        self.next_btn.setObjectName("navBtn")
        self.next_btn.setText("›")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setToolTip("下一张")
        self.next_btn.clicked.connect(lambda: self._show_image(self.image_index + 1))

        gallery_row = QHBoxLayout()
        gallery_row.setSpacing(4)
        gallery_row.addWidget(self.prev_btn)
        gallery_row.addWidget(self.image_label, 1)
        gallery_row.addWidget(self.next_btn)
        root.addLayout(gallery_row, 1)

        self.index_label = QLabel()
        self.index_label.setObjectName("indexLabel")
        self.index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 0)
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
        self.prev_music_btn.setToolTip("上一首")
        self.prev_music_btn.clicked.connect(self._prev_music)
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setObjectName("primaryBtn")
        self.play_btn.setFixedWidth(110)
        self.play_btn.clicked.connect(self._toggle_play)
        self.next_music_btn = QPushButton("下一首 ⏭")
        self.next_music_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_music_btn.setToolTip("下一首")
        self.next_music_btn.clicked.connect(self._next_music)
        self.mode_btn = QPushButton()
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.clicked.connect(self._cycle_mode)
        self._update_mode_button()
        self.vol_icon = QLabel("🔊")
        self.vol_icon.setObjectName("volIcon")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
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
        self.play_btn.setText("❚❚ 暂停")
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

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶ 播放")
        else:
            self.player.play()
            self.play_btn.setText("❚❚ 暂停")

    def _show_music_menu(self):
        """点击音乐列表按钮，弹出可选歌曲菜单。"""
        menu = QMenu(self)
        menu.setObjectName("musicMenu")
        for i, m in enumerate(self.musics):
            action = menu.addAction(f"{i + 1}. {m['name']}")
            action.setCheckable(True)
            action.setChecked(i == self.music_index)
            action.triggered.connect(lambda _=False, idx=i: self._select_music(idx))
        menu.exec(self.list_btn.mapToGlobal(self.list_btn.rect().bottomLeft()))

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
        self.index_label.setText(f"图片 {self.image_index + 1} / {len(self.images)}")
        self._update_image_display()

    def _update_image_display(self):
        """按当前控件尺寸等比缩放图片（保持纵横比）。"""
        if self._origin_pixmap is None:
            return
        size = self.image_label.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        scaled = self._origin_pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_image_display()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_image_display()

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
                self.play_btn.setText("▶ 播放")
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
