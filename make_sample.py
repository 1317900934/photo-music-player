# -*- coding: utf-8 -*-
"""生成示例音乐相册：3 张渐变风景图 + 3 首不同频率的音乐，打包为 .pmb。"""
import math
import os
import struct
import sys
import tempfile
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication

from bundle import create_bundle

app = QApplication(sys.argv)


def make_landscape(path, w, h, colors, text, sub):
    """用线性渐变画一张"风景"风格图片。"""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    grad = QLinearGradient(QPointF(0, 0), QPointF(0, h))
    for stop, c in enumerate(colors):
        grad.setColorAt(stop / max(1, len(colors) - 1), QColor(c))
    p.fillRect(QRectF(0, 0, w, h), grad)
    # 太阳
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 220, 130, 200))
    p.drawEllipse(int(w * 0.72), int(h * 0.18), 70, 70)
    # 文字
    p.setPen(QColor(255, 255, 255, 235))
    p.setFont(QFont("Microsoft YaHei", 34, QFont.Weight.Bold))
    p.drawText(QRectF(0, h * 0.36, w, 60), Qt.AlignmentFlag.AlignCenter, text)
    p.setFont(QFont("Microsoft YaHei", 15))
    p.setPen(QColor(255, 255, 255, 190))
    p.drawText(QRectF(0, h * 0.36 + 64, w, 30), Qt.AlignmentFlag.AlignCenter, sub)
    p.end()
    assert img.save(path, "PNG"), path


def make_melody(path, seconds, freq):
    """生成一段正弦波 wav，作为示例音乐。"""
    rate = 44100
    n = int(rate * seconds)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            env = min(1.0, i / (rate * 0.05), (n - i) / (rate * 0.08))  # 淡入淡出
            v = int(11000 * env * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", v)
        wf.writeframes(bytes(frames))


def main():
    tmp = tempfile.mkdtemp(prefix="sample_")
    imgs = [
        (os.path.join(tmp, "海边黄昏.png"), ["#1e3c72", "#2a5298", "#ff9a5a"], "海边黄昏", "2024 年夏天"),
        (os.path.join(tmp, "山间清晨.png"), ["#0f2027", "#203a43", "#2c5364"], "山间清晨", "一次说走就走的旅行"),
        (os.path.join(tmp, "城市夜色.png"), ["#141e30", "#243b55", "#6a3093"], "城市夜色", "与你走过的街头"),
    ]
    for path, colors, text, sub in imgs:
        make_landscape(path, 1280, 720, colors, text, sub)
    songs = [
        (os.path.join(tmp, "风之诗.wav"), 8, 440.0),
        (os.path.join(tmp, "星之语.wav"), 8, 554.37),
        (os.path.join(tmp, "海之韵.wav"), 8, 659.25),
    ]
    for path, sec, freq in songs:
        make_melody(path, sec, freq)
    out = os.path.join(os.path.expanduser("~"), "Desktop", "示例音乐相册.pmb")
    create_bundle("示例音乐相册", [i[0] for i in imgs], [s[0] for s in songs], out)
    print("OK:", out)
    print("存在:", os.path.exists(out))


if __name__ == "__main__":
    main()
