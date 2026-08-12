# -*- coding: utf-8 -*-
"""冒烟测试：不弹窗（offscreen 模式）验证打包、识别、播放器控件逻辑。"""
import math
import os
import struct
import sys
import tempfile
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from bundle import Bundle, BundleError, create_bundle, extract_bundle, is_bundle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = QApplication(sys.argv)  # 生成测试图片也需要 QGuiApplication

FAIL = []


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        FAIL.append(name)


def make_image(path, w, h, color, text):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    p = QPainter(img)
    p.setPen(QColor("#ffffff"))
    p.setFont(QFont("Arial", 28, QFont.Weight.Bold))
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    assert img.save(path, "PNG"), f"保存图片失败: {path}"


def make_wav(path, seconds=3, freq=440, rate=44100):
    n = int(rate * seconds)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", v)
        wf.writeframes(bytes(frames))


def main():
    # 播放器把播放模式/音量持久化到 player_state.ini；测试改用临时
    # 状态文件，既不影响用户设置，也保证每次测试都从"顺序播放"开始。
    from PySide6.QtCore import QSettings

    test_state_ini = os.path.join(
        tempfile.gettempdir(), f"pmb_test_state_{os.getpid()}.ini"
    )
    os.environ["PMB_STATE_INI"] = test_state_ini
    st = QSettings(test_state_ini, QSettings.Format.IniFormat)
    st.setValue("play_mode", "顺序播放")
    st.setValue("volume", 80)
    st.sync()

    tmp = tempfile.mkdtemp(prefix="smoke_")
    img1 = os.path.join(tmp, "photo_a.png")
    img2 = os.path.join(tmp, "photo_b.png")
    song = os.path.join(tmp, "song.wav")
    make_image(img1, 800, 500, "#3a4a8f", "照片 1")
    make_image(img2, 800, 500, "#8f5b3a", "照片 2")
    make_wav(song, seconds=2)

    bundle_path = os.path.join(tmp, "test.pmb")
    create_bundle("冒烟测试相册", [img1, img2], [song], bundle_path)
    check("create_bundle 生成文件", os.path.exists(bundle_path))
    check("is_bundle 识别为合法", is_bundle(bundle_path))
    check("is_bundle 拒绝非包文件", not is_bundle(__file__))

    b = Bundle(bundle_path)
    check("Bundle 打开成功", b.title == "冒烟测试相册")
    check("图片数量=2", len(b.images) == 2)
    check("音乐数量=1", len(b.musics) == 1)
    check("解压后图片可读", os.path.exists(b.asset_path(b.images[0]["path"])))

    # ---- 序号前缀：包内文件带 0001_ 前缀，manifest 保留原始名 ----
    check("图片1包内名带前缀", b.images[0]["path"].endswith("0001_photo_a.png"))
    check("图片2包内名带前缀", b.images[1]["path"].endswith("0002_photo_b.png"))
    check("音乐包内名带前缀", b.musics[0]["path"].endswith("0001_song.wav"))
    check("manifest 图片名保留原始名", b.images[0]["name"] == "photo_a.png")
    check("manifest 音乐名保留原始名", b.musics[0]["name"] == "song.wav")

    # ---- 拆解：还原原始文件名，不带序号前缀 ----
    extract_dir = os.path.join(tmp, "extract")
    os.makedirs(extract_dir, exist_ok=True)
    extracted = extract_bundle(bundle_path, extract_dir)
    img_names = sorted(os.listdir(os.path.join(extracted, "图片")))
    music_names = sorted(os.listdir(os.path.join(extracted, "音乐")))
    check("拆解图片名还原无前缀", img_names == ["photo_a.png", "photo_b.png"])
    check("拆解音乐名还原无前缀", music_names == ["song.wav"])

    # ---- 图片允许重名：显示名相同，包内靠序号前缀区分 ----
    dup_a = os.path.join(tmp, "dup_a")
    dup_b = os.path.join(tmp, "dup_b")
    os.makedirs(dup_a, exist_ok=True)
    os.makedirs(dup_b, exist_ok=True)
    make_image(os.path.join(dup_a, "同款.png"), 300, 200, "#222222", "A")
    make_image(os.path.join(dup_b, "同款.png"), 300, 200, "#444444", "B")
    dup_path = os.path.join(tmp, "dup.pmb")
    create_bundle(
        "重名相册",
        [os.path.join(dup_a, "同款.png"), os.path.join(dup_b, "同款.png")],
        [],
        dup_path,
    )
    bd = Bundle(dup_path)
    check("重名图片数量=2", len(bd.images) == 2)
    check("重名图片显示名相同", bd.images[0]["name"] == bd.images[1]["name"] == "同款.png")
    check("重名图片包内路径不同", bd.images[0]["path"] != bd.images[1]["path"])
    extract_dir2 = os.path.join(tmp, "extract_dup")
    os.makedirs(extract_dir2, exist_ok=True)
    extracted2 = extract_bundle(dup_path, extract_dir2)
    dup_out = sorted(os.listdir(os.path.join(extracted2, "图片")))
    check("重名图片拆解不覆盖", len(dup_out) == 2 and "同款 (2).png" in dup_out)
    bd.close()

    # 数据层兼容旧包：manifest 显示名允许重复（旧版本产物），
    # 界面层已禁止产生新的重名
    named_dup_path = os.path.join(tmp, "named_dup.pmb")
    create_bundle(
        "显示重名",
        [img1, img2],
        [],
        named_dup_path,
        image_names=["同款.png", "同款.png"],
    )
    bnd = Bundle(named_dup_path)
    check("显示重名 manifest 名相同",
          bnd.images[0]["name"] == bnd.images[1]["name"] == "同款.png")
    check("显示重名包内路径不同", bnd.images[0]["path"] != bnd.images[1]["path"])
    bnd.close()

    # GUI 部分
    from player_window import PlayerWindow

    win = PlayerWindow(b)
    win.show()
    check("播放器窗口创建", win.windowTitle() == "冒烟测试相册 · 音乐相册")
    check("播放器无边框", bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint))
    check("播放器透明背景", win.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
    check("播放器标题栏显示相册名",
          win._tb_title.title_label.text() == "冒烟测试相册")
    win._title_bar = win._tb_title
    check("默认显示第 1 张", win.image_index == 0)
    win._show_image(1)
    check("切到第 2 张", win.image_index == 1)
    win._show_image(2)  # 越界循环回第 1 张
    check("越界循环回第 1 张", win.image_index == 0)
    win._select_music(0)
    check("默认选第 1 首音乐", win.music_index == 0)
    check("音乐列表按钮隐藏(仅1首)", not win.list_btn.isVisible())
    # offscreen 无音频设备无法真实播放，用 fake player 验证播放/暂停分支逻辑
    from PySide6.QtMultimedia import QMediaPlayer

    class FakePlayer:
        def __init__(self):
            self.state = QMediaPlayer.PlaybackState.StoppedState
            self.calls = []
        def playbackState(self):
            return self.state
        def play(self):
            self.state = QMediaPlayer.PlaybackState.PlayingState
            self.calls.append("play")
        def pause(self):
            self.state = QMediaPlayer.PlaybackState.PausedState
            self.calls.append("pause")
        def stop(self):
            self.state = QMediaPlayer.PlaybackState.StoppedState
            self.calls.append("stop")
        def setSource(self, url):
            self.calls.append(("source", url))
        def setPosition(self, pos):
            self.calls.append(("seek", pos))
        def duration(self):
            return 10000

    fake = FakePlayer()
    win.player = fake
    check("单曲时导航按钮禁用",
          not win.prev_music_btn.isEnabled() and not win.next_music_btn.isEnabled())
    check("默认播放模式=顺序", win.play_mode == "顺序播放")
    win.play_btn.setText("▶ 播放")
    win._toggle_play()
    check("暂停态点击→播放", "暂停" in win.play_btn.text() and fake.calls == ["play"])
    win._toggle_play()
    check("播放态点击→暂停", "播放" in win.play_btn.text() and fake.calls == ["play", "pause"])
    win._on_volume(0)
    check("音量归零图标静音", win.vol_icon.text() == "🔇")
    win._on_volume(66)
    check("音量 66 恢复图标", win.vol_icon.text() == "🔊")

    # ---- 三首歌：导航按钮 + 播放模式 ----
    song2 = os.path.join(tmp, "song2.wav")
    song3 = os.path.join(tmp, "song3.wav")
    make_wav(song2, seconds=2, freq=554)
    make_wav(song3, seconds=2, freq=659)
    b3_path = os.path.join(tmp, "three.pmb")
    create_bundle("三曲相册", [img1, img2], [song, song2, song3], b3_path)
    b3 = Bundle(b3_path)
    win3 = PlayerWindow(b3)
    win3.show()
    check("3首歌时导航按钮启用",
          win3.prev_music_btn.isEnabled() and win3.next_music_btn.isEnabled())
    win3.player = fake
    check("默认模式=顺序播放", win3.play_mode == "顺序播放")
    win3._on_status(QMediaPlayer.MediaStatus.EndOfMedia)
    check("顺序模式播完切下一首", win3.music_index == 1)
    win3._cycle_mode()
    check("切到单曲循环", win3.play_mode == "单曲循环")
    win3._on_status(QMediaPlayer.MediaStatus.EndOfMedia)
    check("单曲循环不切歌", win3.music_index == 1 and ("seek" in [c[0] for c in fake.calls if isinstance(c, tuple)]))
    win3._cycle_mode()
    check("切到随机播放", win3.play_mode == "随机播放")
    win3._on_status(QMediaPlayer.MediaStatus.EndOfMedia)
    check("随机模式切到未播曲", win3.music_index in (0, 2))
    win3._on_status(QMediaPlayer.MediaStatus.EndOfMedia)
    check("随机模式继续未播曲", win3.music_index in (0, 1, 2))
    win3._on_status(QMediaPlayer.MediaStatus.EndOfMedia)
    check("随机模式新一轮", win3.music_index in (0, 1, 2))
    win3._cycle_mode()
    check("模式循环回到顺序播放", win3.play_mode == "顺序播放")
    cur = win3.music_index
    win3._next_music()
    check("手动下一首按列表顺序", win3.music_index == (cur + 1) % 3)
    win3._prev_music()
    check("手动上一首回退", win3.music_index == cur)
    win3._cycle_mode()  # 顺序 → 单曲
    win3._cycle_mode()  # 单曲 → 随机
    win3._next_music()  # 随机模式下手动下一首从未播池取
    check("随机模式手动下一首", win3.music_index != cur)
    win3.close()
    b3.close()

    # ---- 无边框主题：主窗口 + 创建窗口 ----
    from main import MainWindow
    from creator_window import CreatorWindow

    mw = MainWindow()
    mw.show()
    check("主窗口无边框", bool(mw.windowFlags() & Qt.WindowType.FramelessWindowHint))
    check("主窗口透明背景",
          mw.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
    check("主窗口有圆角容器",
          hasattr(mw, "_tb_content") and mw._tb_content.objectName() == "appContent")
    check("主窗口有自绘标题栏", hasattr(mw, "_tb_title"))
    tb = mw._tb_title
    check("标题栏含最小化/最大化/关闭按钮",
          tb.min_btn is not None and tb.max_btn is not None and tb.close_btn is not None)
    mw.showMaximized()
    mw._tb_title.sync_max_state()
    check("最大化后圆角关闭", mw._tb_shell.property("tbMax") is True)
    check("最大化图标切换为还原", tb.max_btn.text() == "❐")
    mw.showNormal()
    mw._tb_title.sync_max_state()
    check("还原后圆角恢复", mw._tb_shell.property("tbMax") is False)

    # 边缘拉动命中区应与圆角内容边缘对齐（含四角）
    shell = mw._tb_shell
    inner = shell._inner_rect()
    helper = mw._tb_helper
    cx = int((inner.left() + inner.right()) / 2)
    cy = int((inner.top() + inner.bottom()) / 2)
    L, R, T, B = (int(inner.left()), int(inner.right()),
                  int(inner.top()), int(inner.bottom()))
    # resize 只在内容边缘 2px 内触发（光标变拉动样式后才能拉动）
    check("左边缘命中 l", helper._hit(QPoint(L - 1, cy)) == "l")
    check("右边缘命中 r", helper._hit(QPoint(R + 1, cy)) == "r")
    check("上边缘命中 t", helper._hit(QPoint(cx, T - 1)) == "t")
    check("下边缘命中 b", helper._hit(QPoint(cx, B + 1)) == "b")
    # 靠近边缘但未到 2px：拖动窗口移动位置（不触发缩放）
    check("左外4px为移动区", helper._hit(QPoint(L - 4, cy)) == helper.MOVE)
    check("右外4px为移动区", helper._hit(QPoint(R + 4, cy)) == helper.MOVE)
    check("上外4px为移动区", helper._hit(QPoint(cx, T - 4)) == helper.MOVE)
    check("下外4px为移动区", helper._hit(QPoint(cx, B + 4)) == helper.MOVE)
    check("左内4px为移动区", helper._hit(QPoint(L + 4, cy)) == helper.MOVE)
    check("右内4px为移动区", helper._hit(QPoint(R - 4, cy)) == helper.MOVE)
    check("上内4px为移动区", helper._hit(QPoint(cx, T + 4)) == helper.MOVE)
    check("下内4px为移动区", helper._hit(QPoint(cx, B - 4)) == helper.MOVE)
    # 四角判定区：半径与圆角一致（14px），弧线 ±2px 内触发对角缩放
    Rc = int(helper.CORNER)
    check("左上角命中 tl", helper._hit(QPoint(L, T + Rc)) == "tl")
    check("右上角命中 tr", helper._hit(QPoint(R, T + Rc)) == "tr")
    check("左下角命中 bl", helper._hit(QPoint(L, B - Rc)) == "bl")
    check("右下角命中 br", helper._hit(QPoint(R, B - Rc)) == "br")
    # 弧线窄带：弧内 2px 仍命中（只在最外圈有效）
    check("四角-左上弧内2px命中", helper._hit(QPoint(L + Rc, T + 2)) == "tl")
    check("四角-右上弧内2px命中", helper._hit(QPoint(R - Rc, T + 2)) == "tr")
    check("四角-左下弧内2px命中", helper._hit(QPoint(L + Rc, B - 2)) == "bl")
    check("四角-右下弧内2px命中", helper._hit(QPoint(R - Rc, B - 2)) == "br")
    # 弧外 2~7px：四角附近移动窗口（不触发缩放）
    check("四角-左上弧外为移动区", helper._hit(QPoint(L + Rc, T - 3)) == helper.MOVE)
    check("四角-右上弧外为移动区", helper._hit(QPoint(R - Rc, T - 3)) == helper.MOVE)
    check("四角-左下弧外为移动区", helper._hit(QPoint(L + Rc, B + 3)) == helper.MOVE)
    check("四角-右下弧外为移动区", helper._hit(QPoint(R - Rc, B + 3)) == helper.MOVE)
    # 弧线深处（角内 10px）不触发对角缩放：只在最外圈窄带有效
    check("四角-左上内10px不触发", helper._hit(QPoint(L + 10, T + 10)) is None)
    check("四角-右上内10px不触发", helper._hit(QPoint(R - 10, T + 10)) is None)
    check("四角-左下内10px不触发", helper._hit(QPoint(L + 10, B - 10)) is None)
    check("四角-右下内10px不触发", helper._hit(QPoint(R - 10, B - 10)) is None)
    # 圆角弧外（角外 30px 处）不应触发
    check("四角外不触发-左上", helper._hit(QPoint(L - 30, T - 30)) is None)
    check("窗口中央不触发拉动", helper._hit(QPoint(cx, cy)) is None)
    check("阴影最外圈不触发拉动", helper._hit(QPoint(0, cy)) is None)

    # 光标恢复：鼠标移到边缘（2px 内）变拉动光标，移回窗口内部立即恢复普通光标；
    # 移到靠近边缘的移动区（未到 2px）光标保持普通样式
    mw.setCursor(Qt.CursorShape.SizeHorCursor)
    ev_in = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(cx, cy), shell.mapToGlobal(QPointF(cx, cy)),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    helper.eventFilter(shell, ev_in)
    check("移回窗口内部光标恢复普通", mw.cursor().shape() == Qt.CursorShape.ArrowCursor)
    # 边缘处（2px 内）光标为拉动样式
    ev_edge = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(L - 1, cy), shell.mapToGlobal(QPointF(L - 1, cy)),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    helper.eventFilter(shell, ev_edge)
    check("移到边缘光标为拉动样式", mw.cursor().shape() == Qt.CursorShape.SizeHorCursor)
    # 移动区（内容外 4px）光标保持普通样式
    ev_move = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(L - 4, cy), shell.mapToGlobal(QPointF(L - 4, cy)),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    helper.eventFilter(shell, ev_move)
    check("移动区光标保持普通样式", mw.cursor().shape() == Qt.CursorShape.ArrowCursor)
    tb.set_title("改标题")
    check("标题栏标题可更新", tb.title_label.text() == "改标题")
    mw.close()

    cw = CreatorWindow()
    cw.show()
    check("创建窗口无边框",
          bool(cw.windowFlags() & Qt.WindowType.FramelessWindowHint))
    check("创建窗口有标题栏", hasattr(cw, "_tb_title"))
    cw.close()

    # ---- 编辑窗口：加载时去掉序号前缀，重编号恢复 ----
    from editor_window import EditorWindow

    ew = EditorWindow()
    check("编辑窗口加载成功", ew.load_bundle(bundle_path))
    check("编辑加载图片名无前缀",
          all(not os.path.basename(p).startswith("0001_") for p in ew.image_paths))
    check("编辑加载音乐名无前缀",
          all(not os.path.basename(p).startswith("0001_") for p in ew.music_paths))

    # 保存流：加载（去前缀）后直接打包，包内仍是单层序号前缀
    save_path = os.path.join(tmp, "saved.pmb")
    create_bundle("保存流", list(ew.image_paths), list(ew.music_paths), save_path)
    bs = Bundle(save_path)
    check("保存流包内名单层前缀", bs.images[0]["path"].endswith("0001_photo_a.png"))
    check("保存流 manifest 名无前缀", bs.images[0]["name"] == "photo_a.png")
    bs.close()

    ew._renumber_temp_files()
    check("编辑重编号图片",
          ew.image_paths[0].endswith("0001_photo_a.png")
          and ew.image_paths[1].endswith("0002_photo_b.png"))
    check("编辑重编号音乐", ew.music_paths[0].endswith("0001_song.wav"))
    ew.close()

    # 编辑界面重命名遇到重名直接失败并提示
    import editor_window as ew_mod

    ew4 = EditorWindow()
    check("重名编辑加载成功", ew4.load_bundle(bundle_path))
    ew4.image_list.setCurrentRow(1)
    ew4.image_list.item(1).setSelected(True)
    orig_dialog = ew_mod.show_input_dialog
    orig_warning = ew_mod.show_warning
    warnings = []
    ew_mod.show_input_dialog = lambda *a, **k: ("photo_a.png", True)
    ew_mod.show_warning = lambda *a, **k: warnings.append(a) or None
    try:
        ew4._rename_selected(ew4.image_list, ew4.image_paths)
    finally:
        ew_mod.show_input_dialog = orig_dialog
        ew_mod.show_warning = orig_warning
    check("重命名重名直接失败",
          len(warnings) == 1 and "重名" in str(warnings[0]))
    check("重命名失败后显示名未变",
          ew4.image_list.item_name(ew4.image_list.item(1)) == "photo_b.png")
    check("重命名失败后磁盘未变",
          os.path.basename(ew4.image_paths[1]) == "photo_b.png")
    ew4.close()

    # 加载含重名图片的包时，界面显示名带 " (2)" 后缀，不隐藏
    ew5 = EditorWindow()
    check("重名包编辑加载成功", ew5.load_bundle(dup_path))
    check("重名包第一项显示原名",
          ew5.image_list.item_name(ew5.image_list.item(0)) == "同款.png")
    check("重名包第二项显示后缀",
          ew5.image_list.item_name(ew5.image_list.item(1)) == "同款 (2).png")
    ew5.close()

    # 添加同名文件时自动生成不重复的显示名
    from sortable_list import SortableListWidget

    sl = SortableListWidget([])
    sl.add_item("x", "photo.png")
    check("唯一名-同名追加后缀", sl.unique_name("photo.png") == "photo (2).png")
    check("唯一名-不同名不变", sl.unique_name("other.png") == "other.png")
    sl.add_item("x", sl.unique_name("photo.png"))
    check("唯一名-后缀再同名继续递增", sl.item_name(sl.item(1)) == "photo (2).png")
    check("唯一名-第三个继续递增", sl.unique_name("photo.png") == "photo (3).png")

    # 悬停预览容器：深色圆角背景包裹图片
    from sortable_list import HoverImagePreview

    hp = HoverImagePreview()
    hp.show_image(img1, QPoint(100, 100))
    hp_pm = hp.grab()
    check("预览容器深色背景",
          hp_pm.toImage().pixelColor(2, hp_pm.height() // 2).name().lower()
          == "#1d2027")
    check("预览容器圆角外透明",
          hp_pm.toImage().pixelColor(1, 1).alpha() == 0)
    hp.hide_preview()

    # ---- 创建窗口：每次打开前重置为空 ----
    cw.image_paths.append(img1)
    cw.image_list.add_item(img1, os.path.basename(img1))
    cw.music_paths.append(song)
    cw.music_list.add_item(song, os.path.basename(song))
    check("图片列表关闭悬停名称提示",
          cw.image_list.item(0).toolTip() == "")
    check("音乐列表保留悬停名称提示",
          cw.music_list.item(0).toolTip() == os.path.basename(song))
    cw.title_edit.setText("残留标题")
    cw.reset()
    check("创建窗口重置图片列表",
          len(cw.image_paths) == 0 and cw.image_list.count() == 0)
    check("创建窗口重置标题", cw.title_edit.text() == "")

    win.close()
    app.processEvents()
    check("关闭后释放临时目录", b._tmpdir is None or not os.path.exists(b._tmpdir))

    # 坏文件拒绝
    bad = os.path.join(tmp, "bad.pmb")
    with open(bad, "w") as f:
        f.write("not a zip")
    try:
        Bundle(bad)
        check("坏文件被拒绝", False)
    except BundleError:
        check("坏文件被拒绝", True)

    print("=" * 40)
    if FAIL:
        print(f"冒烟测试失败 {len(FAIL)} 项: {FAIL}")
        sys.exit(1)
    print("冒烟测试全部通过")


if __name__ == "__main__":
    main()
